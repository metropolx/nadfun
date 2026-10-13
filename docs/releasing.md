# Syncing the repository with the database

The dataset is regenerated from the `dyad` database through a read-only role. The connection string lives only in a local, git-ignored `.env`:

```sh
ANALYTICS_DATABASE_URL=postgresql://analytics:…@…/dyad?sslmode=require
```

Exports run locally, never in CI, so no database credentials are stored on GitHub.

## Steps

```sh
uv sync
uv run nadfun-export status     # row counts and blocks an export would add, vs manifest.json
uv run nadfun-export export     # snapshot -> .export-tmp/ -> validate -> move into place
git diff --stat
uv run pytest -q
git add -A && git commit -m "data: snapshot YYYY-MM-DD"
```

What `export` does:

1. It opens one `REPEATABLE READ READ ONLY` transaction and refuses to continue if the session isn't read-only.
2. It reads the per-chain complete-through block from the indexer checkpoints, then every table up to that block, with `count(*)` checked against the rows read.
3. It writes all files into `.export-tmp/` and runs the full validation there.
4. Only if validation passes, it replaces the committed files and refreshes the stats block in `README.md`. If validation fails, the committed files are left untouched and `.export-tmp/` is kept for inspection.

Data files are only appended to between snapshots, unless rows are corrected upstream, so `git diff` shows exactly what's new.

## Changing the schema

1. Edit [`src/nadfun_export/tables.py`](../src/nadfun_export/tables.py) and bump `SCHEMA_VERSION`: major for removed, renamed or retyped columns; minor for added columns.
2. Run `uv run nadfun-export export`. For a description-only change, `uv run nadfun-export regen` rewrites the schemas and table READMEs without touching the database.
3. Add an entry to [`CHANGELOG.md`](../CHANGELOG.md).

`validate` fails if any committed schema or table README is out of date with `tables.py`.

## Size limits

GitHub rejects files over 100 MB. When any single data file passes 50 MB, partition that table by UTC month of its event time (`data/<table>/<YYYY-MM>.csv` / `.json`). Then list the parts as a multipart `path` array in `datapackage.json`. The schemas stay unchanged. At the first snapshot the largest file, `tokens.json`, is 29 MB.
