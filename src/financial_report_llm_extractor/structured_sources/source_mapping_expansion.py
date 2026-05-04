"""Review-gated source mapping expansion from provider candidates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ExpansionAction = Literal["promote", "defer", "block"]


@dataclass(frozen=True)
class CandidateDecision:
    field_id: str
    source: str
    raw_field_name: str
    raw_field_code: str | None
    action: ExpansionAction
    reason: str
    aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMappingExpansionReviewResult:
    json_path: Path
    markdown_path: Path
    promoted_count: int
    deferred_count: int
    blocked_count: int


def decide_candidate_promotion(
    candidate: dict[str, object],
    *,
    existing_aliases_by_source: dict[str, dict[str, str]],
) -> CandidateDecision:
    field_id = str(candidate["field_id"])
    source = str(candidate["source"])
    raw_field_name = str(candidate["raw_field_name"])
    raw_field_code = candidate.get("raw_field_code")
    code = raw_field_code if isinstance(raw_field_code, str) and raw_field_code else None
    raw_signals = candidate.get("signals", ())
    signal_values = raw_signals if isinstance(raw_signals, (list, tuple)) else ()
    signals = tuple(str(signal) for signal in signal_values)
    strength = str(candidate["strength"])
    aliases = tuple(dict.fromkeys(value for value in (raw_field_name, code) if value))

    if strength != "strong":
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate is not strong",
            aliases=(),
        )
    if "statement_match" not in signals or "period_support" not in signals:
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate lacks required support signals",
            aliases=(),
        )
    if "existing_alias" not in signals and "exact_text" not in signals:
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate is not deterministic",
            aliases=(),
        )

    source_aliases = existing_aliases_by_source.get(source, {})
    for alias in aliases:
        owner = source_aliases.get(alias)
        if owner is not None and owner != field_id:
            return CandidateDecision(
                field_id=field_id,
                source=source,
                raw_field_name=raw_field_name,
                raw_field_code=code,
                action="block",
                reason=f"alias already belongs to {owner}",
                aliases=(),
            )

    new_aliases = tuple(alias for alias in aliases if source_aliases.get(alias) != field_id)
    if not new_aliases:
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate already mapped",
            aliases=(),
        )

    return CandidateDecision(
        field_id=field_id,
        source=source,
        raw_field_name=raw_field_name,
        raw_field_code=code,
        action="promote",
        reason="strong deterministic candidate",
        aliases=new_aliases,
    )


def write_source_mapping_expansion_review(
    *,
    candidate_report_path: Path,
    mapping_catalog_path: Path,
    output_dir: Path,
) -> SourceMappingExpansionReviewResult:
    candidate_report = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    mapping_catalog = json.loads(mapping_catalog_path.read_text(encoding="utf-8"))
    existing_aliases_by_source = _existing_aliases_by_source(mapping_catalog)
    decisions = _decisions_from_candidate_report(
        candidate_report,
        existing_aliases_by_source=existing_aliases_by_source,
    )
    promoted = tuple(decision for decision in decisions if decision.action == "promote")
    deferred = tuple(decision for decision in decisions if decision.action == "defer")
    blocked = tuple(decision for decision in decisions if decision.action == "block")
    no_candidates = _no_candidate_fields(candidate_report)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "source_mapping_expansion_review.json"
    markdown_path = output_dir / "source_mapping_expansion_review.md"
    payload = {
        "report_id": "source_mapping_expansion_review",
        "candidate_report": str(candidate_report_path),
        "mapping_catalog": str(mapping_catalog_path),
        "candidate_summary": candidate_report.get("summary", {}),
        "promoted": [decision.to_dict() for decision in promoted],
        "deferred": [decision.to_dict() for decision in deferred],
        "blocked": [decision.to_dict() for decision in blocked],
        "no_candidates": no_candidates,
        "summary": {
            "promoted_count": len(promoted),
            "deferred_count": len(deferred),
            "blocked_count": len(blocked),
            "no_candidate_count": len(no_candidates),
        },
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _review_markdown(
            promoted=promoted,
            deferred=deferred,
            blocked=blocked,
            no_candidates=no_candidates,
        ),
        encoding="utf-8",
    )
    return SourceMappingExpansionReviewResult(
        json_path=json_path,
        markdown_path=markdown_path,
        promoted_count=len(promoted),
        deferred_count=len(deferred),
        blocked_count=len(blocked),
    )


def _existing_aliases_by_source(
    mapping_catalog: dict[str, object],
) -> dict[str, dict[str, str]]:
    aliases_by_source: dict[str, dict[str, str]] = {}
    source_mappings = mapping_catalog.get("source_mappings", {})
    if not isinstance(source_mappings, dict):
        return aliases_by_source

    for field_id, raw_mapping in source_mappings.items():
        if not isinstance(raw_mapping, dict):
            continue
        source_aliases = raw_mapping.get("source_aliases", {})
        if not isinstance(source_aliases, dict):
            continue
        for source, raw_aliases in source_aliases.items():
            if not isinstance(raw_aliases, list):
                continue
            source_alias_map = aliases_by_source.setdefault(str(source), {})
            for alias in raw_aliases:
                source_alias_map[str(alias)] = str(field_id)
    return aliases_by_source


def _decisions_from_candidate_report(
    candidate_report: dict[str, object],
    *,
    existing_aliases_by_source: dict[str, dict[str, str]],
) -> tuple[CandidateDecision, ...]:
    decisions: list[CandidateDecision] = []
    fields = candidate_report.get("fields", {})
    if not isinstance(fields, dict):
        return ()

    for field_id, raw_field in sorted(fields.items()):
        if not isinstance(raw_field, dict):
            continue
        providers = raw_field.get("providers", {})
        if not isinstance(providers, dict):
            continue
        for source, raw_provider in sorted(providers.items()):
            if not isinstance(raw_provider, dict):
                continue
            candidates = raw_provider.get("candidates", [])
            if not isinstance(candidates, list) or not candidates:
                continue
            top_candidate = candidates[0]
            if not isinstance(top_candidate, dict):
                continue
            candidate = dict(top_candidate)
            candidate["field_id"] = str(field_id)
            candidate["source"] = str(source)
            decisions.append(
                decide_candidate_promotion(
                    candidate,
                    existing_aliases_by_source=existing_aliases_by_source,
                )
            )
    return tuple(decisions)


def _no_candidate_fields(candidate_report: dict[str, object]) -> list[dict[str, str]]:
    no_candidates: list[dict[str, str]] = []
    fields = candidate_report.get("fields", {})
    if not isinstance(fields, dict):
        return no_candidates

    for field_id, raw_field in sorted(fields.items()):
        if not isinstance(raw_field, dict):
            continue
        status = str(raw_field.get("status", ""))
        providers = raw_field.get("providers", {})
        has_providers = isinstance(providers, dict) and bool(providers)
        if has_providers or status == "not_applicable":
            continue
        no_candidates.append(
            {
                "field_id": str(field_id),
                "priority": str(raw_field.get("priority", "")),
                "status": status,
                "statement_type": str(raw_field.get("statement_type", "")),
                "source_mode": str(raw_field.get("source_mode", "")),
            }
        )
    return no_candidates


def _review_markdown(
    *,
    promoted: tuple[CandidateDecision, ...],
    deferred: tuple[CandidateDecision, ...],
    blocked: tuple[CandidateDecision, ...],
    no_candidates: list[dict[str, str]],
) -> str:
    lines = [
        "# Source Mapping Expansion Review",
        "",
        "## Promoted",
        "",
        *_decision_lines(promoted),
        "## Deferred",
        "",
        *_decision_lines(deferred),
        "## Blocked",
        "",
        *_decision_lines(blocked),
        "## No Provider Candidates",
        "",
        *_no_candidate_lines(no_candidates),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _decision_lines(decisions: tuple[CandidateDecision, ...]) -> list[str]:
    if not decisions:
        return ["_None_", ""]
    lines: list[str] = []
    for decision in decisions:
        aliases = ", ".join(f"`{alias}`" for alias in decision.aliases) or "_none_"
        lines.append(
            f"- `{decision.field_id}` `{decision.source}` "
            f"`{decision.raw_field_name}` aliases={aliases}; {decision.reason}"
        )
    lines.append("")
    return lines


def _no_candidate_lines(no_candidates: list[dict[str, str]]) -> list[str]:
    if not no_candidates:
        return ["_None_", ""]
    lines = [
        f"- `{item['field_id']}` priority=`{item['priority']}` "
        f"status=`{item['status']}` statement=`{item['statement_type']}`"
        for item in no_candidates
    ]
    lines.append("")
    return lines
