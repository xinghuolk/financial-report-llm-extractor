"""Raw source artifact and source inventory persistence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from financial_report_llm_extractor.structured_sources.models import (
    SourceArtifact,
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)


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
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(_record_from_jsonable(json.loads(line)))
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


def _record_to_jsonable(record: SourceInventoryRecord) -> dict[str, Any]:
    record.validate()
    payload = asdict(record)
    if record.parsed_numeric_value is not None:
        payload["parsed_numeric_value"] = str(record.parsed_numeric_value)
    return payload


def _record_from_jsonable(payload: dict[str, Any]) -> SourceInventoryRecord:
    evidence = tuple(SourceEvidence(**item) for item in payload.pop("source_evidence", []))
    parsed_numeric_value = payload.get("parsed_numeric_value")
    if parsed_numeric_value is not None:
        payload["parsed_numeric_value"] = Decimal(str(parsed_numeric_value))
    record = SourceInventoryRecord(
        **payload,
        source_evidence=evidence,
    )
    record.validate()
    return record


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.strip().lower())
    return slug.strip("_")
