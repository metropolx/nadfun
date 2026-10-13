"""nadfun-export: regenerate, check and validate the published dataset.

nadfun-export export     read a DB snapshot and rewrite data/, manifest, schemas
nadfun-export status     compare the committed manifest with the live database
nadfun-export validate   offline checks of the committed files (used by CI)
nadfun-export regen      rewrite schemas, table READMEs and datapackage from tables.py
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from .db import ExportError, connect, read_counts, read_snapshot
from .metadata import build_manifest, generated_paths, load_manifest, update_readme, write_metadata
from .tables import TABLES
from .validate import validate
from .writers import write_table

TMP_DIR = ".export-tmp"


def _print_errors(errors: list[str], limit: int = 50) -> None:
    for e in errors[:limit]:
        print(f"  {e}", file=sys.stderr)
    if len(errors) > limit:
        print(f"  ... and {len(errors) - limit} more", file=sys.stderr)


def _compare(previous: dict | None, counts: dict[str, int], through: dict[str, int]) -> None:
    old_tables = (previous or {}).get("tables", {})
    old_chains = (previous or {}).get("chains", {})
    for name, n in counts.items():
        old = old_tables.get(name, {}).get("rows")
        delta = "" if old is None else f" ({n - old:+,})"
        print(f"  {name}: {n:,} rows{delta}")
    for chain, block in through.items():
        old = old_chains.get(chain, {}).get("complete_through_block")
        delta = "" if old is None else f" ({block - old:+,} blocks)"
        print(f"  {chain}: complete through block {block:,}{delta}")


def cmd_export(root: Path) -> int:
    with connect() as conn:
        snapshot = read_snapshot(conn)
    tmp = root / TMP_DIR
    shutil.rmtree(tmp, ignore_errors=True)
    for table in TABLES:
        write_table(table, snapshot.rows[table.name], tmp / "data" / table.name)
    manifest = build_manifest(tmp, snapshot)
    write_metadata(tmp, manifest)

    errors = validate(tmp, expected_counts=snapshot.counts)
    if errors:
        print(f"export failed validation; output left in {tmp}:", file=sys.stderr)
        _print_errors(errors)
        return 1

    previous = load_manifest(root)
    for path in generated_paths():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp / path, root / path)
    shutil.rmtree(tmp)
    update_readme(root / "README.md", manifest)

    print(f"exported snapshot {manifest['snapshot_at']}:")
    _compare(previous, snapshot.counts, snapshot.through_blocks)
    return 0


def cmd_status(root: Path) -> int:
    with connect() as conn:
        counts, through = read_counts(conn)
    previous = load_manifest(root)
    print(f"committed snapshot: {previous['snapshot_at'] if previous else 'none'}")
    print("an export now would produce:")
    _compare(previous, counts, through)
    return 0


def cmd_validate(root: Path) -> int:
    errors = validate(root)
    if errors:
        print(f"{len(errors)} validation error(s):", file=sys.stderr)
        _print_errors(errors)
        return 1
    print("ok")
    return 0


def cmd_regen(root: Path) -> int:
    manifest = load_manifest(root)
    if manifest is None:
        print("manifest.json missing; run `nadfun-export export` first", file=sys.stderr)
        return 1
    write_metadata(root, manifest)
    update_readme(root / "README.md", manifest)
    return cmd_validate(root)


def main() -> None:
    parser = argparse.ArgumentParser(prog="nadfun-export", description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["export", "status", "validate", "regen"])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    args = parser.parse_args()
    commands = {"export": cmd_export, "status": cmd_status, "validate": cmd_validate, "regen": cmd_regen}
    try:
        sys.exit(commands[args.command](args.root.resolve()))
    except ExportError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
