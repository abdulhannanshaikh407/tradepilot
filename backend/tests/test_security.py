# app tests for security hardening and heuristic asset handling
import pytest


def test_breakout_crypto_asset_respects_detected_asset():
    """A Bitcoin breakout transcript must stay on BTC/USD, not be remapped to NAS100."""
    import app.services.ai_strategy_service as svc

    text = (
        "In this video we use a momentum breakout on bitcoin. "
        "Wait for a break of the previous high, set stop loss at 2% and "
        "take profit at 4% on the 4 hour chart, risk 1%."
    )
    raw = svc._extract_heuristic(text)
    assert raw["asset"] == "BTC/USD"
    assert raw["strategy_name"] == "Momentum Breakout"


def test_breakout_nasdaq_respects_detected_asset():
    """A NASDAQ breakout transcript stays on NAS100."""
    import app.services.ai_strategy_service as svc

    text = (
        "Trading a breakout of the NAS100 range. Break the level and ride the "
        "move on the 1 hour chart, stop loss 1%, take profit 3%, risk 1%."
    )
    raw = svc._extract_heuristic(text)
    assert raw["asset"] == "NAS100"


@pytest.mark.parametrize(
    "jwt,webhook,environment,expected",
    [
        ("change-me-in-production", "tradepilot-webhook-secret", "production", True),
        ("short", "tradepilot-webhook-secret", "production", True),
        ("x" * 48, "x" * 32, "production", False),
        ("change-me-in-production", "tradepilot-webhook-secret", "development", False),
    ],
)
def test_production_secret_guard(monkeypatch, jwt, webhook, environment, expected):
    import app.main

    monkeypatch.setattr(app.main, "JWT_SECRET", jwt)
    monkeypatch.setattr(app.main, "TRADINGVIEW_WEBHOOK_SECRET", webhook)
    monkeypatch.setattr(app.main, "ENVIRONMENT", environment)
    if expected:
        with pytest.raises(RuntimeError):
            app.main._assert_production_secrets()
    else:
        app.main._assert_production_secrets()


def test_timeframe_detection_ignores_indicator_periods():
    """'50 day / 200 day SMA' are indicator periods, NOT a chart timeframe."""
    import app.services.ai_strategy_service as svc

    text = "buy when the 50 day SMA crosses above the 200 day SMA"
    assert svc._detect_timeframe(text) is None
    assert svc._detect_timeframe("take entries on the 4 hour chart") == "4H"
    assert svc._detect_timeframe("a daily momentum strategy") == "1D"
    assert svc._detect_timeframe("scalp on the 15 minute chart") == "15m"


def test_golden_cross_heuristic_keeps_supported_timeframe():
    """A golden-cross transcript mentioning SMA periods must not end up on an
    unsupported timeframe like 50D (which would 500 in the signal engine)."""
    import app.services.ai_strategy_service as svc

    text = (
        "Use a golden cross when the 50 day SMA crosses above the 200 day SMA "
        "for a long entry, stop loss 3%, take profit 6%."
    )
    raw = svc._extract_heuristic(text)
    assert raw["strategy_name"] == "Golden Cross Trend"
    assert raw["timeframe"] in {"15m", "1H", "4H", "1D"} or raw["timeframe"] in {"1W", "1M"}
    assert raw["timeframe"] != "50D"


def test_generate_signal_unsupported_timeframe_returns_clean_error(client):
    """signals/generate must return a 422, not a 500, for an unsupported timeframe."""
    token = client.post("/auth/login", json={"email": "demo@tradepilot.ai", "password": "demo"}).json().get(
        "access_token"
    ) or client.post("/auth/demo").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a strategy on an unsupported timeframe.
    created = client.post(
        "/strategies/",
        headers=headers,
        json={
            "name": "Bad TF Strat",
            "asset": "BTC/USD",
            "timeframe": "7D",
            "direction": "LONG",
            "entry_rules": [{"condition": "close > SMA", "params": {"period": 20}}],
            "assumptions": ["test"],
        },
    )
    assert created.status_code in (200, 201, 422), created.text
    if created.status_code in (200, 201):
        sid = created.json()["id"]
        resp = client.post("/signals/generate", headers=headers, json={"strategy_id": sid})
        assert resp.status_code == 422, resp.text
        assert "Cannot generate signal" in resp.json()["detail"]
