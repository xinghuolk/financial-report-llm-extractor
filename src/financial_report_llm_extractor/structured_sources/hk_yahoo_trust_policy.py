"""HK Yahoo trust policy fixture loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, cast


HkYahooRuleClassification = Literal[
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "yahoo_standardized_accepted",
    "pdf_required",
]


@dataclass(frozen=True)
class HkYahooTrustSample:
    company_id: str
    provider_ticker: str
    report_ref: str
    pdf_page: int
    statement_name: str
    statement_line: str
    reported_currency: str
    reported_unit: str
    pdf_value: str
    pdf_unit_multiplier: Decimal
    expected_yahoo_raw_value: str
    yahoo_raw_field: str
    match_basis: str

    def validate(
        self,
        *,
        allowed_yahoo_raw_fields: tuple[str, ...],
        verify_arithmetic: bool,
        page_text_resolver: Callable[["HkYahooTrustSample"], str | None] | None = None,
    ) -> None:
        if not self.company_id:
            raise ValueError("sample company_id is required")
        if not self.provider_ticker:
            raise ValueError("sample provider_ticker is required")
        if not self.report_ref:
            raise ValueError("sample report_ref is required")
        if not isinstance(self.pdf_page, int) or self.pdf_page <= 0:
            raise ValueError("sample pdf_page must be a positive integer")
        if not self.statement_name:
            raise ValueError("sample statement_name is required")
        if not self.statement_line:
            raise ValueError("sample statement_line is required")
        if self.yahoo_raw_field not in allowed_yahoo_raw_fields:
            raise ValueError("sample yahoo_raw_field is not allowed by rule")
        if self.pdf_unit_multiplier <= 0:
            raise ValueError("sample pdf_unit_multiplier must be positive")
        if verify_arithmetic:
            expected = Decimal(self.pdf_value) * self.pdf_unit_multiplier
            if expected != Decimal(self.expected_yahoo_raw_value):
                raise ValueError(
                    "sample arithmetic mismatch: pdf_value * "
                    "pdf_unit_multiplier must equal expected_yahoo_raw_value"
                )
        if page_text_resolver is not None:
            page_text = page_text_resolver(self)
            if page_text is None or self.statement_line not in page_text:
                raise ValueError("sample statement_line not found on pdf_page")
            if self.reported_unit not in page_text:
                raise ValueError("sample reported_unit not found on pdf_page")
            if self.pdf_value not in page_text:
                raise ValueError("sample pdf_value not found on pdf_page")

    def to_policy_evidence(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "provider_ticker": self.provider_ticker,
            "report_ref": self.report_ref,
            "pdf_page": self.pdf_page,
            "statement_name": self.statement_name,
            "statement_line": self.statement_line,
            "reported_currency": self.reported_currency,
            "reported_unit": self.reported_unit,
            "pdf_value": self.pdf_value,
            "pdf_unit_multiplier": str(self.pdf_unit_multiplier),
            "expected_yahoo_raw_value": self.expected_yahoo_raw_value,
            "yahoo_raw_field": self.yahoo_raw_field,
            "match_basis": self.match_basis,
        }


@dataclass(frozen=True)
class HkYahooTrustRule:
    policy_id: str
    field_id: str
    classification: HkYahooRuleClassification
    trusted_currency: str
    trusted_unit: str
    trusted_unit_multiplier: Decimal
    allowed_yahoo_raw_fields: tuple[str, ...]
    definition_status_reason: str | None = None
    required_proof: str | None = None
    samples: tuple[HkYahooTrustSample, ...] = field(default_factory=tuple)
    # Phase HK-B.5 follow-up: when non-None, the trust rule only applies to
    # the listed issuers. Used when adapter-stamped currency (HKD) does not
    # match the issuer's actual reporting currency for some HK issuers but
    # not others, so broad promotion would expose wrong-currency claims for
    # the affected subset. Unlisted HK issuers fall back to unresolved_conflict
    # rather than getting silently promoted.
    pdf_verified_company_ids: tuple[str, ...] | None = None
    # Phase HK-B.5.2: when set, the trust rule also accepts candidates whose
    # `currency` matches any of these in addition to `trusted_currency`. Used
    # when the field is verified to mean the same semantic concept across
    # issuers reporting in different currencies (e.g. `acct_payable` covers
    # Trade payables in HKD/CNY/USD reporters per PDF spot-check).
    additional_trusted_currencies: tuple[str, ...] | None = None
    # 2026-06-12 CN extension: markets this rule applies to. Defaults to
    # HK-only (the policy file's home market). yahoo_standardized_accepted
    # rules may extend to CN when the operator adjudicates the same
    # standardized derivation there (gross_profit: CN GAAP income
    # statements disclose no gross-profit line either).
    applies_to_markets: tuple[str, ...] = ("HK",)

    def validate(
        self,
        *,
        page_text_resolver: Callable[[HkYahooTrustSample], str | None] | None = None,
    ) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required")
        if not self.field_id:
            raise ValueError("field_id is required")
        if self.classification not in {
            "yahoo_pdf_verified",
            "yahoo_definition_unverified",
            "yahoo_standardized_accepted",
            "pdf_required",
        }:
            raise ValueError("unsupported trust policy classification")
        if self.trusted_currency != "HKD":
            raise ValueError("trusted_currency must be HKD")
        if self.trusted_unit != "raw":
            raise ValueError("trusted_unit must be raw")
        if self.trusted_unit_multiplier != Decimal("1"):
            raise ValueError("trusted_unit_multiplier must equal 1")
        if not self.allowed_yahoo_raw_fields:
            raise ValueError("allowed_yahoo_raw_fields is required")
        if self.classification == "yahoo_pdf_verified" and not self.samples:
            raise ValueError("verified rules must include at least one sample")
        if self.classification == "yahoo_definition_unverified":
            if not self.definition_status_reason:
                raise ValueError("definition_status_reason is required")
            if not self.required_proof:
                raise ValueError("required_proof is required")
        if self.classification == "yahoo_standardized_accepted":
            # Acceptance of a provider-standardized derivation is a
            # deliberate judgment: the rationale must be recorded.
            if not self.definition_status_reason:
                raise ValueError("definition_status_reason is required")
        if not self.applies_to_markets:
            raise ValueError("applies_to_markets must not be empty")
        for market in self.applies_to_markets:
            if market not in {"HK", "CN"}:
                raise ValueError("unsupported market in applies_to_markets")
        if self.applies_to_markets != ("HK",) and (
            self.classification != "yahoo_standardized_accepted"
        ):
            # Verified/unverified classifications are proven against HK
            # Yahoo adapter labels specifically — only the operator-
            # adjudicated standardized acceptance may extend markets.
            raise ValueError(
                "applies_to_markets extension requires "
                "yahoo_standardized_accepted classification"
            )
        for sample in self.samples:
            sample.validate(
                allowed_yahoo_raw_fields=self.allowed_yahoo_raw_fields,
                verify_arithmetic=self.classification == "yahoo_pdf_verified",
                page_text_resolver=page_text_resolver,
            )

    def is_pdf_verified(self) -> bool:
        return self.classification == "yahoo_pdf_verified"

    def applies_to_company(self, company_id: str | None) -> bool:
        """Phase HK-B.5 follow-up: gate field-level rules by per-issuer allowlist.

        When ``pdf_verified_company_ids`` is None the rule applies to every HK
        issuer (legacy broad behavior). When set, the rule applies only to
        listed issuers — unlisted issuers fall through to the field's normal
        conflict path. ``company_id=None`` is treated as not in any allowlist.
        """
        if self.pdf_verified_company_ids is None:
            return True
        if company_id is None:
            return False
        return company_id in self.pdf_verified_company_ids

    def applies_to_market(self, market: str | None) -> bool:
        """2026-06-12 CN extension: True when the rule covers `market`."""
        return market is not None and market.upper() in self.applies_to_markets

    def accepted_currencies(self) -> tuple[str, ...]:
        """Phase HK-B.5.2: tuple of all currencies this rule accepts.

        Always includes `trusted_currency`; extends with
        `additional_trusted_currencies` when the rule semantics are
        currency-agnostic across multiple issuer reporting currencies (e.g.
        acct_payable verified across HKD/CNY/USD issuers).
        """
        if self.additional_trusted_currencies is None:
            return (self.trusted_currency,)
        return (self.trusted_currency, *self.additional_trusted_currencies)

    def build_policy_evidence(self) -> dict[str, object]:
        self.validate()
        return {
            "policy_id": self.policy_id,
            "field_id": self.field_id,
            "classification": self.classification,
            "trusted_currency": self.trusted_currency,
            "trusted_unit": self.trusted_unit,
            "trusted_unit_multiplier": str(self.trusted_unit_multiplier),
            "allowed_yahoo_raw_fields": list(self.allowed_yahoo_raw_fields),
            "definition_status_reason": self.definition_status_reason,
            "required_proof": self.required_proof,
            "sample_count": len(self.samples),
            "sample_companies": sorted({sample.company_id for sample in self.samples}),
            "samples": [sample.to_policy_evidence() for sample in self.samples],
        }


@dataclass(frozen=True)
class HkYahooTrustPolicy:
    version: int
    market: str
    provider: str
    rules: tuple[HkYahooTrustRule, ...]

    def validate(
        self,
        *,
        page_text_resolver: Callable[[HkYahooTrustSample], str | None] | None = None,
    ) -> None:
        if self.version <= 0:
            raise ValueError("version must be positive")
        if self.market != "HK":
            raise ValueError("market must be HK")
        if self.provider != "yahoo":
            raise ValueError("provider must be yahoo")
        if not self.rules:
            raise ValueError("rules are required")
        seen_field_ids: set[str] = set()
        for rule in self.rules:
            if rule.field_id in seen_field_ids:
                raise ValueError(f"duplicate rule field_id: {rule.field_id}")
            seen_field_ids.add(rule.field_id)
            rule.validate(page_text_resolver=page_text_resolver)

    def rule_for_field(self, field_id: str) -> HkYahooTrustRule | None:
        for rule in self.rules:
            if rule.field_id == field_id:
                return rule
        return None

    def is_pdf_verified(self, field_id: str) -> bool:
        rule = self.rule_for_field(field_id)
        return rule is not None and rule.is_pdf_verified()

    def build_policy_evidence(self, field_id: str) -> dict[str, object]:
        rule = self.rule_for_field(field_id)
        if rule is None:
            raise KeyError(f"no HK Yahoo trust policy rule for field: {field_id}")
        return rule.build_policy_evidence()


def load_hk_yahoo_trust_policy(path: Path) -> HkYahooTrustPolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trust policy must be a JSON object")
    policy = HkYahooTrustPolicy(
        version=int(payload["version"]),
        market=str(payload["market"]),
        provider=str(payload["provider"]),
        rules=tuple(_parse_rule(rule) for rule in _required_list(payload, "rules")),
    )
    policy.validate()
    return policy


def validate_hk_yahoo_trust_policy_samples(
    policy: HkYahooTrustPolicy,
    page_text_resolver: Callable[[HkYahooTrustSample], str | None],
) -> None:
    policy.validate(page_text_resolver=page_text_resolver)


def _parse_rule(payload: object) -> HkYahooTrustRule:
    if not isinstance(payload, dict):
        raise ValueError("rule must be an object")
    rule = cast(dict[str, object], payload)
    return HkYahooTrustRule(
        policy_id=str(rule["policy_id"]),
        field_id=str(rule["field_id"]),
        classification=_parse_classification(rule["classification"]),
        trusted_currency=str(rule["trusted_currency"]),
        trusted_unit=str(rule["trusted_unit"]),
        trusted_unit_multiplier=Decimal(str(rule["trusted_unit_multiplier"])),
        allowed_yahoo_raw_fields=tuple(
            str(field) for field in _required_list(rule, "allowed_yahoo_raw_fields")
        ),
        definition_status_reason=_optional_str(rule, "definition_status_reason"),
        required_proof=_optional_str(rule, "required_proof"),
        samples=tuple(
            _parse_sample(sample) for sample in _optional_list(rule, "samples")
        ),
        pdf_verified_company_ids=_optional_string_tuple(
            rule, "pdf_verified_company_ids"
        ),
        additional_trusted_currencies=_optional_string_tuple(
            rule, "additional_trusted_currencies"
        ),
        applies_to_markets=(
            _optional_string_tuple(rule, "applies_to_markets") or ("HK",)
        ),
    )


def _parse_sample(payload: object) -> HkYahooTrustSample:
    sample = payload
    if not isinstance(sample, dict):
        raise ValueError("sample must be an object")
    return HkYahooTrustSample(
        company_id=str(sample["company_id"]),
        provider_ticker=str(sample["provider_ticker"]),
        report_ref=str(sample["report_ref"]),
        pdf_page=int(sample["pdf_page"]),
        statement_name=str(sample["statement_name"]),
        statement_line=str(sample["statement_line"]),
        reported_currency=str(sample["reported_currency"]),
        reported_unit=str(sample["reported_unit"]),
        pdf_value=str(sample["pdf_value"]),
        pdf_unit_multiplier=Decimal(str(sample["pdf_unit_multiplier"])),
        expected_yahoo_raw_value=str(sample["expected_yahoo_raw_value"]),
        yahoo_raw_field=str(sample["yahoo_raw_field"]),
        match_basis=str(sample["match_basis"]),
    )


def _parse_classification(payload: object) -> HkYahooRuleClassification:
    classification = str(payload)
    if classification not in {
        "yahoo_pdf_verified",
        "yahoo_definition_unverified",
        "yahoo_standardized_accepted",
        "pdf_required",
    }:
        raise ValueError("unsupported trust policy classification")
    return classification  # type: ignore[return-value]


def _required_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _optional_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_string_tuple(
    payload: dict[str, object], key: str
) -> tuple[str, ...] | None:
    if key not in payload or payload[key] is None:
        return None
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list or null")
    return tuple(str(item) for item in value)
