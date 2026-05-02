from pathlib import Path


def test_real_source_validation_script_forwards_sample_set() -> None:
    script = Path("scripts/run-real-source-validation.sh").read_text(encoding="utf-8")

    assert 'SAMPLE_SET="${SAMPLE_SET:-default}"' in script
    assert '--sample-set "${SAMPLE_SET}"' in script
