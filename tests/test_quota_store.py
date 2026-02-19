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
