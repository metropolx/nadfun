"""Registry of published tables: the single source of truth.

The export SQL, CSV header, JSON key order, Frictionless schema, JSON Schema
and per-table README are all generated from these definitions.
"""

from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0.0"

# Per-chain identifier formats. A chain must be listed here before its rows can
# be published; validation rejects unknown chains rather than guessing.
# EVM identifiers are lowercase hex. Non-EVM chains (e.g. Solana base58) are
# case-sensitive and must never be lowercased.
CHAIN_RULES: dict[str, dict[str, str]] = {
    "monad": {
        "address": r"^0x[0-9a-f]{40}$",
        "hash": r"^0x[0-9a-f]{64}$",
    },
}

UINT_PATTERN = r"^[0-9]+$"
TIMESTAMP_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"


@dataclass(frozen=True)
class Column:
    name: str
    # string | enum | address | hash | uint256 | integer | timestamp
    kind: str
    nullable: bool
    description: str
    unit: str | None = None
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForeignKey:
    fields: tuple[str, ...]
    table: str
    reference_fields: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    description: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    # Unique, chronological order: new events append to the end of the file.
    sort_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...] = field(default=())

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)


_CHAIN = Column("chain", "enum", False, "Chain the event was observed on.", enum=tuple(CHAIN_RULES))
_LAUNCHPAD = Column("launchpad", "enum", False, "Launchpad that emitted the event.", enum=("nadfun",))
_EVENT_LOCATION = (
    Column("block_number", "integer", False, "Block containing the event."),
    Column("tx_hash", "hash", False, "Transaction containing the event."),
    Column("log_index", "integer", False, "Position of the event log within its block."),
)

TOKENS = Table(
    name="tokens",
    title="Tokens",
    description="One row per token launched on nad.fun (one CurveCreate event).",
    columns=(
        _CHAIN,
        Column("token_address", "address", False, "Address of the launched ERC-20 token."),
        _LAUNCHPAD,
        Column(
            "version",
            "enum",
            True,
            "nad.fun launch generation: `old` (contract_version `v3`) or `v2` (contract_version `nadfun-v2`).",
            enum=("old", "v2"),
        ),
        Column("contract_version", "string", False, "Label of the bonding-curve contract that emitted the event."),
        Column("contract_address", "address", False, "Bonding-curve contract that emitted the event."),
        Column("creator", "address", False, "Address that launched the token."),
        Column("name", "string", True, "Token name as recorded at launch. User-chosen, may contain any Unicode."),
        Column("symbol", "string", True, "Token symbol as recorded at launch. User-chosen."),
        Column("token_uri", "string", True, "URI of the token's off-chain metadata JSON."),
        Column(
            "quote_token",
            "address",
            True,
            "Token the curve is priced in. Usually WMON "
            "(`0x3bd359c1119da7da1d913d1c4d2b7c461115433a`); some `v2` tokens pair with other tokens.",
        ),
        Column("pool_address", "address", True, "Pool address recorded for the token at launch."),
        Column(
            "virtual_quote_reserve",
            "uint256",
            True,
            "Initial virtual reserve of the quote token on the curve.",
            unit="base units of quote_token",
        ),
        Column(
            "virtual_token_reserve",
            "uint256",
            True,
            "Initial virtual reserve of the launched token on the curve.",
            unit="base units of the token",
        ),
        Column(
            "target_token_amount",
            "uint256",
            True,
            "Target token amount of the curve.",
            unit="base units of the token",
        ),
        Column(
            "min_token_reserve",
            "uint256",
            True,
            "Minimum token reserve of the curve. Only set for `v2` tokens.",
            unit="base units of the token",
        ),
        Column("created_at", "timestamp", True, "Timestamp of the block containing the launch event.", unit="UTC"),
        *_EVENT_LOCATION,
    ),
    primary_key=("chain", "token_address"),
    sort_key=("chain", "block_number", "log_index"),
)

TOKEN_GRADUATIONS = Table(
    name="token_graduations",
    title="Token graduations",
    description="One row per token that left its bonding curve (one CurveGraduate event).",
    columns=(
        _CHAIN,
        Column("token_address", "address", False, "Graduated token. Joins to `tokens` on (chain, token_address)."),
        _LAUNCHPAD,
        Column("contract_address", "address", False, "Bonding-curve contract that emitted the event."),
        Column("pool_address", "address", True, "Pool address recorded in the graduation event."),
        Column(
            "graduated_at", "timestamp", True, "Timestamp of the block containing the graduation event.", unit="UTC"
        ),
        *_EVENT_LOCATION,
    ),
    primary_key=("chain", "token_address"),
    sort_key=("chain", "block_number", "log_index"),
    foreign_keys=(ForeignKey(("chain", "token_address"), "tokens", ("chain", "token_address")),),
)

TABLES: tuple[Table, ...] = (TOKENS, TOKEN_GRADUATIONS)
