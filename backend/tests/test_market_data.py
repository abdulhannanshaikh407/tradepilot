"""Tests for market-data providers, symbol normalization and live quotes."""
from conftest import auth

from app.services.market_data_service import (
    ASSETS,
    LiveQuoteStore,
    apply_live_quote,
    get_provider,
    normalize_symbol,
    tradingview_symbol,
)


def _signup(client, email: str) -> str:
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Market Tester"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["access_token"]


def test_default_provider_is_simulated():
    provider = get_provider()
    valid_providers = ("simulated", "binance", "real", "biquote", "finnhub", "gold_forex", "mtsocket")
    assert provider.name in valid_providers


def test_normalize_symbol_aliases():
    assert normalize_symbol("XAUUSD") == "XAUUSD"
    assert normalize_symbol("xauusd") == "XAUUSD"
    assert normalize_symbol("BTCUSD") == "BTC/USD"
    assert normalize_symbol("EURUSD") == "EUR/USD"
    assert normalize_symbol("BTC/USD") == "BTC/USD"
    assert normalize_symbol("USDJPY") == "USD/JPY"
    assert normalize_symbol("GOLD") == "GOLD"  # no alias: left as-is


def test_tradingview_symbol_roundtrip():
    assert tradingview_symbol("BTC/USD") == "BTCUSD"
    assert tradingview_symbol("XAUUSD") == "XAUUSD"
    assert tradingview_symbol("EUR/USD") == "EURUSD"


def test_xauusd_is_a_supported_asset():
    assert "XAUUSD" in ASSETS
    bars = get_provider().get_ohlcv("XAUUSD", "1D")
    assert len(bars) >= 100
    assert bars[-1]["close"] > 0


def test_unknown_symbol_rejected():
    import pytest

    with pytest.raises(ValueError):
        get_provider().get_ohlcv("NOTREAL123", "1D")


def test_live_quote_store_roundtrip_and_ttl(client):
    store = LiveQuoteStore(ttl=300)
    store.set("XAUUSD", 2410.5, source="tradingview", extra={"timeframe": "4H"})
    quote = store.get("XAUUSD")
    assert quote["price"] == 2410.5
    assert quote["source"] == "tradingview"
    assert quote["symbol"] == "XAUUSD"

    from datetime import datetime, timedelta

    store._quotes["XAUUSD"]["updated_at"] = (
        datetime.now() - timedelta(seconds=600)
    ).isoformat(timespec="seconds")
    assert store.get("XAUUSD") is None


def test_apply_live_quote_stamps_last_bar():
    bars = get_provider().get_ohlcv("BTC/USD", "1D")
    stamped = apply_live_quote(bars, "BTC/USD", price=50000.0)
    assert stamped is not bars
    assert stamped[-1]["close"] == 50000.0
    assert stamped[-1]["live"] is True
    # Original bars are not mutated.
    assert bars[-1]["close"] != 50000.0 or bars[-1].get("live") is None


def test_market_live_endpoint(client):
    token = _signup(client, "market-live@test.dev")
    response = client.get("/market/live", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    valid_providers = ("simulated", "binance", "real", "biquote", "finnhub", "gold_forex", "mtsocket")
    assert body["provider"] in valid_providers
    assert body["live_count"] == 0
    assert "XAUUSD" in body["quotes"]
    assert "BTC/USD" in body["quotes"]


def test_market_assets_and_ohlcv(client):
    token = _signup(client, "market-assets@test.dev")
    assets = client.get("/market/assets", headers=auth(token)).json()["assets"]
    assert any(a["symbol"] == "XAUUSD" for a in assets)

    ohlcv = client.get(
        "/market/ohlcv?symbol=XAUUSD&timeframe=1D&live=1", headers=auth(token)
    ).json()
    assert ohlcv["symbol"] == "XAUUSD"
    assert ohlcv["demo"] is True
    assert len(ohlcv["bars"]) > 0