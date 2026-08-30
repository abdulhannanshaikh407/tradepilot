"""Tests for the parameter optimizer (grid search + walk-forward)."""
import pytest

from app.services import optimizer as opt

DEMO_STRATEGY = {
    "strategy_name": "Optimizer test",
    "name": "Optimizer test",
    "direction": "LONG",
    "asset": "BTC/USD",
    "timeframe": "4H",
    "rules": {
        "entry": {"logic": "all", "conditions": [
            {"condition": "price_breakout_above", "params": {"period": 20}},
        ]},
        "confirmation": {"logic": "all", "conditions": [
            {"condition": "price_above_ma", "params": {"period": 100, "ma": "ema"}},
        ]},
        "exit": {"logic": "any", "conditions": [
            {"condition": "price_breakdown_below", "params": {"period": 20}},
        ]},
    },
    "stop_loss_type": "percent",
    "stop_loss_value": 1.0,
    "take_profit_type": "percent",
    "take_profit_value": 2.0,
}

PARAMS = [{"path": "entry.conditions.0.params.period", "min": 14.0, "max": 18.0, "step": 2.0}]


def test_grid_best_and_oos():
    result = opt.optimize(
        strategy=DEMO_STRATEGY,
        symbol="BTC/USD",
        timeframe="4H",
        parameters=PARAMS,
        metric="return_percent",
        mode="grid",
        max_bars=2000,
    )
    assert result["mode"] == "grid"
    assert result["grid_total_evals"] == 3  # 14, 16, 18
    assert result["best_params"]
    # Shorthand path is canonicalized to the engine's rules.* form.
    assert "rules.entry.conditions.0.params.period" in result["best_params"]
    assert result["best_metrics"]["return_percent"] is not None
    assert len(result["top_results"]) == 3
    # oos split with default test_ratio=0.3 leaves >=80 bars.
    assert result["out_of_sample_metrics"] is not None


def test_grid_no_oos_when_ratio_zero():
    result = opt.optimize(
        strategy=DEMO_STRATEGY,
        symbol="BTC/USD",
        timeframe="4H",
        parameters=PARAMS,
        metric="sharpe_ratio",
        mode="grid",
        test_ratio=0.0,
        max_bars=2000,
    )
    assert result["out_of_sample_metrics"] is None
    assert "sharpe_ratio" in result["best_metrics"]


def test_max_drawdown_minimized_by_default():
    result = opt.optimize(
        strategy=DEMO_STRATEGY,
        symbol="BTC/USD",
        timeframe="4H",
        parameters=PARAMS,
        metric="max_drawdown",
        mode="grid",
        max_bars=2000,
    )
    assert result["direction"] == "minimize"


def test_oversized_grid_rejected():
    big = [{"path": "entry.conditions.0.params.period", "min": 1.0, "max": 100.0, "step": 1.0}]
    with pytest.raises(ValueError, match="max"):
        opt.optimize(
            strategy=DEMO_STRATEGY,
            symbol="BTC/USD",
            timeframe="4H",
            parameters=big,
            metric="return_percent",
            mode="grid",
            max_evals=50,
            max_bars=2000,
        )


def test_unknown_metric_rejected():
    with pytest.raises(ValueError, match="Unsupported optimization metric"):
        opt.optimize(
            strategy=DEMO_STRATEGY,
            symbol="BTC/USD",
            timeframe="4H",
            parameters=PARAMS,
            metric="not_a_metric",
            max_bars=2000,
        )


def test_empty_parameters_rejected():
    with pytest.raises(ValueError, match="at least one"):
        opt.optimize(
            strategy=DEMO_STRATEGY,
            symbol="BTC/USD",
            timeframe="4H",
            parameters=[],
            metric="return_percent",
            max_bars=2000,
        )


def test_bad_direction_rejected():
    with pytest.raises(ValueError, match="Invalid direction"):
        opt.optimize(
            strategy=DEMO_STRATEGY,
            symbol="BTC/USD",
            timeframe="4H",
            parameters=PARAMS,
            metric="return_percent",
            direction="sideways",
            max_bars=2000,
        )


def test_walk_forward_folds_and_combined_metrics():
    result = opt.optimize(
        strategy=DEMO_STRATEGY,
        symbol="BTC/USD",
        timeframe="4H",
        parameters=PARAMS,
        metric="return_percent",
        mode="walk_forward",
        folds=3,
        max_bars=2000,
    )
    assert result["mode"] == "walk_forward"
    wf = result["walk_forward"]
    assert wf is not None
    assert len(wf["folds"]) == 3
    for fold in wf["folds"]:
        assert fold["best_params"]
        assert fold["test_metrics"]["total_trades"] >= 0
    assert "return_percent" in wf["combined_metrics"]
    assert wf["combined_equity_curve"]


def test_apply_params_top_level_and_nested():
    candidate = opt.apply_params(
        DEMO_STRATEGY,
        {"rules.entry.conditions.0.params.period": 30, "stop_loss_value": 2.5},
    )
    assert candidate["rules"]["entry"]["conditions"][0]["params"]["period"] == 30
    assert candidate["stop_loss_value"] == 2.5
    assert candidate is not DEMO_STRATEGY


def test_param_values_expansion():
    values = opt.param_values({"min": 1.0, "max": 5.0, "step": 2.0})
    assert values == [1.0, 3.0, 5.0]
    with pytest.raises(ValueError, match="invalid"):
        opt.param_values({"min": 5.0, "max": 1.0})
    with pytest.raises(ValueError, match="step"):
        opt.param_values({"min": 1.0, "max": 5.0, "step": 0.0})


def _payload():
    return {
        "strategy_name": "Optimizer test",
        "symbol": "BTC/USD",
        "timeframe": "4H",
        "initial_capital": 10000,
        "risk_percent": 1.0,
        "fee_percent": 0.05,
        "slippage_percent": 0.02,
        "optimization": {
            "parameters": [{"path": "entry.conditions.0.params.period", "min": 14.0, "max": 18.0, "step": 2.0}],
            "metric": "return_percent",
            "mode": "walk_forward",
            "folds": 3,
            "test_ratio": 0.2,
            "max_evals": 400,
            "max_bars": 2000,
        },
    }


def test_optimize_endpoint_walk_forward(client):
    token = client.post(
        "/auth/signup",
        json={"email": "opt-wf@test.dev", "password": "password123", "name": "WF"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/backtests/optimize", headers=headers, json=_payload())
    data = resp.json()
    assert resp.status_code == 200, data
    assert data["mode"] == "walk_forward"
    assert len(data["walk_forward"]["folds"]) == 3
    assert "backtest_id" in data


def test_optimize_endpoint_grid(client):
    token = client.post(
        "/auth/signup",
        json={"email": "opt-grid@test.dev", "password": "password123", "name": "Grid"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = _payload()
    payload["optimization"]["mode"] = "grid"
    resp = client.post("/backtests/optimize", headers=headers, json=payload)
    data = resp.json()
    assert resp.status_code == 200, data
    assert data["mode"] == "grid"
    assert data["grid_total_evals"] == 3
    assert data["best_params"]
    assert "backtest_id" in data