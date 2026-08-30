"""Direct unit tests of the deterministic backtest engine (no HTTP needed)."""
from app.services.ai_strategy_service import available_demo_strategies
from app.services.backtest_engine import normalize_strategy, run_backtest, validate_rules


def test_available_demo_strategies_are_valid():
    strategies = available_demo_strategies()
    assert strategies
    for strategy in strategies:
        normalized = normalize_strategy(strategy)
        rules = normalized.get("rules", {})
        assert rules["entry"]["conditions"], f"strategy {strategy['name']} has no entry rules"
        errors = validate_rules(rules["entry"]["conditions"])
        assert not errors, f"strategy {strategy['name']}: {errors}"


def test_run_backtest_produces_metrics():
    strategies = available_demo_strategies()
    for strategy in strategies:
        normalized = normalize_strategy(strategy)
        result = run_backtest(
            strategy=normalized,
            symbol=strategy["asset"],
            timeframe=strategy["timeframe"],
            initial_capital=10000.0,
            risk_percent=1.0,
            fee_percent=0.05,
            slippage_percent=0.02,
        )
        assert "metrics" in result
        metrics = result["metrics"]
        assert "total_trades" in metrics
        assert metrics["total_trades"] >= 0
        assert isinstance(metrics["net_pnl"], (int, float))
        assert isinstance(metrics["win_rate"], (int, float))
        assert isinstance(metrics["max_drawdown"], (int, float))
        assert round(metrics["net_pnl"], 2) == round(sum(t["pnl"] for t in result["trade_history"]), 2)
        assert result["equity_curve"]
        assert result["equity_curve"][0]["equity"] == 10000.0
        assert result["monthly_performance"] is not None
        assert result["wl_distribution"]["total"] == metrics["total_trades"]


def test_run_backtest_returns_deterministic_results():
    """Same inputs ⇒ identical outcomes (seeded simulated market data)."""
    strategies = available_demo_strategies()
    first = strategies[0]
    normalized = normalize_strategy(first)

    a = run_backtest(normalized, first["asset"], first["timeframe"])
    b = run_backtest(normalized, first["asset"], first["timeframe"])

    assert a["metrics"] == b["metrics"]
    assert a["equity_curve"] == b["equity_curve"]
    assert a["trade_history"] == b["trade_history"]


def test_validate_rules_flags_unknown_conditions():
    errors = validate_rules([{"condition": "NOT_A_REAL_CONDITION", "params": {}}])
    assert errors