"""Generated metadata: Frictionless schemas, JSON Schemas, table READMEs,
``datapackage.json`` and ``manifest.json``."""

import hashlib
import json
from datetime import UTC
from pathlib import Path

from . import __version__
from .tables import CHAIN_RULES, SCHEMA_VERSION, TABLES, TIMESTAMP_PATTERN, UINT_PATTERN, Column, Table

DATASET_NAME = "nadfun-launches"
CSV_DIALECT = {"delimiter": ",", "lineTerminator": "\n", "quoteChar": '"', "doubleQuote": True, "header": True}
STATS_START = "<!-- stats:start -->"
STATS_END = "<!-- stats:end -->"


def table_dir(table: Table) -> str:
    return f"data/{table.name}"


def data_paths(table: Table) -> dict[str, str]:
    return {fmt: f"{table_dir(table)}/{table.name}.{fmt}" for fmt in ("csv", "json")}


def generated_paths() -> list[str]:
    paths = []
    for table in TABLES:
        paths += [*data_paths(table).values()]
        paths += [f"{table_dir(table)}/{name}" for name in ("schema.json", "json-schema.json", "README.md")]
    return paths + ["datapackage.json", "manifest.json"]


def _identifier_pattern(kind: str, anchored: bool) -> str:
    patterns = [rules[kind] for rules in CHAIN_RULES.values()]
    if not anchored:
        patterns = [p.removeprefix("^").removesuffix("$") for p in patterns]
    return patterns[0] if len(patterns) == 1 else "|".join(f"(?:{p})" for p in patterns)


# --- Frictionless Table Schema -------------------------------------------------


def _field(col: Column) -> dict:
    field: dict = {"name": col.name, "description": col.description}
    constraints: dict = {"required": not col.nullable}
    if col.kind in ("string", "enum", "address", "hash"):
        field["type"] = "string"
        if col.kind == "enum":
            constraints["enum"] = list(col.enum)
        elif col.kind in ("address", "hash"):
            constraints["pattern"] = _identifier_pattern(col.kind, anchored=False)
        else:
            constraints["minLength"] = 1
    elif col.kind == "uint256":
        # Arbitrary precision per the spec; JSON carries it as a string.
        field["type"] = "integer"
        field["x-sqlType"] = "numeric(78,0)"
        constraints["minimum"] = 0
    elif col.kind == "integer":
        field["type"] = "integer"
        constraints["minimum"] = 0
    elif col.kind == "timestamp":
        field["type"] = "datetime"
        field["format"] = "%Y-%m-%dT%H:%M:%SZ"
    else:
        raise ValueError(f"unknown kind {col.kind}")
    if col.unit:
        field["x-unit"] = col.unit
    field["constraints"] = constraints
    return field


def table_schema(table: Table) -> dict:
    schema: dict = {
        "fields": [_field(c) for c in table.columns],
        "missingValues": [""],
        "primaryKey": list(table.primary_key),
    }
    if table.foreign_keys:
        schema["foreignKeys"] = [
            {
                "fields": list(fk.fields),
                "reference": {"resource": f"{fk.table}-csv", "fields": list(fk.reference_fields)},
            }
            for fk in table.foreign_keys
        ]
    return schema


# --- JSON Schema for <table>.json ----------------------------------------------


def _json_property(col: Column) -> dict:
    prop: dict = {"description": col.description}
    if col.kind == "integer":
        prop.update(type="integer", minimum=0)
    else:
        prop["type"] = "string"
        if col.kind == "enum":
            prop["enum"] = list(col.enum)
        elif col.kind in ("address", "hash"):
            prop["pattern"] = _identifier_pattern(col.kind, anchored=True)
        elif col.kind == "uint256":
            prop["pattern"] = UINT_PATTERN
        elif col.kind == "timestamp":
            prop["pattern"] = TIMESTAMP_PATTERN
        else:
            prop["minLength"] = 1
    if col.nullable:
        prop["type"] = [prop["type"], "null"]
        if "enum" in prop:
            prop["enum"] = [*prop["enum"], None]
    return prop


def json_schema(table: Table) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{table.name}.json",
        "description": table.description,
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": table.column_names,
            "properties": {c.name: _json_property(c) for c in table.columns},
        },
    }


# --- Per-table README (data dictionary) ----------------------------------------

_TYPE_LABELS = {
    "string": "string",
    "enum": "string (enum)",
    "address": "address",
    "hash": "tx hash",
    "uint256": "uint256 as decimal string",
    "integer": "integer",
    "timestamp": "timestamp `YYYY-MM-DDTHH:MM:SSZ`",
}


def _describe(col: Column) -> str:
    text = col.description
    if col.kind == "enum":
        text += " Values: " + ", ".join(f"`{v}`" for v in col.enum) + "."
    return text.replace("|", "\\|")


def table_readme(table: Table) -> str:
    cols = ", ".join(f"`{c}`" for c in table.primary_key)
    sort = ", ".join(f"`{c}`" for c in table.sort_key)
    lines = [
        f"# `{table.name}`",
        "",
        "<!-- Generated by `nadfun-export` from src/nadfun_export/tables.py. Do not edit. -->",
        "",
        table.description,
        "",
        f"- Files: [`{table.name}.csv`]({table.name}.csv), [`{table.name}.json`]({table.name}.json)",
        "- Schemas: [`schema.json`](schema.json) (Frictionless Table Schema), "
        "[`json-schema.json`](json-schema.json) (JSON Schema 2020-12 for the JSON file)",
        f"- Primary key: ({cols})",
        f"- Row order: ({sort}), ascending. Chronological, so new rows are appended at the end.",
    ]
    for fk in table.foreign_keys:
        lines.append(
            f"- Foreign key: ({', '.join(fk.fields)}) → [`{fk.table}`](../{fk.table}/README.md) "
            f"({', '.join(fk.reference_fields)})"
        )
    lines += [
        "",
        "Conventions (nulls, numbers, timestamps) are in [docs/conventions.md](../../docs/conventions.md).",
        "",
        "| column | type | nullable | unit | description |",
        "|---|---|---|---|---|",
    ]
    for c in table.columns:
        nullable = "yes" if c.nullable else "no"
        lines.append(f"| `{c.name}` | {_TYPE_LABELS[c.kind]} | {nullable} | {c.unit or ''} | {_describe(c)} |")
    return "\n".join(lines) + "\n"


# --- Manifest and datapackage ---------------------------------------------------


def file_info(root: Path, path: str) -> dict:
    data = (root / path).read_bytes()
    return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_manifest(root: Path, snapshot) -> dict:
    tables = {}
    for table in TABLES:
        rows = snapshot.rows[table.name]
        block_index = table.column_names.index("block_number")
        tables[table.name] = {
            "rows": len(rows),
            "max_block_number": max((r[block_index] for r in rows), default=None),
            "files": {fmt: file_info(root, p) for fmt, p in data_paths(table).items()},
        }
    return {
        "dataset": DATASET_NAME,
        "schema_version": SCHEMA_VERSION,
        "exporter_version": __version__,
        "snapshot_at": snapshot.snapshot_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"database": "dyad", "schema_migration": snapshot.schema_migration},
        "chains": {
            chain: {"complete_through_block": block} for chain, block in sorted(snapshot.through_blocks.items())
        },
        "tables": tables,
    }


def datapackage(manifest: dict) -> dict:
    resources = []
    for table in TABLES:
        for fmt, info in manifest["tables"][table.name]["files"].items():
            resource = {
                "name": f"{table.name}-{fmt}",
                "path": info["path"],
                "profile": "tabular-data-resource",
                "title": f"{table.title} ({fmt.upper()})",
                "format": fmt,
                "mediatype": "text/csv" if fmt == "csv" else "application/json",
                "encoding": "utf-8",
                "bytes": info["bytes"],
                "hash": f"sha256:{info['sha256']}",
                "schema": f"{table_dir(table)}/schema.json",
            }
            if fmt == "csv":
                resource["dialect"] = CSV_DIALECT
            resources.append(resource)
    return {
        "profile": "tabular-data-package",
        "name": DATASET_NAME,
        "title": "nad.fun launch dataset",
        "description": "Tokens launched on nad.fun and their graduations, decoded from on-chain events.",
        "version": manifest["schema_version"],
        "created": manifest["snapshot_at"],
        "licenses": [
            {
                "name": "CC0-1.0",
                "title": "CC0 1.0 Universal",
                "path": "https://creativecommons.org/publicdomain/zero/1.0/",
            }
        ],
        "sources": [{"title": "nad.fun bonding-curve contract events on Monad"}],
        "resources": resources,
    }


def dump_json(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def write_metadata(root: Path, manifest: dict) -> None:
    for table in TABLES:
        directory = root / table_dir(table)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "schema.json").write_text(dump_json(table_schema(table)), encoding="utf-8")
        (directory / "json-schema.json").write_text(dump_json(json_schema(table)), encoding="utf-8")
        (directory / "README.md").write_text(table_readme(table), encoding="utf-8")
    (root / "datapackage.json").write_text(dump_json(datapackage(manifest)), encoding="utf-8")
    (root / "manifest.json").write_text(dump_json(manifest), encoding="utf-8")


def _size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def readme_stats(manifest: dict) -> str:
    lines = [
        STATS_START,
        f"Snapshot `{manifest['snapshot_at']}`, "
        + ", ".join(
            f"{chain} complete through block {info['complete_through_block']:,}"
            for chain, info in manifest["chains"].items()
        )
        + ".",
        "",
        "| table | rows | CSV | JSON |",
        "|---|---:|---:|---:|",
    ]
    for name, info in manifest["tables"].items():
        sizes = [_size(info["files"][fmt]["bytes"]) for fmt in ("csv", "json")]
        lines.append(f"| [`{name}`](data/{name}/README.md) | {info['rows']:,} | {sizes[0]} | {sizes[1]} |")
    return "\n".join(lines + [STATS_END])


def update_readme(path: Path, manifest: dict) -> bool:
    text = path.read_text(encoding="utf-8")
    start, end = text.find(STATS_START), text.find(STATS_END)
    if start < 0 or end < 0:
        return False
    path.write_text(text[:start] + readme_stats(manifest) + text[end + len(STATS_END) :], encoding="utf-8")
    return True


def load_manifest(root: Path) -> dict | None:
    path = root / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
