from pathlib import Path


SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "skills"
    / "financial-report-extractor"
)


def test_skill_wrapper_has_required_frontmatter() -> None:
    skill_path = SKILL_DIR / "SKILL.md"

    text = skill_path.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "name: financial-report-extractor" in text
    assert "description:" in text
    assert "Use when" in text


def test_skill_wrapper_calls_cli_instead_of_reimplementing_logic() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "financial-report-llm-extractor ingest" in text
    assert "financial-report-llm-extractor chunk" in text
    assert "financial-report-llm-extractor retrieve" in text
    assert "financial-report-llm-extractor extract" in text
    assert "Do not parse PDFs inside the skill" in text
    assert "Do not normalize money inside the skill" in text


def test_skill_wrapper_links_review_checklist() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    checklist_path = SKILL_DIR / "references" / "review-checklist.md"
    checklist_text = checklist_path.read_text(encoding="utf-8")

    assert "references/review-checklist.md" in skill_text
    assert "present monetary items" in checklist_text
    assert "page" in checklist_text
    assert "chunk_id" in checklist_text
    assert "block_id" in checklist_text
