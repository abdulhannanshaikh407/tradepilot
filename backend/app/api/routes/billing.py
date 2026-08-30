# app/api/routes/billing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import PlanInfo
from app.services import usage_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
def plans():
    return {"plans": usage_service.plans_payload()}


@router.get("/current", response_model=PlanInfo)
def current_plan(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    usage = usage_service.get_usage(db, user.id)
    limits = usage_service.PLAN_LIMITS.get(user.plan, usage_service.PLAN_LIMITS["FREE"])
    return PlanInfo(plan=user.plan, limits=limits, usage=usage)


@router.post("/select-plan")
def select_plan(
    plan: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = plan.upper()
    valid = {p.value for p in models.Plan}
    if plan not in valid:
        raise HTTPException(status_code=400, detail="Invalid plan.")
    user.plan = plan
    subscription = (
        db.query(models.Subscription).filter(models.Subscription.user_id == user.id).first()
    )
    if subscription:
        subscription.plan = plan
        subscription.status = models.SubscriptionStatus.TRIAL.value
    else:
        db.add(
            models.Subscription(
                user_id=user.id,
                plan=plan,
                status=models.SubscriptionStatus.TRIAL.value,
            )
        )
    db.commit()
    label = usage_service.PLAN_DETAILS.get(plan, {}).get("label", plan)
    return {"message": f"Switched to the {label} plan.", "plan": plan}