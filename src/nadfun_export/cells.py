"""Canonical cell values shared by the CSV and JSON writers and by validation.

Every database row is converted exactly once into a tuple of canonical cells
(``str | int | None``). Both output formats are rendered from that same tuple,
so they cannot disagree.
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime

from .tables import CHAIN_RULES, TIMESTAMP_PATTERN, UINT_PATTERN, Column, Table

Cell = str | int | None

_UINT = re.compile(UINT_PATTERN)
_TIMESTAMP = re.compile(TIMESTAMP_PATTERN)
_CHAIN_PATTERNS = {chain: {k: re.compile(p) for k, p in rules.items()} for chain, rules in CHAIN_RULES.items()}


class CellError(ValueError):
    pass


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise CellError(f"naive timestamp {value!r}")
    if value.microsecond:
        raise CellError(f"timestamp {value.isoformat()} has sub-second precision; column is second-precision")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_cell(col: Column, value: object) -> Cell:
    """Convert a value as returned by psycopg into its canonical cell."""
    if value is None:
        return None
    if col.kind == "timestamp":
        if not isinstance(value, datetime):
            raise CellError(f"{col.name}: expected datetime, got {type(value).__name__}")
        return format_timestamp(value)
    if col.kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise CellError(f"{col.name}: expected int, got {type(value).__name__}")
        return value
    # Everything else, including uint256 (cast ::text in SQL), arrives as str.
    if not isinstance(value, str):
        raise CellError(f"{col.name}: expected str, got {type(value).__name__}")
    if value == "" and col.kind == "string" and col.nullable:
        # CSV cannot tell "" from NULL; an empty free-text value is published as NULL.
        return None
    return value


def check_cell(col: Column, cell: Cell, chain: str) -> None:
    """Raise CellError unless ``cell`` is a valid canonical value for ``col``."""
    if cell is None:
        if not col.nullable:
            raise CellError(f"{col.name}: NULL in non-nullable column")
        return
    if col.kind == "integer":
        if isinstance(cell, bool) or not isinstance(cell, int) or cell < 0:
            raise CellError(f"{col.name}: expected non-negative int, got {cell!r}")
        return
    if not isinstance(cell, str):
        raise CellError(f"{col.name}: expected str, got {cell!r}")
    if cell == "":
        # CSV cannot distinguish "" from NULL, so empty strings are not allowed.
        raise CellError(f"{col.name}: empty string")
    if col.kind == "enum" and cell not in col.enum:
        raise CellError(f"{col.name}: {cell!r} not in {col.enum}")
    if col.kind == "uint256" and not _UINT.match(cell):
        raise CellError(f"{col.name}: {cell!r} is not a non-negative integer string")
    if col.kind == "timestamp" and not _TIMESTAMP.match(cell):
        raise CellError(f"{col.name}: {cell!r} is not YYYY-MM-DDTHH:MM:SSZ")
    if col.kind in ("address", "hash") and not _CHAIN_PATTERNS[chain][col.kind].match(cell):
        raise CellError(f"{col.name}: {cell!r} is not a valid {chain} {col.kind}")


def row_cells(table: Table, row: Sequence[object]) -> tuple[Cell, ...]:
    """Convert and check one database row."""
    if len(row) != len(table.columns):
        raise CellError(f"{table.name}: expected {len(table.columns)} values, got {len(row)}")
    cells = tuple(to_cell(col, value) for col, value in zip(table.columns, row, strict=True))
    check_row(table, cells)
    return cells


def check_row(table: Table, cells: Sequence[Cell]) -> None:
    chain = cells[table.column_names.index("chain")]
    if chain not in CHAIN_RULES:
        raise CellError(f"{table.name}: unknown chain {chain!r}; add it to CHAIN_RULES first")
    for col, cell in zip(table.columns, cells, strict=True):
        check_cell(col, cell, chain)


def from_csv(col: Column, text: str) -> Cell:
    """Parse a CSV field back into its canonical cell."""
    if text == "":
        return None
    if col.kind == "integer":
        if not _UINT.match(text):
            raise CellError(f"{col.name}: {text!r} is not an integer")
        return int(text)
    return text
