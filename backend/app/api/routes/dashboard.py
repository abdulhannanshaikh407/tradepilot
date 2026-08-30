# app/api/routes/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import DashboardStats, SignalOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trades = db.query(models.Trade).filter(models.Trade.user_id == user.id).all()
    signals = (
        db.query(models.Signal)
        .filter(models.Signal.user_id == user.id)
        .order_by(models.Signal.created_at.desc())
        .limit(8)
        .all()
    )

    net_pnl = sum(t.pnl or 0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl or 0) > 0)
    portfolio_value = 10000.0 + net_pnl

    # Equity curve across trades + backtest curves for a fuller visual.
    running = 0.0
    points = [{"timestamp": "start", "equity": round(portfolio_value - net_pnl, 2)}]
    for t in sorted(trades, key=lambda x: x.entered_at or x.id):
        running += t.pnl or 0
        points.append(
            {
                "timestamp": (t.exited_at or t.entered_at or "").strftime("%Y-%m-%d"),
                "equity": round(portfolio_value - net_pnl + running, 2),
            }
        )

    backtests = (
        db.query(models.Backtest)
        .filter(models.Backtest.user_id == user.id)
        .order_by(models.Backtest.created_at.desc())
        .all()
    )
    strategy_perf = {}
    for b in backtests:
        metrics = b.metrics or {}
        name = b.strategy_name or "Strategy"
        bucket = strategy_perf.setdefault(name, {"trades": 0, "win_rate": 0.0, "return_percent": 0.0, "pf": 0.0})
        bucket["trades"] += metrics.get("total_trades", 0)
        bucket["win_rate"] = metrics.get("win_rate", bucket["win_rate"])
        bucket["return_percent"] = metrics.get("return_percent", bucket["return_percent"])
        bucket["pf"] = metrics.get("profit_factor", bucket["pf"])
    strategy_rows = [
        {
            "name": name,
            "asset": b.symbol if False else "—",
            "trades": v["trades"],
            "win_rate": round(v["win_rate"], 1),
            "return_percent": round(v["return_percent"], 1),
            "profit_factor": round(v["pf"], 2),
        }
        for name, v in strategy_perf.items()
    ][:8]

    recent_activity = []
    for n in (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user.id)
        .order_by(models.Notification.created_at.desc())
        .limit(6)
        .all()
    ):
        recent_activity.append(
            {
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
            }
        )

    active_signals = db.query(models.Signal).filter(
        models.Signal.user_id == user.id,
        models.Signal.status.in_(["PENDING", "ACTIVE"]),
    ).count()

    peak = portfolio_value - net_pnl
    max_dd = 0.0
    running_value = peak
    cur_peak = peak
    for p in points[1:]:
        running_value = p["equity"]
        cur_peak = max(cur_peak, running_value)
        if cur_peak > 0:
            max_dd = max(max_dd, (cur_peak - running_value) / cur_peak * 100)

    return DashboardStats(
        portfolio_value=round(portfolio_value, 2),
        net_pnl=round(net_pnl, 2),
        win_rate=round((wins / len(trades) * 100), 1) if trades else 0.0,
        active_signals=active_signals,
        total_trades=len(trades),
        max_drawdown=round(max_dd, 2),
        equity_curve=points,
        recent_signals=[SignalOut.model_validate(s) for s in signals],
        strategy_performance=strategy_rows,
        recent_activity=recent_activity,
    )


@router.get("/tradingview-info")
def tradingview_info(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.core.config import TRADINGVIEW_WEBHOOK_SECRET

    return {
        "global_secret": TRADINGVIEW_WEBHOOK_SECRET[:12] + "..." if TRADINGVIEW_WEBHOOK_SECRET else "",
        "user_secret": user.webhook_secret or "",
        "webhook_path": "/webhook/tradingview",
        "example_payload": {
            "secret": user.webhook_secret or TRADINGVIEW_WEBHOOK_SECRET,
            "symbol": "BTCUSD",
            "direction": "LONG",
            "price": 65000.0,
            "timeframe": "4H",
            "strategy": "RSI Momentum",
            "timestamp": "2026-08-28T12:00:00Z",
        },
    }