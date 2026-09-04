# app/api/routes/performance.py
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import PerformanceSummary

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/summary", response_model=PerformanceSummary)
def summary(
    strategy_id: Optional[int] = None,
    asset: Optional[str] = None,
    timeframe: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # SQL aggregates instead of loading ALL trades
    q = db.query(
        func.count(models.Trade.id).label("total"),
        func.coalesce(func.sum(models.Trade.pnl), 0).label("net_pnl"),
        func.coalesce(func.sum(models.Trade.r_multiple), 0).label("total_r"),
        func.coalesce(
            func.sum(case((models.Trade.pnl > 0, models.Trade.pnl), else_=0)), 0
        ).label("gross_profit"),
        func.coalesce(
            func.sum(case((models.Trade.pnl < 0, func.abs(models.Trade.pnl)), else_=0)), 0
        ).label("gross_loss"),
        func.coalesce(
            func.sum(case((models.Trade.pnl > 0, 1), else_=0)), 0
        ).label("wins"),
    ).filter(models.Trade.user_id == user.id)

    if asset:
        q = q.filter(models.Trade.symbol == asset.upper())

    agg = q.one()
    total = agg.total
    wins = int(agg.wins)
    losses = total - wins
    net_pnl = float(agg.net_pnl)
    gross_profit = float(agg.gross_profit)
    gross_loss = float(agg.gross_loss)
    total_r = float(agg.total_r)

    # Max drawdown (needs ordered equity walk - limited to recent 500 trades for performance)
    recent_trades = (
        db.query(models.Trade.pnl)
        .filter(models.Trade.user_id == user.id)
        .order_by(models.Trade.entered_at.asc())
        .limit(500)
        .all()
    )
    equity_walk = 0.0
    peak = 0.0
    max_dd = 0.0
    for (pnl,) in recent_trades:
        equity_walk += pnl or 0
        peak = max(peak, equity_walk)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity_walk) / peak * 100)

    return PerformanceSummary(
        total_trades=total,
        winning_trades=wins,
        losing_trades=losses,
        win_rate=(wins / total * 100) if total else 0.0,
        net_pnl=round(net_pnl, 2),
        return_percent=round((net_pnl / 10000.0) * 100, 2) if total else 0.0,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else (gross_profit or 0.0),
        expectancy=round(net_pnl / total, 2) if total else 0.0,
        max_drawdown=round(max_dd, 2),
        average_r=round(total_r / total, 2) if total else 0.0,
        total_backtests=db.query(models.Backtest)
        .filter(models.Backtest.user_id == user.id)
        .count(),
        total_strategies=db.query(models.Strategy)
        .filter(models.Strategy.user_id == user.id)
        .count(),
        total_signals=db.query(models.Signal)
        .filter(models.Signal.user_id == user.id)
        .count(),
        active_signals=db.query(models.Signal)
        .filter(models.Signal.user_id == user.id, models.Signal.status.in_(["PENDING", "ACTIVE"]))
        .count(),
    )


@router.get("/strategies")
def strategy_performance(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate backtest metrics per strategy for comparison charts."""
    # Single query with join instead of N+1
    subq = (
        db.query(
            models.Backtest.strategy_id,
            func.max(models.Backtest.id).label("latest_id"),
        )
        .join(models.Strategy, models.Strategy.id == models.Backtest.strategy_id)
        .filter(models.Strategy.user_id == user.id)
        .group_by(models.Backtest.strategy_id)
        .subquery()
    )
    latest_backtests = (
        db.query(models.Backtest, models.Strategy)
        .join(subq, models.Backtest.id == subq.c.latest_id)
        .join(models.Strategy, models.Strategy.id == models.Backtest.strategy_id)
        .all()
    )

    rows = []
    for bt, strat in latest_backtests:
        metrics = bt.metrics or {}
        rows.append({
            "strategy_id": strat.id,
            "name": strat.name,
            "asset": strat.asset,
            "timeframe": strat.timeframe,
            "win_rate": metrics.get("win_rate", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "return_percent": metrics.get("return_percent", 0),
            "net_pnl": metrics.get("net_pnl", 0),
            "total_trades": metrics.get("total_trades", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "trade_count": metrics.get("total_trades", 0),
        })
    rows.sort(key=lambda r: r["return_percent"], reverse=True)
    return {"strategies": rows}


@router.get("/assets")
def asset_performance(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # SQL GROUP BY instead of loading ALL trades
    rows_data = (
        db.query(
            models.Trade.symbol,
            func.count(models.Trade.id).label("trades"),
            func.coalesce(
                func.sum(case((models.Trade.pnl > 0, 1), else_=0)), 0
            ).label("wins"),
            func.coalesce(func.sum(models.Trade.pnl), 0).label("pnl"),
        )
        .filter(models.Trade.user_id == user.id)
        .group_by(models.Trade.symbol)
        .order_by(models.Trade.symbol)
        .all()
    )
    rows = [
        {
            "symbol": r.symbol,
            "trades": r.trades,
            "win_rate": (int(r.wins) / r.trades * 100) if r.trades else 0,
            "net_pnl": round(float(r.pnl), 2),
        }
        for r in rows_data
    ]
    return {"assets": rows}


@router.get("/equity")
def equity_curve(
    strategy_id: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(
        models.Trade.pnl, models.Trade.entered_at, models.Trade.exited_at
    ).filter(models.Trade.user_id == user.id)
    if strategy_id:
        q = q.filter(models.Trade.strategy_id == strategy_id)
    trades = q.order_by(models.Trade.entered_at.asc()).all()

    running = 0.0
    points = [{"timestamp": "start", "equity": round(running, 2)}]
    for pnl, entered, exited in trades:
        running += pnl or 0
        ts = exited or entered or ""
        points.append({
            "timestamp": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
            "equity": round(running, 2),
        })
    return {"equity_curve": points}


@router.get("/monthly")
def monthly_performance(
    strategy_id: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(
        models.Trade.pnl,
        models.Trade.exited_at,
        models.Trade.entered_at,
    ).filter(models.Trade.user_id == user.id)
    if strategy_id:
        q = q.filter(models.Trade.strategy_id == strategy_id)
    trades = q.all()

    months: dict = {}
    for pnl, exited, entered in trades:
        date = exited or entered
        key = date.strftime("%Y-%m") if date else "?"
        bucket = months.setdefault(key, {"pnl": 0.0, "trades": 0, "wins": 0})
        bucket["pnl"] += pnl or 0
        bucket["trades"] += 1
        if (pnl or 0) > 0:
            bucket["wins"] += 1
    rows = [{"period": k, **v} for k, v in sorted(months.items())]
    return {"monthly": rows}
