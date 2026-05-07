# E2E Validation Layers Design

## Goal

Add three validation layers for the current financial report extraction pipeline:

1. A default no-network pytest E2E that runs on every developer machine.
2. A local real-PDF E2E script for repository-local annual reports.
3. An opt-in real-LLM smoke script for provider configuration and artifact wiring.

## Non-Goals

- Do not make real PDFs or real LLM calls part of default pytest.
- Do not validate final financial extraction accuracy in the LLM smoke.
- Do not add provider fallback or automatic model selection.

## Layer 1: Default No-Network E2E

The pytest E2E uses a tiny synthetic PDF file plus a fake parser. It exercises the same Python pipeline functions used by the CLI:

`ingest_pdf -> build_chunk_store -> write_parser_capability_probe -> write_document_map -> write_statement_map -> write_row_inventory -> write_catalog_mapping -> write_retrieval_probe -> run_fake_extraction -> write_review_summary`

Assertions should verify that key artifacts exist, statement/row counts are non-zero, retrieval finds candidates for core fields, fake extraction writes all selected fields, and review summary includes the extraction result.

## Layer 2: Local Real-PDF E2E

Create `scripts/run-local-pdf-e2e.sh`. It defaults to:

- PDF: `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
- Report id: `00001_2025_en`
- Root: `tmp/runs/e2e_local_pdf`

It runs `quick-validate`, then runs retrieval, fake extraction, and evaluation artifacts in the generated run directory. It must fail early if the PDF is missing.

## Layer 3: Real-LLM Smoke E2E

Create `scripts/run-real-llm-smoke.sh`. It defaults to DeepSeek because that provider has already been validated, while still supporting `PROVIDER=ollama` and `PROVIDER=gemini`.

The script loads `.env` if present, creates a temporary `llm_config.json` under the run directory, runs `quick-validate`, then runs `discover-rows-llm` against the statement map. It must archive prompt payloads, raw responses, parsed responses, and `row_inventory_llm.json`.

The script should not print API key values. Ollama may omit an API key.

## Environment

`env.example` should include provider model and base URL knobs:

- `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `GEMINI_BASE_URL`, `GEMINI_MODEL`

API key variables remain optional or required according to provider behavior.
