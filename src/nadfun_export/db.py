"""Read-only, mutually consistent snapshot of the published tables."""

import os
from dataclasses import dataclass
from datetime import datetime

import psycopg
from dotenv import load_dotenv
from psycopg import sql

from .cells import Cell, CellError, row_cells
from .tables import TABLES, Table

ENV_VAR = "ANALYTICS_DATABASE_URL"

# Per chain, the highest block for which every indexer stream is complete.
# A stream that reached its end_block no longer limits the cut.
_THROUGH_BLOCK = """
SELECT chain,
       coalesce(min(CASE WHEN end_block IS NOT NULL AND last_completed_block >= end_block
                         THEN NULL ELSE last_completed_block END),
                max(last_completed_block)) AS through_block
FROM ingest_checkpoints
GROUP BY chain
"""


class ExportError(RuntimeError):
    pass


@dataclass
class Snapshot:
    snapshot_at: datetime
    schema_migration: str | None
    through_blocks: dict[str, int]
    rows: dict[str, list[tuple[Cell, ...]]]
    counts: dict[str, int]


def connect() -> psycopg.Connection:
    load_dotenv()
    url = os.environ.get(ENV_VAR)
    if not url:
        raise ExportError(f"{ENV_VAR} is not set. Put it in a local .env (see .env.example).")
    try:
        conn = psycopg.connect(url, application_name="nadfun-export")
    except psycopg.Error as e:
        # Never echo the connection string.
        raise ExportError(f"could not connect via {ENV_VAR}: {str(e).replace(url, '<redacted>')}") from None
    conn.read_only = True
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    return conn


def _select(table: Table) -> sql.Composed:
    cols = [
        sql.SQL("t.{}::text").format(sql.Identifier(c.name))
        if c.kind == "uint256"
        else sql.SQL("t.{}").format(sql.Identifier(c.name))
        for c in table.columns
    ]
    order = [
        sql.SQL('t.{} COLLATE "C"').format(sql.Identifier(k))
        if table.column(k).kind != "integer"
        else sql.SQL("t.{}").format(sql.Identifier(k))
        for k in table.sort_key
    ]
    return sql.SQL("SELECT {cols} FROM {table} t {filter} ORDER BY {order}").format(
        cols=sql.SQL(", ").join(cols),
        table=sql.Identifier(table.name),
        filter=_filter(),
        order=sql.SQL(", ").join(order),
    )


def _count(table: Table) -> sql.Composed:
    return sql.SQL("SELECT count(*) FROM {table} t {filter}").format(table=sql.Identifier(table.name), filter=_filter())


def _filter() -> sql.Composed:
    return sql.SQL("JOIN ({cp}) cp ON cp.chain = t.chain WHERE t.block_number <= cp.through_block").format(
        cp=sql.SQL(_THROUGH_BLOCK)
    )


def _convert(table: Table, row: tuple) -> tuple[Cell, ...]:
    try:
        return row_cells(table, row)
    except CellError as e:
        key = {k: row[table.column_names.index(k)] for k in table.primary_key}
        raise ExportError(f"{table.name} {key}: {e}") from None


def _begin(cur: psycopg.Cursor) -> None:
    cur.execute("SET LOCAL TimeZone = 'UTC'")
    cur.execute("SET LOCAL statement_timeout = '300s'")
    cur.execute("SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')")
    isolation, read_only = cur.fetchone()
    if isolation != "repeatable read" or read_only != "on":
        raise ExportError(f"expected a repeatable read, read-only transaction; got {isolation}, read_only={read_only}")


def read_counts(conn: psycopg.Connection) -> tuple[dict[str, int], dict[str, int]]:
    """Row counts and through-blocks the next export would produce."""
    with conn.transaction(), conn.cursor() as cur:
        _begin(cur)
        cur.execute(_THROUGH_BLOCK)
        through = {chain: block for chain, block in cur.fetchall()}
        counts = {}
        for table in TABLES:
            cur.execute(_count(table))
            counts[table.name] = cur.fetchone()[0]
    return counts, through


def read_snapshot(conn: psycopg.Connection) -> Snapshot:
    with conn.transaction(), conn.cursor() as cur:
        _begin(cur)
        cur.execute("SELECT now()")
        snapshot_at = cur.fetchone()[0]
        cur.execute("SELECT max(version)::text FROM schema_migrations")
        schema_migration = cur.fetchone()[0]
        cur.execute(_THROUGH_BLOCK)
        through = {chain: block for chain, block in cur.fetchall()}
        rows, counts = {}, {}
        for table in TABLES:
            cur.execute(_select(table))
            rows[table.name] = [_convert(table, r) for r in cur]
            cur.execute(_count(table))
            counts[table.name] = cur.fetchone()[0]
            if counts[table.name] != len(rows[table.name]):
                raise ExportError(
                    f"{table.name}: read {len(rows[table.name])} rows but count(*) is {counts[table.name]}"
                )
    return Snapshot(snapshot_at.replace(microsecond=0), schema_migration, through, rows, counts)
