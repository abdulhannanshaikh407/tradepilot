from conftest import auth


def _signup(client, email: str):
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Webhook Tester"},
    )
    return response.json()["access_token"]


def test_test_alert_creates_signal(client):
    token = _signup(client, "hook@test.dev")
    response = client.post(
        "/webhook/tradingview/test",
        json={"symbol": "BTC/USD", "direction": "LONG", "price": 60000.0},
        headers=auth(token),
    )
    assert response.status_code == 201
    signal = response.json()
    assert signal["symbol"] == "BTC/USD"
    assert signal["direction"] == "LONG"
    assert signal["status"] in ("PENDING", "ACTIVE")
    assert signal["source"] in ("tradingview", "webhook")

    events = client.get("/webhook/events", headers=auth(token)).json()
    assert any(ev["signal_id"] == signal["id"] for ev in events)


def test_anonymous_webhook_valid_secret_routes_to_demo(client):
    response = client.post(
        "/webhook/tradingview",
        json={"secret": "test-webhook-secret", "symbol": "BTCUSD", "direction": "LONG", "price": 60000.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["signal_id"] is not None

    # The demo user should own that signal.
    demo = client.post("/auth/demo")
    demo_token = demo.json()["access_token"]
    signals = client.get("/signals?source=tradingview", headers=auth(demo_token)).json()
    assert any(s["id"] == body["signal_id"] for s in signals)


def test_anonymous_webhook_invalid_secret_rejected(client):
    response = client.post(
        "/webhook/tradingview",
        json={"secret": "wrong-secret", "symbol": "BTCUSD", "direction": "LONG", "price": 1.0},
    )
    assert response.status_code == 401


def test_per_user_webhook_secret_accepted_and_attributed(client):
    """A real user configuring TradingView with their own dashboard secret works."""
    token = _signup(client, "ownsecret@test.dev")
    headers = auth(token)

    info = client.get("/dashboard/tradingview-info", headers=headers).json()
    user_secret = info["user_secret"]
    assert user_secret

    # Global secret must never equal a per-user secret, and vice-versa.
    assert user_secret != info["global_secret"]

    # Anonymous webhook using the user's OWN secret is accepted (P0 fix).
    response = client.post(
        "/webhook/tradingview",
        json={"secret": user_secret, "symbol": "SOL/USD", "direction": "LONG", "price": 150.0},
    )
    assert response.status_code == 200, response.text
    signal_id = response.json()["signal_id"]
    assert signal_id is not None

    # The signal is attributed to the user who owns that secret.
    mine = client.get(f"/signals/{signal_id}", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["symbol"] == "SOL/USD"
    assert mine.json()["source"] == "tradingview"

    # A different user cannot see it.
    token_b = _signup(client, "nosneak@test.dev")
    assert client.get(f"/signals/{signal_id}", headers=auth(token_b)).status_code == 404


def test_webhook_signal_fields(client):
    token = _signup(client, "hook2@test.dev")
    response = client.post(
        "/webhook/tradingview/test",
        json={"symbol": "ETH/USD", "direction": "SHORT", "price": 3000.0, "timeframe": "1H"},
        headers=auth(token),
    )
    assert response.status_code == 201
    signal = response.json()
    assert signal["entry_price"] == 3000.0
    assert signal["is_demo"] is False
    assert signal["stop_loss"] is None or signal["stop_loss"] > 3000.0
    assert signal["take_profit"] is None or signal["take_profit"] < 3000.0