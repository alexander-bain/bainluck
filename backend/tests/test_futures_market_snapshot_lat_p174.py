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

import ast
import inspect
import textwrap
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


class UnauditableMarketRead(AssertionError):
    """The scan met a read it cannot follow, so it must not report success.

    CERT-615 [P1] is the reason this class exists. The predecessor of this
    module scanned the source with `re.findall(r"\\bmarket\\.(\\w+)")`, which
    sees a literal `market.<attr>` and NOTHING else. The certifier put
    `market_alias = market; _ = market_alias.event_id` inside the scoring loop:
    all seventeen tests here stayed green while every candidate row raised
    `AttributeError`, the per-item catch skipped it, and `/api/feed` answered
    `200` with an empty futures pool. The guard was green about a mechanism that
    had been switched off.

    The lesson is not "widen the regex". It is that a scan which silently
    returns "nothing to report" for constructs it cannot parse is indistinguish-
    able from a scan that found nothing. So this analyser RAISES on anything it
    cannot resolve — a computed `getattr`, a callee it cannot find, a call
    signature it cannot bind. A guard that cannot see is required to say so.
    """


#: Builtins that provably read no mapped column off the object handed to them.
#: Deliberately tiny: every name here is a hole in the escape analysis, so the
#: bar is "reads the object's identity or type, never its attributes".
_ATTRIBUTE_FREE_BUILTINS = frozenset({"isinstance", "id", "type", "bool"})

#: Recursion bound for following the market into helper callees. Reaching it is
#: a failure, not a truncation — see `UnauditableMarketRead`.
_MAX_ESCAPE_DEPTH = 6


def _alias_names(tree: ast.AST, seed: str) -> set[str]:
    """Every local name that can hold the market object, seeded from `seed`.

    Deliberately flow-INSENSITIVE: a name that is ever assigned from an alias
    counts as an alias everywhere in the function, even on paths where it holds
    something else. That over-approximates, and over-approximation is the only
    safe direction for this guard — the worst it can do is demand a column the
    snapshot did not strictly need, which fails loudly and is fixed by adding
    the column. Under-approximating is what shipped an empty feed.
    """
    aliases = {seed}
    for _ in range(_MAX_ESCAPE_DEPTH):
        before = len(aliases)
        for node in ast.walk(tree):
            value = getattr(node, "value", None)
            if not isinstance(value, ast.Name) or value.id not in aliases:
                continue
            if isinstance(node, ast.Assign):
                aliases.update(
                    t.id for t in node.targets if isinstance(t, ast.Name)
                )
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(
                node.target, ast.Name
            ):
                aliases.add(node.target.id)
        if len(aliases) == before:
            break
    return aliases


def _reads_from_call(node: ast.Call, aliases: set[str], owner, seen, depth) -> set[str]:
    """Attributes reached through a call that receives the market object."""
    carried_pos = [
        i
        for i, arg in enumerate(node.args)
        if isinstance(arg, ast.Name) and arg.id in aliases
    ]
    carried_kw = [
        kw.arg
        for kw in node.keywords
        if isinstance(kw.value, ast.Name) and kw.value.id in aliases and kw.arg
    ]
    if not carried_pos and not carried_kw:
        return set()

    where = f"{owner.__qualname__}: `{ast.unparse(node)[:120]}`"
    name = node.func.id if isinstance(node.func, ast.Name) else None

    if name == "getattr":
        # The read the regex could never see. Five of these are live in
        # `_score_futures` today (`market_type`, `llm_league`, `llm_gender`,
        # `llm_level`, `id`) and the predecessor guard was blind to all five —
        # the certifier proved it by deleting `llm_gender` from MARKET_COLUMNS
        # and watching every test stay green.
        if (
            carried_pos == [0]
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            return {node.args[1].value}
        raise UnauditableMarketRead(
            f"{where} — a `getattr` on the market whose attribute name is not a "
            "string literal cannot be audited. Read the column directly, or "
            "this guard cannot promise the snapshot carries it."
        )

    if name in _ATTRIBUTE_FREE_BUILTINS:
        return set()

    if name is None:
        raise UnauditableMarketRead(
            f"{where} — the market escapes into a callee this scan cannot name. "
            "Bind it to a module-level function so the reads can be followed."
        )

    module = inspect.getmodule(owner)
    target = getattr(module, name, None)
    if not inspect.isfunction(target):
        raise UnauditableMarketRead(
            f"{where} — the market escapes into `{name}`, which does not resolve "
            f"to a function in `{getattr(module, '__name__', '?')}`. This scan "
            "will not report success about reads it cannot follow."
        )

    params = list(inspect.signature(target).parameters)
    out: set[str] = set()
    for index in carried_pos:
        if index >= len(params):
            raise UnauditableMarketRead(
                f"{where} — cannot bind positional argument {index} of `{name}`."
            )
        out |= _market_attributes_read_by(target, params[index], seen, depth + 1)
    for keyword in carried_kw:
        if keyword not in params:
            raise UnauditableMarketRead(
                f"{where} — cannot bind keyword `{keyword}` of `{name}`."
            )
        out |= _market_attributes_read_by(target, keyword, seen, depth + 1)
    return out


def _market_attributes_read_by(func, param: str = "market", seen=None, depth=0):
    """Every attribute of the market object `func` can read, transitively.

    Covers, and is tested below to cover: a direct `market.attr`, a read through
    a local alias, a `getattr` with a literal name, and a read inside any helper
    the market is passed to. Anything it cannot follow raises
    `UnauditableMarketRead` rather than being omitted.

    Working on the AST rather than the text also retires the docstring-vacuity
    problem structurally: prose that happens to mention `market.event_id` is a
    `Constant`, never an `Attribute`, so it cannot be mistaken for a read and
    there is nothing to strip.
    """
    if depth > _MAX_ESCAPE_DEPTH:
        raise UnauditableMarketRead(
            f"escape analysis exceeded depth {_MAX_ESCAPE_DEPTH} at "
            f"`{func.__qualname__}`; the market is being handed through too many "
            "layers for this guard to stay honest about what it reads."
        )
    seen = set() if seen is None else seen
    fingerprint = (func.__module__, func.__qualname__, param)
    if fingerprint in seen:  # recursion / diamond — already accounted for
        return set()
    seen.add(fingerprint)

    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    aliases = _alias_names(tree, param)

    attrs: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            attrs.add(node.attr)
        elif isinstance(node, ast.Call):
            attrs |= _reads_from_call(node, aliases, func, seen, depth)
    return attrs


def test_every_market_attribute_the_scoring_loop_reads_is_on_the_snapshot():
    """The drift gate.

    `_score_futures` may read a market attribute only if the snapshot carries
    it — and CERT-615 [P1] is why "reads" now means aliases, literal `getattr`,
    and helper callees rather than the literal token `market.`. Three names are
    structural rather than columns and are named here rather than pattern-
    matched away: `outcomes` and `sport` are the eagerly-loaded relationships
    the snapshot rebuilds, and `__dict__` is the deliberate unloaded-column
    idiom (`market.__dict__.get("story_key")`).
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


def test_the_drift_gate_sees_the_reads_the_regex_could_not():
    """The guard's own kill-proof — CERT-615 [P1], stated as a test.

    Each specimen is a construct the predecessor `re.findall(r"market\\.\\w+")`
    scan returned NOTHING for. If any of these stops being detected, the drift
    gate above is decorative again and an empty futures pool ships green.
    """

    def _via_alias(market):
        alias = market
        return alias.event_id

    def _via_walrus(market):
        return (alias := market) and alias.event_id

    def _via_literal_getattr(market):
        return getattr(market, "event_id", None)

    def _via_helper(market):
        return _reads_event_id_off(market)

    def _via_keyword(market):
        return _reads_event_id_off(candidate=market)

    for specimen in (
        _via_alias,
        _via_walrus,
        _via_literal_getattr,
        _via_helper,
        _via_keyword,
    ):
        assert "event_id" in _market_attributes_read_by(specimen), (
            f"the drift gate cannot see the read in `{specimen.__name__}` — this "
            "is exactly the blind spot that let CERT-615's mutation stay green"
        )


def test_the_drift_gate_refuses_rather_than_shrugs_at_what_it_cannot_follow():
    """A scan that returns "nothing" for what it cannot parse is a scan that
    always passes. These must RAISE, not come back empty."""

    def _computed_getattr(market):
        name = "event" + "_id"
        return getattr(market, name, None)

    def _unresolvable_callee(market):
        return market.helpers.dispatch(market)

    for specimen in (_computed_getattr, _unresolvable_callee):
        with pytest.raises(UnauditableMarketRead):
            _market_attributes_read_by(specimen)


def _reads_event_id_off(candidate):
    """Module-level helper for the escape-analysis specimens above.

    Module-level on purpose: the analyser resolves callees through the owning
    module's namespace, which is how it follows the market into
    `_futures_recycle_eligible`, `_should_skip_futures_for_recent_dismissal`
    and `_market_runtime_filter_trace` in `feed.py`.
    """
    return candidate.event_id


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


def _well_formed_payload() -> dict:
    """A payload that MUST validate — the positive control for everything below.

    Without it, a validator that refused literally everything would satisfy each
    refusal test in this section while emptying the feed on every request. Any
    zero needs a positive control (the array_agg lesson, in a different costume).
    """
    return fms.to_plain([_loaded_market(), _loaded_market(4343)])


def test_the_validator_accepts_the_payload_the_encoder_actually_produces():
    """The positive control. If this goes red, every refusal test below is
    vacuous and the shared cache never hits."""
    payload = _well_formed_payload()
    assert fms.is_snapshot_payload(payload) is True
    assert len(fms.from_plain(payload)) == 2


@pytest.mark.parametrize(
    "label,rows",
    [
        # The certifier's exact probe: a same-version envelope whose row is a
        # 2-tuple. `is_snapshot_payload` used to answer True and `from_plain`
        # used to skip it, so the route was told "readable" and handed nothing.
        ("row is not a triple", [["market-only", "missing-outcomes"]]),
        ("row is not a sequence", [{"market": []}]),
        # zip() TRUNCATES, so a short market row built a snapshot whose trailing
        # columns were absent rather than None — an AttributeError inside the
        # per-item serializer, i.e. the whole pool (gotcha #42).
        ("market row too short", [[[1, 2, 3], [], None]]),
        (
            "market row too long",
            [[[None] * (len(fms.MARKET_ROW_COLUMNS) + 1), [], None]],
        ),
        (
            "outcome row wrong width",
            [[[None] * len(fms.MARKET_ROW_COLUMNS), [[1, 2]], None]],
        ),
        (
            "outcomes is not a sequence",
            [[[None] * len(fms.MARKET_ROW_COLUMNS), "nope", None]],
        ),
        (
            "sport row wrong width",
            [[[None] * len(fms.MARKET_ROW_COLUMNS), [], ["key", "name", "extra"]]],
        ),
    ],
)
def test_a_same_version_malformed_payload_is_refused_rather_than_decoded_as_empty(
    label, rows
):
    """CERT-615 [P2].

    The version is necessary and not sufficient. Every shape here carries the
    CURRENT version, so nothing upstream of this check can tell it apart from a
    good entry — and each one used to decode to `[]`, which the route was
    entitled to serve as "there are no candidate markets". An empty result is a
    shape, not a fact (gotcha #53); the only correct answer is "rebuild".
    """
    payload = {"v": fms.SNAPSHOT_SCHEMA_VERSION, "rows": rows}
    assert fms.is_snapshot_payload(payload) is False, label
    assert fms.from_plain(payload) == [], label


def test_one_malformed_row_rejects_the_whole_payload_rather_than_being_skipped():
    """A partial candidate base is not a cheaper answer than a rebuild.

    Skipping the bad row would serve a feed silently missing markets — the
    failure nobody can see, which is strictly worse than the one that rebuilds.
    """
    payload = _well_formed_payload()
    assert len(payload["rows"]) == 2
    payload["rows"].append(["truncated"])

    assert fms.is_snapshot_payload(payload) is False
    assert fms.from_plain(payload) == [], (
        "the two good rows were decoded anyway; a corrupt artifact must send the "
        "caller back to the builder, not hand back a partial pool"
    )


def test_the_check_the_route_makes_is_the_check_the_rebuilder_makes():
    """The two used to disagree, and the disagreement WAS the defect.

    `is_snapshot_payload` said readable; `from_plain` then dropped rows. Pin
    them to one another over every specimen in this file so they cannot drift
    apart again.
    """
    specimens = [
        _well_formed_payload(),
        {"v": fms.SNAPSHOT_SCHEMA_VERSION, "rows": []},
        {"v": fms.SNAPSHOT_SCHEMA_VERSION, "rows": [["truncated"]]},
        {"v": fms.SNAPSHOT_SCHEMA_VERSION + 1, "rows": []},
        {"v": fms.SNAPSHOT_SCHEMA_VERSION, "rows": "not-a-list"},
        {"not": "a payload"},
        None,
        [],
    ]
    for payload in specimens:
        accepted = fms.is_snapshot_payload(payload)
        decoded = fms.from_plain(payload)
        expected = len((payload or {}).get("rows") or []) if accepted else 0
        assert len(decoded) == expected, (
            f"accepted={accepted} but decoded {len(decoded)} of {expected} rows "
            f"for {str(payload)[:80]!r} — the acceptance check and the decoder "
            "disagree, which is CERT-615 [P2] exactly"
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
