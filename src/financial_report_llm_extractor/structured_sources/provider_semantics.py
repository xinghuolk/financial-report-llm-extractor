"""Provider raw field semantics catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSemanticsRule:
    provider: str
    market: str
    raw_field_name: str
    raw_field_code: str | None
    turtle_field_id: str
    semantic_claim: str
    classification: str
    trusted_currency: str | None
    trusted_unit: str | None
    trusted_unit_multiplier: int | None
    allowed_as_primary: bool
    related_only_fields: tuple[str, ...]
    negative_examples: tuple[str, ...]
    proof_origin: str
    samples: tuple[dict[str, Any], ...]
    required_proof: tuple[str, ...]
    # Phase HK-B.5 follow-up: optional per-issuer allowlist. When non-None,
    # the rule's `allowed_as_primary` promotion only applies to listed
    # issuers. Mirrors `HkYahooTrustRule.pdf_verified_company_ids` so trust
    # policy + semantics promotion stay in lockstep when one issuer has
    # adapter currency-label divergence that excludes it from clean promotion.
    pdf_verified_company_ids: tuple[str, ...] | None = None

    def applies_to_company(self, company_id: str | None) -> bool:
        if self.pdf_verified_company_ids is None:
            return True
        if company_id is None:
            return False
        return company_id in self.pdf_verified_company_ids

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int) -> ProviderSemanticsRule:
        required = (
            "provider",
            "market",
            "raw_field_name",
            "raw_field_code",
            "turtle_field_id",
            "semantic_claim",
            "classification",
            "trusted_currency",
            "trusted_unit",
            "trusted_unit_multiplier",
            "allowed_as_primary",
            "related_only_fields",
            "negative_examples",
            "proof_origin",
            "samples",
            "required_proof",
        )
        missing = [name for name in required if name not in raw]
        if missing:
            raise ValueError(f"provider semantics rule {index} missing keys: {missing}")
        rule = cls(
            provider=_required_str(raw, "provider", index),
            market=_required_str(raw, "market", index),
            raw_field_name=_required_str(raw, "raw_field_name", index),
            raw_field_code=_optional_str(raw, "raw_field_code", index),
            turtle_field_id=_required_str(raw, "turtle_field_id", index),
            semantic_claim=_required_str(raw, "semantic_claim", index),
            classification=_required_str(raw, "classification", index),
            trusted_currency=_optional_str(raw, "trusted_currency", index),
            trusted_unit=_optional_str(raw, "trusted_unit", index),
            trusted_unit_multiplier=_optional_int(
                raw,
                "trusted_unit_multiplier",
                index,
            ),
            allowed_as_primary=_required_bool(raw, "allowed_as_primary", index),
            related_only_fields=_str_tuple(raw, "related_only_fields", index),
            negative_examples=_str_tuple(raw, "negative_examples", index),
            proof_origin=_required_str(raw, "proof_origin", index),
            samples=_dict_tuple(raw, "samples", index),
            required_proof=_str_tuple(raw, "required_proof", index),
            pdf_verified_company_ids=_optional_string_tuple(
                raw, "pdf_verified_company_ids", index
            ),
        )
        rule.validate()
        return rule

    def validate(self) -> None:
        if self.raw_field_name in self.related_only_fields:
            raise ValueError("related_only_fields must not include raw_field_name")
        if self.allowed_as_primary and not self.semantic_claim:
            raise ValueError("primary provider semantics rules require semantic_claim")
        if (
            self.allowed_as_primary
            and self.classification == "provider_semantics_unverified"
        ):
            raise ValueError("unverified provider semantics rule cannot be primary")


@dataclass(frozen=True)
class ProviderSemanticsCatalog:
    rules: tuple[ProviderSemanticsRule, ...]

    def require_rule(
        self,
        *,
        provider: str,
        market: str,
        turtle_field_id: str,
        raw_field_name: str,
    ) -> ProviderSemanticsRule:
        for rule in self.rules:
            if (
                rule.provider == provider
                and rule.market == market
                and rule.turtle_field_id == turtle_field_id
                and rule.raw_field_name == raw_field_name
            ):
                return rule
        raise ValueError(
            "provider semantics rule not found: "
            f"{provider}/{market}/{turtle_field_id}/{raw_field_name}"
        )

    def rule_for(
        self,
        *,
        provider: str,
        market: str,
        turtle_field_id: str,
        raw_field_name: str | None,
    ) -> ProviderSemanticsRule | None:
        if raw_field_name is None:
            return None
        for rule in self.rules:
            if (
                rule.provider == provider
                and rule.market == market
                and rule.turtle_field_id == turtle_field_id
                and rule.raw_field_name == raw_field_name
            ):
                return rule
        return None


def load_provider_semantics_catalog(path: Path | str) -> ProviderSemanticsCatalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError("provider semantics catalog must contain a rules list")
    rules: list[ProviderSemanticsRule] = []
    for index, rule in enumerate(raw["rules"]):
        if not isinstance(rule, dict):
            raise ValueError(f"provider semantics rule {index} must be an object")
        rules.append(ProviderSemanticsRule.from_dict(rule, index))
    return ProviderSemanticsCatalog(rules=tuple(rules))


def _required_str(raw: dict[str, Any], key: str, index: int) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"provider semantics rule {index} key {key} must be a non-empty string"
        )
    return value


def _optional_str(raw: dict[str, Any], key: str, index: int) -> str | None:
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"provider semantics rule {index} key {key} "
            "must be null or a non-empty string"
        )
    return value


def _optional_int(raw: dict[str, Any], key: str, index: int) -> int | None:
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(
            f"provider semantics rule {index} key {key} must be null or an integer"
        )
    return value


def _required_bool(raw: dict[str, Any], key: str, index: int) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(
            f"provider semantics rule {index} key {key} must be a boolean"
        )
    return value


def _str_tuple(raw: dict[str, Any], key: str, index: int) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(
            f"provider semantics rule {index} key {key} must be a list of strings"
        )
    return tuple(value)


def _dict_tuple(raw: dict[str, Any], key: str, index: int) -> tuple[dict[str, Any], ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(
            f"provider semantics rule {index} key {key} must be a list of objects"
        )
    return tuple(value)


def _optional_string_tuple(
    raw: dict[str, Any], key: str, index: int
) -> tuple[str, ...] | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(
            f"provider semantics rule {index} key {key} "
            "must be null or a list of non-empty strings"
        )
    return tuple(value)
