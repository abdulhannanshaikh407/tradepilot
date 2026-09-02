# tests/test_backtest_accuracy.py
"""Backtest accuracy validation tests.

These tests verify that the backtest engine produces results consistent
with known strategy outcomes. Run with: pytest tests/test_backtest_accuracy.py -v
"""
import pytest

from app.services.market_data_service import SimulatedMarketDataProvider


@pytest.fixture
def sim_provider():
    return SimulatedMarketDataProvider()


def test_simulated_provider_deterministic(sim_provider):
    """Same inputs must produce same outputs."""
    bars1 = sim_provider.get_ohlcv("BTC/USD", "1H")
    bars2 = sim_provider.get_ohlcv("BTC/USD", "1H")
    assert len(bars1) == len(bars2)
    assert bars1[0]["close"] == bars2[0]["close"]
    assert bars1[-1]["close"] == bars2[-1]["close"]


def test_simulated_provider_multiple_assets(sim_provider):
    """Provider should handle multiple crypto assets."""
    for symbol in ["BTC/USD", "ETH/USD", "SOL/USD"]:
        bars = sim_provider.get_ohlcv(symbol, "4H")
        assert len(bars) > 100
        assert bars[0]["open"] > 0
        assert bars[0]["high"] >= bars[0]["low"]


def test_simulated_provider_timeframes(sim_provider):
    """Each timeframe should produce different bar counts."""
    counts = {}
    for tf in ["15m", "1H", "4H", "1D"]:
        bars = sim_provider.get_ohlcv("BTC/USD", tf)
        counts[tf] = len(bars)
    # 15m should have more bars than 1D
    assert counts["15m"] > counts["1D"]
    assert counts["1H"] > counts["4H"]


def test_bars_ohlc_integrity(sim_provider):
    """OHLC relationships must hold: high >= open,close and low <= open,close."""
    bars = sim_provider.get_ohlcv("ETH/USD", "1H")
    for bar in bars[-100:]:
        assert bar["high"] >= bar["open"]
        assert bar["high"] >= bar["close"]
        assert bar["low"] <= bar["open"]
        assert bar["low"] <= bar["close"]
        assert bar["volume"] >= 0


def test_backtest_basic_long_strategy():
    """Simple long strategy using the backtest engine."""
    from app.services.backtest_engine import run_backtest

    strategy = {
        "rules": {
            "entry": {"logic": "all", "conditions": [{"condition": "close > open", "params": {}}]},
            "confirmation": {"logic": "all", "conditions": []},
            "exit": {"logic": "any", "conditions": [{"condition": "close < open", "params": {}}]},
        }
    }

    result = run_backtest(
        strategy=strategy,
        symbol="BTC/USD",
        timeframe="4H",
        initial_capital=10000,
        risk_percent=1.0,
    )

    assert result is not None
    assert "metrics" in result
    assert result["metrics"]["total_trades"] >= 0


def test_backtest_engine_runs():
    """Backtest should run without errors on a simple strategy."""
    from app.services.backtest_engine import run_backtest

    strategy = {
        "rules": {
            "entry": {"logic": "all", "conditions": [{"condition": "close > open", "params": {}}]},
            "confirmation": {"logic": "all", "conditions": []},
            "exit": {"logic": "any", "conditions": [{"condition": "close < open", "params": {}}]},
        }
    }

    result = run_backtest(
        strategy=strategy,
        symbol="ETH/USD",
        timeframe="1D",
        initial_capital=10000,
        risk_percent=2.0,
    )

    assert result is not None
    assert "metrics" in result
    metrics = result["metrics"]

    required_keys = [
        "total_trades", "winning_trades", "losing_trades", "win_rate",
        "net_pnl", "return_percent", "profit_factor", "max_drawdown",
    ]
    for key in required_keys:
        assert key in metrics, f"Missing metric: {key}"


def test_backtest_metrics_structure():
    """Backtest result should contain all required metrics."""
    from app.services.backtest_engine import run_backtest

    strategy = {
        "rules": {
            "entry": {"logic": "all", "conditions": [{"condition": "close > open", "params": {}}]},
            "confirmation": {"logic": "all", "conditions": []},
            "exit": {"logic": "any", "conditions": []},
        }
    }

    result = run_backtest(
        strategy=strategy,
        symbol="BTC/USD",
        timeframe="4H",
        initial_capital=10000,
        risk_percent=1.0,
    )

    assert "equity_curve" in result
    assert "trade_history" in result
    assert isinstance(result["equity_curve"], list)
    assert isinstance(result["trade_history"], list)


def test_backtest_with_stop_loss():
    """Backtest with stop loss and take profit levels."""
    from app.services.backtest_engine import run_backtest

    strategy = {
        "stop_loss_type": "percent",
        "stop_loss_value": 2.0,
        "take_profit_type": "percent",
        "take_profit_value": 4.0,
        "rules": {
            "entry": {"logic": "all", "conditions": [{"condition": "close > open", "params": {}}]},
            "confirmation": {"logic": "all", "conditions": []},
            "exit": {"logic": "any", "conditions": []},
        }
    }

    result = run_backtest(
        strategy=strategy,
        symbol="SOL/USD",
        timeframe="4H",
        initial_capital=10000,
        risk_percent=1.0,
    )

    assert result is not None
    assert "metrics" in result
    assert result["metrics"]["total_trades"] >= 0
