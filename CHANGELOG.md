# Changelog

## Snapshot 2026-10-13 (schema 1.0.0)

First release.

- `tokens`: 34,626 rows. `token_graduations`: 180 rows.
- Monad, complete through block 113,135,630.
- On-chain data only. Indexer bookkeeping columns (`ingested_at`, `first_seen_at`) are not published.
- 4 tokens with an empty `token_uri` in the source are published with `token_uri` NULL.
