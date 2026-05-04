"""Review-gated source mapping expansion from provider candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
