"""Default path resolution: catalog/taxonomy via importlib.resources;
cache_root via env var or ~/.cache fallback.

These tests must work even when CWD is not the repo root."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_default_catalog_path_resolves_via_importlib_resources() -> None:
    """The packaged catalog must be loadable without CWD assumption."""
    from financial_report_llm_extractor.client import (
        resolve_catalog_path,
        resolve_taxonomy_path,
    )

    catalog = resolve_catalog_path(override=None)
    assert catalog.exists(), f"catalog file not found: {catalog}"
    assert catalog.name == "turtle_v015_source_mapping_minimal.json"

    taxonomy = resolve_taxonomy_path(override=None)
    assert taxonomy.exists(), f"taxonomy file not found: {taxonomy}"
    assert taxonomy.name == "turtle_v015_field_taxonomy.json"


def test_catalog_path_override_takes_precedence(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import resolve_catalog_path

    custom = tmp_path / "my_catalog.json"
    custom.write_text("{}", encoding="utf-8")
    assert resolve_catalog_path(override=custom) == custom


def test_cache_root_uses_env_var_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    custom = tmp_path / "custom_cache"
    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(custom))
    assert resolve_cache_root(override=None) == custom


def test_cache_root_falls_back_to_user_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    monkeypatch.delenv("FR_LLM_CACHE_ROOT", raising=False)
    fake_home = tmp_path / "fake_home"
    monkeypatch.setenv("HOME", str(fake_home))
    result = resolve_cache_root(override=None)
    assert result == fake_home / ".cache" / "financial-report-llm-extractor"


def test_cache_root_override_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    # env var set but override should win
    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(tmp_path / "env_wins"))
    custom = tmp_path / "override_wins"
    assert resolve_cache_root(override=custom) == custom


def test_db_path_default_is_under_cache_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import (
        resolve_cache_root,
        resolve_db_path,
    )

    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(tmp_path / "c"))
    cache_root = resolve_cache_root(override=None)
    db = resolve_db_path(override=None, cache_root=cache_root)
    assert db == cache_root / "extracted.db"
