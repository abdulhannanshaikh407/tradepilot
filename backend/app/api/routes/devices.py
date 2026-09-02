# app/api/routes/devices.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.services import fcm_service

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceTokenRegister(BaseModel):
    token: str
    platform: str = "android"  # android | ios | web


class DeviceTokenOut(BaseModel):
    id: int
    platform: str
    is_active: bool
    created_at: str | None = None


@router.post("/register")
def register_device(
    payload: DeviceTokenRegister,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register an FCM device token for push notifications."""
    existing = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.token == payload.token)
        .first()
    )
    if existing:
        existing.user_id = user.id
        existing.platform = payload.platform
        existing.is_active = True
        db.commit()
        return {"message": "Device token updated.", "id": existing.id}

    device = models.DeviceToken(
        user_id=user.id,
        token=payload.token,
        platform=payload.platform,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {"message": "Device registered.", "id": device.id}


@router.delete("/unregister")
def unregister_device(
    token: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a device token."""
    device = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.token == token, models.DeviceToken.user_id == user.id)
        .first()
    )
    if device:
        device.is_active = False
        db.commit()
    return {"message": "Device unregistered."}


@router.get("/", response_model=List[DeviceTokenOut])
def list_devices(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active device tokens for the current user."""
    devices = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.user_id == user.id, models.DeviceToken.is_active == True)
        .all()
    )
    return [
        DeviceTokenOut(
            id=d.id,
            platform=d.platform,
            is_active=d.is_active,
            created_at=d.created_at.isoformat() if d.created_at else None,
        )
        for d in devices
    ]


@router.post("/test-push")
def test_push(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a test push notification to all of the user's devices."""
    tokens = [
        d.token
        for d in db.query(models.DeviceToken)
        .filter(models.DeviceToken.user_id == user.id, models.DeviceToken.is_active == True)
        .all()
    ]
    if not tokens:
        raise HTTPException(status_code=404, detail="No registered devices found.")

    result = fcm_service.send_push_to_tokens(
        tokens,
        "TradePilot AI",
        "Push notifications are working!",
        {"type": "test"},
    )
    return {"message": f"Test push sent to {result['sent']} device(s).", **result}
