# Translator API Proxy

A single translation endpoint that routes requests across Google, Microsoft Translator, and DeepL while tracking monthly character usage so you stay in free-tier limits.

## Features

- `POST /translate` accepts single translation requests and chooses a provider with available quota and rate-limit capacity.
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

## API

### Translate

`POST /translate`

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
| `GOOGLE_API_KEY` | unset | Google Translate API key |
| `MICROSOFT_TRANSLATOR_KEY` | unset | Microsoft Translator key |
| `MICROSOFT_TRANSLATOR_REGION` | unset | Microsoft Translator resource region |
| `DEEPL_API_KEY` | unset | DeepL API key |
| `GOOGLE_MONTHLY_CHAR_QUOTA` | `500000` | Monthly Google character quota |
| `MICROSOFT_MONTHLY_CHAR_QUOTA` | `2000000` | Monthly Microsoft character quota |
| `DEEPL_MONTHLY_CHAR_QUOTA` | `500000` | Monthly DeepL character quota |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Upstream API timeout |
| `GOOGLE_REQUESTS_PER_MINUTE` | `60` | Google request rate limit enforced by proxy |
| `GOOGLE_SOURCE_CHARS_PER_MINUTE` | `100000` | Google source-character per-minute limit enforced by proxy |
| `MICROSOFT_REQUESTS_PER_MINUTE` | `60` | Microsoft request rate limit enforced by proxy |
| `MICROSOFT_SOURCE_CHARS_PER_MINUTE` | `100000` | Microsoft source-character per-minute limit enforced by proxy |
| `DEEPL_REQUESTS_PER_MINUTE` | `60` | DeepL request rate limit enforced by proxy |
| `DEEPL_SOURCE_CHARS_PER_MINUTE` | `100000` | DeepL source-character per-minute limit enforced by proxy |
| `BATCH_MAX_CONCURRENCY` | `5` | Max concurrent translations processed in `/translate/batch` |
| `MOCK_TRANSLATION` | `false` | If `true`, mock translation responses |

## Notes

- The router picks the provider with the most remaining characters and falls back if that provider fails or has no quota left.
- Quota consumption is reserved atomically in SQLite before provider calls to prevent concurrent requests from overshooting monthly caps.
- Provider per-minute request/character limits are enforced in SQLite so concurrent traffic cannot exceed configured rate limits.
- Quotas are tracked by month (`YYYY-MM`) in UTC.
