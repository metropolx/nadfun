"""End-to-end over fixture rows: write, read back, validate, mutate, re-validate."""

import json
from pathlib import Path

import pytest
from conftest import RAW_TOKENS, export_to, make_snapshot

from nadfun_export.metadata import data_paths, datapackage, dump_json, file_info, load_manifest
from nadfun_export.tables import TOKEN_GRADUATIONS, TOKENS
from nadfun_export.validate import validate


def test_fixture_export_validates(exported: Path):
    assert validate(exported) == []


def test_json_keeps_big_numbers_as_strings(exported: Path):
    rows = json.loads((exported / data_paths(TOKENS)["json"]).read_text(encoding="utf-8"))
    assert rows[0]["target_token_amount"] == str(2**256 - 1)
    assert rows[0]["block_number"] == 101
    assert rows[0]["min_token_reserve"] is None
    assert rows[1]["name"] == "Line\nbreak\r\nand CR"
    assert rows[0]["created_at"] == "2026-01-01T00:00:01Z"


def test_json_has_one_row_per_line(exported: Path):
    lines = (exported / data_paths(TOKENS)["json"]).read_text(encoding="utf-8").split("\n")
    assert lines[0] == "[" and lines[-2] == "]" and lines[-1] == ""
    assert len(lines) == len(RAW_TOKENS) + 3


def test_csv_null_is_empty_field(exported: Path):
    lines = (exported / data_paths(TOKENS)["csv"]).read_bytes().split(b"\n")
    assert lines[1].endswith(b",,2026-01-01T00:00:01Z,101," + b"0x" + b"0" * 63 + b"1,1")


def test_export_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    export_to(a, make_snapshot())
    export_to(b, make_snapshot())
    for rel in ["manifest.json", "datapackage.json", *data_paths(TOKENS).values()]:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_empty_tables(tmp_path: Path):
    export_to(tmp_path, make_snapshot([], []))
    assert (tmp_path / data_paths(TOKENS)["json"]).read_text() == "[\n]\n"
    assert validate(tmp_path) == []


def _tamper(root: Path, rel: str, old: str, new: str) -> None:
    """Edit a data file and re-sign it in the manifest, so only the content check can catch it."""
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    manifest = load_manifest(root)
    for table in manifest["tables"].values():
        for fmt, info in table["files"].items():
            if info["path"] == rel:
                table["files"][fmt] = file_info(root, rel)
    (root / "manifest.json").write_text(dump_json(manifest), encoding="utf-8")
    (root / "datapackage.json").write_text(dump_json(datapackage(manifest)), encoding="utf-8")


@pytest.mark.parametrize(
    "rel,old,new,expected",
    [
        (data_paths(TOKENS)["json"], '"CQ"', '"CX"', "CSV and JSON differ"),
        (data_paths(TOKENS)["json"], "0x" + "0" * 36 + "03e9", "0x" + "0" * 36 + "03E9", "not a valid monad address"),
        (data_paths(TOKEN_GRADUATIONS)["json"], "0x" + "0" * 36 + "03ea", "0x" + "0" * 36 + "0bad", "not found in"),
        (data_paths(TOKENS)["json"], '"block_number":101', '"block_number":"101"', "expected non-negative int"),
    ],
    ids=["csv-json-drift", "uppercase-address", "orphan-fk", "json-int-as-string"],
)
def test_validation_catches(exported: Path, rel, old, new, expected):
    _tamper(exported, rel, old, new)
    errors = validate(exported)
    assert any(expected in e for e in errors), errors


def test_validation_catches_bad_checksum(exported: Path):
    path = exported / data_paths(TOKENS)["csv"]
    path.write_text(path.read_text(encoding="utf-8").replace("CQ", "CZ"), encoding="utf-8")
    assert any("sha256" in e for e in validate(exported))


def test_validation_catches_unsorted_rows(tmp_path: Path):
    export_to(tmp_path, make_snapshot(list(reversed(RAW_TOKENS))))
    assert any("sort key" in e for e in validate(tmp_path))


def test_validation_catches_rows_past_through_block(tmp_path: Path):
    snapshot = make_snapshot()
    snapshot.through_blocks = {"monad": 102}
    export_to(tmp_path, snapshot)
    assert any("beyond complete_through_block" in e for e in validate(tmp_path))


def test_validation_catches_stale_schema(exported: Path):
    path = exported / "data/tokens/schema.json"
    path.write_text(path.read_text(encoding="utf-8").replace("Token symbol", "Symbol"), encoding="utf-8")
    assert any("out of date" in e for e in validate(exported))
