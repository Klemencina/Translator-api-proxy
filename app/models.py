from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ProviderName = Literal["deepl", "microsoft", "google", "microsoft_paid"]


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1)
    source_language: str | None = Field(
        default=None,
        description="Original text language code (for example 'en'). Optional; providers may auto-detect.",
    )
    target_language: str = Field(
        min_length=2,
        max_length=10,
        description="Target translation language code (for example 'es').",
    )


class TranslationResponse(BaseModel):
    translated_text: str
    provider: str
    characters_charged: int


class BatchTranslationRequest(BaseModel):
    requests: list[TranslationRequest] = Field(min_length=1)


class BatchTranslationResult(BaseModel):
    index: int
    ok: bool
    result: TranslationResponse | None = None
    error: str | None = None


class BatchTranslationResponse(BaseModel):
    results: list[BatchTranslationResult]


class ProviderUsage(BaseModel):
    provider: str
    used_characters: int
    monthly_quota: int
    remaining_characters: int


class UsageResponse(BaseModel):
    month: str
    providers: list[ProviderUsage]


class ProviderUsageDetails(BaseModel):
    provider: ProviderName
    used_characters: int
    monthly_quota: int
    remaining_characters: int
    current_minute: str
    requests_this_minute: int
    source_characters_this_minute: int
    requests_per_minute_limit: int
    source_characters_per_minute_limit: int
