# app/main.py
import asyncio
import logging
import time
from collections import defaultdict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.routes import (
    alert_preferences,
    auth,
    autotrade,
    backtests,
    billing,
    brokers,
    dashboard,
    devices,
    health,
    market,
    notifications,
    performance,
    pinescript,
    push,
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
    WS_HEARTBEAT_INTERVAL,
)
from sqlalchemy import text as sql_text

from app.core.cache import rate_limiter
from app.db.database import Base, engine

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tradepilot")

_WEAK_JWT_SECRETS = {"change-me-in-production", "changeme", "secret", ""}
_WEAK_WEBHOOK_SECRETS = {"tradepilot-webhook-secret", "changeme", "secret", ""}


def _assert_production_secrets() -> None:
    """Refuse to boot in production with default/weak secrets."""
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
    openapi_tags=[
        {"name": "auth", "description": "Signup, login, demo, token refresh"},
        {"name": "market", "description": "Live market data, OHLCV, assets"},
        {"name": "strategies", "description": "Trading strategies"},
        {"name": "signals", "description": "Trading signals"},
        {"name": "webhooks", "description": "TradingView webhook integration"},
        {"name": "brokers", "description": "Broker connections (Alpaca, Binance, OANDA)"},
        {"name": "push", "description": "Web push notifications"},
    ],
)

# OpenAPI security scheme for Bearer token auth
from fastapi.openapi.utils import get_openapi


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=APP_NAME,
        version=APP_VERSION,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your access token from /auth/login or /auth/demo",
        }
    }
    # Apply Bearer auth to all protected endpoints (everything except public ones)
    public_paths = {"/", "/health", "/docs", "/openapi.json", "/auth/login", "/auth/signup", "/auth/demo",
                    "/webhook/tradingview", "/push/vapid-public-key", "/billing/plans", "/youtube/demo-strategies"}
    for path, methods in openapi_schema.get("paths", {}).items():
        # Normalize path: strip trailing slash for comparison
        check_path = path.rstrip("/") or "/"
        if check_path not in public_paths:
            for method in methods:
                if method in ("get", "post", "put", "delete", "patch"):
                    methods[method]["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Dynamic CORS: allow configured origins + any *.vercel.app deployment
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    from fastapi.responses import Response
    origin = request.headers.get("origin", "")
    allowed = CORS_ORIGINS[:]
    # Strict CORS: only allow exact Vercel deployment URL
    VERCEL_ORIGINS = {"https://tradepilot-psi-pearl.vercel.app"}
    if origin in VERCEL_ORIGINS and origin not in allowed:
        allowed.append(origin)
    # Handle preflight
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": origin if origin in allowed else allowed[0],
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600",
        }
        return Response(status_code=204, headers=headers)
    response = await call_next(request)
    if origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# ---- Rate limiting (Redis-backed, per-IP) ----
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 300    # requests per window per IP
RATE_LIMIT_ENABLED = ENVIRONMENT != "test"


@app.middleware("http")
async def rate_limit_log_and_seed(request: Request, call_next):
    # Deferred seeding on first non-health request
    global _seeded
    path = request.url.path
    if not _seeded and path not in ("/health", "/docs", "/openapi", "/redoc"):
        _seeded = True
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            # Run seeding in a thread to avoid blocking the event loop
            # Use a lock to prevent concurrent seeding
            async def _safe_seed():
                try:
                    await asyncio.to_thread(seed.seed_demo_data)
                    logger.info("Demo data seeded successfully")
                except Exception as e:
                    logger.warning("Deferred demo seeding failed (non-critical): %s", e)

            loop.create_task(_safe_seed())
        except Exception:
            logger.exception("Deferred demo seeding failed to start")

    # Rate limit: skip health/docs endpoints and test mode
    client_ip = request.client.host if request.client else "unknown"
    if RATE_LIMIT_ENABLED and not path.startswith("/health") and not path.startswith("/docs") and not path.startswith("/openapi"):
        rate_key = f"rl:{client_ip}"
        if not rate_limiter.is_allowed(rate_key, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        path,
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
app.include_router(pinescript.router)
app.include_router(alert_preferences.router)
app.include_router(devices.router)
app.include_router(brokers.router)
app.include_router(push.router)

# Create tables (dev convenience; production uses Alembic migrations).
Base.metadata.create_all(bind=engine)

# Ensure columns added after initial migration exist (safe for both SQLite and PostgreSQL)
try:
    with engine.connect() as _conn:
        _dialect = engine.dialect.name
        if _dialect == "sqlite":
            _conn.execute(sql_text(
                "ALTER TABLE broker_connections ADD COLUMN account_id VARCHAR"
            ))
        else:
            _conn.execute(sql_text(
                "ALTER TABLE broker_connections ADD COLUMN IF NOT EXISTS account_id VARCHAR"
            ))
        _conn.commit()
except Exception:
    pass  # Column already exists

from app.db import seed  # noqa: E402

demo_user = seed.ensure_demo_user()
if demo_user:
    try:
        from app.db.database import SessionLocal as _SL
        _db = _SL()
        seed.seed_default_strategies_for_user(_db, demo_user)
        _db.close()
    except Exception:
        pass

_seeded = False


# ---- WebSocket connection manager for real-time signal push ----
class ConnectionManager:
    """Manages WebSocket connections per user for real-time signal delivery."""

    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_signal(self, user_id: int, signal_data: dict):
        if user_id in self.active_connections:
            dead = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(signal_data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                try:
                    await ws.close()
                except Exception:
                    pass
                self.active_connections[user_id].remove(ws)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast_signal(self, signal_data: dict):
        for user_id in list(self.active_connections.keys()):
            await self.send_signal(user_id, signal_data)

    def send_signal_sync(self, user_id: int, signal_data: dict):
        """Thread-safe method for background threads to push signals to a specific user.

        The market scanner runs in a background thread and cannot call async
        methods directly. This method schedules the async send on the event loop.
        """
        if self._loop is None or self._loop.is_closed():
            logger.warning("No event loop available for WebSocket push to user %d", user_id)
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.send_signal(user_id, signal_data), self._loop
            )
        except Exception as e:
            logger.warning("WebSocket push failed for user %d: %s", user_id, e)

    def broadcast_signal_sync(self, signal_data: dict):
        """Thread-safe method for background threads to broadcast to all users."""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_signal(signal_data), self._loop
            )
        except Exception as e:
            logger.warning("WebSocket broadcast failed: %s", e)

    def get_connected_count(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())

    def cleanup_stale(self, max_idle_seconds: int = 300):
        """Remove connections that have been idle too long."""
        pass


ws_manager = ConnectionManager()


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for real-time signal streaming.

    Clients connect with: ws://host/ws/signals?token=<jwt>
    After auth, they receive signal events as JSON.
    """
    from app.core.security import decode_access_token
    from app.db.database import SessionLocal

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket, user_id)
    logger.info("WebSocket connected: user=%s", user_id)

    try:
        while True:
            # Server-initiated ping every 30s to detect dead connections
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=WS_HEARTBEAT_INTERVAL)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # No client activity — send server ping
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        ws_manager.disconnect(websocket, user_id)
        logger.info("WebSocket disconnected: user=%s", user_id)


@app.on_event("startup")
async def start_bg() -> None:
    """Start the real-time feed, market scanner, and auto-trade engine."""
    from app.core.config import AUTOTRADE_ENABLED, AUTOTRADE_INTERVAL

    # --- Store event loop in ws_manager so background threads can push signals ---
    ws_manager.set_loop(asyncio.get_running_loop())
    logger.info("Event loop stored in WebSocket manager")

    # --- Real-time price feed (Binance WebSocket) ---
    try:
        from app.services.realtime_feed import feed as realtime_feed
        realtime_feed.start()
        logger.info("Real-time Binance feed started")
    except Exception:
        logger.exception("Failed to start real-time feed")

    # --- Forex/Commodity feed (Biquote polling for EUR/USD, GBP/USD, XAUUSD, etc.) ---
    try:
        from app.services.realtime_feed import forex_feed
        forex_feed.start()
        logger.info("Forex/Commodity feed started (Biquote polling)")
    except Exception:
        logger.exception("Failed to start forex feed")

    # --- Market scanner (evaluates strategies on every price tick) ---
    try:
        from app.services.market_scanner import scanner as market_scanner
        # Use send_signal_sync so the background scanner thread can push to a specific user
        market_scanner.set_ws_callback(ws_manager.send_signal_sync)
        market_scanner.start()
        logger.info("Market scanner started — watching for live signals")
    except Exception:
        logger.exception("Failed to start market scanner")

    # --- Register forex feed with market scanner ---
    try:
        from app.services.realtime_feed import forex_feed
        forex_feed.on_price_update(market_scanner._on_price_update)
        logger.info("Forex feed registered with market scanner")
    except Exception:
        logger.exception("Failed to register forex feed with scanner")

    # --- Auto-trade monitor loop (existing) ---
    if AUTOTRADE_ENABLED and AUTOTRADE_INTERVAL >= 30:

        async def monitor_loop() -> None:
            await asyncio.sleep(5)
            from app.services import autotrade
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

    # Log system status
    logger.info("TradePilot AI started | env=%s | real-time feed + scanner active", ENVIRONMENT)


@app.get("/")
async def root():
    return {
        "message": f"{APP_NAME} API is running",
        "docs": "/docs",
        "version": APP_VERSION,
    }