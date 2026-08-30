"""End-to-end API flow: strategy -> backtest -> signal -> dashboard."""
from conftest import auth

from app.services.ai_strategy_service import available_demo_strategies


def _signup(client, email: str):
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Flow Tester"},
    )
    return response.json()["access_token"]


def test_full_flow(client):
    token = _signup(client, "flow@test.dev")
    headers = auth(token)
    demo = available_demo_strategies()[0]

    # Create a strategy from an available demo strategy's extracted fields.
    create = client.post(
        "/strategies",
        json={
            "name": demo["strategy_name"],
            "description": demo.get("description"),
            "asset": demo["asset"],
            "market": demo.get("market"),
            "timeframe": demo["timeframe"],
            "strategy_type": demo.get("strategy_type"),
            "direction": demo["direction"],
            "indicators": demo.get("indicators", []),
            "entry_rules": demo.get("entry_rules", []),
            "confirmation_rules": demo.get("confirmation_rules", []),
            "exit_rules": demo.get("exit_rules", []),
            "stop_loss_type": demo.get("stop_loss_type"),
            "stop_loss_value": demo.get("stop_loss_value"),
            "take_profit_type": demo.get("take_profit_type"),
            "take_profit_value": demo.get("take_profit_value"),
            "risk_per_trade": demo.get("risk_per_trade"),
            "risk_reward": demo.get("risk_reward"),
            "confidence": demo.get("confidence"),
            "assumptions": demo.get("assumptions", []),
            "missing_information": demo.get("missing_information", []),
            "source": "test",
            "is_demo": False,
            "is_active": True,
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    strategy = create.json()
    strategy_id = strategy["id"]

    # Run a backtest.
    backtest = client.post(
        "/backtests/run",
        json={
            "strategy_id": strategy_id,
            "symbol": strategy["asset"],
            "timeframe": strategy["timeframe"],
            "initial_capital": 10000,
            "risk_percent": strategy["risk_per_trade"] or 1,
        },
        headers=headers,
    )
    assert backtest.status_code == 201, backtest.text
    bt = backtest.json()
    assert bt["metrics"]["total_trades"] >= 0

    # List & fetch a single backtest.
    assert client.get("/backtests", headers=headers).status_code == 200
    detail = client.get(f"/backtests/{bt['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["metrics"] == bt["metrics"]

    # Generate a signal from the strategy.
    signal = client.post("/signals/generate", json={"strategy_id": strategy_id}, headers=headers)
    assert signal.status_code == 201, signal.text
    sig = signal.json()
    assert sig["direction"] in ("LONG", "SHORT")
    assert sig["reason"]

    # Patch its status then list filtered.
    patch = client.patch(f"/signals/{sig['id']}/status?status=ACTIVE", headers=headers)
    assert patch.status_code == 200
    active = client.get("/signals?status=ACTIVE", headers=headers).json()
    assert any(s["id"] == sig["id"] for s in active)

    # Dashboard + performance endpoints resolve.
    assert client.get("/dashboard/stats", headers=headers).status_code == 200
    assert client.get("/performance/summary", headers=headers).status_code == 200
    assert client.get("/performance/strategies", headers=headers).status_code == 200
    assert client.get("/performance/equity", headers=headers).status_code == 200
    assert client.get("/performance/monthly", headers=headers).status_code == 200

    # Billing + settings.
    assert client.get("/billing/plans").status_code == 200
    assert client.get("/billing/current", headers=headers).status_code == 200
    assert client.put("/settings", json={"name": "Flow Updated"}, headers=headers).status_code == 200

    # Notifications arrived for the analysis/backtest/signal activity.
    notifs = client.get("/notifications", headers=headers).json()
    assert len(notifs) >= 1


def test_strategy_delete(client):
    token = _signup(client, "del@test.dev")
    headers = auth(token)
    demo = available_demo_strategies()[0]
    create = client.post(
        "/strategies",
        json={
            "name": "Delete Me",
            "asset": demo["asset"],
            "timeframe": demo["timeframe"],
            "direction": "LONG",
            "indicators": [],
            "entry_rules": demo["entry_rules"],
            "confirmation_rules": [],
            "exit_rules": demo["exit_rules"],
            "source": "test",
            "is_demo": False,
            "is_active": True,
        },
        headers=headers,
    )
    assert create.status_code == 201
    sid = create.json()["id"]
    assert client.delete(f"/strategies/{sid}", headers=headers).status_code == 204
    assert client.get(f"/strategies/{sid}", headers=headers).status_code == 404