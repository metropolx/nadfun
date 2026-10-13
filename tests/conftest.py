from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from nadfun_export.cells import row_cells
from nadfun_export.metadata import build_manifest, write_metadata
from nadfun_export.tables import TABLES, TOKEN_GRADUATIONS, TOKENS
from nadfun_export.writers import write_table

WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"


def _addr(n: int) -> str:
    return f"0x{n:040x}"


def _tx(n: int) -> str:
    return f"0x{n:064x}"


def _token(n: int, name: str, symbol: str | None, min_reserve: str | None) -> tuple:
    return (
        "monad", _addr(1000 + n), "nadfun", "v2" if min_reserve else "old", "nadfun-v2" if min_reserve else "v3",
        _addr(1), _addr(2000 + n), name, symbol, f"https://example.org/{n}.json", WMON, _addr(3000 + n),
        "90000000000000000000000", "1073000191000000000000000000", str(2**256 - 1), min_reserve,
        datetime(2026, 1, 1, 0, 0, n, tzinfo=UTC), 100 + n, _tx(n), n,
    )  # fmt: skip


# Awkward values on purpose: CSV specials, newlines, CR, Unicode, formula prefix, NULLs.
RAW_TOKENS = [
    _token(1, 'Comma, "quoted"', "CQ", None),
    _token(2, "Line\nbreak\r\nand CR", "NL", "1"),
    _token(3, "ünïcødé 🚀  ", None, None),
    _token(4, "=HYPERLINK(1)", "-X", "279900191000000000000000000"),
]
RAW_GRADUATIONS = [
    ("monad", _addr(1002), "nadfun", _addr(1), _addr(3002), datetime(2026, 2, 1, tzinfo=UTC), 500, _tx(99), 7),
]


def make_snapshot(raw_tokens=RAW_TOKENS, raw_graduations=RAW_GRADUATIONS) -> SimpleNamespace:
    rows = {
        TOKENS.name: [row_cells(TOKENS, r) for r in raw_tokens],
        TOKEN_GRADUATIONS.name: [row_cells(TOKEN_GRADUATIONS, r) for r in raw_graduations],
    }
    return SimpleNamespace(
        snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
        schema_migration="9",
        through_blocks={"monad": 1000},
        rows=rows,
        counts={k: len(v) for k, v in rows.items()},
    )


def export_to(root: Path, snapshot: SimpleNamespace) -> dict:
    for table in TABLES:
        write_table(table, snapshot.rows[table.name], root / "data" / table.name)
    manifest = build_manifest(root, snapshot)
    write_metadata(root, manifest)
    return manifest


@pytest.fixture
def exported(tmp_path: Path) -> Path:
    export_to(tmp_path, make_snapshot())
    return tmp_path
