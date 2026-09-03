# app/services/market_scanner.py
"""Real-time market scanner.

Runs in the background, listening to price updates from the real-time feed.
On every price tick, evaluates ALL user strategies against the latest bars.
When entry + confirmation conditions fire, creates a Signal and pushes it
to the user via WebSocket + notifications.

This is the core engine that makes the bot find real trades in real-time.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db import models
from app.services.backtest_engine import RuleContext, evaluate_rule_group
from app.services.market_data_service import live_quotes
from app.services.signal_engine import build_strategy_rules_dict, describe_rule, reasons_for_group
from app.services.notification_service import create_notification

logger = logging.getLogger("tradepilot.scanner")

# How often to re-scan strategies that haven't fired (full rescan interval)
FULL_RESCAN_INTERVAL = 60  # seconds

# Dedup window: don't fire same signal for same symbol/strategy within N seconds
SIGNAL_DEDUP_WINDOW = 300  # 5 minutes

# Thread pool for parallel strategy evaluation
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="scanner")


class MarketScanner:
    """Evaluates user strategies against real-time price data.

    Architecture:
    1. Listens to price updates from RealtimeFeed
    2. For each price update, finds all strategies watching that symbol+timeframe
    3. Evaluates entry/confirmation/exit rules against the latest bars
    4. If signal fires: creates Signal record, pushes WebSocket alert, sends notification
    5. Maintains dedup to avoid spamming the same signal
    """

    def __init__(self):
        self._running = False
        self._last_scan: Dict[str, float] = {}  # key: "user_id:strategy_id" -> timestamp
        self._signal_dedup: Dict[str, float] = {}  # key: "symbol:direction:user_id" -> timestamp
        self._thread: Optional[threading.Thread] = None
        self._ws_callback = None  # Set by main.py to push signals via WebSocket

    def set_ws_callback(self, callback):
        """Set the WebSocket broadcast function. Called from main.py."""
        self._ws_callback = callback

    def _on_price_update(self, symbol: str, timeframe: str, bar: dict, price: float):
        """Called by RealtimeFeed on every price tick."""
        try:
            # Update the live quote store so the rest of the system sees real prices
            live_quotes.set(symbol, price, source="binance_ws", extra={
                "timeframe": timeframe,
                "high": bar.get("high"),
                "low": bar.get("low"),
                "volume": bar.get("volume"),
            })

            # Find and evaluate all strategies for this symbol+timeframe
            self._evaluate_strategies(symbol, timeframe, price)
        except Exception as e:
            logger.exception("Error in price update handler for %s: %s", symbol, e)

    def _evaluate_strategies(self, symbol: str, timeframe: str, current_price: float):
        """Find all active strategies for this symbol/timeframe and evaluate them."""
        db = SessionLocal()
        try:
            # Find all active auto-trade configs or strategies watching this symbol+timeframe
            strategies = (
                db.query(models.Strategy)
                .filter(
                    models.Strategy.is_active.is_(True),
                    models.Strategy.asset == symbol,
                    models.Strategy.timeframe == timeframe,
                )
                .all()
            )

            if not strategies:
                return

            # Get the bar store from the feed to build RuleContext
            from app.services.realtime_feed import feed as realtime_feed
            bars = realtime_feed.bar_store.get_bars(symbol, timeframe)

            if not bars or len(bars) < 30:
                # Not enough bars for indicator calculation
                return

            rctx = RuleContext(bars)
            i = len(bars) - 1  # Evaluate the latest bar

            for strategy in strategies:
                try:
                    self._evaluate_single_strategy(db, strategy, rctx, i, current_price, bars)
                except Exception as e:
                    logger.exception("Error evaluating strategy %d: %s", strategy.id, e)
        finally:
            db.close()

    def _evaluate_single_strategy(
        self, db: Session, strategy: models.Strategy,
        rctx: RuleContext, i: int, current_price: float, bars: list
    ):
        """Evaluate one strategy and fire signal if conditions are met."""
        dedup_key = f"{strategy.asset}:{strategy.direction}:{strategy.user_id}"

        # Check dedup
        last_signal_time = self._signal_dedup.get(dedup_key, 0)
        if time.time() - last_signal_time < SIGNAL_DEDUP_WINDOW:
            return

        # Build rules from the strategy
        rules = build_strategy_rules_dict(strategy)
        entry_group = rules["rules"]["entry"]
        confirm_group = rules["rules"]["confirmation"]
        exit_group = rules["rules"]["exit"]

        # Evaluate conditions
        entry_fired = evaluate_rule_group(rctx, i, entry_group)
        confirm_fired = evaluate_rule_group(rctx, i, confirm_group)
        exit_fired = evaluate_rule_group(rctx, i, exit_group)

        signal_fires = entry_fired and confirm_fired and not exit_fired

        if not signal_fires:
            return

        # Signal fired! Create it.
        entry_reasons = reasons_for_group(rctx, i, entry_group)
        confirm_reasons = reasons_for_group(rctx, i, confirm_group)
        reasons = [r for r in entry_reasons + confirm_reasons if r["fired"]]

        # Calculate stop loss and take profit
        stop_value = strategy.stop_loss_value
        stop_type = strategy.stop_loss_type
        target_value = strategy.take_profit_value
        target_type = strategy.take_profit_type
        is_long = (strategy.direction or "LONG").upper() == "LONG"

        stop_price = None
        if stop_value and stop_type == "percent":
            stop_price = current_price * (1 - stop_value / 100) if is_long else current_price * (1 + stop_value / 100)
        elif stop_value:
            stop_price = float(stop_value)

        target_price = None
        if target_value and target_type == "percent":
            target_price = current_price * (1 + target_value / 100) if is_long else current_price * (1 - target_value / 100)
        elif target_value:
            target_price = float(target_value)

        # Calculate risk/reward
        rr = None
        if stop_price and target_price:
            risk = abs(current_price - stop_price)
            reward = abs(target_price - current_price)
            if risk > 0:
                rr = round(reward / risk, 2)

        confidence = min(95, max(60, int(strategy.confidence or 70)))

        # Build reason text
        reason_text = "LIVE SIGNAL: "
        if reasons:
            reason_text += "; ".join(r["description"] for r in reasons[:4])
        else:
            reason_text = "Entry and confirmation conditions met."

        # Create the signal in the database
        signal = models.Signal(
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            symbol=strategy.asset,
            direction=strategy.direction or "LONG",
            entry_price=round(current_price, 6),
            stop_loss=round(stop_price, 6) if stop_price else None,
            take_profit=round(target_price, 6) if target_price else None,
            risk_reward=rr,
            confidence=confidence,
            reason=reason_text,
            status=models.SignalStatus.PENDING.value,
            source="realtime_scanner",
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)

        # Update dedup
        self._signal_dedup[dedup_key] = time.time()

        logger.info(
            "SIGNAL FIRED: %s %s @ %.6f | Strategy: %s | R:R: %s | Confidence: %d%%",
            strategy.direction, strategy.asset, current_price,
            strategy.name, rr, confidence,
        )

        # Create in-app notification
        notification_msg = (
            f"{strategy.direction} {strategy.asset} @ {current_price:.6f}\n"
            f"Strategy: {strategy.name}\n"
        )
        if stop_price:
            notification_msg += f"Stop Loss: {stop_price:.6f}\n"
        if target_price:
            notification_msg += f"Take Profit: {target_price:.6f}\n"
        if rr:
            notification_msg += f"Risk/Reward: 1:{rr}\n"
        notification_msg += f"Confidence: {confidence}%\n"
        notification_msg += f"Reason: {reason_text}"

        create_notification(
            db, strategy.user_id, "live_signal",
            f"🚨 {strategy.direction} Signal: {strategy.asset}",
            notification_msg,
            strategy.user.email if strategy.user else "",
        )

        # Push via WebSocket if available
        if self._ws_callback:
            signal_data = {
                "type": "new_signal",
                "signal": {
                    "id": signal.id,
                    "symbol": signal.symbol,
                    "direction": signal.direction,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "risk_reward": signal.risk_reward,
                    "confidence": signal.confidence,
                    "reason": signal.reason,
                    "status": signal.status,
                    "source": signal.source,
                    "strategy_name": strategy.name,
                    "created_at": signal.created_at.isoformat() if signal.created_at else None,
                },
            }
            try:
                self._ws_callback(strategy.user_id, signal_data)
            except Exception as e:
                logger.warning("WebSocket push failed for user %d: %s", strategy.user_id, e)

    def _periodic_rescan(self):
        """Periodic full rescan of all strategies (catches anything missed)."""
        from app.services.realtime_feed import feed as realtime_feed

        db = SessionLocal()
        try:
            strategies = (
                db.query(models.Strategy)
                .filter(models.Strategy.is_active.is_(True))
                .all()
            )

            for strategy in strategies:
                try:
                    bars = realtime_feed.bar_store.get_bars(strategy.asset, strategy.timeframe)
                    if not bars or len(bars) < 30:
                        continue

                    rctx = RuleContext(bars)
                    i = len(bars) - 1
                    current_price = bars[i]["close"]

                    self._evaluate_single_strategy(db, strategy, rctx, i, current_price, bars)
                except Exception as e:
                    logger.debug("Periodic rescan error for strategy %d: %s", strategy.id, e)
        finally:
            db.close()

    def _scan_loop(self):
        """Background loop that periodically rescans all strategies."""
        import asyncio
        from app.services.realtime_feed import feed as realtime_feed

        # Wait for initial bar data to load
        time.sleep(10)

        while self._running:
            try:
                self._periodic_rescan()
            except Exception as e:
                logger.exception("Periodic rescan failed: %s", e)

            # Sleep until next scan
            time.sleep(FULL_RESCAN_INTERVAL)

    def start(self):
        """Start the market scanner."""
        if self._running:
            return
        self._running = True

        # Register for price updates from the real-time feed
        from app.services.realtime_feed import feed as realtime_feed
        realtime_feed.on_price_update(self._on_price_update)

        # Start the periodic rescan loop
        self._thread = threading.Thread(target=self._scan_loop, daemon=True, name="market-scanner")
        self._thread.start()
        logger.info("Market scanner started")

    def stop(self):
        """Stop the market scanner."""
        self._running = False
        logger.info("Market scanner stopped")


# Singleton
scanner = MarketScanner()
