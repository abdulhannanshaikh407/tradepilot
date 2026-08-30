"""Signal engine unit tests — signal shape and explanation guarantees."""
from app.services.ai_strategy_service import available_demo_strategies
from app.services.signal_engine import describe_rule, generate_signal


def test_generate_signal_shape():
    strategy = available_demo_strategies()[0]
    result = generate_signal(strategy, strategy["asset"], strategy["timeframe"])

    assert result["symbol"] == strategy["asset"]
    assert result["direction"] in ("LONG", "SHORT")
    assert result["entry_price"] > 0
    assert result["status"] == "PENDING"
    assert result["reason"]
    assert result["source"] in ("youtube", "signal_engine", "demo")
    assert isinstance(result["signal_fires"], bool)


def test_generate_signal_stop_and_target_are_percent_derived():
    strategy = available_demo_strategies()[1]
    strategy = {**strategy, "stop_loss_value": 2.0, "stop_loss_type": "percent",
                "take_profit_value": 4.0, "take_profit_type": "percent", "direction": "LONG"}
    result = generate_signal(strategy, strategy["asset"], strategy["timeframe"])

    close = result["entry_price"]
    if result["stop_loss"] and result["take_profit"]:
        assert result["stop_loss"] < close < result["take_profit"]
        assert abs(round((close - result["stop_loss"]) / close * 100, 1) - 2.0) <= 0.2
        assert abs(round((result["take_profit"] - close) / close * 100, 1) - 4.0) <= 0.2


def test_reasons_are_explainable():
    strategy = available_demo_strategies()[0]
    result = generate_signal(strategy, strategy["asset"], strategy["timeframe"])
    for reason in result["reasons"]:
        assert reason["condition"]
        assert reason["description"]
        assert isinstance(reason["fired"], bool)


def test_describe_rule_readable():
    text = describe_rule({"condition": "price_above_ma", "params": {"period": 200, "ma": "ema"}})
    assert "200" in text
    assert text.lower()