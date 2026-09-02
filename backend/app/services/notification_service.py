# app/services/notification_service.py
"""In-app notifications with a provider abstraction.

New providers (email, Telegram, ...) implement `NotificationProvider.send(...)`
and are registered in `get_providers()`. None are required for demo mode.
"""
from __future__ import annotations

from typing import List, Protocol

from sqlalchemy.orm import Session

from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.db import models


class NotificationProvider(Protocol):
    name: str

    def send(self, title: str, message: str, user_email: str) -> bool:
        ...


class InAppStore:
    """Persists the notification in the database (always active)."""
    name = "in_app"

    def send(self, db: Session, user_id: int, ntype: str, title: str, message: str) -> bool:
        db.add(
            models.Notification(
                user_id=user_id,
                type=ntype,
                title=title,
                message=message,
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            return False
        return True


class FCMProvider:
    """Sends push notifications via Firebase Cloud Messaging when configured."""
    name = "fcm"

    def send(self, title: str, message: str, user_email: str, db: Session = None, user_id: int = None) -> bool:
        if db is None or user_id is None:
            return False
        try:
            from app.services.fcm_service import send_push_to_tokens

            tokens = [
                d.token
                for d in db.query(models.DeviceToken)
                .filter(
                    models.DeviceToken.user_id == user_id,
                    models.DeviceToken.is_active == True,
                )
                .all()
            ]
            if not tokens:
                return False
            result = send_push_to_tokens(tokens, title, message, {"type": "notification"})
            return result["sent"] > 0
        except Exception:
            return False


class TelegramProvider:
    """Sends a Telegram message when TELEGRAM_BOT_TOKEN and CHAT_ID are set."""
    name = "telegram"

    def send(self, title: str, message: str, user_email: str) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False
        try:
            import requests

            text = f"*{title}*\n{message}"
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=5,
            )
            return resp.ok
        except Exception:
            return False


class EmailProvider:
    """Placeholder for a future email provider (e.g. Resend/SendGrid)."""
    name = "email"

    def send(self, title: str, message: str, user_email: str) -> bool:
        return False


def get_providers() -> List:
    return [TelegramProvider(), FCMProvider(), EmailProvider()]


def create_notification(
    db: Session,
    user_id: int,
    ntype: str,
    title: str,
    message: str,
    user_email: str = "",
) -> models.Notification:
    """Create an in-app notification and fan out to configured providers."""
    in_app = InAppStore()
    in_app.send(db, user_id, ntype, title, message)

    for provider in get_providers():
        try:
            if provider.name == "fcm":
                provider.send(title, message, user_email, db=db, user_id=user_id)
            else:
                provider.send(title, message, user_email)
        except Exception:
            continue

    notification = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.id.desc())
        .first()
    )
    return notification or models.Notification(
        id=0,
        user_id=user_id,
        type=ntype,
        title=title,
        message=message,
        is_read=False,
    )