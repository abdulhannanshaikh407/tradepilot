# app/api/routes/autotrade.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import AUTOTRADE_INTERVAL, AUTOTRADE_ENABLED
from app.db.database import get_db
from app.db import models
from app.db.schemas import (
    AutoTradeConfigCreate,
    AutoTradeConfigOut,
    AutoTradeConfigUpdate,
    AutoTradeStatus,
    PositionOut,
)
from app.services import autotrade
from app.services.broker import get_broker
from app.services.market_data_service import MARKET_DATA_PROVIDER

router = APIRouter(prefix="/autotrade", tags=["autotrade"])


def _strategy_or_404(db: Session, user: models.User, strategy_id: int) -> models.Strategy:
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return strategy


def _config_out(config: models.AutoTradeConfig, strategy: models.Strategy) -> AutoTradeConfigOut:
    return AutoTradeConfigOut(
        id=config.id,
        strategy_id=config.strategy_id,
        strategy_name=strategy.name,
        strategy_symbol=strategy.asset,
        strategy_timeframe=strategy.timeframe,
        enabled=config.enabled,
        mode=config.mode,
        capital=config.capital,
        risk_percent=config.risk_percent,
        slippage_percent=config.slippage_percent,
        max_concurrent=config.max_concurrent,
        max_daily_loss=config.max_daily_loss,
        cooldown_minutes=config.cooldown_minutes,
        last_run_at=config.last_run_at,
        last_error=config.last_error,
    )


@router.get("/status", response_model=AutoTradeStatus)
def autotrade_status(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    open_positions = (
        db.query(models.Position)
        .filter(
            models.Position.user_id == user.id,
            models.Position.status == models.TradeStatus.OPEN.value,
        )
        .count()
    )
    return AutoTradeStatus(
        running=bool(autotrade.STATE["running"]),
        enabled=AUTOTRADE_ENABLED,
        interval_seconds=AUTOTRADE_INTERVAL,
        provider=MARKET_DATA_PROVIDER,
        last_run_at=autotrade.STATE["last_run_at"],
        last_error=autotrade.STATE["last_error"],
        strategies_watched=autotrade.STATE["strategies_watched"],
        open_positions=open_positions,
        live_available=bool(get_broker("live")),
    )


@router.get("/config", response_model=list[AutoTradeConfigOut])
def list_configs(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out = []
    for config in (
        db.query(models.AutoTradeConfig)
        .filter(models.AutoTradeConfig.user_id == user.id)
        .order_by(models.AutoTradeConfig.id.desc())
        .all()
    ):
        strategy = db.get(models.Strategy, config.strategy_id) if config.strategy_id else None
        if strategy:
            out.append(_config_out(config, strategy))
    return out


@router.post("/config", response_model=AutoTradeConfigOut, status_code=status.HTTP_201_CREATED)
def create_config(
    payload: AutoTradeConfigCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _strategy_or_404(db, user, payload.strategy_id)
    existing = (
        db.query(models.AutoTradeConfig)
        .filter(
            models.AutoTradeConfig.user_id == user.id,
            models.AutoTradeConfig.strategy_id == strategy.id,
        )
        .first()
    )
    if existing:
        return _config_out(existing, strategy)

    mode = "paper"
    if payload.mode == "live" and not get_broker("live"):
        raise HTTPException(
            status_code=400,
            detail="Live mode requires BINANCE_API_KEY / BINANCE_API_SECRET on the server.",
        )
    mode = payload.mode

    config = models.AutoTradeConfig(
        user_id=user.id,
        strategy_id=strategy.id,
        enabled=payload.enabled,
        mode=mode,
        capital=payload.capital,
        risk_percent=payload.risk_percent,
        slippage_percent=payload.slippage_percent,
        max_concurrent=payload.max_concurrent,
        max_daily_loss=payload.max_daily_loss,
        cooldown_minutes=payload.cooldown_minutes,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_out(config, strategy)


@router.patch("/config/{strategy_id}", response_model=AutoTradeConfigOut)
def update_config(
    strategy_id: int,
    payload: AutoTradeConfigUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _strategy_or_404(db, user, strategy_id)
    config = (
        db.query(models.AutoTradeConfig)
        .filter(
            models.AutoTradeConfig.user_id == user.id,
            models.AutoTradeConfig.strategy_id == strategy.id,
        )
        .first()
    )
    if config is None:
        raise HTTPException(status_code=404, detail="No auto-trade config for this strategy.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field == "mode" and value == "live" and not get_broker("live"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires BINANCE_API_KEY / BINANCE_API_SECRET on the server.",
            )
        setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return _config_out(config, strategy)


@router.delete("/config/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    strategy_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _strategy_or_404(db, user, strategy_id)
    config = (
        db.query(models.AutoTradeConfig)
        .filter(
            models.AutoTradeConfig.user_id == user.id,
            models.AutoTradeConfig.strategy_id == strategy.id,
        )
        .first()
    )
    if config:
        db.delete(config)
        db.commit()
    return None


@router.get("/positions", response_model=list[PositionOut])
def list_positions(
    status_f: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Position).filter(models.Position.user_id == user.id)
    if status_f:
        query = query.filter(models.Position.status == status_f.upper())
    positions = query.order_by(models.Position.opened_at.desc()).limit(200).all()
    return [PositionOut.model_validate(p) for p in positions]


@router.post("/positions/{position_id}/close", response_model=PositionOut)
def close_position(
    position_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    position = (
        db.query(models.Position)
        .filter(models.Position.id == position_id, models.Position.user_id == user.id)
        .first()
    )
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found.")
    if position.status == models.TradeStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Position is already closed.")

    from app.services.broker import get_broker

    strategy = db.get(models.Strategy, position.strategy_id) if position.strategy_id else None
    timeframe = strategy.timeframe if strategy else "1H"
    broker = get_broker(position.broker, timeframe) or get_broker("paper", timeframe)
    from app.services.autotrade import _close_position

    _close_position(db, position, "manual_close", broker, broker.market_price(position.symbol))
    db.refresh(position)
    return PositionOut.model_validate(position)


@router.post("/run-now")
def run_now(
    user: models.User = Depends(get_current_user),
    _: Session = Depends(get_db),
):
    """Trigger an immediate scan cycle (for demos and debugging)."""
    try:
        result = autotrade.run_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto-trade scan failed: {exc}")
    return result