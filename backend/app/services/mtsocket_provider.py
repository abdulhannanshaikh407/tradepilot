# app/services/mtsocket_provider.py
"""MTSocket provider — free tier for XAUUSD + forex via WebSocket/REST.

Free to start, no credit card. Provides live bid/ask/spread for XAUUSD
and major currency pairs. REST + WebSocket with <50ms latency.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("tradepilot.marketdata.mtsocket")

MTSOCKET_REST_URL = "https://api.mtsocket.com/v1"

# Symbol mapping
SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "USD/JPY": "USDJPY",
    "AUD/USD": "AUDUSD",
    "USD/CAD": "USDCAD",
    "USD/CHF": "USDCHF",
    "NZD/USD": "NZDUSD",
    "EUR/GBP": "EURGBP",
    "EUR/JPY": "EURJPY",
    "GBP/JPY": "GBPJPY",
    "BTC/USD": "BTCUSD",
    "ETH/USD": "ETHUSD",
}


class MTSocketProvider:
    """Market data from MTSocket — free tier, XAUUSD + forex.

    Free plan: live bid/ask, REST + WebSocket, <50ms latency.
    """
    name = "mtsocket"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._cache: Dict[str, dict] = {}
        self._cache_ts: Dict[str, float] = {}
        self._client = httpx.Client(
            base_url=MTSOCKET_REST_URL,
            timeout=10.0,
            headers={"User-Agent": "TradePilot/1.0"},
        )

    def _mt_symbol(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol, symbol.replace("/", ""))

    def _fetch_price(self, mt_symbol: str) -> Optional[dict]:
        """Fetch live price from MTSocket."""
        try:
            headers = {"User-Agent": "TradePilot/1.0"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            resp = self._client.get(
                f"/quote/{mt_symbol}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            bid = float(data.get("bid", 0))
            ask = float(data.get("ask", 0))
            if bid <= 0:
                return None
            return {
                "bid": bid,
                "ask": ask,
                "spread": float(data.get("spread", ask - bid)),
                "volume": int(data.get("volume", 0)),
                "timeStamp": data.get("timeStamp", ""),
            }
        except Exception as exc:
            logger.debug("MTSocket fetch failed for %s: %s", mt_symbol, exc)
            return None

    def get_tick(self, symbol: str) -> Optional[dict]:
        from app.services.market_data_service import normalize_symbol
        symbol = normalize_symbol(symbol)

        now = time.time()
        cache_key = f"tick:{symbol}"
        if cache_key in self._cache and now - self._cache_ts.get(cache_key, 0) < 5:
            return self._cache[cache_key]

        mt_sym = self._mt_symbol(symbol)
        data = self._fetch_price(mt_sym)
        if not data:
            return None

        result = {
            "symbol": symbol,
            "bid": data["bid"],
            "ask": data["ask"],
            "mid": (data["bid"] + data["ask"]) / 2,
            "spread": data["spread"],
            "source": "mtsocket",
        }
        self._cache[cache_key] = result
        self._cache_ts[cache_key] = now
        return result

    def get_ticks_batch(self, symbols: List[str]) -> Dict[str, dict]:
        return {s: self.get_tick(s) or {} for s in symbols}

    def get_quote(self, symbol: str) -> dict:
        tick = self.get_tick(symbol)
        if tick:
            return {
                "symbol": symbol,
                "bid": tick["bid"],
                "ask": tick["ask"],
                "last": tick["mid"],
                "volume": 0,
            }
        return {"symbol": symbol, "bid": 0, "ask": 0, "last": 0, "volume": 0}

    def close(self):
        self._client.close()


mtsocket_provider = MTSocketProvider()
