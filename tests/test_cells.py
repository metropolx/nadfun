from datetime import UTC, datetime, timedelta, timezone

import pytest

from nadfun_export.cells import CellError, check_cell, format_timestamp, from_csv, row_cells, to_cell
from nadfun_export.tables import TOKENS, Column

ADDR = "0x" + "ab" * 20
TX = "0x" + "cd" * 32


def col(kind: str, nullable: bool = False, **kw) -> Column:
    return Column("c", kind, nullable, "test", **kw)


def test_timestamp_is_utc_with_z():
    plus2 = timezone(timedelta(hours=2))
    assert format_timestamp(datetime(2026, 1, 2, 5, 4, 3, tzinfo=plus2)) == "2026-01-02T03:04:03Z"


@pytest.mark.parametrize(
    "value", [datetime(2026, 1, 1), datetime(2026, 1, 1, microsecond=1, tzinfo=UTC)], ids=["naive", "subsecond"]
)
def test_timestamp_rejects(value):
    with pytest.raises(CellError):
        format_timestamp(value)


def test_uint256_keeps_full_precision():
    big = str(2**256 - 1)
    cell = to_cell(col("uint256"), big)
    check_cell(col("uint256"), cell, "monad")
    assert cell == big


@pytest.mark.parametrize("value", ["-1", "1.5", "1E-10", ""])
def test_uint256_rejects_non_integers(value):
    with pytest.raises(CellError):
        check_cell(col("uint256"), value, "monad")


def test_integer_rejects_bool():
    with pytest.raises(CellError):
        to_cell(col("integer"), True)


@pytest.mark.parametrize("kind,value", [("address", ADDR.upper().replace("0X", "0x")), ("hash", TX[:-1])])
def test_identifiers_must_be_lowercase_and_well_formed(kind, value):
    with pytest.raises(CellError):
        check_cell(col(kind), value, "monad")


def test_null_handling():
    check_cell(col("string", nullable=True), None, "monad")
    with pytest.raises(CellError):
        check_cell(col("string"), None, "monad")
    with pytest.raises(CellError):
        check_cell(col("string", nullable=True), "", "monad")


def test_enum():
    with pytest.raises(CellError):
        check_cell(col("enum", enum=("a",)), "b", "monad")


def test_unknown_chain_is_rejected():
    row = ["solana", *[None] * (len(TOKENS.columns) - 1)]
    with pytest.raises(CellError, match="unknown chain"):
        row_cells(TOKENS, row)


def test_from_csv():
    assert from_csv(col("integer"), "42") == 42
    assert from_csv(col("string", nullable=True), "") is None
    assert from_csv(col("uint256"), "007") == "007"


def test_empty_free_text_becomes_null():
    assert to_cell(col("string", nullable=True), "") is None
    assert to_cell(col("string"), "") == ""  # then rejected by check_cell
