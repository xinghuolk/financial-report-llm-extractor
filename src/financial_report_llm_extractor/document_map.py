"""Parser capability and document structure artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParserCapabilityResult:
    output_path: Path
    page_count: int


@dataclass(frozen=True)
class DocumentMapResult:
    output_path: Path
    section_count: int


def write_parser_capability_probe(
    pages_path: Path,
    metadata_path: Path,
    *,
    output_path: Path | None = None,
) -> ParserCapabilityResult:
    pages = _read_jsonl(pages_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    output = output_path or pages_path.parent / "parser_capability.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    texts = [str(page.get("text", "")) for page in pages]
    non_empty_texts = [text for text in texts if text.strip()]
    total_chars = sum(len(text) for text in texts)
    page_count = len(pages)
    average_chars = total_chars / page_count if page_count else 0.0
    contains_financial_terms = any(
        _contains_financial_statement_terms(text) for text in texts
    )

    warnings: list[str] = []
    if page_count == 0:
        warnings.append("no_pages_extracted")
    if average_chars < 20:
        warnings.append("low_text_volume")
    if not contains_financial_terms:
        warnings.append("no_financial_statement_terms_detected")

    payload = {
        "parser_name": metadata.get("parser_name"),
        "parser_version": metadata.get("parser_version"),
        "source_pdf_hash": metadata.get("source_pdf_hash"),
        "page_count": page_count,
        "non_empty_page_count": len(non_empty_texts),
        "average_chars_per_page": average_chars,
        "contains_cjk": any(_contains_cjk(text) for text in texts),
        "contains_financial_statement_terms": contains_financial_terms,
        "warnings": warnings,
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ParserCapabilityResult(output_path=output, page_count=page_count)


def write_document_map(
    chunks_path: Path,
    *,
    output_path: Path | None = None,
) -> DocumentMapResult:
    blocks = [
        record for record in _read_jsonl(chunks_path) if record.get("record_type") == "block"
    ]
    output = output_path or chunks_path.parent / "document_map.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    sections = _detect_sections(blocks)
    output.write_text(
        json.dumps({"sections": sections}, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return DocumentMapResult(output_path=output, section_count=len(sections))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _contains_financial_statement_terms(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    terms = (
        "consolidated statement of financial position",
        "consolidated balance sheet",
        "consolidated income statement",
        "consolidated statement of comprehensive income",
        "consolidated statement of cash flows",
        "资产负债表",
        "利润表",
        "现金流量表",
    )
    return any(term in normalized or term in text for term in terms)


def _detect_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detected: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        kind = _section_kind(str(block.get("text", "")))
        if kind is None:
            continue
        detected.setdefault(kind, []).append(block)

    order = (
        "contents",
        "financial_summary",
        "management_discussion",
        "independent_auditor_report",
        "audited_financial_statements",
        "notes_to_financial_statements",
    )
    return [
        _section_payload(kind, detected[kind])
        for kind in order
        if kind in detected
    ]


def _section_kind(text: str) -> str | None:
    normalized = " ".join(text.lower().split())
    if "contents" in normalized or "目录" in text:
        return "contents"
    if "notes to the financial statements" in normalized:
        return "notes_to_financial_statements"
    if "independent auditor" in normalized:
        return "independent_auditor_report"
    if _contains_formal_statement_title(normalized, text):
        return "audited_financial_statements"
    if "management discussion" in normalized or "management's discussion" in normalized:
        return "management_discussion"
    if "financial summary" in normalized or "five year financial summary" in normalized:
        return "financial_summary"
    return None


def _contains_formal_statement_title(normalized: str, text: str) -> bool:
    return _contains_financial_statement_terms(text) and (
        "consolidated" in normalized
        or "合并" in text
        or "资产负债表" in text
        or "利润表" in text
        or "现金流量表" in text
    )


def _section_payload(kind: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    pages = [int(block["page"]) for block in blocks]
    first = blocks[0]
    return {
        "kind": kind,
        "page_start": min(pages),
        "page_end": max(pages),
        "confidence": 0.8,
        "evidence": [
            {
                "page": first.get("page"),
                "block_id": first.get("block_id"),
                "snippet": _first_line(str(first.get("text", ""))),
            }
        ],
    }


def _first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text.splitlines() else ""
