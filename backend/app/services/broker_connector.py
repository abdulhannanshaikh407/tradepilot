# app/services/broker_connector.py
"""Unified broker connector interface.

Provides an abstract base class ``BrokerConnector`` that all broker
integrations must implement.  Concrete implementations live in separate
modules (``alpaca_connector``, ``binance_connector``) so the core interface
stays broker-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BrokerAccount:
    """Unified account info from any broker."""

    balance: float
    buying_power: float
    cash: float
    positions: list["BrokerPosition"] = field(default_factory=list)
    account_type: str = "paper"  # "paper" | "live"
    broker_name: str = ""
    daily_pnl: float = 0.0
    daily_pnl_percent: float = 0.0


@dataclass
class BrokerPosition:
    """Open position."""

    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    pnl: float = 0.0
    pnl_percent: float = 0.0


@dataclass
class BrokerOrder:
    """Submitted order."""

    order_id: str
    symbol: str
    quantity: float
    side: str  # "buy" | "sell"
    price: Optional[float] = None  # None = market
    status: str = "pending"  # "pending" | "filled" | "cancelled"
    filled_price: Optional[float] = None
    filled_at: Optional[datetime] = None


class BrokerConnector(ABC):
    """Base class for broker connections."""

    @abstractmethod
    async def authenticate(self, api_key: str, api_secret: str) -> bool:
        """Test credentials, return True if valid."""
        ...

    @abstractmethod
    async def get_account(self) -> BrokerAccount:
        """Fetch current account status."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Fetch all open positions."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Fetch single position or None if not open."""
        ...

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "market",
        price: Optional[float] = None,
    ) -> BrokerOrder:
        """Place an order, return order object."""
        ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Fetch order status."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order, return True if successful."""
        ...

    @abstractmethod
    async def close_position(self, symbol: str) -> BrokerOrder:
        """Close entire position (market sell/buy), return order."""
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict:
        """Get real-time price: {symbol, bid, ask, last, volume}."""
        ...
