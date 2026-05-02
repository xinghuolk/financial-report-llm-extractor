"""Raw source artifact and source inventory persistence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from financial_report_llm_extractor.structured_sources.models import (
    SourceArtifact,
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)

_ALLOWED_SOURCE_NAMES = {"akshare", "yahoo", "fixture"}
_ALLOWED_SOURCE_VALUE_TYPES = {"money", "number", "percent", "text", "derived"}
_ALLOWED_SOURCE_STATUSES = {
    "present",
    "missing",
    "ambiguous",
    "source_error",
    "unsupported",
}
_ALLOWED_CURRENCIES = {"CNY", "HKD", "USD", "unknown", "ambiguous"}


@dataclass(frozen=True)
class SourceArtifactManifestEntry:
    source: SourceName
    artifact_id: str
    path: str
    content_type: str
    sha256: str
    market: str | None = None
    ticker: str | None = None
    statement_type: str | None = None
    function: str | None = None
    schema_version: str | None = None
    created_by: str | None = None

    def validate(self) -> None:
        _validate_required_string(self.source, "source")
        _validate_required_string(self.artifact_id, "artifact_id")
        _validate_required_string(self.path, "path")
        _validate_required_string(self.content_type, "content_type")
        _validate_required_string(self.sha256, "sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hex digest")
        artifact_path = Path(self.path)
        if artifact_path.is_absolute() or ".." in artifact_path.parts:
            raise ValueError("path must be relative and must not contain '..'")


@dataclass(frozen=True)
class SourceArtifactManifest:
    manifest_id: str
    version: str
    artifact_root: str
    artifacts: tuple[SourceArtifactManifestEntry, ...]

    def validate(self) -> None:
        _validate_required_string(self.manifest_id, "manifest_id")
        _validate_required_string(self.version, "version")
        _validate_required_string(self.artifact_root, "artifact_root")
        seen_artifact_ids: set[str] = set()
        for artifact in self.artifacts:
            artifact.validate()
            if artifact.artifact_id in seen_artifact_ids:
                raise ValueError(f"duplicate artifact_id: {artifact.artifact_id}")
            seen_artifact_ids.add(artifact.artifact_id)


def build_artifact_id(
    *,
    source: SourceName,
    market: str,
    ticker: str,
    artifact_type: str,
) -> str:
    parts = (source, market, ticker, artifact_type)
    return "_".join(_slug(part) for part in parts if part)


class SourceArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_json(
        self,
        *,
        source: SourceName,
        artifact_id: str,
        payload: Any,
    ) -> SourceArtifact:
        relative_path = Path(source) / f"{artifact_id}.json"
        full_path = self.root / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact = SourceArtifact(
            source=source,
            artifact_id=artifact_id,
            path=relative_path.as_posix(),
            content_type="application/json",
        )
        artifact.validate()
        return artifact


def write_source_artifact_manifest(
    path: Path,
    *,
    artifact_root: Path,
    artifacts: Iterable[SourceArtifact],
    manifest_id: str = "source_artifact_manifest",
    version: str = "1",
) -> SourceArtifactManifest:
    entries = tuple(
        sorted(
            (
                _manifest_entry_from_artifact(
                    artifact,
                    artifact_root=artifact_root,
                )
                for artifact in artifacts
            ),
            key=lambda entry: (entry.source, entry.artifact_id, entry.path),
        )
    )
    manifest = SourceArtifactManifest(
        manifest_id=manifest_id,
        version=version,
        artifact_root=artifact_root.as_posix(),
        artifacts=entries,
    )
    manifest.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_manifest_to_jsonable(manifest), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return manifest


def read_source_artifact_manifest(path: Path) -> SourceArtifactManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid source artifact manifest JSON: {path}") from exc
    manifest = _manifest_from_jsonable(_require_object(payload, "source artifact manifest"))
    return manifest


def validate_source_inventory_artifacts(
    manifest: SourceArtifactManifest,
    records: Iterable[SourceInventoryRecord],
    artifact_root: Path,
) -> None:
    manifest.validate()
    root_path = artifact_root.resolve()
    entries = {entry.artifact_id: entry for entry in manifest.artifacts}
    for record in records:
        record.validate()
        for evidence in record.source_evidence:
            entry = entries.get(evidence.artifact_id)
            if entry is None:
                raise ValueError(
                    f"source evidence references missing artifact_id: {evidence.artifact_id}"
                )
            full_path = (artifact_root / entry.path).resolve()
            if not full_path.is_relative_to(root_path):
                raise ValueError(
                    f"source artifact path escapes artifact root: {evidence.artifact_id}"
                )
            if not full_path.exists():
                raise ValueError(f"source artifact file is missing: {evidence.artifact_id}")
            actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
            if actual_hash != entry.sha256:
                raise ValueError(f"source artifact hash mismatch: {evidence.artifact_id}")


def write_source_inventory(
    path: Path,
    records: Iterable[SourceInventoryRecord],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(_record_to_jsonable(record), ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_source_inventory(path: Path) -> tuple[SourceInventoryRecord, ...]:
    records: list[SourceInventoryRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        label = f"source inventory line {line_number}"
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} is invalid JSON") from exc
        try:
            records.append(
                _record_from_jsonable(
                    _require_object(payload, label),
                    line_number=line_number,
                )
            )
        except (TypeError, KeyError, ValueError) as exc:
            message = str(exc)
            if message.startswith(label):
                raise
            raise ValueError(f"{label}: {message}") from exc
    return tuple(records)


def _manifest_entry_from_artifact(
    artifact: SourceArtifact,
    *,
    artifact_root: Path,
) -> SourceArtifactManifestEntry:
    artifact.validate()
    artifact_path = artifact_root / artifact.path
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    entry = SourceArtifactManifestEntry(
        source=artifact.source,
        artifact_id=artifact.artifact_id,
        path=artifact.path,
        content_type=artifact.content_type,
        sha256=digest,
        market=getattr(artifact, "market", None),
        ticker=getattr(artifact, "ticker", None),
        statement_type=getattr(artifact, "statement_type", None),
        function=getattr(artifact, "function", None),
        schema_version=getattr(artifact, "schema_version", None),
        created_by=getattr(artifact, "created_by", None),
    )
    entry.validate()
    return entry


def _manifest_to_jsonable(manifest: SourceArtifactManifest) -> dict[str, Any]:
    manifest.validate()
    return asdict(manifest)


def _manifest_from_jsonable(payload: dict[str, Any]) -> SourceArtifactManifest:
    raw_artifacts = _require_list(
        _require_key(payload, "artifacts", "source artifact manifest"),
        "source artifact manifest artifacts",
    )
    entries = tuple(
        _manifest_entry_from_jsonable(
            item,
            f"source artifact manifest artifacts[{index}]",
        )
        for index, item in enumerate(raw_artifacts)
    )
    manifest = SourceArtifactManifest(
        manifest_id=_require_key(payload, "manifest_id", "source artifact manifest"),
        version=_require_key(payload, "version", "source artifact manifest"),
        artifact_root=_require_key(payload, "artifact_root", "source artifact manifest"),
        artifacts=entries,
    )
    manifest.validate()
    return manifest


def _manifest_entry_from_jsonable(value: Any, label: str) -> SourceArtifactManifestEntry:
    payload = _require_object(value, label)
    required_keys = ("source", "artifact_id", "path", "content_type", "sha256")
    optional_keys = (
        "market",
        "ticker",
        "statement_type",
        "function",
        "schema_version",
        "created_by",
    )
    allowed_keys = set(required_keys + optional_keys)
    unexpected_keys = sorted(set(payload) - allowed_keys)
    if unexpected_keys:
        raise ValueError(
            f"{label} has unsupported keys: {', '.join(unexpected_keys)}"
        )
    for key in required_keys:
        _require_key(payload, key, label)

    entry = SourceArtifactManifestEntry(**payload)
    entry.validate()
    return entry


def _source_evidence_from_jsonable(value: Any, label: str) -> SourceEvidence:
    payload = _require_object(value, label)
    required_keys = (
        "source",
        "adapter",
        "function",
        "artifact_id",
        "raw_record_id",
        "raw_field_name",
    )
    optional_keys = ("raw_field_code", "retrieved_at", "provider_version")
    allowed_keys = set(required_keys + optional_keys)
    unexpected_keys = sorted(set(payload) - allowed_keys)
    if unexpected_keys:
        raise ValueError(
            f"{label} has unsupported keys: {', '.join(unexpected_keys)}"
        )
    for key in required_keys:
        _require_key(payload, key, label)
        _validate_required_string(payload[key], f"{label} {key}")
    for key in optional_keys:
        if key in payload and payload[key] is not None:
            _validate_optional_string(payload[key], f"{label} {key}")
    _validate_allowed_value(payload["source"], f"{label} source", _ALLOWED_SOURCE_NAMES)

    evidence = SourceEvidence(**payload)
    evidence.validate()
    return evidence


def _validate_source_inventory_payload(payload: dict[str, Any], label: str) -> None:
    required_keys = (
        "source",
        "market",
        "ticker",
        "statement_type",
        "period",
        "raw_field_name",
        "raw_value",
    )
    allowed_keys = {
        "source",
        "market",
        "ticker",
        "statement_type",
        "period",
        "raw_field_name",
        "raw_value",
        "parsed_numeric_value",
        "value_type",
        "source_status",
        "report_type",
        "fiscal_year",
        "scope",
        "account_standard",
        "currency",
        "unit",
        "raw_field_code",
        "source_evidence",
    }
    unexpected_keys = sorted(set(payload) - allowed_keys)
    if unexpected_keys:
        raise ValueError(
            f"{label} has unsupported keys: {', '.join(unexpected_keys)}"
        )
    for key in required_keys:
        _require_key(payload, key, label)

    for key in ("source", "market", "ticker", "statement_type"):
        _validate_required_string(payload[key], f"{label} {key}")
    _validate_optional_string(payload["raw_field_name"], f"{label} raw_field_name")
    if payload["period"] is not None:
        _validate_optional_string(payload["period"], f"{label} period")
    _validate_raw_value(payload["raw_value"], f"{label} raw_value")
    for key in (
        "value_type",
        "source_status",
        "report_type",
        "fiscal_year",
        "scope",
        "account_standard",
        "currency",
        "unit",
        "raw_field_code",
    ):
        if key in payload and payload[key] is not None:
            _validate_optional_string(payload[key], f"{label} {key}")
    _validate_allowed_value(payload["source"], f"{label} source", _ALLOWED_SOURCE_NAMES)
    if "value_type" in payload:
        _validate_allowed_value(
            payload["value_type"],
            f"{label} value_type",
            _ALLOWED_SOURCE_VALUE_TYPES,
        )
    if "source_status" in payload:
        _validate_allowed_value(
            payload["source_status"],
            f"{label} source_status",
            _ALLOWED_SOURCE_STATUSES,
        )
    if "currency" in payload:
        _validate_allowed_value(payload["currency"], f"{label} currency", _ALLOWED_CURRENCIES)


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _require_key(payload: dict[str, Any], key: str, label: str) -> Any:
    if key not in payload:
        raise ValueError(f"{label} {key} is required")
    return payload[key]


def _validate_required_string(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if not value:
        raise ValueError(f"{label} is required")


def _validate_optional_string(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")


def _validate_allowed_value(value: str, label: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{label} has unsupported value: {value}")


def _validate_raw_value(value: Any, label: str) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int, float))
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        raise ValueError(f"{label} must be a finite string, number, or null")


def _record_to_jsonable(record: SourceInventoryRecord) -> dict[str, Any]:
    record.validate()
    payload = asdict(record)
    if record.parsed_numeric_value is not None:
        payload["parsed_numeric_value"] = str(record.parsed_numeric_value)
    return payload


def _record_from_jsonable(
    payload: dict[str, Any],
    *,
    line_number: int | None = None,
) -> SourceInventoryRecord:
    label = "source inventory"
    if line_number is not None:
        label = f"{label} line {line_number}"

    record_payload = dict(payload)
    _validate_source_inventory_payload(record_payload, label)
    if "source_evidence" in record_payload:
        raw_evidence = record_payload.pop("source_evidence")
        evidence_items: tuple[Any, ...] | list[Any] = _require_list(
            raw_evidence,
            f"{label} source_evidence",
        )
    else:
        evidence_items = ()
    evidence = tuple(
        _source_evidence_from_jsonable(item, f"{label} source_evidence[{index}]")
        for index, item in enumerate(evidence_items)
    )
    parsed_numeric_value = payload.get("parsed_numeric_value")
    if parsed_numeric_value is not None:
        try:
            parsed_value = Decimal(str(parsed_numeric_value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{label} parsed_numeric_value is invalid") from exc
        if not parsed_value.is_finite():
            raise ValueError(f"{label} parsed_numeric_value is invalid")
        record_payload["parsed_numeric_value"] = parsed_value
    record = SourceInventoryRecord(
        **record_payload,
        source_evidence=evidence,
    )
    record.validate()
    return record


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.strip().lower())
    return slug.strip("_")
