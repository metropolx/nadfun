"""CSV and JSON writers. Both consume the same canonical cell tuples."""

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from .cells import Cell
from .tables import Table


def write_table(table: Table, rows: Iterable[tuple[Cell, ...]], directory: Path) -> tuple[Path, Path]:
    """Write ``<table>.csv`` and ``<table>.json`` from one pass over ``rows``."""
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / f"{table.name}.csv"
    json_path = directory / f"{table.name}.json"
    names = table.column_names
    with (
        csv_path.open("w", encoding="utf-8", newline="") as csv_file,
        json_path.open("w", encoding="utf-8", newline="") as json_file,
    ):
        writer = csv.writer(csv_file, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(names)
        json_file.write("[")
        separator = "\n"
        for row in rows:
            # None -> empty field; ints and strings are written as-is.
            writer.writerow(row)
            json_file.write(separator)
            json_file.write(json.dumps(dict(zip(names, row, strict=True)), ensure_ascii=False, separators=(",", ":")))
            separator = ",\n"
        json_file.write("\n]\n")
    return csv_path, json_path
