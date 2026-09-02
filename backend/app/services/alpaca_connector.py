# app/services/alpaca_connector.py
"""Alpaca broker connector (US stocks + paper trading)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from app.services.broker_connector import (
    BrokerAccount,
    BrokerConnector,
    BrokerOrder,
    BrokerPosition,
)

logger = logging.getLogger("tradepilot.broker.alpaca")

ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_URL = "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"


class AlpacaConnector(BrokerConnector):
    """Connect to Alpaca (stocks, paper + live)."""

    def __init__(self, api_key: str, api_secret: str, account_type: str = "paper") -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_type = account_type
        self.base_url = ALPACA_PAPER_URL if account_type == "paper" else ALPACA_LIVE_URL
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

    async def authenticate(self, api_key: str, api_secret: str) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/v2/account",
                    headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
                    timeout=10,
                )
                return resp.status_code == 200
            except Exception as exc:
                logger.warning("Alpaca auth failed: %s", exc)
                return False

    async def get_account(self) -> BrokerAccount:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/account",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            positions = await self.get_positions()

            equity = float(data.get("equity", 0))
            last_equity = float(data.get("last_equity", equity))
            daily_pnl = equity - last_equity

            return BrokerAccount(
                balance=equity,
                buying_power=float(data.get("buying_power", 0)),
                cash=float(data.get("cash", 0)),
                positions=positions,
                account_type=self.account_type,
                broker_name="alpaca",
                daily_pnl=daily_pnl,
                daily_pnl_percent=(daily_pnl / last_equity * 100) if last_equity else 0,
            )

    async def get_positions(self) -> list[BrokerPosition]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/positions",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            positions = []
            for pos in resp.json():
                positions.append(BrokerPosition(
                    symbol=pos["symbol"],
                    quantity=float(pos["qty"]),
                    entry_price=float(pos["avg_entry_price"]),
                    current_price=float(pos["current_price"]),
                    pnl=float(pos["unrealized_pl"]),
                    pnl_percent=float(pos["unrealized_plpc"]) * 100,
                ))
            return positions

    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/v2/positions/{symbol}",
                    headers=self._headers,
                    timeout=10,
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                pos = resp.json()
                return BrokerPosition(
                    symbol=pos["symbol"],
                    quantity=float(pos["qty"]),
                    entry_price=float(pos["avg_entry_price"]),
                    current_price=float(pos["current_price"]),
                    pnl=float(pos["unrealized_pl"]),
                    pnl_percent=float(pos["unrealized_plpc"]) * 100,
                )
            except httpx.HTTPStatusError:
                return None

    async def place_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "market",
        price: Optional[float] = None,
    ) -> BrokerOrder:
        body: dict = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.lower(),
            "type": order_type,
            "time_in_force": "day",
        }
        if price is not None:
            body["limit_price"] = str(price)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/orders",
                headers=self._headers,
                json=body,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            filled_price = None
            if data.get("filled_avg_price"):
                filled_price = float(data["filled_avg_price"])

            filled_at = None
            if data.get("filled_at"):
                filled_at = datetime.fromisoformat(data["filled_at"].replace("Z", "+00:00"))

            return BrokerOrder(
                order_id=data["id"],
                symbol=data["symbol"],
                quantity=float(data.get("qty", 0)),
                side=data["side"].lower(),
                price=float(data["limit_price"]) if data.get("limit_price") else None,
                status=data["status"],
                filled_price=filled_price,
                filled_at=filled_at,
            )

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/orders/{order_id}",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return BrokerOrder(
                order_id=data["id"],
                symbol=data["symbol"],
                quantity=float(data.get("qty", 0)),
                side=data["side"].lower(),
                price=float(data["limit_price"]) if data.get("limit_price") else None,
                status=data["status"],
                filled_price=float(data["filled_avg_price"]) if data.get("filled_avg_price") else None,
                filled_at=datetime.fromisoformat(data["filled_at"].replace("Z", "+00:00")) if data.get("filled_at") else None,
            )

    async def cancel_order(self, order_id: str) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.delete(
                    f"{self.base_url}/v2/orders/{order_id}",
                    headers=self._headers,
                    timeout=10,
                )
                return resp.status_code in (200, 204)
            except Exception:
                return False

    async def close_position(self, symbol: str) -> BrokerOrder:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/v2/positions/{symbol}",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return BrokerOrder(
                order_id=data.get("id", ""),
                symbol=symbol,
                quantity=float(data.get("qty", 0)),
                side="sell",
                status=data.get("status", "filled"),
                filled_price=float(data.get("filled_avg_price", 0)) if data.get("filled_avg_price") else None,
            )

    async def get_quote(self, symbol: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()["quote"]
            return {
                "symbol": symbol,
                "bid": float(data.get("bp", 0)),
                "ask": float(data.get("ap", 0)),
                "last": float(data.get("bp", 0)),
                "volume": 0,
            }
