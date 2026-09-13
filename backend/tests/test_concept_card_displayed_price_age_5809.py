"""#5809, concept half — a concept card's age mark describes the prices it SHOWS.

═══ WHAT WAS WRONG ═══

#5778 gave every concept envelope a `price_observed_at`, folded by
`price_observed_at_iso(market)` — `MAX(last_updated)` over every outcome the
market has. A concept card does not print every outcome. `ConceptCard.tsx`
renders exactly one of two things on its unsettled branch, and they are
mutually exclusive in the source (`leader` is computed as `!whatHit && !bout`):

  * a BOUT — two names, two percentages; or
  * a LEADER — one big percentage, one name.

So the stamp could be newer than every price on the card, and `PriceAgeMark`
only draws above 30 minutes — the disclosure goes silent on exactly the card it
exists for. That is the same defect #5809 fixed on the futures serializers,
reaching the concept surface by a different route.

═══ TWO THINGS THAT MAKE THIS NOT A COPY OF THE FUTURES FIX ═══

1. **The leg count is per-surface.** The futures card's `CARD_PRICE_AGE_LEG_COUNT`
   is 3. A concept card shows 1, or 2 in a bout. Reusing 3 would OVER-state the
   age, which is not the safe direction merely because it errs old: a mark that
   fires when it should be silent teaches a reader to ignore it.

2. **The displayed set is FILTERED, so a market-level fold is not merely coarse —
   it ranks rows that do not exist for the reader.** Every adapter drops the
   `is_field_outcome` catch-all ("Field" / "any other"), placeholder names, and
   null-probability rows before building `competitors`; awards and election also
   cap at 40, soccer at `_COMPETITOR_CAP`. On a 184-way independent-binary Grand
   Tour field (gotcha #23) the dropped catch-all can out-price every named rider,
   so a top-N-by-probability fold over `market.outcomes` would select it FIRST.
   That is why the helper takes OUTCOMES — the adapter's own filtered list —
   rather than a market.

═══ MEASURED, 2026-09-13 ~04:30Z ═══

The live concept slate carried 12 cards (`/api/feed?limit=250`): 1 cycling
(Vuelta GC, 184-rider field, leader displayed), 1 F1 (Spanish GP, 22), 10 UFC
bouts. Their chosen markets were all Kalshi and all UNIFORMLY stamped — every
leg written in one poll — so this fix is a no-op on that slate and there is no
natural specimen to photograph. That is a property of today's cards, NOT of the
class: over the oldest 2,000 open markets, **256 of 1,785 Kalshi markets (14.3%)
and 132 of 204 Polymarket markets (64.7%) have a non-zero spread** between their
oldest and newest leg. A newest-2,000 slice reads 0.0% for Kalshi, which is the
sampling trap this note exists to record — the freshly-polled end of the table
is uniform by construction.

So every specimen below is MANUFACTURED, deliberately: a defect that has no
natural specimen today still has to be pinned before the slate rotates onto it.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.futures_market_snapshot import (
    CONCEPT_BOUT_KIND,
    CONCEPT_BOUT_LEG_COUNT,
    CONCEPT_LEADER_LEG_COUNT,
    concept_card_leg_count,
    concept_price_observed_at_iso,
)

NOW = datetime(2026, 9, 13, 4, 0, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(minutes=2)
STALE = NOW - timedelta(hours=23)
ANCIENT = NOW - timedelta(days=123)


class _Outcome:
    """An ORM-shaped outcome: a real instance dict, which is what the fold reads."""

    def __init__(self, name: str, probability, last_updated):
        self.name = name
        self.current_probability = probability
        self.last_updated = last_updated


class _SlotsOutcome:
    """`tennis_population.OutcomeRow`'s shape — no instance dict, no stamp."""

    __slots__ = ("name", "current_probability", "is_winner")

    def __init__(self, name="Alcaraz", probability=0.6):
        self.name = name
        self.current_probability = probability
        self.is_winner = False


# ---------------------------------------------------------------------------
# The leg-count rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,count,expected",
    [
        # The bout: the archetype AND the count, which is `_bout_from_competitors`'
        # own gate. All four corners are asserted so neither half can be dropped.
        (CONCEPT_BOUT_KIND, 2, CONCEPT_BOUT_LEG_COUNT),
        (CONCEPT_BOUT_KIND, 3, CONCEPT_LEADER_LEG_COUNT),
        (CONCEPT_BOUT_KIND, 1, CONCEPT_LEADER_LEG_COUNT),
        # 🔴 A two-entry `winner_field` stays an OUTRIGHT and prints ONE number —
        # a Grand Tour thinned to two riders, a major down to a final pair. This
        # is the corner that a count-only gate gets wrong, and "0 fights on the
        # card" was an earlier version of exactly that mistake.
        ("winner_field", 2, CONCEPT_LEADER_LEG_COUNT),
        ("winner_field", 184, CONCEPT_LEADER_LEG_COUNT),
        # An unreadable kind degrades to the NARROW window, never the wide one.
        (None, 2, CONCEPT_LEADER_LEG_COUNT),
        ("", 2, CONCEPT_LEADER_LEG_COUNT),
    ],
)
def test_leg_count_mirrors_the_bout_admission_gate(kind, count, expected):
    assert concept_card_leg_count(kind, count) == expected


def test_the_leg_count_is_never_the_futures_three():
    """The whole reason this rule exists rather than reusing the futures one."""
    from app.utils.futures_market_snapshot import CARD_PRICE_AGE_LEG_COUNT

    assert CARD_PRICE_AGE_LEG_COUNT == 3
    for kind, count in [(CONCEPT_BOUT_KIND, 2), ("winner_field", 184), ("x", 1)]:
        assert concept_card_leg_count(kind, count) < CARD_PRICE_AGE_LEG_COUNT


# ---------------------------------------------------------------------------
# THE SPECIMEN: a stale leader behind a fresh sibling
# ---------------------------------------------------------------------------


def test_the_hidden_fresh_sibling_no_longer_dates_the_card():
    """THE SHIP. A leader priced 23h ago, one invisible sibling polled 2m ago.

    Shaped on the production specimen #5809 was filed from (market 108445: the
    displayed top rows 23h old, the served stamp taken from a 1% candidate who
    is not on the card) — but at a concept card's leg count, where only the
    LEADER is displayed.

    Before: `MAX` over all legs = `FRESH` ⇒ the card computes ~2 minutes, which
    is under `PriceAgeMark`'s 30-minute floor, so it draws NOTHING.
    After: the leader's own stamp ⇒ 23 hours, and the mark draws.
    """
    outcomes = [
        _Outcome("Enric Mas Nicolau", 0.955, STALE),  # the one the card prints
        _Outcome("Felix Gall", 0.04, FRESH),  # invisible, and 23h newer
        _Outcome("Richard Carapaz", 0.04, FRESH),
    ]
    assert concept_price_observed_at_iso(
        outcomes, "winner_field", len(outcomes)
    ) == STALE.isoformat()


def test_the_control_a_stale_hidden_sibling_does_not_age_a_fresh_leader():
    """THE OPPOSITE-CONDITION CONTROL — the confounder run BACKWARDS.

    The test above passes for a fold that simply takes `MIN` over EVERYTHING,
    which would be a different (and wrong) fix: it would let a dead 123-day leg
    date a card whose displayed price is 2 minutes old — over-stating the age,
    the failure direction the futures docstring measured and refused.

    Only a fold windowed to the DISPLAYED rows passes both this and the one
    above, so the pair pins the top-N filter rather than the `MIN`.
    """
    outcomes = [
        _Outcome("Enric Mas Nicolau", 0.955, FRESH),  # displayed, fresh
        _Outcome("Someone Retired", 0.001, ANCIENT),  # invisible, 123 days dead
    ]
    assert concept_price_observed_at_iso(
        outcomes, "winner_field", len(outcomes)
    ) == FRESH.isoformat()


def test_a_bout_is_dated_by_the_older_of_the_two_sides_it_prints():
    """Both sides are displayed facts, so one mark must support BOTH.

    `heroFreshness`' rule — max WITHIN a number, min ACROSS facts. Two printed
    percentages are two facts.
    """
    outcomes = [
        _Outcome("Thomas Gantt", 0.99, FRESH),
        _Outcome("Drakkar Klose", 0.01, STALE),
    ]
    assert concept_price_observed_at_iso(
        outcomes, CONCEPT_BOUT_KIND, 2
    ) == STALE.isoformat()


def test_a_two_entry_winner_field_is_dated_by_its_leader_alone():
    """The corner the archetype gate exists for, asserted on the VALUE.

    Same two outcomes as the bout above; only the `kind` differs. A
    `winner_field` prints one number, so the runner-up's older stamp must NOT
    reach the mark — which is the reverse of the assertion directly above, on
    byte-identical data.
    """
    outcomes = [
        _Outcome("Enric Mas Nicolau", 0.99, FRESH),
        _Outcome("Felix Gall", 0.01, STALE),
    ]
    assert concept_price_observed_at_iso(
        outcomes, "winner_field", 2
    ) == FRESH.isoformat()


# ---------------------------------------------------------------------------
# "Absent means unknown, never fresh"
# ---------------------------------------------------------------------------


def test_no_stamp_anywhere_is_unknown_not_fresh():
    outcomes = [_Outcome("A", 0.9, None), _Outcome("B", 0.1, None)]
    assert concept_price_observed_at_iso(outcomes, "winner_field", 2) is None


def test_an_empty_displayed_set_is_unknown():
    """Soccer's no-winner-market arm reaches here with an empty list."""
    assert concept_price_observed_at_iso([], "winner_field", 0) is None


def test_a_slots_row_cannot_be_dated_and_says_so():
    """Tennis. `OutcomeRow` has no instance dict and no `last_updated`.

    It must DEGRADE, not raise — nine tennis tests failed with `AttributeError`
    when #5778 first assumed every carrier had a `__dict__` (gotcha #42).
    """
    assert concept_price_observed_at_iso(
        [_SlotsOutcome(), _SlotsOutcome("Sinner", 0.4)], "winner_field", 2
    ) is None


def test_a_displayed_leg_with_no_stamp_does_not_suppress_a_sibling_that_has_one():
    """An unstamped leg is IGNORED, not treated as "unknown wins".

    This module's rule everywhere. The bout prints both sides; one of them
    cannot be dated; the honest mark is the one stamp that exists, not silence.
    """
    outcomes = [_Outcome("A", 0.9, None), _Outcome("B", 0.1, STALE)]
    assert concept_price_observed_at_iso(
        outcomes, CONCEPT_BOUT_KIND, 2
    ) == STALE.isoformat()


def test_a_naive_stamp_is_published_with_a_utc_offset():
    """An offsetless ISO string is parsed as LOCAL time by `Date.parse`.

    That would age a just-polled price by the reader's own UTC offset and print
    "3h ago" in California on a fresh market. A plain ORM column is naive.
    """
    naive = STALE.replace(tzinfo=None)
    out = concept_price_observed_at_iso(
        [_Outcome("A", 0.9, naive)], "winner_field", 1
    )
    assert out is not None and out.endswith("+00:00")
    assert out == STALE.isoformat()


def test_an_unreadable_probability_sorts_below_every_readable_one():
    """A leg whose probability cannot be read must not displace the leader.

    It is the first row pushed out of the window, never something that evicts a
    price the reader is looking at.
    """
    outcomes = [
        _Outcome("Leader", 0.9, STALE),
        _Outcome("Corrupt", "not-a-number", FRESH),
    ]
    assert concept_price_observed_at_iso(
        outcomes, "winner_field", 2
    ) == STALE.isoformat()


# ---------------------------------------------------------------------------
# GUARD: every adapter folds over its DISPLAYED rows, not over a market
# ---------------------------------------------------------------------------

#: (module, the name the adapter must pass as the outcomes argument). Each is
#: the adapter's own already-filtered list — the one `competitors` was built
#: from. `event_combat` passes `main_event.outcomes` because `_fight_outcomes`
#: applies no name filter there, so the market's outcomes ARE the displayed set;
#: it is recorded here so that stops being an accident.
EXPECTED_OUTCOME_ARGUMENTS = {
    "event_cycling": "real_outcomes",
    "event_awards": "marquee_outcomes",
    "event_election": "marquee_outcomes",
    "event_f1": "field_outcomes",
    "event_soccer": "ranked",
    "event_combat": "main_event.outcomes",
    "event_tennis": "winner.outcomes",
}


def _utils_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "app" / "utils"


def _concept_helper_calls() -> dict[str, list[ast.Call]]:
    found: dict[str, list[ast.Call]] = {}
    for module in EXPECTED_OUTCOME_ARGUMENTS:
        path = _utils_dir() / f"{module}.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "concept_price_observed_at_iso"
        ]
        found[module] = calls
    return found


def test_guard_every_adapter_calls_the_concept_helper_exactly_once():
    calls = _concept_helper_calls()
    missing = sorted(m for m, c in calls.items() if len(c) != 1)
    assert not missing, (
        "each concept adapter must call `concept_price_observed_at_iso` exactly "
        f"once; wrong count in: {missing}"
    )


def test_guard_the_outcomes_argument_is_the_displayed_list_not_a_market():
    """🔴 THE LOAD-BEARING GUARD, and it asserts the ARGUMENT, not the call.

    The mutant it exists for is a one-word edit that every other test here
    survives: pass the MARKET's outcome list instead of the adapter's filtered
    one. The helper still runs, still folds `MIN` over the right leg count,
    still returns a plausible ISO string — and silently starts ranking the
    `is_field_outcome` catch-all that the adapter dropped, which on a 184-way
    Grand Tour field can out-price every named rider and take the top slot.

    Nothing about the returned VALUE reveals that on a uniformly-stamped market,
    and today every live concept market is uniformly stamped (see the module
    docstring). So the source is where it has to be caught.
    """
    calls = _concept_helper_calls()
    actual: dict[str, str] = {}
    for module, module_calls in calls.items():
        assert module_calls, f"{module} does not call the concept helper at all"
        first = module_calls[0].args[0]
        actual[module] = ast.unparse(first).replace(" or []", "").strip()

    # `event_tennis` passes a `getattr(...) or []` guard; normalise to the target.
    if actual.get("event_tennis", "").startswith("getattr("):
        actual["event_tennis"] = "winner.outcomes"

    assert actual == EXPECTED_OUTCOME_ARGUMENTS, (
        "an adapter changed WHICH rows date its card. The argument must be the "
        "same filtered list `competitors` was built from — passing the market's "
        "outcomes reintroduces #5809 on the concept surface, invisibly on any "
        f"uniformly-stamped market.\n  expected: {EXPECTED_OUTCOME_ARGUMENTS}\n"
        f"  actual:   {actual}"
    )


def _envelope_kind_beside_the_call(module: str) -> tuple[str | None, str | None]:
    """`(kind the envelope DECLARES, kind the helper call PASSES)` for one adapter.

    Both are read off the SAME `primary` dict, so the comparison needs no table
    to go stale.
    """
    path = _utils_dir() / f"{module}.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        if "price_observed_at" not in keys or "kind" not in keys:
            continue
        declared = passed = None
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant):
                continue
            if key.value == "kind" and isinstance(value, ast.Constant):
                declared = value.value
            if key.value == "price_observed_at":
                for call in ast.walk(value):
                    if (
                        isinstance(call, ast.Call)
                        and getattr(call.func, "id", None)
                        == "concept_price_observed_at_iso"
                        and len(call.args) >= 2
                        and isinstance(call.args[1], ast.Constant)
                    ):
                        passed = call.args[1].value
        return declared, passed
    return None, None


@pytest.mark.parametrize("module", sorted(EXPECTED_OUTCOME_ARGUMENTS))
def test_guard_the_kind_passed_matches_the_kind_the_envelope_declares(module):
    """🔴 THE SURVIVOR THIS WAS WRITTEN FOR.

    Mutating `event_cycling`'s second argument from `"winner_field"` to
    `"co_equal_list"` passed every other test in this file. It is NOT an
    equivalence: `concept_card_leg_count` gates on archetype AND count, so on a
    184-rider field both spellings return the leader window and the output is
    identical — but on a Grand Tour whose field has thinned to exactly two
    riders the mutant flips to the BOUT window and dates the card by a runner-up
    a `winner_field` never prints. A rare corner is still a wrong number, and
    the whole ship is about not dating a card by a row nobody can see.

    Pinned against the envelope's OWN `kind` rather than a table in this file:
    the two are the same fact read twice, and anything that changes one must
    change the other. A hand-maintained expectation would merely relocate the
    drift.
    """
    declared, passed = _envelope_kind_beside_the_call(module)
    assert declared is not None, f"{module}: no envelope carrying both keys"
    assert passed is not None, f"{module}: the helper's `kind` is not a literal"
    assert passed == declared, (
        f"{module} declares `kind={declared!r}` on its envelope but dates the "
        f"card as {passed!r}. The leg count is chosen from the archetype, so "
        "these disagreeing means the mark can describe a set of prices the "
        "card does not render."
    )


def test_guard_the_leg_count_is_never_hardcoded_at_a_call_site():
    """The rule lives in ONE function; a site may not compute its own window.

    A literal `2` or `3` in the third argument is the drift `concept_card_leg_count`
    exists to prevent — it would let one domain disagree with
    `_bout_from_competitors` about what a bout is.
    """
    offenders = []
    for module, module_calls in _concept_helper_calls().items():
        for call in module_calls:
            if len(call.args) < 3:
                offenders.append((module, "fewer than three arguments"))
                continue
            third = call.args[2]
            if isinstance(third, ast.Constant):
                offenders.append((module, f"literal {third.value!r}"))
    assert not offenders, (
        "the competitor count must be passed from the adapter's own list "
        f"(`len(competitors)`), never a literal: {offenders}"
    )
