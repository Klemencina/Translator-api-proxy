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
        "MICROSOFT_FALLBACK_MONTHLY_CHAR_QUOTA": "30",
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


def test_routes_in_configured_priority_order(tmp_path: Path):
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


def test_falls_back_to_microsoft_when_deepl_quota_exhausted(tmp_path: Path):
    client, cleanup = _build_client(tmp_path, DEEPL_MONTHLY_CHAR_QUOTA="5")
    try:
        response = client.post("/translate", json={"text": "hello", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "deepl"

        response = client.post("/translate", json={"text": "abc", "target_language": "fr"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "microsoft"
    finally:
        cleanup()


def test_falls_back_to_google_when_deepl_and_microsoft_exhausted(tmp_path: Path):
    client, cleanup = _build_client(
        tmp_path,
        DEEPL_MONTHLY_CHAR_QUOTA="5",
        MICROSOFT_MONTHLY_CHAR_QUOTA="5",
        GOOGLE_MONTHLY_CHAR_QUOTA="20",
    )
    try:
        response = client.post("/translate", json={"text": "hello", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "deepl"

        response = client.post("/translate", json={"text": "world", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "microsoft"

        response = client.post("/translate", json={"text": "again", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "google"
    finally:
        cleanup()


def test_uses_paid_microsoft_fallback_last(tmp_path: Path):
    client, cleanup = _build_client(
        tmp_path,
        DEEPL_MONTHLY_CHAR_QUOTA="5",
        MICROSOFT_MONTHLY_CHAR_QUOTA="5",
        GOOGLE_MONTHLY_CHAR_QUOTA="5",
        MICROSOFT_FALLBACK_MONTHLY_CHAR_QUOTA="20",
    )
    try:
        response = client.post("/translate", json={"text": "hello", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "deepl"

        response = client.post("/translate", json={"text": "world", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "microsoft"

        response = client.post("/translate", json={"text": "apple", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "google"

        response = client.post("/translate", json={"text": "again", "target_language": "fr"})
        assert response.status_code == 200
        assert response.json()["provider"] == "microsoft_paid"
    finally:
        cleanup()


def test_returns_503_when_all_quotas_exceeded(tmp_path: Path):
    client, cleanup = _build_client(
        tmp_path,
        DEEPL_MONTHLY_CHAR_QUOTA="5",
        MICROSOFT_MONTHLY_CHAR_QUOTA="8",
        GOOGLE_MONTHLY_CHAR_QUOTA="5",
        MICROSOFT_FALLBACK_MONTHLY_CHAR_QUOTA="30",
    )
    try:
        response = client.post("/translate", json={"text": "x" * 31, "target_language": "de"})
        assert response.status_code == 503
    finally:
        cleanup()


def test_batch_translate_processes_multiple_requests(tmp_path: Path):
    client, cleanup = _build_client(tmp_path, BATCH_MAX_CONCURRENCY="2")
    try:
        response = client.post(
            "/translate/batch",
            json={
                "requests": [
                    {"text": "hello", "target_language": "es"},
                    {"text": "world", "target_language": "fr"},
                ]
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["results"]) == 2
        assert all(item["ok"] for item in payload["results"])
    finally:
        cleanup()


def test_requires_api_key_when_configured(tmp_path: Path):
    client, cleanup = _build_client(tmp_path, TRANSLATOR_API_KEY="super-secret")
    try:
        response = client.post("/translate", json={"text": "hello", "target_language": "es"})
        assert response.status_code == 401

        response = client.post(
            "/translate",
            json={"text": "hello", "target_language": "es"},
            headers={"X-API-Key": "wrong"},
        )
        assert response.status_code == 401

        response = client.post(
            "/translate",
            json={"text": "hello", "target_language": "es"},
            headers={"X-API-Key": "super-secret"},
        )
        assert response.status_code == 200
    finally:
        cleanup()
