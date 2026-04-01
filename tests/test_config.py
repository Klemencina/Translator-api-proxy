from __future__ import annotations

from pathlib import Path

from app import config


def test_default_database_path_prefers_env_override(monkeypatch):
    monkeypatch.setenv("USAGE_DB_PATH", "/custom/usage.db")

    assert config._default_database_path() == "/custom/usage.db"


def test_default_database_path_uses_local_file_when_data_dir_missing(monkeypatch):
    monkeypatch.delenv("USAGE_DB_PATH", raising=False)
    monkeypatch.setattr(Path, "is_dir", lambda self: False)

    assert config._default_database_path() == "usage.db"


def test_default_database_path_uses_data_dir_inside_container(monkeypatch):
    monkeypatch.delenv("USAGE_DB_PATH", raising=False)
    monkeypatch.setattr(Path, "is_dir", lambda self: str(self) == "\\data" or str(self) == "/data")

    assert config._default_database_path() == "/data/usage.db"
