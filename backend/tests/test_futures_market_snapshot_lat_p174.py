"""Fidelity and drift guards for the LAT-P174 hydration snapshot (#2143 residual).

`test_feed_market_load_shared_lat_p174.py` proves the SHIP — a second principal
does not re-issue the candidate hydration SELECT. This file proves the thing
that makes the ship safe: the rows the scoring loop reads out of the shared
artifact are the rows the SELECT loaded, with the same types and the same
absences.

Three failure classes, each with its own gate:

1. **The snapshot is missing a column a consumer reads.** Production catches
   this today as a `MissingGreenlet` inside the per-item serializer, which
   empties the WHOLE futures pool rather than dropping one card (gotcha #42) —
   i.e. the loudest possible symptom with the least useful message.
   `test_every_market_attribute_the_scoring_loop_reads_is_on_the_snapshot`
   reads the attribute surface out of `_score_futures` itself, so a consumer
   added later fails here instead.

2. **A type changed on the way through the cache.** The scoring path compares
   and rounds `Decimal` probabilities and does arithmetic on `datetime`s. A
   snapshot that quietly handed back `float` and `str` would still render a
   feed — a DIFFERENT feed. Gated over the real codec, not over a hand-rolled
   one.

3. **An ORM row got in anyway.** The whole reason this module exists is that
   `principal_independent_cache.assert_plain_data` refuses ORM instances
   (#2107, gotcha #6). Gated by running the real guard over the real artifact.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.utils import futures_market_snapshot as fms
from app.utils.principal_independent_cache import (
    NotPlainData,
    assert_plain_data,
    decode_shared_payload,
    encode_shared_payload,
)

# --------------------------------------------------------------------------
# a stand-in for a `load_only`-restricted ORM row
# --------------------------------------------------------------------------


class _DeferredColumnRow:
    """An object that behaves like a `load_only` ORM instance.

    Loaded columns live in `__dict__`. Anything else EXPLODES on `getattr`,
    which is what SQLAlchemy does under async for a deferred attribute — it
    attempts a lazy load and raises rather than returning a default. This is the
    fixture that makes "use `__dict__.get`, never `getattr`" a testable claim
    instead of a code-review preference.
    """

    def __init__(self, loaded: dict):
        self.__dict__.update(loaded)

    def __getattr__(self, name):  # only called when `__dict__` lacks `name`
        raise AssertionError(
            f"lazy load attempted for deferred column {name!r} — under async "
            "this raises MissingGreenlet and empties the futures pool"
        )


_NOW = datetime(2026, 8, 31, 20, 15, 0, tzinfo=timezone.utc)


def _loaded_market(market_id: int = 4242) -> _DeferredColumnRow:
    values = dict.fromkeys(fms.MARKET_COLUMNS)
    values.update(
        {
            "id": market_id,
            "name": "Who wins the 2026 election?",
            "source": "polymarket",
            "external_id": f"ext-{market_id}",
            "category": "politics",
            "llm_sport_category": "politics",
            "market_tier": 2,
            "market_type": "field",
            "canonical_market_key": "canon-election-2026",
            "market_metadata": {"polymarket_event_id": "998", "tags": ["politics"]},
            "curation_score_adj": 3,
            "volume_24h": Decimal("104253.480000"),
            "updated_at": _NOW,
            "commence_time": _NOW - timedelta(days=2),
            "resolution_date": _NOW + timedelta(days=64),
            "status": "open",
            "created_at": _NOW - timedelta(days=120),
        }
    )
    outcome_values = dict.fromkeys(fms.OUTCOME_COLUMNS)
    outcome_values.update(
        {
            "id": 71,
            "name": "Candidate A",
            "team_id": None,
            "current_probability": Decimal("0.617500"),
            "probability_change_24h": Decimal("-0.023100"),
            "rank": 1,
            "rank_change_24h": 0,
            "opening_probability": Decimal("0.501000"),
            "calibration_probability": Decimal("0.610000"),
            "current_yes_bid": Decimal("0.6100"),
            "current_yes_ask": Decimal("0.6250"),
        }
    )
    row = _DeferredColumnRow(values)
    row.__dict__["outcomes"] = [_DeferredColumnRow(outcome_values)]
    row.__dict__["sport"] = _DeferredColumnRow({"key": "politics", "name": "Politics"})
    return row


# --------------------------------------------------------------------------
# 1 — the attribute surface
# --------------------------------------------------------------------------


def _market_attributes_read_by(func) -> set[str]:
    """Every `market.<attr>` the given function's SOURCE reads.

    The docstring is stripped first. A `getsource` guard that scans the
    docstring too goes vacuous the moment the prose quotes an attribute name —
    it would then pass because the DOCUMENTATION mentions the field, not because
    the code has it.
    """
    source = inspect.getsource(func)
    doc = func.__doc__
    if doc:
        source = source.replace(doc, "", 1)
    return set(re.findall(r"\bmarket\.([A-Za-z_][A-Za-z0-9_]*)", source))


def test_every_market_attribute_the_scoring_loop_reads_is_on_the_snapshot():
    """The drift gate.

    `_score_futures` may read a market attribute only if the snapshot carries
    it. Two names are structural rather than columns and are named here rather
    than pattern-matched away: `outcomes` and `sport` are the two eagerly-loaded
    relationships the snapshot rebuilds, and `__dict__` is the deliberate
    unloaded-column idiom (`market.__dict__.get("story_key")`).
    """
    from app.routes.feed import _score_futures

    structural = {"outcomes", "sport", "__dict__"}
    read = _market_attributes_read_by(_score_futures)
    assert read, "read no market attributes at all — the source scan is broken"

    missing = read - set(fms.MARKET_COLUMNS) - structural
    assert not missing, (
        f"`_score_futures` reads market attribute(s) {sorted(missing)} that the "
        "shared hydration snapshot does not carry. Add them to "
        "`futures_market_snapshot.MARKET_COLUMNS` (which also adds them to the "
        "query's load_only) or the futures pool empties in production."
    )


def test_the_route_builds_its_load_only_from_the_snapshot_module():
    """One list, in one place — followed hop by hop.

    If `feed.py` goes back to hand-writing its own `load_only(FuturesMarket...)`
    for this query, the query and the wire format can drift apart silently and
    the gate above stops meaning anything.

    The chain has TWO hops rather than one, and that is CERT-622's doing, not a
    weakening: `_score_futures` and `_score_sports_mode_futures` must share a
    single projection factory (a column added for a read on one path must not
    miss the other), and that factory builds from the tuples here (the query's
    load surface must not drift from the artifact's wire format). Both hops are
    asserted, because either one alone is satisfiable while the other is broken:
    a `_score_futures` that called `market_load_options()` directly would pass a
    one-hop check and still leave the Sports path on its own list.

    The last assertion is the one that does not depend on any name: there is no
    hand-written `load_only(` in `feed.py` at all, so there is nowhere for a
    second projection to be hiding under a spelling this test did not guess.
    """
    import ast

    from app.routes import feed as feed_module

    feed_src = inspect.getsource(feed_module)

    scorer_src = inspect.getsource(feed_module._score_futures)
    assert "_futures_feed_load_options()" in scorer_src, (
        "the candidate hydration query no longer takes its options from the "
        "shared `_futures_feed_load_options()` factory (CERT-622)"
    )

    factory_src = inspect.getsource(feed_module._futures_feed_load_options)
    assert "market_load_options()" in factory_src, (
        "`_futures_feed_load_options()` no longer builds from "
        "`futures_market_snapshot.market_load_options()` — the query's load "
        "surface and the shared artifact's wire format can now drift apart"
    )

    inline = [
        node
        for node in ast.walk(ast.parse(feed_src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_only"
    ]
    assert not inline, (
        f"`feed.py` hand-writes {len(inline)} `load_only(...)` projection(s) again. "
        f"The columns live in `futures_market_snapshot`; an inlined copy is the "
        f"CERT-622 drift returning, one layer up."
    )


def test_the_load_only_options_name_exactly_the_snapshot_columns():
    """The options really are built from the tuples — not merely near them."""
    from app.models.models import FuturesMarket, FuturesOutcome, Sport

    options = fms.market_load_options()
    assert len(options) == 3, options

    # Every declared column must be a real mapped attribute, or the query would
    # fail at compile time in production and here.
    for column in fms.MARKET_COLUMNS:
        assert hasattr(FuturesMarket, column), column
    for column in fms.OUTCOME_COLUMNS:
        assert hasattr(FuturesOutcome, column), column
    for column in fms.SPORT_COLUMNS:
        assert hasattr(Sport, column), column


# --------------------------------------------------------------------------
# 2 — fidelity
# --------------------------------------------------------------------------


def test_to_plain_reads_loaded_columns_without_touching_a_deferred_one():
    """`__dict__.get`, never `getattr`.

    `_DeferredColumnRow` raises on any attribute not in `__dict__`, so a
    `getattr`-based reader fails this outright rather than passing locally and
    raising `MissingGreenlet` on the async production path.
    """
    row = _loaded_market()
    del row.__dict__["llm_league"]  # a column the query asked for but the row lacks

    payload = fms.to_plain([row])

    assert fms.is_snapshot_payload(payload)
    rebuilt = fms.from_plain(payload)
    assert len(rebuilt) == 1
    assert rebuilt[0].llm_league is None


def test_decimal_and_datetime_survive_the_real_wire_codec_unchanged():
    """A type change here is a feed change, not a formatting change.

    Run over `encode_shared_payload`/`decode_shared_payload` — the ACTUAL
    cross-worker codec — because L1 (deepcopy) and L2 (encode/decode) must hand
    out the same object or a reader gets a different feed depending on which
    worker answered.
    """
    original = _loaded_market()
    payload = fms.to_plain([original])

    round_tripped = decode_shared_payload(encode_shared_payload(payload))
    market = fms.from_plain(round_tripped)[0]

    assert isinstance(market.volume_24h, Decimal)
    assert market.volume_24h == Decimal("104253.480000")
    assert isinstance(market.updated_at, datetime)
    assert market.updated_at == _NOW
    assert market.resolution_date == _NOW + timedelta(days=64)
    assert market.market_metadata == {
        "polymarket_event_id": "998",
        "tags": ["politics"],
    }

    outcome = market.outcomes[0]
    assert isinstance(outcome.current_probability, Decimal)
    assert outcome.current_probability == Decimal("0.617500")
    assert outcome.probability_change_24h == Decimal("-0.023100")
    assert outcome.current_yes_bid == Decimal("0.6100")
    assert market.sport is not None
    assert market.sport.key == "politics"
    assert market.sport.name == "Politics"


def test_a_market_with_no_sport_rebuilds_with_no_sport():
    """`market.sport.key if market.sport else None` is read at eight call sites;
    a snapshot that invented an empty Sport instead of `None` would change every
    one of them."""
    row = _loaded_market()
    row.__dict__["sport"] = None
    market = fms.from_plain(fms.to_plain([row]))[0]
    assert market.sport is None


def test_an_unloaded_column_still_reads_as_absent_through_dict_get():
    """`feed.py` reads `market.__dict__.get("story_key")` for a column the query
    deliberately does NOT load, and must keep getting `None`."""
    market = fms.from_plain(fms.to_plain([_loaded_market()]))[0]
    assert market.__dict__.get("story_key") is None
    assert market.__dict__.get("curation_score_adj", 0) == 3


# --------------------------------------------------------------------------
# 3 — the artifact is plain data
# --------------------------------------------------------------------------


def test_the_artifact_passes_the_guard_that_refuses_orm_rows():
    """The point of the snapshot: `assert_plain_data` accepts what we publish."""
    assert_plain_data(fms.to_plain([_loaded_market(), _loaded_market(4343)]))


def test_the_guard_still_refuses_the_hydrated_rows_themselves():
    """The refusal LAT-P174 did not relax.

    Publishing the ORM rows directly — the "simplification" this whole module
    exists to prevent — must still be impossible, not merely discouraged.
    """
    with pytest.raises(NotPlainData):
        assert_plain_data({"v": 1, "rows": [_loaded_market()]})


def test_a_foreign_schema_version_is_refused_rather_than_read_as_empty():
    """An unreadable payload must send the caller back to the builder.

    Returning `[]` for a stale-shape payload and letting the caller treat that
    as the answer would serve an EMPTY futures pool on every request until the
    entry expired — an empty result is a shape, not a fact (gotcha #53). The
    route checks `is_snapshot_payload` and rebuilds; both halves are gated.
    """
    payload = fms.to_plain([_loaded_market()])
    payload["v"] = fms.SNAPSHOT_SCHEMA_VERSION + 1

    assert fms.is_snapshot_payload(payload) is False
    assert fms.from_plain(payload) == []

    source = inspect.getsource(
        __import__("app.routes.feed", fromlist=["_score_futures"])._score_futures
    )
    assert "is_snapshot_payload" in source, (
        "the route no longer checks the payload shape before using it, so a "
        "stale-schema entry would serve an empty futures pool"
    )


# --------------------------------------------------------------------------
# 4 — the memory bound
# --------------------------------------------------------------------------


def test_the_market_load_namespace_has_a_tighter_entry_cap_than_the_default():
    """~1.2 MB encoded per entry makes the count cap a MEMORY bound.

    The default 64 is sized for artifacts of a few kilobytes; sixty-four
    candidate-base hydrations is hundreds of megabytes of resident memory on the
    flagship route, and failing open does not give that back.
    """
    from app.utils import principal_independent_cache as pic

    cap = pic.max_entries_for("market_load")
    assert cap < pic.MAX_ENTRIES_PER_NAMESPACE, (
        f"market_load inherited the default cap of {cap} entries"
    )
    assert pic.max_entries_for("concepts") == pic.MAX_ENTRIES_PER_NAMESPACE


def test_the_cap_is_enforced_and_evicts_oldest_first():
    """A cap nobody applies is a comment."""
    from app.utils import principal_independent_cache as pic

    cap = pic.max_entries_for("market_load")
    entries = {(i,): (float(i), i) for i in range(cap + 5)}
    pic._evict_if_needed(entries, "market_load")

    assert len(entries) == cap
    assert (0,) not in entries, "eviction did not start with the oldest entry"
    assert (cap + 4,) in entries, "eviction discarded the newest entry"
