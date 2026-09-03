# app/services/realtime_feed.py
"""Real-time market data feed using Binance WebSocket.

Connects to Binance's WebSocket API for live kline (candlestick) updates.
Maintains a rolling window of OHLCV bars per symbol/timeframe in memory.

No API key required — uses Binance's public WebSocket streams.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import httpx
import websocket

logger = logging.getLogger("tradepilot.realtime")

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_REST_URL = "https://api.binance.com"

# Mapping from our timeframe format to Binance kline interval
TIMEFRAME_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1H": "1h", "2H": "2h", "4H": "4h", "6H": "6h", "8H": "8h", "12H": "12h",
    "1D": "1d", "3D": "3d", "1W": "1w", "1M": "1M",
}

# How many historical bars to keep per symbol/timeframe (enough for indicator calc)
MAX_BARS = 500

# Crypto symbols we track (Binance format without /USD)
CRYPTO_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "AVAXUSDT",
    "LTCUSDT", "XLMUSDT", "ATOMUSDT", "UNIUSDT", "TRXUSDT",
    "NEARUSDT", "APTUSDT", "FILUSDT", "SUIUSDT",
]

# Timeframes to subscribe to
SUBSCRIBE_TIMEFRAMES = ["15m", "1H", "4H", "1D"]


def _binance_symbol(symbol: str) -> str:
    """Convert our symbol format to Binance format. BTC/USD -> BTCUSDT"""
    return symbol.replace("/", "").replace("USD", "USDT")


def _our_symbol(binance_symbol: str) -> str:
    """Convert Binance format to our format. BTCUSDT -> BTC/USD"""
    s = binance_symbol.replace("USDT", "/USD")
    return s


def _timeframe_ms(timeframe: str) -> int:
    """Convert timeframe string to milliseconds."""
    units = {"m": 60_000, "H": 3_600_000, "h": 3_600_000, "D": 86_400_000, "d": 86_400_000, "W": 604_800_000}
    num = ""
    for c in timeframe:
        if c.isdigit():
            num += c
        else:
            unit = timeframe[len(num):]
            return int(num) * units.get(unit, 3_600_000)
    return 3_600_000


class BarStore:
    """Thread-safe in-memory store of OHLCV bars per symbol/timeframe."""

    def __init__(self):
        self._bars: Dict[str, List[dict]] = {}
        self._lock = threading.Lock()

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"

    def update_from_kline(self, symbol: str, timeframe: str, kline: dict) -> Optional[dict]:
        """Update bars from a Binance kline event. Returns the bar dict."""
        key = self._key(symbol, timeframe)
        bar = {
            "timestamp": datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "open": float(kline["o"]),
            "high": float(kline["h"]),
            "low": float(kline["l"]),
            "close": float(kline["c"]),
            "volume": float(kline["v"]),
            "is_closed": kline.get("x", False),
        }
        with self._lock:
            if key not in self._bars:
                self._bars[key] = []
            bars = self._bars[key]
            if bars and bars[-1]["timestamp"] == bar["timestamp"]:
                bars[-1] = bar
            else:
                bars.append(bar)
                if len(bars) > MAX_BARS:
                    self._bars[key] = bars[-MAX_BARS:]
            return bar

    def set_initial_bars(self, symbol: str, timeframe: str, bars: List[dict]):
        """Set initial historical bars from REST API."""
        key = self._key(symbol, timeframe)
        with self._lock:
            self._bars[key] = bars[-MAX_BARS:]

    def get_bars(self, symbol: str, timeframe: str) -> List[dict]:
        """Get a copy of bars for a symbol/timeframe."""
        key = self._key(symbol, timeframe)
        with self._lock:
            return list(self._bars.get(key, []))

    def get_last_price(self, symbol: str, timeframe: str = "1m") -> Optional[float]:
        """Get the latest close price."""
        bars = self.get_bars(symbol, timeframe)
        if bars:
            return bars[-1]["close"]
        return None

    def get_all_symbols(self) -> List[str]:
        """Get all symbols that have data."""
        with self._lock:
            symbols = set()
            for key in self._bars:
                symbol = key.split(":")[0]
                symbols.add(symbol)
            return list(symbols)


class RealtimeFeed:
    """Real-time price feed from Binance WebSocket.

    Subscribes to kline streams for all crypto pairs across multiple timeframes.
    Maintains a BarStore with the latest bars and notifies listeners on updates.
    """

    def __init__(self, bar_store: BarStore):
        self.bar_store = bar_store
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._listeners: List[Callable] = []
        self._reconnect_delay = 1
        self._last_prices: Dict[str, float] = {}

    def on_price_update(self, callback: Callable[[str, str, dict, float], None]):
        """Register a callback: callback(symbol, timeframe, bar, price)"""
        self._listeners.append(callback)

    def _notify_listeners(self, symbol: str, timeframe: str, bar: dict, price: float):
        for cb in self._listeners:
            try:
                cb(symbol, timeframe, bar, price)
            except Exception as e:
                logger.exception("Price listener error: %s", e)

    def _build_stream_url(self) -> str:
        """Build combined kline stream URL for all symbols/timeframes."""
        streams = []
        for sym in CRYPTO_SYMBOLS:
            for tf in SUBSCRIBE_TIMEFRAMES:
                binance_tf = TIMEFRAME_MAP.get(tf, tf.lower())
                streams.append(f"{sym.lower()}@kline_{binance_tf}")
        if len(streams) == 1:
            return f"{BINANCE_WS_URL}/{streams[0]}"
        combined = "/".join(streams)
        return f"{BINANCE_WS_URL}/stream?streams={combined}"

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data:
                event = data["data"]
            else:
                event = data

            if event.get("e") != "kline":
                return

            kline = event["k"]
            binance_symbol = kline["s"]
            symbol = _our_symbol(binance_symbol)

            # Determine timeframe from stream
            interval = kline["i"]
            tf_reverse = {v: k for k, v in TIMEFRAME_MAP.items()}
            timeframe = tf_reverse.get(interval, interval)

            bar = self.bar_store.update_from_kline(symbol, timeframe, kline)
            if bar:
                price = bar["close"]
                self._last_prices[f"{symbol}:{timeframe}"] = price
                self._notify_listeners(symbol, timeframe, bar, price)

        except Exception as e:
            logger.exception("Error processing WS message: %s", e)

    def _on_error(self, ws, error):
        logger.error("Binance WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg):
        logger.warning("Binance WebSocket closed (%s: %s)", close_status_code, close_msg)
        if self._running:
            self._schedule_reconnect()

    def _on_open(self, ws):
        logger.info("Binance WebSocket connected — streaming %d symbol/timeframe pairs",
                     len(CRYPTO_SYMBOLS) * len(SUBSCRIBE_TIMEFRAMES))
        self._reconnect_delay = 1

    def _schedule_reconnect(self):
        if not self._running:
            return
        logger.info("Reconnecting in %ds...", self._reconnect_delay)
        time.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, 60)
        self._connect()

    def _connect(self):
        url = self._build_stream_url()
        self._ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self._ws.run_forever(ping_interval=30, ping_timeout=10)

    def fetch_historical_bars(self, symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
        """Fetch historical klines from Binance REST API."""
        binance_sym = _binance_symbol(symbol)
        interval = TIMEFRAME_MAP.get(timeframe, timeframe.lower())

        try:
            resp = httpx.get(
                f"{BINANCE_REST_URL}/api/v3/klines",
                params={"symbol": binance_sym, "interval": interval, "limit": limit},
                timeout=15.0,
                headers={"User-Agent": "TradePilot/1.0"},
            )
            resp.raise_for_status()
            bars = []
            for k in resp.json():
                bars.append({
                    "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return bars
        except Exception as e:
            logger.warning("Failed to fetch historical bars for %s %s: %s", symbol, timeframe, e)
            return []

    def preload_history(self):
        """Fetch historical bars for all tracked symbols/timeframes."""
        logger.info("Preloading historical bars from Binance REST API...")
        loaded = 0
        for sym in CRYPTO_SYMBOLS:
            our_sym = _our_symbol(sym)
            for tf in SUBSCRIBE_TIMEFRAMES:
                bars = self.fetch_historical_bars(our_sym, tf, limit=300)
                if bars:
                    self.bar_store.set_initial_bars(our_sym, tf, bars)
                    loaded += 1
        logger.info("Preloaded historical bars for %d symbol/timeframe pairs", loaded)

    def start(self):
        """Start the real-time feed in a background thread."""
        if self._running:
            return
        self._running = True
        self.preload_history()
        self._thread = threading.Thread(target=self._connect, daemon=True, name="binance-ws")
        self._thread.start()
        logger.info("Real-time feed started")

    def stop(self):
        """Stop the real-time feed."""
        self._running = False
        if self._ws:
            self._ws.close()
        logger.info("Real-time feed stopped")

    def is_connected(self) -> bool:
        return self._running and self._ws is not None

    def get_last_prices(self) -> Dict[str, float]:
        return dict(self._last_prices)


# Singleton
_bar_store = BarStore()
feed = RealtimeFeed(_bar_store)
