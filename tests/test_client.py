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
