# app/api/routes/backtests.py
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import BacktestOut, BacktestRequest, OptimizeRequest
from app.services import backtest_engine, optimizer, usage_service
from app.services.backtest_engine import strategy_to_engine_form
from app.services.notification_service import create_notification

router = APIRouter(prefix="/backtests", tags=["backtests"])


def _resolve_engine_strategy(
    db: Session,
    user: models.User,
    strategy_id: Optional[int],
    strategy_name: Optional[str],
    symbol: str,
    timeframe: str,
) -> Tuple[Optional[models.Strategy], dict, str, str]:
    """Return (orm strategy or None, engine-form strategy, symbol, timeframe)."""
    strategy = None
    if strategy_id:
        strategy = (
            db.query(models.Strategy)
            .filter(models.Strategy.id == strategy_id, models.Strategy.user_id == user.id)
            .first()
        )
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found.")

    symbol = symbol.upper()
    if strategy is not None:
        if not strategy_name:
            symbol = strategy.asset
            timeframe = strategy.timeframe
        engine_strategy = strategy_to_engine_form(strategy)
    else:
        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_id or strategy_name is required.")
        # Adhoc strategy — a sensible default breakout template for quick tests.
        rules = {
            "entry": {"logic": "all", "conditions": [
                {"condition": "price_breakout_above", "params": {"period": 20}},
            ]},
            "confirmation": {"logic": "all", "conditions": [
                {"condition": "price_above_ma", "params": {"period": 100, "ma": "ema"}},
            ]},
            "exit": {"logic": "any", "conditions": [
                {"condition": "price_breakdown_below", "params": {"period": 20}},
            ]},
        }
        engine_strategy = {
            "strategy_name": strategy_name,
            "name": strategy_name,
            "direction": "LONG",
            "asset": symbol,
            "timeframe": timeframe,
            "rules": rules,
            "entry_rules": rules["entry"]["conditions"],
            "confirmation_rules": rules["confirmation"]["conditions"],
            "exit_rules": rules["exit"]["conditions"],
            "stop_loss_type": "percent",
            "stop_loss_value": 1.0,
            "take_profit_type": "percent",
            "take_profit_value": 2.0,
        }
    return strategy, engine_strategy, symbol, timeframe


def _persist_backtest(
    db: Session,
    user: models.User,
    step,
) -> models.Backtest:
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.post("/run", response_model=BacktestOut, status_code=status.HTTP_201_CREATED)
def run_backtest(
    payload: BacktestRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, _ = usage_service.check_and_increment(db, user, "backtests")
    if not allowed:
        raise HTTPException(status_code=429, detail="Backtest limit reached for today.")

    strategy, engine_strategy, symbol, timeframe = _resolve_engine_strategy(
        db, user, payload.strategy_id, payload.strategy_name, payload.symbol, payload.timeframe
    )

    try:
        result = backtest_engine.run_backtest(
            strategy=engine_strategy,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=payload.initial_capital,
            risk_percent=payload.risk_percent,
            fee_percent=payload.fee_percent,
            slippage_percent=payload.slippage_percent,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot run backtest: {exc}")

    backtest = models.Backtest(
        user_id=user.id,
        strategy_id=strategy.id if strategy else None,
        strategy_name=payload.strategy_name or (strategy.name if strategy else engine_strategy.get("strategy_name")),
        symbol=symbol,
        timeframe=timeframe,
        start_date=payload.start_date or (result["equity_curve"][0]["timestamp"] if result["equity_curve"] else None),
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        risk_percent=payload.risk_percent,
        fee_percent=payload.fee_percent,
        slippage_percent=payload.slippage_percent,
        metrics=result["metrics"],
        equity_curve=result["equity_curve"],
        trade_history=result["trade_history"],
        monthly_performance=result["monthly_performance"],
        wl_distribution=result["wl_distribution"],
        is_demo=strategy.is_demo if strategy else False,
    )
    _persist_backtest(db, user, backtest)

    create_notification(
        db,
        user.id,
        "backtest_complete",
        "Backtest complete",
        f"{backtest.strategy_name} on {symbol} {timeframe}: {result['metrics']['total_trades']} trades, "
        f"{result['metrics']['return_percent']}% return.",
        user.email,
    )
    return BacktestOut.model_validate(backtest)


@router.post("/optimize")
def optimize_backtest(
    payload: OptimizeRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, _ = usage_service.check_and_increment(db, user, "backtests")
    if not allowed:
        raise HTTPException(status_code=429, detail="Backtest limit reached for today.")

    strategy, engine_strategy, symbol, timeframe = _resolve_engine_strategy(
        db, user, payload.strategy_id, payload.strategy_name, payload.symbol, payload.timeframe
    )
    oc = payload.optimization

    try:
        result = optimizer.optimize(
            strategy=engine_strategy,
            symbol=symbol,
            timeframe=timeframe,
            parameters=[p.model_dump() for p in oc.parameters],
            metric=oc.metric,
            direction=oc.direction,
            mode=oc.mode,
            folds=oc.folds,
            test_ratio=oc.test_ratio,
            max_evals=oc.max_evals,
            max_bars=oc.max_bars,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_capital=payload.initial_capital,
            risk_percent=payload.risk_percent,
            fee_percent=payload.fee_percent,
            slippage_percent=payload.slippage_percent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot optimize: {exc}")

    response = dict(result)
    response["request"] = {
        "strategy_id": strategy.id if strategy else None,
        "strategy_name": engine_strategy.get("strategy_name"),
        "symbol": symbol,
        "timeframe": timeframe,
    }

    # Persist a representative backtest (best grid run, or combined walk-forward)
    # so the result also shows up in backtest history.
    is_demo = strategy.is_demo if strategy else False
    strategy_name = engine_strategy.get("strategy_name") or "Optimized strategy"
    try:
        if result["mode"] == "walk_forward" and result.get("walk_forward"):
            wf = result["walk_forward"]
            cm = wf["combined_metrics"]
            pers = {
                "metrics": cm,
                "equity_curve": wf.get("combined_equity_curve", []),
                "trade_history": wf.get("combined_trade_history", []),
                "monthly_performance": wf.get("combined_monthly_performance", []),
                "wl_distribution": {
                    "wins": cm.get("winning_trades", 0),
                    "losses": cm.get("losing_trades", 0),
                    "total": cm.get("total_trades", 0),
                },
            }
            saved_name = f"{strategy_name} (walk-forward)"
        else:
            best_strategy = optimizer.apply_params(engine_strategy, result.get("best_params") or {})
            pers = backtest_engine.run_backtest(
                strategy=best_strategy,
                symbol=symbol,
                timeframe=timeframe,
                initial_capital=payload.initial_capital,
                risk_percent=payload.risk_percent,
                fee_percent=payload.fee_percent,
                slippage_percent=payload.slippage_percent,
                start_date=payload.start_date,
                end_date=payload.end_date,
            )
            saved_name = f"{strategy_name} (optimized)"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot persist optimized backtest: {exc}")

    backtest = models.Backtest(
        user_id=user.id,
        strategy_id=strategy.id if strategy else None,
        strategy_name=saved_name,
        symbol=symbol,
        timeframe=timeframe,
        start_date=payload.start_date or (pers["equity_curve"][0]["timestamp"] if pers["equity_curve"] else None),
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        risk_percent=payload.risk_percent,
        fee_percent=payload.fee_percent,
        slippage_percent=payload.slippage_percent,
        metrics=pers["metrics"],
        equity_curve=pers["equity_curve"],
        trade_history=pers["trade_history"],
        monthly_performance=pers["monthly_performance"],
        wl_distribution=pers["wl_distribution"],
        is_demo=is_demo,
    )
    _persist_backtest(db, user, backtest)

    bm = result.get("best_metrics") or {}
    if result["mode"] == "walk_forward" and result.get("walk_forward"):
        bm = result["walk_forward"].get("combined_metrics") or {}
    create_notification(
        db,
        user.id,
        "backtest_complete",
        "Optimization complete",
        f"{saved_name} tested {result['grid_total_evals']} combinations. "
        f"Best: {bm.get('return_percent')}% return, {bm.get('sharpe_ratio')} Sharpe.",
        user.email,
    )
    response["backtest_id"] = backtest.id
    return response


@router.get("/", response_model=list[BacktestOut])
def list_backtests(
    strategy_id: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: int = 100,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Backtest).filter(models.Backtest.user_id == user.id)
    if strategy_id:
        query = query.filter(models.Backtest.strategy_id == strategy_id)
    if symbol:
        query = query.filter(models.Backtest.symbol == symbol.upper())
    backtests = query.order_by(models.Backtest.created_at.desc()).limit(min(limit, 500)).all()
    return [BacktestOut.model_validate(b) for b in backtests]


@router.get("/{backtest_id}", response_model=BacktestOut)
def get_backtest(
    backtest_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backtest = (
        db.query(models.Backtest)
        .filter(models.Backtest.id == backtest_id, models.Backtest.user_id == user.id)
        .first()
    )
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found.")
    return BacktestOut.model_validate(backtest)


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest(
    backtest_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backtest = (
        db.query(models.Backtest)
        .filter(models.Backtest.id == backtest_id, models.Backtest.user_id == user.id)
        .first()
    )
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found.")
    db.delete(backtest)
    db.commit()
    return None