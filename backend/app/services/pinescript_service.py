# app/services/pinescript_service.py
"""Convert a strategy JSON config into TradingView PineScript v5 code.

The generator produces clean, copy-paste-ready PineScript that:
- Defines all indicators with user-specified parameters
- Evaluates entry/confirmation/exit rules
- Applies stop-loss and take-profit via strategy.exit
- Works as an overlay on TradingView charts
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Indicator code fragments
# ---------------------------------------------------------------------------

def _indicator_var_name(name: str, params: dict) -> str:
    """Generate a unique Pine variable name for an indicator instance."""
    base = name.lower().replace(" ", "_")
    period = params.get("period", "")
    fast = params.get("fast", "")
    slow = params.get("slow", "")
    signal = params.get("signal", "")
    if fast and slow:
        suffix = f"_{fast}_{slow}" + (f"_{signal}" if signal else "")
    elif period:
        suffix = f"_{period}"
    else:
        suffix = ""
    return f"{base}{suffix}"


def _render_indicator(name: str, params: dict) -> str:
    """Return a PineScript line that calculates the given indicator."""
    n = name.upper()
    var = _indicator_var_name(name, params)

    if n == "RSI":
        period = params.get("period", 14)
        return f"rsi_{period} = ta.rsi(close, {period})"
    elif n == "SMA":
        period = params.get("period", 20)
        return f"sma_{period} = ta.sma(close, {period})"
    elif n == "EMA":
        period = params.get("period", 200)
        return f"ema_{period} = ta.ema(close, {period})"
    elif n == "MACD":
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        return (
            f"[macd_{fast}_{slow}_{signal}, signal_{fast}_{slow}_{signal}, "
            f"hist_{fast}_{slow}_{signal}] = ta.macd(close, {fast}, {slow}, {signal})"
        )
    elif n == "DONCHIAN" or n == "DONCHIAN_CHANNEL":
        period = params.get("period", 20)
        return (
            f"upper_{period} = ta.highest(high, {period})\n"
            f"lower_{period} = ta.lowest(low, {period})"
        )
    elif n == "ATR":
        period = params.get("period", 14)
        return f"atr_{period} = ta.atr({period})"
    elif n == "STOCH" or n == "STOCHASTIC":
        k = params.get("k", 14)
        d = params.get("d", 3)
        return f"stoch_k_{k}_{d} = ta.stoch(close, high, low, {k})\n" \
               f"stoch_d_{k}_{d} = ta.sma(stoch_k_{k}_{d}, {d})"
    elif n == "ADX":
        period = params.get("period", 14)
        return f"adx_{period} = ta.dmi({period}, {period}).adx"
    elif n == "VWAP":
        return "vwap_val = ta.vwap(hlc3)"
    else:
        period = params.get("period", "")
        if period:
            return f"{var} = ta.sma(close, {period})"
        return f"// Unsupported indicator: {name}"


def _render_condition(expr: str, var_map: dict) -> str:
    """Convert a strategy rule condition into a PineScript boolean expression."""
    return expr


# ---------------------------------------------------------------------------
# Rule → PineScript expression mapping
# ---------------------------------------------------------------------------

def _rule_to_pine(condition: str, params: dict) -> str:
    """Map a strategy rule condition + params into a PineScript boolean expression."""
    c = condition.lower()

    if c == "rsi_above":
        p = params.get("period", 14)
        level = params.get("level", 70)
        return f"rsi_{p} > {level}"
    elif c == "rsi_below":
        p = params.get("period", 14)
        level = params.get("level", 30)
        return f"rsi_{p} < {level}"
    elif c == "rsi_cross_above":
        p = params.get("period", 14)
        level = params.get("level", 30)
        return f"ta.crossover(rsi_{p}, {level})"
    elif c == "rsi_cross_below":
        p = params.get("period", 14)
        level = params.get("level", 70)
        return f"ta.crossunder(rsi_{p}, {level})"
    elif c == "price_above_ma":
        p = params.get("period", 200)
        ma = params.get("ma", "sma").lower()
        return f"close > {ma}_{p}"
    elif c == "price_below_ma":
        p = params.get("period", 200)
        ma = params.get("ma", "sma").lower()
        return f"close < {ma}_{p}"
    elif c == "price_cross_above_ma":
        p = params.get("period", 200)
        ma = params.get("ma", "sma").lower()
        return f"ta.crossover(close, {ma}_{p})"
    elif c == "price_cross_below_ma":
        p = params.get("period", 200)
        ma = params.get("ma", "sma").lower()
        return f"ta.crossunder(close, {ma}_{p})"
    elif c == "ma_cross_above":
        fast = params.get("fast", 50)
        slow = params.get("slow", 200)
        ma = params.get("ma", "sma").lower()
        return f"ta.crossover({ma}_{fast}, {ma}_{slow})"
    elif c == "ma_cross_below":
        fast = params.get("fast", 50)
        slow = params.get("slow", 200)
        ma = params.get("ma", "sma").lower()
        return f"ta.crossunder({ma}_{fast}, {ma}_{slow})"
    elif c == "macd_above":
        f_ = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        return f"macd_{f_}_{s}_{sig} > signal_{f_}_{s}_{sig}"
    elif c == "macd_below":
        f_ = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        return f"macd_{f_}_{s}_{sig} < signal_{f_}_{s}_{sig}"
    elif c == "macd_cross_above":
        f_ = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        return f"ta.crossover(macd_{f_}_{s}_{sig}, signal_{f_}_{s}_{sig})"
    elif c == "macd_cross_below":
        f_ = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        return f"ta.crossunder(macd_{f_}_{s}_{sig}, signal_{f_}_{s}_{sig})"
    elif c == "price_breakout_above":
        p = params.get("period", 20)
        return f"close > ta.highest(high[{1}], {p})"
    elif c == "price_breakdown_below":
        p = params.get("period", 20)
        return f"close < ta.lowest(low[{1}], {p})"
    elif c == "price_above":
        level = params.get("level", 0)
        return f"close > {level}"
    elif c == "price_below":
        level = params.get("level", 0)
        return f"close < {level}"
    else:
        return f"// Unknown condition: {condition}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pinescript(config: Dict[str, Any]) -> str:
    """Generate TradingView PineScript v5 code from a strategy config dict.

    Parameters
    ----------
    config : dict
        The strategy configuration (same shape as StrategyCreate / StrategyOut).

    Returns
    -------
    str
        Complete PineScript v5 source code ready to paste into TradingView.
    """
    name = config.get("name", "TradePilot Strategy")
    direction = config.get("direction", "LONG").upper()
    indicators = config.get("indicators") or []
    entry_rules = config.get("entry_rules") or []
    confirm_rules = config.get("confirmation_rules") or []
    exit_rules = config.get("exit_rules") or []
    sl_type = config.get("stop_loss_type")
    sl_value = config.get("stop_loss_value")
    tp_type = config.get("take_profit_type")
    tp_value = config.get("take_profit_value")
    risk = config.get("risk_per_trade", 1.0)
    timeframe = config.get("timeframe", "4H")

    lines: List[str] = []

    # Header
    safe_name = name.replace('"', '\\"')[:40]
    lines.append("//@version=5")
    lines.append(f'strategy("{safe_name}", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value={risk})')
    lines.append("")

    # Indicators
    rendered = set()
    for ind in indicators:
        ind_name = ind.get("name", "")
        ind_params = {}
        if ind.get("period"):
            ind_params["period"] = ind["period"]
        if ind_name.upper() == "MACD":
            ind_params.setdefault("fast", 12)
            ind_params.setdefault("slow", 26)
            ind_params.setdefault("signal", 9)

        code = _render_indicator(ind_name, ind_params)
        for line in code.split("\n"):
            key = line.split("=")[0].strip() if "=" in line else line
            if key not in rendered:
                lines.append(line)
                rendered.add(key)

    # Also ensure any indicators referenced by rules but not in the indicators list are declared
    all_periods = set()
    for rule in entry_rules + confirm_rules + exit_rules:
        params = rule.get("params", {})
        c = rule.get("condition", "")
        if "rsi" in c:
            p = params.get("period", 14)
            key = f"rsi_{p}"
            if key not in rendered:
                lines.append(f"rsi_{p} = ta.rsi(close, {p})")
                rendered.add(key)
        if "ma" in c or "price_" in c:
            period = params.get("period", 200)
            ma = params.get("ma", "sma").lower()
            key = f"{ma}_{period}"
            if key not in rendered:
                lines.append(f"{ma}_{period} = ta.{'sma' if ma == 'sma' else 'ema'}(close, {period})")
                rendered.add(key)
        if "macd" in c:
            f_ = params.get("fast", 12)
            s = params.get("slow", 26)
            sig = params.get("signal", 9)
            key = f"macd_{f_}_{s}_{sig}"
            if key not in rendered:
                lines.append(
                    f"[macd_{f_}_{s}_{sig}, signal_{f_}_{s}_{sig}, hist_{f_}_{s}_{sig}] = "
                    f"ta.macd(close, {f_}, {s}, {sig})"
                )
                rendered.add(key)

    lines.append("")

    # Entry conditions
    entry_parts = []
    for rule in entry_rules:
        pine_expr = _rule_to_pine(rule.get("condition", ""), rule.get("params", {}))
        entry_parts.append(pine_expr)

    confirm_parts = []
    for rule in confirm_rules:
        pine_expr = _rule_to_pine(rule.get("condition", ""), rule.get("params", {}))
        confirm_parts.append(pine_expr)

    exit_parts = []
    for rule in exit_rules:
        pine_expr = _rule_to_pine(rule.get("condition", ""), rule.get("params", {}))
        exit_parts.append(pine_expr)

    # Build entry logic
    if entry_parts:
        entry_expr = " and ".join(entry_parts)
        if confirm_parts:
            confirm_expr = " and ".join(confirm_parts)
            entry_combined = f"({entry_expr}) and ({confirm_expr})"
        else:
            entry_combined = entry_expr

        lines.append("// Entry condition")
        if direction == "LONG":
            lines.append(f"long_entry = {entry_combined}")
            lines.append("if long_entry")
            lines.append('    strategy.entry("LONG", strategy.long)')
        else:
            lines.append(f"short_entry = {entry_combined}")
            lines.append("if short_entry")
            lines.append('    strategy.entry("SHORT", strategy.short)')
        lines.append("")

    # Exit conditions
    if exit_parts:
        exit_expr = " and ".join(exit_parts)
        lines.append("// Exit condition")
        if direction == "LONG":
            lines.append(f"long_exit = {exit_expr}")
            lines.append("if long_exit")
            lines.append('    strategy.close("LONG")')
        else:
            lines.append(f"short_exit = {exit_expr}")
            lines.append("if short_exit")
            lines.append('    strategy.close("SHORT")')
        lines.append("")

    # Stop loss / Take profit
    if sl_value or tp_value:
        lines.append("// Stop loss & Take profit")
        sl_pct = sl_value if sl_type == "percent" else None
        tp_pct = tp_value if tp_type == "percent" else None

        if direction == "LONG":
            sl_pct = sl_pct or 2.0
            tp_pct = tp_pct or 4.0
            lines.append(
                f'strategy.exit("TP/SL", "LONG", '
                f'profit={tp_pct * 100}, loss={sl_pct * 100})'
            )
        else:
            sl_pct = sl_pct or 2.0
            tp_pct = tp_pct or 4.0
            lines.append(
                f'strategy.exit("TP/SL", "SHORT", '
                f'profit={tp_pct * 100}, loss={sl_pct * 100})'
            )
        lines.append("")

    # Plot indicators for visual reference
    lines.append("// Visual plots")
    for ind in indicators:
        ind_name = ind.get("name", "").upper()
        ind_params = {}
        if ind.get("period"):
            ind_params["period"] = ind["period"]
        if ind_name == "RSI":
            p = ind_params.get("period", 14)
            lines.append(f"plot(rsi_{p}, 'RSI {p}', color=color.orange, display=display.pane)")
        elif ind_name in ("SMA", "EMA"):
            p = ind_params.get("period", 20)
            ma_type = "sma" if ind_name == "SMA" else "ema"
            lines.append(f"plot({ma_type}_{p}, '{ind_name} {p}', color=color.blue)")
        elif ind_name == "MACD":
            f_ = ind_params.get("fast", 12)
            s = ind_params.get("slow", 26)
            sig = ind_params.get("signal", 9)
            lines.append(f"plot(macd_{f_}_{s}_{sig}, 'MACD', color=color.blue, display=display.pane)")
            lines.append(f"plot(signal_{f_}_{s}_{sig}, 'Signal', color=color.red, display=display.pane)")

    lines.append("")
    lines.append("// Generated by TradePilot AI — https://tradepilot-ai.vercel.app")

    return "\n".join(lines)


def generate_pinescript_from_strategy(strategy) -> str:
    """Convenience wrapper that accepts a Strategy model or dict."""
    if hasattr(strategy, "model_dump"):
        config = strategy.model_dump()
    elif hasattr(strategy, "__dict__"):
        config = {
            "name": getattr(strategy, "name", "TradePilot Strategy"),
            "direction": getattr(strategy, "direction", "LONG"),
            "indicators": getattr(strategy, "indicators", []) or [],
            "entry_rules": getattr(strategy, "entry_rules", []) or [],
            "confirmation_rules": getattr(strategy, "confirmation_rules", []) or [],
            "exit_rules": getattr(strategy, "exit_rules", []) or [],
            "stop_loss_type": getattr(strategy, "stop_loss_type", None),
            "stop_loss_value": getattr(strategy, "stop_loss_value", None),
            "take_profit_type": getattr(strategy, "take_profit_type", None),
            "take_profit_value": getattr(strategy, "take_profit_value", None),
            "risk_per_trade": getattr(strategy, "risk_per_trade", 1.0),
            "timeframe": getattr(strategy, "timeframe", "4H"),
        }
    else:
        config = dict(strategy)
    return generate_pinescript(config)
