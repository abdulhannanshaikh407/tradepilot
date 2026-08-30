# app/services/trading_adapter.py
"""Trading execution abstraction.

Only PAPER trading is implemented. A future broker adapter would implement the
same interface; live execution stays OFF by default and is explicitly labelled.
"""
from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.db import models


class TradingAdapter(Protocol):
    def execute(self, db: Session, signal: models.Signal, user_id: int) -> dict:
        ...


class PaperTradingAdapter:
    """Simulated fills — no real money, clearly labelled PAPER TRADING."""

    def execute(self, db: Session, signal: models.Signal, user_id: int) -> dict:
        entry = signal.entry_price
        size = None
        trade = models.Trade(
            user_id=user_id,
            signal_id=signal.id,
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            status=models.TradeStatus.OPEN.value,
            is_demo=signal.is_demo,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return {
            "status": "paper_filled",
            "trade_id": trade.id,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": entry,
            "message": "Paper trade opened (simulated). Live execution is not enabled.",
        }


class FutureBrokerAdapter:
    """Not implemented — reserved for a real broker integration."""

    def execute(self, db: Session, signal: models.Signal, user_id: int) -> dict:
        raise NotImplementedError(
            "Live broker execution is not enabled. Use the PaperTradingAdapter."
        )


def get_trading_adapter() -> TradingAdapter:
    return PaperTradingAdapter()