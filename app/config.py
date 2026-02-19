from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderQuota:
    monthly_chars: int


@dataclass(frozen=True)
class Settings:
    database_path: str
    google_api_key: str | None
    microsoft_api_key: str | None
    microsoft_region: str | None
    deepl_api_key: str | None
    google_quota: ProviderQuota
    microsoft_quota: ProviderQuota
    deepl_quota: ProviderQuota
    request_timeout_seconds: float
    mock_translation: bool



def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


def load_settings() -> Settings:
    return Settings(
        database_path=os.getenv("USAGE_DB_PATH", "usage.db"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        microsoft_api_key=os.getenv("MICROSOFT_TRANSLATOR_KEY"),
        microsoft_region=os.getenv("MICROSOFT_TRANSLATOR_REGION"),
        deepl_api_key=os.getenv("DEEPL_API_KEY"),
        google_quota=ProviderQuota(monthly_chars=_int_env("GOOGLE_MONTHLY_CHAR_QUOTA", 500_000)),
        microsoft_quota=ProviderQuota(monthly_chars=_int_env("MICROSOFT_MONTHLY_CHAR_QUOTA", 2_000_000)),
        deepl_quota=ProviderQuota(monthly_chars=_int_env("DEEPL_MONTHLY_CHAR_QUOTA", 500_000)),
        request_timeout_seconds=_float_env("REQUEST_TIMEOUT_SECONDS", 15.0),
        mock_translation=os.getenv("MOCK_TRANSLATION", "false").lower() == "true",
    )
