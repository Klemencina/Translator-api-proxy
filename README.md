# Translator API Proxy

A single translation endpoint that routes requests across DeepL, Microsoft Translator, Google, and an optional paid Microsoft fallback while tracking monthly character usage.

## Features

- `POST /translate` accepts single translation requests and tries providers in fixed order: `deepl` -> `microsoft` -> `google` -> `microsoft_paid`.
- `POST /translate/batch` accepts multiple translation requests and processes them concurrently (bounded concurrency).
- `GET /usage` shows monthly usage and remaining characters per provider.
- SQLite-backed usage tracking (safe to run locally, easy to persist in a volume).
- Configurable quotas and API credentials via environment variables.
- Optional `MOCK_TRANSLATION=true` mode for local testing without real API keys.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

## Deploy on Coolify

This repo is ready for Dockerfile-based deployment in Coolify.

1. Create a new **Application** in Coolify and connect this repository.
2. Build pack: **Dockerfile** (repo root).
3. Exposed/internal port: `8000`.
4. Health check path: `/health`.
5. Add persistent storage and mount it to `/data`.
6. Set `USAGE_DB_PATH=/data/usage.db` so usage tracking survives restarts.
7. Set `TRANSLATOR_API_KEY` to a long random secret.
8. Add provider credentials (real mode):
    - `GOOGLE_API_KEY`
    - `MICROSOFT_TRANSLATOR_KEY`
    - `MICROSOFT_TRANSLATOR_LOCATION`
    - `MICROSOFT_TRANSLATOR_ENDPOINT`
    - `MICROSOFT_FALLBACK_TRANSLATOR_KEY`
    - `MICROSOFT_FALLBACK_TRANSLATOR_LOCATION`
    - `MICROSOFT_FALLBACK_TRANSLATOR_ENDPOINT`
    - `DEEPL_API_KEY`
9. Set `MOCK_TRANSLATION=false`.

You can copy `.env.example` as a starting point for your Coolify environment variables.

Recommended: run a single instance/replica while using SQLite (`usage.db`).

After deployment, verify:

- `GET /health`
- `POST /translate` with `X-API-Key: <your key>`
- `GET /usage` with `X-API-Key: <your key>`

## API

### Translate

`POST /translate`

Requires authentication header:

- `X-API-Key: <TRANSLATOR_API_KEY>`

Alternative:

- `Authorization: Bearer <TRANSLATOR_API_KEY>`

You can send both the **original language** and the **language to translate into**.

Preferred request shape:

```json
{
  "text": "Hello world",
  "source_language": "en",
  "target_language": "es"
}
```


Response:

```json
{
  "translated_text": "Hola mundo",
  "provider": "deepl",
  "characters_charged": 11
}
```

### Batch translate

`POST /translate/batch`

```json
{
  "requests": [
    {"text": "Hello", "source_language": "en", "target_language": "es"},
    {"text": "How are you?", "source_language": "en", "target_language": "fr"}
  ]
}
```

Response:

```json
{
  "results": [
    {"index": 0, "ok": true, "result": {"translated_text": "Hola", "provider": "deepl", "characters_charged": 5}, "error": null},
    {"index": 1, "ok": true, "result": {"translated_text": "Comment ça va ?", "provider": "microsoft", "characters_charged": 12}, "error": null}
  ]
}
```

### Usage

`GET /usage`

```json
{
  "month": "2026-02",
  "providers": [
    {
      "provider": "google",
      "used_characters": 1000,
      "monthly_quota": 500000,
      "remaining_characters": 499000
    }
  ]
}
```


## How providers count usage

Billing is generally based on **source/input characters**, not translated output length:

- **Google Cloud Translation**: billed by input characters submitted for translation.
- **Microsoft Translator**: billed by source text characters; if you translate into multiple target languages in one request, each target translation is counted.
- **DeepL API (Free/Pro)**: billed by source text characters submitted; output characters are not additionally billed.

Practical implication for this proxy:
- Tracking `len(text)` as `characters_charged` is a good approximation for single-target translations.
- For strict accounting, review each provider's latest billing docs and align counting rules (especially for multi-target or document translation scenarios).

## Environment variables

| Variable | Default | Description |
|---|---:|---|
| `USAGE_DB_PATH` | `usage.db` | SQLite DB path for usage records |
| `TRANSLATOR_API_KEY` | unset | If set, protects `/translate`, `/translate/batch`, and `/usage` |
| `GOOGLE_API_KEY` | unset | Google Translate API key |
| `MICROSOFT_TRANSLATOR_KEY` | unset | Microsoft Translator key |
| `MICROSOFT_TRANSLATOR_LOCATION` | unset | Microsoft Translator resource location |
| `MICROSOFT_TRANSLATOR_ENDPOINT` | `https://api.cognitive.microsofttranslator.com/translate` | Microsoft Translator endpoint |
| `MICROSOFT_FALLBACK_TRANSLATOR_KEY` | unset | Paid fallback Microsoft Translator key |
| `MICROSOFT_FALLBACK_TRANSLATOR_LOCATION` | primary location | Paid fallback Microsoft Translator location |
| `MICROSOFT_FALLBACK_TRANSLATOR_ENDPOINT` | primary endpoint | Paid fallback Microsoft Translator endpoint |
| `DEEPL_API_KEY` | unset | DeepL API key |
| `GOOGLE_MONTHLY_CHAR_QUOTA` | `500000` | Monthly Google character quota |
| `MICROSOFT_MONTHLY_CHAR_QUOTA` | `2000000` | Monthly Microsoft character quota |
| `MICROSOFT_FALLBACK_MONTHLY_CHAR_QUOTA` | `10000000` | Monthly paid fallback Microsoft character quota |
| `DEEPL_MONTHLY_CHAR_QUOTA` | `500000` | Monthly DeepL character quota |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Upstream API timeout |
| `GOOGLE_REQUESTS_PER_MINUTE` | `60` | Google request rate limit enforced by proxy |
| `GOOGLE_SOURCE_CHARS_PER_MINUTE` | `100000` | Google source-character per-minute limit enforced by proxy |
| `MICROSOFT_REQUESTS_PER_MINUTE` | `60` | Microsoft request rate limit enforced by proxy |
| `MICROSOFT_SOURCE_CHARS_PER_MINUTE` | `100000` | Microsoft source-character per-minute limit enforced by proxy |
| `MICROSOFT_FALLBACK_REQUESTS_PER_MINUTE` | `MICROSOFT_REQUESTS_PER_MINUTE` | Paid fallback Microsoft request rate limit |
| `MICROSOFT_FALLBACK_SOURCE_CHARS_PER_MINUTE` | `MICROSOFT_SOURCE_CHARS_PER_MINUTE` | Paid fallback Microsoft source-char rate limit |
| `DEEPL_REQUESTS_PER_MINUTE` | `60` | DeepL request rate limit enforced by proxy |
| `DEEPL_SOURCE_CHARS_PER_MINUTE` | `100000` | DeepL source-character per-minute limit enforced by proxy |
| `BATCH_MAX_CONCURRENCY` | `5` | Max concurrent translations processed in `/translate/batch` |
| `MOCK_TRANSLATION` | `false` | If `true`, mock translation responses |

## Notes

- Provider priority is fixed: `deepl`, then `microsoft`, then `google`, then `microsoft_paid`.
- If `TRANSLATOR_API_KEY` is set, `/translate`, `/translate/batch`, and `/usage` require it; `/health` stays public.
- `MICROSOFT_TRANSLATOR_REGION` is still accepted as a backward-compatible alias for `MICROSOFT_TRANSLATOR_LOCATION`.
- `MICROSOFT_PAID_TRANSLATOR_*` is also accepted as an alias for `MICROSOFT_FALLBACK_TRANSLATOR_*`.
- Quota consumption is reserved atomically in SQLite before provider calls to prevent concurrent requests from overshooting monthly caps.
- Provider per-minute request/character limits are enforced in SQLite so concurrent traffic cannot exceed configured rate limits.
- Quotas are tracked by month (`YYYY-MM`) in UTC.
