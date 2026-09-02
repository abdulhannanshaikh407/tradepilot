# PlayStore Submission Guide — TradePilot AI

## Prerequisites

1. **Google Play Developer Account** ($25 one-time fee)
   - Sign up at https://play.google.com/console
2. **EAS CLI** installed globally
   ```bash
   npm install -g eas-cli
   ```
3. **Expo account** (free)
   ```bash
   eas login
   ```

## Step-by-Step Submission

### 1. Prepare Production Assets

Replace placeholder files with real assets:
- `assets/icon.png` — 1024x1024 PNG (app icon)
- `assets/splash.png` — 1284x2778 PNG (splash screen)
- `assets/adaptive-icon.png` — 1024x1024 PNG (Android adaptive icon)

Design tool: https://www.figma.com or https://canva.com

### 2. Set Environment Variables

Create `mobile/.env.production`:
```
EXPO_PUBLIC_API_URL=https://tradepilot-ai-api.onrender.com
```

### 3. Build for Android

```bash
cd mobile
eas build -p android --profile production
```

This produces an AAB (Android App Bundle) file.

### 4. Submit to Play Store

```bash
eas submit -p android
```

This uploads the AAB to Google Play Console.

### 5. Configure Play Console

1. Go to https://play.google.com/console
2. Select your app
3. **Store listing**: Add title, description, screenshots
4. **Content rating**: Complete questionnaire (trading/finance app)
5. **Pricing**: Free
6. **Target audience**: Adults (18+)
7. **Privacy policy**: Required — host at your domain
8. **Data safety**: Declare data collection (email, trading data)

### 6. Testing Track

1. First upload goes to **Internal Testing**
2. Add testers via email
3. Once verified, promote to **Production**

### 7. Required Assets

| Asset | Size | Format |
|-------|------|--------|
| App icon | 512x512 | PNG |
| Feature graphic | 1024x500 | PNG |
| Screenshots (phone) | 16:9 or 9:16 | PNG/JPG |
| Screenshots (tablet) | 16:9 or 9:16 | PNG/JPG |

### 8. Android Permissions

Already configured in `app.json`:
- `INTERNET` — API communication
- `RECEIVE_BOOT_COMPLETED` — Background notifications
- `VIBRATE` — Notification sounds
- `SCHEDULE_EXACT_ALARM` — Timed notifications

### 9. Firebase Setup (for Push Notifications)

1. Go to https://console.firebase.google.com
2. Create project or use existing
3. Add Android app with package `com.tradepilot.app`
4. Download `google-services.json` → place in `mobile/`
5. Go to Project Settings → Service Accounts → Generate New Private Key
6. Save as `backend/firebase-service-account.json`
7. Set `FIREBASE_CREDENTIALS_PATH` in backend `.env`

### 10. Post-Launch

- Monitor crash reports in Play Console
- Respond to user reviews
- Push updates via `eas build -p android --profile production` + `eas submit -p android`

## Common Issues

| Issue | Fix |
|-------|-----|
| "App not installed" | Ensure AAB format, not APK |
| "Upload failed" | Check asset sizes, API level requirements |
| "Policy violation" | Review trading/financial app policies |
| "Missing privacy policy" | Add privacy policy URL to store listing |
