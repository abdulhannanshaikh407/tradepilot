# TradePilot AI — Session State (Sep 5, 2026)

## Live URLs
- **Frontend:** https://tradepilot-psi-pearl.vercel.app
- **Backend:** https://tradepilot-xfk2.onrender.com
- **Health:** https://tradepilot-xfk2.onrender.com/health
- **API Docs:** https://tradepilot-xfk2.onrender.com/docs

## Cost: $0/month (all free tier)
| Service | Free Tier |
|---------|-----------|
| Vercel (frontend) | Unlimited |
| Render (backend) | 750 hrs/mo |
| Database | SQLite (local) or Neon PostgreSQL (free) |
| Redis | In-memory fallback (no Redis needed) |
| Binance (crypto) | Unlimited public API |
| Biquote (forex/metals) | Unlimited, no key |
| gold-api.com | Free, no key |
| Groq AI | 30 req/min |
| Google Gemini AI | 15 req/min |
| Finnhub | 60 calls/min |
| Web Push (VAPID) | Free, browser-native |

## Security Hardening (This Session)
- Encryption: Fernet AES-128 only (no base64 fallback)
- CORS: Locked to exact Vercel URL (no wildcard)
- Auth rate limit: 10 req/min per IP on login/signup/demo
- JWT expiry: 60 minutes (was 7 days)
- Token refresh: `/auth/refresh` endpoint
- Webhook secret: Never exposed in API responses
- OpenAPI docs: Bearer token auth scheme in Swagger UI

## 38 Tracked Assets
- 19 Crypto: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, DOT, LINK, AVAX, LTC, XLM, ATOM, UNI, TRX, NEAR, APT, FIL, SUI
- 7 Forex: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
- 7 Commodities: GOLD, XAUUSD, XAGUSD, XPTUSD, XPDUSD, USOIL, UKOIL
- 5 Indices: NAS100, US500, US30, SPX500, US100

## Broker Connectors
| Broker | Markets | Status |
|--------|---------|--------|
| Binance | Crypto | Paper + Live |
| Alpaca | US Stocks | Paper + Live |
| OANDA | Forex + Metals | Paper + Live |
| Paper | All (simulated) | Always |

## What's Working
- Real-time Binance WebSocket feed (19 crypto pairs)
- Composite data provider (all markets from free sources)
- Market scanner (evaluates strategies on every price tick)
- WebSocket real-time signal push to browser
- Web Push notifications (device push even when site closed)
- In-app notifications
- Signup, login, demo, dashboard, backtests, signals
- YouTube analysis with AI extraction (Groq/Gemini/heuristic)
- TradingView webhook alerts
- 3 broker connectors (Binance, Alpaca, OANDA)
- Auto-trade engine with multi-broker routing
- 87 API routes, all passing security audit

## Start Command
Just say "continue" or "start" and reference this file at `SESSION_STATE.md`.
