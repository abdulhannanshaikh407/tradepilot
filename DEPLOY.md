# Deploy Runbook — TradePilot AI

Goal: **Frontend in production on Vercel**, **backend (FastAPI + auto-trade engine) as an
always-on service on Render (or Railway)**, running **paper-only** trading on **real Binance
market data** (public klines, no keys). Live execution stays off until you deliberately add
keys and arm a strategy.

Architecture (why two hosts):

```
Vercel (Next.js)  ── HTTPS ──▶ Render/Railway (FastAPI + monitor_loop) ──▶ Binance klines (public)
                                    └── paper broker + SQLite/Postgres ──▶ no real orders
```

Vercel cannot host the backend: it's serverless (function timeouts, no persistent process),
so the 24/7 auto-trade `monitor_loop` and broker engine cannot run there.

---

## 0. One-time prep

1. Install the GitHub CLI (https://cli.github.com) and log in:
   ```bash
   gh auth login
   ```
2. Create the repo and push from this folder (PowerShell):
   ```powershell
   git init
   git add .
   git commit -m "TradePilot AI: backend + frontend + mobile (auto-trade, paper-first)"
   gh repo create tradepilot --public --source=. --push
   ```
   (`.gitignore` already excludes `venv/`, `node_modules/`, `.env`, `*.db`.)

---

## 1. Backend → Render (recommended)

1. Sign up at https://render.com (GitHub login, free plan).
2. **New+ → Web Service** (not Blueprint — Render Blueprints don't support
   `rootDirectory` in `render.yaml`).
3. Connect GitHub → select the **tradepilot** repo.
4. Fill in:
   - **Name:** `tradepilot-api`
   - **Root Directory:** `backend` ← critical, sets the working directory
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt` (auto-filled)
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment** add:
   - `PYTHON_VERSION` = `3.12`
   - `ENVIRONMENT` = `production`
   - `JWT_SECRET` = (click Generate)
   - `TRADINGVIEW_WEBHOOK_SECRET` = (click Generate)
   - `MARKET_DATA_PROVIDER` = `binance`
   - `AUTOTRADE_ENABLED` = `true`
   - `AUTOTRADE_INTERVAL` = `120`
   - `AUTOTRADE_PAPER_CAPITAL` = `10000`
   - `BINANCE_API_KEY` = (leave empty)
   - `BINANCE_API_SECRET` = (leave empty)
   - `CORS_ORIGINS` = `http://localhost:3000,https://YOUR-FRONTEND.vercel.app`
6. **Create Web Service** → wait for deploy → grab the URL (e.g. `https://tradepilot-api.onrender.com`).
3. On first deploy, grab the URL: `https://tradepilot-api.onrender.com`. Verify:
   ```bash
   curl https://tradepilot-api.onrender.com/
   curl https://tradepilot-api.onrender.com/docs
   ```
4. In the Render dashboard, open the service env settings and update:
   - `CORS_ORIGINS` → add your Vercel domain (from step 2, e.g. `https://tradepilot-ai.vercel.app`).
   - optional persistence: create a **Render Postgres**, copy its internal connection string
     into `DATABASE_URL` (the app creates tables on startup, SQLAlchemy sync engine).
   - `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` → optional, paste if you have them.
5. **Paper-only is enforced by defaults here:** `BINANCE_API_KEY` / `BINANCE_API_SECRET`
   stay empty, so arming `mode=live` returns HTTP 400. Real Binance market data still flows
   because `MARKET_DATA_PROVIDER=binance` (public API, no key).

> Note: free Render web services spin down after ~15 min idle — first request after idle
> wakes it (a few seconds). The auto-trade loop runs while the instance is awake. Paid
> Starter plan removes sleep.

### Alternative: backend → Railway (CLI)

```bash
npm i -g @railway/cli
railway login
railway init --name tradepilot     # run in this folder; backend/Procfile is honored
```
- Railway detects the Python app via Nixpacks (`web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` in `backend/Procfile`).
- In the dashboard → Variables add the same env values as step 4
  (`ENVIRONMENT=production`, `MARKET_DATA_PROVIDER=binance`, `CORS_ORIGINS=…`,
  `JWT_SECRET=<random>`, `AUTOTRADE_ENABLED=true`, `AUTOTRADE_INTERVAL=120`).
- `railway up` deploys. Add a Railway Postgres and set `DATABASE_URL` for persistence.

---

## 2. Frontend → Vercel

Option A — click (Vercel web):
1. Go to https://vercel.com/new, import the `tradepilot` GitHub repo.
2. **Root Directory = `frontend`** (framework auto-detected as Next.js; `vercel.json` forces it).
3. Environment variable: `NEXT_PUBLIC_API_URL=https://tradepilot-api.onrender.com`
4. Deploy. Result: `https://tradepilot-ai.vercel.app` (or your subdomain).

Option B — CLI:
```bash
npm i -g vercel
vercel login
cd frontend
vercel --prod
# answer: root already frontend; set env NEXT_PUBLIC_API_URL when prompted
```
After the first deploy, set the env var for prod via:
```bash
vercel env add NEXT_PUBLIC_API_URL production
```
then `vercel --prod` again.

---

## 3. Wire frontend + backend CORS

Add your exact Vercel domain to the backend `CORS_ORIGINS` (Render dashboard → env → save →
deploy). Two origins must match exactly: `https://tradepilot-ai.vercel.app` (no trailing slash)
in CORS, and `NEXT_PUBLIC_API_URL` pointing back to the Render URL.

---

## 4. Verify the whole thing

1. Open the Vercel URL → **Try the demo** (backend seeds a demo user at startup).
2. Dashboard loads portfolio metrics + **Binance-backed prices** (assets like `BTC/USD`,
   `ETH/USD` come from real klines — labelled according to provider).
3. **Auto-trade:** on the demo account, create a simple strategy, hit
   `POST /autotrade/run-now` (or from the mobile app later), then check
   `GET /autotrade/positions` shows an `OPEN` **paper** position with SL/TP.
4. Confirm `GET /autotrade/status` shows `"provider": "binance"` and `"live_available": false`.
5. Render logs show `Auto-trade monitor started (interval 120s)`.

---

## 5. Mobile app (after the backend is live)

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=https://tradepilot-api.onrender.com npx expo start   # dev
npx eas build -p android --profile production
npx eas build -p ios --profile production
```
See `mobile/README.md` for Play Store / App Store submission.

---

## 6. Going live later (deliberate, one-time)

Real execution is blocked until **both** are true:
1. Server `BINANCE_API_KEY` / `BINANCE_API_SECRET` are set (trading-only keys, **no**
   withdrawal permission — create at binance.com → API Management).
2. A strategy's auto-trade config is switched to `mode=live` (the API refuses without keys).

Recommended first step when you're ready: keep `mode=paper`, watch real paper fills on real
prices for a week, then arm one small config live. The engine enforces SL/TP, `risk_percent`,
`max_concurrent`, cooldown and a daily-loss cap.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Frontend CORS/network error | `CORS_ORIGINS` must contain the exact Vercel origin matching `NEXT_PUBLIC_API_URL` |
| `ImportError` during backend build | Set `PYTHON_VERSION=3.12` on the service (pinned in `render.yaml`) |
| Demo user missing | It's seeded at startup (`seed_demo_data`); redeploy or sign up manually |
| DB resets on redeploy | Add managed Postgres and set `DATABASE_URL` |
| `/autotrade/config` returns 400 on `mode=live` | Correct — keys aren't set. Paper mode is intentional |
| Auto-trade loop not running | `AUTOTRADE_ENABLED=true` and `AUTOTRADE_INTERVAL >= 30`; free-tier sleep stops scans until the instance wakes |