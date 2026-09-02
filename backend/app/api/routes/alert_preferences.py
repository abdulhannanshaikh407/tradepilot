# app/api/routes/alert_preferences.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import AlertPreferenceOut, AlertPreferenceUpdate

router = APIRouter(prefix="/alert-preferences", tags=["alert-preferences"])


def _get_or_create(db: Session, user_id: int, strategy_id: int) -> models.AlertPreference:
    pref = (
        db.query(models.AlertPreference)
        .filter(
            models.AlertPreference.user_id == user_id,
            models.AlertPreference.strategy_id == strategy_id,
        )
        .first()
    )
    if pref is None:
        pref = models.AlertPreference(user_id=user_id, strategy_id=strategy_id)
        db.add(pref)
        db.flush()
    return pref


@router.get("/", response_model=List[AlertPreferenceOut])
def list_alert_preferences(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = (
        db.query(models.AlertPreference)
        .filter(models.AlertPreference.user_id == user.id)
        .all()
    )
    result = []
    for p in prefs:
        strat = db.query(models.Strategy).filter(models.Strategy.id == p.strategy_id).first()
        out = AlertPreferenceOut.model_validate(p)
        out.strategy_name = strat.name if strat else None
        result.append(out)
    return result


@router.get("/strategy/{strategy_id}", response_model=AlertPreferenceOut)
def get_alert_preference(
    strategy_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = _get_or_create(db, user.id, strategy_id)
    strat = db.query(models.Strategy).filter(models.Strategy.id == strategy_id).first()
    out = AlertPreferenceOut.model_validate(pref)
    out.strategy_name = strat.name if strat else None
    return out


@router.put("/strategy/{strategy_id}", response_model=AlertPreferenceOut)
def update_alert_preference(
    strategy_id: int,
    payload: AlertPreferenceUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    pref = _get_or_create(db, user.id, strategy_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pref, field, value)
    db.commit()
    db.refresh(pref)

    out = AlertPreferenceOut.model_validate(pref)
    out.strategy_name = strategy.name
    return out


@router.patch("/strategy/{strategy_id}/toggle")
def toggle_alerts(
    strategy_id: int,
    enabled: bool = True,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strategy = (
        db.query(models.Strategy)
        .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    pref = _get_or_create(db, user.id, strategy_id)
    pref.alerts_enabled = enabled
    db.commit()

    return {"message": f"Alerts {'enabled' if enabled else 'disabled'} for '{strategy.name}'."}
