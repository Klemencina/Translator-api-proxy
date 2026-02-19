from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.quota import QuotaStore


def test_try_reserve_is_atomic_under_concurrency(tmp_path: Path):
    store = QuotaStore(str(tmp_path / "usage.db"))
    provider = "google"
    quota = 10
    charge = 7

    def reserve_once() -> bool:
        return store.try_reserve(provider, charge, quota)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve_once(), range(2)))

    assert sum(results) == 1
    assert store.get_used(provider) == charge


def test_release_reverts_reserved_usage(tmp_path: Path):
    store = QuotaStore(str(tmp_path / "usage.db"))
    provider = "deepl"

    assert store.try_reserve(provider, 5, 20)
    assert store.get_used(provider) == 5

    store.release(provider, 5)
    assert store.get_used(provider) == 0


def test_try_consume_rate_limit_enforces_requests_and_chars(tmp_path: Path):
    store = QuotaStore(str(tmp_path / "usage.db"))
    provider = "microsoft"
    minute = "2026-02-19T07:42"

    assert store.try_consume_rate_limit(provider, 1, 4, 2, 10, minute=minute)
    assert store.try_consume_rate_limit(provider, 1, 4, 2, 10, minute=minute)
    assert not store.try_consume_rate_limit(provider, 1, 1, 2, 10, minute=minute)

    req_used, chars_used = store.get_rate_usage(provider, minute=minute)
    assert req_used == 2
    assert chars_used == 8


def test_try_consume_rate_limit_is_atomic_under_concurrency(tmp_path: Path):
    store = QuotaStore(str(tmp_path / "usage.db"))
    provider = "google"
    minute = "2026-02-19T07:43"

    def consume_once() -> bool:
        return store.try_consume_rate_limit(provider, 1, 60, 1, 100, minute=minute)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume_once(), range(2)))

    assert sum(results) == 1
    req_used, chars_used = store.get_rate_usage(provider, minute=minute)
    assert req_used == 1
    assert chars_used == 60
