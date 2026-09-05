# app/services/youtube_service.py
"""YouTube URL handling: validation, video ID extraction, titles."""
from __future__ import annotations

import re
from typing import Optional

YOUTUBE_PATTERNS = [
    re.compile(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]

SAMPLE_TRANSCRIPTS = {
    "SETANDFORGET": (
        "This is the only trading strategy you need to be profitable. It's a set and forget swing "
        "trading approach based on supply and demand zones. First, identify the higher timeframe trend "
        "on the daily and weekly charts. Only trade in the direction of that trend. Then mark your "
        "areas of interest which are fresh untested supply and demand zones. Look for at least two "
        "confluences at each zone like a swing level plus a fair value gap. Wait for price to sweep "
        "liquidity into your zone and then look for a lower timeframe structure shift as your entry "
        "trigger. Place a limit order at the proximal edge of the zone with your stop loss just "
        "beyond the distal edge. Your take profit should be at the next opposing zone giving you at "
        "least a one to four risk to reward ratio. Risk only one percent per trade. Take your first "
        "partial profit at one R to one and a half R and move your stop to breakeven. Let the runner "
        "continue to the next higher timeframe target. Set your orders and forget about them. Do not "
        "adjust your trades once they are placed. This is a set and forget approach."
    ),
    "RSI": (
        "In this video I'm going to break down my RSI momentum reversal strategy on Bitcoin. "
        "We trade the 4 hour chart. This strategy is long only when the market makes a strong "
        "higher low. First, we wait for the RSI 14 to drop below 30, which signals an oversold "
        "condition. We do not enter immediately. We wait for the RSI to recover and cross back "
        "above 30. As a confirmation, price must stay above the 200 EMA on the same 4 hour "
        "timeframe. Our stop loss is set at 2% below our entry. Our take profit target is 4% "
        "meaning we get a 1 to 2 risk reward. We risk 1% of our account per trade. "
        "If price closes below the 200 EMA we exit early and take the loss."
    ),
    "MA": (
        "Today I'll show you a simple moving average crossover system for Ethereum on the daily "
        "chart. We buy when the 50 day SMA crosses above the 200 day SMA, the so called golden "
        "cross. This strategy is long only. We place our stop loss 3% below entry and aim for a "
        "6% take profit, giving us a 1 to 2 risk to reward ratio. We risk one and a half percent "
        "of the account. For confirmation we use the MACD on the default settings and require the "
        "MACD line to be above the signal line. We exit when the 50 SMA crosses back below the "
        "200 SMA."
    ),
    "BREAKOUT": (
        "This is my momentum breakout strategy for the NASDAQ index on the hourly chart. "
        "We buy the break of the last 20 periods high, and we go short the break of the last "
        "20 periods low. Entry happens when the current bar closes above the previous twenty "
        "bar high. Our stop is a 1% fixed stop and the target is 2%, one to two risk reward. "
        "We confirm with the ADX rising and price trading above the VWAP for longs. "
        "We risk 1% per trade."
    ),
}


def extract_video_id(url: str) -> Optional[str]:
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(url.strip())
        if match:
            return match.group(1)
    return None


def is_valid_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    if "youtube.com" in url or "youtu.be" in url:
        return extract_video_id(url) is not None
    return False


def fetch_video_metadata(video_id: str) -> dict:
    """Best-effort metadata fetch. Never raises — returns empty dict on failure."""
    try:
        import urllib.request

        url = f"https://www.youtube.com/watch?v={video_id}"
        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; TradePilot/1.0)"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
        title = ""
        match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
        if match:
            title = match.group(1).strip().replace(" - YouTube", "")
        return {"video_id": video_id, "video_url": url, "video_title": title or "YouTube video"}
    except Exception:
        return {"video_id": video_id, "video_url": f"https://www.youtube.com/watch?v={video_id}", "video_title": "YouTube video"}


def demo_transcript_for(video_id: str, hint: Optional[str] = None) -> dict:
    """Return a simulated transcript for offline/demo use.

    Picks a deterministic sample based on the video id hash so the demo feels
    consistent. Returns {"transcript": ..., "is_demo": True}.
    """
    text = None
    if hint:
        lower = hint.lower()
        for key, value in SAMPLE_TRANSCRIPTS.items():
            if key.lower() in lower:
                text = value
                break
    if not text:
        import hashlib

        seed = int(hashlib.sha256(video_id.encode()).hexdigest()[:2], 16) % len(SAMPLE_TRANSCRIPTS)
        text = list(SAMPLE_TRANSCRIPTS.values())[seed]
    return {"transcript": text, "is_demo": True}