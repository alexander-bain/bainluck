"""The RECENT RESULTS rail must keep its optimization fence (#2260, LAT-P110).

## Why this file exists

`/api/leagues/{sport_key}` builds two event rails. The results rail read

    ... WHERE sports.key = :k
        AND events.status IN ('completed','closed')
        AND events.commence_time >= now() - interval '14 days'
    ORDER BY events.commence_time DESC LIMIT 9

and PostgreSQL, offered an index that already produces `commence_time` order,
satisfied the ORDER BY from `ix_events_commence_time` and walked it expecting to
stop after nine rows. For a league that played yesterday it stops immediately.
For a league that did not, nothing stops it but the 14-day window, so it reads
every event in that window — **60,447 rows and 39,605 blocks to return seven
CFL games**, measured on production slug `67e2585c`. The first cold open of
`/api/leagues/americanfootball_cfl` cost **4,649 ms**.

`OFFSET 0` in the subquery blocks pull-up (`is_simple_subquery()` refuses any
subquery carrying a limit/offset node), the filter therefore runs before the
sort, and the same eight leagues drop from 230,256 blocks to 2,313 with row
counts asserted identical on every one.

## The shape of the guard

The fence is one clause with no visible effect on results, in a query whose
correctness is unchanged by deleting it. Nothing about the payload goes wrong
when it is removed — only the plan does, on production data this suite does not
have (there is no local Postgres in this sandbox; a real-plan gate is CI-only).
So the guard asserts the STATEMENT, in both directions:

* the fence is present, and the ORDER BY / LIMIT sit OUTSIDE it — the two halves
  that make it work. A fence with the sort still pushed inside is not a fence;
* the sibling upcoming-games query is NOT fenced. That asymmetry is a measured
  decision (`basketball_ncaab` 56 -> 5,130 blocks when the fence was applied
  there), and a later reader tidying the two into a matching pair would be
  undoing a measurement, so the test says so out loud;
* the route ACTUALLY EMITS the fenced statement. A helper that compiles the
  right SQL while `build_league` keeps its own inline copy is the failure this
  file's last test exists to catch (memory: a plant must hit the render).
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.utils.event_completion import UPCOMING_GRACE
from app.routes.league_futures import (
    RESULTS_LIMIT,
    RESULTS_LOOKBACK_DAYS,
    UNREPORTED_LIMIT,
    UPCOMING_GAMES_LIMIT,
    build_league,
    recent_results_query,
    unreported_games_query,
    upcoming_games_query,
)

NOW = datetime(2026, 8, 28, 23, 0, tzinfo=timezone.utc)

#: The live-first ordering, as SQLAlchemy actually renders it — parenthesised,
#: with the status value bound. Matched by shape rather than by an exact string
#: so a bind-numbering change is not read as the CASE having disappeared.
_CASE_ORDER = re.compile(r"CASE WHEN \(events\.status = ")


def _sql(query, *, literal: bool = False) -> str:
    kwargs = {"literal_binds": True} if literal else {}
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs=kwargs))


def _split_on_fence(sql: str) -> tuple[str, str]:
    """(inside the fenced subquery, outside it). Raises if the fence is gone."""
    marker = "LIMIT ALL OFFSET 0"
    assert marker in sql, (
        "the OFFSET 0 optimization fence is missing from the recent-results "
        "query — see the module docstring: without it the planner walks "
        "ix_events_commence_time and a quiet league costs ~4.9 s"
    )
    head, tail = sql.split(marker, 1)
    return head, tail


# ---------------------------------------------------------------------------
# the fence itself
# ---------------------------------------------------------------------------


def test_recent_results_query_carries_the_offset_zero_fence():
    sql = _sql(recent_results_query("americanfootball_cfl", NOW))
    _split_on_fence(sql)


def test_unreported_games_query_carries_the_fence_too():
    """#3211's rail is the same SHAPE of question as the recent one — a status
    filter over one league inside the 14-day window, ordered by time and capped
    — so LAT-P110's measurement transfers and the fence comes with it.

    What must NOT be inherited is the sibling UPCOMING rail's *no-fence*
    decision: that was measured on an ORDER BY leading with a CASE, which has no
    LIMIT pushdown to prevent, and this query orders on `commence_time` exactly
    as the fenced one does. A fence is a claim about one plan, and this rail's
    plan is the fenced rail's plan.
    """
    sql = _sql(unreported_games_query("americanfootball_cfl", NOW))
    _split_on_fence(sql)
    inside, outside = _split_on_fence(sql)
    assert "ORDER BY" not in inside.upper(), "the ORDER BY was pushed inside the fence"
    assert "ORDER BY" in outside.upper()


def test_the_unreported_rail_declares_its_own_cap():
    """+1, like the other two, so the cap is DECLARED rather than silently
    applied — and its OWN constant, because the entire reason this rail exists
    is that one cap shared across two unequal populations starved the smaller
    one out of existence."""
    sql = _sql(unreported_games_query("tennis_wta", NOW), literal=True)
    assert re.search(rf"LIMIT {UNREPORTED_LIMIT + 1}\b", sql)
    assert UNREPORTED_LIMIT != RESULTS_LIMIT, (
        "the unreported rail's cap has become the results rail's cap — two "
        "rails governed by one number cannot be tuned apart, which is the "
        "trap #3211's third rail exists to escape"
    )


def test_the_fence_is_a_literal_zero_not_a_bind():
    """`.offset(0)` renders `OFFSET $1`, which fences identically but makes the
    emitted statement differ from the one every measurement in the docstring was
    taken on. Same text, same plan, same evidence."""
    sql = _sql(recent_results_query("soccer_epl", NOW))
    assert "OFFSET 0" in sql
    assert not re.search(r"OFFSET %\(param", sql), (
        "the offset compiled to a bind parameter — the measured statement uses a "
        "literal 0"
    )


def test_order_by_and_limit_sit_outside_the_fence():
    """The whole mechanism. A fence with the sort still inside it is not a fence:
    the planner would push the LIMIT back down and the 39,605-block walk returns."""
    inside, outside = _split_on_fence(_sql(recent_results_query("baseball_mlb", NOW)))

    assert "ORDER BY" not in inside.upper(), (
        "the ORDER BY was pushed inside the fenced subquery — that is the "
        "index-ordered walk this fence exists to prevent"
    )
    assert "LIMIT %(param" not in inside, "the LIMIT was pushed inside the fence"

    assert "ORDER BY" in outside.upper()
    assert re.search(
        r"ORDER BY anon_\d+\.commence_time DESC", outside
    ), "the outer sort must be on the SUBQUERY's commence_time column"
    assert "LIMIT" in outside.upper()


def test_the_fence_does_not_change_what_the_rail_asks_for():
    """Same filters, same window, same cap — only the plan moves. If a future
    edit changes the predicates while keeping the fence, this catches it."""
    sql = _sql(recent_results_query("icehockey_nhl", NOW), literal=True)

    assert "sports.key = 'icehockey_nhl'" in sql
    assert "JOIN sports ON sports.id = events.sport_id" in sql
    # 'closed' as well as 'completed' — #1204's doubleheader lesson.
    assert "'completed'" in sql and "'closed'" in sql
    # SQLAlchemy renders a datetime literal space-separated, not ISO 'T'.
    cutoff = (NOW - timedelta(days=RESULTS_LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    assert cutoff in sql, f"the 14-day lookback bound is missing: {cutoff}"
    # +1 so the cap is DECLARED rather than silently applied.
    assert re.search(rf"LIMIT {RESULTS_LIMIT + 1}\b", sql)


# ---------------------------------------------------------------------------
# the declared asymmetry — the sibling query must stay UNfenced
# ---------------------------------------------------------------------------


def test_upcoming_games_query_is_deliberately_not_fenced():
    """Measured, not stylistic: fencing this one took `basketball_ncaab` from 56
    blocks to 5,130. Its ORDER BY leads with a CASE, so no index can serve the
    ordering and there is no LIMIT pushdown to prevent. Tidying the two queries
    into a matching pair would be undoing a measurement."""
    sql = _sql(upcoming_games_query("basketball_ncaab", NOW))

    assert "OFFSET" not in sql.upper(), (
        "the upcoming-games query grew a fence — that measured WORSE; see the "
        "docstring on upcoming_games_query"
    )
    assert _CASE_ORDER.search(sql), (
        "the CASE-first ordering is why this query needs no fence — if it is "
        "gone, the no-fence decision has to be re-measured, not inherited"
    )
    assert re.search(r"LIMIT %\(param_\d+\)s", sql)
    assert upcoming_games_query("basketball_ncaab", NOW)._limit_clause is not None


def test_the_two_rails_ask_for_different_statuses():
    """A live/scheduled rail and a completed/closed rail. Cheap, but it is the
    assertion that catches a copy-paste between the two builders.

    🔴 AMENDED BY #3211: THERE ARE THREE BUILDERS NOW, so "the two rails ask for
    different statuses" needs a third column or it certifies two thirds of the
    page.

    #3211's rows — `scheduled`, kickoff already past — were on neither of the
    original rails, and 171 US Open matches were invisible for a fortnight. They
    could not simply join the recent rail: they sort above every Final on a
    `commence_time DESC LIMIT 8` and took all eight slots (measured). So they
    have their own builder, `unreported_games_query`, and the settled rail is
    exactly as narrow as it always was — which is why the original assertions
    below are UNCHANGED rather than relaxed.

    The property this test reaches for is that no two builders have been
    copy-pasted into each other. That it holds over ROWS — exactly one rail per
    row, no gap and no overlap — is a different and stronger claim, asserted
    where it can be executed rather than grepped, in
    `test_the_two_rails_are_jointly_exhaustive_3211.py`.
    """
    upcoming = _sql(upcoming_games_query("soccer_epl", NOW), literal=True)
    results = _sql(recent_results_query("soccer_epl", NOW), literal=True)
    unreported = _sql(unreported_games_query("soccer_epl", NOW), literal=True)

    assert "'live'" in upcoming and "'scheduled'" in upcoming
    assert "'completed'" not in upcoming and "'closed'" not in upcoming
    assert "'completed'" in results and "'closed'" in results
    assert "'live'" not in results and "'scheduled'" not in results

    # #3211's own rail: `scheduled` and nothing else. If it ever names a settled
    # state it has become a second results rail, and the page would print one
    # match twice.
    assert "'scheduled'" in unreported
    assert "'completed'" not in unreported and "'closed'" not in unreported
    assert "'live'" not in unreported

    # It splits from the UPCOMING rail on the same grace expression, from the
    # two sides. One constant, or they overlap or leave a sliver between them —
    # and a sliver is #3211 again, one minute wide.
    grace_edge = (NOW - UPCOMING_GRACE).strftime("%Y-%m-%d %H:%M:%S")
    assert grace_edge in unreported and grace_edge in upcoming, (
        "the upcoming and unreported rails no longer split on the SAME grace "
        f"boundary ({grace_edge})"
    )


def test_the_caps_are_the_declared_constants_plus_one():
    up = _sql(upcoming_games_query("baseball_mlb", NOW), literal=True)
    res = _sql(recent_results_query("baseball_mlb", NOW), literal=True)
    assert re.search(rf"LIMIT {UPCOMING_GAMES_LIMIT + 1}\b", up)
    assert re.search(rf"LIMIT {RESULTS_LIMIT + 1}\b", res)


# ---------------------------------------------------------------------------
# the route actually emits it
# ---------------------------------------------------------------------------


class _EmptyScalars:
    def unique(self):
        return self

    def all(self):
        return []


class _EmptyResult:
    def scalars(self):
        return _EmptyScalars()


class _RecordingSession:
    """An AsyncSession stand-in that records every statement `build_league`
    executes and answers each with an empty result set.

    Empty is the right answer here: the rails are what this file is about, and a
    league with no games still has to ASK for them with the fenced statement.
    """

    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return _EmptyResult()


def _build(sport_key: str) -> _RecordingSession:
    session = _RecordingSession()
    payload = asyncio.run(build_league(sport_key, session))
    assert isinstance(payload, dict)
    return session


def test_build_league_emits_the_fenced_statement_for_the_results_rail():
    """The wiring proof. A builder that compiles the right SQL while the route
    keeps an inline copy of the old one is green everywhere else in this file.

    TWO fenced statements since #3211, not one: the past is now two rails, and
    `unreported_games_query` is the same shape of question as the results one,
    so it carries the same fence for the same measured reason. The count is
    asserted exactly rather than loosened to `>= 1` — that would have let the
    original defect this test exists for (an inline copy beside a correct
    helper) come back through the new rail."""
    session = _build("americanfootball_cfl")

    fenced = [s for s in session.statements if "LIMIT ALL OFFSET 0" in s]
    assert len(fenced) == 2, (
        "expected exactly two fenced statements from build_league — the "
        "results rail and #3211's unreported rail — got "
        f"{len(fenced)} of {len(session.statements)}"
    )
    for statement in fenced:
        assert "events.commence_time" in statement
        assert re.search(r"ORDER BY anon_\d+\.commence_time DESC", statement)


def test_build_league_still_emits_an_unfenced_upcoming_statement():
    """Both directions (gotcha #43): the fence must appear on ONE rail, and the
    other rail must still be issued — a refactor that dropped the games query
    entirely would pass the test above."""
    session = _build("americanfootball_cfl")

    upcoming = [
        s
        for s in session.statements
        if _CASE_ORDER.search(s) and "OFFSET" not in s.upper()
    ]
    assert len(upcoming) == 1, (
        "the upcoming-games rail statement is missing or grew a fence: "
        f"{len(upcoming)} candidates in {len(session.statements)} statements"
    )


def test_build_league_issues_exactly_four_statements():
    """One futures query and the three rails. A FIFTH would mean the fence had
    been paid for with an extra round trip — the sport_id-resolving form of this
    fix, which was measured and rejected in favour of keeping the join.

    Was three; #3211 split the past into settled and unreported, and one more
    round trip is the honest price of that split. It is priced rather than
    assumed: the alternative was one shared cap, and that cost every real result
    on the page (see `unreported_rail_condition`). An exact count, still, so the
    next rail has to argue for its own round trip too."""
    session = _build("americanfootball_cfl")
    assert len(session.statements) == 4, session.statements


@pytest.mark.parametrize(
    "sport_key",
    ["americanfootball_cfl", "basketball_ncaab", "soccer_epl", "baseball_mlb"],
)
def test_every_league_gets_the_fence(sport_key: str):
    """The fence is not conditional on the league. The quiet ones are exactly
    the ones that pay for its absence, so a per-league opt-in would protect the
    leagues that never needed protecting."""
    session = _build(sport_key)
    assert any("LIMIT ALL OFFSET 0" in s for s in session.statements)
