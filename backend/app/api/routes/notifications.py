# app/api/routes/notifications.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, le=200),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Notification).filter(models.Notification.user_id == user.id)
    if unread_only:
        query = query.filter(models.Notification.is_read.is_(False))
    notifications = query.order_by(models.Notification.created_at.desc()).limit(limit).all()
    return [NotificationOut.model_validate(n) for n in notifications]


@router.get("/unread-count")
def unread_count(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user.id, models.Notification.is_read.is_(False))
        .count()
    )
    return {"count": count}


@router.post("/read")
def mark_all_read(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(models.Notification).filter(models.Notification.user_id == user.id).update(
        {models.Notification.is_read: True}
    )
    db.commit()
    return {"message": "All notifications marked as read."}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == user.id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notification.is_read = True
    db.commit()
    return NotificationOut.model_validate(notification)


@router.delete("/{notification_id}", status_code=204)
def delete_notification(
    notification_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == user.id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    db.delete(notification)
    db.commit()
    return None