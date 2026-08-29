"""LAT-P135 / #1866 — the typeahead "did you mean" fallback must use the INDEXABLE
trigram predicate, and both fuzzy surfaces must stay in agreement about it.

THE DEFECT, MEASURED ON PRODUCTION `ce5f719b` (2026-08-29).

`/api/events/search` and `/api/events/typeahead` each carry a fuzzy team fallback
that answers "did you mean". They are the same question against the same table
with the same 0.25 threshold. LAT-P002/#1494 fixed the `/search` one to use the
`%` OPERATOR, which `ix_teams_name_trgm` (a GIN over `teams.name`) can serve.
`/typeahead`'s twin was never changed and kept the FUNCTION form,
`similarity(a, b) > 0.25`, which no index can serve and which was evaluated three
times per row — in the SELECT, the WHERE and the ORDER BY.

`EXPLAIN (ANALYZE)` on production, same query, same 9,619-row `teams` table:

    WHERE similarity(teams.name, 'yankes') > 0.25
        -> Seq Scan, 9,617 Rows Removed by Filter, Execution Time 176.379 ms
    WHERE teams.name % 'yankes'
        -> Bitmap Index Scan on ix_teams_name_trgm, Execution Time 1.138 ms

**155x, from an index that already exists.** No DDL — which is the whole reason
this was reachable at all, because the dominant cost on this endpoint
(`futures_query`, 87 % of a ~3.6 s cold build) IS blocked on DDL.

WHY THE `%` SWITCH IS NOT FREE, AND WHAT MAKES IT SAFE HERE. `%` tests
`similarity >= pg_trgm.similarity_threshold`, and that GUC defaults to **0.3** —
STRICTER than the 0.25 both paths have always used. Switching naively would
silently narrow "did you mean" and nothing would fail. So the threshold is pinned
for the transaction and the explicit `> 0.25` is KEPT as the exact boundary (`%`
is `>=`; the contract is `>`). Only the access path changes.

🔴 THE BAND IS NOT HYPOTHETICAL AND THAT WAS CHECKED BY LOOKING. On production,
`q="lakrs"` has a best team similarity of **0.2667** — inside (0.25, 0.30). Under
an unpinned threshold that correction disappears. It is live right now:
`/api/events/search?q=lakrs` answers `did_you_mean: "Växjö Lakers"`, which is also
the end-to-end PROOF that `SET LOCAL` genuinely takes effect on this connection
rather than being a no-op nobody ever verified.

WHAT THIS FILE ASSERTS, AND WHY IT IS SHAPE RATHER THAN WALL-CLOCK. A timing
assertion on CI hardware is flaky and proves nothing about production (LAT-P002's
own note, inherited). These assert the structural properties whose absence made
the query slow, plus the two that make the speed-up recall-neutral.

🔴 THIS FILE READS COMMENT-STRIPPED SOURCE, WHICH LAT-P002's EQUIVALENT DOES NOT.
`test_search_latency_contract.py` asserts against raw `SEARCH_SRC`, and the code
it guards is heavily commented with text that QUOTES the anti-pattern it replaced.
That guard passes today by luck of phrasing, not by construction: a future comment
containing the asserted substring would make it green over deleted code. The
helper to avoid that (`_strip_comments`) already exists in that file and simply is
not used by those two tests. Recorded rather than silently fixed in a latency
cycle — see the parked item in the LAT-P135 report.

THE GUARD THAT IS ACTUALLY ABOUT THE BUG: every property is asserted over BOTH
surfaces from one parameterised list. The defect was never "typeahead is slow";
it was that ONE of two twins was repaired and nothing compared them for 130
cycles. A test that only pins `/typeahead` rebuilds exactly that arrangement
facing the other way.

🔴 WHY THE CHECKS BELOW ARE PURE FUNCTIONS OVER A SOURCE STRING RATHER THAN
ASSERTIONS INLINE IN THE TESTS. `scripts/evals/_mutation_guard.py` states that a
harness which `exec`s a mutated STRING is strictly better than one that writes a
mutated file to disk, and that new harnesses should prefer it — the alternative
put a live mutant into a commit once already. These predicates are the seam that
makes that possible: `gate_typeahead_fuzzy_index_mutations.py` feeds mutated
source strings through THESE functions, so the battery exercises the real guard
logic instead of a second copy of it that can drift, and it never touches disk.
"""

import inspect
import re

import pytest

from app.routes import events as events_route

#: The two fuzzy "did you mean" surfaces. Named, not discovered: a test that
#: sweeps "every function containing similarity()" would go quietly green if a
#: third surface were added without the fix, because it would sweep zero of them
#: on the day someone renames one. `test_no_fuzzy_surface_is_left_on_the_function_form`
#: is the sweep that covers what this list cannot.
FUZZY_SURFACES = ("search_events", "typeahead_search")

#: The contract threshold, and the ONE place this file states it. Both surfaces
#: must agree with each other and with this.
CONTRACT_THRESHOLD = 0.25

#: Production, 2026-08-29: `max(similarity(teams.name, 'lakrs'))` over all 9,619
#: rows. Inside (0.25, 0.30), i.e. exactly the recall an unpinned `%` would drop.
#: A literal, because the point of recording it is that the band is OCCUPIED —
#: re-deriving it would make the test depend on the data it exists to describe.
LIVE_BAND_CASE = ("lakrs", 0.2667)

_OPERATOR_FORM = 'Team.name.op("%")(q)'
_PIN_PREFIX = "SET LOCAL pg_trgm.similarity_threshold"
_BOUNDARY_RE = r"func\.similarity\(Team\.name, q\) > ([0-9.]+)"
_PIN_RE = r"SET LOCAL pg_trgm\.similarity_threshold = ([0-9.]+)"
_RANK_FORM = "func.similarity(Team.name, q).desc()"


def strip_comments(src: str) -> str:
    """Drop whole-line `#` comments.

    The code being guarded explains itself by QUOTING the anti-pattern it
    replaced, so a substring check against raw source can match the explanation
    instead of live code — i.e. pass over a deleted fix.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


def source_of(name: str) -> str:
    """Comment-stripped source of one route function, by attribute name."""
    return strip_comments(inspect.getsource(getattr(events_route, name)))


# ---------------------------------------------------------------------------
# THE CHECKS. Each takes comment-stripped source and returns None when the
# property holds, or a human sentence naming what broke. Shared verbatim with
# the mutation battery — see the module docstring.
# ---------------------------------------------------------------------------

def check_uses_indexable_operator(code: str) -> str | None:
    """`similarity(a,b) > x` cannot use ix_teams_name_trgm; `%` can."""
    if _OPERATOR_FORM not in code:
        return (
            "on the unindexable similarity() function form — a full Seq Scan of "
            "teams with three similarity() evaluations per row"
        )
    return None


def check_pins_the_threshold(code: str) -> str | None:
    """Without the pin, `%` filters at the 0.3 GUC default and recall narrows."""
    if _PIN_PREFIX not in code:
        return (
            "uses `%` without pinning the threshold — `%` is >= the GUC, which "
            "defaults to 0.3, so 'did you mean' silently loses the 0.25-0.30 band"
        )
    return None


def check_keeps_the_exact_boundary(code: str) -> str | None:
    """`%` is `>=`; the contract has always been `>`. The explicit check stays."""
    match = re.search(_BOUNDARY_RE, code)
    if not match:
        return "dropped the exact boundary check — `%` is >=, the contract is >"
    if float(match.group(1)) != CONTRACT_THRESHOLD:
        return (
            f"filters at {match.group(1)}, not the {CONTRACT_THRESHOLD} contract "
            "both surfaces share"
        )
    return None


def check_pin_is_not_stricter_than_the_boundary(code: str) -> str | None:
    """The real invariant, and the one a substring test cannot express.

    A pin BELOW the boundary is harmless — `%` widens, the explicit `> 0.25`
    still cuts, recall is identical. A pin ABOVE it silently narrows recall and
    NOTHING else in the system notices, because the query still returns rows and
    the endpoint still answers. The two numbers live on different lines and there
    has never been anything comparing them; that is the same shape as a period
    and a TTL set in different files.
    """
    pin = re.search(_PIN_RE, code)
    boundary = re.search(_BOUNDARY_RE, code)
    if not pin or not boundary:
        return "is missing one of the two numbers that have to agree"
    if float(pin.group(1)) > float(boundary.group(1)):
        return (
            f"pins the threshold at {pin.group(1)} but filters at "
            f"> {boundary.group(1)} — `%` would drop rows the contract admits"
        )
    return None


def check_pin_is_issued_before_the_query(code: str) -> str | None:
    """Order is the whole mechanism: `SET LOCAL` after the SELECT pins nothing.

    Source order is execution order here — both statements sit in one straight
    line inside the same `if` block, with no branch between them. A substring
    test passes with the two lines swapped; this one does not.
    """
    if _PIN_PREFIX not in code or _OPERATOR_FORM not in code:
        return "is missing the pin or the operator, so their order says nothing"
    if code.index(_PIN_PREFIX) > code.index(_OPERATOR_FORM):
        return (
            "issues the threshold pin AFTER the query it is supposed to govern — "
            "the query runs at the 0.3 default and recall narrows"
        )
    return None


def check_still_ranks_by_similarity(code: str) -> str | None:
    """Access-path-only. If the ORDER BY went too, this became a recall change."""
    if _RANK_FORM not in code:
        return (
            "no longer ranks candidates by similarity — the change was supposed "
            "to touch the access path and nothing else"
        )
    return None


#: Every check, in the order a reader should meet them. The battery iterates
#: this, so a check added here is automatically part of the battery's oracle.
CHECKS = (
    check_uses_indexable_operator,
    check_pins_the_threshold,
    check_keeps_the_exact_boundary,
    check_pin_is_not_stricter_than_the_boundary,
    check_pin_is_issued_before_the_query,
    check_still_ranks_by_similarity,
)


@pytest.fixture(params=FUZZY_SURFACES)
def surface(request):
    return request.param


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_every_fuzzy_surface_satisfies_every_check(surface, check):
    """The whole contract, both surfaces, one matrix.

    12 cells. Before this cycle, the six `typeahead_search` cells were four reds
    and two greens — the two greens being the boundary and the ranking, which the
    slow form also satisfied.
    """
    problem = check(source_of(surface))
    assert problem is None, f"{surface} {problem}"


def test_the_live_band_case_is_inside_the_window_the_pin_protects():
    """The band is OCCUPIED on production, so narrowing it is a real recall loss.

    `lakrs` -> 0.2667 (production, 2026-08-29, max over 9,619 teams). Recorded so
    that a future reader deciding "the pin is probably unnecessary" is arguing
    with a measurement rather than with a preference.
    """
    query, sim = LIVE_BAND_CASE
    assert CONTRACT_THRESHOLD < sim < 0.30, (
        f"{query!r} at {sim} is no longer the boundary case this file documents; "
        "re-measure before relaxing the pin"
    )


def test_no_fuzzy_surface_is_left_on_the_function_form():
    """The bug was DRIFT, not slowness.

    `/search` was repaired by LAT-P002 and `/typeahead` was not, and for 130
    cycles nothing asked whether the two agreed. This sweeps the whole route
    module so a THIRD surface cannot be added on the slow form — the parameterised
    matrix above can only check the surfaces someone remembered to list.
    """
    module_src = strip_comments(inspect.getsource(events_route))
    offenders = re.findall(
        r"\.where\(\s*func\.similarity\(Team\.name, q\) > [0-9.]+\s*\)", module_src
    )
    assert not offenders, (
        "a fuzzy team lookup filters on the bare similarity() function form with "
        f"no `%` operator beside it — unindexable Seq Scan: {offenders}"
    )
