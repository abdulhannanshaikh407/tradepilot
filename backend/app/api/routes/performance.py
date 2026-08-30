# app/api/routes/performance.py
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import PerformanceSummary

router = APIRouter(prefix="/performance", tags=["performance"])


def _backtest_stats(db: Session, user: models.User, strategy_id: Optional[int] = None) -> list:
    query = db.query(models.Backtest).filter(models.Backtest.user_id == user.id)
    if strategy_id:
        query = query.filter(models.Backtest.strategy_id == strategy_id)
    return query.order_by(models.Backtest.created_at.desc()).limit(20).all()


@router.get("/summary", response_model=PerformanceSummary)
def summary(
    strategy_id: Optional[int] = None,
    asset: Optional[str] = None,
    timeframe: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trades_query = db.query(models.Trade).filter(models.Trade.user_id == user.id)
    if asset:
        trades_query = trades_query.filter(models.Trade.symbol == asset.upper())
    trades = trades_query.all()

    wins = sum(1 for t in trades if (t.pnl or 0) > 0)
    losses = len(trades) - wins
    net_pnl = sum(t.pnl or 0 for t in trades)
    total_r = sum(t.r_multiple or 0 for t in trades)
    gross_profit = sum(t.pnl for t in trades if (t.pnl or 0) > 0)
    gross_loss = abs(sum(t.pnl for t in trades if (t.pnl or 0) < 0))

    equity_walk = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.exited_at or x.entered_at or x.id):
        equity_walk += t.pnl or 0
        peak = max(peak, equity_walk)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity_walk) / peak * 100)

    return PerformanceSummary(
        total_trades=len(trades),
        winning_trades=wins,
        losing_trades=losses,
        win_rate=(wins / len(trades) * 100) if trades else 0.0,
        net_pnl=round(net_pnl, 2),
        return_percent=round((net_pnl / 10000.0) * 100, 2) if trades else 0.0,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else (gross_profit or 0.0),
        expectancy=round(net_pnl / len(trades), 2) if trades else 0.0,
        max_drawdown=round(max_dd, 2),
        average_r=round(total_r / len(trades), 2) if trades else 0.0,
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
    strategies = db.query(models.Strategy).filter(models.Strategy.user_id == user.id).all()
    rows = []
    for strategy in strategies:
        backtests = (
            db.query(models.Backtest)
            .filter(models.Backtest.strategy_id == strategy.id)
            .order_by(models.Backtest.created_at.desc())
            .limit(1)
            .all()
        )
        if not backtests:
            continue
        metrics = backtests[0].metrics or {}
        trades = (
            db.query(models.Trade)
            .filter(models.Trade.strategy_id == strategy.id)
            .count()
        )
        rows.append(
            {
                "strategy_id": strategy.id,
                "name": strategy.name,
                "asset": strategy.asset,
                "timeframe": strategy.timeframe,
                "win_rate": metrics.get("win_rate", 0),
                "profit_factor": metrics.get("profit_factor", 0),
                "return_percent": metrics.get("return_percent", 0),
                "net_pnl": metrics.get("net_pnl", 0),
                "total_trades": metrics.get("total_trades", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "trade_count": trades,
            }
        )
    rows.sort(key=lambda r: r["return_percent"], reverse=True)
    return {"strategies": rows}


@router.get("/assets")
def asset_performance(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assets = {}
    trades = db.query(models.Trade).filter(models.Trade.user_id == user.id).all()
    for t in trades:
        bucket = assets.setdefault(t.symbol, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += 1 if (t.pnl or 0) > 0 else 0
        bucket["pnl"] += t.pnl or 0
    rows = [
        {
            "symbol": symbol,
            "trades": v["trades"],
            "win_rate": (v["wins"] / v["trades"] * 100) if v["trades"] else 0,
            "net_pnl": round(v["pnl"], 2),
        }
        for symbol, v in sorted(assets.items())
    ]
    return {"assets": rows}


@router.get("/equity")
def equity_curve(
    strategy_id: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trades = (
        db.query(models.Trade).filter(models.Trade.user_id == user.id)
    )
    if strategy_id:
        trades = trades.filter(models.Trade.strategy_id == strategy_id)
    trades = trades.order_by(models.Trade.entered_at.asc()).all()

    running = 0.0
    points = [{"timestamp": "start", "equity": round(running, 2)}]
    for t in trades:
        running += t.pnl or 0
        points.append(
            {
                "timestamp": (t.exited_at or t.entered_at or "").strftime("%Y-%m-%d"),
                "equity": round(running, 2),
            }
        )
    return {"equity_curve": points}


@router.get("/monthly")
def monthly_performance(
    strategy_id: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trades = (
        db.query(models.Trade).filter(models.Trade.user_id == user.id)
    )
    if strategy_id:
        trades = trades.filter(models.Trade.strategy_id == strategy_id)
    months: dict = {}
    for t in trades.all():
        date = t.exited_at or t.entered_at
        key = date.strftime("%Y-%m") if date else "?"
        bucket = months.setdefault(key, {"pnl": 0.0, "trades": 0, "wins": 0})
        bucket["pnl"] += t.pnl or 0
        bucket["trades"] += 1
        if (t.pnl or 0) > 0:
            bucket["wins"] += 1
    rows = [
        {"period": k, **v}
        for k, v in sorted(months.items())
    ]
    return {"monthly": rows}