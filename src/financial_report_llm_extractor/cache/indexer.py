"""Index a single evaluate-company run directory into the extraction DB.

Reads BOTH evaluation.json AND llm_evidence_supplement.json from the run dir
and UPSERTs one extractions row plus N field_values rows.

Why two files: evaluation.json carries the bucket assignment and
deterministic (clean_present) values, but for LLM-supplement buckets the
actual value/page/confidence/reasoning live in llm_evidence_supplement.json.
We join by field_id and pick the right source per bucket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from financial_report_llm_extractor.cache.db import connect


def index_run(
    *,
    run_dir: Path,
    db_path: Path,
    catalog_version: str,
    priority_map: Mapping[str, str],
) -> int:
    """Index the given run directory into the DB.

    Reads run_dir/evaluation.json (required) and run_dir/llm_evidence_supplement.json
    (optional — only LLM buckets need it). Returns the number of field rows
    written.

    Raises FileNotFoundError if evaluation.json does not exist.
    """
    eval_path = run_dir / "evaluation.json"
    if not eval_path.exists():
        raise FileNotFoundError(f"no evaluation.json under {run_dir}")
    payload = json.loads(eval_path.read_text(encoding="utf-8"))

    supplement_items: dict[str, dict[str, Any]] = {}
    llm_provider: str | None = None
    llm_model: str | None = None
    supp_path = run_dir / "llm_evidence_supplement.json"
    if supp_path.exists():
        supp_payload = json.loads(supp_path.read_text(encoding="utf-8"))
        llm_provider = _optional_text(supp_payload.get("llm_provider"))
        llm_model = _optional_text(supp_payload.get("llm_model"))
        items = supp_payload.get("items", {})
        if isinstance(items, dict):
            supplement_items = {
                str(k): v for k, v in items.items() if isinstance(v, dict)
            }

    company = str(payload["company"])
    period_end = str(payload["period_end"])
    market = str(payload["market"])
    report_type = str(payload.get("report_type", "annual"))
    schema_version = str(payload.get("schema_version", "evaluation_v1"))
    generated_at = str(payload.get("generated_at", ""))

    # Forward-compat: prefer catalog_version recorded in evaluation.json
    # (R4 will start writing this); fall back to the explicit argument.
    effective_catalog_version = str(
        payload.get("catalog_version") or catalog_version
    )

    fields: dict[str, dict[str, Any]] = payload.get("fields", {})

    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO extractions (
              company, period_end, market, report_type,
              catalog_version, schema_version, generated_at,
              artifact_path, llm_provider, llm_model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company, period_end, market, catalog_version)
            DO UPDATE SET
              schema_version = excluded.schema_version,
              generated_at   = excluded.generated_at,
              artifact_path  = excluded.artifact_path,
              llm_provider   = excluded.llm_provider,
              llm_model      = excluded.llm_model
            """,
            (
                company, period_end, market, report_type,
                effective_catalog_version, schema_version, generated_at,
                str(run_dir), llm_provider, llm_model,
            ),
        )

        # field_values is "latest catalog version only" — replace all rows
        # for this (company, period_end, market) on every index.
        # R5: scope DELETE by market so cross-market rows are not wiped.
        conn.execute(
            "DELETE FROM field_values "
            "WHERE company = ? AND period_end = ? AND market = ?",
            (company, period_end, market),
        )

        written = 0
        for field_id, eval_info in fields.items():
            bucket = str(eval_info.get("bucket", ""))
            supp = supplement_items.get(field_id, {})
            row = _merge_field_row(
                bucket=bucket,
                eval_info=eval_info,
                supplement=supp,
            )
            conn.execute(
                """
                INSERT INTO field_values (
                  company, period_end, market, field_id, priority, bucket, value,
                  currency, unit, selected_source, reason,
                  evidence_page, llm_confidence, llm_reasoning_short,
                  normalized_value, canonical_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company, period_end, market, field_id,
                    priority_map.get(field_id),
                    bucket,
                    row["value"],
                    row["currency"],
                    row["unit"],
                    row["selected_source"],
                    row["reason"],
                    row["evidence_page"],
                    row["llm_confidence"],
                    row["llm_reasoning_short"],
                    row["normalized_value"],
                    row["canonical_unit"],
                ),
            )
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def _merge_field_row(
    *,
    bucket: str,
    eval_info: dict[str, Any],
    supplement: dict[str, Any],
) -> dict[str, Any]:
    """Pick value/page/confidence/reasoning from the right source per bucket.

    - llm_supplement_present: prefer supplement, fall back to evaluation.
    - other buckets: use evaluation directly. Supplement metadata (if any)
      is ignored to avoid mixing LLM-attempt artifacts into deterministic rows.
    """
    eval_value = eval_info.get("value")

    if bucket == "llm_supplement_present":
        value = supplement.get("value") if supplement else eval_value
        page = supplement.get("page")
        confidence = supplement.get("confidence")
        reasoning = supplement.get("reasoning")
        currency = (
            supplement.get("currency") or eval_info.get("currency") or None
        )
        unit = supplement.get("unit") or eval_info.get("unit") or None
    else:
        value = eval_value
        page = None
        confidence = None
        reasoning = None
        currency = eval_info.get("currency")
        unit = eval_info.get("unit")

    return {
        "value": _json_encode(value),
        "currency": currency if currency != "unknown" else None,
        "unit": unit,
        "selected_source": eval_info.get("selected_source"),
        "reason": eval_info.get("reason"),
        "evidence_page": (
            int(page) if isinstance(page, (int, float)) and page else None
        ),
        "llm_confidence": (
            float(confidence)
            if isinstance(confidence, (int, float)) else None
        ),
        "llm_reasoning_short": _truncate(reasoning, 500),
        # normalized_value/canonical_unit always come from eval_info: normalization
        # happens upstream (LLM-merge funnel / provider) and is serialized into
        # evaluation.json. The raw llm_evidence_supplement items carry no normalized fields.
        "normalized_value": eval_info.get("normalized_value"),
        "canonical_unit": eval_info.get("canonical_unit"),
    }


def _json_encode(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _truncate(text: Any, max_chars: int) -> str | None:
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
