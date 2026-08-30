"""Recorded local tests for the TradingView alert webhook.

These run against the real FastAPI application via the TestClient and do NOT
require any TradingView credentials. They exercise the exact contract of the
public alert endpoint:

    POST /webhook/tradingview

Supported JSON payload (TradingViewWebhook schema):
    secret      (str,  optional) - global TRADINGVIEW_WEBHOOK_SECRET or a user's
                                   per-user webhook_secret
    symbol      (str,  required) - e.g. "BTCUSD", "BTC/USD", "ETH/USD", "NAS100"
    direction   (str,  optional) - "LONG"/"SHORT" (also BUY/SELL/BULL/BEAR)
    price       (float,optional) - if present a Signal is created
    timeframe   (str,  optional) - e.g. "1H", "4H", "1D"
    strategy    (str,  optional)
    timestamp   (str,  optional)

Authentication: the secret may be supplied in the body OR via the
X-Webhook-Secret header. Invalid/missing secrets are rejected with HTTP 401.
"""
import time

from conftest import auth


def _signup(client, email: str) -> str:
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "TV Tester"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["access_token"]


def _user_secret(client, token: str) -> str:
    info = client.get("/dashboard/tradingview-info", headers=auth(token)).json()
    return info["user_secret"]


def test_valid_payload_success_and_field_parsing(client):
    token = _signup(client, "tv-valid@test.dev")
    secret = _user_secret(client, token)
    response = client.post(
        "/webhook/tradingview",
        json={
            "secret": secret,
            "symbol": "BTC/USD",
            "direction": "BUY",  # must normalize to LONG
            "price": 61000.0,
            "timeframe": "1H",
            "strategy": "RSI Momentum",
            "timestamp": "2026-08-28T12:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "processed"
    assert body["signal_id"] is not None
    assert body["symbol"] == "BTC/USD"
    assert body["direction"] == "LONG"
    assert body["price"] == 61000.0

    # Signal persisted with parsed fields.
    signal = client.get(f"/signals/{body['signal_id']}", headers=auth(token)).json()
    assert signal["symbol"] == "BTC/USD"
    assert signal["direction"] == "LONG"
    assert signal["entry_price"] == 61000.0
    assert signal["source"] == "tradingview"

    # Webhook event persisted and linked (timeframe lives on the event payload).
    events = client.get("/webhook/events", headers=auth(token)).json()
    matched = [ev for ev in events if ev["signal_id"] == body["signal_id"]]
    assert matched
    assert matched[0]["payload"].get("timeframe") == "1H"


def test_price_optional_no_signal(client):
    """A valid webhook without a price is recorded but produces no signal."""
    response = client.post(
        "/webhook/tradingview",
        json={"secret": "test-webhook-secret", "symbol": "EURUSD", "direction": "LONG"},
    )
    # Global secret is valid; no price => recorded but no signal (status no_signal).
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["signal_id"] is None
    assert body["status"] == "no_signal"


def test_malformed_payload_rejected(client):
    """Missing required 'symbol' is rejected with 422, not a 500."""
    response = client.post(
        "/webhook/tradingview",
        json={"secret": "test-webhook-secret", "direction": "LONG"},
    )
    assert response.status_code == 422, response.text


def test_invalid_secret_rejected(client):
    response = client.post(
        "/webhook/tradingview",
        json={"secret": "totally-wrong", "symbol": "BTCUSD", "price": 1.0},
    )
    assert response.status_code == 401, response.text


def test_missing_secret_rejected(client):
    response = client.post(
        "/webhook/tradingview",
        json={"symbol": "BTCUSD", "price": 1.0},
    )
    assert response.status_code == 401, response.text


def test_header_secret_accepted(client):
    """TradingView can send the secret via the X-Webhook-Secret header."""
    response = client.post(
        "/webhook/tradingview",
        json={"symbol": "SOL/USD", "direction": "LONG", "price": 150.0},
        headers={"X-Webhook-Secret": "test-webhook-secret"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["signal_id"] is not None


def test_idempotency_duplicate_alert_no_dup_signal(client):
    """Re-sending the same alert within the dedup window must NOT create a
    duplicate signal (idempotency protection)."""
    token = _signup(client, "tv-dup@test.dev")
    secret = _user_secret(client, token)
    payload = {
        "secret": secret,
        "symbol": "NAS100",
        "direction": "SHORT",
        "price": 19000.0,
        "timeframe": "4H",
        "strategy": "Breakout",
    }

    first = client.post("/webhook/tradingview", json=payload)
    assert first.status_code == 200
    first_id = first.json()["signal_id"]

    # Deliver identical alert again immediately.
    second = client.post("/webhook/tradingview", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "duplicate"
    assert body["signal_id"] == first_id

    # Only one signal exists with that entry price.
    signals = client.get("/signals?source=tradingview", headers=auth(token)).json()
    same_price = [s for s in signals if s["entry_price"] == 19000.0]
    assert len(same_price) == 1


def test_idempotency_not_triggered_by_different_alert(client):
    """A different alert on the same symbol must still produce a new signal."""
    token = _signup(client, "tv-diff@test.dev")
    secret = _user_secret(client, token)
    base = {"secret": secret, "symbol": "GOLD", "timeframe": "1D"}

    r1 = client.post("/webhook/tradingview", json={**base, "direction": "LONG", "price": 2400.0})
    assert r1.status_code == 200

    r2 = client.post("/webhook/tradingview", json={**base, "direction": "SHORT", "price": 2450.0})
    assert r2.status_code == 200
    assert r2.json()["status"] != "duplicate"
    assert r2.json()["signal_id"] != r1.json()["signal_id"]


def test_self_test_endpoint_requires_auth(client):
    response = client.post("/webhook/tradingview/test")
    assert response.status_code in (401, 422)
