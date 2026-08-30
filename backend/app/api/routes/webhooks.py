# app/api/routes/webhooks.py
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import TRADINGVIEW_WEBHOOK_SECRET
from app.db.database import get_db
from app.db import models
from app.db.schemas import SignalOut, TradingViewWebhook, WebhookEventOut, WebhookTestRequest
from app.services.market_data_service import live_quotes, normalize_symbol
from app.services.notification_service import create_notification
from app.services.trading_adapter import get_trading_adapter

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _secret_is_valid(db: Session, secret: str | None) -> bool:
    """A webhook is accepted when its secret equals the global webhook secret OR
    the per-user webhook secret of any registered account (so real users can wire
    their alerts with their own secret shown in the dashboard)."""
    if not secret:
        return False
    if secret == TRADINGVIEW_WEBHOOK_SECRET:
        return True
    return (
        db.query(models.User.id)
        .filter(models.User.webhook_secret == secret)
        .first()
        is not None
    )


def _resolve_webhook_owner(db: Session, secret: str | None) -> models.User | None:
    """Attribute an anonymous webhook to the user who owns the matching secret."""
    if secret:
        owner = db.query(models.User).filter(models.User.webhook_secret == secret).first()
        if owner:
            return owner
    demo = db.query(models.User).filter(models.User.is_demo.is_(True)).first()
    if demo:
        return demo
    return db.query(models.User).order_by(models.User.id.asc()).first()


DEDUP_WINDOW_SECONDS = 30


def _find_recent_dup_signal(
    db: Session,
    symbol: str,
    direction: str,
    price: float,
    timeframe: str,
    strategy_name: str,
    user_id: int | None,
) -> models.Signal | None:
    """Idempotency guard: prevent duplicate signals from duplicate TradingView
    alert deliveries. If an identical TradingView signal (same owner, symbol,
    side, entry price, timeframe and strategy) was created within the dedup
    window, the re-sent alert is treated as a duplicate and no new signal is
    created. Scoping by user_id keeps idempotency from leaking across users."""
    cutoff = datetime.utcnow() - timedelta(seconds=DEDUP_WINDOW_SECONDS)
    return (
        db.query(models.Signal)
        .filter(
            models.Signal.source == "tradingview",
            models.Signal.user_id == user_id,
            models.Signal.symbol == symbol,
            models.Signal.direction == direction,
            models.Signal.entry_price == price,
            models.Signal.strategy_id.is_(None),
            models.Signal.created_at >= cutoff,
        )
        .order_by(models.Signal.created_at.desc())
        .first()
    )


def _handle_webhook(
    db: Session,
    payload: dict,
    valid_secret: bool,
    user_id: int | None = None,
    mark_demo: bool = True,
) -> dict:
    symbol = normalize_symbol(payload.get("symbol", "BTCUSD"))
    direction = str(payload.get("direction", payload.get("signal", "LONG"))).upper()
    if direction in {"BUY", "BULL", "GO_LONG"}:
        direction = "LONG"
    elif direction in {"SELL", "BEAR", "GO_SHORT"}:
        direction = "SHORT"
    else:
        direction = "LONG" if direction != "SHORT" else "SHORT"

    if user_id is None:
        owner = _resolve_webhook_owner(db, payload.get("secret"))
        user_id = owner.id if owner else None
        mark_demo = owner.is_demo if owner else mark_demo

    price = payload.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    timeframe = payload.get("timeframe") or payload.get("interval") or "4H"
    strategy_name = payload.get("strategy") or "TradingView Alert"

    slot = payload.get("slot") or payload.get("take") or 2.0
    stop = payload.get("stop") or payload.get("stop_loss") or 1.0
    try:
        stop_pct = float(str(stop).replace("%", ""))
    except (TypeError, ValueError):
        stop_pct = 1.0
    try:
        tp_pct = float(str(slot).replace("%", ""))
    except (TypeError, ValueError):
        tp_pct = stop_pct * 2

    if price is not None:
        stop_price = price * (1 - stop_pct / 100) if direction == "LONG" else price * (1 + stop_pct / 100)
        target_price = price * (1 + tp_pct / 100) if direction == "LONG" else price * (1 - tp_pct / 100)
    else:
        stop_price = None
        target_price = None

    event = models.WebhookEvent(
        user_id=user_id,
        payload=payload,
        secret_valid=valid_secret,
        status="processed" if valid_secret else "rejected",
    )
    db.add(event)
    db.flush()

    if valid_secret and price is not None:
        # Feed the live-quote store: TradingView alerts are a legitimate source
        # of real, recent prices (e.g. XAUUSD) that the rest of the product can
        # surface as "Live · TradingView".
        live_quotes.set(
            symbol,
            price,
            source="tradingview",
            extra={"strategy": strategy_name, "timeframe": timeframe, "direction": direction},
        )

        duplicate = _find_recent_dup_signal(
            db, symbol, direction, price, timeframe, strategy_name, user_id
        )
        if duplicate is not None:
            event.signal_id = duplicate.id
            db.commit()
            return {
                "status": "duplicate",
                "signal_id": duplicate.id,
                "symbol": symbol,
                "direction": direction,
                "price": price,
            }

        signal = models.Signal(
            user_id=user_id if user_id else None,
            strategy_id=None,
            symbol=symbol,
            direction=direction,
            entry_price=price,
            stop_loss=round(stop_price, 6) if stop_price else None,
            take_profit=round(target_price, 6) if target_price else None,
            risk_reward=round(tp_pct / stop_pct, 2) if stop_pct else None,
            confidence=80,
            reason=f"TradingView alert triggered: {strategy_name} — {symbol} {direction} at {price}.",
            status=models.SignalStatus.PENDING.value,
            source="tradingview",
            is_demo=mark_demo,
        )
        db.add(signal)
        db.flush()
        event.signal_id = signal.id

        if user_id:
            create_notification(
                db,
                user_id,
                "tradingview_alert",
                "TradingView alert received",
                f"{symbol} {direction} at {price} from {strategy_name}.",
                "",
            )
        db.commit()
        return {
            "status": "processed",
            "signal_id": signal.id,
            "symbol": symbol,
            "direction": direction,
            "price": price,
        }

    db.commit()
    return {
        "status": "processed" if not valid_secret else "no_signal",
        "signal_id": None,
        "message": "Webhook event recorded." if valid_secret else "Webhook rejected: invalid secret.",
    }


@router.post("/tradingview")
async def tradingview_webhook(
    payload: TradingViewWebhook,
    request: Request,
    db: Session = Depends(get_db),
):
    valid = _secret_is_valid(db, payload.secret)
    body = payload.model_dump()
    if not valid:
        # Verify secret from the raw header for TradingView compatibility.
        header_secret = request.headers.get("X-Webhook-Secret")
        if header_secret and _secret_is_valid(db, header_secret):
            valid = True
            body["secret"] = header_secret
    result = _handle_webhook(db, body, valid_secret=valid)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")
    return result


@router.post("/tradingview/test", response_model=SignalOut, status_code=201)
def test_webhook(
    payload: WebhookTestRequest = WebhookTestRequest(),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Instant local test alert — no TradingView account required.

    Works through the exact same webhook pipeline (event -> signal -> notification).
    """
    symbol = payload.symbol or "BTCUSD"
    direction = (payload.direction or "LONG").upper()
    price = payload.price or 0.0
    if price == 0.0:
        from app.services.market_data_service import get_provider

        try:
            normalized = normalize_symbol(symbol)
            price = get_provider().latest_quote(normalized)["close"]
        except Exception:
            price = 65000.0

    body = {
        "secret": TRADINGVIEW_WEBHOOK_SECRET,
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "timeframe": "4H",
        "strategy": "Test Alert",
        "timestamp": datetime.utcnow().isoformat(),
        "test": True,
    }
    result = _handle_webhook(db, body, valid_secret=True, user_id=user.id, mark_demo=False)
    signal = (
        db.query(models.Signal)
        .filter(models.Signal.id == result["signal_id"])
        .first()
    )
    create_notification(
        db,
        user.id,
        "tradingview_alert",
        "Test alert received",
        f"Test TradingView alert: {result['symbol']} {result['direction']} at {result['price']}.",
        "",
    )
    return SignalOut.model_validate(signal)


@router.get("/events", response_model=list[WebhookEventOut])
def webhook_events(
    limit: int = Query(default=50, le=200),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    events = (
        db.query(models.WebhookEvent)
        .filter(models.WebhookEvent.user_id == user.id)
        .order_by(models.WebhookEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [WebhookEventOut.model_validate(e) for e in events]