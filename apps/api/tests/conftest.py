"""Offline tests never touch a real DB, Ollama or secret-bearing .env."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key, value in {
    "APP_ENV": "development", "APP_SECRET": "offline-test-only-not-a-live-secret",
    "DATABASE_URL": "postgresql+asyncpg://demo:demo@127.0.0.1:5432/demo",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "MINIO_ROOT_USER": "offline-test", "MINIO_ROOT_PASSWORD": "offline-test",
    "ORDERNEXA_OPERATOR_KEY": "test-secret-key-longer-than-24-characters",
}.items():
    os.environ.setdefault(key, value)
