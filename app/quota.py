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

    @staticmethod
    def current_month() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m")

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
