"""LAT-P020/#1107 — picking the evolution market must not cost a query per market.

Why this file exists
--------------------
`get_golf_tournament` chooses ONE winner market to draw the path-to-resolution
chart. It used to do that by looping over every winner-market candidate and
awaiting THREE queries inside the loop: an outcome count, a snapshot count, and
the graded winner's last price. Two of the three are semi-joins against
`futures_odds_snapshots` (~50M rows), so the cost scaled with the number of
winner markets — and a major carries the most of them.

MEASURED in production 2026-08-09 by diffing `pg_stat_statements` around a single
cold request for `event:golf:pga-championship` (18.77s wall, HTTP 200). The
attribution, largest first:

======================================  ==========================
count(futures_odds_snapshots) semi-join **6,951 ms across 7 calls**
`futures_markets` golf scan (phase 1)   4,839 ms / 1 call
`futures_markets` full-column selects   3,926 ms / 2 calls
======================================  ==========================

~993 ms EACH, seven times, strictly sequential on one connection — the largest
single bucket remaining in #1107 after LAT-P014 stopped the corpus load, and pure
round-trip: the same three facts can be had for every candidate in three grouped
queries no matter how many candidates there are.

The fix also discharges **ruling 005 (extract-on-touch)**: the RANKING is policy,
so it moved to `app.utils.golf_evolution_market` as a pure module — no session, no
request context — and its semantics are pinned below without any fixture.

These assert SHAPE and POLICY, never wall-clock: a timing assertion on CI hardware
is flaky and proves nothing about production (LAT-P005).
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.routes import golf as golf_route
from app.utils.golf_evolution_market import (
    MIN_CONTENDER_OUTCOMES,
    NON_CONTENDER_WINNER_RE,
    SETTLED_RESOLVE_MIN,
    contender_candidates,
    eligible_candidates,
    select_by_settled_resolution,
    select_by_snapshot_richness,
    select_evolution_market,
)


# ---------------------------------------------------------------------------
# SHAPE — the round-trip count must not scale with the number of markets.
# ---------------------------------------------------------------------------

_ROUTE_SRC = textwrap.dedent(inspect.getsource(golf_route.get_golf_tournament))
_ROUTE_TREE = ast.parse(_ROUTE_SRC).body[0]

# Names that hold a COLLECTION OF MARKETS. A query awaited inside a loop over one
# of these is an N+1 by construction, whatever it is selecting.
_PER_MARKET_ITERABLES = (
    "market_ids",
    "candidate_ids",
    "eligible_ids",
    "mids",
    "rt_ids",
)


def _executes_with_enclosing_loops(fn_node):
    """Yield (lineno, [loop source, ...]) for every awaited `db.execute`."""
    found = []

    def walk(node, loops):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.AsyncFor)):
                walk(child, loops + [ast.unparse(child.iter)])
            else:
                if isinstance(child, ast.Await) and "db.execute" in ast.unparse(
                    child.value
                ):
                    found.append((child.lineno, loops))
                walk(child, loops)

    walk(fn_node, [])
    return found


def test_no_query_is_awaited_inside_a_loop_over_markets():
    """The regression that cost 6,951 ms: one query per candidate market.

    This is the guard that fails if the per-market loop is reintroduced in ANY
    form — it keys on iterating a market collection, not on the specific query.
    """
    offenders = [
        (line, loops)
        for line, loops in _executes_with_enclosing_loops(_ROUTE_TREE)
        if any(
            name in loop_src
            for loop_src in loops
            for name in _PER_MARKET_ITERABLES
        )
    ]
    assert not offenders, (
        "a DB query is awaited inside a loop over markets — that is the N+1 "
        f"measured at 6,951 ms across 7 calls in #1107: {offenders}"
    )


def _route_code_without_comments() -> str:
    return "\n".join(
        line
        for line in _ROUTE_SRC.splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_facts_are_fetched_as_grouped_batches():
    """Positive half of the mutation check.

    Absence of the N+1 is satisfiable by deleting the feature, so assert the
    batched form is actually present and actually bounded by an id list.
    """
    winner_block = _route_code_without_comments().split("placement_market_ids")[0]

    assert winner_block.count("group_by(FuturesOutcome.market_id)") == 2, (
        "expected exactly two grouped counts (outcomes, snapshots) for the "
        "evolution pick"
    )
    assert "distinct(FuturesOutcome.market_id)" in winner_block, (
        "the graded-winner lookup lost its DISTINCT ON — it is either back to a "
        "per-market LIMIT 1 or returning every snapshot"
    )
    for bound in ("in_(candidate_ids)", "in_(eligible_ids)"):
        assert bound in winner_block, (
            f"a batched query is not bounded by {bound} — it is scanning beyond "
            "the tournament's own candidates"
        )


def test_the_expensive_count_is_only_paid_when_it_can_change_the_answer():
    """The larger half of #1107's win, and the easiest thing to regress.

    Resolution decides whenever it produces an answer, so building `snap_counts`
    eagerly means paying a ~4.7s count (193,981 rows for ONE market, measured
    2026-08-09) to compute a value that `or` then discards. Every completed major
    grades at 0.895-0.9995, so that was the cost on the whole #1107 population.

    Asserts the SEQUENCE — resolve, then a conditional richness fetch — because
    the cost is in the ordering, not in either query alone.
    """
    code = _route_code_without_comments()
    resolve_at = code.find("select_by_settled_resolution(")
    guard_at = code.find("if evolution_market_id is None")
    count_at = code.find("sqlfunc.count(FuturesOddsSnapshot.id)")
    richness_at = code.find("select_by_snapshot_richness(")

    assert -1 not in (resolve_at, guard_at, count_at, richness_at), (
        "the lazy-richness structure is gone: "
        f"resolve={resolve_at} guard={guard_at} count={count_at} "
        f"richness={richness_at}"
    )
    assert resolve_at < guard_at < count_at < richness_at, (
        "the snapshot count is no longer gated behind a failed resolution — it "
        "is back to being paid on every completed major and thrown away"
    )


def test_the_ranking_policy_is_delegated_to_the_pure_module():
    """Ruling 005: the policy this fix touched leaves the route as a pure module.

    'Moved the code' only discharges the ruling if the route actually calls it,
    so assert the call sites rather than the import.
    """
    code = _ROUTE_SRC
    for fn in ("contender_candidates(", "eligible_candidates(",
               "select_by_settled_resolution(", "select_by_snapshot_richness("):
        assert fn in code, f"the route no longer delegates to {fn}"
    assert "resolved_best_val" not in code, (
        "the ranking was re-inlined into the route; it belongs in "
        "app.utils.golf_evolution_market where it is testable without a session"
    )


def test_the_pure_module_takes_no_session():
    """The property that makes the extraction worth anything (ruling 005)."""
    import app.utils.golf_evolution_market as mod

    src = inspect.getsource(mod)
    for forbidden in ("AsyncSession", "db.execute", "await ", "from app.models"):
        assert forbidden not in src, (
            f"{forbidden!r} appears in the pure policy module — it is no longer "
            "testable without fixtures, which was the point"
        )


# ---------------------------------------------------------------------------
# POLICY — the decisions themselves, now unit-testable with plain dicts.
# ---------------------------------------------------------------------------


def test_winner_shaped_props_are_dropped_before_any_fact_is_fetched():
    """#955: a 26-outcome "Winner Nationality" market passes the >5 filter and
    was once plotted as the contenders chart (US/England/Spain/Other)."""
    names = {
        1: "The Open Championship Winner 2026",
        2: "2026 U.S. Open: Winner Nationality",
        3: "Country of Winner",
        4: "Winning Margin",
        5: "PGA Tour: U.S. Open Winner",
    }
    assert contender_candidates([1, 2, 3, 4, 5], names) == [1, 5]


def test_a_real_field_is_never_mistaken_for_a_prop():
    """The exclusion must not eat "PGA Tour: <event> Winner" — the tour token is
    what makes this regex delicate."""
    assert not NON_CONTENDER_WINNER_RE.search("PGA Tour: U.S. Open Winner")
    assert NON_CONTENDER_WINNER_RE.search("Tour of Winner")


def test_thin_markets_are_not_eligible():
    """"League of Winner" (3 outcomes) and Yes/No binaries are not fields."""
    counts = {1: 156, 2: 3, 3: 2, 4: MIN_CONTENDER_OUTCOMES}
    assert eligible_candidates([1, 2, 3, 4], counts) == [1, 4]


def test_a_market_with_no_outcomes_at_all_is_not_eligible():
    """Absent from the grouped count == zero outcomes, matching the old
    per-market `scalar() or 0`."""
    assert eligible_candidates([7], {}) == []


def test_a_live_tournament_falls_back_to_the_snapshot_richest_market():
    """No `is_winner` exists before a tournament settles, so `winner_last` is
    empty and richness decides."""
    pick = select_evolution_market([1, 2, 3], {1: 10, 2: 900, 3: 40}, {})
    assert pick == 2


def test_a_settled_resolved_winner_beats_raw_snapshot_richness():
    """#225 Item 3, the whole reason the second ranking exists.

    The odds_api futures market is snapshot-richest but fizzles at ~18%; the
    real-money Kalshi market converges to ~0.999 and is the honest journey.
    """
    pick = select_evolution_market(
        [101, 202],
        snap_counts={101: 5000, 202: 200},   # odds_api richest
        winner_last={101: 0.18, 202: 0.999},  # ...but it never resolved
    )
    assert pick == 202


def test_a_market_below_the_resolve_floor_cannot_win_on_resolution():
    """DataGolf RESETS to ~0.5% post-event. Below the floor it must not be
    promoted over the richness pick."""
    pick = select_evolution_market(
        [1, 2],
        snap_counts={1: 900, 2: 10},
        winner_last={2: 0.005},
    )
    assert pick == 1


def test_the_floor_itself_qualifies():
    """`>=` — a value exactly at the floor is preferred, as it always was."""
    pick = select_evolution_market(
        [1, 2], {1: 900, 2: 10}, {2: SETTLED_RESOLVE_MIN}
    )
    assert pick == 2


def test_richness_ties_keep_the_first_market():
    """Strict `>`. Asserted because batching made the iteration order explicit
    and an accidental `>=` here would silently change which chart is drawn."""
    assert select_evolution_market([1, 2, 3], {1: 50, 2: 50, 3: 50}, {}) == 1


def test_resolution_ties_keep_the_last_market():
    """`>=`. The opposite tie-break from richness, in the same loop — the pair is
    exactly the kind of detail a rewrite loses."""
    pick = select_evolution_market([1, 2, 3], {}, {1: 0.99, 2: 0.99, 3: 0.99})
    assert pick == 3


def test_no_eligible_markets_yields_no_pick():
    """The route falls back to `market_ids[0]`; that only works if this says
    None rather than raising or inventing an id."""
    assert select_evolution_market([], {}, {}) is None


def test_resolution_alone_answers_for_a_settled_tournament():
    """The property the laziness rests on: for a settled major, the cheap half
    returns a real answer, so the expensive half is never needed.

    Values are the real production prices measured 2026-08-09 for the PGA
    Championship and Open Championship winner markets.
    """
    graded = {10671874: 0.9995, 11208470: 0.8950, 19455434: 0.0020,
              20566735: 0.9995, 54838223: 0.9990}
    pick = select_by_settled_resolution(sorted(graded), graded)
    assert pick is not None, (
        "a completed major produced no settled pick — the lazy path would then "
        "pay the ~4.7s snapshot count it was written to avoid"
    )


def test_resolution_declines_for_a_live_tournament():
    """Nothing graded => None => the caller pays for richness, correctly."""
    assert select_by_settled_resolution([1, 2, 3], {}) is None


def test_resolution_declines_when_everything_is_below_the_floor():
    """A DataGolf model that reset to ~0.5% must not be promoted; the caller
    still needs richness."""
    assert select_by_settled_resolution([1, 2], {1: 0.0046, 2: 0.0020}) is None


def test_the_split_functions_compose_into_the_combined_policy():
    """`select_evolution_market` must stay the honest statement of the policy the
    route now executes in two steps, or the equivalence tests below stop
    guarding the route."""
    ids, snaps, wins = [1, 2, 3], {1: 10, 2: 900, 3: 40}, {3: 0.99}
    assert select_evolution_market(ids, snaps, wins) == (
        select_by_settled_resolution(ids, wins)
        or select_by_snapshot_richness(ids, snaps)
    )


# ---------------------------------------------------------------------------
# EQUIVALENCE — the batched pick agrees with the loop it replaced.
#
# The claim made in the route comment is "set-identical by construction". This
# proves it against the ORIGINAL algorithm rather than asserting it, over inputs
# that deliberately include the cases that distinguish the two tie-breaks.
# ---------------------------------------------------------------------------


def _original_algorithm(eligible_ids, snap_counts, winner_last):
    """Verbatim transcription of the pre-LAT-P020 inline loop."""
    best_id = None
    best_count = -1
    resolved_best_id = None
    resolved_best_val = 0.5
    for mid in eligible_ids:
        total = snap_counts.get(mid, 0)
        if total > best_count:
            best_count = total
            best_id = mid
        winner_resolve = winner_last.get(mid)
        if winner_resolve is not None and float(winner_resolve) >= resolved_best_val:
            resolved_best_val = float(winner_resolve)
            resolved_best_id = mid
    return resolved_best_id or best_id


@pytest.mark.parametrize("seed", range(60))
def test_the_batched_pick_matches_the_loop_it_replaced(seed):
    import random

    rng = random.Random(seed)
    ids = list(range(1, rng.randint(1, 7) + 1))
    snaps = {i: rng.choice([0, 10, 50, 50, 900]) for i in ids if rng.random() < 0.9}
    # Values straddle the 0.5 floor and repeat, so ties and near-misses both occur.
    wins = {
        i: rng.choice([0.005, 0.18, 0.5, 0.99, 0.99, 0.999])
        for i in ids
        if rng.random() < 0.6
    }
    assert select_evolution_market(ids, snaps, wins) == _original_algorithm(
        ids, snaps, wins
    ), f"divergence on seed={seed} ids={ids} snaps={snaps} wins={wins}"
