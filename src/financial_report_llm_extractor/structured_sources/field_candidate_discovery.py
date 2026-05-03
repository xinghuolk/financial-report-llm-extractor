"""Provider raw field candidate discovery for Turtle mappings."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Literal

from financial_report_llm_extractor.field_metadata import (
    FieldTaxonomyEntry,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.artifacts import read_source_inventory
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)

CandidateStrength = Literal["strong", "medium", "weak"]
FieldCandidateStatus = Literal[
    "has_candidates",
    "no_candidates",
    "not_applicable",
    "catalog_gap",
]

_COMMON_WORDS = {
    "and",
    "the",
    "of",
    "from",
    "to",
    "for",
    "net",
    "total",
}


@dataclass(frozen=True)
class ProviderRawField:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    normalized_names: tuple[str, ...]
    normalized_codes: tuple[str, ...]
    tickers: tuple[str, ...]
    periods: tuple[str, ...]
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _RawFieldBucket:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    tickers: set[str]
    periods: set[str]
    record_count: int


def normalize_match_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return re.sub(r"\s+", "", text)
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.lower().split())


def build_provider_raw_field_index(
    records: Iterable[SourceInventoryRecord],
) -> dict[tuple[str, str, str, str | None], ProviderRawField]:
    grouped: dict[tuple[str, str, str, str | None], _RawFieldBucket] = {}
    for record in records:
        if record.source_status != "present":
            continue
        key: tuple[str, str, str, str | None] = (
            record.source,
            record.statement_type,
            record.raw_field_name,
            record.raw_field_code,
        )
        bucket = grouped.setdefault(
            key,
            _RawFieldBucket(
                source=record.source,
                statement_type=record.statement_type,
                raw_field_name=record.raw_field_name,
                raw_field_code=record.raw_field_code,
                tickers=set(),
                periods=set(),
                record_count=0,
            ),
        )
        bucket.tickers.add(record.ticker)
        if record.period is not None:
            bucket.periods.add(record.period)
        bucket.record_count += 1

    index: dict[tuple[str, str, str, str | None], ProviderRawField] = {}
    for key, bucket in grouped.items():
        raw_field_name = bucket.raw_field_name
        raw_field_code = bucket.raw_field_code
        normalized_names = tuple(
            value
            for value in (normalize_match_text(raw_field_name),)
            if value
        )
        normalized_codes = tuple(
            value
            for value in (
                (
                    normalize_match_text(raw_field_code)
                    if isinstance(raw_field_code, str)
                    else ""
                ),
            )
            if value
        )
        index[key] = ProviderRawField(
            source=bucket.source,
            statement_type=bucket.statement_type,
            raw_field_name=raw_field_name,
            raw_field_code=raw_field_code,
            normalized_names=normalized_names,
            normalized_codes=normalized_codes,
            tickers=tuple(sorted(bucket.tickers)),
            periods=tuple(sorted(bucket.periods)),
            record_count=bucket.record_count,
        )
    return index


@dataclass(frozen=True)
class ProviderFieldCandidate:
    raw_field_name: str
    raw_field_code: str | None
    score: int
    strength: CandidateStrength
    signals: tuple[str, ...]
    target_count: int
    period_count: int
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCandidateGroup:
    candidates: tuple[ProviderFieldCandidate, ...]

    def to_dict(self) -> dict[str, object]:
        return {"candidates": [candidate.to_dict() for candidate in self.candidates]}


@dataclass(frozen=True)
class FieldCandidateReportEntry:
    priority: str
    statement_type: str
    source_mode: str
    status: FieldCandidateStatus
    providers: dict[str, ProviderCandidateGroup]

    def to_dict(self) -> dict[str, object]:
        return {
            "priority": self.priority,
            "statement_type": self.statement_type,
            "source_mode": self.source_mode,
            "status": self.status,
            "providers": {
                source: group.to_dict()
                for source, group in sorted(self.providers.items())
            },
        }


@dataclass(frozen=True)
class ProviderFieldCandidateReport:
    report_id: str
    version: str
    taxonomy_catalog: str
    mapping_catalog: str
    fixture: str
    priorities: tuple[str, ...]
    fields: dict[str, FieldCandidateReportEntry]

    @property
    def summary(self) -> dict[str, int]:
        statuses = [entry.status for entry in self.fields.values()]
        return {
            "field_count": len(statuses),
            "fields_with_candidates": statuses.count("has_candidates"),
            "fields_without_candidates": statuses.count("no_candidates"),
            "not_applicable_fields": statuses.count("not_applicable"),
            "catalog_gap_fields": statuses.count("catalog_gap"),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "version": self.version,
            "taxonomy_catalog": self.taxonomy_catalog,
            "mapping_catalog": self.mapping_catalog,
            "fixture": self.fixture,
            "priorities": list(self.priorities),
            "fields": {
                field_id: entry.to_dict()
                for field_id, entry in sorted(self.fields.items())
            },
            "summary": self.summary,
        }


def discover_provider_field_candidates(
    *,
    taxonomy_entries: dict[str, FieldTaxonomyEntry],
    mapping_entries: dict[str, SourceMappingEntry],
    records: Iterable[SourceInventoryRecord],
    priorities: tuple[str, ...] = ("P0", "P1"),
    fixture: str = "provider_field_baseline",
    taxonomy_catalog: str = "turtle_v015_field_taxonomy",
    mapping_catalog: str = "turtle_v015_source_mapping_minimal",
) -> ProviderFieldCandidateReport:
    raw_index = build_provider_raw_field_index(records)
    selected_priorities = set(priorities)
    fields: dict[str, FieldCandidateReportEntry] = {}
    for field_id, taxonomy in sorted(taxonomy_entries.items()):
        if taxonomy.priority not in selected_priorities:
            continue
        if taxonomy.source_mode in {"pdf_only", "llm_review"}:
            fields[field_id] = FieldCandidateReportEntry(
                priority=taxonomy.priority,
                statement_type=taxonomy.statement_type,
                source_mode=taxonomy.source_mode,
                status="not_applicable",
                providers={},
            )
            continue

        mapping = mapping_entries.get(field_id)
        provider_groups: dict[str, ProviderCandidateGroup] = {}
        for source in ("akshare", "yahoo"):
            candidates = _rank_provider_candidates(
                field_id=field_id,
                taxonomy=taxonomy,
                mapping=mapping,
                source=source,
                raw_fields=raw_index.values(),
            )
            if candidates:
                provider_groups[source] = ProviderCandidateGroup(candidates=candidates)
        provider_groups = _add_cross_provider_support(provider_groups)
        if mapping is None:
            status: FieldCandidateStatus = "catalog_gap"
        elif provider_groups:
            status = "has_candidates"
        else:
            status = "no_candidates"
        fields[field_id] = FieldCandidateReportEntry(
            priority=taxonomy.priority,
            statement_type=taxonomy.statement_type,
            source_mode=taxonomy.source_mode,
            status=status,
            providers=provider_groups,
        )

    return ProviderFieldCandidateReport(
        report_id="provider_field_candidate_report",
        version="1",
        taxonomy_catalog=taxonomy_catalog,
        mapping_catalog=mapping_catalog,
        fixture=fixture,
        priorities=priorities,
        fields=fields,
    )


def _rank_provider_candidates(
    *,
    field_id: str,
    taxonomy: FieldTaxonomyEntry,
    mapping: SourceMappingEntry | None,
    source: str,
    raw_fields: Iterable[ProviderRawField],
) -> tuple[ProviderFieldCandidate, ...]:
    source_aliases = set(mapping.source_aliases.get(source, ())) if mapping else set()
    normalized_aliases = {normalize_match_text(alias) for alias in source_aliases}
    field_tokens = _field_tokens(field_id, taxonomy)
    candidates: list[ProviderFieldCandidate] = []
    for raw in raw_fields:
        if raw.source != source:
            continue
        if raw.statement_type != taxonomy.statement_type:
            continue
        signals: list[str] = ["statement_match"]
        raw_labels = {
            raw.raw_field_name,
            raw.raw_field_code or "",
            *raw.normalized_names,
            *raw.normalized_codes,
        }
        normalized_raw_labels = {
            normalize_match_text(label)
            for label in raw_labels
            if label
        }
        if source_aliases.intersection(raw_labels) or normalized_aliases.intersection(
            normalized_raw_labels
        ):
            signals.insert(0, "existing_alias")
        elif normalized_raw_labels.intersection(field_tokens):
            signals.insert(0, "exact_text")
        elif _keyword_overlap(field_tokens, normalized_raw_labels) >= 2:
            signals.insert(0, "keyword_overlap")
        else:
            continue
        if len(raw.periods) > 1:
            signals.append("period_support")
        if len(raw.tickers) > 1:
            signals.append("provider_presence")
        score = _score_signals(signals)
        candidates.append(
            ProviderFieldCandidate(
                raw_field_name=raw.raw_field_name,
                raw_field_code=raw.raw_field_code,
                score=score,
                strength=_strength_for_score(score),
                signals=tuple(signals),
                target_count=len(raw.tickers),
                period_count=len(raw.periods),
                record_count=raw.record_count,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.raw_field_name,
                candidate.raw_field_code or "",
            ),
        )[:10]
    )


def _add_cross_provider_support(
    provider_groups: dict[str, ProviderCandidateGroup],
) -> dict[str, ProviderCandidateGroup]:
    if set(provider_groups) != {"akshare", "yahoo"}:
        return provider_groups
    provider_labels = {
        source: {
            normalize_match_text(candidate.raw_field_name)
            for candidate in group.candidates
        }
        for source, group in provider_groups.items()
    }
    shared_labels = provider_labels["akshare"].intersection(provider_labels["yahoo"])
    if not shared_labels:
        return provider_groups

    updated: dict[str, ProviderCandidateGroup] = {}
    for source, group in provider_groups.items():
        updated_candidates: list[ProviderFieldCandidate] = []
        for candidate in group.candidates:
            if normalize_match_text(candidate.raw_field_name) not in shared_labels:
                updated_candidates.append(candidate)
                continue
            signals = tuple((*candidate.signals, "cross_provider_support"))
            score = min(candidate.score + 5, 100)
            updated_candidates.append(
                replace(
                    candidate,
                    score=score,
                    strength=_strength_for_score(score),
                    signals=signals,
                )
            )
        updated[source] = ProviderCandidateGroup(candidates=tuple(updated_candidates))
    return updated


def _field_tokens(field_id: str, taxonomy: FieldTaxonomyEntry) -> set[str]:
    values = [field_id, taxonomy.description]
    tokens: set[str] = set()
    for value in values:
        normalized = normalize_match_text(value)
        tokens.add(normalized)
        tokens.update(part for part in normalized.split() if part not in _COMMON_WORDS)
    return {token for token in tokens if token}


def _keyword_overlap(field_tokens: set[str], raw_labels: set[str]) -> int:
    raw_tokens: set[str] = set()
    for label in raw_labels:
        raw_tokens.add(label)
        raw_tokens.update(part for part in label.split() if part not in _COMMON_WORDS)
    return len(field_tokens.intersection(raw_tokens))


def _score_signals(signals: list[str]) -> int:
    score = 0
    if "existing_alias" in signals:
        score += 80
    if "exact_text" in signals:
        score += 70
    if "keyword_overlap" in signals:
        score += 40
    if "statement_match" in signals:
        score += 10
    if "period_support" in signals:
        score += 10
    if "provider_presence" in signals:
        score += 5
    return min(score, 100)


def _strength_for_score(score: int) -> CandidateStrength:
    if score >= 90:
        return "strong"
    if score >= 60:
        return "medium"
    return "weak"


@dataclass(frozen=True)
class ProviderFieldCandidateReportResult:
    json_path: Path
    markdown_path: Path
    field_count: int


def write_provider_field_candidate_report(
    *,
    taxonomy_path: Path,
    mapping_catalog_path: Path,
    inventory_path: Path,
    summary_path: Path,
    output_dir: Path,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> ProviderFieldCandidateReportResult:
    taxonomy = load_field_taxonomy(taxonomy_path)
    mapping_catalog = load_source_mapping_catalog(
        mapping_catalog_path,
        priorities=priorities,
    )
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    records = read_source_inventory(inventory_path)
    report = discover_provider_field_candidates(
        taxonomy_entries=taxonomy.fields,
        mapping_entries=mapping_catalog.entries,
        records=records,
        priorities=priorities,
        taxonomy_catalog=taxonomy.catalog_id,
        mapping_catalog=mapping_catalog.catalog_id,
    )
    report_dict = report.to_dict()
    summary_dict = dict(report.summary)
    summary_dict["inventory_record_count"] = int(summary_payload["record_count"])
    summary_dict["source_artifact_count"] = int(
        summary_payload["source_artifact_count"]
    )
    report_dict["summary"] = summary_dict

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "provider_field_candidate_report.json"
    markdown_path = output_dir / "provider_field_candidate_report.md"
    json_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _candidate_report_markdown(
            report,
            inventory_record_count=int(summary_payload["record_count"]),
            source_artifact_count=int(summary_payload["source_artifact_count"]),
        ),
        encoding="utf-8",
    )
    return ProviderFieldCandidateReportResult(
        json_path=json_path,
        markdown_path=markdown_path,
        field_count=len(report.fields),
    )


def _candidate_report_markdown(
    report: ProviderFieldCandidateReport,
    *,
    inventory_record_count: int,
    source_artifact_count: int,
) -> str:
    lines = [
        "# Provider Field Candidate Report",
        "",
        f"- Fixture: `{report.fixture}`",
        f"- Priorities: `{','.join(report.priorities)}`",
        f"- Fields: `{len(report.fields)}`",
        f"- Inventory records: `{inventory_record_count}`",
        f"- Source artifacts: `{source_artifact_count}`",
        "",
    ]
    priorities = sorted({entry.priority for entry in report.fields.values()})
    for priority in priorities:
        lines.extend([f"## {priority}", ""])
        for field_id, entry in sorted(report.fields.items()):
            if entry.priority != priority:
                continue
            lines.append(f"### `{field_id}`")
            lines.append("")
            lines.append(
                f"- Status: `{entry.status}`; statement: `{entry.statement_type}`; "
                f"mode: `{entry.source_mode}`"
            )
            if not entry.providers:
                lines.append("")
                continue
            for source, group in sorted(entry.providers.items()):
                lines.append(f"- Provider `{source}`")
                for candidate in group.candidates[:5]:
                    code = candidate.raw_field_code or ""
                    lines.append(
                        f"  - `{candidate.raw_field_name}` `{code}` "
                        f"score={candidate.score} strength=`{candidate.strength}` "
                        f"signals={','.join(candidate.signals)} "
                        f"targets={candidate.target_count} "
                        f"periods={candidate.period_count}"
                    )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
