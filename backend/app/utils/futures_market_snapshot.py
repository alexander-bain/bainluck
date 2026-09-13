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

from datetime import timezone
from typing import Any, Iterable, Sequence

#: Columns loaded for `FuturesMarket` on the Discover futures candidate query.
#:
#: ORDER IS THE WIRE FORMAT — of the FIRST part of the market row. The row is
#: `MARKET_ROW_COLUMNS`: these loaded columns, then `DERIVED_MARKET_COLUMNS`.
#: This tuple alone is what `market_load_options()` projects, so it alone is the
#: load surface; nothing derived may be added here.
#:
#: A row is a positional list, not a dict, because the
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

# D1 clause a (#4066) wanted `opening_captured_at` HERE, on the outcome row —
# the day an opening price was taken, which is what turns "moved 37.5 points
# from opening" into a fact about a calendar. IT IS STILL REFUSED IN THIS
# TUPLE, on the same measurement as `last_updated` below and for the same
# reason: one timestamp per outcome, over 6,904 outcomes, grew the fixture's
# envelope from 2,928,973 B to 3,289,739 B (+12%) and the validator node count
# from 115,133 to 122,028. Every hard cap still passed with headroom; what
# failed is the pair of calibration tests that hold the fixture to the MEASURED
# production artifact, and re-deriving those constants from a fixture I had
# just changed would turn the file into a fixture testing itself — which is
# precisely the decoration LAT-P221 was written to end.
#
# Borrowing the market's own `created_at` as the date was measured as the cheap
# alternative and REFUSED on the data, not on taste: across the 93,481 top-5
# outcomes of open markets that carry an opening (production 2026-09-08),
# `opening_captured_at` sits within a day of `created_at` for only 80,483 of
# them (86%), a mean 4.41 days apart and a maximum of 214.9 days. Publishing
# `created_at` as "the opening date" would date one card in seven wrongly, some
# by months.
#
# 🟢 #4758 — THE BASELINE IS NOW BUILT, AND IT IS NEITHER OF THOSE TWO THINGS.
# The column is LOADED (`OUTCOME_LOAD_ONLY_EXTRA`) and folded at build time into
# ONE derived market value, `opening_baseline_at`, published only when every
# outcome of the market that carries a stamp carries the SAME one. That is what
# makes it exact rather than cheap: the fold cannot date an outcome by another
# outcome's stamp, because a market whose outcomes disagree publishes nothing
# and stays exactly as silent as it is today.
#
# MEASURED on production 2026-09-11, open markets with a future
# `resolution_date` that carry any stamp (30,944 markets): 26,310 (85.0%) have
# exactly one distinct `opening_captured_at` and are dated by this fold; 4,634
# disagree (mean spread 4.0 days, max 217.9) and are not. On the two-outcome
# markets — the yes/no shape whose copy is composed by
# `compose_binary_card_copy` — it is 13,886 of 14,196 (97.8%).
#
# The wire cost is one datetime per MARKET, not per outcome: +700 nodes on the
# LAT-P221 fixture (115,133 -> 115,833) against a 200,000 cap, and an envelope
# delta inside that file's +/-10% band. The +12% refusal above is what this is
# the alternative TO, and it is why the outcome tuple did not grow.

# ux/1070 item 5 wanted a price AGE, and `last_updated` is deliberately NOT in
# the outcome tuple above. It was added there once, and two guards in a row
# priced that decision: `test_feed_outcome_projection_cert622` demanded the
# projection grow (correct — an unprojected read is a MissingGreenlet inside the
# serializer), and then `test_feed_market_load_fits_the_shared_wire_lat_p221`
# measured the result at 3,361,009 B against a 2,928,973 B budget — a 15% growth
# in a shared Redis artifact, for one timestamp repeated across up to 193
# outcomes per market. That refusal stands.
#
# 🔴 WHAT DID **NOT** WORK, AND WHY IT IS WRITTEN HERE (CERT-949):
# the next attempt read `FuturesMarket.updated_at` instead — already loaded, one
# value per market, and measured on production 2026-09-04 within 0.4h of
# `max(outcome.last_updated)` on every row of the in-window population. The
# measurement was real and the inference from it was still wrong.
# `FuturesMarket.updated_at` is `onupdate=func.now()`: it means ANY write, and
# `app/tasks/enrich_markets.py` runs a SIX-HOURLY update of `hook_description` /
# `hook_generated_at` / `hook_leader_at_generation` / `market_metadata` that
# touches no price. So a market whose prices last moved in May reads as hours
# fresh — and it re-stamps exactly the stale markets the bound exists to
# exclude, because a stale market is the one whose hook keeps being regenerated.
# The defence offered at the time ("the threshold sits in a measured 6h–92h gap")
# does not survive the writer's own cadence being INSIDE that gap.
#
# So the signal is derived, not borrowed: `price_polled_at` below.

#: Outcome columns LOADED but never carried on the wire.
#:
#: The load surface is a superset of the wire format for exactly one reason, and
#: this is the whole of it: `price_polled_at` is folded out of these values at
#: BUILD time (`to_plain`), while the hydrated rows are still in hand, and the
#: per-outcome value itself never needs to reach a reader.
#:
#: The rule the wire format actually enforces is unchanged — anything the
#: SERIALIZER reads must be loaded AND carried, or the cached path serves `None`
#: where the direct path serves a value. Nothing downstream reads
#: `outcome.last_updated`; `test_my_stuff_price_freshness_cert949.py` pins that,
#: because reading it off a rebuilt snapshot is an `AttributeError` in the
#: per-item serializer, i.e. the whole futures pool (gotcha #42).
#:
#: MEASURED, and the measurement is why it is done this way (production
#: 2026-09-05, EXPLAIN ANALYZE, the ~700-id candidate set): a separate
#: `SELECT market_id, MAX(last_updated) … GROUP BY market_id` over the same ids
#: is a second bitmap heap scan of the same 9,220 rows and costs **423 ms warm**
#: — roughly 72% of the entire 588 ms `market_load` stage, on the flagship
#: route's cold build. Adding the column to the outcome SELECT that is already
#: fetching those rows is inside that statement's own run-to-run noise
#: (base 493/741/426 ms vs wide 531/242/292 ms, interleaved).
#:
#: `opening_captured_at` joins it for #4758, under the same rule and the same
#: economics: it is read once per market at BUILD time by
#: `_opening_baseline_at`, and the per-outcome value never needs to reach a
#: reader. It rides the outcome SELECT that is already fetching these rows, so
#: it is the free half of the measurement above, not a second query.
OUTCOME_LOAD_ONLY_EXTRA: tuple[str, ...] = ("last_updated", "opening_captured_at")

#: Market-level values that are COMPUTED for the artifact, not loaded from the
#: `futures_markets` row.
#:
#: `price_polled_at` is `MAX(FuturesOutcome.last_updated)` for the market — the
#: newest price-poll stamp across its outcomes, which is the question "are these
#: numbers current?" asked of the rows that actually hold the numbers. It is
#: derived because neither carrier alone can answer it: the market row's own
#: timestamps mean "any write" (see the note above), and the per-outcome column
#: costs 15% of a size-capped shared artifact to say one thing per market.
#:
#: These ride in the SAME positional row as `MARKET_COLUMNS`, appended after it —
#: see `MARKET_ROW_COLUMNS`. They are NOT in `MARKET_COLUMNS` for a mechanical
#: reason as well as a conceptual one: `market_load_options()` does
#: `getattr(FuturesMarket, c)` over that tuple, and there is no such attribute.
#:
#: The honest bound on what this measures: `last_updated` is written by the price
#: writers (`futures_price_refresh`, `kalshi`, `kalshi_ws`, `polymarket_ws`,
#: `tournament_price_refresh`) and also by the settlement writers in
#: `backfill_winners`. A settlement write therefore reads as a poll — which is a
#: far narrower overlap than "any write", and it lands on markets that have just
#: RESOLVED, i.e. the ones a `resolution_date`-in-the-future window already
#: excludes.
#: `opening_baseline_at` (#4758) is the market's single opening-capture instant
#: — the day "up 83 points since ___" is measured FROM — or `None` when its
#: outcomes do not agree on one. See the long note above `OUTCOME_COLUMNS` for
#: why it is folded to one value per market instead of carried per outcome, and
#: for the production coverage the fold buys.
#: `top_price_observed_at` (#5809) is `MIN(FuturesOutcome.last_updated)` over the
#: legs the CARD PRINTS — the newest stamp a card's own displayed prices can all
#: support. It rides here for exactly the reason its two neighbours do: the
#: per-outcome column costs 15% of a size-capped shared artifact, and the fold
#: needs the hydrated rows that only exist at build time. It is a SECOND value
#: rather than a redefinition of `price_polled_at` because the two answer
#: different questions for different consumers — see `_top_price_observed_at`.
DERIVED_MARKET_COLUMNS: tuple[str, ...] = (
    "price_polled_at",
    "opening_baseline_at",
    "top_price_observed_at",
)

#: The full positional market row on the wire: loaded columns, then derived ones.
#: Building/validating/rebuilding all go through this, so the appended block can
#: never drift out of position — and `market_load_options()` keeps using
#: `MARKET_COLUMNS` alone, which is still exactly the load surface.
MARKET_ROW_COLUMNS: tuple[str, ...] = MARKET_COLUMNS + DERIVED_MARKET_COLUMNS

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
#: v3 — `DERIVED_MARKET_COLUMNS` appended to the market row (`price_polled_at`,
#: CERT-949). The bump is not optional politeness: an in-flight v2 entry has a
#: market row one value SHORT, and the reader must not decide that every market
#: has an unknown price age for the life of that entry. Under v3 those entries
#: are simply never read and expire under their own TTL.
#:
#: v4 — `opening_baseline_at` appended to the same derived block (#4758), for
#: exactly the reason v3 was bumped: an in-flight v3 entry is one value short,
#: and reading it would tell the copy layer that no market on the cached path
#: has a dated opening while the build path knows the date — a DIFFERENT feed,
#: which is the failure this module exists to make impossible. Arity would in
#: fact reject those rows too (30 values against 31); the version is what makes
#: the rejection intentional rather than incidental.
#:
#: v5 — `top_price_observed_at` appended to the derived block (#5809), for the
#: third time and the same reason: an in-flight v4 entry is one value short, and
#: the failure it would cause is the SPECIFIC one this column ships to end. The
#: cached path would report "we cannot date this card" for every market it holds
#: while the build path knows the date, so a reader's age mark would blink in and
#: out with the cache rather than track the price — worse than either behaviour
#: on its own. Under v5 those entries are never read and expire under their TTL.
SNAPSHOT_SCHEMA_VERSION = 5


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
        # `MARKET_ROW_COLUMNS`, not `MARKET_COLUMNS`: the derived values are part
        # of the row and a snapshot that dropped them would report "price age
        # unknown" for every market on the cached path while the build path knew
        # it — a DIFFERENT feed, which is the failure this module exists to make
        # impossible.
        for name, value in zip(MARKET_ROW_COLUMNS, values):
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
            *(
                getattr(FuturesOutcome, c)
                for c in OUTCOME_COLUMNS + OUTCOME_LOAD_ONLY_EXTRA
            )
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


#: Read-only stand-in for the instance dict of a `__slots__` row, so the folds
#: below keep reading `__dict__` (never `getattr` — gotcha #42) on a carrier
#: that has no instance dict. Module-level and shared because it is never
#: written to; a fresh `{}` per outcome would allocate once per leg per fold.
_NO_INSTANCE_DICT: dict[str, Any] = {}


def _instance_dict(obj: Any) -> dict[str, Any] | None:
    """`obj.__dict__`, or `None` for a `__slots__` row that has none (#5778).

    🔴 `try`/`except AttributeError`, never the three-argument `getattr` form,
    and the distinction is not cosmetic. `test_feed_dead_market_clock_uxp251`
    asserts that call form never appears in `price_poll_stamp`, and it is right
    to assert the mechanism rather than the outcome: reaching `__dict__` that
    way is harmless in itself, but it is one edit from the same call on a
    MAPPED attribute, which lazy-loads and raises `MissingGreenlet` inside the
    per-item serializer — emptying the whole futures pool instead of dropping
    one card (gotcha #42). This form cannot become that one by accident.

    (Spelled without the open paren on purpose: the scan that pins this rule
    matches the call form as a substring, and a docstring is source too.)

    Extracted rather than inlined so `price_poll_stamp` and `_price_polled_at`
    answer the carrier question identically; the `None`-vs-`{}` distinction is
    the caller's, because only `price_poll_stamp` needs to tell "this row has
    no instance dict" from "it has one and the key is missing".
    """
    try:
        return obj.__dict__
    except AttributeError:
        return None


def _price_polled_at(outcomes: Iterable[Any]) -> Any:
    """`MAX(outcome.last_updated)` for one market, or `None` if it has no price.

    Folded here, at build time, off the hydrated rows — see
    `OUTCOME_LOAD_ONLY_EXTRA` for why this is not a second query and not a wire
    column. `__dict__.get`, never `getattr`, for this module's usual reason: a
    deferred attribute lazy-loads and raises `MissingGreenlet` on this async
    path. That also means a projection that stops loading the column degrades to
    `None` — "we do not know" — rather than to a wrong answer, and `None` is
    exclusion at every consumer.

    `_NO_INSTANCE_DICT` extends that same degradation to an outcome with no
    instance dict at all (#5778). `tennis_population.OutcomeRow` is a
    `__slots__` row carrying exactly `("name", "current_probability",
    "is_winner")` — the compact projection LAT-P146 caches — so it cannot hold
    `last_updated` no matter how it is read, and reading `o.__dict__` on it
    raised `AttributeError` through this fold. Contributing nothing is the
    correct answer for such a row and is the rule already stated above: an
    outcome with no stamp is ignored rather than treated as a disagreement.
    Note this is a genuine "we cannot date this", not a silent zero papering
    over a bug — the column is absent from the carrier BY DESIGN, and widening
    that cache row is latency's call, not this module's.
    """
    stamps = [
        stamp
        for stamp in (
            (_instance_dict(o) or _NO_INSTANCE_DICT).get("last_updated")
            for o in outcomes
        )
        if stamp is not None
    ]
    return max(stamps) if stamps else None


#: How many legs a Discover futures card PRINTS. `feed.py` slices
#: `card_outcomes[:3]` at both of its futures serializers, and
#: `test_card_price_age_fold_5809` scans that module for the literal so the two
#: cannot drift apart silently — a fold over more legs than the card shows
#: over-states the age, one over fewer under-states it, and #5809 is on record
#: that both directions are equally a lie to the reader.
CARD_PRICE_AGE_LEG_COUNT = 3


def _outcome_probability(outcome: Any) -> float:
    """An outcome's display probability as a sortable float; `-1.0` if unreadable.

    `__dict__.get`, never `getattr`, for this module's usual reason (gotcha
    #42). An outcome whose probability cannot be read sorts BELOW every one that
    can, so it is the first thing pushed out of the top-N window rather than
    something that can displace a leg the reader actually sees.
    """
    value = (_instance_dict(outcome) or _NO_INSTANCE_DICT).get("current_probability")
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1.0


def _top_price_observed_at(
    outcomes: Iterable[Any], leg_count: int = CARD_PRICE_AGE_LEG_COUNT
) -> Any:
    """`MIN(last_updated)` over the legs the CARD SHOWS, or `None` (#5809).

    `leg_count` DEFAULTS to the futures card's three and is passed explicitly
    only by the concept path, which shows one leg or two — see
    `concept_card_leg_count`. It is a parameter rather than two copies of this
    fold because the rule ("the oldest of what is displayed") is identical and
    only the window differs; what must never be shared is the *choice* of
    window, which is why no caller may pass a number it computed itself.

    ═══ WHY THIS EXISTS BESIDE `_price_polled_at` AND DOES NOT REPLACE IT ═══

    `price_polled_at` is `MAX` over ALL of a market's outcomes and answers "when
    did we last read this book" — which is the right question for a freshness
    bound over the whole market, and is what `my-stuff` and the dead-market clock
    consume. It is the WRONG question for the age mark under a card, and the
    difference is reader-visible: a card prints three probabilities, so an
    outcome nobody can see must not vouch for the ones they can.

    MEASURED on production `/api/feed?limit=40`, 2026-09-13 ~03:00Z, over the 38
    cards carrying the key: **1 card** served a stamp newer than EVERY price it
    displayed, and 3 served one more than an hour newer than the oldest price
    displayed. The specimen is market `108445`, "2028 Democratic presidential
    nominee" — 48 outcomes, 3 shown. Ossoff 17% / AOC 16% / Newsom 14% were all
    last observed `2026-09-12 03:51:10Z`, twenty-three hours old, and the served
    `price_observed_at` was byte-identical to the `last_updated` of Chris Van
    Hollen at 1%, who is not on the card. `PriceAgeMark` only draws above 30
    minutes, so the card computed ~0 and drew NOTHING: the disclosure went silent
    on exactly the card it exists for. Reach: 890 of 26,971 open markets (3.3%)
    carry a leader more than an hour behind their own market max, 503 by a day.

    ═══ WHY `MIN`, WHEN THE FUNCTION ABOVE TAKES `MAX` ═══

    The two are the same rule applied to different sets, not a disagreement —
    `heroFreshness`'s "max WITHIN a number, min ACROSS facts". Three displayed
    probabilities are three FACTS, each with its own observation time, and one
    mark speaks for all of them; the oldest is the only claim all three support.

    The `MAX` docstring defends itself with a real measurement — one market's
    fifth leg at 123 DAYS while its leader was 50 minutes old — and that concern
    survives here intact, but it is answered by the TOP-N FILTER rather than by
    `MAX`: a dead fifth leg is not in the top three, so it cannot date the card.
    What does not survive is that docstring's premise, that "a futures card's
    legs are one market's prices, written by one poll of one venue, so their
    stamps answer one question". Market `108445` has one leg written today and 47
    written yesterday. `last_updated` is a per-outcome TOUCH stamp (the model is
    explicit that it stays unconditional so stable prices do not drop out of the
    playoff grid, and `price_changed_at` carries change), and a poll only touches
    the outcomes it writes.

    ═══ THE RESIDUE, STATED RATHER THAN PAPERED OVER ═══

    Top-N-by-probability is a close PROXY for "displayed", not an identity.
    `feed.py` applies `_strip_mixed_binary_meta` and `drop_dominant_field_outcomes`
    before its slice, so on a card whose filters drop a high-probability leg the
    two sets diverge by one row and the fold can read a leg the card does not
    print. That cannot be closed on this carrier: the filters are feed-internal
    and the per-outcome column is deliberately off the wire (see
    `OUTCOME_LOAD_ONLY_EXTRA` — it was measured at +15% of a 2.9 MB size-capped
    shared artifact). Narrowing 48 legs to 3 is the whole of the available win;
    the last row of it is not reachable from here.

    An outcome with no stamp is IGNORED rather than treated as undatable, which
    is this module's rule everywhere (see `_opening_baseline_at`) and is also not
    a regression: `MAX` ignored it too. `None` when no displayed leg has a stamp
    — "we do not know", which every consumer reads as not-fresh (gotcha #53).
    """
    ranked = sorted(outcomes, key=_outcome_probability, reverse=True)
    stamps = [
        stamp
        for stamp in (
            (_instance_dict(o) or _NO_INSTANCE_DICT).get("last_updated")
            for o in ranked[:leg_count]
        )
        if stamp is not None
    ]
    return min(stamps) if stamps else None


def _opening_baseline_at(outcomes: Iterable[Any]) -> Any:
    """The market's one opening-capture instant, or `None` if it has no ONE.

    #4758. The copy layer needs to name the day a lifetime move is measured
    from — `format_baseline_date` in `feed_reasons`, and the branches gated on
    it — and until this fold existed there was no carrier for that day at all,
    so the dated sentence was unreachable and four of the fourteen bundle rows
    page one served on 2026-09-11 rendered with no caption whatsoever.

    🔴 THE UNANIMITY RULE IS THE WHOLE POINT, NOT A DEFENSIVE EXTRA. A market
    whose outcomes carry two different opening dates has no single answer to
    "since when?", and the two ways of pretending otherwise were both measured
    and both refused (see the note above `OUTCOME_COLUMNS`): borrowing
    `created_at` dates one market in seven wrongly, and picking one outcome's
    stamp for the whole market dates the OTHER outcomes by a day they were not
    captured on. Publishing nothing keeps such a market exactly as silent as it
    is today, which is the honest state and not a regression.

    Outcomes with no stamp are ignored rather than treated as a disagreement:
    the question is whether the stamps that EXIST agree, and a leg that was
    never stamped is not evidence that they do not.

    `__dict__.get`, never `getattr`, for this module's usual reason — a
    deferred attribute lazy-loads and raises `MissingGreenlet` on this async
    path (gotcha #42). A projection that stops loading the column therefore
    degrades to `None`, "we do not know", which is exclusion at every consumer.
    """
    stamps = {
        stamp
        for stamp in (o.__dict__.get("opening_captured_at") for o in outcomes)
        if stamp is not None
    }
    if len(stamps) != 1:
        return None
    return next(iter(stamps))


def opening_baseline_stamp(market: Any) -> Any:
    """`opening_baseline_at` for a market on EITHER carrier shape (#4758).

    The same two carriers as `price_poll_stamp`, in the same order and for the
    same reason: a market rebuilt by `from_plain` has the value already folded
    onto its row and outcomes that do not carry the column at all, while a
    market from a plain ORM query has no derived column and outcomes that DO
    carry it because `market_load_options()` projects it. Reading the folded
    value first and falling back to the fold makes each carrier authoritative
    exactly where it is the one that exists.

    A snapshot written by a pre-v4 build has neither, and reads `None` — but it
    cannot reach this function anyway, because the schema version rejects it.
    """
    state = market.__dict__
    if "opening_baseline_at" in state:
        return state["opening_baseline_at"]
    return _opening_baseline_at(state.get("outcomes") or [])


def price_poll_stamp(market: Any) -> Any:
    """`price_polled_at` for a market on EITHER carrier shape (UX-P251).

    The same value reaches a reader by two different routes and a caller must
    not have to know which one it holds:

    * a market rebuilt by `from_plain` carries the value ALREADY FOLDED, on the
      row, because `to_plain` reduced it at build time. Its outcomes do **not**
      carry `last_updated` — that column is `OUTCOME_LOAD_ONLY_EXTRA`,
      deliberately loaded and deliberately not on the wire — so re-deriving it
      from them there would read `None` off every outcome.
    * a market from a plain ORM query (`_score_sports_mode_futures`) has no
      derived column at all, because `price_polled_at` is not a database column;
      but its outcomes DO carry `last_updated`, because `market_load_options()`
      projects it.

    Reading the folded value first and falling back to the fold is therefore not
    a defensive `or` — it is the two carriers, in the order that makes each one
    authoritative where it is the one that exists.

    `_carrier_stamp` holds those branches (#5809) now that `top_price_stamp`
    needs the identical resolution for a different key; every branch there uses
    `__dict__.get`, never `getattr`, for this module's usual reason — a deferred
    attribute lazy-loads and raises `MissingGreenlet` on the async feed path,
    inside the per-item serializer, which empties the whole futures pool rather
    than dropping one card (gotcha #42). That also makes the degradation safe in
    the one case no branch covers — a market rehydrated from a snapshot written
    by an OLDER build, which has neither the derived key nor the outcome column:
    it reads `None`, "we do not know", never a wrong stamp.
    """
    return _carrier_stamp(market, "price_polled_at", _price_polled_at)


def top_price_stamp(market: Any) -> Any:
    """`top_price_observed_at` for a market on ANY carrier shape (#5809).

    `price_poll_stamp`'s twin, over the same three carriers and by the same
    delegation, for the value defined in `_top_price_observed_at`: the oldest
    observation among the legs the card PRINTS, rather than the newest across
    every leg the market has.

    The two are deliberately separate functions rather than one with a flag.
    They have different consumers — the dead-market clock and `my-stuff` want
    the market-wide bound, the age mark under a card wants the displayed one —
    and a single call site choosing between them by argument is how a later edit
    silently gives one consumer the other's answer.
    """
    return _carrier_stamp(market, "top_price_observed_at", _top_price_observed_at)


def _carrier_stamp(market: Any, key: str, fold: Any) -> Any:
    """One derived stamp off whichever of the three carriers `market` is.

    Extracted (#5809) so `price_poll_stamp` and `top_price_stamp` cannot drift
    on the carrier question, which is the part that is subtle and shared; what
    differs between them is only the wire key and the fold, and those are the
    arguments. Before this existed there was one such reader; a second copy of
    the three branches below would be the drift this module keeps a changelog
    about.
    """
    state = _instance_dict(market)
    if state is None:
        # THIRD CARRIER (#5778): a `__slots__` row. `tennis_population.MarketRow`
        # is "deliberately duck-type-identical to the ORM object it replaces" —
        # and it is, for every reader that uses attributes. This module does not:
        # it reads `__dict__` on purpose, and a slots class has no instance dict
        # at all, so both branches below raised `AttributeError` on it rather
        # than degrading (nine tennis tests, not a wrong number).
        #
        # Such a row can only ever hold the outcome carrier — there is no folded
        # `key` slot to read.
        #
        # 🔴 THE ATTRIBUTE READ BELOW IS SAFE, AND ONLY HERE. Touching
        # `.outcomes` on a mapped object is precisely what this module forbids:
        # it is a relationship, and on an unloaded one it emits IO and raises
        # `MissingGreenlet`. It cannot happen on this line, because this line is
        # only reachable when the object has NO instance dict — and every
        # SQLAlchemy-mapped instance has one. A slots row's `outcomes` is a
        # plain slot holding an already-materialised list; there is no loader
        # behind it to fire.
        #
        # An empty or absent `outcomes` (the row was never selected for the
        # page, which is exactly what the two-phase load leaves behind) folds to
        # `None`: "we do not know", the same honest degradation as every other
        # unreadable case here.
        try:
            outcomes = market.outcomes
        except AttributeError:
            return None
        return fold(outcomes or [])
    if key in state:
        return state[key]
    return fold(state.get("outcomes") or [])


def price_observed_at_iso(market: Any) -> str | None:
    """`price_poll_stamp` as a UTC ISO string, for a payload (#5778).

    The one way a market's price age reaches a reader. `price_poll_stamp`
    answers the carrier question and returns a `datetime`; this puts that
    datetime on the wire, and exists as a named function for two reasons that
    are not stylistic.

    ═══ THE OFFSET IS NOT OPTIONAL ═══

    A naive `isoformat()` carries no offset, and `Date.parse` reads an
    offsetless stamp as LOCAL time in the reader's browser — which ages a fresh
    price by the reader's own UTC offset and would print "3h ago" on a
    just-polled market in California. The two carriers hand back stamps that
    differ in `tzinfo` (a plain ORM row's column is naive; a `from_plain`
    rebuild's folded value is aware), so the normalisation has to happen
    somewhere, and doing it once here is what stops each caller getting it
    right separately.

    ═══ 🔴 NO APP CALL SITE TODAY, AND THAT IS DELIBERATE (#5809) ═══

    This shipped (#5778) as the one helper all seven concept adapters called.
    #5809 then moved every one of them to `concept_price_observed_at_iso`,
    because folding `MAX` over a MARKET answers a different question from "how
    old are the prices this CARD shows" — see that function for the filtering
    that makes the two sets genuinely different rather than merely differently
    computed.

    It is kept rather than deleted for one named consumer, not on general
    principle: `feed.py`'s `_card_price_observed_at` (#5752) is this exact rule
    open-coded on the futures serializers and should be collapsed onto this
    function. That collapse is not done here because those lines are inside a
    gated sha in the desk tray and rewriting them would invalidate it.

    So a reader finding this unused should NOT wire it back into a concept
    adapter — the guard in `test_concept_card_price_observed_at_5778` refuses
    that by name, and the refusal message says why.

    ═══ `None` IS AN ANSWER ═══

    `price_poll_stamp` already returns `None` for a market whose outcomes carry
    no stamp, and that propagates rather than being papered over: the reader
    draws nothing for a price we cannot date, which is honest, where a borrowed
    `created_at` would be a wrong stamp (gotcha #53 — "it returned" is not "it
    worked"). Serving the key with a null is the #2088 rule: null is "checked,
    and there is no stamp"; the key being ABSENT is "a payload built before
    this shipped".
    """
    stamp = price_poll_stamp(market)
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


#: A concept card that renders a BOUT prints both sides, so both are displayed
#: facts and the mark must speak for the older of them.
CONCEPT_BOUT_LEG_COUNT = 2
#: Every other concept card prints exactly one probability — `leader`, the
#: favourite — so exactly one price is displayed and nothing else may date it.
CONCEPT_LEADER_LEG_COUNT = 1
#: `_bout_from_competitors`' archetype gate, named here so this module and
#: `feed.py` cannot drift on it silently; the guard test scans both for it.
CONCEPT_BOUT_KIND = "co_equal_list"


def concept_card_leg_count(kind: Any, competitor_count: int) -> int:
    """How many prices a concept card DISPLAYS, given its envelope (#5809).

    ═══ WHY THIS IS NOT `CARD_PRICE_AGE_LEG_COUNT` ═══

    A futures card prints its top three outcomes. A concept card never prints
    three. `ConceptCard.tsx` renders exactly one of two things on its unsettled
    branch, and they are mutually exclusive in the source (`leader` is computed
    as `!whatHit && !bout && …`):

      * a BOUT — two names, two percentages, one row each; or
      * a LEADER — one big percentage and one name.

    So reusing the futures three here would date a concept card by two
    candidates it does not show. ux/1226 declined to ship that on exactly this
    reasoning, and it is worth restating why an over-statement is not the safe
    direction merely because it errs old: the mark's whole job is to tell a
    reader which numbers to trust. A card whose three-deep fold reaches a dead
    47th leg would print "priced 3 days ago" over two prices polled a minute
    ago — the disclosure firing when it should be silent, which teaches a reader
    to ignore it, and an ignored disclosure protects nobody on the card that
    needed it. Both directions are a lie; #5809 is on record about that.

    ═══ THE GATE MIRRORS `_bout_from_competitors`, DELIBERATELY ═══

    The bout is admitted by ARCHETYPE AND COUNT, not by count alone — a
    two-entry `winner_field` (a Grand Tour thinned to two riders, a golf major
    down to a final pair) stays an outright and prints one number. That is
    `_bout_from_competitors`' own rule and the copy here is the risk this
    function exists to concentrate: one place to read, one place to scan. The
    guard test asserts the two agree on all four corners of (kind, count).

    A count this function cannot trust degrades to the LEADER window, which is
    the narrow one: a wrong guess there dates the card by the single price it
    most certainly does display.
    """
    if kind == CONCEPT_BOUT_KIND and competitor_count == CONCEPT_BOUT_LEG_COUNT:
        return CONCEPT_BOUT_LEG_COUNT
    return CONCEPT_LEADER_LEG_COUNT


def concept_price_observed_at_iso(
    outcomes: Iterable[Any], kind: Any, competitor_count: int
) -> str | None:
    """When the prices a CONCEPT card displays were last polled (#5809).

    `price_observed_at_iso`' sibling for the concept envelope, and it takes
    OUTCOMES rather than a market on purpose. That is the whole correction.

    ═══ WHY NOT A MARKET ═══

    `price_observed_at_iso(market)` folds over `market.outcomes` — every leg the
    market has. A concept adapter's `competitors` list is NOT that set: every
    adapter filters it first, and the rows they drop are exactly the rows most
    likely to carry the extreme probability that a top-N-by-probability fold
    would then select. `event_cycling._real_outcomes` and the `_outcomes`
    closures in `event_awards` / `event_election` drop `is_field_outcome` names
    (the "Field" / "any other" catch-all, which on a 184-rider Grand Tour can
    out-price every named rider), `is_placeholder_outcome_name` rows, and rows
    with no probability at all; awards and election additionally cap at 40.

    So a fold over the MARKET can rank a leg the card never prints and date the
    card by it — which is #5809's own defect wearing a concept costume. Passing
    the adapter's already-filtered list means the fold ranks the same rows the
    reader sees, and the "is this the displayed set?" question is answered by
    construction at the call site instead of being re-derived here from data
    that no longer knows what was filtered.

    ═══ `None` IS AN ANSWER, AND TENNIS IS WHY IT HAS TO BE ═══

    An outcome carrying no `last_updated` contributes nothing, and a set in
    which none does folds to `None` — "we do not know", which every consumer
    reads as not-fresh (gotcha #53), never as fresh. `tennis_population`'s
    `OutcomeRow` is a `__slots__` row carrying exactly
    `("name", "current_probability", "is_winner")`, so tennis genuinely cannot
    date its prices and correctly discloses nothing; `_instance_dict` degrades
    it rather than raising. The call stays at that site for the reason #5778
    gave: if that row ever widens, the card lights up with no edit here.

    The UTC offset is applied here for the same reason `price_observed_at_iso`
    applies it — an offsetless stamp is parsed as LOCAL time by `Date.parse`,
    which would age a just-polled price by the reader's own offset.
    """
    stamp = _top_price_observed_at(
        outcomes, concept_card_leg_count(kind, competitor_count)
    )
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


def to_plain(markets: Iterable[Any]) -> dict[str, Any]:
    """Convert hydrated ORM markets into the shareable plain-data artifact.

    The result contains only `None`/`bool`/`int`/`float`/`str`/`datetime`/
    `Decimal` and lists of those — i.e. it passes `assert_plain_data`, which is
    what makes it eligible for the cross-worker cache at all. `Decimal` and
    `datetime` are carried AS THEMSELVES rather than normalised to float/str:
    the scoring path compares and rounds these values, and a snapshot that
    silently changed their type would change the feed.

    This is also where `DERIVED_MARKET_COLUMNS` are folded — the one moment in
    the request when the hydrated outcome rows exist and their price-poll stamps
    and opening-capture stamps can each be reduced to one value per market. A
    market with no outcomes, or one whose stamps are all `NULL`, gets `None`:
    "we do not know", which every consumer must read as not-fresh rather than
    fresh (gotcha #53), and which for `opening_baseline_at` also covers the
    market whose outcomes disagree about their opening day.
    """
    # Keyed by column NAME and read by name below, so a derived column added to
    # the tuple without a producer here is a `KeyError` at build time rather
    # than a row of the wrong width that the validator then rejects forever.
    producers = {
        "price_polled_at": _price_polled_at,
        "opening_baseline_at": _opening_baseline_at,
        "top_price_observed_at": _top_price_observed_at,
    }
    rows: list[list[Any]] = []
    for market in markets:
        state = market.__dict__
        outcomes = state.get("outcomes") or []
        sport = state.get("sport")
        rows.append(
            [
                _row(market, MARKET_COLUMNS)
                + [producers[name](outcomes) for name in DERIVED_MARKET_COLUMNS],
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
        if not _is_value_tuple(market_values, len(MARKET_ROW_COLUMNS)):
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
    "DERIVED_MARKET_COLUMNS",
    "MARKET_ROW_COLUMNS",
    "OUTCOME_COLUMNS",
    "SPORT_COLUMNS",
    "SNAPSHOT_SCHEMA_VERSION",
    "FuturesMarketSnapshot",
    "FuturesOutcomeSnapshot",
    "SportSnapshot",
    "market_load_options",
    "opening_baseline_stamp",
    "price_poll_stamp",
    "concept_card_leg_count",
    "concept_price_observed_at_iso",
    "to_plain",
    "from_plain",
    "is_snapshot_payload",
]
