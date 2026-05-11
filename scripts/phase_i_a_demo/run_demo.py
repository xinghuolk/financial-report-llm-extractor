"""Phase I-A feasibility demo.

Tests cross-company generalization of LLM field extraction:
- ingest + chunk arbitrary HK PDF
- alias-based chunk retrieval for standard fields
- broad statement-type chunk selection for non-standard fields
- LLM extraction via existing llm_field_extraction module

Run:
    set -a; source .env; set +a
    uv run python scripts/phase_i_a_demo/run_demo.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from financial_report_llm_extractor.llm_field_extraction import (  # noqa: E402
    FieldExtractionRequest,
    run_field_extraction,
)
from financial_report_llm_extractor.llm_transport import (  # noqa: E402
    LlmTransportConfig,
    create_llm_client,
)


# Six HK PDFs available locally
COMPANIES = [
    ("00001", "downloads/hk_stocks/00001/annual/2025_annual_en.pdf"),
    ("01113", "downloads/hk_stocks/01113/annual/2025_annual_en.pdf"),
    ("01810", "downloads/hk_stocks/01810/annual/2024_annual_en.pdf"),
    ("02498", "downloads/hk_stocks/02498/annual/2024_annual_en.pdf"),
    ("06862", "downloads/hk_stocks/06862/annual/2024_annual_en.pdf"),
    ("09987", "downloads/hk_stocks/09987/annual/2025_annual_en.pdf"),
]


@dataclass(frozen=True)
class FieldDef:
    field_id: str
    description: str
    statement_type: str
    standard_aliases: tuple[str, ...]   # for alias-based scoring (standard fields)
    notes_keywords: tuple[str, ...]     # for broad notes inclusion (non-standard)
    is_standard: bool                   # whether to rely on alias retrieval


FIELDS: list[FieldDef] = [
    FieldDef(
        field_id="accounts_receiv",
        description=(
            "Trade receivables (accounts receivable from customers). "
            "On HK balance sheets often reported within 'Trade receivables and "
            "other current assets' or 'Debtors, prepayments and others'. "
            "The precise trade receivables figure is typically broken out in a "
            "supporting note. Return the trade receivables value (not the "
            "combined category)."
        ),
        statement_type="balance_sheet",
        standard_aliases=(
            "trade receivables",
            "accounts receivable",
            "应收账款",
            "应收帐款",
            "trade and other receivables",
            "debtors",
        ),
        notes_keywords=("receivable", "debtor"),
        is_standard=True,
    ),
    FieldDef(
        field_id="rd_exp",
        description=(
            "Research and development expenses. HK companies that don't have "
            "a discrete R&D line on the income statement may disclose it in "
            "MD&A or notes. Some HK issuers (non-tech) report no R&D expense. "
            "Return the explicit R&D expense if disclosed; otherwise return "
            "found=false."
        ),
        statement_type="income_statement",
        standard_aliases=(
            "research and development",
            "r&d expense",
            "研发费用",
            "research expense",
        ),
        notes_keywords=("research", "r&d", "development cost"),
        is_standard=False,
    ),
]


def run_cli(cmd: list[str]) -> None:
    """Run CLI command, raise on failure."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDOUT: {result.stdout}")
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def ensure_chunks(ticker: str, pdf_path: Path, work_dir: Path) -> Path:
    """Ingest + chunk PDF, return path to chunks.jsonl."""
    chunks_path = work_dir / "chunks.jsonl"
    if chunks_path.exists():
        return chunks_path

    work_dir.mkdir(parents=True, exist_ok=True)
    pages_path = work_dir / "pages.jsonl"
    metadata_path = work_dir / "run_metadata.json"

    if not pages_path.exists():
        run_cli([
            "uv", "run", "financial-report-llm-extractor", "ingest",
            "--pdf", str(pdf_path),
            "--out", str(work_dir),
        ])

    run_cli([
        "uv", "run", "financial-report-llm-extractor", "chunk",
        "--pages", str(pages_path),
        "--metadata", str(metadata_path),
        "--out", str(chunks_path),
    ])
    return chunks_path


def load_chunks(path: Path) -> list[dict[str, object]]:
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            chunks.append(json.loads(line))
    return chunks


def alias_score(chunk_text: str, aliases: tuple[str, ...]) -> int:
    """Naive alias scorer: count alias occurrences (case-insensitive)."""
    text_lower = chunk_text.lower()
    return sum(text_lower.count(a.lower()) for a in aliases)


def select_chunks_for_field(
    chunks: list[dict[str, object]],
    field: FieldDef,
    *,
    top_k_standard: int = 8,
    notes_chunk_limit: int = 30,
) -> list[dict[str, object]]:
    """Field-specific chunk selection.

    Standard fields: alias score → top-k by score.
    Non-standard fields: include all chunks where notes_keywords appear,
    up to notes_chunk_limit, plus any income_statement chunks.
    """
    if field.is_standard:
        scored = []
        for c in chunks:
            text = str(c.get("text", "") or "")
            score = alias_score(text, field.standard_aliases)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k_standard]]

    # Non-standard: broader. Include keyword-matching chunks + statement-typed
    # chunks. This errs toward more context for the LLM.
    selected: list[dict[str, object]] = []
    seen_ids = set()
    for c in chunks:
        text = str(c.get("text", "") or "").lower()
        chunk_id = str(c.get("chunk_id") or c.get("block_id") or "")
        if any(kw in text for kw in field.notes_keywords):
            if chunk_id not in seen_ids:
                selected.append(c)
                seen_ids.add(chunk_id)
        if len(selected) >= notes_chunk_limit:
            break
    return selected


def trim_chunk_text(chunk: dict[str, object], max_chars: int = 2000) -> dict[str, object]:
    """Truncate long chunk text to keep prompt under budget."""
    text = str(chunk.get("text", "") or "")
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    out = dict(chunk)
    out["text"] = text
    return out


def main() -> None:
    if os.environ.get("REAL_LLM_SMOKE") != "1":
        print("Set REAL_LLM_SMOKE=1 to run the demo.")
        sys.exit(2)

    config_path = Path(os.environ.get("LLM_CONFIG_PATH", "tmp/llm_configs/deepseek.json"))
    if not config_path.exists():
        print(f"LLM config not found: {config_path}")
        sys.exit(2)

    config = LlmTransportConfig.from_json(config_path)
    client = create_llm_client(config)

    out_root = REPO_ROOT / "tmp" / "runs" / "phase_i_a_demo"
    out_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict[str, dict[str, object]]] = {}

    for ticker, pdf_rel in COMPANIES:
        pdf_path = REPO_ROOT / pdf_rel
        if not pdf_path.exists():
            print(f"SKIP {ticker}: PDF not found at {pdf_path}")
            continue

        print(f"\n=== {ticker} ===")
        ticker_dir = out_root / ticker
        chunks_dir = ticker_dir / "ingest"

        try:
            chunks_path = ensure_chunks(ticker, pdf_path, chunks_dir)
        except Exception as exc:
            print(f"  INGEST FAILED: {exc}")
            summary.setdefault(ticker, {})["_ingest_error"] = {"error": str(exc)}
            continue

        all_chunks = load_chunks(chunks_path)
        print(f"  total chunks: {len(all_chunks)}")

        ticker_summary: dict[str, dict[str, object]] = {}

        for field in FIELDS:
            field_dir = ticker_dir / field.field_id
            field_dir.mkdir(parents=True, exist_ok=True)

            selected = select_chunks_for_field(all_chunks, field)
            trimmed = [trim_chunk_text(c) for c in selected]
            (field_dir / "selected_chunks.json").write_text(
                json.dumps([{
                    "chunk_id": c.get("chunk_id") or c.get("block_id"),
                    "page": c.get("page"),
                    "text_preview": str(c.get("text", ""))[:200],
                } for c in selected], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print(f"  {field.field_id}: {len(selected)} chunks selected")

            if not selected:
                ticker_summary[field.field_id] = {
                    "status": "no_chunks",
                    "selected_chunk_count": 0,
                }
                continue

            request = FieldExtractionRequest(
                field_id=field.field_id,
                field_description=field.description,
                statement_type=field.statement_type,
                value_type="money",
                chunks=tuple(trimmed),
                expected_currency="HKD",
                expected_unit="million",
            )

            try:
                result = run_field_extraction(
                    request,
                    client,
                    raw_response_dir=field_dir,
                )
            except Exception as exc:
                print(f"    LLM call failed: {exc}")
                ticker_summary[field.field_id] = {
                    "status": "llm_call_failed",
                    "error": str(exc),
                    "selected_chunk_count": len(selected),
                }
                continue

            ticker_summary[field.field_id] = {
                "status": result.status,
                "value": result.value,
                "parsed_numeric_value": str(result.parsed_numeric_value)
                    if result.parsed_numeric_value is not None else None,
                "currency": result.currency,
                "unit": result.unit,
                "page": result.page,
                "statement_line": result.statement_line,
                "confidence": result.confidence,
                "reasoning": (result.reasoning or "")[:200],
                "errors": list(result.errors),
                "selected_chunk_count": len(selected),
            }
            (field_dir / "extraction_result.json").write_text(
                json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            print(
                f"    -> status={result.status} value={result.value} "
                f"page={result.page} unit={result.unit}"
            )

        summary[ticker] = ticker_summary

    summary_path = out_root / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSummary: {summary_path}")

    # Brief tabular print
    print("\n" + "=" * 80)
    print(f"{'ticker':<10s} {'field':<25s} {'status':<20s} {'value':<20s} {'page':<6s}")
    print("=" * 80)
    for ticker, fields in summary.items():
        for fid, info in fields.items():
            if fid.startswith("_"):
                continue
            print(
                f"{ticker:<10s} {fid:<25s} "
                f"{str(info.get('status', '?')):<20s} "
                f"{str(info.get('value', '-'))[:19]:<20s} "
                f"{str(info.get('page', '-')):<6s}"
            )


if __name__ == "__main__":
    main()
