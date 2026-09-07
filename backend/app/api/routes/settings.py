# app/api/routes/settings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import verify_password, hash_password
from app.db.database import get_db
from app.db import models
from app.db.schemas import SettingsUpdate, UserOut

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=UserOut)
def get_settings(user: models.User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.put("/", response_model=UserOut)
def update_settings(
    payload: SettingsUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.name is not None:
        user.name = payload.name.strip() or user.name

    if payload.current_password or payload.new_password:
        if not payload.current_password or not user.password_hash:
            raise HTTPException(status_code=400, detail="Current password required.")
        if not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        if payload.new_password:
            if len(payload.new_password) < 8:
                raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
            user.password_hash = hash_password(payload.new_password)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/kill-switch")
def toggle_kill_switch(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle the user-level kill switch. When enabled, blocks all live order execution."""
    user.kill_switch = not user.kill_switch
    db.commit()
    db.refresh(user)
    state = "enabled" if user.kill_switch else "disabled"
    return {"kill_switch": user.kill_switch, "message": f"Kill switch {state}. Live orders are {'blocked' if user.kill_switch else 'allowed'}."}


@router.get("/kill-switch")
def get_kill_switch_status(
    user: models.User = Depends(get_current_user),
):
    """Check current kill switch status."""
    return {"kill_switch": user.kill_switch}