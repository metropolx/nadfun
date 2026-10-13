# nad.fun launch dataset

Every token launched on [nad.fun](https://nad.fun) (Monad) and every graduation from its bonding curve, decoded from on-chain events. Each table is published as both CSV and JSON.

> [!WARNING]
> **This dataset contains no data from the nad.fun website or API (`api.nad.fun`), and we can't republish any.** The nad.fun [Terms of Use](https://nad-fun.gitbook.io/nad.fun/legal-and-risk/terms-of-use-and-warranty-disclaimer) prohibit distributing content from their interface, data included, without NadFun's prior written approval (§8.2.7, §9.3). They also prohibit scrapers and crawlers (§8.2.4). For that reason, price candles, site-only fields (e.g. community-takeover flags) and anything else fetched from nad.fun's API are not included, and pull requests adding them can't be accepted. Every value here was decoded from public Monad blockchain events.

<!-- stats:start -->

Snapshot `2026-10-13T20:28:18Z`, monad complete through block 113,135,630.

| table                                                   |   rows |     CSV |    JSON |
| ------------------------------------------------------- | -----: | ------: | ------: |
| [`tokens`](data/tokens/README.md)                       | 34,626 | 17.8 MB | 29.3 MB |
| [`token_graduations`](data/token_graduations/README.md) |    180 |   44 KB |   69 KB |

<!-- stats:end -->

## Tables

| table               | one row per                                               | key                                         | docs                                                |
| ------------------- | --------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------- |
| `tokens`            | token launch (`CurveCreate` event)                        | `(chain, token_address)`                    | [data dictionary](data/tokens/README.md)            |
| `token_graduations` | token that left its bonding curve (`CurveGraduate` event) | `(chain, token_address)`, joins to `tokens` | [data dictionary](data/token_graduations/README.md) |

Each table directory under [`data/`](data/) has:

- `<table>.csv` and `<table>.json`: the same rows in the same order
- `schema.json`: Frictionless Table Schema
- `json-schema.json`: JSON Schema for the `.json` file
- `README.md`: the data dictionary

[`datapackage.json`](datapackage.json) describes all files as a Frictionless Data Package. [`manifest.json`](manifest.json) records the snapshot time, the block the data is complete through, row counts and SHA-256 checksums.

## Formats in short

Full rules are in [docs/conventions.md](docs/conventions.md).

- **Big integers are strings.** Reserves and amounts are uint256 values in base units, and some exceed 2^90. JSON stores them as strings, e.g. `"1073000191000000000000000000"`. Keep them as strings or big integers: parsing them as floats (the default in JavaScript, pandas and jq) silently loses precision.
- **Timestamps** are ISO 8601 UTC: `2025-11-24T15:06:55Z`.
- **NULL** is an empty CSV field and `null` in JSON. Empty strings never occur.
- **Row order** is `(chain, block_number, log_index)`. That order is chronological, so each new snapshot only appends rows.
- **Identifiers**: EVM addresses and transaction hashes are lowercase `0x` hex.

## Quick start

```python
import pandas as pd

tokens = pd.read_csv("data/tokens/tokens.csv", dtype=str)  # keep uint256 columns exact
grads = pd.read_csv("data/token_graduations/token_graduations.csv", dtype=str)
graduated = tokens.merge(grads, on=["chain", "token_address"], suffixes=("", "_grad"))
```

```sql
-- DuckDB
SELECT version, count(*) AS launched, count(g.token_address) AS graduated
FROM 'data/tokens/tokens.csv' t
LEFT JOIN 'data/token_graduations/token_graduations.csv' g USING (chain, token_address)
GROUP BY version;
```

```sh
jq -r '.[] | select(.version == "v2") | .symbol' data/tokens/tokens.json | head
```

## Caveats

- **Free-text names.** `name` and `symbol` are chosen by token creators. They can contain any Unicode, newlines and offensive or misleading text. Some start with `=`, `+`, `-` or `@`, which spreadsheets may run as formulas. Import the CSV as text rather than opening it directly.
- **Quote tokens differ.** Most curves are priced in WMON, but some `v2` tokens pair with other quote tokens, so amounts in `virtual_quote_reserve` need that token's decimals.
- **`version` vs `contract_version`.** `version` `old` corresponds to contract_version `v3`, and `v2` corresponds to `nadfun-v2`.
- **Coverage.** A snapshot includes every event up to `complete_through_block` (see the manifest) and nothing after it.
- **Off-chain metadata is not included.** `token_uri` points to it.
- **No API data.** On-chain data only; see the warning at the top.

## Regenerating

You need read access to the source database, through a read-only role.

```sh
uv sync
cp .env.example .env               # then set ANALYTICS_DATABASE_URL
uv run nadfun-export status        # what an export would change
uv run nadfun-export export        # rewrite data/, schemas, manifest
uv run nadfun-export validate      # offline checks (also run in CI)
```

See [docs/releasing.md](docs/releasing.md).

## Licence

- **Data** (`data/`, `manifest.json`, `datapackage.json`): [CC0 1.0](LICENSE-DATA), dedicated to the public domain. Attribution is appreciated but not required.
- **Code**: [MIT](LICENSE).

To report a problem or request a correction, open an issue.
