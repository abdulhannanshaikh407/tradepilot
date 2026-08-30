# TradingView Webhook Setup (TradePilot AI)

TradePilot ingests TradingView **alert webhooks** — it does **not** use a TradingView API key.
You configure a TradingView alert to POST a JSON payload to the app's webhook endpoint on
trigger. No TradingView credentials are required beyond your normal alert/account.

---

## 1. Webhook endpoint

| Method | Path | Auth |
|--------|------|------|
| POST | `/webhook/tradingview` | Webhook secret (body or `X-Webhook-Secret` header) |

Unauthenticated? The endpoint is public by design (TradingView can't send auth headers in
alerts), but it **requires a valid secret**. Invalid/missing secrets are rejected with
**HTTP 401** and recorded as `rejected` events.

Helpful supporting endpoints (both require a user bearer token):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/dashboard/tradingview-info` | Returns your per-user secret + example payload |
| GET | `/webhook/events` | List recent webhook events for your account |
| POST | `/webhook/tradingview/test` | Create a test alert instantly (no TradingView needed) |

---

## 2. Secrets (never hard-coded)

- **Global secret** — read from the `TRADINGVIEW_WEBHOOK_SECRET` environment variable
  (see `backend/.env.example` / `backend/app/core/config.py`). Production refuses to boot
  with a weak/too-short secret.
- **Per-user secret** — generated for each account and shown in the dashboard
  (`/dashboard/tradingview`). Use this to attribute alerts to your own account.

The dashboard deliberately **masks** the global secret (`abc...`); each user is expected to
use their own `user_secret`, which the dashboard shows in full and which `example_payload`
uses.

**TradingView compatibility:** the secret can be sent either in the JSON body
(`"secret"`) — the simplest and recommended — or via an `X-Webhook-Secret` header.

---

## 3. Expected JSON payload

`POST /webhook/tradingview` with `Content-Type: application/json`:

```json
{
  "secret": "YOUR_USER_SECRET_OR_GLOBAL_SECRET",
  "symbol": "BTC/USD",
  "direction": "LONG",
  "price": 65000.0,
  "timeframe": "4H",
  "strategy": "RSI Momentum",
  "timestamp": "2026-08-28T12:00:00Z"
}
```

Schema (`TradingViewWebhook`):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `secret` | string | no | Per-user or global secret. Missing/wrong → 401. |
| `symbol` | string | **yes** | e.g. `XAUUSD`, `BTCUSD`, `EURUSD`, `BTC/USD`, `US30`, `SPX500` |
| `direction` | string | no | `LONG`/`SHORT` (also accepts `BUY`/`SELL`/`BULL`/`BEAR`; normalised) |
| `price` | number | no | If present → a Signal is created **and the live-quote store is updated**. If absent → event only. |
| `timeframe` | string | no | e.g. `1m`, `15m`, `1H`, `4H`, `1D`. Stored on the event payload. |
| `strategy` | string | no | Alert/strategy name, used in the signal reason. |
| `timestamp` | string | no | Alert time (ISO-8601). |

On success (valid secret + price): HTTP **200** with

```json
{ "status": "processed", "signal_id": 94, "symbol": "XAUUSD", "direction": "LONG", "price": 2410.5 }
```

- A `Signal` is created (source `tradingview`) and a notification of type `tradingview_alert`
  is raised.
- A `WebhookEvent` is persisted for every delivery, `processed` or `rejected`.
- **Live prices:** a valid alert with a `price` refreshes the live-quote store. For the next
  `LIVE_QUOTE_TTL` seconds the price appears in `GET /market/live` (badged **Live**), stamps
  the last bar of `GET /market/ohlcv?live=1`, and is used as the signal engine's suggested
  entry price (`data_source: "tradingview"`).
- **Idempotency:** an identical alert (same owner, symbol, side, price) re-sent within the
  30-second dedup window returns `{ "status": "duplicate", "signal_id": <same> }` and does
  NOT create a duplicate signal.
- `symbol` and `direction` are normalised to canonical form: `BTCUSD`/`BTCUSDT` → `BTC/USD`,
  `XAUUSD` stays `XAUUSD`, `BUY` → `LONG`.
- Malformed JSON / missing required `symbol` → **HTTP 422**.

---

## 4. TradingView alert message template

Create a TradingView alert and set **"Webhook-URL"** to:

```
https://YOUR-RAILWAY-APP.UP.RAILWAY.APP/webhook/tradingview
```

(For local testing use `http://127.0.0.1:8000/webhook/tradingview`.)

**Message** — use TradingView's placeholder variables so every alert is a valid payload
(`{{interval}}` is the chart timeframe, `{{ticker}}` the symbol, `{{close}}` the close price,
`{{timenow}}` the current time). This example watches **XAUUSD**:

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

Notes:

- `{{ticker}}` arrives as `XAUUSD`, `BTCUSD`, `EURUSD`, `US30`, `SPX500`, `USOIL`, … — all of
  these map straight to the supported symbol list (`XAUUSD` stays `XAUUSD`, `BTCUSD` becomes
  `BTC/USD`, `EURUSD` → `EUR/USD`). These symbols power the live-chart presets on the
  **TradingView** dashboard page.
- Set the **side** in your strategy: emit `LONG`/`SHORT` (or `BUY`/`SELL`) into
  `strategy.order_action` (e.g. via `strategy.order_action == "buy"` checks). The endpoint
  also accepts a static `"direction": "LONG"`.
- **Recommended:** use your per-user `user_secret` for the `"secret"` value so the signal is
  attributed to your account.

---

## 5. Local testing (no TradingView needed)

FastAPI app running: `http://127.0.0.1:8000`

**Option A — automated test (full pipeline):**

```powershell
cd backend
venv\Scripts\python.exe -m pytest tests\test_tradingview_webhook.py -v
```

**Option B — instant self-test endpoint (authenticated):**

```powershell
curl -X POST http://127.0.0.1:8000/webhook/tradingview/test `
  -H "Authorization: Bearer <TOKEN>" `
  -H "Content-Type: application/json" `
  -d '{"symbol":"BTC/USD","direction":"LONG"}'
```

**Option C — raw POST (simulate a real TradingView alert):**

```powershell
curl -X POST http://127.0.0.1:8000/webhook/tradingview `
  -H "Content-Type: application/json" `
  -d '{"secret":"YOUR_USER_SECRET","symbol":"XAUUSD","direction":"LONG","price":2410.5,"timeframe":"4H","strategy":"Test","timestamp":"2026-08-28T12:00:00Z"}'
```

Then confirm in the dashboard (`/dashboard/tradingview`) or via `GET /webhook/events`.

---

## 6. Production (Railway)

1. Deploy the `backend` as a Railway service with a `web` start command:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. Set env vars on Railway: `TRADINGVIEW_WEBHOOK_SECRET`, `JWT_SECRET`,
   `OPENAI_API_KEY`, `DATABASE_URL`, ... (see `README.md` and `backend/.env.example`).
3. Use the Railway HTTPS URL in your TradingView alert webhook URL.
4. Keep `TRADINGVIEW_WEBHOOK_SECRET` strong; production refuses weak defaults.
5. CORS already allows `https://tradepilot-ai.vercel.app` (frontend) and localhost.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| HTTP 401 | Missing or wrong `secret`. Use your per-user secret or the global `TRADINGVIEW_WEBHOOK_SECRET`. |
| HTTP 422 | Missing required `symbol`, or malformed JSON. Fix the payload. |
| HTTP 200 but `signal_id` is `null` | No `price` in the payload — only an event was recorded. Add `price`. |
| HTTP 200 `status: duplicate` | The alert was re-delivered within the dedup window; no new signal (expected). |
| Alert fires but no signal | Verify `secret` + `price` present, and that you are viewing the owning account's signals. |
| `{{ticker}}` came through e.g. `BTCUSD=...` | Keep `ticker`/`close`/`interval`/`timenow` as plain placeholders in the message. |
