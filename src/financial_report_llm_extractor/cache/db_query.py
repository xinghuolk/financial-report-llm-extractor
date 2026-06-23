"""Read-side queries against the extraction cache DB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.db import connect


_FIELD_COLUMNS = (
    "bucket", "value", "currency", "unit", "selected_source",
    "reason", "evidence_page", "llm_confidence", "llm_reasoning_short",
    "priority", "normalized_value", "canonical_unit",
)


def query_field(
    *,
    db_path: Path,
    company: str,
    period_end: str,
    market: str,
    field_id: str,
) -> dict[str, Any] | None:
    """Return one field row as a dict, or None on miss."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            f"SELECT {', '.join(_FIELD_COLUMNS)} "
            "FROM field_values "
            "WHERE company = ? AND period_end = ? AND market = ? AND field_id = ?",
            (company, period_end, market, field_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _decode_field_row(
        company=company, period_end=period_end, market=market,
        field_id=field_id, row=row,
    )


def query_extraction(
    *,
    db_path: Path,
    company: str,
    period_end: str,
    market: str,
) -> dict[str, Any] | None:
    """Return extraction metadata + all field rows as a nested dict."""
    conn = connect(db_path)
    try:
        meta = conn.execute(
            """
            SELECT market, report_type, catalog_version, schema_version,
                   generated_at, artifact_path, llm_provider, llm_model
            FROM extractions
            WHERE company = ? AND period_end = ? AND market = ?
            ORDER BY catalog_version DESC
            LIMIT 1
            """,
            (company, period_end, market),
        ).fetchone()
        if meta is None:
            return None
        field_rows = list(
            conn.execute(
                f"SELECT field_id, {', '.join(_FIELD_COLUMNS)} "
                "FROM field_values "
                "WHERE company = ? AND period_end = ? AND market = ?",
                (company, period_end, market),
            )
        )
    finally:
        conn.close()
    fields: dict[str, dict[str, Any]] = {}
    for r in field_rows:
        fid = r[0]
        decoded = _decode_field_row(
            company=company, period_end=period_end, market=market,
            field_id=fid, row=r[1:],
        )
        fields[fid] = {k: v for k, v in decoded.items()
                       if k not in {"company", "period_end", "market", "field_id"}}
    return {
        "company": company,
        "period_end": period_end,
        "market": market,
        "report_type": meta[1],
        "catalog_version": meta[2],
        "schema_version": meta[3],
        "generated_at": meta[4],
        "artifact_path": meta[5],
        "llm_provider": meta[6],
        "llm_model": meta[7],
        "fields": fields,
    }


def list_companies(*, db_path: Path) -> list[tuple[str, str, str, str]]:
    """Return list of (company, period_end, market, catalog_version) tuples."""
    conn = connect(db_path)
    try:
        return [
            (r[0], r[1], r[2], r[3])
            for r in conn.execute(
                "SELECT company, period_end, market, catalog_version "
                "FROM extractions ORDER BY company, period_end"
            )
        ]
    finally:
        conn.close()


def _decode_field_row(
    *, company: str, period_end: str, market: str, field_id: str,
    row: tuple[Any, ...],
) -> dict[str, Any]:
    (bucket, value_text, currency, unit, selected_source, reason,
     evidence_page, llm_confidence, llm_reasoning_short, priority,
     normalized_value, canonical_unit) = row
    return {
        "company": company,
        "period_end": period_end,
        "market": market,
        "field_id": field_id,
        "priority": priority,
        "bucket": bucket,
        "value": json.loads(value_text) if value_text is not None else None,
        "currency": currency,
        "unit": unit,
        "selected_source": selected_source,
        "reason": reason,
        "evidence_page": evidence_page,
        "llm_confidence": llm_confidence,
        "llm_reasoning_short": llm_reasoning_short,
        "normalized_value": normalized_value,
        "canonical_unit": canonical_unit,
    }
