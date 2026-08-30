# TradePilot AI — Mobile App (Expo / React Native)

Native iOS + Android companion app for your TradePilot backend: portfolio stats,
live AI signals, auto-trade engine control (paper first, arm live), open/close
positions, and alerts.

## Stack

- **Expo SDK 53** + React Native **0.79** + TypeScript (strict)
- **React Navigation** bottom tabs (Home, AutoTrade, Signals, Strategies, Settings)
- **AsyncStorage** for the JWT session token
- **EAS Build / Submit** for Play Store + App Store releases

## Run locally

```bash
cd mobile
npm install
npx expo start          # press a for Android emulator, i for iOS simulator
```

Point Expo Go / the emulator at a running backend:

```bash
# Android emulator reaches the host at 10.0.2.2
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 npx expo start

# iOS simulator / same machine
EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start
```

Create a `.env` file (Expo picks up `EXPO_PUBLIC_*` automatically):

```
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

## Where trading actually happens

The phone is a **remote control** — all analysis, taps, and risk caps live in the
backend (`backend/app/services/autotrade.py`). The app:

1. shows engine status + open positions (`GET /autotrade/status`, `/autotrade/positions`),
2. toggles monitored strategies (`GET/PATCH /autotrade/config`),
3. triggers a scan (`POST /autotrade/run-now`) and closes positions (`POST /autotrade/positions/{id}/close`).

**Live trading is paper-safe by default.** Live execution only activates when the
backend runs with `BINANCE_API_KEY`/`BINANCE_API_SECRET` AND a strategy config is
set to `mode=live` (LONG-only on spot, SL/TP enforced, cooldown + daily-loss caps).

## Validation

```bash
npx tsc --noEmit     # strict typecheck
```

## Release to Play Store / App Store

1. **Set the API URL for production** — `.env.production`:
   ```
   EXPO_PUBLIC_API_URL=https://api.yourdomain.com
   ```
2. Add icons/splash: replace `assets/icon.png` (1024×1024),
   `assets/splash.png` (1284×2778), `assets/adaptive-icon.png` (1024×1024).
3. Install EAS: `npm i -g eas-cli` then `eas login`.
4. Android:
   ```bash
   npx eas build -p android --profile production
   npx eas submit -p android          # uploads to Play Console
   ```
   Keep the **Google Play App Signing** key created by EAS — you need it for every
   future upload.
5. iOS:
   ```bash
   npx eas build -p ios --profile production
   npx eas submit -p ios              # uploads to App Store Connect
   ```
   You need an Apple Developer account ($99/yr); EAS handles signing once you add
   your Apple credentials in `eas credentials`.

## Notes

- HTTP-only login on physical devices: the store build must talk to a **HTTPS**
  backend, or traffic will be blocked (iOS ATS / Android cleartext policy).
- For push notifications (signal fired / position closed) add `expo-notifications`
  and forward a webhook from the Telegram/notification path in `backend`.

## Prod checklist

- [ ] `app.json` bundle ids (`com.tradepilot.app`) point at your accounts
- [ ] Real icons + splash added
- [ ] `EXPO_PUBLIC_API_URL` set to an HTTPS backend
- [ ] Backend deployed with `ENVIRONMENT=production`, strong `JWT_SECRET`
- [ ] Privacy policy + terms pages reachable from the store listing
- [ ] Test flight (iOS) / internal track (Android) review before public release