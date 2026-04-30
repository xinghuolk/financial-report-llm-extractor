"""Evidence block and logical chunk artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.ingestion import PageRecord


BlockKind = Literal["layout_line"]
LogicalChunkKind = Literal["page_text", "statement_table"]
StatementKind = Literal["balance_sheet", "income_statement", "cash_flow"]

CHUNKER_VERSION = "phase2-logical-chunks-v1"


@dataclass(frozen=True)
class BlockRecord:
    block_id: str
    page: int
    kind: BlockKind
    text: str


@dataclass(frozen=True)
class LogicalChunkRecord:
    chunk_id: str
    kind: LogicalChunkKind
    page_start: int
    page_end: int
    block_ids: tuple[str, ...]
    text: str
    statement_kind: StatementKind | None = None


@dataclass(frozen=True)
class ChunkStore:
    source_pdf_hash: str
    blocks: tuple[BlockRecord, ...]
    chunks: tuple[LogicalChunkRecord, ...]


@dataclass(frozen=True)
class ChunkStoreResult:
    chunks_path: Path
    block_count: int
    chunk_count: int


def split_page_blocks(page: PageRecord) -> list[BlockRecord]:
    blocks: list[BlockRecord] = []
    raw_paragraphs = [p for p in re.split(r"\n\s*\n+", page.text.strip()) if p.strip()]
    paragraphs = _merge_statement_title_paragraphs(raw_paragraphs)
    for index, paragraph in enumerate(paragraphs, start=1):
        text = "\n".join(line.strip() for line in paragraph.splitlines() if line.strip())
        blocks.append(
            BlockRecord(
                block_id=f"p{page.page:04d}_b{index:04d}",
                page=page.page,
                kind="layout_line",
                text=text,
            )
        )
    return blocks


def _merge_statement_title_paragraphs(paragraphs: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        is_title_only = "\n" not in paragraph.strip()
        if (
            is_title_only
            and detect_statement_kind(paragraph) is not None
            and index + 1 < len(paragraphs)
        ):
            merged.append(f"{paragraph}\n{paragraphs[index + 1]}")
            index += 2
            continue
        merged.append(paragraph)
        index += 1
    return merged


def detect_statement_kind(text: str) -> StatementKind | None:
    normalized = " ".join(text.lower().split())
    if "资产负债表" in text or "statement of financial position" in normalized:
        return "balance_sheet"
    if "利润表" in text or "profit or loss" in normalized or "income statement" in normalized:
        return "income_statement"
    if "现金流量表" in text or "cash flow" in normalized or "cash flows" in normalized:
        return "cash_flow"
    return None


def is_statement_terminator(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    cn_markers = (
        "财务报表附注",
        "财务报表注释",
        "附注",
        "审计报告",
        "管理层讨论",
    )
    en_markers = (
        "notes to the financial statements",
        "notes to consolidated financial statements",
        "independent auditor",
        "independent auditor's report",
        "management discussion",
        "management's discussion",
    )
    return any(marker in text for marker in cn_markers) or any(
        marker in normalized for marker in en_markers
    )


def chunk_pages(
    pages: list[PageRecord],
    *,
    source_pdf_hash: str,
) -> ChunkStore:
    blocks = tuple(block for page in pages for block in split_page_blocks(page))
    page_chunks = _build_page_chunks(blocks)
    statement_chunks = _build_statement_chunks(blocks)
    return ChunkStore(
        source_pdf_hash=source_pdf_hash,
        blocks=blocks,
        chunks=tuple(page_chunks + statement_chunks),
    )


def build_chunk_store(
    pages_path: Path,
    metadata_path: Path,
    *,
    chunks_path: Path | None = None,
) -> ChunkStoreResult:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pages = _read_pages_jsonl(pages_path)
    output_path = chunks_path or pages_path.parent / "chunks.jsonl"
    store = chunk_pages(pages, source_pdf_hash=metadata["source_pdf_hash"])
    block_texts = {block.block_id: block.text for block in store.blocks}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as chunks_file:
        for block in store.blocks:
            chunks_file.write(
                json.dumps(
                    {
                        "record_type": "block",
                        "source_pdf_hash": store.source_pdf_hash,
                        "block_id": block.block_id,
                        "page": block.page,
                        "kind": block.kind,
                        "text": block.text,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            chunks_file.write("\n")
        for chunk in store.chunks:
            chunks_file.write(
                json.dumps(
                    {
                        "record_type": "chunk",
                        "source_pdf_hash": store.source_pdf_hash,
                        "chunk_id": chunk.chunk_id,
                        "kind": chunk.kind,
                        "statement_kind": chunk.statement_kind,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "block_ids": list(chunk.block_ids),
                        "block_texts": {
                            block_id: block_texts[block_id]
                            for block_id in chunk.block_ids
                        },
                        "text": chunk.text,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            chunks_file.write("\n")

    metadata["chunker_version"] = CHUNKER_VERSION
    metadata.setdefault("artifacts", {})["chunks"] = str(output_path)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return ChunkStoreResult(
        chunks_path=output_path,
        block_count=len(store.blocks),
        chunk_count=len(store.chunks),
    )


def _read_pages_jsonl(pages_path: Path) -> list[PageRecord]:
    pages: list[PageRecord] = []
    for line in pages_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        pages.append(PageRecord(page=record["page"], text=record["text"]))
    return pages


def _build_page_chunks(blocks: tuple[BlockRecord, ...]) -> list[LogicalChunkRecord]:
    chunks: list[LogicalChunkRecord] = []
    pages = sorted({block.page for block in blocks})
    for page in pages:
        page_blocks = tuple(block for block in blocks if block.page == page)
        chunks.append(
            LogicalChunkRecord(
                chunk_id=f"page_p{page:04d}",
                kind="page_text",
                page_start=page,
                page_end=page,
                block_ids=tuple(block.block_id for block in page_blocks),
                text="\n".join(block.text for block in page_blocks),
            )
        )
    return chunks


def _build_statement_chunks(blocks: tuple[BlockRecord, ...]) -> list[LogicalChunkRecord]:
    starts: list[tuple[int, StatementKind]] = []
    for index, block in enumerate(blocks):
        statement_kind = detect_statement_kind(block.text)
        if statement_kind is not None:
            starts.append((index, statement_kind))

    chunks: list[LogicalChunkRecord] = []
    for start_number, (start_index, statement_kind) in enumerate(starts):
        next_statement_index = (
            starts[start_number + 1][0] if start_number + 1 < len(starts) else len(blocks)
        )
        end_index = _find_statement_end(blocks, start_index, next_statement_index)
        statement_blocks = blocks[start_index:end_index]
        if not statement_blocks:
            continue
        page_start = statement_blocks[0].page
        page_end = statement_blocks[-1].page
        chunks.append(
            LogicalChunkRecord(
                chunk_id=(
                    f"stmt_{statement_kind}_p{page_start:04d}_p{page_end:04d}"
                ),
                kind="statement_table",
                statement_kind=statement_kind,
                page_start=page_start,
                page_end=page_end,
                block_ids=tuple(block.block_id for block in statement_blocks),
                text="\n".join(block.text for block in statement_blocks),
            )
        )
    return chunks


def _find_statement_end(
    blocks: tuple[BlockRecord, ...],
    start_index: int,
    fallback_end_index: int,
) -> int:
    for index in range(start_index + 1, fallback_end_index):
        if is_statement_terminator(blocks[index].text):
            return index
    return fallback_end_index
