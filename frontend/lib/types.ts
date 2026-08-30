export type Direction = "LONG" | "SHORT";

export interface User {
  id: number;
  email: string;
  name: string;
  plan: string;
  is_demo: boolean;
  created_at?: string | null;
  last_login?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface StrategyRule {
  condition: string;
  params: Record<string, unknown>;
}

export interface Strategy {
  id: number;
  user_id: number;
  name: string;
  description?: string | null;
  asset: string;
  market?: string | null;
  timeframe: string;
  strategy_type?: string | null;
  direction: Direction;
  indicators: { name?: string; period?: number | string }[];
  entry_rules: StrategyRule[];
  confirmation_rules: StrategyRule[];
  exit_rules: StrategyRule[];
  stop_loss_type?: string | null;
  stop_loss_value?: number | null;
  take_profit_type?: string | null;
  take_profit_value?: number | null;
  risk_per_trade?: number | null;
  risk_reward?: number | null;
  confidence?: number | null;
  assumptions: string[];
  missing_information: string[];
  source: string;
  source_url?: string | null;
  is_demo: boolean;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface YouTubeAnalysis {
  strategy: Strategy;
  transcript_preview?: string | null;
  video_id?: string | null;
  video_title?: string | null;
  used_demo_fallback: boolean;
  message: string;
}

export interface Signal {
  id: number;
  user_id: number;
  strategy_id?: number | null;
  symbol: string;
  direction: Direction;
  entry_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  risk_reward?: number | null;
  confidence?: number | null;
  reason?: string | null;
  status: string;
  source: string;
  is_demo: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Backtest {
  id: number;
  user_id: number;
  strategy_id?: number | null;
  strategy_name?: string | null;
  symbol: string;
  timeframe: string;
  start_date?: string | null;
  end_date?: string | null;
  initial_capital?: number | null;
  risk_percent?: number | null;
  fee_percent?: number | null;
  slippage_percent?: number | null;
  metrics: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    net_pnl: number;
    return_percent: number;
    profit_factor: number;
    expectancy: number;
    max_drawdown: number;
    average_r: number;
    largest_win: number;
    largest_loss: number;
    average_winner: number;
    average_loser: number;
    sharpe_ratio?: number | null;
    sortino_ratio?: number | null;
    cagr?: number | null;
    calmar_ratio?: number | null;
    recovery_factor?: number | null;
    annualized_volatility?: number | null;
    symbol: string;
    strategy_name: string;
  };
  equity_curve: { timestamp: string; equity: number }[];
  trade_history: {
    entry_timestamp: string;
    exit_timestamp: string;
    symbol: string;
    direction: Direction;
    entry_price: number;
    exit_price: number;
    stop_loss: number | null;
    take_profit: number | null;
    size: number;
    pnl: number;
    pnl_percent: number;
    r_multiple: number;
    exit_reason: string;
  }[];
  monthly_performance: { period: string; pnl: number; trades: number; wins: number }[];
  wl_distribution: { wins: number; losses: number; total: number };
  is_demo: boolean;
  created_at?: string | null;
}

export interface PerformanceSummary {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  net_pnl: number;
  return_percent: number;
  profit_factor: number;
  expectancy: number;
  max_drawdown: number;
  average_r: number;
  total_backtests: number;
  total_strategies: number;
  total_signals: number;
  active_signals: number;
}

export interface DashboardStats {
  portfolio_value: number;
  net_pnl: number;
  win_rate: number;
  active_signals: number;
  total_trades: number;
  max_drawdown: number;
  equity_curve: { timestamp: string; equity: number }[];
  recent_signals: Signal[];
  strategy_performance: {
    name: string;
    asset: string;
    trades: number;
    win_rate: number;
    return_percent: number;
    profit_factor: number;
  }[];
  recent_activity: { type: string; title: string; message: string; created_at: string }[];
}

export interface Notification {
  id: number;
  user_id: number;
  type: string;
  title: string;
  message?: string | null;
  is_read: boolean;
  created_at?: string | null;
}

export interface WebhookEvent {
  id: number;
  user_id: number | null;
  payload: Record<string, unknown>;
  secret_valid: boolean;
  status: string;
  signal_id: number | null;
  created_at?: string | null;
}

export interface TradingViewInfo {
  global_secret: string;
  user_secret: string;
  webhook_path: string;
  example_payload: Record<string, unknown>;
}

export interface LiveQuote {
  symbol: string;
  price: number;
  source: string;
  updated_at?: string | null;
}

export interface MarketLive {
  provider: string;
  live_count: number;
  quotes: Record<string, LiveQuote>;
}

export type OptimizationMetric =
  | "return_percent"
  | "net_pnl"
  | "profit_factor"
  | "win_rate"
  | "max_drawdown"
  | "expectancy"
  | "average_r"
  | "sharpe_ratio"
  | "sortino_ratio"
  | "cagr"
  | "calmar_ratio";

export interface OptimizationResult {
  mode: "grid" | "walk_forward";
  direction: string;
  grid_total_evals: number;
  best_params: Record<string, number> | null;
  best_metrics: Record<string, number> | null;
  top_results: { params: Record<string, number>; metrics: Record<string, number> }[];
  out_of_sample_metrics: Record<string, number> | null;
  walk_forward: {
    folds: {
      fold: number;
      window_start: string;
      window_end: string;
      train_start: string;
      train_end: string;
      test_start: string;
      test_end: string;
      best_params: Record<string, number>;
      train_metrics: Record<string, number>;
      test_metrics: Record<string, number>;
      test_trades: number;
    }[];
    combined_metrics: Record<string, number>;
    combined_equity_curve: { timestamp: string; equity: number }[];
    combined_trade_history: unknown[];
    combined_monthly_performance: { period: string; pnl: number }[];
  } | null;
  backtest_id?: number;
}

export interface BillingPlan {
  FREE: { label: string; price: number; features: string[] };
  PRO: { label: string; price: number; features: string[] };
  BUSINESS: { label: string; price: number; features: string[] };
}

export interface CurrentPlan {
  plan: string;
  limits: Record<string, number>;
  usage: Record<string, number>;
}