# app/services/optimizer.py
"""Parameter optimization and walk-forward validation.

Runs the deterministic backtest engine across a grid of strategy parameters and
optionally validates the best parameter set out-of-sample using an anchored
train/test split (``grid`` mode) or rolling walk-forward folds
(``walk_forward`` mode).

Parameters are expressed as dotted paths into the engine-form strategy dict,
e.g. ``"entry.conditions.0.params.period"`` or ``"stop_loss_value"``.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Optional, Tuple

from app.services import market_data_service
from app.services.backtest_engine import _compute_results, run_backtest

GRID_MODE = "grid"
WALK_FORWARD_MODE = "walk_forward"

ALLOWED_METRICS = {
    "return_percent",
    "net_pnl",
    "profit_factor",
    "win_rate",
    "max_drawdown",
    "expectancy",
    "average_r",
    "sharpe_ratio",
    "sortino_ratio",
    "cagr",
    "calmar_ratio",
}

DEFAULT_METRIC_DIRECTION = {"max_drawdown": "minimize"}


def _parts(path: str) -> List[Any]:
    """Split a dotted path like 'entry.conditions.0.params.period'."""
    parts: List[Any] = []
    for chunk in path.split("."):
        if chunk == "":
            continue
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    return parts


def _get_by_path(node: Any, parts: List[Any]) -> Any:
    current = node
    for part in parts:
        try:
            current = current[part]
        except (KeyError, IndexError, TypeError):
            return None
    return current


def _set_by_path(node: Any, parts: List[Any], value: Any) -> None:
    current = node
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def param_values(spec: dict) -> List[float]:
    """Expand min/max/step into a discrete, de-duplicated value list."""
    low = float(spec.get("min", 1))
    high = float(spec.get("max", 100))
    step = float(spec.get("step", 1))
    if high < low:
        raise ValueError(f"Parameter range invalid: min {low} > max {high}.")
    if step <= 0:
        raise ValueError(f"Parameter step must be > 0 (got {step}).")
    count = int(round((high - low) / step))
    values = [low + i * step for i in range(count + 1)]
    out: List[float] = []
    for v in values:
        v = round(v, 10)
        if not out or abs(v - out[-1]) > 1e-9:
            out.append(v)
    return out


def _canonical_path(strategy: dict, path: str) -> str:
    """Allow 'entry.conditions.0' shorthand while the engine stores rules under 'rules'."""
    first = (path or "").split(".")[0]
    if "rules" in strategy and first in {"entry", "exit", "confirmation"}:
        return "rules." + path
    return path


def _specs(parameters: List[dict], strategy: dict) -> List[Tuple[str, List[float]]]:
    specs = []
    for p in parameters:
        path = str(p.get("path", "")).strip()
        if not path:
            raise ValueError("Every optimization parameter needs a 'path'.")
        specs.append((_canonical_path(strategy, path), param_values(p)))
    return specs


def _combos_count(specs: List[Tuple[str, List[float]]]) -> int:
    total = 1
    for _, values in specs:
        total *= len(values)
    return total


def metric_direction(metric: str, override: Optional[str]) -> str:
    if override and override in {"maximize", "minimize"}:
        direction = override
    elif override:
        raise ValueError(f"Invalid direction '{override}' (use 'maximize' or 'minimize').")
    else:
        direction = DEFAULT_METRIC_DIRECTION.get(metric, "maximize")
    return direction


def _metric(metrics: dict, metric: str) -> float:
    value = metrics.get(metric)
    if value is None:
        raise ValueError(f"Metric '{metric}' is not produced by the backtest engine.")
    return float(value)


def _max_drawdown_pct(equity_curve: List[dict]) -> float:
    peak = 0.0
    max_dd = 0.0
    for point in equity_curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return max_dd


def _load_bars(
    symbol: str,
    timeframe: str,
    start_date: Optional[str],
    end_date: Optional[str],
    max_bars: Optional[int],
) -> List[dict]:
    bars = market_data_service.get_provider().get_ohlcv(symbol, timeframe)
    if start_date:
        bars = [b for b in bars if b["timestamp"][:10] >= start_date]
    if end_date:
        bars = [b for b in bars if b["timestamp"][:10] <= end_date]
    if not bars:
        raise ValueError("No market data available for the requested date range/symbol.")
    if max_bars:
        bars = bars[-max_bars:]
    if len(bars) < 120:
        raise ValueError(
            f"Only {len(bars)} bars available for optimization on {symbol} {timeframe}; "
            "need at least 120. Use a longer period or a higher timeframe."
        )
    return bars


def apply_params(strategy: dict, params: Dict[str, Any]) -> dict:
    """Return a copy of an engine-form strategy with the given path->value map applied."""
    candidate = dict(strategy)
    for path, value in (params or {}).items():
        _set_by_path(candidate, _parts(path), value)
    return candidate


def _run(
    strategy: dict,
    symbol: str,
    timeframe: str,
    bars: List[dict],
    initial_capital: float,
    risk_percent: float,
    fee_percent: float,
    slippage_percent: float,
) -> dict:
    return run_backtest(
        strategy=strategy,
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        initial_capital=initial_capital,
        risk_percent=risk_percent,
        fee_percent=fee_percent,
        slippage_percent=slippage_percent,
    )


def _grid_search(
    bars: List[dict],
    strategy: dict,
    specs: List[Tuple[str, List[float]]],
    metric: str,
    direction: str,
    max_evals: int,
    symbol: str,
    timeframe: str,
    initial_capital: float,
    risk_percent: float,
    fee_percent: float,
    slippage_percent: float,
) -> Tuple[Dict[str, Any], dict, List[dict]]:
    """Return (best_params, best_metrics, sorted_results)."""
    total = _combos_count(specs)
    if total > max_evals:
        raise ValueError(
            f"Grid would test {total} combinations (max {max_evals}). "
            "Reduce parameter ranges or increase the step."
        )

    maximize = direction != "minimize"
    best: Optional[Dict[str, Any]] = None
    best_metrics: Optional[dict] = None
    results: List[dict] = []

    for combo in itertools.product(*(values for _, values in specs)):
        candidate = {path: value for (path, _), value in zip(specs, combo)}
        candidate_strategy = apply_params(strategy, candidate)
        result = _run(
            candidate_strategy, symbol, timeframe, bars,
            initial_capital, risk_percent, fee_percent, slippage_percent,
        )
        metrics = result["metrics"]
        value = _metric(metrics, metric)
        results.append({"params": candidate, "metrics": metrics, "value": value})
        if best is None or (value > _metric(best_metrics, metric)) == maximize:
            best, best_metrics = candidate, metrics

    results.sort(key=lambda r: r["value"], reverse=maximize)
    return best or {}, best_metrics or {}, results


def optimize(
    strategy: dict,
    symbol: str,
    timeframe: str,
    parameters: List[dict],
    metric: str,
    direction: Optional[str] = None,
    mode: str = GRID_MODE,
    folds: int = 5,
    test_ratio: float = 0.3,
    max_evals: int = 400,
    max_bars: Optional[int] = 2000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 10000.0,
    risk_percent: float = 1.0,
    fee_percent: float = 0.05,
    slippage_percent: float = 0.02,
) -> dict:
    if metric not in ALLOWED_METRICS:
        raise ValueError(
            f"Unsupported optimization metric '{metric}'. "
            f"Choose from: {', '.join(sorted(ALLOWED_METRICS))}."
        )
    if mode not in {GRID_MODE, WALK_FORWARD_MODE}:
        raise ValueError(f"Unsupported optimization mode '{mode}'.")
    if not parameters:
        raise ValueError("Provide at least one optimization parameter.")

    specs = _specs(parameters, strategy)
    direction = metric_direction(metric, direction)
    bars = _load_bars(symbol, timeframe, start_date, end_date, max_bars)

    common = dict(
        initial_capital=initial_capital,
        risk_percent=risk_percent,
        fee_percent=fee_percent,
        slippage_percent=slippage_percent,
    )

    combine = {
        "symbol": symbol,
        "timeframe": timeframe,
        "metric": metric,
        "direction": direction,
        "mode": mode,
        "parameters": [
            {"path": path, "min": min(v), "max": max(v), "values_count": len(v)}
            for path, v in specs
        ],
        "combinations_per_estimate": _combos_count(specs),
        "best_params": None,
        "best_metrics": None,
        "top_results": [],
        "grid_total_evals": 0,
        "out_of_sample_metrics": None,
        "walk_forward": None,
    }

    if mode == GRID_MODE:
        train = bars
        oos_bars = None
        if 0.0 < test_ratio < 0.5:
            cut = int(len(bars) * (1 - test_ratio))
            train = bars[:cut]
            oos_bars = bars[cut:]
            if len(oos_bars) < 80:
                oos_bars = None

        best_params, best_metrics, results = _grid_search(
            train, strategy, specs, metric, direction, max_evals,
            symbol, timeframe, **common,
        )
        combine["best_params"] = best_params
        combine["best_metrics"] = best_metrics
        combine["top_results"] = [
            {"params": r["params"], "metrics": r["metrics"]} for r in results[:10]
        ]
        combine["grid_total_evals"] = len(results)

        if oos_bars:
            best_strategy = apply_params(strategy, best_params)
            oos = _run(best_strategy, symbol, timeframe, oos_bars, **common)
            combine["out_of_sample_metrics"] = oos["metrics"]
        return combine

    # ---- Walk-forward ----
    window = len(bars) // folds
    if window < 200:
        raise ValueError(
            f"Not enough data for {folds} walk-forward folds "
            f"(only {len(bars)} bars; each fold needs >= 200)."
        )
    remainder = len(bars) - window * folds
    running_capital = initial_capital
    start = 0
    fold_results = []
    combined_equity: List[dict] = []
    combined_trades: List[dict] = []

    for fold in range(folds):
        wlen = window + (1 if fold < remainder else 0)
        w = bars[start : start + wlen]
        start += wlen

        test_size = max(int(len(w) * test_ratio), 80)
        train = w[: len(w) - test_size]
        test = w[len(w) - test_size :]
        if len(train) < 120:
            raise ValueError("Walk-forward window too small to leave a viable training fold.")

        best_params, train_metrics, _ = _grid_search(
            train, strategy, specs, metric, direction, max_evals,
            symbol, timeframe, **common,
        )
        test_strategy = apply_params(strategy, best_params)
        test_result = _run(
            test_strategy, symbol, timeframe, test,
            initial_capital=running_capital, risk_percent=risk_percent,
            fee_percent=fee_percent, slippage_percent=slippage_percent,
        )
        test_metrics = test_result["metrics"]

        fold_results.append(
            {
                "fold": fold,
                "window_start": w[0]["timestamp"],
                "window_end": w[-1]["timestamp"],
                "train_start": train[0]["timestamp"],
                "train_end": train[-1]["timestamp"],
                "test_start": test[0]["timestamp"],
                "test_end": test[-1]["timestamp"],
                "best_params": best_params,
                "train_metrics": train_metrics,
                "test_metrics": test_metrics,
                "test_trades": test_metrics.get("total_trades", 0),
            }
        )
        combined_equity.extend(test_result["equity_curve"])
        combined_trades.extend(test_result["trade_history"])
        if test_result["equity_curve"]:
            running_capital = test_result["equity_curve"][-1]["equity"]

    combined = _compute_results(
        trades=combined_trades,
        equity_curve=combined_equity,
        initial_capital=initial_capital,
        max_drawdown=_max_drawdown_pct(combined_equity),
        symbol=symbol,
        strategy_name=(
            strategy.get("strategy_name")
            or strategy.get("name")
            or "Walk-forward"
        ),
    )
    combine["walk_forward"] = {
        "folds": fold_results,
        "combined_metrics": combined["metrics"],
        "combined_equity_curve": combined["equity_curve"],
        "combined_trade_history": combined["trade_history"],
        "combined_monthly_performance": combined["monthly_performance"],
    }
    return combine
