# app/services/broker.py
"""Order execution adapters: paper (default) and real Binance spot.

Papers fills are simulated at the latest provider close with a small slippage
so demo mode works with zero credentials. The Binance adapter signs real order
requests and is only reachable when:
  1. BINANCE_API_KEY / BINANCE_API_SECRET are configured server-side, and
  2. the user has explicitly armed the strategy for live trading.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional, Protocol

import httpx

from app.core.config import BINANCE_API_KEY, BINANCE_API_SECRET
from app.services.market_data_service import get_provider, normalize_symbol

BINANCE_SPOT_ENDPOINT = os.getenv("BINANCE_API_URL", "https://api.binance.com")


class Fill:
    def __init__(self, symbol: str, side: str, price: float, base_qty: float, quote: float):
        self.symbol = symbol
        self.side = side
        self.price = price
        self.base_qty = base_qty
        self.quote = quote

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "base_qty": self.base_qty,
            "quote": self.quote,
        }


class Broker(Protocol):
    name: str
    requires_keys: bool

    def buy_quote(self, symbol: str, quote_cash: float) -> Fill: ...
    def sell_base(self, symbol: str, base_qty: float) -> Fill: ...
    def market_price(self, symbol: str) -> float: ...


def _binance_symbol(symbol: str) -> str:
    """Canonical 'BTC/USD' -> 'BTCUSDT' (all crypto pairs are USDT-quoted)."""
    return symbol.replace("/", "") + "T"


class PaperBroker:
    """Fills executed at the provider's latest close + configured slippage.

    The fill price is taken from the strategy's timeframe so position sizing
    and PnL stay consistent with the signal that produced them.
    """

    name = "paper"
    requires_keys = False

    def __init__(self, slippage_percent: float = 0.1, timeframe: str = "1H") -> None:
        self._slippage = slippage_percent
        self.timeframe = timeframe

    def market_price(self, symbol: str) -> float:
        return float(get_provider().get_ohlcv(symbol, self.timeframe)[-1]["close"])

    def _fill_price(self, symbol: str, side: str) -> float:
        price = self.market_price(symbol)
        slip = price * (self._slippage / 100.0)
        return price - slip if side == "BUY" else price + slip

    def buy_quote(self, symbol: str, quote_cash: float) -> Fill:
        price = self._fill_price(symbol, "BUY")
        base_qty = quote_cash / price
        return Fill(normalize_symbol(symbol), "BUY", round(price, 8), round(base_qty, 8), quote_cash)

    def sell_base(self, symbol: str, base_qty: float) -> Fill:
        price = self._fill_price(symbol, "SELL")
        quote = base_qty * price
        return Fill(normalize_symbol(symbol), "SELL", round(price, 8), round(base_qty, 8), round(quote, 8))


class BinanceBroker:
    """Real Binance spot execution using signed REST requests.

    Scoped to trading keys: default recommendation is an API key with
    \"Enable Spot & Margin Trading\" only (permissions prevent withdrawals).
    """

    name = "binance-live"
    requires_keys = True

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = httpx.Client(base_url=BINANCE_SPOT_ENDPOINT, timeout=10.0)

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _signed(self, path: str, params: dict) -> dict:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        query += "&signature=" + hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        resp = self._client.post(
            path,
            params=query,
            headers={"X-MBX-APIKEY": self._api_key},
        )
        resp.raise_for_status()
        return resp.json()

    def market_price(self, symbol: str) -> float:
        resp = self._client.get(
            "/api/v3/ticker/price",
            params={"symbol": _binance_symbol(symbol)},
        )
        resp.raise_for_status()
        return float(resp.json()["price"])

    def buy_quote(self, symbol: str, quote_cash: float) -> Fill:
        data = self._signed(
            "/api/v3/order",
            {
                "symbol": _binance_symbol(symbol),
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": f"{quote_cash:.8f}",
                "newOrderRespType": "FULL",
            },
        )
        fills = data.get("fills") or [{"price": data["price"], "qty": data["executedQty"]}]
        avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / sum(
            float(f["qty"]) for f in fills
        )
        base_qty = sum(float(f["qty"]) for f in fills)
        return Fill(normalize_symbol(symbol), "BUY", round(avg_price, 8), round(base_qty, 8), quote_cash)

    def sell_base(self, symbol: str, base_qty: float) -> Fill:
        data = self._signed(
            "/api/v3/order",
            {
                "symbol": _binance_symbol(symbol),
                "side": "SELL",
                "type": "MARKET",
                "quantity": f"{base_qty:.8f}",
                "newOrderRespType": "FULL",
            },
        )
        fills = data.get("fills") or [{"price": data["price"], "qty": data["executedQty"]}]
        avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / sum(
            float(f["qty"]) for f in fills
        )
        quote = base_qty * avg_price
        return Fill(normalize_symbol(symbol), "SELL", round(avg_price, 8), round(base_qty, 8), round(quote, 8))


def get_broker(mode: str = "paper", timeframe: str = "1H") -> Optional[Broker]:
    """Return the broker for the requested mode.

    ``mode='live'`` returns the Binance adapter only when keys exist; otherwise
    returns None so callers can fail with a clear message instead of crashing.
    Paper fills are stamped with the strategy timeframe so sizing stays
    consistent with the signal's bars.
    """
    if mode == "live":
        broker = BinanceBroker(BINANCE_API_KEY or "", BINANCE_API_SECRET or "")
        if broker.available:
            return broker
        return None
    return PaperBroker(timeframe=timeframe)