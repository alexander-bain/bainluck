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
#: artifact that is size-capped (`MAX_ENVELOPE_BYTES`). Reordering or removing
#: requires a `SNAPSHOT_SCHEMA_VERSION` bump, which is part of the cache key and
#: therefore self-invalidating.
#:
#: Appending is safe but NOT wire-compatible, and CERT-615 [P2] is why that
#: distinction is now stated: row arity is validated exactly, so an in-flight
#: entry written by the previous width is REJECTED and rebuilt rather than
#: zip-truncated into a pool whose new column is invisibly absent on every row.
#: Rebuilding one artifact once is the cheap outcome; the truncation was not.
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

# ux/1070 item 5 wanted a price AGE here and `last_updated` is deliberately NOT
# in the tuple above. It was added, and two guards in a row priced the decision:
# `test_feed_outcome_projection_cert622` demanded the projection grow (correct —
# an unprojected read is a MissingGreenlet inside the serializer), and then
# `test_feed_market_load_fits_the_shared_wire_lat_p221` measured the result at
# 3,361,009 B against a 2,928,973 B budget — a 15% growth in a shared Redis
# artifact, for one timestamp repeated across up to 193 outcomes per market.
#
# `FuturesMarket.updated_at` is already in `MARKET_COLUMNS`, one value per market
# instead of one per outcome, and it carries the same signal: measured on
# production 2026-09-04 across the whole in-window golf/tennis population, the
# market row's age and `max(outcome.last_updated)` agreed to within 0.4h on every
# row (1023.3/1023.3, 656.2/656.2, 239.9/239.9, 237.4/237.8, 92.9/92.9). The
# poller touches the market row when it writes prices.
#
# The caveat, stated rather than discovered later: a non-price write to the
# market row would make a stale-priced market look fresh. That is tolerable here
# because the threshold sits in a measured 6h–92h gap with nothing in it, so
# being wrong by a few hours changes no card. If a surface ever needs a true
# per-outcome price age, add the column AND re-budget the wire — do not quietly
# reinterpret this one.

#: Columns loaded for the related `Sport`.
SPORT_COLUMNS: tuple[str, ...] = ("key", "name")

#: Bumped whenever the tuples above change shape. It travels in the shared cache
#: key, so a deploy that changes the wire format cannot read a predecessor's
#: entries — they simply expire under their own TTL.
#:
#: CERT-615 [P2]: the version is necessary but NOT sufficient. A same-version
#: payload whose rows are the wrong shape used to be accepted by
#: `is_snapshot_payload` and then silently dropped row-by-row by `from_plain`,
#: so a corrupt entry read as "there are no candidate markets" rather than
#: "rebuild this" — an empty result reported as a fact (gotcha #53). Arity is
#: now validated per row, and a single bad row rejects the whole envelope.
#:
#: v2 — the rebase onto master, and the direction the two checks divide. The
#: columns grew: `image_width` / `image_height` were INSERTED after `image_url`
#: to keep the tuple in load-surface order, and `external_id` appended to the
#: outcome row. Arity alone would in fact catch THESE entries (27 values against
#: 29), but arity is not what makes the bump unnecessary — a future edit that
#: swaps or renames two same-width columns keeps the arity and changes the
#: MEANING of every position, and only the version stops that entry being read.
#: So: the version guards the shape a row CLAIMS, per-row arity guards the shape
#: it HAS, and neither is the other's backstop.
#:
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


def _is_value_tuple(values: Any, width: int) -> bool:
    """Whether `values` is a positional row of exactly `width` entries.

    Exactly, not at-least: `__init__` builds the attributes with `zip`, and
    `zip` TRUNCATES. A short row would therefore construct a snapshot whose
    trailing columns are silently absent rather than `None`, and reading one of
    them raises `AttributeError` inside the per-item serializer — which empties
    the whole futures pool (gotcha #42). A long row would carry a column this
    build has no name for. Both are corruption; neither is readable.
    """
    return isinstance(values, (list, tuple)) and len(values) == width


def _validated_rows(payload: Any) -> list | None:
    """The rows of a well-formed CURRENT-schema artifact, or `None`.

    The single validator behind both `is_snapshot_payload` and `from_plain`, so
    the two can no longer disagree about what "readable" means. CERT-615 [P2]:
    they did — the check accepted any same-version dict with a list of rows,
    while the rebuilder quietly dropped every row it could not unpack, so a
    corrupt envelope decoded to an empty pool and the route, having been told
    the payload was fine, served it.

    One bad row rejects the WHOLE payload rather than being skipped. A partial
    candidate base is not a cheaper answer than rebuilding — it is a feed
    missing markets nobody can see are missing.
    """
    if not isinstance(payload, dict) or payload.get("v") != SNAPSHOT_SCHEMA_VERSION:
        return None
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            return None
        market_values, outcome_rows, sport_values = row
        if not _is_value_tuple(market_values, len(MARKET_COLUMNS)):
            return None
        if not isinstance(outcome_rows, (list, tuple)):
            return None
        if any(not _is_value_tuple(o, len(OUTCOME_COLUMNS)) for o in outcome_rows):
            return None
        if sport_values is not None and not _is_value_tuple(
            sport_values, len(SPORT_COLUMNS)
        ):
            return None
    return rows


def from_plain(payload: Any) -> list[FuturesMarketSnapshot]:
    """Rebuild snapshots from the artifact `to_plain` produced.

    Returns `[]` for anything that is not a fully well-formed payload of this
    schema version — a shape the caller must treat as "build it yourself", never
    as "there are no candidate markets". The caller checks
    `is_snapshot_payload` before deciding; this function refuses rather than
    guesses, and the two now share `_validated_rows` so the check the caller
    makes is the check this function makes.
    """
    rows = _validated_rows(payload)
    if rows is None:
        return []
    out: list[FuturesMarketSnapshot] = []
    for market_values, outcome_rows, sport_values in rows:
        out.append(
            FuturesMarketSnapshot(
                market_values,
                [FuturesOutcomeSnapshot(o) for o in outcome_rows],
                SportSnapshot(sport_values) if sport_values is not None else None,
            )
        )
    return out


def is_snapshot_payload(payload: Any) -> bool:
    """Whether `payload` is a well-formed artifact of the CURRENT schema.

    "Well-formed" means every row too, not merely the envelope — see
    `_validated_rows`. `True` here is the caller's licence to use the decoded
    pool as the answer, so it has to mean the decode will be complete.
    """
    return _validated_rows(payload) is not None


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
