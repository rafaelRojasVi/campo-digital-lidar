from __future__ import annotations

from pathlib import Path

import pytest

from lidar_io.pdal_wrapper import pdal_available, validate_pipeline

PIPELINE_DIR = Path(__file__).resolve().parents[1] / "pipelines" / "pdal"

_STRUCTURAL_ONLY = {"reproject.json"}  # contains placeholder tokens, not literal filenames


@pytest.mark.skipif(not pdal_available(), reason="pdal CLI not installed on this host")
@pytest.mark.parametrize("pipeline_file", sorted(p.name for p in PIPELINE_DIR.glob("*.json")))
def test_pipeline_json_is_valid(pipeline_file: str) -> None:
    ok, message = validate_pipeline(PIPELINE_DIR / pipeline_file)
    assert ok, message


def test_pipeline_files_exist_and_are_json():
    import json

    files = list(PIPELINE_DIR.glob("*.json"))
    assert len(files) >= 6
    for f in files:
        json.loads(f.read_text())
