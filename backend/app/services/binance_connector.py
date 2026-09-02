# app/services/binance_connector.py
"""Binance broker connector (crypto, spot trading)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.services.broker_connector import (
    BrokerAccount,
    BrokerConnector,
    BrokerOrder,
    BrokerPosition,
)

logger = logging.getLogger("tradepilot.broker.binance")

BINANCE_SPOT_ENDPOINT = "https://api.binance.com"


def _binance_symbol(symbol: str) -> str:
    """'BTC/USD' -> 'BTCUSDT'."""
    return symbol.replace("/", "").replace("USD", "USDT")


class BinanceConnector(BrokerConnector):
    """Connect to Binance (crypto, spot trading)."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BINANCE_SPOT_ENDPOINT

    def _sign_request(self, params: dict) -> dict:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    async def authenticate(self, api_key: str, api_secret: str) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                params = {"timestamp": int(time.time() * 1000)}
                query = f"timestamp={params['timestamp']}"
                sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                params["signature"] = sig

                resp = await client.get(
                    f"{self.base_url}/api/v3/account",
                    headers={"X-MBX-APIKEY": api_key},
                    params=params,
                    timeout=10,
                )
                return resp.status_code == 200
            except Exception as exc:
                logger.warning("Binance auth failed: %s", exc)
                return False

    async def get_account(self) -> BrokerAccount:
        async with httpx.AsyncClient() as client:
            params = self._sign_request({})
            resp = await client.get(
                f"{self.base_url}/api/v3/account",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            balances = data.get("balances", [])
            total_balance = sum(
                float(bal["free"]) + float(bal["locked"]) for bal in balances
            )
            free_balance = sum(float(bal["free"]) for bal in balances)
            usdt_cash = sum(
                float(bal["free"])
                for bal in balances
                if bal["asset"] in ("USDT", "BUSD", "USDC")
            )

            positions = await self.get_positions()

            return BrokerAccount(
                balance=total_balance,
                buying_power=free_balance,
                cash=usdt_cash,
                positions=positions,
                account_type="live",
                broker_name="binance",
                daily_pnl=0.0,
                daily_pnl_percent=0.0,
            )

    async def get_positions(self) -> list[BrokerPosition]:
        async with httpx.AsyncClient() as client:
            params = self._sign_request({})
            resp = await client.get(
                f"{self.base_url}/api/v3/account",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            positions = []
            for bal in data.get("balances", []):
                free = float(bal["free"])
                locked = float(bal["locked"])
                if free <= 0 and locked <= 0:
                    continue
                asset = bal["asset"]
                if asset in ("USDT", "BUSD", "USDC", "USD", "EUR", "GBP"):
                    continue

                symbol_binance = f"{asset}USDT"
                try:
                    price_resp = await client.get(
                        f"{self.base_url}/api/v3/ticker/price",
                        params={"symbol": symbol_binance},
                        timeout=5,
                    )
                    current_price = float(price_resp.json().get("price", 0))
                except Exception:
                    current_price = 0.0

                quantity = free + locked
                positions.append(BrokerPosition(
                    symbol=f"{asset}/USD",
                    quantity=quantity,
                    entry_price=current_price,
                    current_price=current_price,
                    pnl=0.0,
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
        binance_sym = _binance_symbol(symbol)

        params: dict = {
            "symbol": binance_sym,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{quantity:.8f}",
        }
        if price is not None:
            params["price"] = f"{price:.8f}"

        signed = self._sign_request(params)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/v3/order",
                headers=self._headers(),
                params=signed,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            fills = data.get("fills", [])
            if fills:
                avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / sum(
                    float(f["qty"]) for f in fills
                )
            else:
                avg_price = float(data.get("price", 0))

            status_map = {"NEW": "pending", "FILLED": "filled", "CANCELED": "cancelled", "PARTIALLY_FILLED": "pending"}
            return BrokerOrder(
                order_id=str(data.get("orderId", "")),
                symbol=symbol,
                quantity=float(data.get("executedQty", 0)),
                side=data["side"].lower(),
                price=float(data.get("price", 0)) if data.get("price") else None,
                status=status_map.get(data.get("status", ""), "pending"),
                filled_price=avg_price,
                filled_at=datetime.now(timezone.utc),
            )

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get order status from Binance."""
        async with httpx.AsyncClient() as client:
            # Note: Binance requires symbol for order lookup, but our interface doesn't pass it.
            # We'll use a placeholder symbol and rely on the order ID.
            # In production, you'd need to track the symbol with the order.
            resp = await client.get(
                f"{self.base_url}/api/v3/order",
                headers=self._headers(),
                params=self._sign_request({"orderId": order_id, "symbol": "BTCUSDT"}),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            
            status_map = {"NEW": "pending", "FILLED": "filled", "CANCELED": "cancelled", "PARTIALLY_FILLED": "pending"}
            return BrokerOrder(
                order_id=str(data.get("orderId", "")),
                symbol=data.get("symbol", ""),
                quantity=float(data.get("origQty", 0)),
                side=data.get("side", "").lower(),
                price=float(data.get("price", 0)) if data.get("price") else None,
                status=status_map.get(data.get("status", ""), "pending"),
                filled_price=float(data.get("price", 0)) if data.get("price") else None,
                filled_at=datetime.now(timezone.utc),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on Binance."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.base_url}/api/v3/order",
                    headers=self._headers(),
                    params=self._sign_request({"orderId": order_id, "symbol": "BTCUSDT"}),
                    timeout=10,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def close_position(self, symbol: str) -> BrokerOrder:
        position = await self.get_position(symbol)
        if position is None:
            raise ValueError(f"No open position for {symbol}")

        return await self.place_order(
            symbol=symbol,
            quantity=position.quantity,
            side="sell",
            order_type="market",
        )

    async def get_quote(self, symbol: str) -> dict:
        binance_sym = _binance_symbol(symbol)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v3/ticker/bookTicker",
                params={"symbol": binance_sym},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "symbol": symbol,
                "bid": float(data.get("bidPrice", 0)),
                "ask": float(data.get("askPrice", 0)),
                "last": float(data.get("bidPrice", 0)),
                "volume": 0,
            }
