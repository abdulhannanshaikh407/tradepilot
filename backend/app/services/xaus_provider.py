# app/services/xaus_provider.py
"""XAUS gold price provider — free, no API key required.

Provides live XAU/USD spot price, historical data, and gold-silver ratio.
Source: https://xaus.com/api
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("tradepilot.marketdata.xaus")

XAUS_BASE_URL = "https://xaus.com/api/v1"


class XausProvider:
    """Free gold price data from XAUS.

    No API key needed. Endpoints:
    - /spot — live XAU/USD spot
    - /history — daily history up to 5 years
    - /intraday — sampled every 2 min, retained 14 days
    """

    name = "xaus"

    def __init__(self) -> None:
        self._cache: Dict[str, dict] = {}
        self._cache_ts: Dict[str, float] = {}
        self._client = httpx.Client(
            base_url=XAUS_BASE_URL,
            timeout=15.0,
            headers={"User-Agent": "TradePilot/1.0"},
        )

    def get_spot(self, currency: str = "USD") -> dict:
        """Get live XAU spot price."""
        try:
            resp = self._client.get("/spot", params={"currency": currency})
            resp.raise_for_status()
            data = resp.json()
            return {
                "price": float(data.get("spot_usd_oz", 0)),
                "currency": currency,
                "per_gram": float(data.get("per_gram_usd", 0)),
                "silver": float(data.get("silver_usd_oz", 0)),
                "gold_silver_ratio": float(data.get("gold_silver_ratio", 0)),
                "updated_at": data.get("updated_at", ""),
            }
        except Exception as exc:
            logger.warning("XAUS spot fetch failed: %s", exc)
            return {}

    def get_history(self, range_str: str = "1y") -> List[dict]:
        """Get historical daily XAU/USD candles."""
        cache_key = f"history:{range_str}"
        now = time.time()
        if cache_key in self._cache and now - self._cache_ts.get(cache_key, 0) < 3600:
            return self._cache[cache_key]

        try:
            resp = self._client.get("/history", params={"range": range_str})
            resp.raise_for_status()
            data = resp.json()

            bars = []
            for point in data.get("history", data.get("bars", [])):
                ts = point.get("date", point.get("time", ""))
                bars.append({
                    "timestamp": ts,
                    "open": float(point.get("open", point.get("price", 0))),
                    "high": float(point.get("high", point.get("price", 0))),
                    "low": float(point.get("low", point.get("price", 0))),
                    "close": float(point.get("close", point.get("price", 0))),
                    "volume": float(point.get("volume", 0)),
                })

            self._cache[cache_key] = bars
            self._cache_ts[cache_key] = now
            return bars
        except Exception as exc:
            logger.warning("XAUS history fetch failed: %s", exc)
            return []

    def get_intraday(self, hours: int = 24) -> List[dict]:
        """Get intraday XAU price series (sampled every 2 min)."""
        try:
            resp = self._client.get("/intraday", params={"symbol": "xau", "hours": hours})
            resp.raise_for_status()
            data = resp.json()

            bars = []
            for point in data.get("series", []):
                ts = point.get("t", "")
                price = float(point.get("p", 0))
                bars.append({
                    "timestamp": ts,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0,
                })
            return bars
        except Exception as exc:
            logger.warning("XAUS intraday fetch failed: %s", exc)
            return []

    def get_quote(self, symbol: str = "XAUUSD") -> dict:
        """Get current XAU/USD quote."""
        cache_key = f"quote:{symbol}"
        now = time.time()
        if cache_key in self._cache and now - self._cache_ts.get(cache_key, 0) < 30:
            return self._cache[cache_key]

        spot = self.get_spot()
        result = {
            "symbol": symbol,
            "bid": spot.get("price", 0),
            "ask": spot.get("price", 0),
            "last": spot.get("price", 0),
            "volume": 0,
            "silver": spot.get("silver", 0),
            "gold_silver_ratio": spot.get("gold_silver_ratio", 0),
        }

        self._cache[cache_key] = result
        self._cache_ts[cache_key] = now
        return result

    def close(self) -> None:
        self._client.close()


# Singleton
xaus_provider = XausProvider()
