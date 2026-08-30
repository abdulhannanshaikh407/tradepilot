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
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

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