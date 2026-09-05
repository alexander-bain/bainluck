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
    UPCOMING_GAMES_LIMIT,
    build_league,
    recent_results_query,
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

    🔴 AMENDED BY #3211, AND THE AMENDMENT IS THE INTERESTING PART. This used to
    finish `assert "'scheduled'" not in results`, and that literal absence
    stopped being true: the recent rail now admits a `scheduled` row whose
    kickoff is more than `UPCOMING_GRACE` behind `now`, because such a row was
    on NEITHER rail and 171 US Open matches were invisible for a fortnight.

    The property the old line was reaching for — the two rails do not overlap
    and do not leave a gap — is not a statement about which words appear in
    which statement, and cannot be, now that both statements contain
    `'scheduled'`. It is a statement about ROWS, so it is asserted over rows in
    `test_the_two_rails_are_jointly_exhaustive_3211.py`, which executes both
    conditions against a status × time matrix.

    What survives here is what this file is actually for: the two builders have
    not been copy-pasted into each other. The upcoming rail must never name a
    settled state, and the recent rail must never name `live` — those two are
    still true, still cheap, and still the shape a careless edit would break.
    """
    upcoming = _sql(upcoming_games_query("soccer_epl", NOW), literal=True)
    results = _sql(recent_results_query("soccer_epl", NOW), literal=True)

    assert "'live'" in upcoming and "'scheduled'" in upcoming
    assert "'completed'" not in upcoming and "'closed'" not in upcoming
    assert "'completed'" in results and "'closed'" in results
    assert "'live'" not in results

    # #3211 — `'scheduled'` is now in BOTH, and the grace boundary is what keeps
    # them apart. Asserting it appears is not decoration: if a later edit drops
    # the arm, this test would otherwise go quiet while the gap re-opened.
    assert "'scheduled'" in results, (
        "the recent rail stopped admitting a past-kickoff `scheduled` row — "
        "that is #3211, and it puts every unsettled row back on no rail at all"
    )
    grace_edge = (NOW - UPCOMING_GRACE).strftime("%Y-%m-%d %H:%M:%S")
    assert grace_edge in results and grace_edge in upcoming, (
        "the two rails no longer split on the SAME grace boundary — one "
        "constant, or they overlap or leave a sliver between them"
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
    keeps an inline copy of the old one is green everywhere else in this file."""
    session = _build("americanfootball_cfl")

    fenced = [s for s in session.statements if "LIMIT ALL OFFSET 0" in s]
    assert len(fenced) == 1, (
        "expected exactly one fenced statement from build_league, got "
        f"{len(fenced)} of {len(session.statements)} — the route is not using "
        "recent_results_query()"
    )
    assert "events.commence_time" in fenced[0]
    assert re.search(r"ORDER BY anon_\d+\.commence_time DESC", fenced[0])


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


def test_build_league_issues_exactly_three_statements():
    """One futures query and the two rails. A fourth would mean the fence had
    been paid for with an extra round trip — the sport_id-resolving form of this
    fix, which was measured and rejected in favour of keeping the join."""
    session = _build("americanfootball_cfl")
    assert len(session.statements) == 3, session.statements


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
