from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app



def _build_client(tmp_path: Path, **env_overrides: str):
    base_env = {
        "USAGE_DB_PATH": str(tmp_path / "usage.db"),
        "MOCK_TRANSLATION": "true",
        "GOOGLE_MONTHLY_CHAR_QUOTA": "5",
        "MICROSOFT_MONTHLY_CHAR_QUOTA": "8",
        "DEEPL_MONTHLY_CHAR_QUOTA": "20",
    }
    old_values = {k: os.getenv(k) for k in set(base_env) | set(env_overrides)}
    os.environ.update(base_env)
    for key, value in env_overrides.items():
        os.environ[key] = value

    app = create_app()
    client = TestClient(app)

    def cleanup():
        for k, v in old_values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return client, cleanup


def test_routes_to_provider_with_highest_remaining_quota(tmp_path: Path):
    client, cleanup = _build_client(tmp_path)
    try:
        response = client.post("/translate", json={"text": "hello", "target_language": "es"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "deepl"

        usage = client.get("/usage").json()
        deepl = next(p for p in usage["providers"] if p["provider"] == "deepl")
        assert deepl["used_characters"] == 5
    finally:
        cleanup()


def test_falls_back_when_top_provider_quota_exhausted(tmp_path: Path):
    client, cleanup = _build_client(tmp_path)
    try:
        for _ in range(4):
            client.post("/translate", json={"text": "hello", "target_language": "fr"})

        response = client.post("/translate", json={"text": "abc", "target_language": "fr"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "microsoft"
    finally:
        cleanup()


def test_returns_503_when_all_quotas_exceeded(tmp_path: Path):
    client, cleanup = _build_client(tmp_path)
    try:
        response = client.post("/translate", json={"text": "x" * 21, "target_language": "de"})
        assert response.status_code == 503
    finally:
        cleanup()
