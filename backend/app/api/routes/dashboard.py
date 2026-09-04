# app/api/routes/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.cache import cache
from app.db.database import get_db
from app.db import models
from app.db.schemas import DashboardStats, SignalOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cache_key = f"dashboard:{user.id}"
    cached = cache.get(cache_key)
    if cached:
        return DashboardStats(**cached)

    # SQL aggregates instead of loading ALL trades
    trade_agg = db.query(
        func.count(models.Trade.id).label("total"),
        func.coalesce(func.sum(models.Trade.pnl), 0).label("net_pnl"),
        func.coalesce(
            func.sum(case((models.Trade.pnl > 0, 1), else_=0)), 0
        ).label("wins"),
    ).filter(models.Trade.user_id == user.id).one()

    total_trades = trade_agg.total
    net_pnl = float(trade_agg.net_pnl)
    wins = int(trade_agg.wins)
    portfolio_value = 10000.0 + net_pnl

    # Equity curve: only fetch trades with pnl (much smaller result set)
    trade_rows = (
        db.query(models.Trade.pnl, models.Trade.entered_at, models.Trade.exited_at, models.Trade.id)
        .filter(models.Trade.user_id == user.id)
        .order_by(models.Trade.entered_at.asc())
        .all()
    )
    running = 0.0
    points = [{"timestamp": "start", "equity": round(portfolio_value - net_pnl, 2)}]
    for pnl, entered, exited, _ in trade_rows:
        running += pnl or 0
        ts = (exited or entered or "")
        points.append({
            "timestamp": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
            "equity": round(portfolio_value - net_pnl + running, 2),
        })

    # Max drawdown
    peak_val = portfolio_value - net_pnl
    max_dd = 0.0
    cur_peak = peak_val
    for p in points[1:]:
        cur_peak = max(cur_peak, p["equity"])
        if cur_peak > 0:
            max_dd = max(max_dd, (cur_peak - p["equity"]) / cur_peak * 100)

    # Recent signals (8)
    signals = (
        db.query(models.Signal)
        .filter(models.Signal.user_id == user.id)
        .order_by(models.Signal.created_at.desc())
        .limit(8)
        .all()
    )

    # Strategy performance: only latest backtest per strategy (not ALL backtests)
    strategy_perf = {}
    subq = (
        db.query(
            models.Backtest.strategy_name,
            func.max(models.Backtest.id).label("latest_id"),
        )
        .filter(models.Backtest.user_id == user.id)
        .group_by(models.Backtest.strategy_name)
        .subquery()
    )
    latest_backtests = (
        db.query(models.Backtest)
        .join(subq, models.Backtest.id == subq.c.latest_id)
        .limit(8)
        .all()
    )
    for b in latest_backtests:
        metrics = b.metrics or {}
        name = b.strategy_name or "Strategy"
        strategy_perf[name] = {
            "trades": metrics.get("total_trades", 0),
            "win_rate": metrics.get("win_rate", 0.0),
            "return_percent": metrics.get("return_percent", 0.0),
            "pf": metrics.get("profit_factor", 0.0),
        }
    strategy_rows = [
        {
            "name": name,
            "asset": "—",
            "trades": v["trades"],
            "win_rate": round(v["win_rate"], 1),
            "return_percent": round(v["return_percent"], 1),
            "profit_factor": round(v["pf"], 2),
        }
        for name, v in strategy_perf.items()
    ][:8]

    # Recent activity (6)
    recent_activity = []
    for n in (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user.id)
        .order_by(models.Notification.created_at.desc())
        .limit(6)
        .all()
    ):
        recent_activity.append({
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
        })

    active_signals = db.query(models.Signal).filter(
        models.Signal.user_id == user.id,
        models.Signal.status.in_(["PENDING", "ACTIVE"]),
    ).count()

    result = DashboardStats(
        portfolio_value=round(portfolio_value, 2),
        net_pnl=round(net_pnl, 2),
        win_rate=round((wins / total_trades * 100), 1) if total_trades else 0.0,
        active_signals=active_signals,
        total_trades=total_trades,
        max_drawdown=round(max_dd, 2),
        equity_curve=points,
        recent_signals=[SignalOut.model_validate(s) for s in signals],
        strategy_performance=strategy_rows,
        recent_activity=recent_activity,
    )

    cache.set(cache_key, result.model_dump(), ttl=60)
    return result


@router.get("/tradingview-info")
def tradingview_info(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.core.config import TRADINGVIEW_WEBHOOK_SECRET

    return {
        "global_secret": TRADINGVIEW_WEBHOOK_SECRET[:8] + "..." if TRADINGVIEW_WEBHOOK_SECRET else "",
        "user_secret": user.webhook_secret or "",
        "webhook_path": "/webhook/tradingview",
        "example_payload": {
            "secret": "YOUR_WEBHOOK_SECRET_HERE",
            "symbol": "BTCUSD",
            "direction": "LONG",
            "price": 65000.0,
            "timeframe": "4H",
            "strategy": "RSI Momentum",
            "timestamp": "2026-08-28T12:00:00Z",
        },
    }
