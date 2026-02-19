from __future__ import annotations

from pydantic import BaseModel, Field


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


class ProviderUsage(BaseModel):
    provider: str
    used_characters: int
    monthly_quota: int
    remaining_characters: int


class UsageResponse(BaseModel):
    month: str
    providers: list[ProviderUsage]
