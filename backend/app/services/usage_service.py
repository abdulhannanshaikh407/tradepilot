# app/services/usage_service.py
"""Plan definitions and usage-limit enforcement.

Plans are ready for a future Stripe integration; usage is tracked per user per
feature per calendar period and enforced on the backend.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.db import models

PLAN_LIMITS: Dict[str, Dict[str, int]] = {
    "FREE": {
        "analyses_per_day": 3,
        "backtests_per_day": 25,
        "signals_per_day": 20,
        "webhooks_per_day": 30,
        "strategies": 50,
    },
    "PRO": {
        "analyses_per_day": 100,
        "backtests_per_day": 500,
        "signals_per_day": 1000,
        "webhooks_per_day": 5000,
        "strategies": 10000,
    },
    "BUSINESS": {
        "analyses_per_day": 5000,
        "backtests_per_day": 5000,
        "signals_per_day": 50000,
        "webhooks_per_day": 50000,
        "strategies": 500000,
    },
}

PLAN_DETAILS = {
    "FREE": {
        "label": "Free",
        "price": 0,
        "features": [
            "3 AI strategy analyses / month",
            "Basic backtesting",
            "Demo signals",
            "In-app notifications",
        ],
    },
    "PRO": {
        "label": "Pro",
        "price": 29,
        "features": [
            "Unlimited AI analyses",
            "Advanced backtesting",
            "TradingView alerts",
            "Performance analytics",
            "Paper trading",
        ],
    },
    "BUSINESS": {
        "label": "Business",
        "price": 99,
        "features": [
            "Everything in Pro",
            "Higher usage limits",
            "API access",
            "Team functionality",
            "Custom integrations",
        ],
    },
}


def current_period() -> str:
    return date.today().isoformat()


def get_usage(db: Session, user_id: int, period: str | None = None) -> Dict[str, int]:
    period = period or current_period()
    records = (
        db.query(models.UsageRecord)
        .filter(models.UsageRecord.user_id == user_id, models.UsageRecord.period == period)
        .all()
    )
    usage: Dict[str, int] = {}
    for record in records:
        usage[record.feature] = record.count
    return usage


def _record_count(db: Session, user_id: int, feature: str, delta: int = 1) -> int:
    period = current_period()
    record = (
        db.query(models.UsageRecord)
        .filter(
            models.UsageRecord.user_id == user_id,
            models.UsageRecord.feature == feature,
            models.UsageRecord.period == period,
        )
        .first()
    )
    if record is None:
        record = models.UsageRecord(user_id=user_id, feature=feature, period=period, count=0)
        db.add(record)
        db.flush()
    record.count = (record.count or 0) + delta
    db.commit()
    return record.count


def check_and_increment(db: Session, user: models.User, feature: str, amount: int = 1) -> tuple[bool, int]:
    """Increment usage, returning (allowed, current_count)."""
    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["FREE"])
    limit_key = {
        "analysis": "analyses_per_day",
        "analyses": "analyses_per_day",
        "backtest": "backtests_per_day",
        "backtests": "backtests_per_day",
        "signal": "signals_per_day",
        "signals": "signals_per_day",
        "webhook": "webhooks_per_day",
        "webhooks": "webhooks_per_day",
    }.get(feature, feature)

    usage = get_usage(db, user.id)
    current = usage.get(feature, 0)
    limit = limits.get(feature, limits.get(limit_key, 9999))
    if current + amount > limit:
        return False, current
    new_count = _record_count(db, user.id, feature, amount)
    return True, new_count


def usage_left(db: Session, user: models.User, feature: str) -> int:
    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["FREE"])
    usage = get_usage(db, user.id)
    current = usage.get(feature, 0)
    limit = limits.get(feature, limits.get({
        "analysis": "analyses_per_day",
        "backtests": "backtests_per_day",
        "signals": "signals_per_day",
        "webhooks": "webhooks_per_day",
    }.get(feature, feature), 9999))
    return max(0, limit - current)


def plans_payload() -> Dict:
    return PLAN_DETAILS