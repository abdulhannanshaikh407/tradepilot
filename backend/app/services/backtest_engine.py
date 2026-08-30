# app/services/backtest_engine.py
"""Deterministic backtesting engine.

Consumes a normalized strategy (canonical machine-readable rules) plus OHLCV
data and produces real performance metrics: win rate, profit factor, expectancy,
max drawdown, equity curve, trade history and monthly performance.

Everything is deterministic — no randomness at evaluation time. Simulated market
data itself is a seeded random walk, so results are reproducible.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.services import indicators as ind
from app.services.market_data_service import get_provider


# --------------------------------------------------------------------------- #
# Indicator context + rule evaluator
# --------------------------------------------------------------------------- #
class RuleContext:
    def __init__(self, bars: List[dict]) -> None:
        self.closes: List[float] = [b["close"] for b in bars]
        self.highs: List[float] = [b["high"] for b in bars]
        self.lows: List[float] = [b["low"] for b in bars]
        self.timestamps: List[str] = [b["timestamp"] for b in bars]
        self._cache: Dict[tuple, Any] = {}

    def series(self, kind: str, **params: Any) -> Any:
        key = (kind, tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        if kind == "sma":
            val = ind.sma(self.closes, int(params.get("period", 20)))
        elif kind == "ema":
            val = ind.ema(self.closes, int(params.get("period", 20)))
        elif kind == "rsi":
            val = ind.rsi(self.closes, int(params.get("period", 14)))
        elif kind == "macd":
            val = ind.macd(
                self.closes,
                int(params.get("fast", 12)),
                int(params.get("slow", 26)),
                int(params.get("signal", 9)),
            )
        elif kind == "highest":
            val = ind.highest(self.highs, int(params.get("period", 20)))
        elif kind == "lowest":
            val = ind.lowest(self.lows, int(params.get("period", 20)))
        elif kind == "close":
            val = self.closes
        else:
            val = [None] * len(self.closes)
        self._cache[key] = val
        return val


def _a(rctx: RuleContext, i: int, condition: str, params: dict) -> bool:
    """Evaluate one rule at bar index i."""
    p = params or {}

    if condition == "always":
        return True

    if condition == "price_above":
        level = float(p.get("level", 0))
        return rctx.closes[i] > level
    if condition == "price_below":
        level = float(p.get("level", 0))
        return rctx.closes[i] < level

    if condition in {"rsi_above", "rsi_below", "rsi_cross_above", "rsi_cross_below"}:
        period = int(p.get("period", 14))
        level = float(p.get("level", 30))
        s = rctx.series("rsi", period=period)
        if s[i] is None:
            return False
        if condition == "rsi_above":
            return s[i] > level
        if condition == "rsi_below":
            return s[i] < level
        if condition == "rsi_cross_above":
            prev = s[i - 1] if i - 1 >= 0 else None
            return prev is not None and prev <= level < s[i]
        prev = s[i - 1] if i - 1 >= 0 else None
        return prev is not None and prev >= level > s[i]

    if condition in {
        "price_above_ma",
        "price_below_ma",
        "price_cross_above_ma",
        "price_cross_below_ma",
    }:
        period = int(p.get("period", 200))
        ma = p.get("ma", "ema")
        s = rctx.series("ema" if ma in {"ema", "exponential"} else "sma", period=period)
        if s[i] is None:
            return False
        if condition == "price_above_ma":
            return rctx.closes[i] > s[i]
        if condition == "price_below_ma":
            return rctx.closes[i] < s[i]
        if condition == "price_cross_above_ma":
            prev = s[i - 1] if i - 1 >= 0 else None
            return prev is not None and rctx.closes[i - 1] <= prev < rctx.closes[i]
        prev = s[i - 1] if i - 1 >= 0 else None
        return prev is not None and rctx.closes[i - 1] >= prev > rctx.closes[i]

    if condition in {"ma_cross_above", "ma_cross_below"}:
        fast = int(p.get("fast", 50))
        slow = int(p.get("slow", 200))
        ma = p.get("ma", "sma")
        f = rctx.series("ema" if ma in {"ema", "exponential"} else "sma", period=fast)
        s = rctx.series("ema" if ma in {"ema", "exponential"} else "sma", period=slow)
        if f[i] is None or s[i] is None:
            return False
        if condition == "ma_cross_above":
            prev = f[i - 1] and s[i - 1]
            return prev and f[i - 1] <= s[i - 1] and f[i] > s[i]
        prev = f[i - 1] and s[i - 1]
        return prev and f[i - 1] >= s[i - 1] and f[i] < s[i]

    if condition in {"macd_above", "macd_below", "macd_cross_above", "macd_cross_below"}:
        macd_line, signal_line, _ = rctx.series(
            "macd",
            fast=int(p.get("fast", 12)),
            slow=int(p.get("slow", 26)),
            signal=int(p.get("signal", 9)),
        )
        if macd_line[i] is None or signal_line[i] is None:
            return False
        if condition == "macd_above":
            return macd_line[i] > signal_line[i]
        if condition == "macd_below":
            return macd_line[i] < signal_line[i]
        if condition == "macd_cross_above":
            prev = i - 1 >= 0 and macd_line[i - 1] is not None and signal_line[i - 1] is not None
            return prev and macd_line[i - 1] <= signal_line[i - 1] and macd_line[i] > signal_line[i]
        prev = i - 1 >= 0 and macd_line[i - 1] is not None and signal_line[i - 1] is not None
        return prev and macd_line[i - 1] >= signal_line[i - 1] and macd_line[i] < signal_line[i]

    if condition in {"price_breakout_above", "price_breakdown_below"}:
        period = int(p.get("period", 20))
        h = rctx.series("highest", period=period)
        lo = rctx.series("lowest", period=period)
        if condition == "price_breakout_above":
            prev_high = h[i - 1] if i - 1 >= 0 else None
            return prev_high is not None and rctx.closes[i - 1] <= prev_high and rctx.closes[i] > prev_high
        prev_low = lo[i - 1] if i - 1 >= 0 else None
        return prev_low is not None and rctx.closes[i - 1] >= prev_low and rctx.closes[i] < prev_low

    return False


def evaluate_rule_group(rctx: RuleContext, i: int, group: Optional[dict]) -> bool:
    """Evaluate a rule group: {'logic': 'all'|'any', 'conditions':[rules]}."""
    if not group:
        return True
    conditions: list = group.get("conditions", [])
    if not conditions:
        return True
    results = [_a(rctx, i, c.get("condition", "always"), c.get("params", {})) for c in conditions]
    if group.get("logic", "all") == "any":
        return any(results)
    # Allow OR groups nested inside an AND list.
    if group.get("logic") == "or":
        return any(results)
    return all(results)


SUPPORTED_CONDITIONS = {
    "always",
    "price_above",
    "price_below",
    "rsi_above",
    "rsi_below",
    "rsi_cross_above",
    "rsi_cross_below",
    "price_above_ma",
    "price_below_ma",
    "price_cross_above_ma",
    "price_cross_below_ma",
    "ma_cross_above",
    "ma_cross_below",
    "macd_above",
    "macd_below",
    "macd_cross_above",
    "macd_cross_below",
    "price_breakout_above",
    "price_breakdown_below",
}


def validate_rules(rules: List[dict]) -> List[str]:
    problems = []
    for rule in rules:
        cond = rule.get("condition")
        if cond not in SUPPORTED_CONDITIONS:
            problems.append(f"unsupported condition: {cond}")
    return problems


# --------------------------------------------------------------------------- #
# Backtest engine
# --------------------------------------------------------------------------- #
def run_backtest(
    strategy: Dict[str, Any],
    symbol: str,
    timeframe: str,
    bars: Optional[List[dict]] = None,
    initial_capital: float = 10000.0,
    risk_percent: float = 1.0,
    fee_percent: float = 0.05,
    slippage_percent: float = 0.02,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    if bars is None:
        bars = get_provider().get_ohlcv(symbol, timeframe)

    if start_date:
        bars = [b for b in bars if b["timestamp"][:10] >= start_date]
    if end_date:
        bars = [b for b in bars if b["timestamp"][:10] <= end_date]

    if not bars:
        raise ValueError("No market data available for the requested date range/symbol.")

    rctx = RuleContext(bars)

    direction = (strategy.get("direction") or "LONG").upper()
    is_long = direction != "SHORT"

    rules = strategy.get("rules", {})
    entry_group: dict = rules.get("entry", {"logic": "all", "conditions": []})
    confirmation_group: dict = rules.get("confirmation", {"logic": "all", "conditions": []})
    exit_group: dict = rules.get("exit", {"logic": "any", "conditions": []})

    stop_type = strategy.get("stop_loss_type")
    stop_value = strategy.get("stop_loss_value")
    target_type = strategy.get("take_profit_type")
    target_value = strategy.get("take_profit_value")

    equity = initial_capital
    peak_equity = initial_capital
    max_drawdown = 0.0
    trades: List[dict] = []
    equity_curve: List[dict] = [{"timestamp": rctx.timestamps[0], "equity": round(equity, 2)}]

    in_position = False
    entry_price = 0.0
    entry_index = 0
    entry_date = ""
    size = 0.0
    stop_price = 0.0
    target_price = 0.0
    risk_r = 0.0

    warmup = 60  # ensure indicators are warm

    def close_trade(index: int, exit_price: float, exit_reason: str, ts: str) -> None:
        nonlocal equity, peak_equity, max_drawdown
        fee = fee_percent / 100.0
        slip = slippage_percent / 100.0
        if is_long:
            sell = exit_price * (1 - slip)
            gross = size * (sell - entry_price)
        else:
            sell = exit_price * (1 + slip)
            gross = size * (entry_price - sell)
        costs = (size * entry_price * fee) + (size * sell * fee)
        pnl = gross - costs
        equity += pnl
        r = (pnl / risk_r) if risk_r else 0.0
        trades.append(
            {
                "entry_timestamp": entry_date,
                "exit_timestamp": ts,
                "symbol": symbol,
                "direction": direction,
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "stop_loss": round(stop_price, 6) if stop_price else None,
                "take_profit": round(target_price, 6) if target_price else None,
                "size": round(size, 4),
                "pnl": round(pnl, 2),
                "pnl_percent": round((pnl / (size * entry_price)) * 100, 4) if size else 0.0,
                "r_multiple": round(r, 4),
                "exit_reason": exit_reason,
            }
        )
        equity_curve.append({"timestamp": ts, "equity": round(equity, 2)})
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            dd = (peak_equity - equity) / peak_equity * 100
            max_drawdown = max(max_drawdown, dd)

    for i in range(1, len(bars)):
        if not in_position:
            entry_fires = evaluate_rule_group(rctx, i, entry_group)
            if not entry_fires:
                continue
            confirmed = evaluate_rule_group(rctx, i, confirmation_group)
            if not confirmed:
                continue
            if i < warmup:
                continue

            ts = rctx.timestamps[i]
            close = rctx.closes[i]

            # Build stop / target prices from percent values (relative to entry close).
            if stop_value and stop_type == "percent":
                stop_price = close * (1 - stop_value / 100.0) if is_long else close * (1 + stop_value / 100.0)
            elif stop_value:
                stop_price = float(stop_value)
            else:
                stop_price = close * (1 - 0.02) if is_long else close * (1 + 0.02)

            if target_value and target_type == "percent":
                target_price = close * (1 + target_value / 100.0) if is_long else close * (1 - target_value / 100.0)
            elif target_value:
                target_price = float(target_value)
            else:
                target_price = close * (1.02 if is_long else 0.98)

            slip = slippage_percent / 100.0
            entry_price = close * (1 + slip) if is_long else close * (1 - slip)
            entry_index = i
            entry_date = ts

            distance = abs(entry_price - stop_price)
            risk_r = distance * min(size, 0)  # placeholder replaced below
            allocation = equity * (risk_percent / 100.0)
            if distance > 0:
                size = allocation / distance
            else:
                size = (equity * 0.04) / entry_price
            notional = size * entry_price
            cap = equity * 4.0
            if notional > cap:
                size = cap / entry_price
            risk_r = abs(entry_price - stop_price) * size
            in_position = True
        else:
            bar_high = rctx.highs[i]
            bar_low = rctx.lows[i]
            ts = rctx.timestamps[i]
            closed = False

            # In-bar stop / target (conservative: stop is checked first for longs).
            if is_long:
                if stop_price and bar_low <= stop_price:
                    close_trade(i, stop_price, "STOP", ts)
                    closed = True
                elif target_price and bar_high >= target_price:
                    close_trade(i, target_price, "TARGET", ts)
                    closed = True
            else:
                if stop_price and bar_high >= stop_price:
                    close_trade(i, stop_price, "STOP", ts)
                    closed = True
                elif target_price and bar_low <= target_price:
                    close_trade(i, target_price, "TARGET", ts)
                    closed = True

            if not closed and evaluate_rule_group(rctx, i, exit_group):
                close_trade(i, rctx.closes[i], "EXIT_RULE", ts)
                closed = True

            if closed:
                in_position = False
                equity_curve.append(
                    {"timestamp": ts, "equity": round(equity, 2)}
                )

    if in_position:
        last = len(bars) - 1
        close_trade(last, rctx.closes[last], "END_OF_DATA", rctx.timestamps[last])

    return _compute_results(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=initial_capital,
        max_drawdown=max_drawdown,
        symbol=symbol,
        strategy_name=strategy.get("strategy_name") or strategy.get("name") or "Strategy",
    )


def _equity_risk_metrics(equity_curve: List[dict], net_pnl: float) -> Dict[str, Any]:
    """Sharpe / Sortino / CAGR / Calmar / recovery on a calendar-day equity curve.

    Daily equity is the last recorded equity for each calendar day; returns are
    day-over-day pct changes annualised by 365. All metrics degrade gracefully
    to 0 when there is too little data to be meaningful.
    """
    empty = {
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "cagr": 0.0,
        "calmar_ratio": 0.0,
        "recovery_factor": 0.0,
        "annualized_volatility": 0.0,
    }
    if not equity_curve:
        return empty

    daily: Dict[str, float] = {}
    for point in equity_curve:
        daily[point["timestamp"][:10]] = point["equity"]
    ordered = [daily[d] for d in sorted(daily)]
    if len(ordered) < 2:
        return empty

    returns = [ordered[i] / ordered[i - 1] - 1.0 for i in range(1, len(ordered))]
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(variance) if variance > 0 else 0.0
    annual_factor = math.sqrt(365.0)

    sharpe = (mean / std * annual_factor) if std > 0 else 0.0

    downside = [r for r in returns if r < 0]
    down_var = sum(r * r for r in downside) / n
    dstd = math.sqrt(down_var) if down_var > 0 else 0.0
    sortino = (mean / dstd * annual_factor) if dstd > 0 else 0.0

    start_eq, end_eq = ordered[0], ordered[-1]
    if start_eq > 0 and n > 0:
        cagr = (end_eq / start_eq) ** (365.0 / n) - 1.0
    else:
        cagr = 0.0

    peak = ordered[0]
    max_dd_currency = 0.0
    max_dd_pct = 0.0
    for eq in ordered:
        peak = max(peak, eq)
        if peak > 0:
            dd_pct = (peak - eq) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd_pct)
        max_dd_currency = max(max_dd_currency, peak - eq)

    return {
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "cagr": round(cagr * 100.0, 2),
        "calmar_ratio": round((cagr / (max_dd_pct / 100.0)) if max_dd_pct > 0 else 0.0, 2),
        "recovery_factor": round(net_pnl / max_dd_currency, 2) if max_dd_currency > 0 else 0.0,
        "annualized_volatility": round(std * annual_factor * 100.0, 2),
    }


def _compute_results(
    trades: List[dict],
    equity_curve: List[dict],
    initial_capital: float,
    max_drawdown: float,
    symbol: str,
    strategy_name: str,
) -> dict:
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total = len(trades)
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_pnl = gross_profit - gross_loss
    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
    return_pct = (final_equity / initial_capital - 1) * 100 if initial_capital else 0.0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    expect = net_pnl / total if total else 0.0
    avg_r = sum(t["r_multiple"] for t in trades) / total if total else 0.0

    monthly: Dict[str, dict] = {}
    for t in trades:
        month = t["exit_timestamp"][:7] if t["exit_timestamp"] else "?"
        bucket = monthly.setdefault(month, {"pnl": 0.0, "trades": 0, "wins": 0})
        bucket["pnl"] += t["pnl"]
        bucket["trades"] += 1
        if t["pnl"] > 0:
            bucket["wins"] += 1
    monthly_perf = [
        {"period": m, "pnl": round(v["pnl"], 2), "trades": v["trades"], "wins": v["wins"]}
        for m, v in sorted(monthly.items())
    ]

    winning = len(wins)
    losing = len(losses)
    metrics = {
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": (winning / total * 100) if total else 0.0,
        "net_pnl": round(net_pnl, 2),
        "return_percent": round(return_pct, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expect, 2),
        "max_drawdown": round(max_drawdown, 2),
        "average_r": round(avg_r, 2),
        "largest_win": round(max((t["pnl"] for t in wins), default=0.0), 2),
        "largest_loss": round(min((t["pnl"] for t in losses), default=0.0), 2),
        "average_winner": round((gross_profit / len(wins)) if wins else 0.0, 2),
        "average_loser": round((gross_loss / len(losses)) if losses else 0.0, 2),
        "symbol": symbol,
        "strategy_name": strategy_name,
    }
    metrics.update(_equity_risk_metrics(equity_curve, net_pnl))

    return {
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trade_history": trades,
        "monthly_performance": monthly_perf,
        "wl_distribution": {"wins": winning, "losses": losing, "total": total},
    }


# --------------------------------------------------------------------------- #
# Normalization — StrategyModel / extracted dict -> engine-ready dict
# --------------------------------------------------------------------------- #
def normalize_strategy(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a stored strategy (list-based rules) into engine format.

    The stored strategy may already contain canonical rules; if so it passes
    through. Ensures defaults exist for the engine fields.
    """
    rules = strategy.get("rules")
    if rules and rules.get("entry", {}).get("conditions"):
        normalized = dict(strategy)
        return normalized

    entry_conditions = strategy.get("entry_rules") or []
    confirm_conditions = strategy.get("confirmation_rules") or []
    exit_conditions = strategy.get("exit_rules") or []

    normalized = dict(strategy)
    normalized["rules"] = {
        "entry": {"logic": "all", "conditions": entry_conditions},
        "confirmation": {"logic": "all", "conditions": confirm_conditions},
        "exit": {"logic": "any", "conditions": exit_conditions},
    }
    return normalized


def strategy_to_engine_form(strategy: Any) -> Dict[str, Any]:
    """Accept a SQLAlchemy Strategy (or dict) and produce engine-ready dict."""
    if hasattr(strategy, "__table__"):
        data = {
            "strategy_name": strategy.name,
            "name": strategy.name,
            "direction": strategy.direction,
            "asset": strategy.asset,
            "timeframe": strategy.timeframe,
            "entry_rules": strategy.entry_rules or [],
            "confirmation_rules": strategy.confirmation_rules or [],
            "exit_rules": strategy.exit_rules or [],
            "stop_loss_type": strategy.stop_loss_type,
            "stop_loss_value": strategy.stop_loss_value,
            "take_profit_type": strategy.take_profit_type,
            "take_profit_value": strategy.take_profit_value,
            "risk_per_trade": strategy.risk_per_trade,
        }
    else:
        data = dict(strategy)
    return normalize_strategy(data)