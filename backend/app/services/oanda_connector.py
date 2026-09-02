# app/services/oanda_connector.py
"""OANDA broker connector — free demo account for forex + metals.

Provides real-time pricing, historical data (since 2005), and trade
execution (paper + live). Sign up at oanda.com for free demo keys.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from app.services.broker_connector import (
    BrokerAccount,
    BrokerConnector,
    BrokerOrder,
    BrokerPosition,
)

logger = logging.getLogger("tradepilot.broker.oanda")

OANDA_PRACTICE_URL = "https://api-fxpractice.oanda.com"
OANDA_LIVE_URL = "https://api-fxtrade.oanda.com"
OANDA_STREAM_PRACTICE_URL = "https://stream-fxpractice.oanda.com"
OANDA_STREAM_LIVE_URL = "https://stream-fxtrade.oanda.com"
OANDA_API_VERSION = "v3"

# OANDA instrument mapping
INSTRUMENT_MAP = {
    "EUR/USD": "EUR_USD",
    "GBP/USD": "GBP_USD",
    "USD/JPY": "USD_JPY",
    "AUD/USD": "AUD_USD",
    "USD/CAD": "USD_CAD",
    "USD/CHF": "USD_CHF",
    "NZD/USD": "NZD_USD",
    "XAUUSD": "XAU_USD",
    "XAGUSD": "XAG_USD",
    "EUR/GBP": "EUR_GBP",
    "EUR/JPY": "EUR_JPY",
    "GBP/JPY": "GBP_JPY",
    "AUD/JPY": "AUD_JPY",
    "EUR/AUD": "EUR_AUD",
    "EUR/CAD": "EUR_CAD",
    "EUR/CHF": "EUR_CHF",
    "GBP/CHF": "GBP_CHF",
    "USD/SGD": "USD_SGD",
    "USD/HKD": "USD_HKD",
    "USD/MXN": "USD_MXN",
}


def _oanda_instrument(oanda_id: str) -> str:
    """Convert canonical symbol to OANDA instrument format."""
    return INSTRUMENT_MAP.get(oanda_id, oanda_id.replace("/", "_"))


def _canonical_to_oanda(symbol: str) -> str:
    """Convert 'EUR/USD' or 'XAUUSD' to OANDA format 'EUR_USD' or 'XAU_USD'."""
    if symbol in INSTRUMENT_MAP:
        return INSTRUMENT_MAP[symbol]
    return symbol.replace("/", "_").replace("USD", "_USD") if "/" in symbol else symbol


class OandaConnector(BrokerConnector):
    """Connect to OANDA (forex + metals, paper + live)."""

    def __init__(self, api_key: str, account_id: str, account_type: str = "paper") -> None:
        self.api_key = api_key
        self.account_id = account_id
        self.account_type = account_type
        self.base_url = OANDA_PRACTICE_URL if account_type == "paper" else OANDA_LIVE_URL
        self.stream_url = (
            OANDA_STREAM_PRACTICE_URL if account_type == "paper" else OANDA_STREAM_LIVE_URL
        )
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def authenticate(self, api_key: str, api_secret: str) -> bool:
        """Test credentials by fetching account details."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                return resp.status_code == 200
            except Exception as exc:
                logger.warning("OANDA auth failed: %s", exc)
                return False

    async def get_account(self) -> BrokerAccount:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("account", {})

            positions = await self.get_positions()

            balance = float(data.get("balance", 0))
            nav = float(data.get("NAV", balance))
            daily_pnl = nav - balance

            return BrokerAccount(
                balance=nav,
                buying_power=float(data.get("marginAvailable", 0)),
                cash=balance,
                positions=positions,
                account_type=self.account_type,
                broker_name="oanda",
                daily_pnl=daily_pnl,
                daily_pnl_percent=(daily_pnl / balance * 100) if balance else 0,
            )

    async def get_positions(self) -> list[BrokerPosition]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/openTrades",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            positions = []
            for trade in data.get("trades", []):
                instrument = trade.get("instrument", "")
                # Convert OANDA instrument back to canonical
                canonical = instrument.replace("_", "/") if "_" in instrument else instrument
                positions.append(BrokerPosition(
                    symbol=canonical,
                    quantity=float(trade.get("currentUnits", 0)),
                    entry_price=float(trade.get("price", 0)),
                    current_price=float(trade.get("price", 0)),
                    pnl=float(trade.get("unrealizedPL", 0)),
                    pnl_percent=0.0,
                ))
            return positions

    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None

    async def place_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "market",
        price: Optional[float] = None,
    ) -> BrokerOrder:
        instrument = _canonical_to_oanda(symbol)
        units = int(quantity) if side.lower() == "buy" else -int(quantity)

        body: dict = {
            "type": "MARKET" if order_type == "market" else "LIMIT",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK" if order_type == "market" else "GTC",
        }

        if order_type == "limit" and price is not None:
            body["price"] = str(price)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/orders",
                headers=self._headers,
                json={"order": body},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            order_data = data.get("orderFillTransaction", data.get("orderCreateTransaction", {}))
            filled_price = float(order_data.get("price", 0)) if order_data.get("price") else None
            filled_at = None
            if order_data.get("time"):
                filled_at = datetime.fromisoformat(order_data["time"].replace("Z", "+00:00"))

            return BrokerOrder(
                order_id=str(order_data.get("id", "")),
                symbol=symbol,
                quantity=abs(float(order_data.get("units", 0))),
                side=side.lower(),
                price=price,
                status="filled" if filled_price else "pending",
                filled_price=filled_price,
                filled_at=filled_at,
            )

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/trades/{order_id}",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("trade", {})
            return BrokerOrder(
                order_id=order_id,
                symbol=data.get("instrument", ""),
                quantity=abs(float(data.get("currentUnits", 0))),
                side="buy" if float(data.get("currentUnits", 0)) > 0 else "sell",
                status="filled",
                filled_price=float(data.get("price", 0)) if data.get("price") else None,
            )

    async def cancel_order(self, order_id: str) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.put(
                    f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/trades/{order_id}/close",
                    headers=self._headers,
                    json={"units": "ALL"},
                    timeout=10,
                )
                return resp.status_code in (200, 201)
            except Exception:
                return False

    async def close_position(self, symbol: str) -> BrokerOrder:
        position = await self.get_position(symbol)
        if position is None:
            raise ValueError(f"No open position for {symbol}")

        return await self.place_order(
            symbol=symbol,
            quantity=abs(position.quantity),
            side="sell" if position.quantity > 0 else "buy",
            order_type="market",
        )

    async def get_quote(self, symbol: str) -> dict:
        """Get real-time OANDA pricing."""
        instrument = _canonical_to_oanda(symbol)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/pricing",
                headers=self._headers,
                params={"instruments": instrument},
                timeout=10,
            )
            resp.raise_for_status()
            prices = resp.json().get("prices", [])
            if not prices:
                return {"symbol": symbol, "bid": 0, "ask": 0, "last": 0, "volume": 0}

            p = prices[0]
            bid = float(p.get("bids", [{}])[0].get("price", 0))
            ask = float(p.get("asks", [{}])[0].get("price", 0))
            return {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "last": (bid + ask) / 2,
                "volume": 0,
            }

    async def get_candles(
        self, symbol: str, timeframe: str = "1H", count: int = 500
    ) -> List[dict]:
        """Fetch OHLCV candles from OANDA (bonus: real historical data)."""
        instrument = _canonical_to_oanda(symbol)
        granularity_map = {"15m": "M15", "1H": "H1", "4H": "H4", "1D": "D"}
        granularity = granularity_map.get(timeframe, "H1")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{OANDA_API_VERSION}/accounts/{self.account_id}/candles",
                headers=self._headers,
                params={
                    "instrument": instrument,
                    "granularity": granularity,
                    "count": min(count, 5000),
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            bars = []
            for candle in data.get("candles", []):
                if not candle.get("mid"):
                    continue
                mid = candle["mid"]
                ts = candle.get("time", "")
                bars.append({
                    "timestamp": ts,
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": float(candle.get("volume", 0)),
                })
            return bars
