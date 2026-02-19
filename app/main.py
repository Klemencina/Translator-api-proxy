from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.config import Settings, load_settings
from app.models import ProviderUsage, TranslationRequest, TranslationResponse, UsageResponse
from app.providers import DeepLProvider, GoogleProvider, MicrosoftProvider, ProviderError, TranslationProvider
from app.quota import QuotaStore


class TranslationRouter:
    def __init__(self, settings: Settings, quota_store: QuotaStore) -> None:
        self.settings = settings
        self.quota_store = quota_store
        self.providers: dict[str, TranslationProvider] = {
            "google": GoogleProvider(settings),
            "microsoft": MicrosoftProvider(settings),
            "deepl": DeepLProvider(settings),
        }
        self.quotas = {
            "google": settings.google_quota.monthly_chars,
            "microsoft": settings.microsoft_quota.monthly_chars,
            "deepl": settings.deepl_quota.monthly_chars,
        }

    def _remaining(self, provider: str) -> int:
        return self.quotas[provider] - self.quota_store.get_used(provider)

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
        candidates = sorted(self.providers.keys(), key=self._remaining, reverse=True)
        errors: list[str] = []

        for provider_name in candidates:
            if self._remaining(provider_name) < char_count:
                errors.append(f"{provider_name}: quota exceeded")
                continue

            provider = self.providers[provider_name]
            try:
                result = await provider.translate(text, target_language, source_language)
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
                continue

            self.quota_store.increment(provider_name, char_count)
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

    return app


app = create_app()
