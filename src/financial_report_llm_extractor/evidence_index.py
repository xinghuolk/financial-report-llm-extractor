import re
from dataclasses import dataclass
from typing import Any


NUMBER_BODY_RE = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUMERIC_TOKEN_RE = re.compile(
    rf"(?<![\w.,])(?:\(-?{NUMBER_BODY_RE}\)|-{NUMBER_BODY_RE}|{NUMBER_BODY_RE})(?![\w.,])"
)
YEAR_TOKEN_RE = re.compile(r"\b20\d{2}\b")
TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class EvidenceBlock:
    block_id: str
    page: int
    chunk_id: str
    statement_kind: str | None
    text: str
    token_count: int
    numeric_token_count: int
    year_count: int


@dataclass(frozen=True)
class EvidenceIndex:
    blocks: tuple[EvidenceBlock, ...]


def build_evidence_index(records: list[dict[str, Any]]) -> EvidenceIndex:
    blocks: list[EvidenceBlock] = []
    block_records: dict[str, dict[str, Any]] = {
        str(record["block_id"]): record
        for record in records
        if record.get("record_type") == "block" and "block_id" in record
    }

    for record in records:
        if record.get("record_type") != "chunk":
            continue

        chunk_id = str(record["chunk_id"])
        block_texts = record.get("block_texts")
        if not isinstance(block_texts, dict):
            block_texts = {}

        for block_id in record.get("block_ids", []):
            block_id_text = str(block_id)
            block_record = block_records.get(block_id_text, {})
            page = int(block_record.get("page", record["page_start"]))
            text = str(
                block_record.get(
                    "text",
                    block_texts.get(block_id_text, record.get("text", "")),
                )
            )
            blocks.append(
                EvidenceBlock(
                    block_id=block_id_text,
                    page=page,
                    chunk_id=chunk_id,
                    statement_kind=record.get("statement_kind"),
                    text=text,
                    token_count=len(TOKEN_RE.findall(text)),
                    numeric_token_count=len(NUMERIC_TOKEN_RE.findall(text)),
                    year_count=len(YEAR_TOKEN_RE.findall(text)),
                )
            )

    return EvidenceIndex(blocks=tuple(blocks))
