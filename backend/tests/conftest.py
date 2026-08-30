"""Shared pytest fixtures for TradePilot backend tests.

A dedicated temp-file SQLite database is created before the FastAPI app is
imported so module-level engine/table creation targets it. The TestClient is
used WITHOUT the context manager so the startup demo-seeder never runs during
tests (keeping them fast and deterministic).
"""
import os
import pathlib
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="tradepilot_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{pathlib.Path(_SCRATCH) / 'test.db'}"
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}