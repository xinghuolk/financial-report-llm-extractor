"""Task 7: FieldValue 公共 API 新增 normalized_value + canonical_unit 字段测试。"""

from __future__ import annotations

from decimal import Decimal

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
