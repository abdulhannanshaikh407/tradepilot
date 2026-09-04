# TradePilot AI — 10,000 User Readiness Report

## Current Verdict: **NOT ready for 10K users as-is**

You have **5 critical bottlenecks** that will break at scale. Here's each one with **free solutions**.

---

## BOTTLENECK #1: SQLite Database (CRITICAL)
**Location:** `backend/app/db/database.py:7`

SQLite supports ~100 concurrent writes. With 10K users you'll hit lock errors immediately.

**Free Fix: Switch to PostgreSQL on Neon or Supabase**

| Provider | Free Tier | Enough for 10K? |
|----------|-----------|-----------------|
| **Neon** | 512MB storage, 24/7 compute | Yes (starter) |
| **Supabase** | 500MB, 50K monthly active users | Yes |
| **Railway** | $5 free credit/mo | Yes |

**Action:**
1. Sign up at neon.com (free, no credit card)
2. Create a project, copy the connection string
3. Change one line in `.env`:
```
DATABASE_URL=postgresql+psycopg2://user:pass@ep-xxx.us-east-2.aws.neon.tech/tradepilot?sslmode=require
```
4. Run `alembic upgrade head` to create tables

---

## BOTTLENECK #2: Render Free Tier Backend (CRITICAL)
**Location:** `backend/Procfile`

Render free tier: 512MB RAM, **spins down after 15 min idle**, 750 hours/mo. With 10K users this will crash constantly.

**Free Fix: Move to Oracle Cloud Always Free ARM**

Oracle Cloud gives **4 OCPU + 24GB RAM forever free** — enough for 10K+ users.

**Action:**
1. Sign up at cloud.oracle.com (free tier, no charge)
2. Create an ARM A1 instance (Always Free eligible)
3. Install Python, clone your repo, run with `uvicorn`
4. Use **Cloudflare Tunnel** (free) to expose without opening ports

**Alternative free options:**
- **Railway** ($5/mo free credit — enough for a small instance)
- **Koyeb** (free tier: 1 shared CPU, 512MB)
- **Fly.io** (3 shared VMs free)

---

## BOTTLENECK #3: WebSocket at Scale (HIGH)
**Location:** `backend/app/main.py:176-254`

Your `ConnectionManager` stores all connections in a Python dict in memory. This:
- Dies when the server restarts
- Can't work across multiple worker processes
- Will eat 512MB RAM with 10K connections

**Free Fix: Use Server-Sent Events (SSE) instead, or add a free Redis pub/sub**

**Option A — SSE (simplest, no extra infra):**
```python
# Replace WebSocket with SSE endpoint
from fastapi.responses import StreamingResponse

@app.get("/ws/signals")
async def signal_stream(user_id: int = Depends(get_current_user)):
    async def event_generator():
        while True:
            signal = await check_new_signal(user_id)
            if signal:
                yield f"data: {json.dumps(signal)}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Option B — Free Redis for pub/sub:**
- Use Upstash Redis (free: 10K commands/day, no credit card)
- Replace in-memory dict with Redis pub/sub
- Survives restarts, works across workers

---

## BOTTLENECK #4: AI API Rate Limits (HIGH)
**Location:** `backend/app/services/ai_strategy_service.py`

Free tiers:
- **Groq**: 30 req/min, 14,400 req/day
- **Gemini**: 15 req/min, 1,500 req/day

With 10K users doing YouTube analysis, you'll burn through these fast.

**Free Fix: Aggressive caching + queuing**

```python
# In usage_service.py, tighten FREE plan limits:
PLAN_LIMITS = {
    "FREE": {
        "analyses_per_day": 3,      # Keep this LOW
        "backtests_per_day": 10,     # Reduce from 25
        "signals_per_day": 10,       # Reduce from 20
        "webhooks_per_day": 15,      # Reduce from 30
        "strategies": 10,            # Reduce from 50
    },
}
```

**Additional free strategies:**
- Cache AI results by YouTube video ID (same video = same analysis)
- Use **deterministic parser first** (your code already does this), only call AI for complex videos
- Add a **queue** (use free Upstash Redis) so AI calls are serialized, not parallel
- Rotate between Groq + Gemini to double your free quota

---

## BOTTLENECK #5: Auto-Trade Engine on Free Tier (MEDIUM)
**Location:** `backend/app/services/autotrade.py:463-524`

The `run_once()` loop runs every 120 seconds, scanning ALL enabled configs. With 10K users each having 5 strategies = 50K configs to scan every 2 minutes. This will:
- Timeout on free tier
- Eat all available CPU/RAM

**Free Fix: Optimize the scan loop**

```python
# In autotrade.py, add symbol-level caching:
def run_once():
    # Fetch market data ONCE per symbol, not per config
    symbols_needing_data = set()
    for config in configs:
        symbols_needing_data.add((config.strategy.asset, config.strategy.timeframe))

    # Cache all OHLCV data upfront
    ohlcv_cache = {}
    for symbol, tf in symbols_needing_data:
        ohlcv_cache[(symbol, tf)] = get_provider().get_ohlcv(symbol, tf)

    # Then scan configs using cached data
```

Also: **disable auto-trade for FREE users** — make it a PRO-only feature. This eliminates most of the load.

---

## Complete Free Stack for 10K Users

| Component | Current | Free Replacement |
|-----------|---------|-----------------|
| **Database** | SQLite | **Neon PostgreSQL** (free 512MB) |
| **Backend** | Render free | **Oracle ARM Always Free** (4 OCPU, 24GB) |
| **Frontend** | Vercel | **Vercel** (free, already good) |
| **Caching** | In-memory | **Upstash Redis** (free 10K cmds/day) |
| **WebSocket** | In-memory dict | **SSE** or **Upstash Redis pub/sub** |
| **AI** | Multiple providers | **Groq + Gemini** (rotate, cache aggressively) |
| **Market Data** | Binance/Simulated | **Binance public API** (free, no key needed) |
| **Push Notifications** | FCM | **FCM** (free for unlimited devices) |
| **Domain/DNS** | None | **Cloudflare** (free) |
| **Tunnel** | Direct IP | **Cloudflare Tunnel** (free, exposes backend) |

**Total cost: $0/month**

---

## Priority Action Plan

1. **Today:** Switch to Neon PostgreSQL (1 line change in `.env`)
2. **Today:** Deploy backend to Oracle ARM or Railway ($5 credit)
3. **This week:** Add Redis via Upstash (free) for caching + rate limiting
4. **This week:** Tighten FREE plan usage limits in `usage_service.py`
5. **This week:** Disable auto-trade for FREE users (PRO only)
6. **Optional:** Replace WebSocket with SSE for simpler scaling

The architecture is solid — FastAPI async, connection pooling, batch processing, fallback chains. The code itself is well-structured for scaling. You just need to swap the infrastructure components from dev/free-tier to proper free-tier services.
