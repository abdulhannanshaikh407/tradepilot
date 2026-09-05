# app/services/realtime_feed.py
"""Real-time market data feed using Binance WebSocket + Biquote polling for forex/gold.

Connects to Binance's WebSocket API for live kline (candlestick) updates for crypto.
Polls Biquote API every 30 seconds for forex and gold prices.
Maintains a rolling window of OHLCV bars per symbol/timeframe in memory.

No API key required for Binance or Biquote.
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

# Forex symbols we track (canonical format)
FOREX_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "NZD/USD"]

# Commodity symbols we track (gold, silver)
COMMODITY_SYMBOLS = ["XAUUSD", "XAGUSD"]

# All non-crypto symbols that need Biquote polling
FOREX_COMMODITY_SYMBOLS = FOREX_SYMBOLS + COMMODITY_SYMBOLS

# Timeframes to subscribe to
SUBSCRIBE_TIMEFRAMES = ["15m", "1H", "4H", "1D"]

# Biquote polling interval for forex/gold
FOREX_POLL_INTERVAL = 30  # seconds


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


class ForexCommodityFeed:
    """Polls Biquote API for forex and gold prices, builds bars, and notifies listeners.

    Runs in a background thread, polling every FOREX_POLL_INTERVAL seconds.
    Fetches live ticks from Biquote and constructs OHLCV bars in the shared BarStore.
    """

    def __init__(self, bar_store: BarStore):
        self.bar_store = bar_store
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._listeners: List[Callable] = []
        self._last_prices: Dict[str, float] = {}
        # Track current bar being built per symbol/timeframe
        self._current_bars: Dict[str, dict] = {}
        self._bar_open_times: Dict[str, float] = {}

    def on_price_update(self, callback: Callable[[str, str, dict, float], None]):
        """Register a callback: callback(symbol, timeframe, bar, price)"""
        self._listeners.append(callback)

    def _notify_listeners(self, symbol: str, timeframe: str, bar: dict, price: float):
        for cb in self._listeners:
            try:
                cb(symbol, timeframe, bar, price)
            except Exception as e:
                logger.exception("Forex price listener error: %s", e)

    def _fetch_tick(self, symbol: str) -> Optional[float]:
        """Fetch a live tick from Biquote API."""
        try:
            biquote_sym = symbol.replace("/", "")
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"https://biquote.io/api/{biquote_sym}",
                    headers={"User-Agent": "TradePilot/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    price = data.get("price") or data.get("bid") or data.get("mid")
                    if price:
                        return float(price)
        except Exception as e:
            logger.debug("Biquote tick fetch failed for %s: %s", symbol, e)
        return None

    def _timeframe_seconds(self, timeframe: str) -> int:
        """Convert timeframe string to seconds."""
        units = {"m": 60, "H": 3600, "h": 3600, "D": 86400, "d": 86400}
        num = ""
        for c in timeframe:
            if c.isdigit():
                num += c
            else:
                unit = timeframe[len(num):]
                return int(num) * units.get(unit, 3600)
        return 3600

    def _update_bar(self, symbol: str, timeframe: str, price: float):
        """Update the current bar for a symbol/timeframe with a new tick."""
        now = time.time()
        bar_duration = self._timeframe_seconds(timeframe)
        # Align to bar boundaries
        bar_start = (int(now) // bar_duration) * bar_duration
        bar_ts = datetime.fromtimestamp(bar_start, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        key = f"{symbol}:{timeframe}"
        current = self._current_bars.get(key)

        if current and current["timestamp"] == bar_ts:
            # Update existing bar
            current["high"] = max(current["high"], price)
            current["low"] = min(current["low"], price)
            current["close"] = price
            current["volume"] += 0.1  # Simulated volume for ticks
        else:
            # Close previous bar and start new one
            if current:
                current["is_closed"] = True
                self.bar_store.update_from_kline(symbol, timeframe, {
                    "t": int(datetime.fromisoformat(current["timestamp"]).replace(tzinfo=timezone.utc).timestamp() * 1000),
                    "o": current["open"],
                    "h": current["high"],
                    "l": current["low"],
                    "c": current["close"],
                    "v": current["volume"],
                    "x": True,
                })

            # Start new bar
            self._current_bars[key] = {
                "timestamp": bar_ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.1,
                "is_closed": False,
            }

        # Also update the bar store with the current (open) bar
        bar = self._current_bars[key]
        self.bar_store.update_from_kline(symbol, timeframe, {
            "t": int(datetime.fromisoformat(bar["timestamp"]).replace(tzinfo=timezone.utc).timestamp() * 1000),
            "o": bar["open"],
            "h": bar["high"],
            "l": bar["low"],
            "c": bar["close"],
            "v": bar["volume"],
            "x": False,
        })

        return bar

    def _poll_loop(self):
        """Background loop that polls Biquote for forex/gold ticks."""
        logger.info("Forex/Commodity poll feed started — polling every %ds for %d symbols",
                     FOREX_POLL_INTERVAL, len(FOREX_COMMODITY_SYMBOLS))

        # Initial historical preload
        self._preload_forex_history()

        while self._running:
            for symbol in FOREX_COMMODITY_SYMBOLS:
                if not self._running:
                    break
                try:
                    price = self._fetch_tick(symbol)
                    if price and price > 0:
                        self._last_prices[symbol] = price
                        # Update bars for all timeframes
                        for tf in SUBSCRIBE_TIMEFRAMES:
                            bar = self._update_bar(symbol, tf, price)
                            self._notify_listeners(symbol, tf, bar, price)
                except Exception as e:
                    logger.debug("Error polling %s: %s", symbol, e)

            time.sleep(FOREX_POLL_INTERVAL)

    def _preload_forex_history(self):
        """Fetch historical bars for forex/gold from Biquote with retry."""
        logger.info("Preloading historical bars for forex/gold from Biquote...")
        loaded = 0
        failed = 0
        for symbol in FOREX_COMMODITY_SYMBOLS:
            for tf in SUBSCRIBE_TIMEFRAMES:
                success = False
                for attempt in range(3):
                    try:
                        biquote_sym = symbol.replace("/", "")
                        with httpx.Client(timeout=15) as client:
                            resp = client.get(
                                f"https://biquote.io/api/{biquote_sym}/ohlc",
                                params={"timeframe": tf, "limit": 300},
                                headers={"User-Agent": "TradePilot/1.0"},
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                bars_data = data.get("bars") or data.get("data") or data if isinstance(data, list) else []
                                bars = []
                                for k in bars_data:
                                    if isinstance(k, dict):
                                        bars.append({
                                            "timestamp": k.get("timestamp") or k.get("time") or k.get("t") or k.get("openTime", ""),
                                            "open": float(k.get("open", k.get("o", 0))),
                                            "high": float(k.get("high", k.get("h", 0))),
                                            "low": float(k.get("low", k.get("l", 0))),
                                            "close": float(k.get("close", k.get("c", 0))),
                                            "volume": float(k.get("volume", k.get("v", k.get("tickVolume", 0)))),
                                        })
                                if bars:
                                    self.bar_store.set_initial_bars(symbol, tf, bars)
                                    loaded += 1
                                    success = True
                                    break
                            elif resp.status_code == 429:
                                logger.warning("Biquote rate limited for %s %s, retrying...", symbol, tf)
                                time.sleep(2)
                                continue
                            else:
                                logger.warning("Biquote returned %d for %s %s", resp.status_code, symbol, tf)
                                break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning("Preload attempt %d failed for %s %s: %s", attempt + 1, symbol, tf, e)
                            time.sleep(1)
                        else:
                            logger.error("Preload FAILED for %s %s after 3 attempts: %s", symbol, tf, e)
                if not success:
                    failed += 1
        logger.info("Preloaded forex/gold bars for %d symbol/timeframe pairs (%d failed)", loaded, failed)

    def start(self):
        """Start the forex/commodity poll feed in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="forex-poll")
        self._thread.start()
        logger.info("Forex/Commodity feed started")

    def stop(self):
        """Stop the forex/commodity feed."""
        self._running = False
        logger.info("Forex/Commodity feed stopped")


# Singleton
forex_feed = ForexCommodityFeed(_bar_store)
