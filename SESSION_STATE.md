# TradePilot AI — Session State (Sep 4, 2026)

## Live URLs
- **Frontend:** https://tradepilot-psi-pearl.vercel.app
- **Backend:** https://tradepilot-xfk2.onrender.com
- **Health:** https://tradepilot-xfk2.onrender.com/health
- **API Docs:** https://tradepilot-xfk2.onrender.com/docs

## What's Working
- Backend on Render + PostgreSQL (Neon)
- Frontend on Vercel (auto-deploys from GitHub)
- CORS configured for Vercel ↔ Render (dynamic middleware)
- Real-time Binance WebSocket feed (19 crypto pairs, 4 timeframes)
- Market scanner (evaluates strategies on every price tick)
- **WebSocket real-time signal push** to browser
- **Web Push notifications** (device push even when site is closed)
- **Mobile push notifications** via FCM (when Firebase configured)
- Signup, login, demo, dashboard, backtests, signals, YouTube analysis
- In-app notifications (always active)
- Notification fan-out: in-app + web push + FCM + Telegram

## Push Notification Channels (All Free)
1. **In-app** — always on (database)
2. **WebSocket push** — real-time to browser when site is open
3. **Web Push (VAPID)** — device push even when browser is closed (NEW)
4. **FCM push** — mobile app push (needs Firebase project)
5. **Telegram** — free, needs bot token from @BotFather

## How Device Push Works
1. User visits Notifications page → clicks "Enable" on Device Push Notifications
2. Browser requests permission → service worker registers
3. Frontend gets VAPID public key from `/push/vapid-public-key`
4. Frontend subscribes via PushManager → sends subscription to `/push/subscribe`
5. Backend stores subscription in `device_tokens` table (platform=web)
6. When a signal fires → notification_service.py fans out to web push → browser shows notification

## Key Files
- `public/sw.js` — Service worker for background push
- `public/manifest.json` — PWA manifest
- `lib/usePushNotifications.ts` — Frontend push subscription hook
- `lib/useSignalWebSocket.ts` — Frontend WebSocket hook for real-time signals
- `backend/app/api/routes/push.py` — VAPID keys + subscription endpoints
- `backend/app/services/notification_service.py` — Fan-out to web push
- `pages/dashboard/notifications.tsx` — Push notification toggle UI
- `pages/dashboard/signals.tsx` — Real-time signal terminal

## Testing After Deploy
1. Open frontend → Login → go to /dashboard/signals → should see "Live" indicator
2. Go to /dashboard/notifications → click "Enable" on Device Push
3. Grant browser permission → should show "Active"
4. When a strategy fires a signal → get push notification on device

## Mobile Play Store (Manual Steps)
1. Create Firebase project → get `google-services.json` → put in `mobile/`
2. `cd mobile && eas login`
3. `eas build -p android --profile production`
4. `eas submit -p android`
5. Needs Google Play Developer account ($25)

## Render Env Vars to Set
- `TRADINGVIEW_WEBHOOK_SECRET` — generate: `python -c "import secrets; print('tp_wv_' + secrets.token_urlsafe(32))"`
- `CORS_ORIGINS` — already works via dynamic middleware (auto-allows *.vercel.app)

## Start Command
Just say "continue" or "start" and reference this file at `SESSION_STATE.md`.
