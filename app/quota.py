from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


class QuotaStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage (
                    provider TEXT NOT NULL,
                    usage_month TEXT NOT NULL,
                    used_chars INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, usage_month)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_usage (
                    provider TEXT NOT NULL,
                    usage_minute TEXT NOT NULL,
                    used_requests INTEGER NOT NULL DEFAULT 0,
                    used_source_chars INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, usage_minute)
                )
                """
            )

    @staticmethod
    def current_month() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m")

    @staticmethod
    def current_minute() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")

    def get_used(self, provider: str, month: str | None = None) -> int:
        usage_month = month or self.current_month()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT used_chars FROM usage WHERE provider = ? AND usage_month = ?",
                (provider, usage_month),
            ).fetchone()
        return int(row[0]) if row else 0

    def try_reserve(self, provider: str, chars: int, monthly_quota: int, month: str | None = None) -> bool:
        usage_month = month or self.current_month()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO usage(provider, usage_month, used_chars) VALUES(?, ?, 0)",
                (provider, usage_month),
            )
            result = conn.execute(
                """
                UPDATE usage
                SET used_chars = used_chars + ?
                WHERE provider = ?
                  AND usage_month = ?
                  AND used_chars + ? <= ?
                """,
                (chars, provider, usage_month, chars, monthly_quota),
            )
        return result.rowcount == 1

    def release(self, provider: str, chars: int, month: str | None = None) -> None:
        usage_month = month or self.current_month()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE usage
                SET used_chars = CASE WHEN used_chars > ? THEN used_chars - ? ELSE 0 END
                WHERE provider = ?
                  AND usage_month = ?
                """,
                (chars, chars, provider, usage_month),
            )

    def try_consume_rate_limit(
        self,
        provider: str,
        request_units: int,
        source_char_units: int,
        max_requests_per_minute: int,
        max_source_chars_per_minute: int,
        minute: str | None = None,
    ) -> bool:
        usage_minute = minute or self.current_minute()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO rate_usage(provider, usage_minute, used_requests, used_source_chars)
                VALUES(?, ?, 0, 0)
                """,
                (provider, usage_minute),
            )
            result = conn.execute(
                """
                UPDATE rate_usage
                SET used_requests = used_requests + ?,
                    used_source_chars = used_source_chars + ?
                WHERE provider = ?
                  AND usage_minute = ?
                  AND used_requests + ? <= ?
                  AND used_source_chars + ? <= ?
                """,
                (
                    request_units,
                    source_char_units,
                    provider,
                    usage_minute,
                    request_units,
                    max_requests_per_minute,
                    source_char_units,
                    max_source_chars_per_minute,
                ),
            )
        return result.rowcount == 1

    def get_rate_usage(self, provider: str, minute: str | None = None) -> tuple[int, int]:
        usage_minute = minute or self.current_minute()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT used_requests, used_source_chars FROM rate_usage WHERE provider = ? AND usage_minute = ?",
                (provider, usage_minute),
            ).fetchone()
        if not row:
            return (0, 0)
        return int(row[0]), int(row[1])
