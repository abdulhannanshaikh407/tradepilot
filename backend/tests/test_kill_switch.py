"""Tests for the kill switch feature and signal state fields."""
import pytest

from app.db.database import SessionLocal
from app.db import models


def _setup_user(client, email: str):
    token = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "KS Tester"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _strategy(client, headers: dict, **overrides):
    payload = {
        "name": "KillSwitchTest",
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


# ---------- 1. Toggle via API ----------

def test_kill_switch_toggles_off_to_on(client):
    headers = _setup_user(client, "ks-toggle1@test.dev")
    resp = client.post("/settings/kill-switch", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kill_switch"] is True
    assert "blocked" in body["message"].lower()


def test_kill_switch_toggles_on_to_off(client):
    headers = _setup_user(client, "ks-toggle2@test.dev")
    client.post("/settings/kill-switch", headers=headers)  # enable
    resp = client.post("/settings/kill-switch", headers=headers)  # disable
    assert resp.status_code == 200
    body = resp.json()
    assert body["kill_switch"] is False
    assert "allowed" in body["message"].lower()


# ---------- 2. Status check ----------

def test_kill_switch_status_default_false(client):
    headers = _setup_user(client, "ks-status@test.dev")
    resp = client.get("/settings/kill-switch", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["kill_switch"] is False


def test_kill_switch_status_reflects_toggle(client):
    headers = _setup_user(client, "ks-status2@test.dev")
    client.post("/settings/kill-switch", headers=headers)
    resp = client.get("/settings/kill-switch", headers=headers)
    assert resp.json()["kill_switch"] is True


# ---------- 3. Kill switch blocks live autotrade ----------

def test_kill_switch_blocks_live_autotrade(client):
    from app.services.autotrade import _safety_check

    headers = _setup_user(client, "ks-block@test.dev")
    strategy = _strategy(client, headers)

    # Enable kill switch via API
    client.post("/settings/kill-switch", headers=headers)

    # Create a live-mode config directly in DB (API requires broker credentials)
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "ks-block@test.dev").first()
    assert user.kill_switch is True

    config = models.AutoTradeConfig(
        user_id=user.id,
        strategy_id=strategy["id"],
        enabled=True,
        mode="live",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    result = _safety_check(db, config, account_balance=10000, signal_size=500)
    assert result is False
    db.close()


def test_kill_switch_off_allows_live_safety_check(client):
    from app.services.autotrade import _safety_check

    headers = _setup_user(client, "ks-allow@test.dev")
    strategy = _strategy(client, headers)

    # Kill switch is off by default; create live config in DB
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "ks-allow@test.dev").first()
    assert user.kill_switch is False

    config = models.AutoTradeConfig(
        user_id=user.id,
        strategy_id=strategy["id"],
        enabled=True,
        mode="live",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    result = _safety_check(db, config, account_balance=10000, signal_size=500)
    assert result is True
    db.close()


# ---------- 4. Kill switch does not block paper trading ----------

def test_kill_switch_does_not_block_paper_trading(client):
    headers = _setup_user(client, "ks-paper@test.dev")
    strategy = _strategy(client, headers)

    # Enable kill switch
    client.post("/settings/kill-switch", headers=headers)

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
    assert cfg.status_code == 201

    run = client.post("/autotrade/run-now", headers=headers)
    assert run.status_code == 200
    assert run.json()["configs"] >= 1

    positions = client.get("/autotrade/positions", headers=headers).json()
    open_positions = [p for p in positions if p["status"] == "OPEN"]
    assert len(open_positions) >= 1
    assert open_positions[0]["broker"] == "paper"


# ---------- 5. Signal state fields ----------

def test_signal_output_has_state_fields(client):
    headers = _setup_user(client, "ks-signal@test.dev")
    resp = client.post(
        "/signals/",
        headers=headers,
        json={
            "symbol": "BTC/USD",
            "direction": "LONG",
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "source": "manual",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "signal_state" in body
    assert body["signal_state"] == "WATCHING"
    assert "invalidation_reason" in body
    assert body["invalidation_reason"] is None
    assert "quality_score" in body
    assert body["quality_score"] is None


def test_signal_list_includes_state_fields(client):
    headers = _setup_user(client, "ks-signal2@test.dev")
    client.post(
        "/signals/",
        headers=headers,
        json={
            "symbol": "ETH/USD",
            "direction": "SHORT",
            "entry_price": 3000.0,
            "source": "manual",
        },
    )
    signals = client.get("/signals/", headers=headers).json()
    assert len(signals) >= 1
    sig = signals[0]
    assert "signal_state" in sig
    assert "invalidation_reason" in sig
    assert "quality_score" in sig
