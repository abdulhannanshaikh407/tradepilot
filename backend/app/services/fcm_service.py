# app/services/fcm_service.py
"""Firebase Cloud Messaging push notification service.

Provides functions to:
- Register device tokens (mobile + web)
- Send push notifications to individual users or specific devices
- Send push notifications to all of a user's registered devices

Requires FIREBASE_CREDENTIALS_PATH env var pointing to a Firebase service
account JSON file. Falls back gracefully when Firebase is not configured.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import FCM_ENABLED, FIREBASE_CREDENTIALS_PATH

logger = logging.getLogger("tradepilot.fcm")

_firebase_app = None


def _get_firebase_app():
    """Initialize the Firebase Admin SDK lazily."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    if not FCM_ENABLED or not FIREBASE_CREDENTIALS_PATH:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        return _firebase_app
    except Exception as e:
        logger.warning("Failed to initialize Firebase Admin SDK: %s", e)
        _firebase_app = False
        return None


def is_available() -> bool:
    """Check if FCM push notifications are available."""
    return _get_firebase_app() is not None


def send_push_to_token(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> bool:
    """Send a push notification to a single device token.

    Returns True if the message was accepted by FCM, False otherwise.
    """
    app = _get_firebase_app()
    if not app:
        logger.debug("FCM not configured — skipping push to token")
        return False
    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="tradepilot_alerts",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="default",
                        badge=1,
                    )
                ),
            ),
        )
        response = messaging.send(message)
        logger.info("FCM sent to %s: %s", token[:12], response)
        return True
    except Exception as e:
        logger.warning("FCM send failed for token %s: %s", token[:12], e)
        return False


def send_push_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Send a push notification to multiple device tokens.

    Returns a summary dict with success/failure counts.
    """
    app = _get_firebase_app()
    if not app or not tokens:
        return {"sent": 0, "failed": len(tokens)}
    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="tradepilot_alerts",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )
        response = messaging.send_each(message)
        success = response.success_count
        failure = response.failure_count
        logger.info("FCM multicast: %d sent, %d failed", success, failure)
        return {"sent": success, "failed": failure}
    except Exception as e:
        logger.warning("FCM multicast failed: %s", e)
        return {"sent": 0, "failed": len(tokens)}


def send_signal_alert(
    user_tokens: List[str],
    strategy_name: str,
    symbol: str,
    direction: str,
    entry_price: float,
    confidence: Optional[int] = None,
) -> Dict[str, Any]:
    """Send a pre-formatted signal alert push notification."""
    conf_str = f" ({confidence}% confidence)" if confidence else ""
    title = f"🔔 {direction} Signal: {symbol}"
    body = f"Strategy '{strategy_name}' triggered a {direction} entry at ${entry_price:,.2f}{conf_str}"
    data = {
        "type": "signal_alert",
        "symbol": symbol,
        "direction": direction,
        "strategy_name": strategy_name,
        "entry_price": str(entry_price),
    }
    return send_push_to_tokens(user_tokens, title, body, data)


def send_trade_alert(
    user_tokens: List[str],
    strategy_name: str,
    symbol: str,
    direction: str,
    pnl: float,
    status: str,
) -> Dict[str, Any]:
    """Send a trade execution/closure push notification."""
    emoji = "✅" if pnl >= 0 else "❌"
    title = f"{emoji} Trade {status}: {symbol}"
    body = f"'{strategy_name}' {direction} {status} — PnL: ${pnl:+,.2f}"
    data = {
        "type": "trade_alert",
        "symbol": symbol,
        "direction": direction,
        "pnl": str(pnl),
        "status": status,
        "strategy_name": strategy_name,
    }
    return send_push_to_tokens(user_tokens, title, body, data)
