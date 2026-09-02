export interface User {
  id: number;
  email: string;
  name: string;
  plan: string;
  is_demo: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DashboardStats {
  portfolio_value: number;
  net_pnl: number;
  win_rate: number;
  active_signals: number;
  total_trades: number;
  max_drawdown: number;
  equity_curve: { timestamp?: string; value: number }[];
  recent_signals: Signal[];
  strategy_performance: { strategy: string; return_percent: number }[];
  recent_activity: { type: string; title: string; created_at?: string; message?: string }[];
}

export interface Strategy {
  id: number;
  name: string;
  asset: string;
  timeframe: string;
  direction: string;
  is_active: boolean;
  is_demo: boolean;
  stop_loss_type?: string | null;
  stop_loss_value?: number | null;
  take_profit_type?: string | null;
  take_profit_value?: number | null;
}

export interface Signal {
  id: number;
  symbol: string;
  direction: string;
  entry_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  risk_reward?: number | null;
  confidence?: number | null;
  reason?: string | null;
  status: string;
  source: string;
  created_at?: string | null;
}

export interface AutoTradeStatus {
  running: boolean;
  enabled: boolean;
  interval_seconds: number;
  provider: string;
  last_run_at?: string | null;
  last_error?: string | null;
  strategies_watched: number;
  open_positions: number;
  live_available: boolean;
}

export interface AutoTradeConfig {
  id: number;
  strategy_id: number;
  strategy_name: string;
  strategy_symbol: string;
  strategy_timeframe: string;
  enabled: boolean;
  mode: string;
  capital: number;
  risk_percent: number;
  slippage_percent: number;
  max_concurrent: number;
  max_daily_loss?: number | null;
  cooldown_minutes: number;
  last_run_at?: string | null;
  last_error?: string | null;
}

export interface Position {
  id: number;
  strategy_id?: number | null;
  symbol: string;
  direction: string;
  handler: string;
  broker: string;
  status: string;
  entry_price?: number | null;
  current_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  size?: number | null;
  cost?: number | null;
  unrealized_pnl?: number | null;
  realized_pnl?: number | null;
  pnl_percent?: number | null;
  exit_reason?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message?: string | null;
  is_read: boolean;
  created_at?: string | null;
}

export interface BrokerConnection {
  id: number;
  broker: string;
  account_type: string;
  is_verified: boolean;
  last_verified_at?: string | null;
  created_at?: string | null;
}

export interface BrokerAccount {
  balance: number;
  buying_power: number;
  cash: number;
  account_type: string;
  broker_name: string;
  daily_pnl: number;
  daily_pnl_percent: number;
  positions: {
    symbol: string;
    quantity: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    pnl_percent: number;
  }[];
}