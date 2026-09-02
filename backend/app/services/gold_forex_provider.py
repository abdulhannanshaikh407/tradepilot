# app/services/gold_forex_provider.py
"""Multi-source Gold & Forex data aggregator.

Combines the best FREE providers for XAUUSD + currency pairs:

1. Biquote (primary) — no key, 280+ instruments, 15k req/min, WebSocket
2. XAUS — no key, gold spot + 5yr history
3. gold-api.com — free, no rate limit on real-time, XAU/XAG/XPT/XPD
4. MTSocket — free tier, WebSocket + REST, XAUUSD + forex
5. SiftingIO — free 10k calls/mo, XAUUSD OHLCV + WebSocket
6. MintedMetal — free LBMA prices (twice-daily, CC BY 4.0)
7. goldprice.dev — free 30-day OHLC, 1k calls/mo
8. Metals.Dev — free key, real-time metals + 170 currencies

Fallback chain: Biquote → XAUS → gold-api.com → SiftingIO → simulated
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("tradepilot.marketdata.gold_forex")

# All gold/forex symbols we serve
GOLD_SYMBOLS = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}
FOREX_SYMBOLS = {
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "USD/CHF", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
}


class GoldForexProvider:
    """Multi-source aggregator for gold + forex data.

    Tries providers in order, falls back gracefully. No API keys needed
    for the primary sources (Biquote, XAUS, gold-api.com).
    """

    name = "gold_forex"

    def __init__(self) -> None:
        self._cache: Dict[str, List[dict]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._tick_cache: Dict[str, dict] = {}
        self._tick_cache_ts: Dict[str, float] = {}
        self._client = httpx.Client(timeout=12.0, headers={"User-Agent": "TradePilot/1.0"})

    # ------------------------------------------------------------------ #
    # Source 1: Biquote (primary, no key)
    # ------------------------------------------------------------------ #
    def _biquote_tick(self, symbol: str) -> Optional[dict]:
        """Fetch from Biquote REST — bid/ask/mid."""
        biquote_sym = symbol.replace("/", "")
        try:
            resp = self._client.get(
                f"https://biquote.io/api/{biquote_sym}",
                params={"allowStale": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "symbol": symbol,
                "bid": float(data.get("bid", 0)),
                "ask": float(data.get("ask", 0)),
                "mid": float(data.get("mid", 0)),
                "spread": float(data.get("spread", 0)),
                "market_state": data.get("marketState", "unknown"),
                "source": "biquote",
            }
        except Exception:
            return None

    def _biquote_ohlcv(self, symbol: str, timeframe: str) -> Optional[List[dict]]:
        """Fetch from Biquote OHLCV endpoint."""
        biquote_sym = symbol.replace("/", "")
        interval_map = {"15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
        interval = interval_map.get(timeframe, "1h")
        try:
            resp = self._client.get(
                f"https://biquote.io/api/{biquote_sym}/ohlc",
                params={"interval": interval, "limit": 500},
            )
            resp.raise_for_status()
            data = resp.json()
            bars = []
            for bar in data.get("bars", []):
                ts = bar.get("openTime") or bar.get("time", "")
                bars.append({
                    "timestamp": ts,
                    "open": float(bar.get("open", 0)),
                    "high": float(bar.get("high", 0)),
                    "low": float(bar.get("low", 0)),
                    "close": float(bar.get("close", 0)),
                    "volume": float(bar.get("volume", 0)),
                })
            return bars if bars else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Source 2: XAUS (no key, gold/silver only)
    # ------------------------------------------------------------------ #
    def _xaus_spot(self) -> Optional[dict]:
        """Fetch XAU/USD from XAUS — free, no key."""
        try:
            resp = self._client.get("https://xaus.com/api/v1/spot")
            resp.raise_for_status()
            data = resp.json()
            price = float(data.get("spot_usd_oz", 0))
            if price <= 0:
                return None
            return {
                "symbol": "XAUUSD",
                "bid": price,
                "ask": price,
                "mid": price,
                "spread": 0,
                "source": "xaus",
                "silver": float(data.get("silver_usd_oz", 0)),
                "gold_silver_ratio": float(data.get("gold_silver_ratio", 0)),
            }
        except Exception:
            return None

    def _xaus_history(self, range_str: str = "1y") -> Optional[List[dict]]:
        """Fetch XAU/USD daily history from XAUS."""
        try:
            resp = self._client.get(
                "https://xaus.com/api/v1/history",
                params={"range": range_str},
            )
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
            return bars if bars else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Source 3: gold-api.com (free, no rate limit)
    # ------------------------------------------------------------------ #
    def _goldapi_quote(self, metal: str = "XAU", currency: str = "USD") -> Optional[dict]:
        """Fetch from gold-api.com — free, no rate limit on real-time."""
        try:
            resp = self._client.get(
                f"https://gold-api.com/api/{metal}{currency}",
            )
            resp.raise_for_status()
            data = resp.json()
            # gold-api.com returns price_gram_24k or price
            price = float(data.get("price", 0) or 0)
            if price <= 0:
                # Try alternate field
                price = float(data.get("price_gram_24k", 0) or 0)
            if price <= 0:
                return None
            return {
                "symbol": f"{metal}{currency}",
                "bid": price,
                "ask": price,
                "mid": price,
                "spread": 0,
                "source": "gold-api.com",
            }
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Source 4: MintedMetal (free LBMA, twice-daily)
    # ------------------------------------------------------------------ #
    def _mintedmetal_prices(self) -> Optional[dict]:
        """Fetch LBMA prices from MintedMetal — free, CC BY 4.0."""
        try:
            resp = self._client.get("https://mintedmetal.com/api/prices.json")
            resp.raise_for_status()
            data = resp.json()
            metals = data.get("metals", {})
            result = {}
            for key, label in [("gold", "XAUUSD"), ("silver", "XAGUSD"),
                               ("platinum", "XPTUSD"), ("palladium", "XPDUSD")]:
                if key in metals and metals[key].get("price"):
                    result[label] = float(metals[key]["price"])
            return result if result else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Source 5: SiftingIO (free 10k/mo, XAUUSD OHLCV)
    # ------------------------------------------------------------------ #
    def _siftingio_quote(self, symbol: str = "XAUUSD") -> Optional[dict]:
        """Fetch from SiftingIO — free tier, no key for quote."""
        try:
            resp = self._client.get(
                f"https://api.sifting.io/v1/commodities/quote/{symbol}",
            )
            resp.raise_for_status()
            data = resp.json()
            bid = float(data.get("bid", 0))
            ask = float(data.get("ask", 0))
            if bid <= 0:
                return None
            return {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2 if ask > 0 else bid,
                "spread": ask - bid if ask > 0 else 0,
                "source": "sifting.io",
            }
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Source 6: Metals.Dev (free key, real-time + 170 currencies)
    # ------------------------------------------------------------------ #
    def _metalsdev_quote(self, api_key: str = "") -> Optional[dict]:
        """Fetch from Metals.Dev — free key, real-time."""
        if not api_key:
            return None
        try:
            resp = self._client.get(
                "https://api.metals.dev/v1/latest",
                params={"api_key": api_key, "currency": "USD", "unit": "toz"},
            )
            resp.raise_for_status()
            data = resp.json()
            metals = data.get("metals", {})
            gold = float(metals.get("gold", 0))
            if gold <= 0:
                return None
            return {
                "symbol": "XAUUSD",
                "bid": gold,
                "ask": gold,
                "mid": gold,
                "spread": 0,
                "source": "metals.dev",
                "silver": float(metals.get("silver", 0)),
                "platinum": float(metals.get("platinum", 0)),
                "palladium": float(metals.get("palladium", 0)),
            }
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_tick(self, symbol: str) -> dict:
        """Get latest tick with automatic source fallback."""
        from app.services.market_data_service import normalize_symbol
        symbol = normalize_symbol(symbol)

        # Check cache (5s)
        now = time.time()
        if symbol in self._tick_cache and now - self._tick_cache_ts.get(symbol, 0) < 5:
            return self._tick_cache[symbol]

        # Try sources in order
        tick = None

        # 1. Biquote (fastest, most instruments)
        tick = self._biquote_tick(symbol)
        if tick and tick.get("mid", 0) > 0:
            self._tick_cache[symbol] = tick
            self._tick_cache_ts[symbol] = now
            return tick

        # 2. XAUS for gold/silver
        if symbol in ("XAUUSD", "XAGUSD"):
            tick = self._xaus_spot()
            if tick:
                tick["symbol"] = symbol
                self._tick_cache[symbol] = tick
                self._tick_cache_ts[symbol] = now
                return tick

        # 3. gold-api.com for metals
        if symbol in GOLD_SYMBOLS:
            metal = symbol[:3]
            tick = self._goldapi_quote(metal)
            if tick:
                tick["symbol"] = symbol
                self._tick_cache[symbol] = tick
                self._tick_cache_ts[symbol] = now
                return tick

        # 4. MintedMetal for LBMA prices
        if symbol in GOLD_SYMBOLS:
            prices = self._mintedmetal_prices()
            if prices and symbol in prices:
                tick = {
                    "symbol": symbol,
                    "bid": prices[symbol],
                    "ask": prices[symbol],
                    "mid": prices[symbol],
                    "spread": 0,
                    "source": "mintedmetal.com",
                }
                self._tick_cache[symbol] = tick
                self._tick_cache_ts[symbol] = now
                return tick

        # 5. SiftingIO for commodities
        if symbol in GOLD_SYMBOLS:
            tick = self._siftingio_quote(symbol)
            if tick:
                self._tick_cache[symbol] = tick
                self._tick_cache_ts[symbol] = now
                return tick

        return {"symbol": symbol, "bid": 0, "ask": 0, "mid": 0, "spread": 0, "source": "none"}

    def get_ticks_batch(self, symbols: List[str]) -> Dict[str, dict]:
        """Fetch ticks for multiple symbols."""
        return {s: self.get_tick(s) for s in symbols}

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        """Get OHLCV bars with automatic source fallback."""
        from app.services.market_data_service import normalize_symbol, SimulatedMarketDataProvider
        symbol = normalize_symbol(symbol)

        key = f"{symbol}:{timeframe}"
        now = time.time()
        if key in self._cache and now - self._cache_ts.get(key, 0) < 300:
            return self._cache[key]

        # Try Biquote first
        bars = self._biquote_ohlcv(symbol, timeframe)
        if bars:
            self._cache[key] = bars
            self._cache_ts[key] = now
            return bars

        # XAUS history for gold
        if symbol == "XAUUSD":
            bars = self._xaus_history("1y")
            if bars:
                self._cache[key] = bars
                self._cache_ts[key] = now
                return bars

        # Fallback to simulated
        try:
            return SimulatedMarketDataProvider().get_ohlcv(symbol, timeframe)
        except Exception:
            return []

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        tick = self.get_tick(symbol)
        if tick.get("mid", 0) > 0:
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "open": tick["mid"],
                "high": tick["mid"],
                "low": tick["mid"],
                "close": tick["mid"],
                "volume": 0,
            }
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1] if bars else {}

    def assets(self) -> List[str]:
        return list(GOLD_SYMBOLS | FOREX_SYMBOLS)

    def close(self):
        self._client.close()


# Singleton
gold_forex_provider = GoldForexProvider()
