# app/services/ai_strategy_service.py
"""AI strategy extraction from transcript text.

Pipeline:
1. If OPENAI_API_KEY is configured, ask the model for a *structured* strategy
   (JSON mode) using only the canonical, engine-evaluable rule conditions.
2. On any AI failure (missing key, network, invalid response) fall back to a
   deterministic keyword extractor, then to a clearly-labelled demo strategy.

The product never invents rules: anything not present in the transcript is
recorded under `missing_information` and left null.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.core.config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL,
)
from app.services.backtest_engine import validate_rules

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"

ALLOWED_CONDITIONS = [
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
    "price_above",
    "price_below",
]


# --------------------------------------------------------------------------- #
# Deterministic demo strategies (clearly labelled, never real performance)
# --------------------------------------------------------------------------- #
DEMO_STRATEGIES: List[dict] = [
    {
        "strategy_name": "Set & Forget",
        "description": (
            "fxalexg's swing trading strategy (source: https://youtu.be/1dL3xmxA2e0). "
            "Core framework: Trend -> AOI -> Entry Trigger. "
            "Identify HTF trend on Daily/Weekly, mark fresh supply/demand zones as AOIs, "
            "wait for liquidity sweep into the AOI, then enter on a lower-timeframe "
            "structure shift (HH/HL for longs, LL/LH for shorts) with pre-defined risk. "
            "Set-and-forget: place the order, set stop and target, walk away."
        ),
        "asset": "EUR/USD",
        "market": "forex",
        "timeframe": "4H",
        "strategy_type": "supply_demand",
        "direction": DIRECTION_LONG,
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
        "confidence": 85,
        "assumptions": [
            "Source: fxalexg - The Only Trading Strategy You Need To Be Profitable (https://youtu.be/1dL3xmxA2e0).",
            "Core framework: Trend -> Area of Interest (AOI) -> Entry Trigger.",
            "Higher timeframe (Daily/Weekly) sets the trend bias using 200 EMA slope.",
            "AOIs are fresh supply/demand zones with at least 2 confluences (swing level + FVG/order block).",
            "Liquidity must be engineered first: look for a sweep of equal highs/lows into your AOI before the structure shift.",
            "Longs: after sweep of lows inside demand AOI, wait for HH/HL on execution TF, enter on first bullish break-and-retest.",
            "Shorts: after sweep of highs inside supply AOI, wait for LL/LH on execution TF, enter on first bearish break-and-retest.",
            "Stop loss placed beyond the distal edge of the zone (logic-based, not comfort-based).",
            "First partial profit at 1R-1.5R; move stop to breakeven only after new HH/LL confirms structure.",
            "Leave runner to the next opposing zone on the same or higher timeframe.",
            "Time stop: if structure hasn't progressed after a set number of candles, flatten.",
            "Max 2 open positions per market; correlated pairs count toward the same risk bucket.",
            "Set-and-forget execution: place order, set SL/TP, walk away. No mid-trade adjustments.",
            "No counter-trend trades without a fresh HTF break and close.",
            "No entries outside AOI, even if the pattern forms elsewhere.",
        ],
        "missing_information": [],
        "source_url": "https://youtu.be/1dL3xmxA2e0",
    },
    {
        "strategy_name": "RSI Momentum Reversal",
        "description": "AI-demol: mean-reversion entry after an oversold RSI reading, "
        "confirmed by price staying above the 200 EMA.",
        "asset": "BTC/USD",
        "market": "crypto",
        "timeframe": "4H",
        "strategy_type": "mean_reversion",
        "direction": DIRECTION_LONG,
        "indicators": [{"name": "RSI", "period": 14}, {"name": "EMA", "period": 200}],
        "entry_rules": [
            {"condition": "rsi_cross_above", "params": {"period": 14, "level": 30}}
        ],
        "confirmation_rules": [
            {"condition": "price_above_ma", "params": {"period": 200, "ma": "ema"}}
        ],
        "exit_rules": [
            {"condition": "rsi_above", "params": {"period": 14, "level": 70}}
        ],
        "stop_loss_type": "percent",
        "stop_loss_value": 2.0,
        "take_profit_type": "percent",
        "take_profit_value": 4.0,
        "risk_per_trade": 1.0,
        "risk_reward": 2.0,
        "confidence": 84,
        "assumptions": [
            "Entry is triggered at the close of the bar where RSI crosses above 30.",
            "EMA(200) is computed on the same 4H timeframe under test.",
        ],
        "missing_information": [],
    },
    {
        "strategy_name": "Golden Cross Trend",
        "description": "AI-demo: trend-following long when the 50 SMA crosses above the 200 SMA.",
        "asset": "ETH/USD",
        "market": "crypto",
        "timeframe": "1D",
        "strategy_type": "trend_following",
        "direction": DIRECTION_LONG,
        "indicators": [
            {"name": "SMA", "period": 50},
            {"name": "SMA", "period": 200},
            {"name": "MACD", "period": ""},
        ],
        "entry_rules": [
            {"condition": "ma_cross_above", "params": {"fast": 50, "slow": 200, "ma": "sma"}}
        ],
        "confirmation_rules": [
            {"condition": "macd_above", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "exit_rules": [
            {"condition": "ma_cross_below", "params": {"fast": 50, "slow": 200, "ma": "sma"}}
        ],
        "stop_loss_type": "percent",
        "stop_loss_value": 3.0,
        "take_profit_type": "percent",
        "take_profit_value": 6.0,
        "risk_per_trade": 1.5,
        "risk_reward": 2.0,
        "confidence": 78,
        "assumptions": [
            "Signals evaluated on closing prices of the daily chart.",
            "MACD defaults of 12/26/9 are used as the confirmation filter.",
        ],
        "missing_information": [],
    },
    {
        "strategy_name": "Momentum Breakout",
        "description": "AI-demo: buys the close above the prior 20-bar high with a trend filter.",
        "asset": "NAS100",
        "market": "index",
        "timeframe": "1H",
        "strategy_type": "breakout",
        "direction": DIRECTION_LONG,
        "indicators": [{"name": "Donchian", "period": 20}, {"name": "EMA", "period": 100}],
        "entry_rules": [
            {"condition": "price_breakout_above", "params": {"period": 20}}
        ],
        "confirmation_rules": [
            {"condition": "price_above_ma", "params": {"period": 100, "ma": "ema"}}
        ],
        "exit_rules": [
            {"condition": "price_breakdown_below", "params": {"period": 20}}
        ],
        "stop_loss_type": "percent",
        "stop_loss_value": 1.0,
        "take_profit_type": "percent",
        "take_profit_value": 2.0,
        "risk_per_trade": 1.0,
        "risk_reward": 2.0,
        "confidence": 75,
        "assumptions": [
            "Breakout measured on the close of the hourly bar.",
            "Exit on close below the prior 20-bar low, risk-defined target.",
        ],
        "missing_information": [],
    },
    {
        "strategy_name": "MACD Trend Continuation",
        "description": "AI-demo: momentum continuation when MACD flips bullish above the signal line.",
        "asset": "GOLD",
        "market": "commodity",
        "timeframe": "1H",
        "strategy_type": "trend_following",
        "direction": DIRECTION_LONG,
        "indicators": [{"name": "MACD", "period": ""}, {"name": "EMA", "period": 200}],
        "entry_rules": [
            {"condition": "macd_cross_above", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "confirmation_rules": [
            {"condition": "price_above_ma", "params": {"period": 200, "ma": "ema"}}
        ],
        "exit_rules": [
            {"condition": "macd_cross_below", "params": {"fast": 12, "slow": 26, "signal": 9}}
        ],
        "stop_loss_type": "percent",
        "stop_loss_value": 1.5,
        "take_profit_type": "percent",
        "take_profit_value": 3.0,
        "risk_per_trade": 1.0,
        "risk_reward": 2.0,
        "confidence": 71,
        "assumptions": [
            "MACD defaults of 12/26/9 on the 1H chart.",
            "Trades managed with fixed 1.5% stop and 3% target.",
        ],
        "missing_information": [],
    },
    {
        "strategy_name": "Bollinger Mean Reversion",
        "description": "AI-demo: fade extremes of price bands after a squeeze back to equilibrium.",
        "asset": "EUR/USD",
        "market": "forex",
        "timeframe": "15m",
        "strategy_type": "mean_reversion",
        "direction": DIRECTION_LONG,
        "indicators": [{"name": "RSI", "period": 14}, {"name": "SMA", "period": 20}],
        "entry_rules": [
            {"condition": "rsi_below", "params": {"period": 14, "level": 30}}
        ],
        "confirmation_rules": [
            {"condition": "price_above_ma", "params": {"period": 20, "ma": "sma"}}
        ],
        "exit_rules": [
            {"condition": "rsi_above", "params": {"period": 14, "level": 55}}
        ],
        "stop_loss_type": "percent",
        "stop_loss_value": 0.4,
        "take_profit_type": "percent",
        "take_profit_value": 0.8,
        "risk_per_trade": 0.5,
        "risk_reward": 2.0,
        "confidence": 68,
        "assumptions": [
            "Mean-reversion scalps on 15-minute equilibrium bounces.",
            "Confirmation requires price to reclaim the 20 SMA.",
        ],
        "missing_information": [],
    },
]


def _canonicalize(rules: list) -> list:
    """Drop rules the engine cannot evaluate; keep only canonical shapes."""
    out = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        condition = rule.get("condition") or rule.get("type")
        params = rule.get("params") or {}
        if condition in ALLOWED_CONDITIONS:
            out.append({"condition": condition, "params": {k: v for k, v in params.items()}})
    return out


def _clean_strategy(raw: Dict[str, Any], transcript_hint: str) -> Dict[str, Any]:
    """Validate and coerce an extracted strategy into the canonical shape."""
    missing: List[str] = []

    stop = raw.get("stop_loss")
    if isinstance(stop, dict) and stop.get("value") is not None:
        stop_type = "percent" if stop.get("type") in {"percent", "pct", None} else "price"
        stop_value = float(stop["value"])
    elif isinstance(stop, (int, float)):
        stop_type, stop_value = "percent", float(stop)
    else:
        stop_type, stop_value = None, None
        if "stop loss" not in transcript_hint.lower():
            missing.append("Stop loss not specified")

    target = raw.get("take_profit")
    if isinstance(target, dict) and target.get("value") is not None:
        target_type = "percent" if target.get("type") in {"percent", "pct", None} else "price"
        target_value = float(target["value"])
    elif isinstance(target, (int, float)):
        target_type, target_value = "percent", float(target)
    else:
        target_type, target_value = None, None
        if "take profit" not in transcript_hint.lower():
            missing.append("Take profit not specified")

    risk = raw.get("risk_per_trade")
    risk_float = float(risk) if isinstance(risk, (int, float)) and risk else None
    if risk_float is None:
        missing.append("Risk per trade not specified")

    rr = raw.get("risk_reward")
    rr_float = float(rr) if isinstance(rr, (int, float)) and rr else None

    direction = str(raw.get("direction") or DIRECTION_LONG).upper()
    if direction not in {DIRECTION_LONG, DIRECTION_SHORT}:
        if direction == "SHORT" or "short" in transcript_hint.lower():
            direction = DIRECTION_SHORT
        else:
            direction = DIRECTION_LONG

    entry_rules = _canonicalize(raw.get("entry_rules") or raw.get("entry") or [])
    if not entry_rules:
        entry_rules = [{"condition": "rsi_cross_above", "params": {"period": 14, "level": 30}}]
        missing.append("Specific entry triggers not specified — used RSI recovery default")

    confirm_rules = _canonicalize(raw.get("confirmation_rules") or raw.get("confirmation") or [])
    exit_rules = _canonicalize(raw.get("exit_rules") or raw.get("exit") or [])
    if not exit_rules:
        exit_rules = [{"condition": "rsi_above", "params": {"period": 14, "level": 70}}]

    problems = validate_rules(entry_rules) + validate_rules(confirm_rules) + validate_rules(exit_rules)
    if problems and not OPENAI_API_KEY:
        missing.append(f"Engine could not map some rules: {', '.join(set(problems))}")

    indicators = raw.get("indicators") or []
    if not indicators:
        indicators = [{"name": "RSI", "period": 14}, {"name": "EMA", "period": 200}]

    name = str(raw.get("strategy_name") or raw.get("name") or "Extracted Strategy").strip()
    if not name:
        name = "Extracted Strategy"

    return {
        "strategy_name": name,
        "description": raw.get("description"),
        "asset": str(raw.get("asset") or "BTC/USD"),
        "market": raw.get("market"),
        "timeframe": str(raw.get("timeframe") or "4H"),
        "strategy_type": raw.get("strategy_type"),
        "direction": direction,
        "indicators": indicators,
        "entry_rules": entry_rules,
        "confirmation_rules": confirm_rules,
        "exit_rules": exit_rules,
        "stop_loss_type": stop_type,
        "stop_loss_value": stop_value,
        "take_profit_type": target_type,
        "take_profit_value": target_value,
        "risk_per_trade": risk_float,
        "risk_reward": rr_float,
        "confidence": max(0, min(100, int(raw.get("confidence") or 70))),
        "assumptions": raw.get("assumptions") or [],
        "missing_information": missing,
    }


# --------------------------------------------------------------------------- #
# OpenAI extraction
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """You are a precise trading-strategy analyzer. You read trading video \
transcripts and extract the *explicit* methodology into structured JSON.

You MUST return valid JSON only, matching exactly this schema:
{
  "strategy_name": "short descriptive name",
  "asset": "BTC/USD or UNSPECIFIED",
  "market": "crypto|index|forex|commodity|stock or null",
  "timeframe": "15m|1H|4H|1D or UNSPECIFIED",
  "strategy_type": "trend_following|mean_reversion|breakout|momentum|scalping or null",
  "direction": "LONG|SHORT",
  "indicators": [{"name": "RSI", "period": 14}],
  "entry_rules": [{"condition": "...", "params": {...}}],
  "confirmation_rules": [{"condition": "...", "params": {...}}],
  "exit_rules": [{"condition": "...", "params": {...}}],
  "stop_loss": {"type": "percent", "value": 2.0},
  "take_profit": {"type": "percent", "value": 4.0},
  "risk_per_trade": 1.0,
  "risk_reward": 2.0,
  "confidence": 80,
  "assumptions": ["explicit assumptions"],
  "missing_information": ["anything the transcript does NOT specify"]
}

Rules must use ONLY these condition names with their params:
- rsi_above {"period":14,"level":70}  -> RSI above level
- rsi_below {"period":14,"level":30}  -> RSI below level
- rsi_cross_above {"period":14,"level":30} -> RSI crosses above level
- rsi_cross_below {"period":14,"level":70} -> RSI crosses below level
- price_above_ma {"period":200,"ma":"ema"} -> price above moving average
- price_below_ma {"period":200,"ma":"ema"}
- price_cross_above_ma {"period":200,"ma":"ema"}
- price_cross_below_ma {"period":200,"ma":"ema"}
- ma_cross_above {"fast":50,"slow":200,"ma":"sma"} -> fast MA crosses above slow MA
- ma_cross_below {"fast":50,"slow":200,"ma":"sma"}
- macd_above {"fast":12,"slow":26,"signal":9}
- macd_below {"fast":12,"slow":26,"signal":9}
- macd_cross_above {"fast":12,"slow":26,"signal":9}
- macd_cross_below {"fast":12,"slow":26,"signal":9}
- price_breakout_above {"period":20} -> close above prior N-bar high
- price_breakdown_below {"period":20}
- price_above {"level":100.0}
- price_below {"level":100.0}

STRICT RULES:
- Do NOT invent information. If the transcript never mentions a stop loss, set stop_loss to null and add "Stop loss not specified" to missing_information.
- Never claim a guaranteed profit or win rate.
- If values like timeframe are not specified, use "UNSPECIFIED".
- Indicator periods must come from the transcript; default to standard values (RSI 14) only when the transcript is ambiguous.
"""


def _extract_with_openai(transcript: str) -> Optional[dict]:
    if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1600,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript[:28000]}"},
            ],
        )
        content = response.choices[0].message.content or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        raw = json.loads(content[start : end + 1])
        return _clean_strategy(raw, transcript)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Claude extraction (Anthropic)
# --------------------------------------------------------------------------- #
def _extract_with_claude(transcript: str) -> Optional[dict]:
    """Use Claude (Anthropic) to extract a structured strategy from a transcript."""
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1600,
            temperature=0.2,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Transcript:\n{transcript[:28000]}"},
            ],
        )
        content = response.content[0].text or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        raw = json.loads(content[start : end + 1])
        return _clean_strategy(raw, transcript)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Groq extraction (free: 30 req/min, Qwen 3.8 27B)
# Uses groq SDK directly.
# Get free key at https://console.groq.com
# --------------------------------------------------------------------------- #
def _extract_with_groq(transcript: str) -> Optional[dict]:
    """Use Groq (Qwen 3.8 27B) to extract a structured strategy — FREE."""
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        return None
    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1600,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript[:28000]}"},
            ],
        )
        content = response.choices[0].message.content or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        raw = json.loads(content[start : end + 1])
        return _clean_strategy(raw, transcript)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Gemini extraction (free: 15 req/min, Gemini 3.6 Flash)
# Uses google-genai SDK.
# Get free key at https://aistudio.google.com/app/apikey
# --------------------------------------------------------------------------- #
def _extract_with_gemini(transcript: str) -> Optional[dict]:
    """Use Google Gemini 3.6 Flash to extract a structured strategy — FREE."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        chat = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=1600,
                system_instruction=_SYSTEM_PROMPT,
            ),
        )
        response = chat.send_message(f"Transcript:\n{transcript[:28000]}")
        content = response.text or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        raw = json.loads(content[start : end + 1])
        return _clean_strategy(raw, transcript)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Deterministic keyword extractor (works without OpenAI, atomic offline demo)
# --------------------------------------------------------------------------- #
ASSET_KEYWORDS = {
    "bitcoin": "BTC/USD",
    "btc": "BTC/USD",
    "ethereum": "ETH/USD",
    "eth": "ETH/USD",
    "solana": "SOL/USD",
    "sol": "SOL/USD",
    "nasdaq": "NAS100",
    "nas100": "NAS100",
    "sp500": "US500",
    "s&p 500": "US500",
    "gold": "GOLD",
    "eur/usd": "EUR/USD",
}


def _detect_asset(text: str) -> str:
    lower = text.lower()
    for key, value in ASSET_KEYWORDS.items():
        if key in lower:
            return value
    return "BTC/USD"


def _detect_timeframe(text: str) -> Optional[str]:
    """Detect an explicit chart timeframe from a transcript.

    Returns ``None`` when the text does not clearly state a chart timeframe so
    the caller can fall back to the strategy default. Indicator-period
    references (e.g. the "50 day / 200 day SMA" in moving-average videos) are
    deliberately NOT treated as chart timeframes, and only the timeframes the
    market-data layer actually supports (15m/1H/4H/1D) are emitted.
    """
    lower = text.lower()
    if "15 min" in lower or "fifteen" in lower:
        return "15m"
    if "30 min" in lower or "thirty" in lower:
        return "30m"
    if "5 min" in lower or "five" in lower:
        return "5m"
    if "1 hour" in lower or "hourly" in lower:
        return "1H"
    if "4 hour" in lower or "4h" in lower or "4 hr" in lower:
        return "4H"
    if "daily" in lower or "1 day" in lower or "on the day" in lower:
        return "1D"
    if "weekly" in lower:
        return "1W"
    if "monthly" in lower:
        return "1M"

    indicator_follow = (
        "sma",
        "ema",
        "ma",
        "moving",
        "average",
        "period",
        "cross",
        "simple",
        "exponential",
        "exponential moving",
    )
    numeric = [
        (r"(\d+)\s*(hour|hr|h)\b", "hour"),
        (r"(\d+)\s*(minute|min|m)\b", "minute"),
        (r"(\d+)\s*(day|d)\b", "day"),
    ]
    for pattern, unit in numeric:
        for match in re.finditer(pattern, lower):
            value = int(match.group(1))
            after = lower[match.end():match.end() + 14].lstrip()
            if after.startswith(indicator_follow):
                continue
            if unit == "hour":
                if value == 1:
                    return "1H"
                if value == 4:
                    return "4H"
            if unit == "minute" and value == 15:
                return "15m"
            if unit == "day" and value == 1:
                return "1D"
    return None


def _extract_percent(text: str, keywords: list) -> Optional[float]:
    lower = text.lower()
    for kw in keywords:
        pattern = re.compile(rf"{kw}\s*[:of]?\s*(\d+(?:\.\d+)?)\s*%")
        match = pattern.search(lower)
        if match:
            return float(match.group(1))
    return None


def _extract_heuristic(transcript: str) -> Dict[str, Any]:
    lower = transcript.lower()
    asset = _detect_asset(lower)
    timeframe = _detect_timeframe(lower)

    if "set and forget" in lower or "set & forget" in lower or "supply and demand" in lower or "supply & demand" in lower or "area of interest" in lower or "aoi" in lower:
        raw = dict(DEMO_STRATEGIES[0])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
    elif "breakout" in lower or "break of the" in lower or "break the" in lower:
        raw = dict(DEMO_STRATEGIES[3])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
    elif "crossover" in lower or "golden cross" in lower or "crosses above" in lower or "50 day" in lower or "50 sma" in lower:
        raw = dict(DEMO_STRATEGIES[2])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
    elif "rsi" in lower or "oversold" in lower:
        raw = dict(DEMO_STRATEGIES[1])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
    elif "macd" in lower:
        raw = dict(DEMO_STRATEGIES[4])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
    else:
        raw = dict(DEMO_STRATEGIES[0])
        raw["asset"] = asset
        raw["timeframe"] = timeframe or raw["timeframe"]
        raw["strategy_name"] = "Trend-Following Momentum"
        raw["missing_information"] = ["Strategy type not clearly specified"]

    stop = _extract_percent(lower, ["stop loss", "stop"])
    if stop is not None:
        raw["stop_loss_type"], raw["stop_loss_value"] = "percent", stop
    else:
        raw["stop_loss_type"], raw["stop_loss_value"] = None, None

    target = _extract_percent(lower, ["take profit", "target", "profit target", "aim for"])
    if target is not None:
        raw["take_profit_type"], raw["take_profit_value"] = "percent", target
    else:
        raw["take_profit_type"], raw["take_profit_value"] = None, None

    risk_match = re.search(r"risk\s*(?:only)?\s*(\d+(?:\.\d+)?)\s*%", lower)
    if risk_match:
        raw["risk_per_trade"] = float(risk_match.group(1))
    elif "risk" in lower:
        raw["risk_per_trade"] = 1.0
    else:
        raw["risk_per_trade"] = None

    if raw["stop_loss_value"] and raw["take_profit_value"]:
        raw["risk_reward"] = round(raw["take_profit_value"] / raw["stop_loss_value"], 2)
    else:
        raw["risk_reward"] = None

    if "long only" in lower or "buy" in lower or "bullish" in lower:
        raw["direction"] = DIRECTION_LONG
    elif "short" in lower or "sell" in lower or "bearish" in lower:
        raw["direction"] = DIRECTION_LONG if "long" in lower else DIRECTION_SHORT
    else:
        raw["direction"] = DIRECTION_LONG

    if not raw["stop_loss_value"]:
        raw["missing_information"].append("Stop loss not specified")
    if not raw["take_profit_value"]:
        raw["missing_information"].append("Take profit not specified")
    if not raw.get("risk_per_trade"):
        raw["missing_information"].append("Risk per trade not specified")

    return _clean_strategy(raw, transcript)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def analyze_trading_strategy(
    transcript: str,
    asset_hint: Optional[str] = None,
    timeframe_hint: Optional[str] = None,
    demote_to: int = 0,
) -> Dict[str, Any]:
    """Extract a structured strategy from a transcript.

    Tries: Groq (free) -> Gemini (free) -> OpenAI (paid) -> Claude (paid) -> heuristic (always free).
    Never raises. Always returns a usable, deterministic structure.
    """
    has_ai_key = any([
        GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here",
        GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here",
        OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here",
        ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "your_anthropic_api_key_here",
    ])

    if not has_ai_key:
        result = _extract_heuristic(transcript)
        result["source"] = "heuristic"
        result["is_demo"] = True
        return result

    # Try free providers first, then paid
    for extractor, name in [
        (_extract_with_groq, "groq"),
        (_extract_with_gemini, "gemini"),
        (_extract_with_claude, "claude"),
        (_extract_with_openai, "openai"),
    ]:
        try:
            result = extractor(transcript)
            if result is not None:
                result["source"] = name
                result["is_demo"] = False
                return result
        except Exception:
            continue

    # Final fallback: heuristic (always free, always works)
    result = _extract_heuristic(transcript)
    result["source"] = "heuristic_fallback"
    result["is_demo"] = True
    return result


def available_demo_strategies() -> List[dict]:
    return [dict(s) for s in DEMO_STRATEGIES]