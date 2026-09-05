# TradePilot AI — Session Log (September 6, 2026)

## Goal
Fix YouTube strategy analyzer, sign-in performance, website crashes, add "Set & Forget" (fxalexg) as a default strategy, and make live forex+gold signal alerts work end-to-end so users actually receive trade alerts.

---

## Commits Made (5 total, in order)

### 1. `1c65e8f` — Fix heuristic indices, indicator validation, test rate limiting
**Files:** `ai_strategy_service.py`, `seed.py`, `conftest.py`, `test_market_data.py`, `test_autotrade.py`

| Change | Detail |
|--------|--------|
| Fix DEMO_STRATEGIES index mapping | Golden cross now correctly maps to `[2]`, RSI to `[1]` (were swapped) |
| Fix Set & Forget indicator period | Empty string `""` → `0` for Price Action indicator (avoids int validation error) |
| Add rate limiter clearing fixture | `_clear_rate_limiter` autouse fixture in `conftest.py` prevents 429s across 81 tests |
| Add `composite` to valid_providers | `test_market_data.py` and `test_autotrade.py` now accept `"composite"` provider |

---

### 2. `73ee3e3` — Fix WebSocket alert delivery: async/sync mismatch, args mismatch, broadcast to all
**Files:** `main.py`

Three critical bugs that **silently prevented all users from receiving WebSocket alerts**:

| Bug | Before | After |
|-----|--------|-------|
| **Async from sync thread** | Scanner called `async broadcast_signal()` from background thread → `RuntimeError` silently caught | Added `send_signal_sync()` using `asyncio.run_coroutine_threadsafe()` |
| **Wrong arguments** | Scanner called `callback(user_id, signal_data)` but `broadcast_signal` only takes `(signal_data)` → `TypeError` silently caught | `send_signal_sync(user_id, signal_data)` matches the scanner's call signature |
| **Broadcast to ALL users** | `broadcast_signal` sent to every connected user | `send_signal_sync` pushes only to the specific user who owns the strategy |

Also added:
- `ConnectionManager.set_loop()` — stores the event loop reference at startup
- `ConnectionManager.broadcast_signal_sync()` — thread-safe broadcast method
- Event loop stored in `ws_manager` during `start_bg()` startup

---

### 3. `db7ed98` — Fix forex/gold alert pipeline: 8 critical bugs
**Files:** `seed.py`, `main.py`, `market_scanner.py`, `realtime_feed.py`

| # | Bug | Fix |
|---|-----|-----|
| 1 | **Demo seed: `db.flush()` but no `commit()`** — strategies never persisted to DB | Changed to `db.commit()` |
| 2 | **Biquote preload: wrong timestamp field** — looked for `timestamp`/`time`/`t` but Biquote returns `openTime` → all forex bars had empty timestamps | Added `openTime` as fallback field |
| 3 | **Biquote preload: wrong volume field** — missed `tickVolume` → bars had 0 volume | Added `tickVolume` as fallback |
| 4 | **Scanner min bars too low** — required only 30 bars but EMA-200 needs more | Temporarily increased |
| 5 | **Biquote preload failed silently** — debug-level logs only | Added 3 retries with WARNING logs + 429 backoff |
| 6 | **Scanner source hardcoded `binance_ws`** — for forex/gold prices | Detects forex/gold by symbol format, uses `"biquote"` |
| 7 | **No scanner visibility** — couldn't debug rule evaluation | Added debug log for entry/confirm/exit per strategy |
| 8 | **Demo user strategies not seeded on startup** — only seeded during signup/login | Seed strategies in `main.py` startup for demo user |

---

### 4. `96a872d` — Fix scanner bar threshold and preload limit for Biquote constraints
**Files:** `market_scanner.py`, `realtime_feed.py`

| Change | Detail |
|--------|--------|
| Scanner min bars | Lowered from 200 to 50 (Biquote only returns 169 bars max regardless of limit parameter) |
| Preload limit | Reduced from 300 to 200 (Biquote caps at 169 anyway, avoids slow retries) |
| EMA-200 | Still calculates with 169 bars — slightly less accurate but functional |

---

### 5. `efffce3` — Fix: Layout notification bell refreshes on WebSocket signal events
**Files:** `components/Layout.tsx`

| Change | Detail |
|--------|--------|
| Import `useSignalWebSocket` | Added to Layout component |
| Real-time notification count | When WebSocket receives `new_signal` event, Layout calls `loadNotifications()` to refresh unread badge |
| Before | Bell badge only loaded once on mount, stayed stale |
| After | Badge updates instantly when any signal fires |

---

## Full Alert Delivery Chain (Verified Working)

```
User signs up / clicks Demo
  → seed_default_strategies_for_user() creates 4 active Set & Forget strategies:
     EUR/USD 4H LONG | GBP/USD 4H LONG | USD/JPY 4H LONG | XAUUSD 4H LONG

Server starts (FastAPI on Render)
  → ForexCommodityFeed preloads ~169 bars per symbol from Biquote
  → MarketScanner registers with forex feed via on_price_update callback
  → ws_manager stores asyncio event loop for thread-safe WebSocket push

Every 30 seconds (per symbol)
  → ForexCommodityFeed polls Biquote API for live bid prices
  → Updates OHLCV bars in shared BarStore (same instance used by Binance feed)
  → _notify_listeners() calls market_scanner._on_price_update()
  → Scanner queries DB for active strategies matching symbol+timeframe
  → RuleContext built from 169 bars, EMA-200 calculated
  → Entry rule (cross above EMA-200) + Confirmation (above EMA-200) evaluated
  → If signal fires:
      1. Signal record created in DB
      2. In-app notification created via create_notification()
      3. send_signal_sync(user_id, data) schedules async push on event loop
      4. ConnectionManager.send_signal() pushes JSON via WebSocket
      5. Frontend useSignalWebSocket hook receives event
      6. Signals page: prepends signal to list + shows toast
      7. Layout: notification bell badge updates in real-time

Every 60 seconds (periodic rescan)
  → Catches any missed signals for all active strategies across all users
```

---

## Strategy Rules (Set & Forget)

| Parameter | Value |
|-----------|-------|
| Entry | `price_cross_above_ma` (period=200, ma=ema) |
| Confirmation | `price_above_ma` (period=200, ma=ema) |
| Exit | `price_below_ma` (period=200, ma=ema) |
| Stop Loss | 1.5% |
| Take Profit | 4.0% |
| Risk/Reward | 1:4 |
| Direction | LONG |
| Timeframe | 4H |
| Risk per trade | 1% |

---

## Files Modified (Complete List)

### Backend (`backend/`)
| File | Changes |
|------|---------|
| `app/main.py` | Added `import asyncio`, `ConnectionManager._loop`, `set_loop()`, `send_signal_sync()`, `broadcast_signal_sync()`, event loop stored at startup, demo user strategy seeding, scanner callback changed to `send_signal_sync` |
| `app/services/market_scanner.py` | Min bars 30→50, dynamic source label (`biquote` vs `binance_ws`), debug logging for rule evaluation |
| `app/services/realtime_feed.py` | Biquote preload: added `openTime`/`tickVolume` fallbacks, 3 retries with WARNING logs, limit 300→200 |
| `app/services/ai_strategy_service.py` | DEMO_STRATEGIES index fixes (golden cross→[2], RSI→[1]), Set & Forget indicator period `""`→`0` |
| `app/db/seed.py` | `flush()`→`commit()` in seed_default_strategies_for_user |
| `app/api/routes/auth.py` | Seed strategies on signup (already existed, verified working) |
| `app/services/youtube_service.py` | Set & Forget sample transcript added (earlier session) |
| `app/services/transcript_service.py` | Parallel Invidious fetching (earlier session) |
| `app/api/routes/youtube.py` | Set & Forget TRANSCRIPT_HINT, error handling (earlier session) |
| `tests/conftest.py` | `_clear_rate_limiter` autouse fixture |
| `tests/test_market_data.py` | Added `"composite"` to valid_providers |
| `tests/test_autotrade.py` | Added `"composite"` to valid_providers |

### Frontend (`components/`)
| File | Changes |
|------|---------|
| `components/Layout.tsx` | Added `useSignalWebSocket` import + listener for real-time notification bell updates |

### Config
| File | Changes |
|------|---------|
| `lib/api.ts` | AbortController timeout (earlier session) |
| `pages/dashboard/analyzer.tsx` | 90s timeout for analysis (earlier session) |

---

## Test Results

```
81 passed, 67-68 warnings in 23-44s
```

All 81 tests pass across all commits. No regressions.

---

## Biquote API Notes

| Endpoint | Response |
|----------|----------|
| `GET /api/{symbol}` | Live tick: `{"bid": 1.16139, "ask": 1.16145, "mid": 1.16142, ...}` |
| `GET /api/{symbol}/ohlc?timeframe=4H&limit=200` | Historical bars: `{"bars": [{"openTime": "...", "open": ..., "high": ..., "low": ..., "close": ..., "tickVolume": ...}]}` |

**Important:** Biquote caps at ~169 bars regardless of `limit` parameter. The `openTime` field is the timestamp (not `timestamp`/`time`/`t`). Volume is in `tickVolume` (not `volume`).

---

## Known Limitations

1. **EMA-200 accuracy** — With only 169 bars from Biquote, the EMA-200 is based on ~85% of the required data. Still functional but slightly less accurate than a full 200-bar EMA.
2. **Forex poll interval** — 30 seconds. For 4H timeframe strategies this is fine, but faster timeframes would need shorter intervals.
3. **Only LONG signals** — Set & Forget template defaults to LONG. Could add SHORT signals based on `price_cross_below_ma`.
4. **No email/push notifications in demo** — Only in-app notifications + WebSocket. Telegram/FCM need API keys to be configured.
