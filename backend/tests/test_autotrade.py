"""Tests for the autonomous trading engine (paper execution, risk caps)."""
import pytest

from app.db.database import SessionLocal
from app.db import models
from app.services.broker import PaperBroker


def _setup_user(client, email: str):
    token = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "AT Tester"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _strategy(client, headers: dict, **overrides):
    payload = {
        "name": "AutoTest",
        "asset": "BTC/USD",
        "timeframe": "4H",
        "direction": "LONG",
        "entry_rules": [{"condition": "always", "params": {}}],
        "confirmation_rules": [{"condition": "always", "params": {}}],
        "exit_rules": [],
        "stop_loss_type": "percent",
        "stop_loss_value": 1.0,
        "take_profit_type": "percent",
        "take_profit_value": 2.0,
    }
    payload.update(overrides)
    return client.post("/strategies/", headers=headers, json=payload).json()


def test_paper_broker_pricing_and_slippage():
    broker = PaperBroker(slippage_percent=0.1, timeframe="4H")
    buy = broker.buy_quote("BTC/USD", 1000.0)
    assert buy.side == "BUY"
    assert buy.quote == 1000.0
    assert buy.base_qty > 0
    assert buy.price < broker.market_price("BTC/USD")  # buy slips down vs close
    sell = broker.sell_base("BTC/USD", buy.base_qty)
    assert sell.side == "SELL"
    assert sell.price > buy.price


def test_engine_opens_paper_position(client):
    headers = _setup_user(client, "at-open@test.dev")
    strategy = _strategy(client, headers)

    cfg = client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    assert cfg.status_code == 201, cfg.text

    run = client.post("/autotrade/run-now", headers=headers)
    assert run.status_code == 200
    assert run.json()["configs"] == 1

    positions = client.get("/autotrade/positions", headers=headers).json()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["status"] == "OPEN"
    assert pos["broker"] == "paper"
    assert pos["direction"] == "LONG"
    assert pos["symbol"] == "BTC/USD"
    assert pos["entry_price"] > 0
    assert pos["size"] > 0
    # risk exposed = distance-to-stop * size should equal 1% of capital (~ $100).
    risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["size"]
    assert 80 <= risk <= 120


def test_engine_keeps_position_open_when_signal_still_fires(client):
    headers = _setup_user(client, "at-dup@test.dev")
    strategy = _strategy(client, headers)
    client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    client.post("/autotrade/run-now", headers=headers)
    client.post("/autotrade/run-now", headers=headers)
    open_positions = [
        p
        for p in client.get("/autotrade/positions", headers=headers).json()
        if p["status"] == "OPEN"
    ]
    assert len(open_positions) == 1  # no duplicate entry on repeated scans


def test_engine_closes_on_take_profit(client):
    headers = _setup_user(client, "at-tp@test.dev")
    strategy = _strategy(client, headers)
    client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    client.post("/autotrade/run-now", headers=headers)
    position = client.get("/autotrade/positions", headers=headers).json()[0]

    # Force an immediate target hit: set take-profit below the current price.
    db = SessionLocal()
    row = db.get(models.Position, position["id"])
    row.take_profit = row.current_price * 0.999
    db.commit()
    db.close()

    client.post("/autotrade/run-now", headers=headers)
    closed = client.get("/autotrade/positions", headers=headers).json()[0]
    assert closed["status"] == "CLOSED"
    assert closed["exit_reason"] == "take_profit"
    assert closed["realized_pnl"] is not None
    assert closed["closed_at"] is not None


def test_stop_loss_blocks_new_entries(client):
    headers = _setup_user(client, "at-block@test.dev")
    strategy = _strategy(client, headers)
    client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    client.post("/autotrade/run-now", headers=headers)
    position = client.get("/autotrade/positions", headers=headers).json()[0]

    db = SessionLocal()
    row = db.get(models.Position, position["id"])
    # Drop the take-profit so the engine's enforced max_concurrent=1 is the reason.
    row.take_profit = None
    db.commit()
    db.close()

    # A second enabled config with a second strategy should be blocked by max_concurrent=1.
    strategy2 = _strategy(client, headers, name="AutoTest2")
    client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy2["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    client.post("/autotrade/run-now", headers=headers)
    open_positions = [
        p
        for p in client.get("/autotrade/positions", headers=headers).json()
        if p["status"] == "OPEN"
    ]
    assert len(open_positions) == 1


def test_live_mode_requires_credentials(client):
    headers = _setup_user(client, "at-live@test.dev")
    strategy = _strategy(client, headers)
    resp = client.post(
        "/autotrade/config",
        headers=headers,
        json={"strategy_id": strategy["id"], "enabled": True, "mode": "live"},
    )
    assert resp.status_code == 400


def test_manual_close_endpoint(client):
    headers = _setup_user(client, "at-close@test.dev")
    strategy = _strategy(client, headers)
    client.post(
        "/autotrade/config",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "enabled": True,
            "mode": "paper",
            "capital": 10000.0,
            "risk_percent": 1.0,
            "max_concurrent": 1,
            "cooldown_minutes": 0,
        },
    )
    client.post("/autotrade/run-now", headers=headers)
    position = client.get("/autotrade/positions", headers=headers).json()[0]

    resp = client.post(
        f"/autotrade/positions/{position['id']}/close",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"
    assert resp.json()["exit_reason"] == "manual_close"
    # Closing twice is rejected.
    again = client.post(
        f"/autotrade/positions/{position['id']}/close",
        headers=headers,
    )
    assert again.status_code == 400


@pytest.mark.parametrize("binance_conf", [None], ids=["live-unavailable"])
def test_status_endpoint(client, binance_conf):
    headers = _setup_user(client, "at-status@test.dev")
    status = client.get("/autotrade/status", headers=headers).json()
    assert status["provider"] in ("simulated", "binance")
    assert status["enabled"] is True
    assert "interval_seconds" in status
    assert status["live_available"] is False