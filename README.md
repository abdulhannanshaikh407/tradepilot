# TradePilot AI

AI-powered trading strategy research, backtesting and signal intelligence.

Paste a YouTube strategy video URL → the AI extracts entry/exit rules → backtest
it on historical data → subscribe to live TradingView webhook alerts → track
performance on a clean dashboard. The demo workspace works out of the box with
**no API keys required**.

> **Disclaimer:** TradePilot is a research and education tool. All backtests,
> signals and demo data are simulated or historical — they are **not real
> performance** and never a guarantee of future results. No orders are ever
> placed through real brokers.

---

## Architecture

```
frontend/   Next.js 14 (TypeScript, Tailwind, Recharts) — billing-free SaaS UI
mobile/     Expo / React Native app for iOS + Android (Play Store / App Store)
backend/    FastAPI (Python 3.11, SQLAlchemy 2, Alembic)
  app/core/        config
  app/db/          models, schemas, database, seed (demo workspace)
  app/api/routes/  auth, youtube, strategies, signals, backtests, performance,
                   dashboard, webhooks, notifications, billing, settings, market,
                   autotrade
  app/services/    youtube transcript + AI extraction, backtest engine, signal
                   engine, market data, broker, autotrade engine, usage limits
   tests/           pytest suite (73 tests)
```

### Flow

```
YouTube URL ─▶ transcript ─▶ (OpenAI or deterministic fallback) ─▶ Strategy rules
Strategy  ─▶ Backtest engine (indicators, position sizing, SL/TP, walk-forward)
Strategy  ─▶ Signal engine  ─▶ Dashboard / Telegram / TradingView webhooks
Autotrade ─▶ monitor loop ─▶ signal ─▶ position sizing + SL/TP ─▶ paper or Binance
TradingView alert ─▶ POST /webhook/tradingview ─▶ signal + notification
```

---

## Quick start (local)

Prerequisites: Python 3.11+, Node 18+.

### 1. Backend

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate                 # Windows
# source venv/bin/activate              # macOS/Linux
pip install -r requirements.txt
cp .env.example .env                    # optional — sensible defaults exist
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API + interactive docs: http://localhost:8000/docs
- First startup creates the SQLite DB, a demo user and seeds in the background.
- No `.env` needed for the demo: topics analyze via the deterministic parser.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Click **Try the demo** (no account needed), or
sign up for a free account.

---

## Database migrations

The API creates tables automatically in development. For production, use Alembic:

```bash
cd backend
.\venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"
.\venv\Scripts\python.exe -m alembic upgrade head
```

The initial migration (`alembic/versions/*initial_schema.py`) is included.

---

## Tests

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests -v
```

The suite covers auth, YouTube analysis (with a fake transcript), the backtest
engine, signal engine, webhooks, the optimizer, the auto-trade engine (paper
fills, sizing, SL/TP closes, risk caps, live-arming guard) and a full
strategy→backtest→signal→dashboard flow. Tests run against a temporary SQLite
database — no network or API keys.

---

## Environment variables

See `backend/.env.example` for the full list:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./tradepilot.db` | DB connection (PostgreSQL for prod) |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret — **change it** |
| `OPENAI_API_KEY` | empty | Enables LLM extraction; empty = deterministic parser |
| `TRADINGVIEW_WEBHOOK_SECRET` | `tradepilot-webhook-secret` | Secret expected in webhook payloads |
| `MARKET_DATA_PROVIDER` | `simulated` | `simulated` (deterministic demo data) or `binance` (real crypto klines) |
| `BINANCE_BASE_URL` | `https://api.binance.com` | Binance API base for the real-data provider |
| `BINANCE_CACHE_TTL` | `120` | Seconds to cache Binance klines in memory |
| `LIVE_QUOTE_TTL` | `300` | Freshness window (s) for TradingView-pushed live prices |
| `CORS_ORIGINS` | localhost + Vercel | Comma-separated allowed origins |
| `ENVIRONMENT` / `DEBUG` | development / true | Logging + debug mode |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | empty | Optional Telegram alerting |
| `AUTOTRADE_ENABLED` | `true` | Run the background auto-trade monitor loop |
| `AUTOTRADE_INTERVAL` | `120` | Seconds between scans (min 30) |
| `AUTOTRADE_PAPER_CAPITAL` | `10000` | Default paper capital for new configs |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | empty | Required to arm LIVE execution |

Frontend: `frontend/.env` → `NEXT_PUBLIC_API_URL=http://localhost:8000`.

---

## Market data & optimization

- **38 supported symbols** — crypto (`BTC/USD`, `ETH/USD`, `SOL/USD`, …), metals (`XAUUSD`, `XAGUSD`, `XPTUSD`), indices (`US30`, `SPX500`, `US100`), energy (`USOIL`, `UKOIL`) and FX (`EUR/USD`, `USD/JPY`, …).
- **Simulated provider (default):** deterministic synthetic OHLCV per symbol/timeframe — fast, offline, reproducible.
- **Binance provider (`MARKET_DATA_PROVIDER=binance`):** real public klines for the crypto pairs, cached in memory, with graceful fallback to simulated on any network issue.
- **Live prices via TradingView:** alert webhooks that include a `price` feed the live-quote store (`GET /market/live`, `GET /market/ohlcv?live=1`, and the signal engine use them with a "Live" label / `data_source=tradingview`).
- **Optimization:** `POST /backtests/optimize` runs a grid search (or walk-forward) over dotted strategy parameter paths (e.g. `entry.conditions.0.params.period`), scoring on Sharpe / Sortino / CAGR / Calmar / return / PF / win rate / max-drawdown etc. The representative best backtest is saved to history. Use the panel on **Backtesting** in the UI.

## TradingView integration

See **[`TRADINGVIEW_SETUP.md`](./TRADINGVIEW_SETUP.md)** for the full, verified guide
(endpoint, payload schema, alert template, local testing, production).

Quick overview:

1. Open **Signals → TradingView** in the dashboard.
2. Copy your webhook URL (`…/webhook/tradingview`) and your **per-user secret**.
   (The shared global secret is intentionally hidden; use your own secret so alerts
   are attributed to you.)
3. Create a TradingView alert with **Webhook URL** set to the endpoint and a JSON body
   built from TradingView placeholders:

```json
{
  "secret": "YOUR_USER_SECRET",
  "symbol": "{{ticker}}",
  "direction": "{{strategy.order_action}}",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "strategy": "YOUR_STRATEGY_NAME",
  "timestamp": "{{timenow}}"
}
```

Each alert validates the secret, creates a `tradingview` signal, records a **Webhook
event**, and raises a notification. **Idempotency:** an identical alert re-delivered within
the 30-second dedup window does NOT create a duplicate signal. Invalid secrets are rejected
with 401 and recorded as `rejected`.

No TradingView API key is required — TradePilot only consumes alerts. Fire the endpoint from
the dashboard (*Send test alert*) or `POST /webhook/tradingview/test` to verify end-to-end
without a TradingView account.

### Live charts + live prices

The dashboard's **TradingView** page embeds the official TradingView chart (default symbol
**XAUUSD**, plus one-click presets for metals, indices, FX, oil and crypto). Every alert you
send with a `{{close}}` price also updates the live watchlist and is used as the signal
engine's suggested entry price. See [`TRADINGVIEW_SETUP.md`](./TRADINGVIEW_SETUP.md).

---

## Auto-trade (paper-first autonomous execution)

The backend runs a **monitor loop** (`app/services/autotrade.py`) that periodically scans
enabled strategies against fresh market data, fires signals, and **executes trades** —
paper by default, real via Binance only when explicitly armed.

- **Paper mode (default, zero setup):** fills happen against the same market data feed with
  slippage; capital, `risk_percent`, `max_concurrent`, cooldown and optional `max_daily_loss`
  caps are enforced. No keys, no real money.
- **Live mode (Binance spot):** set `BINANCE_API_KEY` / `BINANCE_API_SECRET` on the server
  (trading-only keys, no withdrawal permission) and switch a strategy config to `mode=live`.
  LONG-only (SHORT needs margin and is rejected), SL/TP enforced via the engine, exits are
  best-effort (network failures leave the position open until the next scan).
- **Risk caps:** per-trade risk = `risk_percent`% of capital (capped at `capital/entry`),
  stops are mandatory, `max_concurrent` blocks new entries while full, daily-loss cap stops
  the loop for new entries once crossed, cooldown prevents re-entering the same strategy too
  quickly. Every open/close/error produces a notification.
- **API:** `GET /autotrade/status`, `GET|POST /autotrade/config`, `PATCH|DELETE /autotrade/config/{strategy_id}`,
  `GET /autotrade/positions`, `POST /autotrade/positions/{id}/close`, `POST /autotrade/run-now`
  (see `/docs` for schemas).

> ⚠️ **Arming live trading is a deliberate, per-strategy action.** Nothing goes to a real
> exchange unless the server has keys AND the config is `mode=live`. Start in paper.

---

## Mobile app (Play Store / App Store)

`mobile/` is an Expo (React Native) companion: portfolio stats, live signals, auto-trade
engine control (toggle strategies, run a scan, open/close positions) and alerts — the phone
is a remote control; analysis and execution run in the backend. Build with EAS:

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=https://your-backend.example.com npx expo start   # dev
npx eas build -p android --profile production
npx eas build -p ios --profile production
```

See [`mobile/README.md`](./mobile/README.md) for store submission details.

---

## Deployment

> Full step-by-step runbook (Vercel + Render/Railway, env wiring, verification,
> troubleshooting): **[`DEPLOY.md`](./DEPLOY.md)**.

### Backend — Railway / Render / Fly.io (any platform that runs Python)

1. Push to your Git repo.
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set `DATABASE_URL` to managed PostgreSQL, `JWT_SECRET` to a random value,
   `ENVIRONMENT=production`, `CORS_ORIGINS` to your frontend domain.
5. Run migrations: `alembic upgrade head`.
6. Optional: set `MARKET_DATA_PROVIDER=binance` for live crypto data and
   `BINANCE_API_KEY`/`BINANCE_API_SECRET` to enable arming live auto-trades.

### Frontend — Vercel

1. Import the repo; root directory = `frontend/`.
2. Environment variable: `NEXT_PUBLIC_API_URL=https://your-backend.example.com`
3. Deploy. Next.js auto-detects the framework (no `vercel.json` needed).

### Mobile — EAS Build

1. `cd mobile && npm install`.
2. `eas login`, then `eas build -p android --profile production` and `eas build -p ios --profile production`.
3. `eas submit -p android` → Play Console, `eas submit -p ios` → App Store Connect.

---

## Project layout

```
backend/app/api/routes/    HTTP routes (protected by JWT + usage limits)
backend/app/services/       extraction, backtest, signals, market data
backend/tests/              pytest suite
frontend/pages/            landing + auth + dashboard pages
frontend/components/       shared UI (Layout, tables, charts, modals)
frontend/lib/              API client + auth context
```