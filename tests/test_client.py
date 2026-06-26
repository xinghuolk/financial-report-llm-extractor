"""Task 7: FieldValue 公共 API 新增 normalized_value + canonical_unit 字段测试。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from financial_report_llm_extractor.client import build_field_value


def test_build_field_value_carries_normalized() -> None:
    db_row = {
        "bucket": "llm_supplement_present",
        "value": "10080.83",
        "currency": "CNY",
        "unit": "万元",
        "selected_source": "llm",
        "evidence_page": None,
        "reason": None,
        "normalized_value": "100808300",
        "canonical_unit": "CNY",
    }
    fv = build_field_value(
        field_id="sbc",
        db_row=db_row,
        field_taxonomy={"value_type": "money"},
        include_llm_supplement=True,
    )
    assert fv.normalized_value == Decimal("100808300")
    assert fv.canonical_unit == "CNY"


def test_build_field_value_normalized_absent_when_no_column() -> None:
    db_row = {
        "bucket": "clean_present",
        "value": "some text",
        "currency": None,
        "unit": None,
        "selected_source": "akshare",
        "evidence_page": None,
        "reason": None,
    }
    fv = build_field_value(
        field_id="audit_opinion",
        db_row=db_row,
        field_taxonomy={"value_type": "text"},
        include_llm_supplement=True,
    )
    assert fv.normalized_value is None
    assert fv.canonical_unit is None


def test_build_field_value_normalized_none_when_value_none() -> None:
    db_row = {
        "bucket": "unresolved_conflict",
        "value": None,
        "currency": "CNY",
        "unit": "元",
        "selected_source": None,
        "evidence_page": None,
        "reason": "normalized_value_conflict",
        "normalized_value": "5000",
        "canonical_unit": "CNY",
    }
    fv = build_field_value(
        field_id="revenue",
        db_row=db_row,
        field_taxonomy={"value_type": "money"},
        include_llm_supplement=True,
    )
    # value 缺失 → normalized_value 与 canonical_unit 对称守护为 None
    assert fv.value is None
    assert fv.normalized_value is None
    assert fv.canonical_unit is None


def test_build_field_value_accounting_negative_parentheses() -> None:
    """HK 财报用括号表示负数 (4652) = -4652。build_field_value 须正确解析为
    负数（保留数据），而非崩溃或降级为 None（PR-25 后港股崩溃根因）。"""
    db_row = {
        "bucket": "llm_supplement_present", "value": "(4652)",
        "currency": "CNY", "unit": "千元", "selected_source": "llm",
        "evidence_page": None, "reason": None,
    }
    fv = build_field_value(
        field_id="c_paid_for_taxes", db_row=db_row,
        field_taxonomy={"value_type": "money"}, include_llm_supplement=True,
    )
    assert fv.value == Decimal("-4652")


def test_build_field_value_comma_and_paren_combined() -> None:
    db_row = {
        "bucket": "llm_supplement_present", "value": "(5,571)",
        "currency": "CNY", "unit": "千元", "selected_source": "llm",
        "evidence_page": None, "reason": None,
    }
    fv = build_field_value(
        field_id="x", db_row=db_row,
        field_taxonomy={"value_type": "number"}, include_llm_supplement=True,
    )
    assert fv.value == Decimal("-5571")


def test_build_field_value_truly_invalid_degrades_to_none() -> None:
    """真正非法的数值（N/A、空串）降级为 None，不抛异常。"""
    for bad in ["N/A", "", "  "]:
        db_row = {
            "bucket": "clean_present", "value": bad, "currency": "CNY",
            "unit": "元", "selected_source": "akshare",
            "evidence_page": None, "reason": None,
        }
        fv = build_field_value(
            field_id="x", db_row=db_row,
            field_taxonomy={"value_type": "money"}, include_llm_supplement=True,
        )
        assert fv.value is None, f"{bad!r} should degrade to None"


def test_build_field_value_normalized_value_paren_safe() -> None:
    """normalized_value 列若意外含括号/逗号也不崩。"""
    db_row = {
        "bucket": "llm_supplement_present", "value": "100",
        "currency": "CNY", "unit": "元", "selected_source": "llm",
        "evidence_page": None, "reason": None,
        "normalized_value": "(1,234)", "canonical_unit": "CNY",
    }
    fv = build_field_value(
        field_id="x", db_row=db_row,
        field_taxonomy={"value_type": "money"}, include_llm_supplement=True,
    )
    assert fv.normalized_value == Decimal("-1234")


def test_materialize_from_hit_isolates_field_decode_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense-in-depth: 单个字段 build_field_value 崩，其余字段仍正常返回，
    崩的字段降级为 UNAVAILABLE（HK 00001 炸穿整份提取的根因防线）。"""
    import financial_report_llm_extractor.client as client_mod
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        ExtractorConfig,
        FinancialReportClient,
    )
    from financial_report_llm_extractor.cache.db import init_db

    db_path = tmp_path / "empty.db"
    init_db(db_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )

    real = client_mod.build_field_value

    def flaky(**kwargs: Any) -> Any:
        if kwargs.get("field_id") == "bad":
            raise RuntimeError("boom")
        return real(**kwargs)

    monkeypatch.setattr(client_mod, "build_field_value", flaky)

    hit = {
        "catalog_version": "x", "generated_at": "t",
        "fields": {
            "good": {"bucket": "clean_present", "value": "100",
                     "currency": "CNY", "unit": "元"},
            "bad": {"bucket": "clean_present", "value": "1",
                    "currency": "CNY", "unit": "元"},
        },
    }
    result = client._materialize_from_hit(
        hit=hit, company="X", period_end="2024-12-31", market="CN",
        current_version="x", include_llm_supplement=True,
    )
    assert result.fields["good"].value is not None
    assert result.fields["bad"].confidence == ConfidenceLevel.UNAVAILABLE
    assert result.fields["bad"].reason == "field_decode_error"
