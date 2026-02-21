from __future__ import annotations

import asyncio
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

from app.config import ProviderRateLimit, Settings, load_settings
from app.models import (
    BatchTranslationRequest,
    BatchTranslationResponse,
    BatchTranslationResult,
    ProviderName,
    ProviderUsage,
    ProviderUsageDetails,
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
        self.provider_order: list[ProviderName] = ["deepl", "microsoft", "google", "microsoft_paid"]
        self.providers: dict[ProviderName, TranslationProvider] = {
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
        self.quotas: dict[ProviderName, int] = {
            "deepl": settings.deepl_quota.monthly_chars,
            "microsoft": settings.microsoft_quota.monthly_chars,
            "google": settings.google_quota.monthly_chars,
            "microsoft_paid": settings.microsoft_fallback_quota.monthly_chars,
        }
        self.rate_limits: dict[ProviderName, ProviderRateLimit] = {
            "deepl": settings.deepl_rate_limit,
            "microsoft": settings.microsoft_rate_limit,
            "google": settings.google_rate_limit,
            "microsoft_paid": settings.microsoft_fallback_rate_limit,
        }

    def _provider_usage(self, provider: ProviderName, month: str) -> ProviderUsage:
        quota = self.quotas[provider]
        used = self.quota_store.get_used(provider, month)
        return ProviderUsage(
            provider=provider,
            used_characters=used,
            monthly_quota=quota,
            remaining_characters=max(quota - used, 0),
        )

    def provider_usage(self) -> UsageResponse:
        month = self.quota_store.current_month()
        providers = [self._provider_usage(name, month) for name in self.provider_order]
        return UsageResponse(month=month, providers=providers)

    def provider_usage_details(self, provider: ProviderName) -> ProviderUsageDetails:
        month = self.quota_store.current_month()
        minute = self.quota_store.current_minute()
        usage = self._provider_usage(provider, month)
        req_used, source_chars_used = self.quota_store.get_rate_usage(provider, minute=minute)
        rate_limit = self.rate_limits[provider]
        return ProviderUsageDetails(
            provider=provider,
            used_characters=usage.used_characters,
            monthly_quota=usage.monthly_quota,
            remaining_characters=usage.remaining_characters,
            current_minute=minute,
            requests_this_minute=req_used,
            source_characters_this_minute=source_chars_used,
            requests_per_minute_limit=rate_limit.requests_per_minute,
            source_characters_per_minute_limit=rate_limit.source_chars_per_minute,
        )

    async def _translate_with_candidates(
        self,
        candidates: list[ProviderName],
        text: str,
        target_language: str,
        source_language: str | None,
    ) -> TranslationResponse:
        char_count = len(text)
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

    async def translate(self, text: str, target_language: str, source_language: str | None) -> TranslationResponse:
        return await self._translate_with_candidates(self.provider_order, text, target_language, source_language)

    async def translate_with_provider(
        self,
        provider: ProviderName,
        text: str,
        target_language: str,
        source_language: str | None,
    ) -> TranslationResponse:
        return await self._translate_with_candidates([provider], text, target_language, source_language)


def create_app() -> FastAPI:
    settings = load_settings()
    quota_store = QuotaStore(settings.database_path)
    router = TranslationRouter(settings, quota_store)

    async def require_api_key(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None),
    ) -> None:
        expected = settings.translator_api_key
        if not expected:
            return

        provided = x_api_key
        if provided is None and authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()

        if not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")

    app = FastAPI(title="Translator API Proxy", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/usage", response_model=UsageResponse, dependencies=[Depends(require_api_key)])
    async def usage() -> UsageResponse:
        return router.provider_usage()

    @app.get("/usage/{provider}", response_model=ProviderUsageDetails, dependencies=[Depends(require_api_key)])
    async def usage_by_provider(provider: ProviderName) -> ProviderUsageDetails:
        return router.provider_usage_details(provider)

    @app.post("/translate", response_model=TranslationResponse, dependencies=[Depends(require_api_key)])
    async def translate(req: TranslationRequest) -> TranslationResponse:
        try:
            return await router.translate(req.text, req.target_language, req.source_language)
        except ProviderError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/translate/batch", response_model=BatchTranslationResponse, dependencies=[Depends(require_api_key)])
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

    @app.post("/translate/{provider}", response_model=TranslationResponse, dependencies=[Depends(require_api_key)])
    async def translate_by_provider(provider: ProviderName, req: TranslationRequest) -> TranslationResponse:
        try:
            return await router.translate_with_provider(provider, req.text, req.target_language, req.source_language)
        except ProviderError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
