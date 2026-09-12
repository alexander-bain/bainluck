"""#5778 — a concept card on the wire says WHEN its prices were last seen.

## The specimen

The FIRST card on Discover, 2026-09-12 22:5xZ: `Vuelta a España 2026`, a large
**96%** under a **LIVE** pill. Measured against production
(`futures_markets` × `futures_outcomes`, `MAX(last_updated)`), the 184-competitor
GC field behind that number was last priced **5h 01m** earlier; its siblings ran
to 15h 58m. Nothing on the card said so, and nothing on the card COULD say so —
`data.leader` is `{name, probability, movement_24h, field_size}` and there is no
stamp anywhere in the concept payload.

## What was actually missing

Not the value. `event_cycling._pick_winner_field` already folds
`max(o.last_updated for o in real)` over each candidate's outcomes in order to
RANK them by freshness, and then returns only the market — the freshness it
computed is dropped on the floor. Every non-golf adapter loads its outcomes with
a plain `selectinload(FuturesMarket.outcomes)`, so `price_poll_stamp` reads a
real stamp on all of them rather than the silent `None` a `load_only` projection
would produce. It needed a key, the same way #5752's futures card did.

## What this file proves, in the order it has to be proven

1. **The ISO wrapper answers on BOTH carriers and keeps its offset.** Same two
   carriers, same reason, as #5752: an offsetless stamp is parsed by the browser
   as LOCAL time and would age a fresh price by the reader's own UTC offset.
2. **Unknown stays unknown.** An undatable market serialises `None`, never
   "now"; the reader draws nothing rather than a stamp we cannot support.
3. **EVERY adapter carries the key.** This is the assertion the others cannot
   make. There are nine envelope-building sites across eight domain modules, and
   an absence-only suite passes on a deletion — so the census below is built
   from the AST of the shipping modules and asserts ADOPTION at every site that
   writes an `evolution_market_id`. A card that discloses its age on the cycling
   concept but not the F1 one is the defect, not half a fix.
4. **The card serves the key at the same name and level a futures card does**,
   so one `ActionBar` prop serves both and null-when-absent is preserved.

The assertions are labelled the way #5752's are:

    SHIP     red against the parent. This is the change.
    GUARD    green against the parent, red against a named mutant.
    CONTROL  green against both.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.futures_market_snapshot import price_observed_at_iso


NOW = datetime(2026, 9, 12, 22, 51, tzinfo=timezone.utc)
#: The specimen's own age — the Vuelta GC field under the `LIVE` pill.
FIVE_HOURS = NOW - timedelta(hours=5, minutes=1)


class _Outcome:
    """An outcome on the ORM carrier: the stamp lives in `__dict__`.

    A plain object rather than a MagicMock, for the reason `price_poll_stamp`'s
    own docstring gives: production reads `__dict__.get` because `getattr` on a
    deferred column lazy-loads and raises `MissingGreenlet` on the async path
    (gotcha #42). A mock answers every attribute and would make a `getattr`
    regression invisible in exactly this file.
    """

    def __init__(self, last_updated):
        self.last_updated = last_updated


class _Market:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _orm_market(*stamps) -> _Market:
    """The carrier every concept adapter holds: `selectinload`ed outcome rows."""
    return _Market(outcomes=[_Outcome(s) for s in stamps])


def _snapshot_market(folded) -> _Market:
    """The carrier `from_plain` rebuilds: the value is folded onto the row.

    Its outcomes carry `last_updated=None` on purpose — that column is
    `OUTCOME_LOAD_ONLY_EXTRA`, loaded and deliberately not on the wire — so a
    reader that re-derived from them would get `None` off every one.
    """
    return _Market(price_polled_at=folded, outcomes=[_Outcome(None), _Outcome(None)])


# ── 1. the ISO wrapper ──────────────────────────────────────────────────────


def test_ship_the_envelope_stamp_is_the_newest_poll():
    """SHIP: the helper exists and answers with the freshest stamp."""
    older = NOW - timedelta(hours=16)
    assert price_observed_at_iso(_orm_market(older, FIVE_HOURS, older)) == (
        FIVE_HOURS.isoformat()
    )


def test_ship_snapshot_carrier_reads_the_folded_value():
    """SHIP: a rehydrated market answers the same question, not `None`.

    Mutant this dies to: re-deriving from `outcomes` instead of reading the
    folded key first.
    """
    assert price_observed_at_iso(_snapshot_market(FIVE_HOURS)) == (
        FIVE_HOURS.isoformat()
    )


def test_guard_a_dead_leg_does_not_date_a_live_field():
    """GUARD: the fold is MAX, not MIN.

    A grand-tour GC field lists 184 riders as independent binaries and they are
    not all repriced together; the measured spread across the Vuelta's own
    markets on 2026-09-12 ran from 5h to 16h. Taking the oldest leg would date a
    card by whichever rider the venue has stopped quoting, which is the
    `heroFreshness` rule this ship shares with #5752: max WITHIN a number, min
    ACROSS facts.
    """
    dead = NOW - timedelta(days=123)
    assert price_observed_at_iso(_orm_market(dead, FIVE_HOURS)) == (
        FIVE_HOURS.isoformat()
    )


@pytest.mark.parametrize(
    "market",
    [
        pytest.param(_Market(outcomes=[]), id="no-outcomes"),
        pytest.param(_Market(outcomes=[_Outcome(None)]), id="unstamped-outcomes"),
        pytest.param(_Market(), id="no-outcomes-attribute-at-all"),
    ],
)
def test_guard_an_undatable_market_is_none_never_now(market):
    """GUARD: `None`, never a substituted "now".

    Gotcha #53 — "it returned" is not "it worked". A price we have never
    observed must not read as one observed a moment ago, and the renderer draws
    nothing for `None`.
    """
    assert price_observed_at_iso(market) is None


def test_guard_a_naive_stamp_is_serialised_with_an_offset():
    """GUARD: the offset is attached, not assumed.

    A naive `isoformat()` is read by `Date.parse` as LOCAL time, which ages a
    fresh price by the reader's own UTC offset — silently, and by a different
    amount per reader. The two carriers differ in `tzinfo` (a plain ORM column
    is naive; a folded value is aware), so this cannot be left to the caller.
    """
    naive = datetime(2026, 9, 12, 17, 50)
    out = price_observed_at_iso(_orm_market(naive))
    assert out is not None
    assert out.endswith("+00:00")
    assert datetime.fromisoformat(out) == naive.replace(tzinfo=timezone.utc)


# ── 1b. the third carrier ───────────────────────────────────────────────────
#
# Found by `test_tennis_population_lat_p146` rather than reasoned out: the
# premise "every adapter holds something `price_poll_stamp` can read" was FALSE,
# and nine tennis tests said so by raising `AttributeError` rather than by
# returning a wrong number. Both shapes are pinned here so the next person does
# not rediscover them from a stack trace.


class _SlotsOutcome:
    """`tennis_population.OutcomeRow`'s shape: slots, and no `last_updated`.

    The real row's slots are exactly `("name", "current_probability",
    "is_winner")`. It is not a degraded ORM object — it is a compact cached
    projection that never carried the column.
    """

    __slots__ = ("name", "current_probability", "is_winner")

    def __init__(self):
        self.name = "Player"
        self.current_probability = 0.5
        self.is_winner = False


class _SlotsMarket:
    """`tennis_population.MarketRow`'s shape: slots, with real `outcomes`."""

    __slots__ = ("id", "outcomes")

    def __init__(self, outcomes):
        self.id = 1
        self.outcomes = outcomes


def test_guard_a_slots_market_degrades_instead_of_raising():
    """GUARD: a `__slots__` row returns `None`; it does not raise.

    This module reads `__dict__` deliberately (gotcha #42), and a slots class
    has no instance dict — so the unguarded read raised `AttributeError` UP
    through the adapter and took the whole tennis concept page with it. Nine
    tests caught it. A helper whose failure mode is an exception inside a
    per-item serializer is the gotcha #42 shape this module exists to avoid.
    """
    assert price_observed_at_iso(_SlotsMarket([_SlotsOutcome()])) is None


def test_guard_a_slots_market_with_datable_outcomes_still_answers():
    """GUARD: the degradation is scoped to the CARRIER, not to slots markets.

    The mutant this kills: "a slots market has no stamp, return None" — which
    would be green on the tennis rows and silently wrong the day a slots-based
    market is handed real hydrated outcomes. The market's shape does not decide
    the answer; whether its OUTCOMES can be dated does.
    """
    assert price_observed_at_iso(_SlotsMarket([_Outcome(FIVE_HOURS)])) == (
        FIVE_HOURS.isoformat()
    )


def test_guard_a_market_with_an_instance_dict_is_never_touched_by_attribute():
    """GUARD: the slots branch is unreachable for anything SQLAlchemy maps.

    `test_feed_dead_market_clock_uxp251` scans `price_poll_stamp` for the word
    `getattr` — the right assertion, and it caught this change when the slots
    branch first read `getattr(market, "outcomes", None)`. A source scan can
    only see the word, though, and the hazard is the MECHANISM: reading
    `.outcomes` on a mapped object emits IO and raises `MissingGreenlet` inside
    the per-item serializer, emptying the whole futures pool (gotcha #42).

    So this asserts the mechanism directly. The market below has a real
    instance dict and a `outcomes` PROPERTY that raises the way an unloaded
    relationship does. If the fold ever reaches it by attribute, this test
    raises instead of returning — which no string scan could tell you.
    """

    class _Exploding:
        """An unloaded relationship: present on the class, fatal to touch."""

        def __init__(self):
            self.__dict__["price_polled_at"] = FIVE_HOURS

        @property
        def outcomes(self):  # pragma: no cover - reaching this IS the failure
            raise AssertionError(
                "price_poll_stamp touched `.outcomes` by attribute on a market "
                "that has an instance dict — on a real mapped row that is a "
                "lazy load and a MissingGreenlet inside the serializer"
            )

    assert price_observed_at_iso(_Exploding()) == FIVE_HOURS.isoformat()


def test_guard_the_carrier_helper_does_not_reintroduce_getattr():
    """GUARD: the rule survives being factored out of `price_poll_stamp`.

    The upstream scan reads `price_poll_stamp`'s source only, so moving the
    `__dict__` read into a helper would slip past it — which would be dodging
    the guard rather than satisfying it. This extends the same assertion to
    the helper the read now lives in.
    """
    from app.utils import futures_market_snapshot as snap

    src = inspect.getsource(snap._instance_dict)
    assert "getattr(" not in src, (
        "_instance_dict must reach __dict__ by try/except, not getattr — one "
        "edit from a getattr on a mapped column (gotcha #42)"
    )


def test_control_a_missing_market_degrades_rather_than_raising():
    """CONTROL: `None` in, `None` out — soccer's arm with no winner market.

    Recorded because a mutant SURVIVED here and the survivor is honest: deleting
    soccer's `if winner_market is not None` guard changes no output, since a
    `None` market has no instance dict, falls to the outcome branch, and folds
    an empty list. The explicit guard beside `evolution_market_id` is therefore
    readability, not behaviour — and this test is what says so, so nobody
    "fixes" the equivalence by inventing an assertion that only the guard can
    pass.
    """
    assert price_observed_at_iso(None) is None


def test_control_the_tennis_carrier_still_cannot_date_a_price():
    """CONTROL: tennis serves null BECAUSE of the slot list, not because of a bug.

    If `last_updated` is ever added to `OutcomeRow`, this fails — and that is
    the point. It is the one signal that the tennis concept card can start
    disclosing its age, and it fails LOUDLY rather than leaving a permanent
    silent null nobody revisits.
    """
    from app.utils.tennis_population import OutcomeRow

    assert "last_updated" not in OutcomeRow.__slots__, (
        "OutcomeRow now carries `last_updated` — tennis can date its prices; "
        "drop the null note at event_tennis.py's `price_observed_at` and "
        "re-measure the card"
    )


# ── 2. the adoption census ──────────────────────────────────────────────────
#
# The assertion nothing else in this file can make. An absence-only suite is
# green after the key is deleted from ONE adapter, which is precisely the drift
# this ship exists to prevent — so the population is read out of the shipping
# modules' AST rather than listed by hand here.

#: Every module that builds a concept envelope. Listed rather than globbed so a
#: NEW domain adapter that forgets the key is caught by the count assertion
#: below instead of quietly widening the population it is measured against.
ADAPTER_MODULES = (
    "event_cycling",
    "event_f1",
    "event_election",
    "event_awards",
    "event_soccer",
    "event_tennis",
    "event_combat",
    "event_concept",
)

#: Nine `primary` dicts across the eight modules — combat builds two (a card
#: with a priced main event and one with no futures market yet).
EXPECTED_ENVELOPE_SITES = 9


def _utils_dir() -> Path:
    import app.utils as utils_pkg

    return Path(utils_pkg.__file__).parent


#: The three sites that legitimately write a bare `None` — named, so the
#: exclusion is a decision on the record and not an accident. Golf maps plain
#: data with no market object; combat's second envelope has no futures market at
#: all; soccer's arm guards a `winner_market` that may be absent.
NULL_ALLOWED_SITES = {
    ("event_concept", "golf maps routes/golf.py plain data — no market object"),
    ("event_combat", "the no-futures-market branch has no price to date"),
}


def _envelope_dicts() -> list[tuple[str, int, set[str]]]:
    """Every dict literal in the adapters that writes `evolution_market_id`.

    `evolution_market_id` is the anchor because it is the key that MAKES a dict
    the `primary` of a concept envelope — it is not written anywhere else in
    these modules, and a new adapter cannot build a chartable envelope without
    it. Keyed off a string constant read from the AST, never off the prose in a
    comment.
    """
    found: list[tuple[str, int, set[str]]] = []
    for name in ADAPTER_MODULES:
        path = _utils_dir() / f"{name}.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            if "evolution_market_id" in keys:
                found.append((name, node.lineno, keys))
    return found


def test_guard_every_concept_adapter_writes_the_key():
    """GUARD: ADOPTION, not absence — the mutant is deleting ONE adapter's key.

    Without this, removing `price_observed_at` from `event_f1` leaves every
    other test in this file green and ships a feed where a cycling card
    discloses its price age and an F1 card does not.
    """
    sites = _envelope_dicts()
    missing = [
        f"{module}.py:{lineno}"
        for module, lineno, keys in sites
        if "price_observed_at" not in keys
    ]
    assert not missing, (
        "concept envelope `primary` built without `price_observed_at` at: "
        + ", ".join(missing)
    )


def test_guard_the_census_still_sees_every_site():
    """GUARD: the scan above is not passing because it found nothing.

    A source scan whose population silently drops to zero is green and vacuous.
    This pins the count, so a renamed module or a refactor that moves an
    envelope out of these files fails LOUDLY here rather than shrinking the
    thing the adoption test measures.
    """
    sites = _envelope_dicts()
    assert len(sites) == EXPECTED_ENVELOPE_SITES, (
        f"expected {EXPECTED_ENVELOPE_SITES} concept envelope sites, found "
        f"{len(sites)}: {[(m, ln) for m, ln, _ in sites]}"
    )
    assert {m for m, _, _ in sites} == set(ADAPTER_MODULES)


def _price_value_at_each_site() -> list[tuple[str, int, str]]:
    """`(module, lineno, kind)` for the VALUE each envelope gives the key.

    `kind` is one of `helper` (a call to `price_observed_at_iso`), `none` (the
    literal `None`), or `other`. Read from the AST rather than by string search
    because the question is what the expression IS, not whether the module
    happens to mention the helper somewhere — an import line alone satisfies a
    substring test while every call site writes `None`.
    """
    out: list[tuple[str, int, str]] = []
    for module, lineno, _keys in _envelope_dicts():
        path = _utils_dir() / f"{module}.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict) or node.lineno != lineno:
                continue
            for key, value in zip(node.keys, node.values):
                if not (
                    isinstance(key, ast.Constant) and key.value == "price_observed_at"
                ):
                    continue
                out.append((module, lineno, _classify(value)))
    return out


def _classify(value: ast.expr) -> str:
    """What kind of expression answers the key — unwrapping a guarded arm.

    Soccer writes `helper(m) if m is not None else None`, which is the helper
    doing its job behind a presence check, not a null site. An `IfExp` is
    therefore classified by its non-`None` branch.
    """
    if isinstance(value, ast.IfExp):
        branches = [value.body, value.orelse]
        real = [
            b
            for b in branches
            if not (isinstance(b, ast.Constant) and b.value is None)
        ]
        return _classify(real[0]) if len(real) == 1 else "other"
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return "helper" if name == "price_observed_at_iso" else "other"
    if isinstance(value, ast.Constant) and value.value is None:
        return "none"
    return "other"


def test_guard_every_site_is_wired_to_the_helper_or_a_named_null():
    """GUARD: the key is not merely PRESENT, it is CONNECTED.

    The mutant this exists for survived the key-presence census above:
    replacing `price_observed_at_iso(winner)` with `None` in one adapter leaves
    the key in place, leaves the module's import line in place — so a substring
    test for the helper's name still passes — and silently stops that domain
    disclosing anything. Only reading the VALUE catches it.

    Two sites may legitimately answer `None` and both are named in
    `NULL_ALLOWED_SITES`; any OTHER null is this mutant.
    """
    sites = _price_value_at_each_site()
    assert len(sites) == EXPECTED_ENVELOPE_SITES, (
        "the value scan lost sites relative to the key scan — it is measuring "
        f"a different population: {sites}"
    )

    null_modules = sorted(m for m, _ln, kind in sites if kind == "none")
    assert null_modules == sorted(m for m, _why in NULL_ALLOWED_SITES), (
        "an adapter answers `price_observed_at` with a bare `None` that is not "
        f"on the named-exception list: {null_modules}"
    )

    other = [(m, ln) for m, ln, kind in sites if kind == "other"]
    assert not other, (
        f"`price_observed_at` is neither the shared helper nor a named null at: {other}"
    )

    helper_modules = {m for m, _ln, kind in sites if kind == "helper"}
    assert helper_modules == {
        "event_cycling",
        "event_f1",
        "event_election",
        "event_awards",
        "event_soccer",
        "event_tennis",
        "event_combat",
    }, f"the set of adapters calling the shared helper changed: {helper_modules}"


# ── 2b. the card itself ─────────────────────────────────────────────────────


def test_guard_the_concept_card_lifts_the_key_to_the_top_level():
    """GUARD: the wire dict carries it, at the level a futures card does.

    Another survivor that the adapter census could never catch: every envelope
    can carry the stamp perfectly and the CARD can still drop it on the floor.
    Deleting the key from the concept card's data dict left all fourteen of the
    other assertions in this file green.

    The level matters as much as the key. `#5752` puts `price_observed_at` at
    the top of a futures card's `data`, so `ConceptCard` and `FuturesCard` pass
    the SAME `ActionBar` prop from the SAME path; nesting it under `leader`
    would work until a card has no leader, which is the case the null exists
    for. Anchored on `marquee_whathit`, which only the concept card writes.
    """
    import app.routes.feed as feed_module

    tree = ast.parse(
        Path(inspect.getfile(feed_module)).read_text(), filename="feed.py"
    )
    concept_dicts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(
            isinstance(k, ast.Constant) and k.value == "marquee_whathit"
            for k in node.keys
        )
    ]
    assert concept_dicts, "the concept card's data dict was not found in feed.py"

    carrying = [
        d
        for d in concept_dicts
        if any(
            isinstance(k, ast.Constant) and k.value == "price_observed_at"
            for k in d.keys
        )
    ]
    assert carrying, (
        "the concept card's data dict does not write `price_observed_at` — the "
        "envelope can carry the stamp and the card still drops it"
    )


# ── 3. the two facts stay two facts ─────────────────────────────────────────


def test_control_the_key_is_not_as_of_under_a_new_name():
    """CONTROL: `price_observed_at` is not `event.as_of`.

    `as_of` is when LIVE LEADERBOARD data was fused into the envelope; this is
    when the PRICES were polled. They are different clocks on different
    pipelines, and the golf adapter — the one that has an `as_of` and no market
    object — is exactly where borrowing one for the other would be tempting and
    wrong.
    """
    from app.utils import event_concept

    source = inspect.getsource(event_concept)
    assert '"as_of": None' in source, "the golf envelope's own as_of moved"
    assert '"price_observed_at": None' in source, (
        "the golf envelope must answer the key with a null, not omit it"
    )
    # The two must not have been collapsed onto one expression.
    assert '"price_observed_at": data.get("as_of")' not in source
    assert '"as_of": data.get("price_observed_at")' not in source
