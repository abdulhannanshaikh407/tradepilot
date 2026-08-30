# app/api/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import APP_NAME, APP_VERSION, DATABASE_URL, OPENAI_API_KEY
from app.db.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "database_type": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql",
        "ai_configured": bool(OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here"),
    }