# app/main.py
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    auth,
    autotrade,
    backtests,
    billing,
    dashboard,
    health,
    market,
    notifications,
    performance,
    settings,
    signals,
    strategies,
    webhooks,
    youtube,
)
from app.core.config import (
    APP_NAME,
    APP_VERSION,
    CORS_ORIGINS,
    DEBUG,
    ENVIRONMENT,
    JWT_SECRET,
    TRADINGVIEW_WEBHOOK_SECRET,
)
from app.db.database import Base, engine

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tradepilot")

_WEAK_JWT_SECRETS = {"change-me-in-production", "changeme", "secret", ""}
_WEAK_WEBHOOK_SECRETS = {"tradepilot-webhook-secret", "changeme", "secret", ""}


def _assert_production_secrets() -> None:
    """Refuse to boot in production with default/weak secrets.

    A production deployment that forgets to set its secrets would otherwise
    silently ship forgeable JWTs and an open webhook that any caller could
    authenticate against.
    """
    if ENVIRONMENT != "production":
        return
    problems = []
    if JWT_SECRET in _WEAK_JWT_SECRETS or len(JWT_SECRET) < 32:
        problems.append("JWT_SECRET")
    if TRADINGVIEW_WEBHOOK_SECRET in _WEAK_WEBHOOK_SECRETS or len(TRADINGVIEW_WEBHOOK_SECRET) < 16:
        problems.append("TRADINGVIEW_WEBHOOK_SECRET")
    if problems:
        raise RuntimeError(
            "Refusing to start in production: set strong values for "
            + ", ".join(problems)
            + " (see backend/.env.example)."
        )


_assert_production_secrets()

app = FastAPI(
    title=APP_NAME,
    description="AI trading strategy research, backtesting and signal intelligence platform.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


# Register routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(youtube.router)
app.include_router(strategies.router)
app.include_router(signals.router)
app.include_router(backtests.router)
app.include_router(performance.router)
app.include_router(dashboard.router)
app.include_router(webhooks.router)
app.include_router(notifications.router)
app.include_router(billing.router)
app.include_router(settings.router)
app.include_router(market.router)
app.include_router(autotrade.router)

# Create tables (dev convenience; production uses Alembic migrations).
Base.metadata.create_all(bind=engine)

from app.db import seed  # noqa: E402

seed.ensure_demo_user()


@app.on_event("startup")
async def seed_and_start_bg() -> None:
    """Seed the demo workspace and start the auto-trade monitor loop."""
    import asyncio

    from app.core.config import AUTOTRADE_ENABLED, AUTOTRADE_INTERVAL
    from app.services import autotrade

    asyncio.create_task(asyncio.to_thread(seed.seed_demo_data))

    if AUTOTRADE_ENABLED and AUTOTRADE_INTERVAL >= 30:

        async def monitor_loop() -> None:
            await asyncio.sleep(2)
            autotrade.STATE["running"] = True
            logger.info("Auto-trade monitor started (interval %ss)", AUTOTRADE_INTERVAL)
            try:
                while True:
                    try:
                        await asyncio.to_thread(autotrade.run_once)
                    except Exception:
                        logger.exception("auto-trade loop iteration failed")
                    await asyncio.sleep(AUTOTRADE_INTERVAL)
            finally:
                autotrade.STATE["running"] = False

        asyncio.create_task(monitor_loop())
    else:
        logger.info("Auto-trade monitor disabled (AUTOTRADE_ENABLED=%s)", AUTOTRADE_ENABLED)


@app.get("/")
async def root():
    return {
        "message": f"{APP_NAME} API is running",
        "docs": "/docs",
        "version": APP_VERSION,
    }