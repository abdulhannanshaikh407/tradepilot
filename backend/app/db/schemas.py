# app/db/schemas.py
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    plan: str
    is_demo: bool
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Strategy ----------
class IndicatorRule(BaseModel):
    name: Optional[str] = None
    period: Optional[int] = None


class StrategyRule(BaseModel):
    condition: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuleGroup(BaseModel):
    logic: str = "all"
    conditions: List[StrategyRule] = Field(default_factory=list)


class StrategyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    asset: str = "BTC/USD"
    market: Optional[str] = "crypto"
    timeframe: str = "4H"
    strategy_type: Optional[str] = None
    direction: str = "LONG"
    indicators: List[IndicatorRule] = Field(default_factory=list)
    entry_rules: List[StrategyRule] = Field(default_factory=list)
    confirmation_rules: List[StrategyRule] = Field(default_factory=list)
    exit_rules: List[StrategyRule] = Field(default_factory=list)
    stop_loss_type: Optional[str] = "percent"
    stop_loss_value: Optional[float] = None
    take_profit_type: Optional[str] = "percent"
    take_profit_value: Optional[float] = None
    risk_per_trade: float = 1.0
    risk_reward: Optional[float] = None
    confidence: Optional[int] = None
    assumptions: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    source: str = "manual"
    source_url: Optional[str] = None
    is_demo: bool = False
    is_active: bool = True


class StrategyOut(ORMModel):
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    asset: str
    market: Optional[str] = None
    timeframe: str
    strategy_type: Optional[str] = None
    direction: str
    indicators: Any = None
    entry_rules: Any = None
    confirmation_rules: Any = None
    exit_rules: Any = None
    stop_loss_type: Optional[str] = None
    stop_loss_value: Optional[float] = None
    take_profit_type: Optional[str] = None
    take_profit_value: Optional[float] = None
    risk_per_trade: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: Optional[int] = None
    assumptions: Any = None
    missing_information: Any = None
    source: str
    source_url: Optional[str] = None
    is_demo: bool
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- YouTube ----------
class YouTubeAnalyzeRequest(BaseModel):
    url: str
    transcript_override: Optional[str] = None


class YouTubeAnalysisResponse(BaseModel):
    strategy: StrategyOut
    transcript_preview: Optional[str] = None
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    used_demo_fallback: bool = False
    message: str = ""


# ---------- Signals ----------
class SignalCreate(BaseModel):
    strategy_id: Optional[int] = None
    symbol: str
    direction: str = "LONG"
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: Optional[int] = None
    reason: Optional[str] = None
    source: str = "manual"


class SignalOut(ORMModel):
    id: int
    user_id: int
    strategy_id: Optional[int] = None
    symbol: str
    direction: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: Optional[int] = None
    reason: Optional[str] = None
    status: str
    source: str
    is_demo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SignalGenerateRequest(BaseModel):
    strategy_id: int


class SignalUpdate(BaseModel):
    status: Optional[str] = None
    outcome: Optional[str] = None


# ---------- Backtest ----------
class BacktestRequest(BaseModel):
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    symbol: str = "BTC/USD"
    timeframe: str = "4H"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000.0
    risk_percent: float = 1.0
    fee_percent: float = 0.05
    slippage_percent: float = 0.02


class BacktestOut(ORMModel):
    id: int
    user_id: int
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    symbol: str
    timeframe: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: Optional[float] = None
    risk_percent: Optional[float] = None
    fee_percent: Optional[float] = None
    slippage_percent: Optional[float] = None
    metrics: Any = None
    equity_curve: Any = None
    trade_history: Any = None
    monthly_performance: Any = None
    wl_distribution: Any = None
    is_demo: bool
    created_at: Optional[datetime] = None


# ---------- Optimization ----------
class OptimizationParameter(BaseModel):
    path: str
    min: float = 1.0
    max: float = 100.0
    step: float = 1.0


class OptimizationConfig(BaseModel):
    parameters: List[OptimizationParameter] = Field(default_factory=list)
    metric: str = "sharpe_ratio"
    direction: Optional[str] = None  # "maximize" | "minimize"; inferred if omitted
    mode: str = "grid"  # "grid" | "walk_forward"
    folds: int = Field(default=5, ge=1, le=20)
    test_ratio: float = Field(default=0.3, ge=0, lt=0.5)
    max_evals: int = Field(default=400, ge=1, le=20000)
    max_bars: Optional[int] = Field(default=2000, ge=500, le=20000)


class OptimizeRequest(BaseModel):
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    symbol: str = "BTC/USD"
    timeframe: str = "4H"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000.0
    risk_percent: float = 1.0
    fee_percent: float = 0.05
    slippage_percent: float = 0.02
    optimization: OptimizationConfig


# ---------- Performance ----------
class PerformanceSummary(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    return_percent: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    average_r: float = 0.0
    total_backtests: int = 0
    total_strategies: int = 0
    total_signals: int = 0
    active_signals: int = 0


# ---------- Webhooks ----------
class TradingViewWebhook(BaseModel):
    secret: Optional[str] = None
    symbol: str
    direction: str = "LONG"
    price: Optional[float] = None
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    timestamp: Optional[str] = None


class WebhookTestRequest(BaseModel):
    symbol: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[float] = None


class WebhookEventOut(ORMModel):
    id: int
    user_id: Optional[int] = None
    payload: Any = None
    secret_valid: bool
    status: str
    signal_id: Optional[int] = None
    created_at: Optional[datetime] = None


# ---------- Notifications ----------
class NotificationOut(ORMModel):
    id: int
    user_id: int
    type: str
    title: str
    message: Optional[str] = None
    is_read: bool
    created_at: Optional[datetime] = None


# ---------- Usage / Dashboard ----------
class DashboardStats(BaseModel):
    portfolio_value: float = 0.0
    net_pnl: float = 0.0
    win_rate: float = 0.0
    active_signals: int = 0
    total_trades: int = 0
    max_drawdown: float = 0.0
    equity_curve: List[dict[str, Any]] = Field(default_factory=list)
    recent_signals: List[SignalOut] = Field(default_factory=list)
    strategy_performance: List[dict[str, Any]] = Field(default_factory=list)
    recent_activity: List[dict[str, Any]] = Field(default_factory=list)


class PlanInfo(BaseModel):
    plan: str
    limits: dict[str, Any]
    usage: dict[str, Any]


# ---------- Settings ----------
class SettingsUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


# ---------- Auto-trade ----------
class AutoTradeConfigCreate(BaseModel):
    strategy_id: int
    broker_connection_id: Optional[int] = None
    enabled: bool = False
    mode: str = "paper"  # "paper" | "live"
    capital: float = 10000.0
    risk_percent: float = 1.0
    slippage_percent: float = 0.1
    max_concurrent: int = 1
    max_daily_loss: Optional[float] = None
    cooldown_minutes: int = 60


class AutoTradeConfigUpdate(BaseModel):
    broker_connection_id: Optional[int] = None
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    capital: Optional[float] = None
    risk_percent: Optional[float] = None
    slippage_percent: Optional[float] = None
    max_concurrent: Optional[int] = None
    max_daily_loss: Optional[float] = None
    cooldown_minutes: Optional[int] = None


class AutoTradeConfigOut(BaseModel):
    id: int
    strategy_id: int
    broker_connection_id: Optional[int] = None
    strategy_name: Optional[str] = None
    strategy_symbol: Optional[str] = None
    strategy_timeframe: Optional[str] = None
    enabled: bool
    mode: str
    capital: float
    risk_percent: float
    slippage_percent: float
    max_concurrent: int
    max_daily_loss: Optional[float] = None
    cooldown_minutes: int = 60
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None


class PositionOut(ORMModel):
    id: int
    strategy_id: Optional[int] = None
    symbol: str
    direction: str
    handler: str
    broker: str
    status: str
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size: Optional[float] = None
    cost: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    exit_reason: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class AutoTradeStatus(BaseModel):
    running: bool
    enabled: bool
    interval_seconds: float
    provider: str
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    strategies_watched: int
    open_positions: int
    live_available: bool


# ---------- Alert Preferences ----------
class AlertPreferenceUpdate(BaseModel):
    alerts_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    min_confidence: Optional[int] = None


class AlertPreferenceOut(ORMModel):
    id: int
    strategy_id: int
    strategy_name: Optional[str] = None
    alerts_enabled: bool
    push_enabled: bool
    email_enabled: bool
    in_app_enabled: bool
    min_confidence: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None