# app/db/seed.py
"""Deterministic demo data seeding.

The demo user receives a realistic, clearly-simulated portfolio so a sales demo
works out of the box with no external services or API keys. Runs idempotently.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import generate_webhook_secret
from app.db.database import SessionLocal, Base, engine
from app.db import models
from app.services import ai_strategy_service, backtest_engine
from app.services.backtest_engine import strategy_to_engine_form
from app.services.market_data_service import get_provider

logger = logging.getLogger("tradepilot.seed")

Base.metadata.create_all(bind=engine)

DEMO_EMAIL = "demo@tradepilot.ai"
RISK_AMOUNT = 100.0  # deterministic risk/unit for demo paper trades

# Lock to prevent concurrent seeding operations that could lock SQLite
_seeding_lock = threading.Lock()

# Curated demo outcome profile (R multiples) so the clearly-simulated demo reads
# as a realistic account: an early drawdown phase (visible losses), then recovery
# into profit — ending net-positive but with losses clearly shown along the way.
# Index 0 maps to the oldest demo trade, so the sequences play out in time.
DEMO_OUTCOMES = [
    # Phase A — drawdown: a run of losses is clearly visible (red) first.
    -1.1, -1.1, 1.5, -1.1, -1.1, 1.5, -1.1, -1.1, -1.1, 1.5,
    # Phase B — recovery: losing streaks are broken by winning trades.
    1.5, -1.1, 1.5, 1.5, -1.1, 1.5, 1.5, -1.1,
    # Phase C — profit: winners dominate and the account ends in profit.
    1.5, 1.5, -1.1, 1.5, 1.5, 1.5,
]


def ensure_demo_user() -> models.User | None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        if user is None:
            user = models.User(
                email=DEMO_EMAIL,
                password_hash=None,
                name="Demo Trader",
                plan=models.Plan.PRO.value,
                is_demo=True,
                webhook_secret=generate_webhook_secret(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Created demo user.")
        return user
    except Exception as e:
        db.rollback()
        logger.error("Failed to ensure demo user: %s", e)
        return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Default strategies for ALL new users (Set & Forget — forex + gold)
# ---------------------------------------------------------------------------

SET_AND_FORGET_ASSETS = [
    {"asset": "EUR/USD", "market": "forex"},
    {"asset": "GBP/USD", "market": "forex"},
    {"asset": "USD/JPY", "market": "forex"},
    {"asset": "XAUUSD", "market": "commodity"},
]

SET_AND_FORGET_TEMPLATE = {
    "name": "Set & Forget",
    "description": (
        "fxalexg's swing trading strategy using supply and demand zones. "
        "Identify the HTF trend, mark Areas of Interest (AOIs), wait for a "
        "lower-timeframe structure shift, then place limit orders with "
        "pre-defined risk and let the trade play out."
    ),
    "timeframe": "4H",
    "strategy_type": "supply_demand",
    "direction": "LONG",
    "indicators": [
        {"name": "Price Action", "period": 0},
        {"name": "EMA", "period": 200},
    ],
    "entry_rules": [
        {"condition": "price_cross_above_ma", "params": {"period": 200, "ma": "ema"}}
    ],
    "confirmation_rules": [
        {"condition": "price_above_ma", "params": {"period": 200, "ma": "ema"}}
    ],
    "exit_rules": [
        {"condition": "price_below_ma", "params": {"period": 200, "ma": "ema"}}
    ],
    "stop_loss_type": "percent",
    "stop_loss_value": 1.5,
    "take_profit_type": "percent",
    "take_profit_value": 6.0,
    "risk_per_trade": 1.0,
    "risk_reward": 4.0,
    "confidence": 82,
    "assumptions": [
        "Core framework: Trend -> Area of Interest (AOI) -> Entry Trigger.",
        "Higher timeframe (Daily/Weekly) sets the trend bias.",
        "Entry via limit order at the proximal edge of a fresh supply/demand zone.",
        "Stop loss placed beyond the distal edge of the zone.",
        "First partial profit at 1R-1.5R, move stop to breakeven after structure confirms.",
        "Leave runner to the next opposing zone on the same or higher timeframe.",
    ],
    "missing_information": [],
    "source": "default",
    "is_demo": False,
    "is_active": True,
}


def seed_default_strategies_for_user(db: Session, user: models.User) -> None:
    """Seed the Set & Forget strategy for forex+gold on all default assets.

    Called during user registration so every user starts with live-alert-ready
    strategies that the market scanner will evaluate automatically.
    """
    existing = (
        db.query(models.Strategy)
        .filter(
            models.Strategy.user_id == user.id,
            models.Strategy.name == "Set & Forget",
            models.Strategy.source == "default",
        )
        .count()
    )
    if existing >= len(SET_AND_FORGET_ASSETS):
        return  # Already seeded

    for asset_info in SET_AND_FORGET_ASSETS:
        # Check if this specific asset+user combo already exists
        already = (
            db.query(models.Strategy)
            .filter(
                models.Strategy.user_id == user.id,
                models.Strategy.name == "Set & Forget",
                models.Strategy.asset == asset_info["asset"],
            )
            .first()
        )
        if already:
            continue

        strategy = models.Strategy(
            user_id=user.id,
            name=SET_AND_FORGET_TEMPLATE["name"],
            description=SET_AND_FORGET_TEMPLATE["description"],
            asset=asset_info["asset"],
            market=asset_info["market"],
            timeframe=SET_AND_FORGET_TEMPLATE["timeframe"],
            strategy_type=SET_AND_FORGET_TEMPLATE["strategy_type"],
            direction=SET_AND_FORGET_TEMPLATE["direction"],
            indicators=SET_AND_FORGET_TEMPLATE["indicators"],
            entry_rules=SET_AND_FORGET_TEMPLATE["entry_rules"],
            confirmation_rules=SET_AND_FORGET_TEMPLATE["confirmation_rules"],
            exit_rules=SET_AND_FORGET_TEMPLATE["exit_rules"],
            stop_loss_type=SET_AND_FORGET_TEMPLATE["stop_loss_type"],
            stop_loss_value=SET_AND_FORGET_TEMPLATE["stop_loss_value"],
            take_profit_type=SET_AND_FORGET_TEMPLATE["take_profit_type"],
            take_profit_value=SET_AND_FORGET_TEMPLATE["take_profit_value"],
            risk_per_trade=SET_AND_FORGET_TEMPLATE["risk_per_trade"],
            risk_reward=SET_AND_FORGET_TEMPLATE["risk_reward"],
            confidence=SET_AND_FORGET_TEMPLATE["confidence"],
            assumptions=SET_AND_FORGET_TEMPLATE["assumptions"],
            missing_information=SET_AND_FORGET_TEMPLATE["missing_information"],
            source=SET_AND_FORGET_TEMPLATE["source"],
            is_demo=False,
            is_active=True,
        )
        db.add(strategy)

    db.commit()
    logger.info("Seeded Set & Forget strategies for user %d (%s)", user.id, user.email)


def _seed_strategy(db: Session, user: models.User, demo: dict) -> models.Strategy:
    strategy = models.Strategy(
        user_id=user.id,
        name=demo["strategy_name"],
        description=demo.get("description"),
        asset=demo["asset"],
        market=demo.get("market"),
        timeframe=demo["timeframe"],
        strategy_type=demo.get("strategy_type"),
        direction=demo["direction"],
        indicators=demo.get("indicators", []),
        entry_rules=demo.get("entry_rules", []),
        confirmation_rules=demo.get("confirmation_rules", []),
        exit_rules=demo.get("exit_rules", []),
        stop_loss_type=demo.get("stop_loss_type"),
        stop_loss_value=demo.get("stop_loss_value"),
        take_profit_type=demo.get("take_profit_type"),
        take_profit_value=demo.get("take_profit_value"),
        risk_per_trade=demo.get("risk_per_trade", 1.0),
        risk_reward=demo.get("risk_reward"),
        confidence=demo.get("confidence"),
        assumptions=demo.get("assumptions", []),
        missing_information=demo.get("missing_information", []),
        source="demo",
        is_demo=True,
    )
    db.add(strategy)
    db.flush()
    return strategy


def _seed_backtest(
    db: Session,
    user: models.User,
    strategy: models.Strategy,
    symbol: str,
    timeframe: str,
) -> models.Backtest | None:
    engine_strategy = strategy_to_engine_form(strategy)
    engine_strategy["strategy_name"] = strategy.name
    engine_strategy["asset"] = symbol

    bars = get_provider().get_ohlcv(symbol, timeframe)
    if len(bars) < 200:
        return None

    result = backtest_engine.run_backtest(
        strategy=engine_strategy,
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        initial_capital=10000.0,
        risk_percent=strategy.risk_per_trade or 1.0,
        fee_percent=0.05,
        slippage_percent=0.02,
    )

    backtest = models.Backtest(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol=symbol,
        timeframe=timeframe,
        start_date=result["equity_curve"][0]["timestamp"] if result["equity_curve"] else None,
        end_date=result["equity_curve"][-1]["timestamp"] if result["equity_curve"] else None,
        initial_capital=10000.0,
        risk_percent=strategy.risk_per_trade or 1.0,
        fee_percent=0.05,
        slippage_percent=0.02,
        metrics=result["metrics"],
        equity_curve=result["equity_curve"],
        trade_history=result["trade_history"],
        monthly_performance=result["monthly_performance"],
        wl_distribution=result["wl_distribution"],
        is_demo=True,
    )
    db.add(backtest)
    db.flush()
    return backtest


def _seed_trades_and_signals(
    db: Session,
    user: models.User,
    strategy: models.Strategy,
    backtests: list[models.Backtest | None],
) -> None:
    combined = []
    for backtest in backtests:
        if backtest is None:
            continue
        for trade in backtest.trade_history or []:
            combined.append((backtest.symbol, trade))
    combined.sort(key=lambda pair: pair[1].get("exit_timestamp") or pair[1].get("entry_timestamp") or "")

    if not combined:
        combined = [(
            strategy.asset,
            {
                "entry_timestamp": "",
                "exit_timestamp": "",
                "direction": strategy.direction,
                "entry_price": 100.0,
                "exit_price": 102.0,
                "stop_loss": 99.0,
                "take_profit": 102.0,
                "exit_reason": "TARGET",
            },
        )]

    # Deterministically curate a realistic, positive demo portfolio: keep the
    # most recent trades for real reference prices but assign a favourable,
    # clearly-simulated outcome profile so the demo reads as profitable.
    recent = combined[-24:]
    outcomes = (DEMO_OUTCOMES * ((len(recent) // len(DEMO_OUTCOMES)) + 1))[: len(recent)]
    if not outcomes:
        outcomes = [1.8] * len(recent)

    for trade, outcome, count in zip(recent, outcomes, range(len(recent))):
        symbol = trade[0]
        t = trade[1]
        r = float(outcome)
        pnl = round(RISK_AMOUNT * r, 2)
        is_win = pnl > 0

        if is_win and count % 5 == 2:
            status = models.SignalStatus.ACTIVE.value
        elif is_win:
            status = models.SignalStatus.TARGET_HIT.value
        elif count % 4 == 0:
            status = models.SignalStatus.EXPIRED.value
        else:
            status = models.SignalStatus.STOP_HIT.value

        signal = models.Signal(
            user_id=user.id,
            strategy_id=strategy.id,
            symbol=symbol,
            direction=t.get("direction", strategy.direction),
            entry_price=t.get("entry_price"),
            stop_loss=t.get("stop_loss"),
            take_profit=t.get("take_profit"),
            risk_reward=strategy.risk_reward,
            confidence=strategy.confidence,
            reason=f"Generated from {strategy.name} rules.",
            status=status,
            source="strategy",
            is_demo=True,
            created_at=_parse_ts(t.get("exit_timestamp") or t.get("entry_timestamp")),
        )
        db.add(signal)
        db.flush()

        db.add(
            models.Trade(
                user_id=user.id,
                signal_id=signal.id,
                strategy_id=strategy.id,
                symbol=symbol,
                direction=t.get("direction", strategy.direction),
                entry_price=t.get("entry_price"),
                exit_price=t.get("exit_price"),
                stop_loss=t.get("stop_loss"),
                take_profit=t.get("take_profit"),
                pnl=pnl,
                pnl_percent=round((pnl / 10000.0) * 100, 3),
                r_multiple=round(r, 2),
                status=models.TradeStatus.CLOSED.value if (not is_win or status != models.SignalStatus.ACTIVE.value) else models.TradeStatus.OPEN.value,
                exit_reason=t.get("exit_reason", "TARGET"),
                entered_at=_parse_ts(t.get("entry_timestamp")),
                exited_at=_parse_ts(t.get("exit_timestamp")),
                is_demo=True,
            )
        )


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime(2025, 1, 1)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime(2025, 1, 1)


def _seed_notifications(db: Session, user: models.User) -> None:
    samples = [
        ("strategy_analyzed", "Welcome to TradePilot AI", "Explore the demo workspace — everything is simulated data."),
        ("backtest_complete", "Demo backtests ready", "Five strategies have been backtested against simulated market data."),
        ("tradingview_alert", "TradingView integration ready", "Send a test alert from the TradingView page to see it flow through."),
        ("system", "Risk disclaimer", "Backtest results are hypothetical. Past performance does not guarantee future results."),
    ]
    existing = (
        db.query(models.Notification).filter(models.Notification.user_id == user.id).count()
    )
    if existing:
        return
    for ntype, title, message in samples:
        db.add(
            models.Notification(user_id=user.id, type=ntype, title=title, message=message, is_read=False)
        )


def _seed_webhook_events(db: Session, user: models.User) -> None:
    existing = (
        db.query(models.WebhookEvent).filter(models.WebhookEvent.user_id == user.id).count()
    )
    if existing:
        return
    db.add(
        models.WebhookEvent(
            user_id=user.id,
            payload={"symbol": "BTCUSD", "direction": "LONG", "price": 62000.0, "test": True},
            secret_valid=True,
            status="processed",
        )
    )


def _refresh_demo_financials(db: Session, user: models.User) -> None:
    """Remove existing demo backtests/trades/signals so re-seeding is idempotent.

    Strategies, notifications and webhook events are kept.
    """
    demo_backtests = (
        db.query(models.Backtest)
        .filter(models.Backtest.user_id == user.id, models.Backtest.is_demo.is_(True))
        .all()
    )
    demo_ids = [b.id for b in demo_backtests]
    db.query(models.Backtest).filter(models.Backtest.id.in_(demo_ids)).delete(
        synchronize_session=False
    ) if demo_ids else None

    demo_trade_ids = [
        t.id for t in db.query(models.Trade)
        .filter(models.Trade.user_id == user.id, models.Trade.is_demo.is_(True)).all()
    ]
    db.query(models.Trade).filter(models.Trade.id.in_(demo_trade_ids)).delete(
        synchronize_session=False
    ) if demo_trade_ids else None

    demo_signal_ids = [
        s.id for s in db.query(models.Signal)
        .filter(models.Signal.user_id == user.id, models.Signal.is_demo.is_(True)).all()
    ]
    db.query(models.Signal).filter(models.Signal.id.in_(demo_signal_ids)).delete(
        synchronize_session=False
    ) if demo_signal_ids else None
    db.flush()


def seed_demo_data(force_refresh: bool = True) -> None:
    """Seed demo data with lock to prevent SQLite contention."""
    if not _seeding_lock.acquire(blocking=False):
        logger.info("Demo seeding already in progress, skipping")
        return
    try:
        db = SessionLocal()
        try:
            user = ensure_demo_user()
            if user is None:
                logger.warning("Could not ensure demo user, skipping seed")
                return

            if force_refresh:
                _refresh_demo_financials(db, user)

            demo_list = ai_strategy_service.available_demo_strategies()
            strategy_assets = {
                "Set & Forget": ["EUR/USD", "GBP/USD", "USD/JPY"],
                "RSI Momentum Reversal": ["BTC/USD", "ETH/USD", "SOL/USD"],
                "Golden Cross Trend": ["ETH/USD", "BTC/USD", "US500"],
                "Momentum Breakout": ["NAS100", "US500", "GOLD"],
                "MACD Trend Continuation": ["GOLD", "ETH/USD", "NAS100"],
                "Bollinger Mean Reversion": ["EUR/USD", "GOLD", "BTC/USD"],
            }
            for demo in demo_list:
                strategy = (
                    db.query(models.Strategy)
                    .filter(
                        models.Strategy.user_id == user.id,
                        models.Strategy.is_demo.is_(True),
                        models.Strategy.name == demo["strategy_name"],
                    )
                    .first()
                )
                if strategy is None:
                    strategy = _seed_strategy(db, user, demo)
                symbols = strategy_assets.get(demo["strategy_name"], [demo["asset"], "BTC/USD", "ETH/USD"])
                backtests = []
                for symbol in symbols:
                    backtests.append(_seed_backtest(db, user, strategy, symbol, strategy.timeframe))
                _seed_trades_and_signals(db, user, strategy, backtests)

            _seed_notifications(db, user)
            _seed_webhook_events(db, user)
            db.commit()
            logger.info("Demo data seeded.")
        except Exception as e:
            db.rollback()
            logger.error("Demo seeding failed: %s", e)
        finally:
            db.close()
    finally:
        _seeding_lock.release()