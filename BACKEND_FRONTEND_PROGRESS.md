# TradePilot AI — Session Summary

## Objective (latest)
1. **Auto-trade**: analyse market data -> generate alerts -> **trade** (Binance crypto), paper-first with a manual arming switch. Done + tested in `backend/`.
2. **Mobile app** for Play Store / App Store (`mobile/`, Expo 53 + React Native, strict TS) — built, typechecked, build/submit via EAS.
3. **Deployment**: backend on Render, frontend on Vercel, **LIVE** at:
   - Backend: https://tradepilot-xfk2.onrender.com
   - Frontend: https://frontend-l6we17khh-abdulhannanshaikh407s-projects.vercel.app
   - GitHub: https://github.com/abdulhannanshaikh407/tradepilot

## Backend: auto-trade engine (done, verified via pytest — **73 tests green**)
- **`app/db/models.py`**: `AutoTradeConfig` (enabled, mode paper/live, capital, risk_percent, slippage_percent, max_concurrent, max_daily_loss, cooldown_minutes, last_run_at, last_error) + `Position` (symbol, direction, broker, status, entry/current/stop/take, size, cost, pnl, exit_reason, opened_at, closed_at) + User relationships.
- **`app/core/config.py`**: `AUTOTRADE_ENABLED` (default true), `AUTOTRADE_INTERVAL` (120s, loop only when >=30), `AUTOTRADE_PAPER_CAPITAL` (10000), `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_SPOT_ENDPOINT`.
- **`app/services/broker.py`**: `Broker` protocol, `Fill`, `PaperBroker` (market-price fills with slippage; **timeframe-aware** constructor param so fills use the signal's timeframe, not a hardcoded 1H), `BinanceBroker` (signed `POST /api/v3/order`, `quoteOrderQty`/`quantity`, ticker price), `get_broker(mode, timeframe)` maps `paper`/`live`/`binance-live`.
- **`app/services/autotrade.py`**: `run_once()` scans enabled configs -> fresh signal per strategy -> sizing (`risk% = min(risk_amount/sl_distance, capital/entry)`) -> enter/exit. Semantics: **empty exit rule group = "hold until SL/TP"** (via `_entry_and_exit_fired`), NOT the signal engine's empty-group=exit behavior. Risk caps: `max_concurrent`, cooldown, daily-loss cap, size cap; every open/close/error -> notification. Notifications fall back to `combined_metrics` when no single best metric exists (walk-forward fix).
- **`app/api/routes/autotrade.py`**: `GET /autotrade/status`, `GET|POST /autotrade/config`, `PATCH|DELETE /autotrade/config/{strategy_id}`, `GET /autotrade/positions`, `POST /autotrade/positions/{id}/close`, `POST /autotrade/run-now`. `mode=live` rejected with 400 when server keys are missing.
- **`app/main.py`**: router registered; startup starts a background `monitor_loop` (`asyncio` task -> `asyncio.to_thread(autotrade.run_once)` every `AUTOTRADE_INTERVAL` when enabled + >=30s); `seed_demo_data` in same handler.
- **Simulated data generator bug fixed** (real pre-existing): positive drift compounded prices to absurd levels on 15m/1H. Added mean reversion `pull = -log(max(price,1e-9)/base) * 0.01` per bar; prices sane across 15m/1H/4H/1D.
- **Walk-forward 500 bug fixed** earlier this session: `POST /backtests/optimize` walk-forward mode crashed on null `best_metrics`; now falls back to `walk_forward.combined_metrics`.
- **New tests**: `tests/test_autotrade.py` (paper pricing/slippage, engine opens sized position, no duplicate entry, SL/TP close via engine, max_concurrent stop, live-guard without keys, manual close endpoint, status endpoint). Current suite: **73 passed**.
- `.env.example` updated with auto-trade + Binance vars.

## Mobile app (built, `npx tsc --noEmit` clean, `expo config` valid — SDK 53)
- `mobile/` Expo app: React Navigation tabs (Home, AutoTrade, Signals, Strategies, Settings), AsyncStorage JWT, API client (`src/api.ts`, `EXPO_PUBLIC_API_URL`, `ApiError`), dark theme + shared UI components.
- Screens: Login (login/signup/demo), Home (stats + latest signals + activity), AutoTrade (engine status, scan-now, strategy toggles, open/close positions), Signals, Strategies, Settings (API URL, logout).
- `app.json` (com.tradepilot.app, android + ios), `eas.json` (development/preview/production, autoIncrement), `mobile/README.md` store-submission guide.
- **Safety**: phone is a remote control; analysis/execution live in backend; live arming requires server keys + explicit `mode=live`.

## Backend: market data + optimizer (prior, still green)
- 38 symbols, Binance klines provider (`MARKET_DATA_PROVIDER=binance`, 120s cache, fallback to simulated), `LiveQuoteStore` + `/market/live`, `/market/ohlcv?live=1`, webhook symbol normalization, signal engine uses live quotes (`data_source`), optimizer (grid + walk-forward), risk-adjusted metrics.
- TradingView integration: `TRADINGVIEW_SETUP.md` updated (XAUUSD-first template, live prices); dashboard TradingView page with OANDA XAUUSD chart + presets + 20s watchlist poll.
- Backtest-vanishing fix: `tp_last_backtest_result` sessionStorage + `PageErrorBoundary` in `_app.tsx`.

## Old Objective (original session)
Bring TradePilot AI toward production readiness (backend FastAPI + frontend Next.js).

## Backend (all done, verified via `pytest`)

### Market data — `backend/app/services/market_data_service.py`
- Asset list extended to 38 symbols: metallics (XAUUSD, XAGUSD, XPTUSD, XPDUSD), indices/FX/energy (US30, SPX500, US100, USOIL, UKOIL, EURUSD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD) + ~16 Binance crypto pairs.
- `BinanceMarketDataProvider`: real `BTCUSDT`-style klines via public Binance API (filters only crypto pairs), 120s cache, graceful fallback to simulated. Activated with `MARKET_DATA_PROVIDER=binance` env var. Default remains `simulated` so tests/CI never touch the network.
- New `normalize_symbol()` / `tradingview_symbol()`: TradingView tickers (XAUUSD, BTCUSD, EURUSD) ↔ canonical symbols (XAUUSD, BTC/USD, EUR/USD). Aliases map XAUUSD→XAUUSD (was previously forced to GOLD).
- New `LiveQuoteStore` (`live_quotes` singleton): fresh prices pushed by TradingView alert webhooks, TTL ~300s (`LIVE_QUOTE_TTL`), tracks source ("tradingview" vs simulated).
- Helpers: `get_live_quote()`, `apply_live_quote()` (stamps last OHLCV bar with real price).

### Webhooks — `backend/app/api/routes/webhooks.py`
- Now uses the shared `normalize_symbol()` (no more inline SYMBOL_MAP; XAUUSD stays XAUUSD).
- Valid alerts with a price now record the price into `live_quotes` (source `tradingview`).

### Market API — `backend/app/api/routes/market.py`
- `GET /market/live` → all supported symbols with last prices; symbols with fresh TradingView quotes labeled `source: "tradingview"`, others fall back to the active provider ("simulated"). Also returns `live_count`.
- `GET /market/ohlcv?live=1` → stamps the last bar with the live quote and includes `live_quote`; response carries `provider` + `demo`.

### Signal engine — `backend/app/services/signal_engine.py`
- When a fresh live quote exists, it is used for the suggested `entry_price`/ST/TP; result includes `data_source: "tradingview" | "simulated"`. Confidence clamped to [60, 95].

### Optimizer — `backend/app/services/optimizer.py` (+ `db/schemas.py`, `api/routes/backtests.py`)
- Grid search + walk-forward + out-of-sample split; dotted param paths (`entry.conditions.0.params.period`) auto-canonicalized to `rules.*`; `apply_params()` public.
- Metrics include risk-adjusted: sharpe_ratio, sortino_ratio, cagr, calmar_ratio, recovery_factor, annualized_volatility (added in `backtest_engine.py`).
- `POST /backtests/optimize` persists a representative backtest (best grid run or combined walk-forward), sends `backtest_complete` notification, returns `backtest_id`.

## Frontend (all done, verified via `tsc --noEmit` + `next lint`)

- **`components/TradingViewChart.tsx`** (new): official TradingView Advanced Chart embed widget (`s3.tradingview.com` external-embedding script), dark theme, RSI+MACD studies, `allow_symbol_change`, plus `TV_PRESETS` symbol list (XAUUSD→OANDA:XAUUSD, BTCUSD→BINANCE:BTCUSDT, EURUSD→FX:EURUSD, indices, USOIL…) and `canonicalTvSymbol()`.
- **`pages/dashboard/tradingview.tsx`**: now titled "TradingView Markets". Top card = live chart (default **XAUUSD**, OANDA feed) + preset chips + live watchlist grid polled from `/market/live` every 20s (labels "Live" for webhook-sourced, "Sim" otherwise). Webhook integration, test alert button, event table and alert-message example (now XAUUSD) kept below.
- **`pages/dashboard/backtesting.tsx`**: defaults include XAUUSD/XAGUSD/US30/SPX500; results now show Sharpe, Sortino, CAGR and Calmar StatCards.
- **`lib/types.ts`**: `Backtest.metrics` gained `sharpe_ratio/sortino_ratio/cagr/calmar_ratio/recovery_factor/annualized_volatility` (optional); added `LiveQuote` + `MarketLive` types.

## Tests
- 44 existing → **63 passed** (`backend\venv\Scripts\python.exe -m pytest tests -q` from `backend`, **never** system Python 3.14).
- New: `tests/test_optimizer.py` (grid best + OOS, no-OOS when ratio=0, max_drawdown minimize default, oversize grid rejected, unknown metric/direction/empty params rejected, walk-forward 3 folds + combined metrics, apply_params, param_values), `tests/test_market_data.py` (default provider simulated, symbol aliases, XAUUSD supported, unknown symbol rejected, LiveQuoteStore roundtrip + TTL expiry by backdating timestamp — avoid wall-clock sleeps; machine clock jitters), `/market/live`, `/market/assets`, `/market/ohlcv?live=1`.
- Updated `test_webhook.py`/`test_tradingview_webhook.py` symbol assertions to canonical form (`BTC/USD`, `SOL/USD`) since webhooks now normalize symbols.

## Environment / how-to-run
- Windows PowerShell; backend venv: `C:\Users\User\Desktop\AI trading bot\backend\venv\Scripts\python.exe`.
- Start backend: `.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` (from `backend`).
- Start frontend: `npm run dev` (from `frontend`).
- Real data opt-in: set `MARKET_DATA_PROVIDER=binance`; live XAUUSD prices: configure a TradingView alert webhook with price → `{{close}}` (see in-app "TradingView Alert Message" example).

## Known notes / gotchas
- Edit tool intermittently mangled indentation in optimizer.py earlier; fixed via inline Python script. If new backend edits break imports: `.\venv\Scripts\python.exe -c "import app.services.optimizer"`.
- Machine wall clock has jitter (non-monotonic): don't test TTL with `time.sleep`.
- TradingView has no free REST price API; live prices come from alert webhooks; live charts come from the official embed widget.