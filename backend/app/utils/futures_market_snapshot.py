"""Frozen, session-free snapshots of the Discover futures candidate rows.

LAT-P174, #2143 residual. This is the piece `principal_independent_cache.py`
explicitly left on the table:

    "A hydrated ORM row therefore CANNOT enter this cache. ... and it is why
     `futures.market_load` (567-617ms of hydrated rows) is left on the table by
     this change."

## Why this is the residual worth taking

Measured on production 2026-08-31, one returning reader (`x-session-id` with 117
recorded impressions), `/api/feed?limit=20&event_pct=0.15`, server-side stage
header, not wall clock:

    x-feed-cache: miss   x-feed-elapsed-ms: 1533.04
    futures=1043.96  futures.market_load=588.48  futures.scoring_loop=433.64
    events=219.28  personalization=113.08  golf=88.19  ranking=41.78

`market_load` is **38% of the whole request** and it is principal-INDEPENDENT by
construction: its only input is the ordered candidate-ID list, which
`candidate_base.py` already shares across principals because the pools depend
only on `(now, sport_filter, static_tag_filter)`. Two principals a second apart
issue the identical three-round-trip SELECT and get the identical rows.

The reason it was not shared was never the data — it was the CARRIER. Which is
what this module changes: the shared artifact is a plain-data table of the
loaded COLUMN VALUES, and the hydrated objects are rebuilt per request as inert
snapshots that hold no session, no identity map and no lazy loaders.

## The load surface is closed, and that is what makes the snapshot faithful

`_score_futures` does not read arbitrary attributes — it reads exactly what the
query loads, because anything else already crashes today. The `load_only` list
is not an optimisation there, it is a contract, and it carries two comments
saying so (#1698 on `market_type`, L2-172 on `calibration_probability`): an
omitted column lazy-loads under async and raises `MissingGreenlet` inside the
per-item serializer, emptying the whole futures pool (gotcha #42).

So the column tuples below ARE the load surface, and `market_load_options()`
builds the query's `load_only` FROM them. A column added to one and not the
other is not possible; there is one list.

## Reading the ORM instance

Every read goes through `instance.__dict__.get(name)`, never `getattr`. On a
`load_only` query an unloaded attribute is *deferred*, and `getattr` on a
deferred attribute in an async context does not return a default — it attempts
a lazy load and raises. `__dict__.get` returns what was loaded and `None`
otherwise, which is the same idiom `feed.py` already uses at its own
`market.__dict__.get("curation_score_adj", 0)` call sites.

The snapshots expose a real instance `__dict__` for the same reason: `feed.py`
reads `market.__dict__.get("story_key")` for a column that is deliberately NOT
loaded, and must keep getting `None` rather than an `AttributeError`.

## What is NOT claimed here

These snapshots are inert data, not ORM rows. They cannot be added to a session,
refreshed, or lazily navigated, and nothing in the futures scoring path does any
of those (verified call-site by call-site: every consumer reads attributes).
`test_futures_market_snapshot_lat_p174.py` pins the surface so a future consumer
that needs a live row fails a test instead of a request.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

#: Columns loaded for `FuturesMarket` on the Discover futures candidate query.
#:
#: ORDER IS THE WIRE FORMAT. A row is a positional list, not a dict, because the
#: repeated key names of a 700-row dict payload are pure overhead on a shared
#: artifact that is size-capped (`MAX_ENVELOPE_BYTES`). Appending is safe;
#: reordering or removing requires a `SNAPSHOT_SCHEMA_VERSION` bump, which is
#: part of the cache key and therefore self-invalidating.
MARKET_COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "source",
    "external_id",
    "sport_id",
    "category",
    "llm_sport_category",
    "market_tier",
    # #1698: the serializer reads `market_type`, so it MUST be loaded. Omitted,
    # the attribute access lazy-loads, and a lazy load under async raises
    # MissingGreenlet INSIDE the per-item serializer — which empties the WHOLE
    # futures pool rather than dropping one card (gotcha #42).
    "market_type",
    "canonical_market_key",
    "group_id",
    "group_type",
    "image_url",
    # LAT-P195 (#2614): the hero `srcset` needs the raster's TRUE width, not the
    # one the URL implies. Same rule as `market_type` above — unprojected, these
    # lazy-load inside the per-item serializer and empty the whole futures pool
    # (gotcha #42). They are also why a snapshot that omitted them would not be
    # faithful: the cached path would serve `None` dimensions where the direct
    # path serves real ones, which is a DIFFERENT feed, not a cheaper one.
    "image_width",
    "image_height",
    "hook_description",
    "hook_generated_at",
    "hook_leader_at_generation",
    "market_metadata",
    "curation_score_adj",
    "volume_24h",
    "updated_at",
    "commence_time",
    "resolution_date",
    "status",
    "created_at",
    "llm_league",
    "llm_gender",
    "llm_level",
)

#: Columns loaded for each `FuturesOutcome`.
OUTCOME_COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "team_id",
    "current_probability",
    "probability_change_24h",
    "rank",
    "rank_change_24h",
    "opening_probability",
    # L2-172: needed for the has_closing_line calibration signal; deferred here
    # would lazy-load per outcome and crash this async route.
    "calibration_probability",
    # UX-P011 (#1574): the fabricated-midpoint gate reads the book. Same rule as
    # the line above — omitting these lazy-loads per outcome and crashes the
    # async route.
    "current_yes_bid",
    "current_yes_ask",
    # Q480 / CERT-622: `drop_duplicate_legs(..., lambda o: o.external_id)` runs
    # on these rows at BOTH scorers — and on the shared path it runs on the
    # SNAPSHOTS. This is the column whose absence emptied the futures pool once
    # already; omitted here it would not lazy-load, it would simply not exist on
    # the rebuilt outcome and raise `AttributeError` instead. Same pool, same
    # emptiness, one layer down.
    "external_id",
)

#: Columns loaded for the related `Sport`.
SPORT_COLUMNS: tuple[str, ...] = ("key", "name")

#: Bumped whenever the tuples above change shape. It travels in the shared cache
#: key, so a deploy that changes the wire format cannot read a predecessor's
#: entries — they simply expire under their own TTL.
#:
#: v2 — rebase onto master: `image_width` / `image_height` were INSERTED (not
#: appended) after `image_url` to keep the tuple reading in load-surface order,
#: and `external_id` appended to the outcome row. An insertion shifts every
#: later position, so a v1 entry decoded as v2 would silently misalign whole
#: columns; the bump is what makes that unreachable rather than unlikely.
SNAPSHOT_SCHEMA_VERSION = 2


class _Snapshot:
    """A plain object whose attributes are its loaded columns.

    Deliberately NOT `__slots__`: `feed.py` reads `market.__dict__.get(...)` for
    columns that are intentionally unloaded and must keep getting `None`, so a
    real instance dict is part of the contract, not an accident.
    """

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        ident = self.__dict__.get("id", self.__dict__.get("key"))
        return f"<{type(self).__name__} {ident!r}>"


class SportSnapshot(_Snapshot):
    """Inert stand-in for a `load_only`-restricted `Sport` row."""

    def __init__(self, values: Sequence[Any]) -> None:
        for name, value in zip(SPORT_COLUMNS, values):
            self.__dict__[name] = value


class FuturesOutcomeSnapshot(_Snapshot):
    """Inert stand-in for a `load_only`-restricted `FuturesOutcome` row."""

    def __init__(self, values: Sequence[Any]) -> None:
        for name, value in zip(OUTCOME_COLUMNS, values):
            self.__dict__[name] = value


class FuturesMarketSnapshot(_Snapshot):
    """Inert stand-in for a hydrated `FuturesMarket` + its outcomes + its sport."""

    def __init__(
        self,
        values: Sequence[Any],
        outcomes: list[FuturesOutcomeSnapshot],
        sport: SportSnapshot | None,
    ) -> None:
        for name, value in zip(MARKET_COLUMNS, values):
            self.__dict__[name] = value
        self.__dict__["outcomes"] = outcomes
        self.__dict__["sport"] = sport


def market_load_options() -> list[Any]:
    """The `load_only` / `selectinload` options for the candidate SELECT.

    Built from the column tuples above so the query and the snapshot can never
    disagree about what is loaded. Imported lazily so this module stays cheap
    for callers that only need the column names (tests, the codec, tooling).
    """
    from sqlalchemy.orm import load_only, selectinload

    from app.models.models import FuturesMarket, FuturesOutcome, Sport

    return [
        load_only(*(getattr(FuturesMarket, c) for c in MARKET_COLUMNS)),
        selectinload(FuturesMarket.outcomes).load_only(
            *(getattr(FuturesOutcome, c) for c in OUTCOME_COLUMNS)
        ),
        selectinload(FuturesMarket.sport).load_only(
            *(getattr(Sport, c) for c in SPORT_COLUMNS)
        ),
    ]


def _row(instance: Any, columns: tuple[str, ...]) -> list[Any]:
    """One positional row of loaded values.

    `__dict__.get`, never `getattr` — a deferred attribute would lazy-load and
    raise `MissingGreenlet` on this async path rather than return a default.
    """
    state = instance.__dict__
    return [state.get(name) for name in columns]


def to_plain(markets: Iterable[Any]) -> dict[str, Any]:
    """Convert hydrated ORM markets into the shareable plain-data artifact.

    The result contains only `None`/`bool`/`int`/`float`/`str`/`datetime`/
    `Decimal` and lists of those — i.e. it passes `assert_plain_data`, which is
    what makes it eligible for the cross-worker cache at all. `Decimal` and
    `datetime` are carried AS THEMSELVES rather than normalised to float/str:
    the scoring path compares and rounds these values, and a snapshot that
    silently changed their type would change the feed.
    """
    rows: list[list[Any]] = []
    for market in markets:
        state = market.__dict__
        outcomes = state.get("outcomes") or []
        sport = state.get("sport")
        rows.append(
            [
                _row(market, MARKET_COLUMNS),
                [_row(o, OUTCOME_COLUMNS) for o in outcomes],
                _row(sport, SPORT_COLUMNS) if sport is not None else None,
            ]
        )
    return {"v": SNAPSHOT_SCHEMA_VERSION, "rows": rows}


def from_plain(payload: Any) -> list[FuturesMarketSnapshot]:
    """Rebuild snapshots from the artifact `to_plain` produced.

    Returns `[]` for anything that is not a payload of this schema version —
    a shape the caller must treat as "build it yourself", never as "there are no
    candidate markets". The caller checks the version itself before deciding;
    this function refuses rather than guesses.
    """
    if not isinstance(payload, dict) or payload.get("v") != SNAPSHOT_SCHEMA_VERSION:
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[FuturesMarketSnapshot] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            continue
        market_values, outcome_rows, sport_values = row
        out.append(
            FuturesMarketSnapshot(
                market_values,
                [FuturesOutcomeSnapshot(o) for o in (outcome_rows or [])],
                SportSnapshot(sport_values) if sport_values is not None else None,
            )
        )
    return out


def is_snapshot_payload(payload: Any) -> bool:
    """Whether `payload` is a well-formed artifact of the CURRENT schema."""
    return (
        isinstance(payload, dict)
        and payload.get("v") == SNAPSHOT_SCHEMA_VERSION
        and isinstance(payload.get("rows"), list)
    )


__all__ = [
    "MARKET_COLUMNS",
    "OUTCOME_COLUMNS",
    "SPORT_COLUMNS",
    "SNAPSHOT_SCHEMA_VERSION",
    "FuturesMarketSnapshot",
    "FuturesOutcomeSnapshot",
    "SportSnapshot",
    "market_load_options",
    "to_plain",
    "from_plain",
    "is_snapshot_payload",
]
