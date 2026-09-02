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

# Safety limits for live trading
SAFETY_LIMITS = {
    "max_position_size_percent": 5,      # Max 5% of account per trade
    "max_concurrent_positions": 3,       # Max 3 open at once
    "max_daily_loss_percent": 2,         # Stop if down 2% in a day
    "max_leverage": 1.0,                 # No margin/leverage for MVP
    "cooldown_seconds": 60,              # Min 60s between orders
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _quote_price(symbol: str, timeframe: str) -> float:
    return float(get_provider().get_ohlcv(symbol, timeframe)[-1]["close"])


def _get_user_broker(db: Session, config: models.AutoTradeConfig, timeframe: str):
    """Get broker for a config: use user's connected broker if available, else server-level."""
    if config.mode == "live" and config.broker_connection_id:
        from app.core.encryption import decrypt_value
        from app.services.broker_connector import BrokerConnector
        from app.services.alpaca_connector import AlpacaConnector
        from app.services.binance_connector import BinanceConnector

        conn = db.query(models.BrokerConnection).filter(
            models.BrokerConnection.id == config.broker_connection_id,
            models.BrokerConnection.user_id == config.user_id,
        ).first()
        if conn:
            api_key = decrypt_value(conn.api_key_encrypted)
            api_secret = decrypt_value(conn.api_secret_encrypted)
            if conn.broker_name == "alpaca":
                return AlpacaConnector(api_key, api_secret, conn.account_type)
            elif conn.broker_name == "binance":
                return BinanceConnector(api_key, api_secret)
    return get_broker(config.mode, timeframe)


def _safety_check(db: Session, config: models.AutoTradeConfig, account_balance: float, signal_size: float) -> bool:
    """Refuse order if any safety limit is violated."""
    # Check 1: Position size cap (max 5% of account)
    if account_balance > 0 and (signal_size / account_balance) > SAFETY_LIMITS["max_position_size_percent"] / 100:
        return False

    # Check 2: Max concurrent positions
    open_count = (
        db.query(models.Position)
        .filter(
            models.Position.user_id == config.user_id,
            models.Position.status == models.TradeStatus.OPEN.value,
        )
        .count()
    )
    if open_count >= SAFETY_LIMITS["max_concurrent_positions"]:
        return False

    # Check 3: Daily loss cap (if max_daily_loss is set)
    if config.max_daily_loss and config.capital > 0:
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
        if lost > 0 and lost / config.capital >= config.max_daily_loss:
            return False

    return True


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

    broker = _get_user_broker(db, config, strategy.timeframe)
    if broker is None:
        config.last_error = "Live trading armed but no broker connection configured."
        config.mode = "paper"
        db.commit()
        create_notification(
            db, config.user_id, "autotrade_error", "Live trading unavailable",
            config.last_error, strategy.user.email,
        )
        return {"skipped": True, "reason": config.last_error}

    # For broker connectors with async API, we need to handle sync wrappers
    from app.services.broker_connector import BrokerConnector as BC
    if isinstance(broker, BC):
        import asyncio
        account = asyncio.get_event_loop().run_until_complete(broker.get_account())
        capital = account.balance if config.mode == "live" else config.capital
    else:
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

    # Safety check before placing order
    if config.mode == "live" and not _safety_check(db, config, capital, size * entry):
        config.last_error = "Safety check failed (position size, concurrent positions, or daily loss)."
        db.commit()
        return {"skipped": True, "reason": config.last_error}

    # Place order via broker connector or legacy broker
    from app.services.broker_connector import BrokerConnector as BC
    if isinstance(broker, BC):
        import asyncio
        order = asyncio.get_event_loop().run_until_complete(
            broker.place_order(symbol, size, "buy", "market")
        )
        fill_price = order.filled_price or entry
        fill_qty = order.quantity
        fill_quote = fill_qty * fill_price
    else:
        fill = broker.buy_quote(symbol, round(size * entry, 8))
        fill_price = fill.price
        fill_qty = fill.base_qty
        fill_quote = fill.quote

    position = models.Position(
        user_id=config.user_id,
        strategy_id=strategy.id,
        symbol=symbol,
        direction="LONG",
        handler="autotrade",
        broker=broker.name if hasattr(broker, 'name') else config.mode,
        status=models.TradeStatus.OPEN.value,
        entry_price=fill_price,
        current_price=fill_price,
        stop_loss=stop,
        take_profit=suggestion.get("take_profit"),
        size=fill_qty,
        cost=fill_quote,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    create_notification(
        db, config.user_id, "position_opened", "Position opened",
        f"{broker.name if hasattr(broker, 'name') else config.mode} {symbol} LONG @ {fill_price} (size {fill_qty}) "
        f"stop {stop} / target {suggestion.get('take_profit') or '-'}.",
        strategy.user.email,
    )
    return {"opened": True, "position_id": position.id, "symbol": symbol, "price": fill_price}


def _close_position(db: Session, position: models.Position, reason: str, broker, current: float) -> dict:
    from app.services.broker_connector import BrokerConnector as BC

    if isinstance(broker, BC):
        import asyncio
        order = asyncio.get_event_loop().run_until_complete(
            broker.close_position(position.symbol)
        )
        fill_price = order.filled_price or current
    else:
        fill = broker.sell_base(position.symbol, position.size)
        fill_price = fill.price

    position.exit_reason = reason
    position.current_price = fill_price
    position.status = models.TradeStatus.CLOSED.value
    position.closed_at = _now()
    position.realized_pnl = round((fill_price - position.entry_price) * position.size, 8)
    position.pnl_percent = round((fill_price - position.entry_price) / position.entry_price * 100.0, 4)
    db.commit()
    create_notification(
        db, position.user_id, "position_closed", "Position closed",
        f"{position.symbol} {position.direction} closed ({reason}) @ {fill_price} "
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

        # Get broker for this position
        from app.services.broker_connector import BrokerConnector as BC
        broker = _get_user_broker(db, config, strategy.timeframe) or get_broker("paper", strategy.timeframe)

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