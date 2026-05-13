"""DDL constants for the extraction cache DB."""

from financial_report_llm_extractor.cache import db_schema


def test_extractions_ddl_contains_primary_key() -> None:
    sql = db_schema.CREATE_EXTRACTIONS_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "extractions" in sql
    assert "PRIMARY KEY" in sql
    for col in ("company", "period_end", "market", "catalog_version"):
        assert col in sql


def test_field_values_ddl_contains_required_columns() -> None:
    sql = db_schema.CREATE_FIELD_VALUES_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "field_values" in sql
    # No SQL FOREIGN KEY — relationship to extractions is logical only,
    # enforced by the indexer (DELETE-then-INSERT semantic).
    assert "FOREIGN KEY" not in sql
    # Columns introduced in the design review (reason + priority denormalized)
    for col in (
        "bucket", "field_id", "value", "reason", "priority",
        "evidence_page", "llm_confidence", "llm_reasoning_short",
    ):
        assert col in sql, f"missing column {col}"


def test_indexes_present() -> None:
    sql = db_schema.CREATE_FIELD_VALUES_INDEXES_SQL
    for idx in (
        "idx_field_values_field",
        "idx_field_values_bucket",
        "idx_field_values_priority",
    ):
        assert idx in sql, f"missing index {idx}"
