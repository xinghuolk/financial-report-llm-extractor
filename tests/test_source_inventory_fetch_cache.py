"""Verify _fetch_*_for_company helpers honour the provider cache."""

from __future__ import annotations

import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock

from financial_report_llm_extractor.cache.provider_cache import (
    cache_path,
    cache_put,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    _record_to_jsonable,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    _fetch_akshare_for_company,
)


def _make_fake_record(
    ticker: str = "600519",
    period: str = "2024-12-31",
) -> SourceInventoryRecord:
    """Construct a minimal but valid SourceInventoryRecord for testing."""
    return SourceInventoryRecord(
        source="akshare",
        market="CN",
        ticker=ticker,
        statement_type="balance_sheet",
        period=period,
        raw_field_name="TOTAL_ASSETS",
        raw_value="100000",
        currency="CNY",
        unit="yuan",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="AkshareAdapter",
                function="fetch_cn_statement_inventory",
                artifact_id="aid_1",
                raw_record_id="rid_1",
                raw_field_name="TOTAL_ASSETS",
            ),
        ),
    )


class _FakeAdapter:
    """Minimal AkshareAdapter substitute that returns a fixed record set."""

    def __init__(self, records: tuple[SourceInventoryRecord, ...]) -> None:
        self._records = records

    def fetch_cn_statement_inventory(
        self, *, ticker: str, exchange: str, statement_type: str, unit: str
    ) -> list[SourceInventoryRecord]:
        return list(self._records)

    def fetch_hk_statement_inventory(
        self, *, ticker: str, statement_type: str, unit: str
    ) -> list[SourceInventoryRecord]:
        return []


def test_fetch_akshare_uses_cache_when_fresh(tmp_path: Path) -> None:
    """If cache is fresh, _fetch_akshare_for_company must NOT invoke the client."""
    cache_root = tmp_path / "cache"
    record = _make_fake_record()
    record_dict = _record_to_jsonable(record)
    cache_put(
        cache_root=cache_root,
        provider="akshare",
        company="600519",
        period_end="2024-12-31",
        records=[record_dict],
    )

    client = MagicMock()
    store = SourceArtifactStore(tmp_path / "artifacts")

    result = _fetch_akshare_for_company(
        company="600519",
        market="CN",
        client=client,
        store=store,
        cache_root=cache_root,
        cache_key="2024-12-31",
        ttl_hours=24,
    )

    assert len(result) == 1
    assert result[0].ticker == "600519"
    # Client must not have been touched at all
    client.assert_not_called()
    assert client.method_calls == []


def test_fetch_akshare_writes_cache_on_miss(tmp_path: Path) -> None:
    """On cache miss, _fetch_akshare_for_company should write the cache file."""
    import financial_report_llm_extractor.structured_sources.source_inventory_fetch as sif

    cache_root = tmp_path / "cache"
    fake_record = _make_fake_record()

    fake_adapter = _FakeAdapter((fake_record,))

    with mock.patch.object(sif, "AkshareAdapter", lambda **kwargs: fake_adapter):
        store = SourceArtifactStore(tmp_path / "artifacts")
        result = _fetch_akshare_for_company(
            company="600519",
            market="CN",
            client=MagicMock(),
            store=store,
            cache_root=cache_root,
            cache_key="2024-12-31",
            ttl_hours=24,
        )

    assert len(result) >= 1
    # Cache file must now exist
    cf = cache_path(
        cache_root=cache_root,
        provider="akshare",
        company="600519",
        period_end="2024-12-31",
    )
    assert cf.exists()


def test_fetch_akshare_no_cache_when_cache_root_is_none(tmp_path: Path) -> None:
    """If cache_root is None, no cache file should be created."""
    import financial_report_llm_extractor.structured_sources.source_inventory_fetch as sif

    fake_record = _make_fake_record()
    fake_adapter = _FakeAdapter((fake_record,))

    with mock.patch.object(sif, "AkshareAdapter", lambda **kwargs: fake_adapter):
        result = _fetch_akshare_for_company(
            company="600519",
            market="CN",
            client=MagicMock(),
            store=SourceArtifactStore(tmp_path / "artifacts"),
            cache_root=None,
            cache_key=None,
        )

    assert len(result) >= 1
    # No cache directory was created
    assert not (tmp_path / "cache").exists()
