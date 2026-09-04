# app/api/routes/push.py
"""Web Push notification endpoints.

Handles VAPID key generation, push subscription storage, and sending
web push notifications. Completely free — no Firebase required.
"""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models

logger = logging.getLogger("tradepilot.push")

router = APIRouter(prefix="/push", tags=["push"])

# In-memory VAPID keys (generated once, persisted in env or file)
_vapid_public_key: str = ""
_vapid_private_key: str = ""


def _get_or_generate_vapid_keys() -> tuple[str, str]:
    """Get or generate VAPID key pair. Uses py_vapid."""
    global _vapid_public_key, _vapid_private_key
    if _vapid_public_key and _vapid_private_key:
        return _vapid_public_key, _vapid_private_key

    import base64
    import os

    pub_file = os.path.join(os.path.dirname(__file__), "../../../.vapid_public.key")
    priv_file = os.path.join(os.path.dirname(__file__), "../../../.vapid_private.key")

    try:
        if os.path.exists(pub_file) and os.path.exists(priv_file):
            with open(pub_file) as f:
                _vapid_public_key = f.read().strip()
            with open(priv_file) as f:
                _vapid_private_key = f.read().strip()
            if _vapid_public_key and _vapid_private_key:
                return _vapid_public_key, _vapid_private_key
    except Exception:
        pass

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        # Generate EC P-256 key pair (required for Web Push VAPID)
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        # Extract raw public key bytes (65 bytes uncompressed point)
        pub_raw = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        # Base64url encode (no padding) — this is the VAPID public key
        _vapid_public_key = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode("ascii")

        # Extract raw private key bytes (32 bytes scalar)
        priv_raw = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        # For pywebpush, we need the raw 32-byte scalar
        priv_numbers = private_key.private_numbers()
        priv_scalar = priv_numbers.private_value.to_bytes(32, byteorder="big")
        _vapid_private_key = base64.urlsafe_b64encode(priv_scalar).rstrip(b"=").decode("ascii")

        # Persist for consistency across restarts
        try:
            with open(pub_file, "w") as f:
                f.write(_vapid_public_key)
            with open(priv_file, "w") as f:
                f.write(_vapid_private_key)
        except Exception:
            pass

        return _vapid_public_key, _vapid_private_key
    except ImportError:
        logger.warning("cryptography not installed — VAPID keys unavailable")
        raise RuntimeError("VAPID keys not available. Install: pip install cryptography")


class PushSubscriptionRequest(BaseModel):
    subscription: dict  # {endpoint, keys: {auth, p256dh}}


@router.get("/vapid-public-key")
def get_vapid_public_key():
    """Return the VAPID public key for the frontend to use."""
    pub_key, _ = _get_or_generate_vapid_keys()
    return {"publicKey": pub_key}


@router.post("/subscribe")
def subscribe_push(
    payload: PushSubscriptionRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store a web push subscription for the user."""
    endpoint = payload.subscription.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Invalid subscription: missing endpoint")

    # Store as device token with platform=web
    token_str = json.dumps(payload.subscription)
    existing = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.token == token_str)
        .first()
    )
    if existing:
        existing.user_id = user.id
        existing.is_active = True
        db.commit()
        return {"message": "Subscription updated.", "id": existing.id}

    device = models.DeviceToken(
        user_id=user.id,
        token=token_str,
        platform="web",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {"message": "Push subscription saved.", "id": device.id}


@router.delete("/unsubscribe")
def unsubscribe_push(
    endpoint: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a web push subscription."""
    # Find by matching endpoint in the token JSON
    devices = (
        db.query(models.DeviceToken)
        .filter(
            models.DeviceToken.user_id == user.id,
            models.DeviceToken.platform == "web",
            models.DeviceToken.is_active == True,
        )
        .all()
    )
    for d in devices:
        try:
            sub = json.loads(d.token)
            if sub.get("endpoint") == endpoint:
                d.is_active = False
        except (json.JSONDecodeError, TypeError):
            continue
    db.commit()
    return {"message": "Unsubscribed."}


def send_web_push(subscription_data: dict, title: str, body: str, data: dict = None) -> bool:
    """Send a web push notification to a browser subscription."""
    try:
        _, priv_key_str = _get_or_generate_vapid_keys()

        endpoint = subscription_data.get("endpoint")
        keys = subscription_data.get("keys", {})
        auth = keys.get("auth")
        p256dh = keys.get("p256dh")

        if not endpoint or not auth or not p256dh:
            return False

        # Build payload
        payload = json.dumps({
            "title": title,
            "body": body,
            "data": data or {},
            "tag": "tradepilot",
        })

        # Send via pywebpush with VAPID signing
        try:
            from pywebpush import webpush
            subscription_info = {
                "endpoint": endpoint,
                "keys": {"auth": auth, "p256dh": p256dh},
            }
            vapid_claims = {
                "sub": "mailto:tradepilot@app.com",
            }
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=priv_key_str,
                vapid_claims=vapid_claims,
            )
            return True
        except ImportError:
            logger.warning("pywebpush not installed — web push requires VAPID signing. Install: pip install pywebpush")
            return False

    except Exception as e:
        logger.warning("Web push failed: %s", e)
        return False


def send_web_push_to_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    data: dict = None,
) -> dict:
    """Send web push to all of a user's browser subscriptions."""
    devices = (
        db.query(models.DeviceToken)
        .filter(
            models.DeviceToken.user_id == user_id,
            models.DeviceToken.platform == "web",
            models.DeviceToken.is_active == True,
        )
        .all()
    )
    sent = 0
    failed = 0
    for d in devices:
        try:
            sub = json.loads(d.token)
            if send_web_push(sub, title, body, data):
                sent += 1
            else:
                failed += 1
        except (json.JSONDecodeError, TypeError):
            failed += 1
    return {"sent": sent, "failed": failed}
