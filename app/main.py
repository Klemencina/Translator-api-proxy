from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException

from app.config import Settings, load_settings
from app.models import (
    BatchTranslationRequest,
    BatchTranslationResponse,
    BatchTranslationResult,
    ProviderUsage,
    TranslationRequest,
    TranslationResponse,
    UsageResponse,
)
from app.providers import DeepLProvider, GoogleProvider, MicrosoftProvider, ProviderError, TranslationProvider
from app.quota import QuotaStore


class TranslationRouter:
    def __init__(self, settings: Settings, quota_store: QuotaStore) -> None:
        self.settings = settings
        self.quota_store = quota_store
        self.provider_order = ["deepl", "microsoft", "google", "microsoft_paid"]
        self.providers: dict[str, TranslationProvider] = {
            "deepl": DeepLProvider(settings),
            "microsoft": MicrosoftProvider(
                settings,
                name="microsoft",
                api_key=settings.microsoft_api_key,
                location=settings.microsoft_location,
                endpoint=settings.microsoft_endpoint,
            ),
            "google": GoogleProvider(settings),
            "microsoft_paid": MicrosoftProvider(
                settings,
                name="microsoft_paid",
                api_key=settings.microsoft_fallback_api_key,
                location=settings.microsoft_fallback_location,
                endpoint=settings.microsoft_fallback_endpoint,
            ),
        }
        self.quotas = {
            "deepl": settings.deepl_quota.monthly_chars,
            "microsoft": settings.microsoft_quota.monthly_chars,
            "google": settings.google_quota.monthly_chars,
            "microsoft_paid": settings.microsoft_fallback_quota.monthly_chars,
        }
        self.rate_limits = {
            "deepl": settings.deepl_rate_limit,
            "microsoft": settings.microsoft_rate_limit,
            "google": settings.google_rate_limit,
            "microsoft_paid": settings.microsoft_fallback_rate_limit,
        }

    def provider_usage(self) -> UsageResponse:
        month = self.quota_store.current_month()
        providers = []
        for name, quota in self.quotas.items():
            used = self.quota_store.get_used(name, month)
            providers.append(
                ProviderUsage(
                    provider=name,
                    used_characters=used,
                    monthly_quota=quota,
                    remaining_characters=max(quota - used, 0),
                )
            )
        return UsageResponse(month=month, providers=providers)

    async def translate(self, text: str, target_language: str, source_language: str | None) -> TranslationResponse:
        char_count = len(text)
        candidates = self.provider_order
        errors: list[str] = []

        for provider_name in candidates:
            rate = self.rate_limits[provider_name]
            allowed_by_rate = self.quota_store.try_consume_rate_limit(
                provider=provider_name,
                request_units=1,
                source_char_units=char_count,
                max_requests_per_minute=rate.requests_per_minute,
                max_source_chars_per_minute=rate.source_chars_per_minute,
            )
            if not allowed_by_rate:
                errors.append(f"{provider_name}: provider rate limit reached")
                continue

            reserved = self.quota_store.try_reserve(provider_name, char_count, self.quotas[provider_name])
            if not reserved:
                errors.append(f"{provider_name}: quota exceeded")
                continue

            provider = self.providers[provider_name]
            try:
                result = await provider.translate(text, target_language, source_language)
            except Exception as exc:
                self.quota_store.release(provider_name, char_count)
                errors.append(f"{provider_name}: {exc}")
                continue

            return TranslationResponse(
                translated_text=result.translated_text,
                provider=result.provider,
                characters_charged=char_count,
            )

        raise HTTPException(status_code=503, detail=f"No provider available. {'; '.join(errors)}")


def create_app() -> FastAPI:
    settings = load_settings()
    quota_store = QuotaStore(settings.database_path)
    router = TranslationRouter(settings, quota_store)

    app = FastAPI(title="Translator API Proxy", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/usage", response_model=UsageResponse)
    async def usage() -> UsageResponse:
        return router.provider_usage()

    @app.post("/translate", response_model=TranslationResponse)
    async def translate(req: TranslationRequest) -> TranslationResponse:
        try:
            return await router.translate(req.text, req.target_language, req.source_language)
        except ProviderError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/translate/batch", response_model=BatchTranslationResponse)
    async def translate_batch(req: BatchTranslationRequest) -> BatchTranslationResponse:
        semaphore = asyncio.Semaphore(max(settings.batch_max_concurrency, 1))

        async def one(index: int, item: TranslationRequest) -> BatchTranslationResult:
            async with semaphore:
                try:
                    result = await router.translate(item.text, item.target_language, item.source_language)
                    return BatchTranslationResult(index=index, ok=True, result=result)
                except HTTPException as exc:
                    return BatchTranslationResult(index=index, ok=False, error=str(exc.detail))
                except Exception as exc:
                    return BatchTranslationResult(index=index, ok=False, error=str(exc))

        tasks = [one(index, item) for index, item in enumerate(req.requests)]
        results = await asyncio.gather(*tasks)
        return BatchTranslationResponse(results=results)

    return app


app = create_app()
