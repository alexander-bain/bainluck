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

from app.routes.league_futures import (
    RESULTS_LIMIT,
    RESULTS_LOOKBACK_DAYS,
    UPCOMING_GAMES_LIMIT,
    _recent_results_filters,
    _upcoming_games_filters,
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


def _sorts_outside_windows(sql: str) -> str:
    """``sql`` with every ``OVER ( … )`` clause removed.

    A window's own ``ORDER BY`` is not a sort the planner can satisfy from an
    index and stop early — the window must see its whole partition before it can
    emit anything — so it has to come out before the assertion below means what
    it says.

    Written as a paren MATCHER rather than a regex on purpose: the collapse's
    ``PARTITION BY`` contains a ``CASE WHEN (… IS NULL OR … IS NULL)``, so the
    clause nests two deep, and the obvious one-level regex silently fails to
    strip it — leaving the test asserting on text it believes it removed.
    """
    out = []
    i = 0
    while i < len(sql):
        j = sql.find("OVER (", i)
        if j == -1:
            out.append(sql[i:])
            break
        out.append(sql[i:j])
        depth = 0
        k = j + len("OVER ") - 1
        while k < len(sql):
            if sql[k] == "(":
                depth += 1
            elif sql[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        assert depth == 0, "unbalanced OVER( in the compiled statement"
        out.append(" ")
        i = k + 1
    return "".join(out)


def test_the_window_stripper_actually_strips_the_nested_clause():
    """The instrument, before the test that leans on it. A stripper that quietly
    matched nothing would make its sibling vacuous — and the first version of it
    did exactly that (a one-level regex against a two-level PARTITION BY)."""
    inside, _ = _split_on_fence(_sql(recent_results_query("baseball_mlb", NOW)))
    assert "OVER (" in inside, "no window to strip — the corpus changed"
    assert "OVER (" not in _sorts_outside_windows(inside)
    assert "row_number()" in _sorts_outside_windows(
        inside
    ), "the stripper ate more than the OVER clause"


def test_the_rails_sort_is_never_expressed_on_the_base_TABLE_column():
    """The whole mechanism, restated for the shape the rails now have (#2057).

    ⚠️ **THIS ASSERTION CHANGED, AND A GRADER SHOULD LOOK HERE FIRST.** It used
    to read "no ORDER BY anywhere inside the fenced subquery". That is no longer
    a statement about the hazard, because the duplicate collapse legitimately
    puts two sorts inside the fence: each window function's own ``ORDER BY``,
    and the ``ORDER BY … LIMIT 9`` that caps the COLLAPSED pool.

    The hazard was never "a sort exists". It is a sort PostgreSQL can satisfy
    from ``ix_events_commence_time`` by walking it until nine rows fall out —
    and that requires the sort to be expressed on ``events.commence_time``, the
    base table's own column. Once the sort reads a subquery alias sitting above
    a ``row_number() OVER (PARTITION BY …)``, no index can serve it and no row
    can be emitted before its partition is complete. That is a STRICTLY STRONGER
    barrier than the ``OFFSET 0`` node the planner declines to pull up.

    So: window ``ORDER BY``s are excused by name, and every remaining sort must
    name a subquery. Measured consequence on production, `tennis_atp`: the plan
    is a Bitmap Heap Scan feeding two WindowAggs at 402 blocks, not an index
    walk — full table in `recent_results_query`'s docstring.
    """
    sql = _sql(recent_results_query("baseball_mlb", NOW))
    inside, outside = _split_on_fence(sql)

    bare = _sorts_outside_windows(inside)
    assert "ORDER BY events.commence_time" not in bare, (
        "the rail's sort is expressed on the base table's own column inside the "
        "fence — that is exactly the index-ordered walk the fence exists to "
        "prevent, and it is reachable again"
    )
    for match in re.finditer(r"ORDER BY ([A-Za-z0-9_]+)\.", bare):
        assert match.group(1) != "events", match.group(0)

    # The outer sort is unchanged and still outside.
    assert re.search(
        r"ORDER BY anon_\d+\.commence_time DESC", outside
    ), "the outer sort must be on the SUBQUERY's commence_time column"
    assert "LIMIT" in outside.upper()


def test_the_collapse_stands_between_the_scan_and_every_sort():
    """The negative half of the test above: the barrier has to BE there.

    Excusing window ``ORDER BY``s is only safe while a window is what the sorts
    sit on top of. Delete the collapse and the excuse becomes a hole, so this
    asserts the window is present inside the fence — one test for the exemption,
    one for the thing that earns it.
    """
    inside, _ = _split_on_fence(_sql(recent_results_query("baseball_mlb", NOW)))
    assert "row_number() OVER (PARTITION BY" in inside, (
        "the duplicate collapse is gone from inside the fence — without it the "
        "sibling test's 'window ORDER BYs are excused' rule guards nothing"
    )
    assert "lag(events.commence_time) OVER (PARTITION BY" in inside


def test_the_fence_does_not_change_what_the_rail_asks_for():
    """Same filters, same window, same cap — only the plan moves. If a future
    edit changes the predicates while keeping the fence, this catches it."""
    sql = _sql(recent_results_query("icehockey_nhl", NOW), literal=True)

    assert "sports.key = 'icehockey_nhl'" in sql
    # The join moved INSIDE the collapse subquery (#2057) and SQLAlchemy renders
    # it with the operands the other way round there. The claim is that the rail
    # is scoped to one league through `sports`, not that one spelling survives.
    assert re.search(
        r"JOIN sports ON (sports\.id = events\.sport_id|events\.sport_id = sports\.id)",
        sql,
    ), "the league scope no longer joins through `sports`"
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


def test_the_two_rails_FILTER_on_different_statuses():
    """A live/scheduled rail and a completed/closed rail — the copy-paste guard.

    ⚠️ **THIS ASSERTION CHANGED TOO.** It used to read "`'completed'` does not
    appear anywhere in the upcoming rail's SQL". Since #2057 both rails carry
    the shared collapse, and the collapse carries `status_tier_expr()` — a CASE
    that MENTIONS `'completed'` and `'closed'` to LABEL a row's tier. The
    literal is now present in the upcoming rail's SQL and says nothing about
    what the rail selects, so a substring test can no longer tell a filter from
    a label and would pass or fail for the wrong reason either way.

    The claim is about the WHERE. It is asserted here on the filter clauses the
    rails are actually built from, and — because a clause list is not a rail —
    driven end to end against a corpus holding every status in
    `test_league_rails_dedup_2057.py::test_each_rail_admits_only_its_own_statuses`.
    That executing test is the real guard; this one keeps the cheap version
    honest about which side of the query it is reading.
    """
    upcoming = " ".join(
        str(
            c.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for c in _upcoming_games_filters("soccer_epl", NOW)
    )
    results = " ".join(
        str(
            c.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for c in _recent_results_filters("soccer_epl", NOW)
    )

    assert "'live'" in upcoming and "'scheduled'" in upcoming
    assert "'completed'" not in upcoming and "'closed'" not in upcoming
    assert "'completed'" in results and "'closed'" in results
    assert "'live'" not in results and "'scheduled'" not in results


@pytest.mark.parametrize(
    "query,cap",
    [
        (upcoming_games_query, UPCOMING_GAMES_LIMIT),
        (recent_results_query, RESULTS_LIMIT),
    ],
)
def test_the_inner_cap_breaks_ties_on_id(query, cap):
    """🔴 THE INNER SELECT DECIDES WHICH ROWS SURVIVE THE CAP, so its ordering
    needs the tiebreak just as much as the outer one — and this is a STATEMENT
    test on purpose, because the executing suite cannot see the difference.

    A mutation that dropped `collapsed.c.id.asc()` from the inner cap survived
    the whole behavioural suite: SQLite resolves the remaining tie by rowid, so
    the result stayed sorted and looked deterministic. PostgreSQL makes no such
    promise — that is the whole reason the tiebreak is there — and no test in
    this repository runs against it. The claim can only be asserted on the SQL.

    Anchored on the LAST ORDER BY term before the inner `LIMIT`, so it fails if
    the tiebreak is deleted OR demoted above `commence_time`.
    """
    sql = _sql(query("baseball_mlb", NOW), literal=True)
    stripped = _sorts_outside_windows(sql)

    inner = re.search(rf"ORDER BY ([^\n]*?)\s*\n?\s*LIMIT {cap + 1}\b", stripped)
    assert inner, f"no inner ORDER BY … LIMIT {cap + 1} found in the statement"
    terms = [t.strip() for t in inner.group(1).split(",")]
    assert terms[-1].endswith(".id ASC"), (
        "the inner cap's ordering does not END on an ascending id — tied rows "
        f"are cut by the plan's whim. Terms were: {terms}"
    )


@pytest.mark.parametrize(
    "query,cap",
    [
        (upcoming_games_query, UPCOMING_GAMES_LIMIT),
        (recent_results_query, RESULTS_LIMIT),
    ],
)
def test_EVERY_cap_in_the_statement_is_the_declared_constant_plus_one(query, cap):
    """Both LIMITs, not just one — and the second one is a COST claim.

    Since #2057 each rail carries two: the inner cap on the collapsed pool, and
    the outer cap on the hydrated rows. Only the outer one is visible in the
    result, so the executing suite cannot tell whether the inner one is right —
    two mutations that widened it to 10,000 returned identical rows and survived
    the entire behavioural band.

    The inner cap is nonetheless the whole reason this change is affordable.
    Widening it puts the plan back to hydrating every survivor before the sort
    discards them: measured on production, `tennis_atp`'s results rail runs
    `Index Scan events_pkey loops=9 blk=36` with the cap and `loops=968
    blk=3,882` without it. That is invisible to every test in this repository —
    there is no local Postgres — so it is pinned HERE, on the statement.

    `LIMIT ALL` (the fence's own) is excused by name; every other limit must be
    the declared constant.
    """
    sql = _sql(query("baseball_mlb", NOW), literal=True)
    limits = [m for m in re.findall(r"LIMIT (ALL|\d+)", sql) if m != "ALL"]

    assert len(limits) == 2, (
        f"expected exactly two caps (inner on the collapsed pool, outer on the "
        f"hydrated rows); found {limits}"
    )
    assert all(int(v) == cap + 1 for v in limits), (
        f"a cap is not the declared constant + 1 ({cap + 1}): {limits}. If the "
        f"inner one was widened, see this test's docstring — it is a plan "
        f"regression that no behavioural test can see."
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
