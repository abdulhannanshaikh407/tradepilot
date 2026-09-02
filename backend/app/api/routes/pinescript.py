# app/api/routes/pinescript.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import StrategyOut
from app.services.pinescript_service import generate_pinescript, generate_pinescript_from_strategy

router = APIRouter(prefix="/pinescript", tags=["pinescript"])


@router.get("/strategy/{strategy_id}")
def get_pinescript(
    strategy_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate PineScript v5 code from a saved strategy."""
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    pinescript = generate_pinescript_from_strategy(strategy)
    return {
        "pinescript": pinescript,
        "strategy_name": strategy.name,
        "strategy_id": strategy.id,
    }


@router.post("/generate")
def generate_from_config(
    config: dict,
    user: models.User = Depends(get_current_user),
):
    """Generate PineScript v5 code from a raw strategy config (no save required)."""
    pinescript = generate_pinescript(config)
    return {"pinescript": pinescript}
