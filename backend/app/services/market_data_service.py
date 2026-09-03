# app/services/market_data_service.py
"""Market data service.

Markets are served through small `MarketDataProvider` implementations behind a
single `get_provider()` factory.

Default (and test-safe) is deterministic *simulated* OHLCV so the whole product
works without any external API. Setting `MARKET_DATA_PROVIDER=binance` swaps in
a real Binance public-market-data provider (no API key required) for crypto
pairs; non-crypto assets and any network failure fall back to the simulated
provider so the app never breaks.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol

import httpx

ASSETS = {
    "BTC/USD": {"base": 42000.0, "drift": 0.0004, "vol": 0.016, "market": "crypto", "decimals": 0},
    "ETH/USD": {"base": 2200.0, "drift": 0.0004, "vol": 0.02, "market": "crypto", "decimals": 1},
    "SOL/USD": {"base": 120.0, "drift": 0.0004, "vol": 0.024, "market": "crypto", "decimals": 2},
    "BNB/USD": {"base": 310.0, "drift": 0.0005, "vol": 0.025, "market": "crypto", "decimals": 2},
    "XRP/USD": {"base": 0.52, "drift": 0.0005, "vol": 0.028, "market": "crypto", "decimals": 4},
    "ADA/USD": {"base": 0.38, "drift": 0.0006, "vol": 0.032, "market": "crypto", "decimals": 4},
    "DOGE/USD": {"base": 0.08, "drift": 0.0006, "vol": 0.035, "market": "crypto", "decimals": 5},
    "DOT/USD": {"base": 4.5, "drift": 0.0006, "vol": 0.034, "market": "crypto", "decimals": 4},
    "LINK/USD": {"base": 13.5, "drift": 0.0006, "vol": 0.033, "market": "crypto", "decimals": 3},
    "AVAX/USD": {"base": 29.0, "drift": 0.0006, "vol": 0.036, "market": "crypto", "decimals": 3},
    "LTC/USD": {"base": 62.0, "drift": 0.0005, "vol": 0.028, "market": "crypto", "decimals": 2},
    "XLM/USD": {"base": 0.09, "drift": 0.0006, "vol": 0.032, "market": "crypto", "decimals": 5},
    "ATOM/USD": {"base": 6.5, "drift": 0.0006, "vol": 0.034, "market": "crypto", "decimals": 4},
    "UNI/USD": {"base": 7.2, "drift": 0.0006, "vol": 0.034, "market": "crypto", "decimals": 3},
    "TRX/USD": {"base": 0.11, "drift": 0.0005, "vol": 0.025, "market": "crypto", "decimals": 5},
    "NEAR/USD": {"base": 2.6, "drift": 0.0007, "vol": 0.04, "market": "crypto", "decimals": 4},
    "APT/USD": {"base": 6.0, "drift": 0.0006, "vol": 0.038, "market": "crypto", "decimals": 3},
    "FIL/USD": {"base": 3.4, "drift": 0.0006, "vol": 0.034, "market": "crypto", "decimals": 4},
    "SUI/USD": {"base": 1.3, "drift": 0.0008, "vol": 0.045, "market": "crypto", "decimals": 4},
    "NAS100": {"base": 18500.0, "drift": 0.00025, "vol": 0.008, "market": "index", "decimals": 0},
    "US500": {"base": 5100.0, "drift": 0.00025, "vol": 0.007, "market": "index", "decimals": 1},
    "GOLD": {"base": 2030.0, "drift": 0.00015, "vol": 0.006, "market": "commodity", "decimals": 1},
    "EUR/USD": {"base": 1.08, "drift": 0.00005, "vol": 0.004, "market": "forex", "decimals": 5},
    # TradingView-style tickers (XAUUSD etc.) — live prices can be pushed from
    # TradingView alerts via the existing webhook endpoint.
    "XAUUSD": {"base": 2030.0, "drift": 0.00015, "vol": 0.006, "market": "commodity", "decimals": 2},
    "XAGUSD": {"base": 23.5, "drift": 0.0002, "vol": 0.009, "market": "commodity", "decimals": 3},
    "XPTUSD": {"base": 950.0, "drift": 0.0001, "vol": 0.006, "market": "commodity", "decimals": 2},
    "XPDUSD": {"base": 1050.0, "drift": 0.0001, "vol": 0.007, "market": "commodity", "decimals": 2},
    "US30": {"base": 35000.0, "drift": 0.00025, "vol": 0.008, "market": "index", "decimals": 0},
    "SPX500": {"base": 5100.0, "drift": 0.00025, "vol": 0.007, "market": "index", "decimals": 1},
    "US100": {"base": 15000.0, "drift": 0.00025, "vol": 0.008, "market": "index", "decimals": 0},
    "USOIL": {"base": 78.5, "drift": 0.0001, "vol": 0.011, "market": "commodity", "decimals": 2},
    "UKOIL": {"base": 82.0, "drift": 0.0001, "vol": 0.01, "market": "commodity", "decimals": 2},
    "GBP/USD": {"base": 1.27, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 5},
    "USD/JPY": {"base": 151.0, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 3},
    "AUD/USD": {"base": 0.66, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 5},
    "USD/CAD": {"base": 1.36, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 5},
    "USD/CHF": {"base": 0.88, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 5},
    "NZD/USD": {"base": 0.61, "drift": 0.00005, "vol": 0.005, "market": "forex", "decimals": 5},
}

TIMEFRAMES = {
    "15m": {"bars_per_day": 96},
    "1H": {"bars_per_day": 24},
    "4H": {"bars_per_day": 6},
    "1D": {"bars_per_day": 1},
}

BARS_OF_HISTORY = 730  # ~2 years of daily bars per asset (deterministic portfolio)
MAX_BARS = 20000        # cap for small timeframes so demo backtests stay fast

# TradingView ticker -> canonical TradePilot symbol. TradingView alerts arrive
# as compact tickers like XAUUSD / BTCUSD / EURUSD; canonical symbols keep the
# "/" so the dashboard and asset lists read cleanly (XAUUSD stays XAUUSD).
TRADINGVIEW_ALIASES = {
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "XPTUSD": "XPTUSD",
    "XPDUSD": "XPDUSD",
    "US30": "US30",
    "SPX500": "SPX500",
    "US100": "US100",
    "USOIL": "USOIL",
    "UKOIL": "UKOIL",
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    "BNBUSD": "BNB/USD",
    "XRPUSD": "XRP/USD",
    "ADAUSD": "ADA/USD",
    "DOGEUSD": "DOGE/USD",
    "DOTUSD": "DOT/USD",
    "LINKUSD": "LINK/USD",
    "AVAXUSD": "AVAX/USD",
    "LTCUSD": "LTC/USD",
    "SUIUSD": "SUI/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "NZDUSD": "NZD/USD",
}
TRADINGVIEW_ALIASES = {k.upper(): v for k, v in TRADINGVIEW_ALIASES.items()}


def normalize_symbol(symbol: str) -> str:
    """Map a TradingView-style ticker (XAUUSD, BTCUSD, GOLD) to a canonical symbol."""
    symbol = (symbol or "").strip().upper()
    symbol = symbol.replace("BTCUSD", "BTC/USD")  # legacy shorthand
    for ticker, canonical in TRADINGVIEW_ALIASES.items():
        if symbol == ticker:
            return canonical
    return symbol


def tradingview_symbol(symbol: str) -> str:
    """Canonical symbol -> TradingView-friendly ticker (XAUUSD, BTCUSD, EURUSD)."""
    return normalize_symbol(symbol).replace("/", "")


LIVE_QUOTE_TTL = float(os.getenv("LIVE_QUOTE_TTL", "300"))


class LiveQuoteStore:
    """Latest known price per symbol, pushed by TradingView alert webhooks.

    A quote is 'fresh' for LIVE_QUOTE_TTL seconds after it arrives. The source
    is recorded (e.g. "tradingview") so the UI can label live prices vs
    simulated ones.
    """

    def __init__(self, ttl: float = LIVE_QUOTE_TTL) -> None:
        self._quotes: Dict[str, dict] = {}
        self._ttl = ttl

    def set(self, symbol: str, price: float, source: str = "tradingview", extra: Optional[dict] = None) -> dict:
        canonical = normalize_symbol(symbol)
        quote = {
            "symbol": canonical,
            "price": float(price),
            "source": source,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "extra": extra or {},
        }
        self._quotes[canonical] = quote
        return quote

    def get(self, symbol: str) -> Optional[dict]:
        canonical = normalize_symbol(symbol)
        quote = self._quotes.get(canonical)
        if not quote:
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(quote["updated_at"])).total_seconds()
        except (TypeError, ValueError):
            return quote
        return quote if age < self._ttl else None

    def all(self) -> Dict[str, dict]:
        return {s: q for s, q in self._quotes.items() if self.get(s) is not None}


class MarketDataProvider(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str) -> List[dict]:
        ...


class SimulatedMarketDataProvider:
    """Generates a deterministic random-walk for any supported asset/timeframe."""

    name = "simulated"

    def __init__(self) -> None:
        self._cache: Dict[str, List[dict]] = {}

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        symbol = normalize_symbol(symbol)
        if symbol not in ASSETS:
            raise ValueError(f"Unsupported symbol for simulated data: {symbol}")
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        key = f"{symbol}:{timeframe}"
        if key in self._cache:
            return self._cache[key]

        cfg = ASSETS[symbol]
        bars_per_day = TIMEFRAMES[timeframe]["bars_per_day"]
        total_bars = min(BARS_OF_HISTORY * bars_per_day, MAX_BARS)
        seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)

        price = cfg["base"] * 0.55
        bars: List[dict] = []
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        step_minutes = {"15m": 15, "1H": 60, "4H": 240, "1D": 1440}[timeframe]
        for i in range(total_bars):
            # Gentle sinusoidal seasonality on top of drift yields realistic regimes.
            wave = math.sin(i / (bars_per_day * 33)) * cfg["vol"] * 0.35
            # Mean-revert toward the base price so long histories (15m/1H have
            # tens of thousands of bars) do not compound drift into absurd prices.
            pull = -math.log(max(price, 1e-9) / cfg["base"]) * 0.01
            ret = rng.gauss(cfg["drift"] + wave, cfg["vol"]) + pull
            open_price = price
            close_price = max(open_price * (1 + ret), cfg["base"] * 0.001)
            spread = abs(ret) * rng.uniform(0.35, 0.75)
            high_price = max(open_price, close_price) * (1 + spread)
            low_price = min(open_price, close_price) * (1 - spread * 0.8)
            volume = rng.uniform(0.8, 1.4) * 1000 * abs(ret + 0.001) / max(cfg["vol"], 1e-9)

            ts = now - timedelta(minutes=step_minutes * (total_bars - 1 - i))
            decimals = cfg["decimals"]
            bars.append(
                {
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                    "open": round(open_price, decimals),
                    "high": round(high_price, decimals),
                    "low": round(low_price, decimals),
                    "close": round(close_price, decimals),
                    "volume": round(volume, 2),
                }
            )
            price = close_price

        self._cache[key] = bars
        return bars

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1]

    def assets(self) -> List[str]:
        return list(ASSETS.keys())


class DemoMarketDataProvider(SimulatedMarketDataProvider):
    """Alias kept for backwards compatibility / clearer naming at the boundary."""


# --------------------------------------------------------------------------- #
# Binance provider (real market data, no API key required)
# --------------------------------------------------------------------------- #
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
BINANCE_CACHE_TTL = float(os.getenv("BINANCE_CACHE_TTL", "120"))
BINANCE_TIMEFRAMES = {"15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}


class BinanceMarketDataProvider:
    """Serves real OHLCV for crypto pairs from Binance's public API.

    - No API keys required (public klines endpoint).
    - Non-crypto assets (indices, commodities, forex) are delegated to the
      simulated provider — Binance has no such pairs.
    - Any network error, unknown pair or timeout falls back to simulated data
      so callers never crash on transient API issues.
    - Responses are cached for ``BINANCE_CACHE_TTL`` seconds.
    """

    name = "binance"

    def __init__(self) -> None:
        self._sim = SimulatedMarketDataProvider()
        self._cache: Dict[str, List[dict]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._client = httpx.Client(
            base_url=BINANCE_BASE_URL,
            timeout=10.0,
            headers={"User-Agent": "TradePilot/1.0"},
        )

    def _binance_symbol(self, symbol: str) -> str:
        # "BTC/USD" -> "BTCUSDT" (all crypto pairs are USDT-quoted on Binance).
        return symbol.replace("/", "") + "T"

    def _fetch_klines(self, binance_symbol: str, timeframe: str) -> List[dict]:
        interval = BINANCE_TIMEFRAMES[timeframe]
        resp = self._client.get(
            "/api/v3/klines",
            params={"symbol": binance_symbol, "interval": interval, "limit": 1000},
        )
        resp.raise_for_status()
        bars: List[dict] = []
        for k in resp.json():
            ts = datetime.fromtimestamp(k[0] / 1000.0).strftime("%Y-%m-%dT%H:%M:%S")
            bars.append(
                {
                    "timestamp": ts,
                    "open": round(float(k[1]), 8),
                    "high": round(float(k[2]), 8),
                    "low": round(float(k[3]), 8),
                    "close": round(float(k[4]), 8),
                    "volume": round(float(k[5]), 4),
                }
            )
        if not bars:
            raise ValueError(f"Binance returned no klines for {binance_symbol}")
        return bars

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        symbol = normalize_symbol(symbol)
        if symbol not in ASSETS:
            raise ValueError(f"Unsupported symbol: {symbol}")
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if ASSETS[symbol]["market"] != "crypto":
            return self._sim.get_ohlcv(symbol, timeframe)

        key = f"{symbol}:{timeframe}"
        now = time.time()
        if key in self._cache and now - self._cache_ts[key] < BINANCE_CACHE_TTL:
            return self._cache[key]

        try:
            bars = self._fetch_klines(self._binance_symbol(symbol), timeframe)
        except Exception as exc:  # network errors, 4xx/429, malformed JSON...
            logging.getLogger("tradepilot.marketdata").warning(
                "Binance fetch failed for %s (%s); falling back to simulated data.",
                key,
                exc,
            )
            return self._sim.get_ohlcv(symbol, timeframe)

        self._cache[key] = bars
        self._cache_ts[key] = now
        return bars

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1]

    def assets(self) -> List[str]:
        return list(ASSETS.keys())


market_data = SimulatedMarketDataProvider()
binance_market_data = BinanceMarketDataProvider()


# --------------------------------------------------------------------------- #
# Real-time market data provider (uses Binance WebSocket bar store)
# --------------------------------------------------------------------------- #
class RealtimeMarketDataProvider:
    """Serves OHLCV bars from the real-time Binance WebSocket feed.

    Falls back to the Binance REST provider (and then simulated) when
    real-time bars are not yet available for a symbol/timeframe.
    """

    name = "realtime"

    def __init__(self):
        self._binance = BinanceMarketDataProvider()
        self._sim = SimulatedMarketDataProvider()

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        symbol = normalize_symbol(symbol)
        if symbol not in ASSETS:
            raise ValueError(f"Unsupported symbol: {symbol}")
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        # Try real-time bar store first
        try:
            from app.services.realtime_feed import feed as realtime_feed
            bars = realtime_feed.bar_store.get_bars(symbol, timeframe)
            if bars and len(bars) >= 30:
                return bars
        except Exception:
            pass

        # Fall back to Binance REST API (real data, just not WebSocket-streamed)
        if ASSETS.get(symbol, {}).get("market") == "crypto":
            try:
                return self._binance.get_ohlcv(symbol, timeframe)
            except Exception:
                pass

        # Fall back to simulated (only for non-crypto or if everything fails)
        return self._sim.get_ohlcv(symbol, timeframe)

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1]

    def assets(self) -> List[str]:
        return list(ASSETS.keys())


realtime_market_data = RealtimeMarketDataProvider()


# --------------------------------------------------------------------------- #
# Real market data provider (multi-source: Alpaca -> Binance -> yfinance)
# --------------------------------------------------------------------------- #

ALPACA_DATA_API_KEY = os.getenv("ALPACA_DATA_API_KEY", "")
ALPACA_DATA_API_SECRET = os.getenv("ALPACA_DATA_API_SECRET", "")

ALPACA_STOCK_SYMBOLS = {
    "SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "NFLX", "JPM", "V", "DIS", "PYPL", "BA", "NKE", "WMT", "JNJ",
}


class RealMarketDataProvider:
    """Multi-source real market data provider.

    Tries sources in order: Alpaca (stocks) -> Binance (crypto) -> yfinance (fallback).
    Non-crypto assets fall back to simulated data if no real source is available.
    """

    name = "real"

    def __init__(self) -> None:
        self._sim = SimulatedMarketDataProvider()
        self._binance = BinanceMarketDataProvider()
        self._cache: Dict[str, List[dict]] = {}
        self._cache_ts: Dict[str, float] = {}

    def get_ohlcv(self, symbol: str, timeframe: str = "4H") -> List[dict]:
        symbol = normalize_symbol(symbol)
        if symbol not in ASSETS:
            raise ValueError(f"Unsupported symbol: {symbol}")
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        key = f"{symbol}:{timeframe}"
        now = time.time()
        if key in self._cache and now - self._cache_ts[key] < 300:
            return self._cache[key]

        bars = None

        # Try yfinance for stocks
        if symbol in ALPACA_STOCK_SYMBOLS or ASSETS.get(symbol, {}).get("market") == "index":
            bars = self._fetch_yfinance(symbol, timeframe)

        # Try Binance for crypto
        if bars is None and ASSETS.get(symbol, {}).get("market") == "crypto":
            try:
                bars = self._binance.get_ohlcv(symbol, timeframe)
            except Exception:
                pass

        # Fallback to simulated
        if bars is None:
            bars = self._sim.get_ohlcv(symbol, timeframe)

        self._cache[key] = bars
        self._cache_ts[key] = now
        return bars

    def _fetch_yfinance(self, symbol: str, timeframe: str) -> Optional[List[dict]]:
        """Fetch from yfinance (slow fallback)."""
        try:
            import yfinance as yf
        except ImportError:
            return None

        yf_symbol = symbol.replace("/", "-").replace("USD", "-USD") if "/" in symbol else symbol
        tf_map = {"15m": "15m", "1H": "1h", "4H": "1h", "1D": "1d"}
        yf_interval = tf_map.get(timeframe, "1h")

        try:
            data = yf.download(yf_symbol, period="2y", interval=yf_interval, progress=False)
            if data.empty:
                return None

            bars = []
            for idx, row in data.iterrows():
                bars.append({
                    "timestamp": idx.strftime("%Y-%m-%dT%H:%M:%S"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                })
            return bars if bars else None
        except Exception:
            return None

    def latest_quote(self, symbol: str, timeframe: str = "4H") -> dict:
        bars = self.get_ohlcv(symbol, timeframe)
        return bars[-1]

    def assets(self) -> List[str]:
        return list(ASSETS.keys())


real_market_data = RealMarketDataProvider()

MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "realtime").strip().lower()


def get_provider() -> MarketDataProvider:
    """Return the active market-data provider.

    Default is ``realtime`` — uses Binance WebSocket for live crypto data,
    falls back to Binance REST, then simulated.

    ``MARKET_DATA_PROVIDER=binance`` uses Binance REST only (no WebSocket);
    ``MARKET_DATA_PROVIDER=real`` uses multi-source real data (yfinance fallback);
    ``MARKET_DATA_PROVIDER=biquote`` uses Biquote free API for forex/metals/crypto;
    ``MARKET_DATA_PROVIDER=finnhub`` uses Finnhub free API (needs FINNHUB_API_KEY);
    ``MARKET_DATA_PROVIDER=gold_forex`` uses multi-source gold+forex aggregator;
    ``MARKET_DATA_PROVIDER=mtsocket`` uses MTSocket free API (XAUUSD + forex);
    ``MARKET_DATA_PROVIDER=simulated`` uses deterministic fake data (demo only).
    """
    if MARKET_DATA_PROVIDER == "realtime":
        return realtime_market_data
    if MARKET_DATA_PROVIDER == "binance":
        return binance_market_data
    if MARKET_DATA_PROVIDER == "real":
        return real_market_data
    if MARKET_DATA_PROVIDER == "biquote":
        try:
            from app.services.biquote_provider import biquote_provider
            return biquote_provider
        except Exception:
            return realtime_market_data
    if MARKET_DATA_PROVIDER == "finnhub":
        try:
            from app.services.finnhub_provider import get_finnhub_provider
            p = get_finnhub_provider()
            if p:
                return p
        except Exception:
            pass
        return realtime_market_data
    if MARKET_DATA_PROVIDER == "gold_forex":
        try:
            from app.services.gold_forex_provider import gold_forex_provider
            return gold_forex_provider
        except Exception:
            return realtime_market_data
    if MARKET_DATA_PROVIDER == "mtsocket":
        try:
            from app.services.mtsocket_provider import mtsocket_provider
            return mtsocket_provider
        except Exception:
            return realtime_market_data
    if MARKET_DATA_PROVIDER == "simulated":
        return market_data
    return realtime_market_data


live_quotes = LiveQuoteStore()


def get_live_quote(symbol: str) -> Optional[dict]:
    """Fresh TradingView-sourced price for a symbol, or None.

    Purely an enhancement: when TradingView alert webhooks push prices in, the
    answer reflects reality; otherwise callers fall back (they always should).
    """
    return live_quotes.get(symbol)


def apply_live_quote(bars: List[dict], symbol: str, price: Optional[float] = None) -> List[dict]:
    """Overwrite the last bar's close (and high/low) with a fresh live price.

    Used to stamp the most recent OHLCV bar with the latest TradingView quote so
    charts end at the true market price. Returns a new list; non-mutating.
    """
    if not bars:
        return bars
    price = price if price is not None else (live_quotes.get(symbol) or {}).get("price")
    if price is None:
        return bars
    out = [dict(b) for b in bars]
    last = dict(out[-1])
    last["close"] = round(float(price), 8)
    last["high"] = max(last["high"], last["close"])
    last["low"] = min(last["low"], last["close"])
    last["live"] = True
    last["source"] = (live_quotes.get(symbol) or {}).get("source", "tradingview")
    out[-1] = last
    return out