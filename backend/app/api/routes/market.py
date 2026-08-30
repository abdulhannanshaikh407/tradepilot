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