# app/api/routes/signals.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import SignalCreate, SignalGenerateRequest, SignalOut
from app.services import signal_engine, usage_service
from app.services.notification_service import create_notification
from app.services.signal_engine import build_strategy_rules_dict

router = APIRouter(prefix="/signals", tags=["signals"])


def _get_strategy(db: Session, user: models.User, strategy_id: int) -> models.Strategy:
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return strategy


@router.get("/", response_model=list[SignalOut])
def list_signals(
    strategy_id: Optional[int] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Signal).filter(models.Signal.user_id == user.id)
    if strategy_id:
        query = query.filter(models.Signal.strategy_id == strategy_id)
    if symbol:
        query = query.filter(models.Signal.symbol == symbol.upper())
    if status:
        query = query.filter(models.Signal.status == status.upper())
    if source:
        query = query.filter(models.Signal.source == source)
    signals = query.order_by(models.Signal.created_at.desc()).limit(min(limit, 500)).all()
    return [SignalOut.model_validate(s) for s in signals]


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(
    signal_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    signal = (
        db.query(models.Signal)
        .filter(models.Signal.id == signal_id, models.Signal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")
    return SignalOut.model_validate(signal)


@router.post("/", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
def create_signal(
    payload: SignalCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, _ = usage_service.check_and_increment(db, user, "signals")
    if not allowed:
        raise HTTPException(status_code=429, detail="Signal limit reached for today.")
    signal = models.Signal(
        user_id=user.id,
        strategy_id=payload.strategy_id,
        symbol=payload.symbol.upper(),
        direction=payload.direction.upper(),
        entry_price=payload.entry_price,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
        risk_reward=payload.risk_reward,
        confidence=payload.confidence,
        reason=payload.reason,
        status=models.SignalStatus.PENDING.value,
        source=payload.source,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    create_notification(
        db,
        user.id,
        "new_signal",
        "New signal",
        f"{signal.symbol} {signal.direction} signal created.",
        user.email,
    )
    return SignalOut.model_validate(signal)


@router.post("/generate", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
def generate_signal_from_strategy(
    payload: SignalGenerateRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, _ = usage_service.check_and_increment(db, user, "signals")
    if not allowed:
        raise HTTPException(status_code=429, detail="Signal limit reached for today.")

    strategy = _get_strategy(db, user, payload.strategy_id)
    rules = build_strategy_rules_dict(strategy)
    try:
        suggestion = signal_engine.generate_signal(rules, strategy.asset, strategy.timeframe)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot generate signal for {strategy.asset} on {strategy.timeframe}: {exc}",
        )

    signal = models.Signal(
        user_id=user.id,
        strategy_id=strategy.id,
        symbol=suggestion["symbol"],
        direction=suggestion["direction"],
        entry_price=suggestion["entry_price"],
        stop_loss=suggestion["stop_loss"],
        take_profit=suggestion["take_profit"],
        risk_reward=suggestion["risk_reward"],
        confidence=suggestion["confidence"],
        reason=suggestion["reason"],
        status=suggestion["status"],
        source=suggestion.get("source", "signal_engine"),
        is_demo=strategy.is_demo,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    create_notification(
        db,
        user.id,
        "new_signal",
        "Signals generated",
        f"{strategy.name} produced a {suggestion['direction']} signal for {suggestion['symbol']}.",
        user.email,
    )
    return SignalOut.model_validate(signal)


@router.patch("/{signal_id}/status")
def update_signal_status(
    signal_id: int,
    status: str,
    outcome: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    signal = (
        db.query(models.Signal)
        .filter(models.Signal.id == signal_id, models.Signal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")
    signal.status = status.upper()
    db.commit()
    return SignalOut.model_validate(signal)


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_signal(
    signal_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    signal = (
        db.query(models.Signal)
        .filter(models.Signal.id == signal_id, models.Signal.user_id == user.id)
        .first()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")
    db.delete(signal)
    db.commit()
    return None