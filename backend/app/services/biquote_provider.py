# app/services/biquote_provider.py
"""Biquote market data provider — free real-time forex, metals, crypto.

No API key required. Provides live tick streaming via SignalR WebSocket
and OHLCV candles via REST. Covers 280+ instruments including XAUUSD.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("tradepilot.marketdata.biquote")

BIQUOTE_BASE_URL = "https://biquote.io"
BIQUOTE_REST_URL = f"{BIQUOTE_BASE_URL}/api"
BIQUOTE_HUB_URL = f"{BIQUOTE_BASE_URL}/hubs/tick"

# Mapping from our canonical symbols to Biquote symbols
SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "XPTUSD": "XPTUSD",
    "XPDUSD": "XPDUSD",
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "USD/JPY": "USDJPY",
    "AUD/USD": "AUDUSD",
    "USD/CAD": "USDCAD",
    "USD/CHF": "USDCHF",
    "NZD/USD": "NZDUSD",
    "BTC/USD": "BTCUSD",
    "ETH/USD": "ETHUSD",
    "USOIL": "USOIL",
    "UKOIL": "UKOIL",
    "NAS100": "NAS100",
    "US500": "US500",
    "US30": "US30",
    "SPX500": "US500",
}

# Biquote OHLCV interval mapping
TIMEFRAME_MAP = {
    "15m": "15m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
}


class BiquoteProvider:
    """Market data provider using Biquote's free API.

    - No API key needed
    - REST for OHLCV candles: /api/{symbol}/ohlc
    - REST for latest tick: /api/{symbol} or /api/latest
    - WebSocket (SignalR) for real-time streaming: /hubs/tick
    """

    name = "biquote"

    def __init__(self) -> None:
        self._cache: Dict[str, List[dict]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._tick_cache: Dict[str, dict] = {}
        self._client = httpx.Client(
            base_url=BIQUOTE_BASE_URL,
            timeout=15.0,
            headers={"User-Agent": "TradePilot/1.0"},
        )

    def _biquote_symbol(self, symbol: str) -> str:
        """Convert canonical symbol to Biquote symbol."""
        return SYMBOL_MAP.get(symbol, symbol.replace("/", ""))

    def _fetch_ohlcv(self, biquote_symbol: str, timeframe: str) -> List[dict]:
        """Fetch OHLCV candles from Biquote REST API."""
        interval = TIMEFRAME_MAP.get(timeframe, "1h")
        resp = self._client.get(
            f"/api/{biquote_symbol}/ohlc",
            params={"interval": interval, "limit": 500},
        )
        resp.raise_for_status()
        data = resp.json()

        bars = []
        for bar in data.get("bars", []):
            ts = bar.get("openTime") or bar.get("time") or bar.get("timestamp", "")
            if isinstance(ts, str) and "T" not in ts:
                ts = ts + "T00:00:00"
            bars.append({
                "timestamp": ts,
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": float(bar.get("volume", 0)),
            })

        if not bars:
            raise ValueError(f"Biquote returned no bars for {biquote_symbol}")
        return bars

    def _fetch_tick(self, biquote_symbol: str) -> dict:
        """Fetch latest tick from Biquote REST API."""
        resp = self._client.get(
            f"/api/{biquote_symbol}",
            params={"allowStale": "true"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": biquote_symbol,
            "bid": float(data.get("bid", 0)),
            "ask": float(data.get("ask", 0)),
            "mid": float(data.get("mid", 0)),
            "spread": float(data.get("spread", 0)),
            "market_state": data.get("marketState", "unknown"),
            "day_diff_percent": float(data.get("dayDiffPercent", 0)),
        }

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        """Get OHLCV bars for a symbol and timeframe."""
        from app.services.market_data_service import normalize_symbol
        symbol = normalize_symbol(symbol)

        key = f"{symbol}:{timeframe}"
        now = time.time()

        # Check cache (5 min TTL for OHLCV)
        if key in self._cache and now - self._cache_ts.get(key, 0) < 300:
            return self._cache[key]

        biquote_sym = self._biquote_symbol(symbol)
        try:
            bars = self._fetch_ohlcv(biquote_sym, timeframe)
        except Exception as exc:
            logger.warning(
                "Biquote OHLCV fetch failed for %s: %s; falling back to simulated.",
                key, exc,
            )
            from app.services.market_data_service import SimulatedMarketDataProvider
            return SimulatedMarketDataProvider().get_ohlcv(symbol, timeframe)

        self._cache[key] = bars
        self._cache_ts[key] = now
        return bars

    def get_tick(self, symbol: str) -> dict:
        """Get latest tick for a symbol."""
        from app.services.market_data_service import normalize_symbol
        symbol = normalize_symbol(symbol)
        biquote_sym = self._biquote_symbol(symbol)

        try:
            return self._fetch_tick(biquote_sym)
        except Exception as exc:
            logger.warning("Biquote tick fetch failed for %s: %s", symbol, exc)
            return {}

    def get_ticks_batch(self, symbols: List[str]) -> Dict[str, dict]:
        """Fetch latest ticks for multiple symbols in one request."""
        from app.services.market_data_service import normalize_symbol
        biquote_syms = [self._biquote_symbol(normalize_symbol(s)) for s in symbols]

        try:
            params = [("symbols", s) for s in biquote_syms]
            resp = self._client.get("/api/latest", params=params)
            resp.raise_for_status()
            data = resp.json()

            results = {}
            for sym, tick in data.items():
                results[sym] = {
                    "symbol": sym,
                    "bid": float(tick.get("bid", 0)),
                    "ask": float(tick.get("ask", 0)),
                    "mid": float(tick.get("mid", 0)),
                    "spread": float(tick.get("spread", 0)),
                    "market_state": tick.get("marketState", "unknown"),
                    "day_diff_percent": float(tick.get("dayDiffPercent", 0)),
                }
            return results
        except Exception as exc:
            logger.warning("Biquote batch tick fetch failed: %s", exc)
            return {}

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        """Get latest quote (OHLCV bar)."""
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1] if bars else {}

    def assets(self) -> List[str]:
        """Return list of supported symbols."""
        from app.services.market_data_service import ASSETS
        return [s for s in ASSETS if s in SYMBOL_MAP]

    def close(self) -> None:
        self._client.close()


# Singleton
biquote_provider = BiquoteProvider()
