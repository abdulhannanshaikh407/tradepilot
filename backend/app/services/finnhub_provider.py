# app/services/finnhub_provider.py
"""Finnhub market data provider — free tier with real-time US stocks.

Free API key at finnhub.io. Provides:
- 60 calls/min on free tier
- WebSocket streaming (up to 50 symbols)
- Real-time US stock quotes
- Forex rates
- Crypto prices
- Alternative data (insider sentiment, congressional trades)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("tradepilot.marketdata.finnhub")

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Symbol mapping from our canonical names to Finnhub symbols
SYMBOL_MAP = {
    "BTC/USD": "BINANCE:BTCUSDT",
    "ETH/USD": "BINANCE:ETHUSDT",
    "EUR/USD": "OANDA:EUR_USD",
    "GBP/USD": "OANDA:GBP_USD",
    "USD/JPY": "OANDA:USD_JPY",
    "AUD/USD": "OANDA:AUD_USD",
    "USD/CAD": "OANDA:USD_CAD",
    "USD/CHF": "OANDA:USD_CHF",
    "NZD/USD": "OANDA:NZD_USD",
    "XAUUSD": "OANDA:XAU_USD",
    "XAGUSD": "OANDA:XAG_USD",
}


class FinnhubProvider:
    """Market data provider using Finnhub's free API.

    Requires a free API key from https://finnhub.io/register
    Free tier: 60 calls/min, WebSocket streaming for 50 symbols.
    """

    name = "finnhub"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._cache: Dict[str, dict] = {}
        self._cache_ts: Dict[str, float] = {}
        self._client = httpx.Client(
            base_url=FINNHUB_BASE_URL,
            timeout=10.0,
            headers={"User-Agent": "TradePilot/1.0"},
        )

    def _finnhub_symbol(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol, symbol.replace("/", ""))

    def _fetch_quote(self, finnhub_symbol: str) -> dict:
        """Fetch real-time quote from Finnhub."""
        resp = self._client.get(
            "/quote",
            params={"symbol": finnhub_symbol, "token": self.api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "current": float(data.get("c", 0)),
            "high": float(data.get("h", 0)),
            "low": float(data.get("l", 0)),
            "open": float(data.get("o", 0)),
            "previous_close": float(data.get("pc", 0)),
            "change": float(data.get("d", 0)),
            "change_percent": float(data.get("dp", 0)),
        }

    def _fetch_candles(
        self, finnhub_symbol: str, resolution: str, from_ts: int, to_ts: int
    ) -> List[dict]:
        """Fetch OHLCV candles from Finnhub (requires paid subscription on free tier)."""
        resp = self._client.get(
            "/stock/candle",
            params={
                "symbol": finnhub_symbol,
                "resolution": resolution,
                "from": from_ts,
                "to": to_ts,
                "token": self.api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("s") != "ok" or not data.get("t"):
            raise ValueError(f"Finnhub returned no candle data for {finnhub_symbol}")

        bars = []
        for i in range(len(data.get("t", []))):
            ts = datetime.fromtimestamp(data["t"][i]).strftime("%Y-%m-%dT%H:%M:%S")
            bars.append({
                "timestamp": ts,
                "open": float(data["o"][i]),
                "high": float(data["h"][i]),
                "low": float(data["l"][i]),
                "close": float(data["c"][i]),
                "volume": float(data["v"][i]),
            })
        return bars

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        from app.services.market_data_service import normalize_symbol, ASSETS
        symbol = normalize_symbol(symbol)

        if not self.api_key:
            logger.warning("Finnhub: no API key configured, falling back to simulated")
            from app.services.market_data_service import SimulatedMarketDataProvider
            return SimulatedMarketDataProvider().get_ohlcv(symbol, timeframe)

        # Free tier only covers US stocks + crypto; forex/metals fall back to Biquote
        market = ASSETS.get(symbol, {}).get("market", "")
        if market in ("forex", "commodity"):
            try:
                from app.services.biquote_provider import biquote_provider
                return biquote_provider.get_ohlcv(symbol, timeframe)
            except Exception:
                from app.services.market_data_service import SimulatedMarketDataProvider
                return SimulatedMarketDataProvider().get_ohlcv(symbol, timeframe)

        finnhub_sym = self._finnhub_symbol(symbol)

        resolution_map = {"15m": "15", "1H": "60", "4H": "D", "1D": "D"}
        resolution = resolution_map.get(timeframe, "60")

        now = int(time.time())
        from_ts = now - (365 * 24 * 3600)  # 1 year back

        try:
            bars = self._fetch_candles(finnhub_sym, resolution, from_ts, now)
        except Exception as exc:
            logger.warning("Finnhub fetch failed for %s: %s; falling back to simulated.", symbol, exc)
            from app.services.market_data_service import SimulatedMarketDataProvider
            return SimulatedMarketDataProvider().get_ohlcv(symbol, timeframe)

        return bars if bars else []

    def get_quote(self, symbol: str) -> dict:
        from app.services.market_data_service import normalize_symbol
        symbol = normalize_symbol(symbol)
        finnhub_sym = self._finnhub_symbol(symbol)

        cache_key = f"quote:{symbol}"
        now = time.time()
        if cache_key in self._cache and now - self._cache_ts.get(cache_key, 0) < 5:
            return self._cache[cache_key]

        try:
            quote = self._fetch_quote(finnhub_sym)
            result = {
                "symbol": symbol,
                "bid": quote["current"],
                "ask": quote["current"],
                "last": quote["current"],
                "volume": 0,
                "change": quote["change"],
                "change_percent": quote["change_percent"],
            }
            self._cache[cache_key] = result
            self._cache_ts[cache_key] = now
            return result
        except Exception as exc:
            logger.warning("Finnhub quote failed for %s: %s", symbol, exc)
            return {"symbol": symbol, "bid": 0, "ask": 0, "last": 0, "volume": 0}

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        quote = self.get_quote(symbol)
        if quote.get("last"):
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "open": quote.get("last", 0),
                "high": quote.get("last", 0),
                "low": quote.get("last", 0),
                "close": quote.get("last", 0),
                "volume": 0,
            }
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1] if bars else {}

    def assets(self) -> List[str]:
        from app.services.market_data_service import ASSETS
        return list(ASSETS.keys())

    def close(self) -> None:
        self._client.close()


def get_finnhub_provider() -> Optional[FinnhubProvider]:
    """Factory: returns FinnhubProvider if API key is configured."""
    import os
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        return None
    return FinnhubProvider(api_key=api_key)
