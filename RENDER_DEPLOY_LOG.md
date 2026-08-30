# Render Deploy Log — August 31, 2026

## Deploy Attempt — Failed (Exit Status 1)

**Deploy ID:** dep-daa9bt142hec739t5a4g
**Service ID:** srv-daa9bsp42hec739t59k0
**Commit:** b0d693c (docs: Render setup uses Web Service, not Blueprint, Root Directory=backend)
**Timestamp:** Aug 31, 2026 at 2:13 AM

### Error

```
Exited with status 1 while running your code.
```

### Log Trace

```
02:14:32 AM [8c4m7] return _bootstrap._gcd_import(name[level:], package, level)
02:14:32 AM [8c4m7]           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap_external>", line 999, in exec_module
02:14:32 AM [8c4m7] File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
02:14:32 AM [8c4m7] File "/opt/render/project/src/backend/app/main.py", line 68, in <module>
02:14:32 AM [8c4m7]     _assert_production_secrets()
02:14:32 AM [8c4m7] File "/opt/render/project/src/backend/app/main.py", line 61, in _assert_production_secrets
02:14:32 AM [8c4m7]     raise RuntimeError(
02:14:32 AM [8c4m7] RuntimeError: Refusing to start in production: set strong values for JWT_SECRET, TRADINGVIEW_WEBHOOK_SECRET (see backend/.env.example).
02:14:36 AM [8c4m7] ==> Exited with status 1
02:14:36 AM [8c4m7] ==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
02:14:40 AM [8c4m7] ==> Running 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

### Root Cause

`ENVIRONMENT=production` triggers `_assert_production_secrets()` in `backend/app/main.py:46-65`.
Two env vars were missing or set to defaults on Render:

| Variable | Requirement | Default (rejected) |
|---|---|---|
| `JWT_SECRET` | ≥ 32 chars, not in weak list | `change-me-in-production` |
| `TRADINGVIEW_WEBHOOK_SECRET` | ≥ 16 chars, not in weak list | `tradepilot-webhook-secret` |

Weak lists (main.py:42-43):
```python
_WEAK_JWT_SECRETS = {"change-me-in-production", "changeme", "secret", ""}
_WEAK_WEBHOOK_SECRETS = {"tradepilot-webhook-secret", "changeme", "secret", ""}
```

### Fix Applied

Set strong values in Render → Environment tab:

| Variable | Value |
|---|---|
| `JWT_SECRET` | `xK9mP2vL8nQ4wR7tY1jH6bF3dS5aG0eC` |
| `TRADINGVIEW_WEBHOOK_SECRET` | `tv-wh-9kLm3nPqR7sT` |

Then: **Manual Deploy → Clear build cache & deploy**.

### Files Involved
- `backend/app/main.py` — `_assert_production_secrets()` at line 46
- `backend/.env.example` — documents required variables
