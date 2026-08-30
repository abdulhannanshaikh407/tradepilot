# app/services/signal_engine.py
"""Generates explainable trading signals from a strategy.

Evaluates the strategy's canonical rules against the latest available market
bar and explains WHY a signal fired (and optionally why a rule has not fired).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.backtest_engine import RuleContext, evaluate_rule_group
from app.services.market_data_service import get_live_quote, get_provider

RULE_DESCRIPTIONS = {
    "rsi_above": "RSI above {level}",
    "rsi_below": "RSI below {level}",
    "rsi_cross_above": "RSI crossed back above {level}",
    "rsi_cross_below": "RSI crossed below {level}",
    "price_above_ma": "Price above {ma} {period}",
    "price_below_ma": "Price below {ma} {period}",
    "price_cross_above_ma": "Price crossed above {ma} {period}",
    "price_cross_below_ma": "Price crossed below {ma} {period}",
    "ma_cross_above": "{fast}-{ma} crossed above {slow}-{ma}",
    "ma_cross_below": "{fast}-{ma} crossed below {slow}-{ma}",
    "macd_above": "MACD above signal line",
    "macd_below": "MACD below signal line",
    "macd_cross_above": "MACD crossed above signal line",
    "macd_cross_below": "MACD crossed below signal line",
    "price_breakout_above": "Price broke above {period}-bar high",
    "price_breakdown_below": "Price broke below {period}-bar low",
    "price_above": "Price above {level}",
    "price_below": "Price below {level}",
    "always": "Condition always true",
}


def describe_rule(rule: dict) -> str:
    params = rule.get("params", {}) or {}
    template = RULE_DESCRIPTIONS.get(rule.get("condition"), rule.get("condition", "rule"))
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return template


def reasons_for_group(
    rctx: RuleContext, i: int, group: Optional[dict]
) -> List[Dict[str, Any]]:
    """Return which conditions in a group are true at bar i (for the signal card)."""
    reasons = []
    conditions = (group or {}).get("conditions", [])
    logic = (group or {}).get("logic", "all")
    for condition in conditions:
        from app.services.backtest_engine import _a

        fired = bool(_a(rctx, i, condition.get("condition", "always"), condition.get("params", {})))
        reasons.append(
            {
                "condition": condition.get("condition"),
                "description": describe_rule(condition),
                "params": condition.get("params", {}),
                "fired": fired,
            }
        )
    if reasons and logic == "any" and any(r["fired"] for r in reasons):
        pass
    return reasons


def generate_signal(
    strategy: Dict[str, Any],
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate the latest market bar against the strategy and return a signal
    suggestion with an explanation. Returns fired rules as `reasons`."""
    symbol = symbol or strategy.get("asset") or "BTC/USD"
    timeframe = timeframe or strategy.get("timeframe") or "4H"

    bars = get_provider().get_ohlcv(symbol, timeframe)
    rctx = RuleContext(bars)
    i = len(bars) - 1

    rules = strategy.get("rules") or {
        "entry": {"logic": "all", "conditions": strategy.get("entry_rules", [])},
        "confirmation": {"logic": "all", "conditions": strategy.get("confirmation_rules", [])},
        "exit": {"logic": "any", "conditions": strategy.get("exit_rules", [])},
    }

    entry_group = rules.get("entry", {"logic": "all", "conditions": []})
    confirm_group = rules.get("confirmation", {"logic": "all", "conditions": []})
    exit_group = rules.get("exit", {"logic": "any", "conditions": []})

    entry_reasons = reasons_for_group(rctx, i, entry_group)
    confirm_reasons = reasons_for_group(rctx, i, confirm_group)
    exit_reasons = reasons_for_group(rctx, i, exit_group)

    entry_fired = evaluate_rule_group(rctx, i, entry_group)
    confirm_fired = evaluate_rule_group(rctx, i, confirm_group)
    signal_fires = entry_fired and confirm_fired
    exit_fired = evaluate_rule_group(rctx, i, exit_group)

    close = rctx.closes[i]
    stop_value = strategy.get("stop_loss_value")
    stop_type = strategy.get("stop_loss_type")
    target_value = strategy.get("take_profit_value")
    target_type = strategy.get("take_profit_type")
    is_long = (strategy.get("direction") or "LONG").upper() == "LONG"

    stop_price = None
    if stop_value and stop_type == "percent":
        stop_price = close * (1 - stop_value / 100) if is_long else close * (1 + stop_value / 100)
    elif stop_value:
        stop_price = float(stop_value)

    target_price = None
    if target_value and target_type == "percent":
        target_price = close * (1 + target_value / 100) if is_long else close * (1 - target_value / 100)
    elif target_value:
        target_price = float(target_value)

    reasons = [r for r in entry_reasons + confirm_reasons if r["fired"]]

    if signal_fires and not exit_fired:
        status = "PENDING"
        reason_text = "All entry conditions are satisfied: " + "; ".join(
            r["description"] for r in reasons
        )
    else:
        status = "PENDING"
        blocked = [r for r in entry_reasons + confirm_reasons if not r["fired"]]
        reason_text = "Entry conditions not fully satisfied. "
        if blocked:
            reason_text += "Waiting for: " + "; ".join(r["description"] for r in blocked[:3])
        elif exit_fired:
            reason_text += "Exit conditions currently active."
        else:
            reason_text += "No entry trigger on the latest bar."

    rr = None
    if stop_price and target_price:
        risk_side = abs(close - stop_price)
        reward_side = abs(target_price - close)
        if risk_side > 0:
            rr = round(reward_side / risk_side, 2)

    conf = min(95, max(60, int(strategy.get("confidence") or 70)))
    live_quote = get_live_quote(symbol)

    # Prefer the fresh TradingView-sourced price for the suggested entry/ST/TP
    # so paper signals match the real market when a live feed exists.
    live_price = float(live_quote["price"]) if live_quote else None
    return {
        "symbol": symbol,
        "direction": strategy.get("direction") or "LONG",
        "entry_price": round(live_price, 6) if live_price else round(close, 6),
        "stop_loss": round(stop_price, 6) if stop_price else None,
        "take_profit": round(target_price, 6) if target_price else None,
        "risk_reward": rr,
        "confidence": conf,
        "status": status,
        "reasons": reasons[:6],
        "reason": reason_text,
        "source": strategy.get("source") or "signal_engine",
        "signal_fires": bool(signal_fires and not exit_fired),
        "data_source": (live_quote or {}).get("source", "simulated"),
    }


def build_strategy_rules_dict(strategy: Any) -> Dict[str, Any]:
    """Turn a StrategyModel into the engine-style rules dict for signal gen."""
    return {
        "rules": {
            "entry": {"logic": "all", "conditions": list(strategy.entry_rules or [])},
            "confirmation": {"logic": "all", "conditions": list(strategy.confirmation_rules or [])},
            "exit": {"logic": "any", "conditions": list(strategy.exit_rules or [])},
        },
        "entry_rules": list(strategy.entry_rules or []),
        "confirmation_rules": list(strategy.confirmation_rules or []),
        "exit_rules": list(strategy.exit_rules or []),
        "stop_loss_type": strategy.stop_loss_type,
        "stop_loss_value": strategy.stop_loss_value,
        "take_profit_type": strategy.take_profit_type,
        "take_profit_value": strategy.take_profit_value,
        "direction": strategy.direction,
        "confidence": strategy.confidence,
        "asset": strategy.asset,
        "timeframe": strategy.timeframe,
        "source": strategy.source,
    }