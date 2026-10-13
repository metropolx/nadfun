"""Checks over the committed dataset (and over a fixture export when none is committed)."""

import json
from pathlib import Path

import jsonschema
import pytest
from frictionless import Package

from nadfun_export.metadata import data_paths, json_schema
from nadfun_export.tables import TABLES
from nadfun_export.validate import validate

REPO = Path(__file__).resolve().parent.parent
COMMITTED = (REPO / "manifest.json").exists()


@pytest.fixture(params=["fixture", "committed"])
def root(request, exported: Path) -> Path:
    if request.param == "fixture":
        return exported
    if not COMMITTED:
        pytest.skip("no committed dataset")
    return REPO


def test_validate(root: Path):
    assert validate(root) == []


def test_json_files_match_json_schema(root: Path):
    for table in TABLES:
        data = json.loads((root / data_paths(table)["json"]).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(json_schema(table)).validate(data)


def test_frictionless_validates_datapackage(root: Path):
    report = Package(str(root / "datapackage.json")).validate()
    # frictionless does not compute byte/hash stats for JSON sources (reports "None");
    # validate() checks bytes and sha256 of every file against the manifest instead.
    errors = [
        f"{task.name}: {e.message}"
        for task in report.tasks
        for e in task.errors
        if not (task.name.endswith("-json") and e.type in ("byte-count", "hash-count"))
    ] + [e.message for e in report.errors]
    assert errors == []
