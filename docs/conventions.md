# Conventions

These rules apply to every published table. Per-column types and descriptions are in each table's `README.md` and `schema.json`, generated from [`src/nadfun_export/tables.py`](../src/nadfun_export/tables.py).

## Files

| | CSV | JSON |
|---|---|---|
| encoding | UTF-8 without BOM | UTF-8 (non-ASCII characters are not escaped) |
| layout | header row, then one record per row | an array of objects, with one object per line: `[`, `{…},` … `{…}`, `]` |
| column/key order | as in the data dictionary | same order; every key is always present |
| dialect | RFC 4180: `,` separator, `"` quote, `""` escapes a quote, LF line endings. Fields that contain `,`, `"`, CR or LF are quoted. | — |

Both files are rendered from the same in-memory rows in a single pass, and validation parses them back and checks that they hold the same data.

## Values

| type | CSV | JSON | example |
|---|---|---|---|
| NULL | empty field | `null` | |
| string | as is | string | `"winter arc"` |
| uint256 (base units) | digits | **string** of digits | `"90000000000000000000000"` |
| integer (`block_number`, `log_index`) | digits | number | `113116552` |
| timestamp | ISO 8601 UTC | string | `"2025-11-26T22:21:13Z"` |
| address / tx hash (EVM) | lowercase `0x` hex | string | `"0x3bd359c1119da7da1d913d1c4d2b7c461115433a"` |

- **Empty strings never occur.** An empty CSV field always means NULL. CSV cannot tell the two apart, so an empty free-text value in the source (e.g. a `token_uri` of `''`) is published as NULL. Validation rejects any empty string that remains.
- **uint256 values are strings in JSON** because they exceed 2^53. JavaScript, jq and pandas would round them as floats. There is no exponent notation and no decimal point.
- **Amounts are in base units.** Token amounts use the launched token's smallest unit, and quote amounts use the `quote_token`'s smallest unit. Divide by `10^decimals` of that token to get whole units.
- **Timestamps are second-precision** block timestamps, always in UTC with a `Z` suffix.

## Ordering and coverage

- Rows are sorted by `(chain, block_number, log_index)`. This key is unique and chronological, so between snapshots rows are only appended. A row can still change in place if it is corrected upstream.
- Each snapshot is read in one `REPEATABLE READ` transaction, so all tables are mutually consistent.
- Per chain, `manifest.json` → `chains.<chain>.complete_through_block` is the highest block for which the indexer has processed every event stream. Rows after that block are left out, so a snapshot never contains a half-indexed block range.

## Multi-chain

- Every table starts with a `chain` column, and keys always include it.
- Today only `monad` is present.
- Identifier formats are defined per chain. EVM identifiers are lowercase hex. Non-EVM chains such as Solana use base58, which is case-sensitive, and will never be lowercased.
- Rows from a chain without defined rules fail validation instead of being published unchecked.
