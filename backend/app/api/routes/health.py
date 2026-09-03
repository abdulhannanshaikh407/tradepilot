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

    # Check real-time feed status
    realtime_status = "not_started"
    realtime_symbols = 0
    try:
        from app.services.realtime_feed import feed as realtime_feed
        if realtime_feed.is_connected():
            realtime_status = "connected"
            realtime_symbols = len(realtime_feed.bar_store.get_all_symbols())
        elif realtime_feed._running:
            realtime_status = "starting"
        else:
            realtime_status = "stopped"
    except Exception:
        realtime_status = "error"

    # Check scanner status
    scanner_status = "not_started"
    try:
        from app.services.market_scanner import scanner as market_scanner
        if market_scanner._running:
            scanner_status = "active"
        else:
            scanner_status = "stopped"
    except Exception:
        scanner_status = "error"

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "database_type": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql",
        "ai_configured": bool(OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here"),
        "realtime_feed": realtime_status,
        "realtime_symbols": realtime_symbols,
        "market_scanner": scanner_status,
    }