# app/services/autotrade.py
"""Autonomous trading engine.

Repeatedly scans each user's auto-trade-enabled strategies against fresh market
data (Binance when ``MARKET_DATA_PROVIDER=binance``, simulated otherwise),
opens paper (or armed-live) positions on fresh signals and manages exits via
stop-loss, take-profit and the strategy's exit rules.

Safety-first by default:
  - PAPER execution unless a strategy is explicitly armed and Binance keys exist.
  - Hard caps: max concurrent positions, per-trade risk % of capital, optional
    per-day loss limit and a cooldown between re-entries.
  - Only LONG spot execution (SHORT requires margin and is rejected).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.services.backtest_engine import RuleContext, evaluate_rule_group
from app.services.broker import Broker, get_broker
from app.services.market_data_service import get_provider, normalize_symbol
from app.services.notification_service import create_notification
from app.services.signal_engine import (
    build_strategy_rules_dict,
    describe_rule,
    generate_signal,
    reasons_for_group,
)

logger = logging.getLogger("tradepilot.autotrade")

# Module-level engine state surfaced by GET /autotrade/status.
STATE = {"running": False, "last_run_at": None, "last_error": None, "strategies_watched": 0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _quote_price(symbol: str, timeframe: str) -> float:
    return float(get_provider().get_ohlcv(symbol, timeframe)[-1]["close"])


def _position_pnl(position: models.Position, current: float) -> tuple:
    if not position.entry_price:
        return 0.0, 0.0
    if position.direction == "LONG":
        unrealized = (current - position.entry_price) * position.size
        pct = (current - position.entry_price) / position.entry_price * 100.0
    else:
        unrealized = (position.entry_price - current) * position.size
        pct = (position.entry_price - current) / position.entry_price * 100.0
    return round(unrealized, 8), round(pct, 4)


def _daily_loss_blocked(db: Session, config: models.AutoTradeConfig) -> bool:
    if not config.max_daily_loss:
        return False
    today = _now().date()
    day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    closed = (
        db.query(models.Position)
        .filter(
            models.Position.user_id == config.user_id,
            models.Position.strategy_id == config.strategy_id,
            models.Position.status == models.TradeStatus.CLOSED.value,
            models.Position.closed_at >= day_start,
        )
        .all()
    )
    lost = -sum(p.realized_pnl or 0.0 for p in closed)
    return lost > 0 and lost / config.capital >= config.max_daily_loss


def _in_cooldown(db: Session, config: models.AutoTradeConfig) -> bool:
    last = (
        db.query(models.Position)
        .filter(
            models.Position.user_id == config.user_id,
            models.Position.strategy_id == config.strategy_id,
        )
        .order_by(models.Position.opened_at.desc())
        .first()
    )
    if last is None:
        return False
    opened = last.opened_at
    if opened and opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    return opened and opened + timedelta(minutes=config.cooldown_minutes) > _now()


def _open_position(db: Session, config: models.AutoTradeConfig, strategy: models.Strategy, suggestion: dict) -> dict:
    symbol = normalize_symbol(suggestion["symbol"])
    direction = (suggestion["direction"] or "LONG").upper()

    if direction != "LONG":
        config.last_error = "SHORT auto-trading requires margin; only LONG supported on spot."
        db.commit()
        return {"skipped": True, "reason": config.last_error}

    entry = suggestion.get("entry_price")
    stop = suggestion.get("stop_loss")
    if not entry:
        entry = _quote_price(symbol, strategy.timeframe)
    if not stop:
        stop = entry * 0.98  # no explicit stop -> 2% default

    broker = get_broker(config.mode, strategy.timeframe)
    if broker is None:
        config.last_error = "Live trading armed but BINANCE_API_KEY/BINANCE_API_SECRET are not configured."
        config.mode = "paper"
        db.commit()
        create_notification(
            db, config.user_id, "autotrade_error", "Live trading unavailable",
            config.last_error, strategy.user.email,
        )
        return {"skipped": True, "reason": config.last_error}

    capital = config.capital if config.mode == "live" else config.capital or 0.0
    risk_amount = capital * (config.risk_percent / 100.0)
    sl_distance = abs(entry - stop) or entry * 0.001
    size = risk_amount / sl_distance
    size = min(size, capital / entry)  # never commit more than the assigned capital
    size = round(size, 8)
    if size <= 0:
        config.last_error = "Position size is zero; check risk/capital settings."
        db.commit()
        return {"skipped": True, "reason": config.last_error}

    fill = broker.buy_quote(symbol, round(size * entry, 8))
    position = models.Position(
        user_id=config.user_id,
        strategy_id=strategy.id,
        symbol=symbol,
        direction="LONG",
        handler="autotrade",
        broker=broker.name,
        status=models.TradeStatus.OPEN.value,
        entry_price=fill.price,
        current_price=fill.price,
        stop_loss=stop,
        take_profit=suggestion.get("take_profit"),
        size=fill.base_qty,
        cost=fill.quote,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    create_notification(
        db, config.user_id, "position_opened", "Position opened",
        f"{broker.name.upper()} {symbol} LONG @ {fill.price} (size {fill.base_qty}) "
        f"stop {stop} / target {suggestion.get('take_profit') or '-'}.",
        strategy.user.email,
    )
    return {"opened": True, "position_id": position.id, "symbol": symbol, "price": fill.price}


def _close_position(db: Session, position: models.Position, reason: str, broker: Broker, current: float) -> dict:
    fill = broker.sell_base(position.symbol, position.size)
    position.exit_reason = reason
    position.current_price = fill.price
    position.status = models.TradeStatus.CLOSED.value
    position.closed_at = _now()
    position.realized_pnl = round((fill.price - position.entry_price) * position.size, 8)
    position.pnl_percent = round((fill.price - position.entry_price) / position.entry_price * 100.0, 4)
    db.commit()
    create_notification(
        db, position.user_id, "position_closed", "Position closed",
        f"{position.symbol} {position.direction} closed ({reason}) @ {fill.price} "
        f"PnL {position.realized_pnl:.2f} ({position.pnl_percent:+.2f}%)",
        "",
    )
    return {"closed": True, "position_id": position.id, "reason": reason, "pnl": position.realized_pnl}


def _manage_open_positions(db: Session, config: models.AutoTradeConfig, strategy: models.Strategy, reason_exit: bool) -> None:
    for position in (
        db.query(models.Position)
        .filter(
            models.Position.user_id == config.user_id,
            models.Position.strategy_id == strategy.id,
            models.Position.status == models.TradeStatus.OPEN.value,
        )
        .all()
    ):
        current = _quote_price(position.symbol, strategy.timeframe)
        position.current_price = current
        position.unrealized_pnl, position.pnl_percent = _position_pnl(position, current)
        broker = get_broker(position.broker, strategy.timeframe) or get_broker("paper", strategy.timeframe)

        hit = None
        if position.direction == "LONG":
            if position.stop_loss and current <= position.stop_loss:
                hit = "stop_loss"
            elif position.take_profit and current >= position.take_profit:
                hit = "take_profit"
        elif position.direction == "SHORT":
            if position.stop_loss and current >= position.stop_loss:
                hit = "stop_loss"
            elif position.take_profit and current <= position.take_profit:
                hit = "take_profit"
        if hit is None and reason_exit:
            hit = "exit_rule"

        if hit:
            _close_position(db, position, hit, broker, current)


def _entry_and_exit_fired(strategy: models.Strategy) -> tuple:
    """Evaluate entry vs exit on the latest bar.

    Unlike ``generate_signal`` (which treats an empty exit group as 'exit now'),
    auto-trade treats *no exit rules* as "hold until stop/target": empty exit
    groups do NOT fire a signal blocker or a close.
    """
    bars = get_provider().get_ohlcv(strategy.asset, strategy.timeframe)
    rctx = RuleContext(bars)
    i = len(bars) - 1
    rules = build_strategy_rules_dict(strategy)["rules"]
    entry_fired = evaluate_rule_group(rctx, i, rules.get("entry", {"logic": "all", "conditions": []}))
    confirm_fired = evaluate_rule_group(
        rctx, i, rules.get("confirmation", {"logic": "all", "conditions": []})
    )
    exit_group = rules.get("exit", {"logic": "any", "conditions": []})
    exit_conditions = (exit_group or {}).get("conditions", [])
    exit_fired = bool(exit_conditions) and evaluate_rule_group(rctx, i, exit_group)
    return bool(entry_fired and confirm_fired and not exit_fired), bool(exit_fired and exit_conditions)


def _scan_config(db: Session, config: models.AutoTradeConfig) -> None:
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == config.strategy_id, models.Strategy.user_id == config.user_id)
        .first()
    )
    if strategy is None or not strategy.is_active:
        config.enabled = False
        config.last_error = "Strategy missing or inactive; auto-trade disabled."
        db.commit()
        return

    try:
        suggestion = generate_signal(
            build_strategy_rules_dict(strategy), strategy.asset, strategy.timeframe
        )
        signal_fires, exit_fired = _entry_and_exit_fired(strategy)
    except ValueError as exc:
        config.last_error = str(exc)
        db.commit()
        return

    _manage_open_positions(db, config, strategy, reason_exit=exit_fired)

    if not signal_fires:
        config.last_error = None
        config.last_run_at = _now()
        db.commit()
        return

    if _daily_loss_blocked(db, config):
        config.last_error = "Daily loss limit reached; new entries blocked."
        db.commit()
        return

    open_count = (
        db.query(models.Position)
        .filter(
            models.Position.user_id == config.user_id,
            models.Position.status == models.TradeStatus.OPEN.value,
        )
        .count()
    )
    if open_count >= config.max_concurrent:
        config.last_error = f"Concurrent position limit ({config.max_concurrent}) reached."
        db.commit()
        return

    if _in_cooldown(db, config):
        config.last_error = f"In cooldown ({config.cooldown_minutes} min)."
        db.commit()
        return

    result = _open_position(db, config, strategy, suggestion)
    if not result.get("skipped"):
        config.last_error = None
    config.last_run_at = _now()
    db.commit()


def run_once() -> dict:
    """One full scan cycle across every enabled auto-trade config."""
    from app.db.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        configs = (
            db.query(models.AutoTradeConfig).filter(models.AutoTradeConfig.enabled.is_(True)).all()
        )
        STATE["strategies_watched"] = len(configs)
        for config in configs:
            try:
                if config.user.is_active is False:
                    continue
                _scan_config(db, config)
            except Exception as exc:  # one bad strategy must not stop the loop
                logger.exception("autotrade scan failed for config %s", config.id)
                config.last_error = str(exc)[:400]
                db.commit()
        STATE["last_run_at"] = datetime.now(timezone.utc)
        STATE["last_error"] = None
        return {"configs": len(configs), "last_run_at": STATE["last_run_at"]}
    except Exception as exc:
        STATE["last_error"] = str(exc)
        logger.exception("autotrade cycle failed")
        return {"configs": 0, "error": str(exc)}
    finally:
        db.close()