from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    translated_text: str


class TranslationProvider:
    name: str

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: str | None,
    ) -> ProviderResult:
        raise NotImplementedError


class GoogleProvider(TranslationProvider):
    name = "google"

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.google_api_key
        self.timeout = settings.request_timeout_seconds
        self.mock = settings.mock_translation

    async def translate(self, text: str, target_language: str, source_language: str | None) -> ProviderResult:
        if self.mock:
            return ProviderResult(provider=self.name, translated_text=f"[google] {text}")
        if not self.api_key:
            raise ProviderError("GOOGLE_API_KEY is not configured")

        payload = {"q": text, "target": target_language, "format": "text", "key": self.api_key}
        if source_language:
            payload["source"] = source_language

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post("https://translation.googleapis.com/language/translate/v2", data=payload)
            resp.raise_for_status()
            data = resp.json()
        translated = data["data"]["translations"][0]["translatedText"]
        return ProviderResult(provider=self.name, translated_text=translated)


class MicrosoftProvider(TranslationProvider):
    name = "microsoft"

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.microsoft_api_key
        self.region = settings.microsoft_region
        self.timeout = settings.request_timeout_seconds
        self.mock = settings.mock_translation

    async def translate(self, text: str, target_language: str, source_language: str | None) -> ProviderResult:
        if self.mock:
            return ProviderResult(provider=self.name, translated_text=f"[microsoft] {text}")
        if not self.api_key or not self.region:
            raise ProviderError("MICROSOFT_TRANSLATOR_KEY and MICROSOFT_TRANSLATOR_REGION must be configured")

        params = {"api-version": "3.0", "to": target_language}
        if source_language:
            params["from"] = source_language

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-Type": "application/json",
        }

        body = [{"text": text}]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.cognitive.microsofttranslator.com/translate",
                params=params,
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        translated = data[0]["translations"][0]["text"]
        return ProviderResult(provider=self.name, translated_text=translated)


class DeepLProvider(TranslationProvider):
    name = "deepl"

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.deepl_api_key
        self.timeout = settings.request_timeout_seconds
        self.mock = settings.mock_translation

    async def translate(self, text: str, target_language: str, source_language: str | None) -> ProviderResult:
        if self.mock:
            return ProviderResult(provider=self.name, translated_text=f"[deepl] {text}")
        if not self.api_key:
            raise ProviderError("DEEPL_API_KEY is not configured")

        data = {"text": text, "target_lang": target_language.upper()}
        if source_language:
            data["source_lang"] = source_language.upper()

        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post("https://api-free.deepl.com/v2/translate", data=data, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        translated = payload["translations"][0]["text"]
        return ProviderResult(provider=self.name, translated_text=translated)
