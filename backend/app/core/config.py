# app/core/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_NAME = "TradePilot AI"
APP_VERSION = "1.0.0"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tradepilot.db")
if DATABASE_URL.startswith("sqlite:///./") or DATABASE_URL.startswith("sqlite:///../"):
    relative = DATABASE_URL.replace("sqlite:///", "", 1)
    DATABASE_URL = f"sqlite:///{BASE_DIR / relative.lstrip('./')}"

# Auth
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Anthropic (Claude)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# Groq (free: 30 req/min, Llama 3.3 70B) — https://console.groq.com
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# Google Gemini (free: 15 req/min, Gemini 2.0 Flash) — https://aistudio.google.com
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Webhook
TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "tradepilot-webhook-secret")

# CORS: comma separated list of allowed origins
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,https://tradepilot-ai.vercel.app",
    ).split(",")
    if origin.strip()
]

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = _get_bool("DEBUG", ENVIRONMENT != "production")

# Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Auto-trading
AUTOTRADE_ENABLED = _get_bool("AUTOTRADE_ENABLED", True)
AUTOTRADE_INTERVAL = float(os.getenv("AUTOTRADE_INTERVAL", "120"))  # seconds between scans
AUTOTRADE_PAPER_CAPITAL = float(os.getenv("AUTOTRADE_PAPER_CAPITAL", "10000"))

# Real execution (optional; paper mode needs none of these)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Firebase Cloud Messaging
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
FCM_ENABLED = _get_bool("FCM_ENABLED", bool(FIREBASE_CREDENTIALS_PATH))

# Redis (production caching, rate limiting, pub/sub)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_ENABLED = _get_bool("REDIS_ENABLED", ENVIRONMENT == "production")

# WebSocket
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))

# Production scaling
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "1"))
AUTOTRADE_BATCH_SIZE = int(os.getenv("AUTOTRADE_BATCH_SIZE", "50"))
AUTOTRADE_MAX_CONCURRENT_USERS = int(os.getenv("AUTOTRADE_MAX_CONCURRENT_USERS", "10"))

# ---- Free market data providers ----
# Biquote (free, no API key — real-time forex, metals, crypto via SignalR)
# No config needed, works out of the box.

# Finnhub (free API key at finnhub.io — US stocks, forex, crypto)
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# OANDA (free demo account — forex + metals, real-time + execution)
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ACCOUNT_TYPE = os.getenv("OANDA_ACCOUNT_TYPE", "paper")  # paper | live