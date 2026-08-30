# app/api/routes/auth.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    generate_webhook_secret,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.db import models
from app.db.schemas import AuthResponse, UserLogin, UserOut, UserSignup

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: UserSignup, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = models.User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name.strip() or "Trader",
        plan=models.Plan.FREE.value,
        webhook_secret=generate_webhook_secret(),
    )
    db.add(user)
    db.flush()
    db.add(
        models.Subscription(
            user_id=user.id,
            plan=models.Plan.FREE.value,
            status=models.SubscriptionStatus.TRIAL.value,
        )
    )
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/logout")
def logout(user: models.User = Depends(get_current_user)):
    return {"message": "Logged out."}


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/demo", response_model=AuthResponse)
def demo_login(db: Session = Depends(get_db)):
    """One-click demo. Creates (or reuses) a seeded demo user."""
    from app.db.seed import ensure_demo_user

    user = ensure_demo_user()
    if user is None:
        raise HTTPException(status_code=500, detail="Could not prepare the demo workspace.")
    strategies = (
        db.query(models.Strategy)
        .filter(models.Strategy.user_id == user.id, models.Strategy.is_demo.is_(True))
        .count()
    )
    if strategies == 0:
        from app.db.seed import seed_demo_data
        import threading

        threading.Thread(target=seed_demo_data, daemon=True).start()

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))