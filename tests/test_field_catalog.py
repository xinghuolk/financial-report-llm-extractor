import json
from pathlib import Path


def test_field_catalog_has_expected_priority_layers() -> None:
    catalog_path = (
        Path(__file__).resolve().parents[1]
        / "field_catalog"
        / "turtle_v015_priority_fields.json"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    priorities = {group["priority"]: group for group in catalog["priorities"]}

    assert set(priorities) == {"P0", "P1", "P2", "P3", "P4"}
    assert "revenue" in priorities["P0"]["fields"]
    assert "total_cur_assets" in priorities["P1"]["fields"]
    assert "mda_risk_factors" in priorities["P4"]["fields"]

