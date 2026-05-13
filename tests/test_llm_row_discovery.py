import json
from pathlib import Path
from typing import cast

import pytest

from financial_report_llm_extractor.llm_row_discovery import (
    build_row_discovery_prompt_payload,
    write_llm_row_inventory,
)


def test_build_row_discovery_prompt_payload_is_statement_scoped() -> None:
    statement = {
        "statement_id": "stmt_0001_income_statement",
        "statement_kind": "income_statement",
        "title": "CONSOLIDATED INCOME STATEMENT",
        "scope": "consolidated",
        "period_columns": ["2025", "2024"],
        "unit_context": "$ Million",
        "chunk_id": "stmt_income_p0134_p0134",
        "evidence_blocks": ["p0134_b0002"],
    }
    chunk = {
        "chunk_id": "stmt_income_p0134_p0134",
        "page_start": 134,
        "page_end": 134,
        "block_ids": ["p0134_b0001", "p0134_b0002", "p0134_b9999"],
        "block_texts": {
            "p0134_b0001": "CONSOLIDATED INCOME STATEMENT\n2025 2024",
            "p0134_b0002": "Revenue 100 90\nProfit attributable 20 18",
            "p0134_b9999": "Unrelated page text must not leak",
        },
        "text": "full chunk text should not be copied wholesale",
    }

    payload = build_row_discovery_prompt_payload(statement, chunk)

    assert payload["prompt_version"] == "row-discovery-v1"
    assert payload["schema_version"] == "row-inventory-v1"
    assert payload["statement"]["statement_id"] == "stmt_0001_income_statement"
    assert payload["statement"]["evidence_blocks"] == [
        {
            "block_id": "p0134_b0002",
            "page": 134,
            "text": "Revenue 100 90\nProfit attributable 20 18",
        }
    ]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Unrelated page text must not leak" not in serialized
    assert "full chunk text should not be copied wholesale" not in serialized


def test_row_response_parser_reads_codex_responses_shape() -> None:
    from financial_report_llm_extractor.llm_row_discovery import _parse_row_response

    raw = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"rows": []})}
                ],
            }
        ]
    }

    assert _parse_row_response(raw) == {"rows": []}


def test_row_response_parser_reads_anthropic_messages_shape() -> None:
    from financial_report_llm_extractor.llm_row_discovery import _parse_row_response

    raw = {"content": [{"type": "text", "text": json.dumps({"rows": []})}]}

    assert _parse_row_response(raw) == {"rows": []}


class FakeHttpTransport:
    def __init__(self, content: str, *, response_kind: str = "openai") -> None:
        self.content = content
        self.response_kind = response_kind
        self.requests: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.response_kind == "gemini":
            return {"candidates": [{"content": {"parts": [{"text": self.content}]}}]}
        return {"choices": [{"message": {"content": self.content}}]}


def test_write_llm_row_inventory_archives_prompt_raw_and_parsed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path, statement_map_path = _write_statement_inputs(tmp_path)
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    transport = FakeHttpTransport(
        json.dumps(
            {
                "rows": [
                    {
                        "row_label": "Revenue",
                        "values": [{"period": "2025", "value_raw": "100"}],
                        "evidence": [{"block_id": "p0134_b0002", "snippet": "Revenue 100"}],
                    }
                ]
            }
        )
    )

    result = write_llm_row_inventory(
        chunks_path,
        statement_map_path,
        config_path=config_path,
        output_path=tmp_path / "row_inventory_llm.json",
        prompt_dir=tmp_path / "prompt_payloads",
        raw_response_dir=tmp_path / "raw_llm_responses",
        parsed_response_dir=tmp_path / "parsed_llm_responses",
        transport=transport,
    )

    assert result.row_count == 1
    assert result.prompt_count == 1
    assert result.raw_response_count == 1
    assert (tmp_path / "prompt_payloads" / "prompt_0001.json").exists()
    assert (tmp_path / "raw_llm_responses" / "raw_response_0001.json").exists()
    assert (tmp_path / "parsed_llm_responses" / "parsed_response_0001.json").exists()
    payload = json.loads((tmp_path / "row_inventory_llm.json").read_text("utf-8"))
    assert payload["rows"][0]["statement_id"] == "stmt_0001_income_statement"
    assert payload["rows"][0]["row_label"] == "Revenue"
    headers = cast(dict[str, str], transport.requests[0]["headers"])
    assert headers["Authorization"] == "Bearer secret-key"


def test_write_llm_row_inventory_archives_error_for_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path, statement_map_path = _write_statement_inputs(tmp_path)
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")

    with pytest.raises(ValueError, match="malformed LLM row discovery JSON"):
        write_llm_row_inventory(
            chunks_path,
            statement_map_path,
            config_path=config_path,
            output_path=tmp_path / "row_inventory_llm.json",
            prompt_dir=tmp_path / "prompt_payloads",
            raw_response_dir=tmp_path / "raw_llm_responses",
            parsed_response_dir=tmp_path / "parsed_llm_responses",
            transport=FakeHttpTransport("{not-json"),
        )

    assert (tmp_path / "prompt_payloads" / "prompt_0001.json").exists()
    assert (tmp_path / "raw_llm_responses" / "raw_response_0001.json").exists()
    error_payload = json.loads(
        (tmp_path / "parsed_llm_responses" / "error_0001.json").read_text("utf-8")
    )
    assert error_payload["status"] == "error"
    assert not (tmp_path / "row_inventory_llm.json").exists()


def test_write_llm_row_inventory_supports_gemini_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path, statement_map_path = _write_statement_inputs(tmp_path)
    config_path = _write_config(
        tmp_path,
        {
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "api_key_env": "GEMINI_API_KEY",
        },
    )
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    transport = FakeHttpTransport(
        json.dumps(
            {
                "rows": [
                    {
                        "row_label": "Revenue",
                        "values": [{"period": "2025", "value_raw": "100"}],
                        "evidence": [{"block_id": "p0134_b0002", "snippet": "Revenue 100"}],
                    }
                ]
            }
        ),
        response_kind="gemini",
    )

    result = write_llm_row_inventory(
        chunks_path,
        statement_map_path,
        config_path=config_path,
        output_path=tmp_path / "row_inventory_llm.json",
        prompt_dir=tmp_path / "prompt_payloads",
        raw_response_dir=tmp_path / "raw_llm_responses",
        parsed_response_dir=tmp_path / "parsed_llm_responses",
        transport=transport,
    )

    assert result.row_count == 1
    assert str(transport.requests[0]["url"]).endswith(
        "/models/gemini-1.5-flash:generateContent"
    )
    headers = cast(dict[str, str], transport.requests[0]["headers"])
    assert headers["x-goog-api-key"] == "gemini-key"


def _write_statement_inputs(tmp_path: Path) -> tuple[Path, Path]:
    chunks_path = tmp_path / "chunks.jsonl"
    statement_map_path = tmp_path / "statement_map.json"
    chunks_path.write_text(
        json.dumps(
            {
                "record_type": "chunk",
                "chunk_id": "stmt_income_p0134_p0134",
                "kind": "statement_table",
                "statement_kind": "income_statement",
                "page_start": 134,
                "page_end": 134,
                "block_ids": ["p0134_b0002"],
                "block_texts": {"p0134_b0002": "Revenue 100 90"},
                "text": "Revenue 100 90",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    statement_map_path.write_text(
        json.dumps(
            {
                "statements": [
                    {
                        "statement_id": "stmt_0001_income_statement",
                        "statement_kind": "income_statement",
                        "title": "CONSOLIDATED INCOME STATEMENT",
                        "scope": "consolidated",
                        "period_columns": ["2025", "2024"],
                        "unit_context": "$ Million",
                        "chunk_id": "stmt_income_p0134_p0134",
                        "evidence_blocks": ["p0134_b0002"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return chunks_path, statement_map_path


def _write_config(
    tmp_path: Path,
    payload: dict[str, object] | None = None,
) -> Path:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps(
            payload
            or {
                "provider": "openai-compatible",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "timeout_seconds": 60,
                "max_retries": 1,
            }
        ),
        encoding="utf-8",
    )
    return config_path
