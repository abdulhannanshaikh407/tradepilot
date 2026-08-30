# app/api/routes/strategies.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import StrategyCreate, StrategyOut

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _dump_rules(rules) -> list:
    return [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in (rules or [])]


def _get_owned(db: Session, user: models.User, strategy_id: int) -> models.Strategy:
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return strategy


@router.get("/", response_model=list[StrategyOut])
def list_strategies(
    search: Optional[str] = None,
    asset: Optional[str] = None,
    direction: Optional[str] = None,
    status_: Optional[str] = Query(None, alias="status"),
    sort: str = "created_at",
    order: str = "desc",
    skip: int = 0,
    limit: int = 100,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Strategy).filter(models.Strategy.user_id == user.id)
    if search:
        query = query.filter(models.Strategy.name.ilike(f"%{search}%"))
    if asset:
        query = query.filter(models.Strategy.asset == asset.upper())
    if direction:
        query = query.filter(models.Strategy.direction == direction.upper())
    if status_:
        active = status_.lower() == "active"
        query = query.filter(models.Strategy.is_active == active)

    sort_col = getattr(models.Strategy, sort, models.Strategy.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())
    strategies = query.offset(skip).limit(limit).all()
    return [StrategyOut.model_validate(s) for s in strategies]


@router.get("/filters")
def strategy_filters(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategies = db.query(models.Strategy).filter(models.Strategy.user_id == user.id).all()
    return {
        "assets": sorted({s.asset for s in strategies}),
        "timeframes": sorted({s.timeframe for s in strategies}),
        "directions": sorted({s.direction for s in strategies}),
        "strategy_types": sorted({s.strategy_type for s in strategies if s.strategy_type}),
    }


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(
    strategy_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return StrategyOut.model_validate(_get_owned(db, user, strategy_id))


@router.post("/", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: StrategyCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = models.Strategy(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        asset=payload.asset,
        market=payload.market,
        timeframe=payload.timeframe,
        strategy_type=payload.strategy_type,
        direction=payload.direction,
        indicators=_dump_rules(payload.indicators),
        entry_rules=_dump_rules(payload.entry_rules),
        confirmation_rules=_dump_rules(payload.confirmation_rules),
        exit_rules=_dump_rules(payload.exit_rules),
        stop_loss_type=payload.stop_loss_type,
        stop_loss_value=payload.stop_loss_value,
        take_profit_type=payload.take_profit_type,
        take_profit_value=payload.take_profit_value,
        risk_per_trade=payload.risk_per_trade,
        risk_reward=payload.risk_reward,
        confidence=payload.confidence,
        assumptions=payload.assumptions,
        missing_information=payload.missing_information,
        source=payload.source,
        source_url=payload.source_url,
        is_demo=payload.is_demo,
        is_active=payload.is_active,
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return StrategyOut.model_validate(strategy)


@router.put("/{strategy_id}", response_model=StrategyOut)
def update_strategy(
    strategy_id: int,
    payload: StrategyCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _get_owned(db, user, strategy_id)
    for field, value in payload.model_dump().items():
        setattr(strategy, field, value)
    db.commit()
    db.refresh(strategy)
    return StrategyOut.model_validate(strategy)


@router.patch("/{strategy_id}/status")
def toggle_strategy(
    strategy_id: int,
    active: bool,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _get_owned(db, user, strategy_id)
    strategy.is_active = active
    db.commit()
    return {"message": "Strategy updated."}


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(
    strategy_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = _get_owned(db, user, strategy_id)
    db.delete(strategy)
    db.commit()
    return None