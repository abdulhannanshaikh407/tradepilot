# app/db/models.py
import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Plan(str, enum.Enum):
    FREE = "FREE"
    PRO = "PRO"
    BUSINESS = "BUSINESS"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class SignalDirection(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=False, default="Trader")
    plan = Column(String, nullable=False, default=Plan.FREE.value)
    webhook_secret = Column(String, unique=True, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="user", cascade="all, delete-orphan")
    backtests = relationship("Backtest", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")
    autotrade_configs = relationship("AutoTradeConfig", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship(
        "Subscription",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String, nullable=False, default=Plan.FREE.value)
    status = Column(String, nullable=False, default=SubscriptionStatus.TRIAL.value)
    stripe_customer_id = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    renews_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="subscription")


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    asset = Column(String, nullable=False)
    market = Column(String, nullable=True)
    timeframe = Column(String, nullable=False)
    strategy_type = Column(String, nullable=True)
    direction = Column(String, nullable=False, default="LONG")
    indicators = Column(JSON, nullable=True, default=list)
    entry_rules = Column(JSON, nullable=True, default=list)
    confirmation_rules = Column(JSON, nullable=True, default=list)
    exit_rules = Column(JSON, nullable=True, default=list)
    stop_loss_type = Column(String, nullable=True)
    stop_loss_value = Column(Float, nullable=True)
    take_profit_type = Column(String, nullable=True)
    take_profit_value = Column(Float, nullable=True)
    risk_per_trade = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    assumptions = Column(JSON, nullable=True, default=list)
    missing_information = Column(JSON, nullable=True, default=list)
    source = Column(String, nullable=False, default="manual")
    source_url = Column(String, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="strategies")
    signals = relationship("Signal", back_populates="strategy")
    backtests = relationship("Backtest", back_populates="strategy")
    transcripts = relationship("Transcript", back_populates="strategy")


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    video_id = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    video_title = Column(String, nullable=True)
    language = Column(String, nullable=True)
    transcript_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    strategy = relationship("Strategy", back_populates="transcripts")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String, nullable=False, default=SignalStatus.PENDING.value)
    source = Column(String, nullable=False, default="manual")
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="signals")
    strategy = relationship("Strategy", back_populates="signals")
    trades = relationship("Trade", back_populates="signal")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    size = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    r_multiple = Column(Float, nullable=True)
    status = Column(String, nullable=False, default=TradeStatus.CLOSED.value)
    exit_reason = Column(String, nullable=True)
    entered_at = Column(DateTime(timezone=True), server_default=func.now())
    exited_at = Column(DateTime(timezone=True), nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)

    user = relationship("User")
    signal = relationship("Signal", back_populates="trades")
    strategy = relationship("Strategy")


class Backtest(Base):
    __tablename__ = "backtests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    strategy_name = Column(String, nullable=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    initial_capital = Column(Float, nullable=True)
    risk_percent = Column(Float, nullable=True)
    fee_percent = Column(Float, nullable=True)
    slippage_percent = Column(Float, nullable=True)
    metrics = Column(JSON, nullable=True, default=dict)
    equity_curve = Column(JSON, nullable=True, default=list)
    trade_history = Column(JSON, nullable=True, default=list)
    monthly_performance = Column(JSON, nullable=True, default=list)
    wl_distribution = Column(JSON, nullable=True, default=dict)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="backtests")
    strategy = relationship("Strategy", back_populates="backtests")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    secret_valid = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="received")
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    signal = relationship("Signal")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False, default="system")
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    feature = Column(String, nullable=False)
    period = Column(String, nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="usage_records")


class AutoTradeConfig(Base):
    """Per-strategy auto-trading settings.

    Trades are PAPER by default. `mode` flips to "live" only when real Binance
    credentials are configured on the server AND the user explicitly arms it.
    """

    __tablename__ = "autotrade_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    mode = Column(String, nullable=False, default="paper")  # "paper" | "live"
    capital = Column(Float, nullable=False, default=10000.0)
    risk_percent = Column(Float, nullable=False, default=1.0)
    slippage_percent = Column(Float, nullable=False, default=0.1)
    max_concurrent = Column(Integer, nullable=False, default=1)
    max_daily_loss = Column(Float, nullable=True)  # optional hard stop, bps of capital
    cooldown_minutes = Column(Integer, nullable=False, default=60)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    strategy = relationship("Strategy")


class Position(Base):
    """An open/closed auto-trade position tracked by the engine."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    handler = Column(String, nullable=False, default="autotrade")  # autotrade | tradingview
    broker = Column(String, nullable=False, default="paper")  # paper | binance-live
    status = Column(String, nullable=False, default=TradeStatus.OPEN.value)
    entry_price = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    size = Column(Float, nullable=True)  # base-currency units (e.g. BTC)
    cost = Column(Float, nullable=True)  # quote-currency committed (e.g. USDT)
    unrealized_pnl = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    strategy = relationship("Strategy")
    signal = relationship("Signal")