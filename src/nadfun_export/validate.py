"""Offline validation of an exported dataset directory. No database needed."""

import csv
import json
from pathlib import Path

from .cells import Cell, CellError, check_row, from_csv
from .metadata import (
    data_paths,
    datapackage,
    file_info,
    json_schema,
    load_manifest,
    table_dir,
    table_readme,
    table_schema,
)
from .tables import TABLES, Table


def _read_csv(table: Table, path: Path) -> list[tuple[Cell, ...]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, strict=True)
        header = next(reader)
        if header != table.column_names:
            raise CellError(f"{path.name}: header {header} != {table.column_names}")
        rows = []
        for line, record in enumerate(reader, start=2):
            if len(record) != len(table.columns):
                raise CellError(f"{path.name} record {line}: {len(record)} fields")
            rows.append(tuple(from_csv(col, text) for col, text in zip(table.columns, record, strict=True)))
        return rows


def _read_json(table: Table, path: Path) -> list[tuple[Cell, ...]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise CellError(f"{path.name}: top level is not an array")
    rows = []
    for i, obj in enumerate(data):
        if not isinstance(obj, dict) or list(obj) != table.column_names:
            raise CellError(f"{path.name} item {i}: keys differ from {table.column_names}")
        rows.append(tuple(obj.values()))
    return rows


def _check_table(table: Table, root: Path, manifest: dict, errors: list[str]) -> list[tuple[Cell, ...]]:
    paths = data_paths(table)
    entry = manifest["tables"].get(table.name)
    if entry is None:
        errors.append(f"{table.name}: missing from manifest")
        return []
    for fmt, path in paths.items():
        if not (root / path).exists():
            errors.append(f"{path}: missing")
            return []
        if file_info(root, path) != entry["files"][fmt]:
            errors.append(f"{path}: bytes/sha256 differ from manifest")
    try:
        csv_rows = _read_csv(table, root / paths["csv"])
        json_rows = _read_json(table, root / paths["json"])
    except (CellError, csv.Error, json.JSONDecodeError) as e:
        errors.append(f"{table.name}: {e}")
        return []

    if csv_rows != json_rows:
        diff = next(
            (i for i, (a, b) in enumerate(zip(csv_rows, json_rows, strict=True)) if a != b),
            min(len(csv_rows), len(json_rows)),
        )
        errors.append(f"{table.name}: CSV and JSON differ (first at data row {diff})")
    if len(csv_rows) != entry["rows"]:
        errors.append(f"{table.name}: {len(csv_rows)} rows, manifest says {entry['rows']}")

    names = table.column_names
    sort_idx = [names.index(k) for k in table.sort_key]
    pk_idx = [names.index(k) for k in table.primary_key]
    chain_idx, block_idx = names.index("chain"), names.index("block_number")
    pks, previous = set(), None
    for n, row in enumerate(json_rows):
        try:
            check_row(table, row)
        except CellError as e:
            errors.append(f"{table.name} row {n}: {e}")
            continue
        key = tuple(row[i] for i in sort_idx)
        if previous is not None and not key > previous:
            errors.append(f"{table.name} row {n}: sort key {key} not after {previous}")
        previous = key
        pk = tuple(row[i] for i in pk_idx)
        if pk in pks:
            errors.append(f"{table.name} row {n}: duplicate primary key {pk}")
        pks.add(pk)
        through = manifest["chains"].get(row[chain_idx], {}).get("complete_through_block")
        if through is None or row[block_idx] > through:
            errors.append(f"{table.name} row {n}: block {row[block_idx]} beyond complete_through_block {through}")
    return json_rows


def _check_metadata(root: Path, manifest: dict, errors: list[str]) -> None:
    expected: dict[str, object] = {"datapackage.json": datapackage(manifest)}
    for table in TABLES:
        expected[f"{table_dir(table)}/schema.json"] = table_schema(table)
        expected[f"{table_dir(table)}/json-schema.json"] = json_schema(table)
    for path, obj in expected.items():
        if not (root / path).exists() or json.loads((root / path).read_text(encoding="utf-8")) != obj:
            errors.append(f"{path}: out of date with tables.py (run `nadfun-export regen`)")
    for table in TABLES:
        path = root / table_dir(table) / "README.md"
        if not path.exists() or path.read_text(encoding="utf-8") != table_readme(table):
            errors.append(f"{path.relative_to(root)}: out of date with tables.py (run `nadfun-export regen`)")


def validate(root: Path, expected_counts: dict[str, int] | None = None) -> list[str]:
    manifest = load_manifest(root)
    if manifest is None:
        return ["manifest.json: missing"]
    errors: list[str] = []
    rows = {table.name: _check_table(table, root, manifest, errors) for table in TABLES}

    for table in TABLES:
        names = table.column_names
        for fk in table.foreign_keys:
            ref_names = next(t for t in TABLES if t.name == fk.table).column_names
            targets = {tuple(r[ref_names.index(f)] for f in fk.reference_fields) for r in rows[fk.table]}
            for n, row in enumerate(rows[table.name]):
                key = tuple(row[names.index(f)] for f in fk.fields)
                if key not in targets:
                    errors.append(f"{table.name} row {n}: {key} not found in {fk.table}")

    for name, count in (expected_counts or {}).items():
        if len(rows.get(name, [])) != count:
            errors.append(f"{name}: wrote {len(rows.get(name, []))} rows, database count(*) is {count}")

    _check_metadata(root, manifest, errors)
    return errors
