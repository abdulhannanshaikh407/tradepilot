# TradePilot AI — Session State (Sep 4, 2026)

## Live URLs
- **Frontend:** https://tradepilot-psi-pearl.vercel.app
- **Backend:** https://tradepilot-xfk2.onrender.com
- **Health:** https://tradepilot-xfk2.onrender.com/health
- **API Docs:** https://tradepilot-xfk2.onrender.com/docs

## Data Sources (ALL FREE, No API Keys)
| Source | Markets | Status |
|--------|---------|--------|
| Binance WebSocket | 19 crypto pairs (BTC, ETH, SOL, etc.) | ✅ Live streaming |
| Binance REST | Crypto OHLCV candles | ✅ Live |
| Biquote | 280+ forex/metals/indices/oil | ✅ Live |
| gold-api.com | XAU/XAG/XPT/XPD | ✅ Live |
| XAUS | Gold spot + 5yr history | ✅ Live |
| Finnhub | US stocks, forex, crypto | ✅ Free key |
| OANDA | Forex + metals (demo) | ✅ Free account |
| Alpaca | US stocks (paper + live) | ✅ Free account |

## Composite Provider (Default)
- **Crypto** → Binance WebSocket + REST
- **Forex** → Biquote (EUR/USD, GBP/USD, etc.)
- **Metals** → Biquote + gold-api.com + XAUS (XAUUSD, XAGUSD, etc.)
- **Indices** → Biquote (NAS100, US500, US30)
- **Oil** → Biquote (USOIL, UKOIL)
- **Last resort** → simulated (never crashes)

## 38 Tracked Assets
- 19 Crypto: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, DOT, LINK, AVAX, LTC, XLM, ATOM, UNI, TRX, NEAR, APT, FIL, SUI
- 7 Forex: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
- 4 Commodities: GOLD, XAUUSD, XAGUSD, XPTUSD, XPDUSD, USOIL, UKOIL
- 4 Indices: NAS100, US500, US30, SPX500, US100

## Broker Connectors (All Working)
| Broker | Markets | Frontend | Autotrade |
|--------|---------|----------|-----------|
| Binance | Crypto | ✅ | ✅ |
| Alpaca | US Stocks | ✅ | ✅ |
| OANDA | Forex + Metals | ✅ | ✅ |
| Paper | All (simulated) | ✅ | ✅ |

## What's Working
- Backend on Render + PostgreSQL (Neon)
- Frontend on Vercel (auto-deploys)
- Real-time Binance WebSocket feed (19 crypto pairs)
- Composite data provider (all markets from free sources)
- Market scanner (evaluates strategies on every price tick)
- WebSocket real-time signal push to browser
- Web Push notifications (device push even when site closed)
- In-app notifications
- Signup, login, demo, dashboard, backtests, signals
- YouTube analysis (Invidious API fallback)
- TradingView webhook alerts
- 3 broker connectors (Binance, Alpaca, OANDA)
- Auto-trade engine with multi-broker routing
- Dynamic CORS middleware

## Start Command
Just say "continue" or "start" and reference this file at `SESSION_STATE.md`.
