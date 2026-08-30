# Session Log — TradePilot AI Production QA (Webhook / Railway)

Date: 2026-08-29
Environment: Windows, PowerShell 5.1. System Python is 3.14.4 (too new) — working
**venv uses Python 3.11.15** at `backend\venv\Scripts\python.exe` (all deps install/import cleanly).

---

# Session — 2026-08-31: Auto-trade engine + mobile app

## Objective
Make TradePilot a real trading product: analyse market data → **alerts** → **auto-execute**
on **Binance crypto**, paper-first with a manual arm-live switch; then ship a **mobile app**
for Play Store / App Store.

## Backend: auto-trade (Phase 1 — done, 73 tests green)
- New tables `AutoTradeConfig` + `Position` (models.py) with User relationships; schemas
  `AutoTradeConfigCreate/Update/Out`, `PositionOut`, `AutoTradeStatus`.
- `broker.py` (new): `Broker` protocol, `Fill`, `PaperBroker` (slippage, **timeframe-aware**
  fills via ctor param), `BinanceBroker` (signed spot order API, ticker price),
  `get_broker(mode, timeframe)` maps `paper`/`live`/`binance-live`.
- `autotrade.py` (new): `run_once()` → fresh signal per enabled config → sizing
  (`min(risk_amount/sl_distance, capital/entry)`) → open/close. **Empty exit group = hold
  until SL/TP** (handled by `_entry_and_exit_fired`). Risk caps: max_concurrent, cooldown,
  daily-loss cap; notifications on every open/close/error.
- `routes/autotrade.py` (new): status / config CRUD / positions / close / run-now;
  `mode=live` → 400 without server keys. `main.py`: router + background `monitor_loop`
  (asyncio + `to_thread`, interval ≥30s).
- **Simulated data generator bug fixed** (real): compounding drift made 15m/1H prices
  explode; mean-reversion `pull = -log(max(price,1e-9)/base)*0.01` keeps prices sane.
- **Walk-forward 500 fix**: backtests.py notification now falls back to
  `walk_forward.combined_metrics` (null best_metrics crash); 2 endpoint regression tests.
- Fixed during smoke: `MARKET_DATA_PROVIDER` import error, missing `Optional` import,
  empty-exit-group blocked entries, PaperBroker hardcoded 1H fill (→ timeframes), sizing now
  consistent (4H entry ≈52945, size 0.18887525, cost ≈ $10000, risk ≈ $90 = 1% risk/10k).
- Tests: `tests/test_autotrade.py` (8 tests). Full suite: **73 passed**. `.env.example`
  updated (AUTOTRADE_*, BINANCE_API_*).

## Mobile app (built, typecheck clean, SDK 53)
- `mobile/` Expo + React Native + strict TS; React Navigation tabs (Home, AutoTrade,
  Signals, Strategies, Settings); AsyncStorage JWT; API client with `EXPO_PUBLIC_API_URL`;
  dark theme; Login (login/signup/demo), Home (stats+signals+activity), AutoTrade
  (status/scan-now/toggles/positions close), Signals, Strategies, Settings (API URL/logout).
- `app.json` bundle ids, `eas.json` channels, `mobile/README.md` Play Store / App Store
  submission guide. `npx tsc --noEmit` clean; `npx expo config` valid. Phone = remote
  control; analysis/execution always in backend (paper-first, live arming guarded).

## Next Steps (not blocking)
- Deploy backend (Postgres + `MARKET_DATA_PROVIDER=binance`) behind HTTPS; set prod
  `EXPO_PUBLIC_API_URL` and run EAS builds.
- Optional: real Binance keys + arm a live config, and a Telegram/push notifier via
  `expo-notifications`.

---

# Session — 2026-08-30 (prior): Market data + optimizer + TradingView live

---

## Objective
Finish production QA on the "TradePilot AI" webhook/Railway architecture
(FastAPI backend + Next.js frontend), fix bugs, run the TradingView local webhook
test cases, add idempotency, run a security audit, create `TRADINGVIEW_SETUP.md`,
update `README.md`, and deliver the final production QA report.

No TradingView API key is used — TradePilot consumes TradingView **alert webhooks** only.

---

## Task Rules Followed
- AUDIT / FIX / TEST, not rewrite. Never fake results; verify every claim.
- Anti-hang: launch servers in background, test via HTTP with timeouts, kill only
  non-listening launchers.
- Trusted routes come from `/openapi.json`. Valid timeframes `15m,1H,4H,1D`.
- Valid assets from `/market/assets` (e.g. `BTC/USD`, `SOL/USD`).

---

## Completed Work

### 1. Backend audit + environment
- Recreated the Python 3.11.15 venv under `backend\venv`.
- All deps install and import cleanly.

### 2. P0 / bug fixes
- **TradingView webhook auth**: `_secret_is_valid` accepts the global secret OR any
  user's per-user `webhook_secret`.
- **`signals/generate` and `backtests/run`**: wrapped `ValueError` → clean **422**
  instead of **500**.
- **Root cleanup**: removed `vercel.json` (was routing all traffic to old
  `receiver.py`, breaking Vercel Next.js deploy), plus `receiver.py`,
  `trade_executor.py`, `signals.json`, `test.sh`, `PROJECT_SUMMARY.md`, root Flask
  `requirements.txt`, dead `webhook.py` route, dead `youtube_parser.py`.
- **Asset bug** (`ai_strategy_service.py`): Boom/crypto breakout no longer forced to
  `NAS100`.
- **Timeframe bug** (`_detect_timeframe`): no longer returns `50D`/`200D`; only
  emits supported `15m/1H/4H/1D` (plus `1W/1M` keywords); demo default restored
  (Golden Cross → `1D`).
- **Frontend webhook URL** (`frontend/pages/dashboard/tradingview.tsx`): now uses
  `API_URL + info.webhook_path`.
- **Security guard** (`backend/app/main.py`): `_assert_production_secrets()` refuses
  to boot in `ENVIRONMENT=production` with weak/too-short `JWT_SECRET` or
  `TRADINGVIEW_WEBHOOK_SECRET`.

### 3. Backend verification
- Live HTTP sweep of all OpenAPI routes passed with an `auth/demo` token.
- Clean DB migration: `alembic upgrade head` → `5fd272de1f65 initial schema`;
  all 10 tables + `alembic_version`. ORM CRUD + relationships + cascade work.
- Backtest trade history is JSON in `backtests.trade_history` (no separate table).

### 4. Frontend verification
- `npm run lint` PASS, `npx tsc --noEmit` PASS, `npm run build` PASS (17 routes).
- Functional HTTP check: `/`, `/login`, `/signup`, `/demo`, `/dashboard`,
  `/analyzer`, `/strategies`, `/signals`, `/backtesting`, `/performance`,
  `/tradingview`, `/notifications`, `/settings`, `/billing` all 200; `/404` → 404.
- `next start -p 3000` verified rendering.

### 5. E2E demo flow (verified live)
`GET /youtube/demo-strategies` → `POST /youtube/analyze` (demo fallback, Golden
Cross `ETH/USD` **1D**) → `POST /backtests/run` → `POST /signals/generate` →
`GET /performance/summary` (84 trades) → `/performance/equity` → `/monthly` →
`/strategies`.

### 6. TradingView webhook tests (all PASS, live)
- A missing secret → 401 ✓
- B wrong secret → 401 ✓
- C1 body = real global secret → 200 ✓
- C2 per-user secret → 200, signal created ✓
- C3 `X-Webhook-Secret` header → 200 ✓
- D WebhookEvents persisted ✓
- E Signal persisted ✓
- F `tradingview_alert` notification persisted ✓
- Dashboard intentionally masks global secret (`[:12] + "..."`) — correct security.

### 7. Security audit (all PASS)
- No hardcoded API keys/tokens in source.
- `.gitignore` excludes `.env`, `.env.local`, `*.db` (keeps `!.env.example`).
- CORS allows `localhost:3000`, `localhost:3001`, `https://tradepilot-ai.vercel.app`.
- JWT/OpenAI/webhook secrets/DATABASE_URL are backend-only (no frontend `.env`).
- Protected routes deny unauthenticated access (401/redirect).
- **User data isolation verified live**: user B cannot list or directly fetch user A's
  signal (list scoped by `user_id`; direct fetch → 404).

### 8. Idempotency (NEW this session)
- Added `_find_recent_dup_signal()` in `backend/app/api/routes/webhooks.py`,
  scoped by owner (`user_id`) + symbol + direction + entry_price + timeframe.
- Duplicate alert re-delivered within the 30-second window returns
  `{status:"duplicate", signal_id:<same>}` and creates NO new signal.
- **Verified live**: 1st POST → processed (signal 94); 2nd identical POST →
  duplicate (same signal 94).

### 9. Tests
- Created **`backend/tests/test_tradingview_webhook.py`** (8 tests) covering: valid
  payload + field parsing, symbol/direction/price/timeframe/timestamp capture,
  persistence, malformed → 422, invalid secret → 401, missing secret → 401,
  header-secret auth, idempotency (dup + non-dup), self-test auth.
- **Full backend suite: 44 passed, 0 failed** (35 prior + 8 new + 1 consolidation).

### 10. Docs (NEW this session)
- Created **`TRADINGVIEW_SETUP.md`** (endpoint, JSON schema, placeholder-based alert
  message template, local testing, Railway production, troubleshooting).
- Updated **`README.md`** (test count 44, TradingView section, link to setup doc).

---

## Final QA Report (summary)

**Webhook endpoint:** `POST /webhook/tradingview` — public but secret-required; 401 on
invalid/missing secret, 422 on malformed.

**Expected payload:**
```json
{ "secret": "<user or global secret>", "symbol": "BTC/USD", "direction": "LONG",
  "price": 65000.0, "timeframe": "4H", "strategy": "name", "timestamp": "ISO-8601" }
```

**Local test command:**
```powershell
cd backend
venv\Scripts\python.exe -m pytest tests\test_tradingview_webhook.py -v
```

**Test result:** 44 passed (full suite); live webhook + idempotency confirmed on a
restarted `http://127.0.0.1:8000`.

**Files changed this session:**
- `backend/app/api/routes/webhooks.py` (idempotency)
- `backend/tests/test_tradingview_webhook.py` (new)
- `TRADINGVIEW_SETUP.md` (new)
- `README.md` (updated)
- Earlier session fixes: `webhooks.py` auth, `ai_strategy_service.py` asset/timeframe,
  `main.py` prod guard, `tradingview.tsx` URL, root cleanup.

**Blocking production?** None functional. Only ordinary env vars needed
(`TRADINGVIEW_WEBHOOK_SECRET`, `JWT_SECRET`, `DATABASE_URL`, optional `OPENAI_API_KEY`).
No TradingView API key/credentials required. Railway/Vercel deploy + wiring a real alert
remain manual (see `TRADINGVIEW_SETUP.md`); the local webhook → FastAPI → validation →
database path is verified end-to-end, including idempotency.

---

# Session Log — Market Data + Parameter Optimizer + TradingView Live Prices

Date: 2026-08-31
Environment: Windows, PowerShell 5.1, `backend\venv\Scripts\python.exe` (Python 3.11.15),
Next.js frontend in `frontend\`.

## Objective
Continue production readiness: real-market-data provider, live prices via TradingView
alerts, strategy parameter optimizer + UI, XAUUSD-first live charts, a backtest-result
persistence bug fix, docs, and full verification.

## Completed Work

### 1. Market data service (`backend/app/services/market_data_service.py`)
- **38 supported symbols**: crypto (`BTC/USD`, `ETH/USD`, `SOL/USD`, …), metals
  (`XAUUSD`, `XAGUSD`, `XPTUSD`), indices (`US30`, `SPX500`, `US100`), energy (`USOIL`,
  `UKOIL`), FX (`EUR/USD`, `USD/JPY`, …).
- **Simulated provider** (default, deterministic synthetic OHLCV) named `simulated`.
- **Binance provider** (`MARKET_DATA_PROVIDER=binance`): real public klines for crypto
  pairs, in-memory cache, graceful fallback to simulated on network failure.
- **Symbol normalization**: `normalize_symbol()` / `tradingview_symbol()` with
  `TRADINGVIEW_ALIASES` — `BTCUSD`/`BTCUSDT` → `BTC/USD`, `EURUSD` → `EUR/USD`,
  `XAUUSD` stays `XAUUSD`, unknown symbols pass through.
- **Live-quote store**: `LiveQuoteStore` + `live_quotes` singleton +
  `get_live_quote()` / `apply_live_quote()`; freshness window `LIVE_QUOTE_TTL` (300s).

### 2. Live webhooks → prices (`webhooks.py`, `market.py`, `signal_engine.py`)
- `webhooks.py` now uses the shared `normalize_symbol()`; a valid alert containing a
  `price` refreshes the live-quote store; stored webhook symbols are canonical.
- `GET /market/live` (assets + live/simulated labels), `GET /market/ohlcv?live=1`
  (last-bar stamp + `live_quote` + `provider`).
- `signal_engine.py`: prefers a fresh live quote as the suggested entry price, adds
  `data_source` (`tradingview` | `simulated`), clamps confidence to [60, 95].

### 3. Parameter optimizer (`backend/app/services/optimizer.py`, `POST /backtests/optimize`)
- Dotted param paths (e.g. `entry.conditions.0.params.period`) auto-canonicalized to
  `rules.*` prefix; grid search + walk-forward (folds, combined metrics, combined equity).
- Metrics: return_percent, net_pnl, profit_factor, win_rate, max_drawdown, expectancy,
  average_r, sharpe_ratio, sortino_ratio, cagr, calmar_ratio. `max_drawdown` minimizes by
  default, everything else maximizes. Oversized grids rejected; representative best
  backtest persisted to history.
- **Bug found in smoke test**: walk-forward leaves `best_metrics` null → endpoint 500'd in
  the completion-notification line. Fixed to fall back to walk-forward `combined_metrics`
  (`backtests.py`). Regression tests added (endpoint-level, both modes).

### 4. Frontend
- **`components/TradingViewChart.tsx`** + **`pages/dashboard/tradingview.tsx`** ("TradingView
  Markets"): official TradingView chart widget defaulting to **OANDA:XAUUSD**, preset chips
  (metals/indices/FX/oil/crypto), live watchlist polled from `/market/live` every 20s.
- **`pages/dashboard/backtesting.tsx`**: XAUUSD/XAGUSD/US30/SPX500 default assets; new
  StatCards (Sharpe/Sortino/CAGR/Calmar) and the **Optimize strategy parameters** panel
  (metric/mode/folds/test-ratio/max-evals + dynamic param rows) with results cards
  (best params, top-5 table, walk-forward fold table + combined metrics).
- **`lib/types.ts`** extended: Backtest metrics (optional risk fields), OptimizationMetric /
  OptimizationResult, LiveQuote / MarketLive.
- **Backtest-result-vanishes bug**: result appeared then disappeared within 1s. No
  root-cause was found in backend (reproduced clean via TestClient) or CSS; applied a
  layered guarantee — result persisted to sessionStorage (key `tp_last_backtest_result`),
  restored on mount, previous result kept during runs/errors, Dismiss/delete clears
  storage, chart data hardened with `|| []`, page-level error boundary added in
  `pages/_app.tsx` so a dashboard crash can no longer blank the page.

### 5. Docs & env
- `backend/.env.example` + README env table: `MARKET_DATA_PROVIDER`, `BINANCE_BASE_URL`,
  `BINANCE_CACHE_TTL`, `LIVE_QUOTE_TTL`.
- `README.md`: "Market data & optimization" section, TradingView integration updates.
- `TRADINGVIEW_SETUP.md`: XAUUSD-first template, live-price/live-chart behavior, canonical
  symbol normalization (reverse of the old BTCUSD mapping).

## Verification
- **Backend tests**: `.\venv\Scripts\python.exe -m pytest tests -q` → **65 passed**.
  New suites: `tests/test_optimizer.py` (12, incl. 2 endpoint tests for the walk-forward
  fix), `tests/test_market_data.py` (7). Webhook symbol assertions updated to canonical
  (`BTC/USD`, `SOL/USD`).
- **Frontend**: `npx tsc --noEmit` clean; `npx next lint` clean.
- End-to-end smoke of `POST /backtests/optimize` for grid + walk-forward (XAUUSD, ad-hoc
  strategy) returned 200 with best params, persisted backtest_id and 3 folds.

## Known Notes / Caveats
- Live prices depend on alert webhooks carrying `price` (there is no free TradingView REST
  price API); before any alerts arrive the watchlist shows simulated values.
- Machine wall clock on Windows is non-monotonic — the LiveQuoteStore TTL test backdates
  `updated_at` instead of `time.sleep` (clock jitter can flake a sleep-based TTL test).
- `main.py` `on_event` startup is deprecated in FastAPI (lint warning only; not blocking).

## Produced / Updated Files
- `backend/app/services/market_data_service.py`, `optimizer.py`, `signal_engine.py`
- `backend/app/api/routes/webhooks.py`, `market.py`, `backtests.py`
- `backend/.env.example`, `backend/tests/test_optimizer.py`, `test_market_data.py`,
  `test_tradingview_webhook.py` (canonical-symbol assertions)
- `frontend/components/TradingViewChart.tsx`, `frontend/pages/dashboard/tradingview.tsx`,
  `frontend/pages/dashboard/backtesting.tsx`, `frontend/pages/_app.tsx`,
  `frontend/lib/types.ts`
- `README.md`, `TRADINGVIEW_SETUP.md`, `BACKEND_FRONTEND_PROGRESS.md`

## Next Steps (not blocking)
- Manual UI pass of the new optimizer panel + TradingView Markets page in the browser.
- Wire real TradingView alerts (with `{{close}}`) to see the watchlist flip to **Live**.
