# app/api/routes/market.py
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.services.market_data_service import (
    ASSETS,
    TIMEFRAMES,
    apply_live_quote,
    get_provider,
    live_quotes,
    normalize_symbol,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/assets")
def assets(user=Depends(get_current_user)):
    return {
        "assets": [
            {"symbol": s, "name": s, "market": cfg["market"]}
            for s, cfg in ASSETS.items()
        ]
    }


@router.get("/timeframes")
def timeframes(user=Depends(get_current_user)):
    return {"timeframes": list(TIMEFRAMES.keys())}


@router.get("/ohlcv")
def ohlcv(
    symbol: str = Query(default="BTC/USD"),
    timeframe: str = Query(default="4H"),
    limit: int = Query(default=200, le=2000),
    live: int = Query(default=0, ge=0, le=1),
    user=Depends(get_current_user),
):
    symbol = normalize_symbol(symbol)
    try:
        provider = get_provider()
        bars = provider.get_ohlcv(symbol, timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stamped = apply_live_quote(bars[-limit:], symbol) if live else bars[-limit:]
    quote = live_quotes.get(symbol)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": stamped,
        "provider": getattr(provider, "name", "simulated"),
        "demo": getattr(provider, "name", "simulated") != "binance",
        "live_quote": quote,
    }


@router.get("/live")
def live_quotes_endpoint(user=Depends(get_current_user)):
    """Latest TradingView-sourced prices pushed via the alert webhook.

    Symbols without a fresh webhook quote are filled in from the active provider
    (simulated or Binance) so the board always has a price to display.
    """
    provider = get_provider()
    quotes = {}
    for symbol in ASSETS:
        quote = live_quotes.get(symbol)
        if quote is not None:
            quotes[symbol] = {
                "symbol": symbol,
                "price": quote["price"],
                "source": quote["source"],
                "updated_at": quote["updated_at"],
            }
            continue
        try:
            last = provider.latest_quote(symbol)["close"]
        except Exception:
            continue
        quotes[symbol] = {"symbol": symbol, "price": last, "source": "simulated", "updated_at": None}

    count_live = sum(1 for q in quotes.values() if q["source"] != "simulated")
    return {
        "provider": getattr(provider, "name", "simulated"),
        "live_count": count_live,
        "quotes": quotes,
    }


@router.get("/tick")
def live_tick(
    symbol: str = Query(default="XAUUSD"),
    user=Depends(get_current_user),
):
    """Real-time tick from Biquote (free, no API key). Returns bid/ask/mid."""
    from app.services.biquote_provider import biquote_provider
    symbol = normalize_symbol(symbol)
    tick = biquote_provider.get_tick(symbol)
    if not tick:
        raise HTTPException(status_code=503, detail="Biquote tick unavailable")
    return tick


@router.get("/ticks")
def live_ticks_batch(
    symbols: str = Query(default="XAUUSD,EUR/USD,GBP/USD"),
    user=Depends(get_current_user),
):
    """Batch real-time ticks from Biquote for multiple symbols."""
    from app.services.biquote_provider import biquote_provider
    symbol_list = [normalize_symbol(s.strip()) for s in symbols.split(",")]
    ticks = biquote_provider.get_ticks_batch(symbol_list)
    return {"ticks": ticks}


@router.get("/gold")
def gold_price(user=Depends(get_current_user)):
    """Live XAU/USD spot from XAUS (free, no API key)."""
    from app.services.xaus_provider import xaus_provider
    return xaus_provider.get_spot()


@router.get("/providers")
def available_providers(user=Depends(get_current_user)):
    """List available market data providers and their status."""
    import os
    providers = {
        "simulated": {"status": "active", "description": "Deterministic demo data"},
        "binance": {"status": "configured" if os.getenv("MARKET_DATA_PROVIDER") == "binance" else "available", "description": "Binance public API (crypto)"},
        "biquote": {"status": "configured" if os.getenv("MARKET_DATA_PROVIDER") == "biquote" else "available", "description": "Biquote free API (280+ forex/metals, no key)"},
        "gold_forex": {"status": "configured" if os.getenv("MARKET_DATA_PROVIDER") == "gold_forex" else "available", "description": "Multi-source gold+forex (Biquote+XAUS+gold-api+MintedMetal, no key)"},
        "finnhub": {"status": "configured" if os.getenv("FINNHUB_API_KEY") else "needs_api_key", "description": "Finnhub free API (US stocks, forex, crypto)"},
        "oanda": {"status": "configured" if os.getenv("OANDA_API_KEY") else "needs_api_key", "description": "OANDA free demo (forex + metals, execution)"},
        "mtsocket": {"status": "available", "description": "MTSocket free tier (XAUUSD + forex, WebSocket + REST)"},
        "xaus": {"status": "available", "description": "XAUS free gold spot (no key)"},
        "gold-api.com": {"status": "available", "description": "gold-api.com free (XAU/XAG/XPT/XPD, no rate limit)"},
        "mintedmetal": {"status": "available", "description": "MintedMetal LBMA prices (free, CC BY 4.0)"},
    }
    return {"providers": providers, "active": os.getenv("MARKET_DATA_PROVIDER", "simulated")}