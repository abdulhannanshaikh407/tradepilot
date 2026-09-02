# app/api/routes/brokers.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.encryption import decrypt_value, encrypt_value
from app.db.database import get_db
from app.db import models
from app.services.broker_connector import BrokerConnector
from app.services.alpaca_connector import AlpacaConnector
from app.services.binance_connector import BinanceConnector
from app.services.oanda_connector import OandaConnector

router = APIRouter(prefix="/brokers", tags=["brokers"])


# ---- Schemas ----
class BrokerConnectRequest(BaseModel):
    broker: str  # "alpaca" | "binance" | "oanda"
    api_key: str
    api_secret: str = ""  # not needed for OANDA (use account_id instead)
    account_type: str = "paper"  # "paper" | "live"
    account_id: str = ""  # OANDA account ID


class BrokerConnectionOut(BaseModel):
    id: int
    broker: str
    account_type: str
    is_verified: bool
    last_verified_at: Optional[str] = None
    created_at: Optional[str] = None


class BrokerAccountOut(BaseModel):
    balance: float
    buying_power: float
    cash: float
    account_type: str
    broker_name: str
    daily_pnl: float
    daily_pnl_percent: float
    positions: list[dict]


# ---- Factory ----
def get_connector(broker_name: str, api_key: str, api_secret: str = "", account_type: str = "paper", account_id: str = "") -> BrokerConnector:
    if broker_name == "alpaca":
        return AlpacaConnector(api_key, api_secret, account_type)
    elif broker_name == "binance":
        return BinanceConnector(api_key, api_secret)
    elif broker_name == "oanda":
        return OandaConnector(api_key, account_id, account_type)
    raise ValueError(f"Unsupported broker: {broker_name}")


def _decrypt_connector(connection: models.BrokerConnection) -> BrokerConnector:
    api_key = decrypt_value(connection.api_key_encrypted)
    api_secret = decrypt_value(connection.api_secret_encrypted)
    account_id = getattr(connection, "account_id", "") or ""
    return get_connector(connection.broker_name, api_key, api_secret, connection.account_type, account_id)


# ---- Routes ----
@router.post("/connect", status_code=status.HTTP_201_CREATED)
async def connect_broker(
    body: BrokerConnectRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.broker not in ("alpaca", "binance", "oanda"):
        raise HTTPException(status_code=400, detail="Unsupported broker. Use 'alpaca', 'binance', or 'oanda'.")

    if body.account_type == "live":
        existing_live = (
            db.query(models.BrokerConnection)
            .filter(
                models.BrokerConnection.user_id == user.id,
                models.BrokerConnection.broker_name == body.broker,
                models.BrokerConnection.account_type == "live",
            )
            .first()
        )
        if existing_live:
            raise HTTPException(status_code=400, detail=f"Already have a live {body.broker} connection.")

    connector = get_connector(body.broker, body.api_key, body.api_secret, body.account_type, body.account_id)
    is_valid = await connector.authenticate(body.api_key, body.api_secret or body.account_id)

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid broker credentials.")

    connection = models.BrokerConnection(
        user_id=user.id,
        broker_name=body.broker,
        api_key_encrypted=encrypt_value(body.api_key),
        api_secret_encrypted=encrypt_value(body.api_secret or body.account_id),
        account_type=body.account_type,
        account_id=body.account_id or None,
        is_verified=True,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    return {
        "connection_id": connection.id,
        "broker": body.broker,
        "account_type": body.account_type,
        "is_verified": True,
    }


@router.get("/connected")
async def get_connected_brokers(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connections = (
        db.query(models.BrokerConnection)
        .filter(models.BrokerConnection.user_id == user.id)
        .all()
    )
    return [
        BrokerConnectionOut(
            id=c.id,
            broker=c.broker_name,
            account_type=c.account_type,
            is_verified=c.is_verified,
            last_verified_at=c.last_verified_at.isoformat() if c.last_verified_at else None,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in connections
    ]


@router.get("/{connection_id}/account")
async def get_account(
    connection_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(models.BrokerConnection)
        .filter(
            models.BrokerConnection.id == connection_id,
            models.BrokerConnection.user_id == user.id,
        )
        .first()
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    try:
        connector = _decrypt_connector(connection)
        account = await connector.get_account()
        return BrokerAccountOut(
            balance=account.balance,
            buying_power=account.buying_power,
            cash=account.cash,
            account_type=account.account_type,
            broker_name=account.broker_name,
            daily_pnl=account.daily_pnl,
            daily_pnl_percent=account.daily_pnl_percent,
            positions=[{
                "symbol": p.symbol,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "pnl": p.pnl,
                "pnl_percent": p.pnl_percent,
            } for p in account.positions],
        )
    except Exception as exc:
        connection.last_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to fetch account: {exc}")


@router.get("/{connection_id}/positions")
async def get_positions(
    connection_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(models.BrokerConnection)
        .filter(
            models.BrokerConnection.id == connection_id,
            models.BrokerConnection.user_id == user.id,
        )
        .first()
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    try:
        connector = _decrypt_connector(connection)
        positions = await connector.get_positions()
        return [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "pnl": p.pnl,
                "pnl_percent": p.pnl_percent,
            }
            for p in positions
        ]
    except Exception as exc:
        connection.last_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to fetch positions: {exc}")


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_broker(
    connection_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(models.BrokerConnection)
        .filter(
            models.BrokerConnection.id == connection_id,
            models.BrokerConnection.user_id == user.id,
        )
        .first()
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    db.delete(connection)
    db.commit()
    return None
