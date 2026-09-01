"""Q496 — the four CERT-664 follow-ups on the Q495 drain, plus the prose defect.

PILLAR: MATCHING. SHIP: the operator draining the Table Tennis backlog can page
to the END of it without the rail silently restarting, timing out with no body,
or refusing to admit it has finished.

WHY THIS FILE EXISTS SEPARATELY FROM THE Q495 GUARDS
====================================================

`test_repair_polymarket_sport_category_q495.py` is 16 guards and CERT-664 graded
them thorough — on CLASSIFICATION and REGISTRATION. Its own gap, named by the
cert: **not one of them executes `repair()`.** Target selection, the
compare-and-set UPDATE, the commit, the cursor and every terminal were covered
only by reading the source, and a source assertion passes just as happily on a
dead call site. Every test below that touches the pager therefore RUNS the
function against a recording session and asserts on the SQL and parameters the
rail actually issued.

The four defects, and the shape each guard has to have to be worth anything:

* ``Q495-REQUEST-BUDGET-UNDER-H12`` — the failure is invisible from inside the
  process: Heroku returns H12 with **no body**, so the operator loses
  ``next_cursor`` and the drain loses its place. Nothing in-process can observe
  that, so this is guarded as an ARITHMETIC INVARIANT over the constants,
  recomputed here rather than restated, plus a behavioural check that the
  per-fetch timeout really is the constant.
* ``Q495-EXECUTABLE-REPAIR-GUARD`` — behavioural, by construction.
* ``Q495-TRUE-REMAINING-TERMINAL`` — needs BOTH arms. A guard that only asserts
  ``complete`` is reachable would pass on a rail that returns ``complete``
  always; the drained arm and the mid-drain arm are both here.
* ``Q495-NULL-DATE-CURSOR`` — the old gate produced NO keyset clause at all, so
  the assertion has to be that a clause is PRESENT and names the null region,
  not merely that the call succeeded. A call with a dropped cursor succeeds
  perfectly; that is the whole bug.

And the prose defect (`Q495-DOC-CURSOR-NAME`): the registration comment
documented ``?after_commence=``, a param the dispatcher does not declare.
FastAPI drops an unknown query param SILENTLY, so an operator following the
comment would re-read page one forever. Fixing the two words is not the guard —
`test_no_comment_names_a_param_the_dispatcher_cannot_pass` is, and it covers
every repair in the file, not just this one.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.tasks import repair_polymarket_sport_category as rail


# ---------------------------------------------------------------------------
# Recording session — the rail runs against this, it is not stubbed out.
# ---------------------------------------------------------------------------


class _Row:
    """One aggregated EVENT row, shaped like the target query's output."""

    def __init__(self, event_id, commence_time, anchor_id, markets=3):
        self.event_id = event_id
        self.commence_time = commence_time
        self.anchor_id = anchor_id
        self.markets = markets


class _Ts:
    """A stand-in for a timestamptz whose `.isoformat()` the cursor calls."""

    def __init__(self, s):
        self._s = s

    def isoformat(self):
        return self._s


class _Result:
    def __init__(self, rows=(), scalar=0):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Update:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _Session:
    """Records every statement and parameter set the rail issues.

    Routes by the statement's own shape rather than by call ORDER, so a rail
    that reorders its queries is still measured correctly instead of silently
    reading a target list as a count.
    """

    def __init__(self, targets=(), remaining=0, update_rowcount=5):
        self.targets = list(targets)
        self.remaining = remaining
        self.update_rowcount = update_rowcount
        self.statements: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    @property
    def target_sql(self) -> str:
        """The one statement that selected the page. Raises if it never ran."""
        for sql, _params in self.statements:
            if "LIMIT :cap" in sql:
                return sql
        raise AssertionError(
            "the rail never issued its target query — every pager assertion in "
            f"this test would be vacuous. Statements seen: {self.statements!r}"
        )

    @property
    def target_params(self) -> dict:
        for sql, params in self.statements:
            if "LIMIT :cap" in sql:
                return params
        raise AssertionError("the rail never issued its target query")

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, dict(params or {})))
        upper = sql.upper()
        if upper.startswith("UPDATE"):
            self.writes.append((sql, dict(params or {})))
            return _Update(self.update_rowcount)
        # Routed on the page limit, which only the target query carries — not on
        # a leading keyword, which a harmless SQL reshape would change.
        if "LIMIT :cap" in sql:
            return _Result(rows=self.targets)
        if upper.startswith("SELECT COUNT("):
            return _Result(scalar=self.remaining)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def fast(monkeypatch):
    """Remove the deliberate venue pause so the suite is not paced by it.

    Patched on the module rather than on `asyncio`, because the constant is read
    at call time. `test_the_venue_pause_is_real_in_production` keeps the real
    value honest, so this fixture cannot hide its removal.
    """
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


def _venue(monkeypatch, answers: dict[str, tuple[str, dict | None]]):
    """Make the venue answer from a dict keyed by event id.

    Patches `_fetch_event`, not the HTTP client, so the rail's real
    `httpx.AsyncClient` lifecycle still runs and a test can never accidentally
    reach the network.
    """
    seen: list[str] = []

    async def _fake(_client, event_id):
        seen.append(str(event_id))
        return answers[str(event_id)]

    monkeypatch.setattr(rail, "_fetch_event", _fake)
    return seen


#: The two payloads Q495 pinned as its oracle, reused so the two files cannot
#: drift about what the venue says.
_TENNIS = ("ok", {"title": "US Open ATP: A vs B", "tags": [{"label": "Tennis"}],
                  "markets": [{"question": "US Open ATP: A vs B"}]})
_SETKA = ("ok", {"title": "N vs. V", "tags": [{"label": "Table Tennis"}],
                 "markets": [{"question": "N vs. V"}]})


# ---------------------------------------------------------------------------
# Q495-REQUEST-BUDGET-UNDER-H12
# ---------------------------------------------------------------------------


def test_the_worst_case_request_fits_under_the_router_wall():
    """The deadline is checked at the TOP of the loop, so it is not the bound.

    After the deadline passes the rail may still start one whole fetch and one
    whole pause — and after THAT returns it still has to write, commit, count
    and serialize. The old constants (55 + 25 + 0.35 = 80.35s against a 30s
    wall) failed by a factor of two and a half; an over-running call returned
    H12 with NO BODY, so the operator lost the cursor and the drain lost its
    place.

    CERT-666 (P2) added the fourth term. ``DEADLINE + FETCH_TIMEOUT +
    VENUE_PAUSE`` was a SUBTOTAL being reported as a worst case: it stopped
    counting at the last fetch, and so advertised 1.65s of headroom the rail did
    not have. The post-loop write, commit and terminal count are real request
    time and are now reserved.

    Recomputed here from the constants rather than restated, so raising any one
    of them fails this test instead of quietly re-opening the hole.
    """
    worst_case = (
        rail.DEADLINE_SECONDS
        + rail.FETCH_TIMEOUT_SECONDS
        + rail.VENUE_PAUSE
        + rail.POST_LOOP_RESERVE_SECONDS
    )
    assert worst_case < rail.ROUTER_WALL_SECONDS, (
        f"worst-case request is {worst_case}s against a "
        f"{rail.ROUTER_WALL_SECONDS}s router wall — an over-run returns H12 "
        f"with no body and the attended drain loses its place"
    )
    # And the helper the rail reports in its own response body agrees with the
    # arithmetic, so an operator reading `budget.worst_case_headroom_s` is
    # reading this same invariant and not a second, drifting copy of it.
    assert rail.budget_headroom_seconds() == pytest.approx(
        rail.ROUTER_WALL_SECONDS - worst_case
    )
    assert rail.budget_headroom_seconds() > 0
    # The terminal count's slice is carved OUT of the post-loop reserve, never
    # added beside it — if it were larger, arming the count's statement timeout
    # would hand it time already promised to the write, the commit and the
    # serialization that still have to happen.
    assert 0 < rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS < rail.POST_LOOP_RESERVE_SECONDS


def test_the_documented_default_page_cannot_spend_the_budget_on_sleep_alone():
    """The default `limit` was the case most likely to fail, which is the worst
    place for it: an operator who follows the instructions verbatim hits H12 and
    reads a correct rail as broken.

    At the old cap of 60 the deliberate sleep alone was 21s of a 30s wall,
    before one byte of HTTP or DB time.
    """
    sleep_only = rail.APPLY_EVENT_CAP * rail.VENUE_PAUSE
    assert sleep_only < rail.DEADLINE_SECONDS / 2, (
        f"a default-sized page spends {sleep_only}s sleeping out of a "
        f"{rail.DEADLINE_SECONDS}s loop deadline — the cap, not the work, is "
        f"the thing consuming the budget"
    )


def test_the_venue_pause_is_real_in_production():
    """The `fast` fixture zeroes the pause; this stops that from hiding a rail
    that shipped with no rate-limit courtesy at all."""
    assert rail.VENUE_PAUSE > 0


@pytest.mark.asyncio
async def test_the_fetch_uses_the_bounded_timeout_constant():
    """Behavioural, not a source scan: a literal `timeout=25` in the call would
    carry a single request past the wall no matter what the loop deadline says,
    and reading the source cannot tell you what was actually passed."""
    passed: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"title": "x"}

    class _Client:
        async def get(self, _url, **kwargs):
            passed.update(kwargs)
            return _Resp()

    status, _payload = await rail._fetch_event(_Client(), "1")
    assert status == "ok"
    assert passed.get("timeout") == rail.FETCH_TIMEOUT_SECONDS
    assert passed["timeout"] < rail.ROUTER_WALL_SECONDS - rail.DEADLINE_SECONDS


def test_the_census_worst_case_also_fits_under_the_router_wall():
    """The census runs TWO scans under ONE wall, so its bound is 2x its timeout.

    At the old `'25s'` its own permitted worst case was 50s against a 30s wall.
    That is worse than it looks: the census's entire reason for having a
    try/except is gotcha #54 — report `measured: false`, never a comforting
    zero — and an H12 returns NO BODY, so the honest answer never reaches the
    operator at exactly the moment it is needed.
    """
    assert 2 * rail.CENSUS_STATEMENT_TIMEOUT_SECONDS < rail.ROUTER_WALL_SECONDS


class _FailingSession(_Session):
    """Fails the Nth query, to place a timeout precisely."""

    def __init__(self, fail_on: int, **kw):
        super().__init__(**kw)
        self.fail_on = fail_on
        self.n = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if not sql.upper().startswith("SET "):
            self.n += 1
            if self.n == self.fail_on:
                raise RuntimeError("canceling statement due to statement timeout")
        return await super().execute(stmt, params)


@pytest.mark.parametrize("fail_on", [1, 2])
@pytest.mark.asyncio
async def test_either_census_query_timing_out_is_measured_false_not_a_500(fail_on):
    """`fail_on=2` is the Q496 regression: the distinct-count query sat OUTSIDE
    the try, so a timeout there escaped, the dispatcher turned it into a 500,
    and the `measured: false` contract was never reached. `fail_on=1` is the
    control — it passed before this change and must still pass, or the guard
    proves nothing about which arm was fixed."""
    s = _FailingSession(fail_on=fail_on)

    out = await rail.census(s)

    assert out["measured"] is False, (
        f"a timeout on census query {fail_on} did not produce the honest "
        f"`measured: false` answer"
    )
    assert "timeout" in out["reason"]
    assert "markets" not in out, "a census that could not look reported a count"
    assert s.commits == 0


@pytest.mark.asyncio
async def test_the_census_bounds_itself_with_the_constant():
    """Behavioural: the SET must reach the session, carrying the constant."""
    s = _Session()

    await rail.census(s)

    sets = [sql for sql, _p in s.statements if sql.upper().startswith("SET ")]
    assert sets, "the census issued no statement_timeout at all"
    assert f"'{rail.CENSUS_STATEMENT_TIMEOUT_SECONDS}s'" in sets[0]


# ---------------------------------------------------------------------------
# Q495-EXECUTABLE-REPAIR-GUARD — these RUN repair()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_finds_the_change_and_writes_absolutely_nothing(fast, monkeypatch):
    s = _Session(targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=4)],
                 remaining=40)
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=False)

    assert out["counts"]["events_examined"] == 1
    assert out["counts"]["changed"] == 1
    assert out["changed_to"] == {"tennis": 1}
    assert out["terminal"] == "dry_run"
    assert out["applied"] is False
    assert s.writes == [], "a dry run issued an UPDATE"
    assert s.commits == 0, "a dry run committed"
    assert out["counts"]["markets_written"] == 0


@pytest.mark.asyncio
async def test_apply_issues_a_compare_and_set_update_and_commits(fast, monkeypatch):
    """The predicate is IN the statement, not a re-read before it.

    A concurrent re-ingest may have already corrected the row between the
    dry-run's verdict and this write; `llm_sport_category = :cat_old` is what
    stops a stale verdict clobbering a fresher correct one.
    """
    s = _Session(targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=3)],
                 remaining=40, update_rowcount=7)
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert len(s.writes) == 1, f"expected exactly one UPDATE, got {s.writes!r}"
    sql, params = s.writes[0]
    assert "llm_sport_category = :cat_old" in sql, (
        "the write is no longer compare-and-set — a verdict computed before a "
        "concurrent re-ingest would clobber it"
    )
    assert params["cat_old"] == rail.SUSPECT_CATEGORY
    assert params["llm"] == "tennis"
    assert params["eid"] == "924377"
    # Scope: this rail moves a category and nothing else.
    for forbidden in ("is_winner", "probability", "resolution", "outcome"):
        assert forbidden not in sql.lower(), f"the write touches {forbidden}"
    assert s.commits == 1
    assert out["applied"] is True
    assert out["terminal"] == "changed"


@pytest.mark.asyncio
async def test_markets_written_is_the_update_rowcount_not_the_target_count(fast, monkeypatch):
    """`markets` on the target row and the rows the UPDATE actually moved are
    different numbers, and reporting the former would make a compare-and-set
    that matched NOTHING look like a successful write."""
    s = _Session(targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=3)],
                 remaining=40, update_rowcount=0)
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["counts"]["markets_written"] == 0, (
        "a compare-and-set that matched no rows was reported as a write"
    )
    assert out["counts"]["changed"] == 1


@pytest.mark.asyncio
async def test_the_setka_control_rides_the_same_path_and_is_never_written(fast, monkeypatch):
    """Setka is INSIDE the population, not excluded from it. `unchanged` rising
    is the rail proving it is safe; a run that changes everything is as suspect
    as one that changes nothing."""
    s = _Session(
        targets=[
            _Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("945534", _Ts("2026-08-30T17:00:00+00:00"), 22),
        ],
        remaining=40,
    )
    seen = _venue(monkeypatch, {"924377": _TENNIS, "945534": _SETKA})

    out = await rail.repair(s, apply=True)

    assert seen == ["924377", "945534"], "Setka was skipped rather than examined"
    assert out["counts"]["unchanged"] == 1
    assert out["counts"]["changed"] == 1
    assert [p["eid"] for _sql, p in s.writes] == ["924377"], (
        "the control event was written — the #1230 half of Q493 is broken"
    )


@pytest.mark.parametrize(
    "answer,bucket",
    [
        (("indeterminate", None), "indeterminate"),
        (("not_at_venue", None), "not_at_venue"),
        (("ok", {"title": "x", "tags": [], "markets": []}), "refused_other"),
    ],
)
@pytest.mark.asyncio
async def test_a_venue_that_did_not_answer_clearly_is_counted_and_never_written(
    fast, monkeypatch, answer, bucket
):
    """Each non-answer is a DIFFERENT real state with its own counter, and none
    of them may reach the database. A rate limit recorded as a category verdict
    is gotcha #36 exactly."""
    s = _Session(targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40)
    _venue(monkeypatch, {"1": answer})

    out = await rail.repair(s, apply=True)

    assert out["counts"][bucket] == 1
    assert out["counts"]["changed"] == 0
    assert s.writes == [], f"{bucket} reached the database"
    assert s.commits == 0


@pytest.mark.asyncio
async def test_limit_above_the_cap_is_clamped_in_the_statement(fast, monkeypatch):
    """Behavioural: the clamp has to reach the SQL, not merely exist in a local."""
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(s, apply=False, limit=999)

    assert s.target_params["cap"] == rail.APPLY_EVENT_CAP
    assert out["cap"] == rail.APPLY_EVENT_CAP


@pytest.mark.asyncio
async def test_the_deadline_stops_the_loop_and_names_where_it_stopped(fast, monkeypatch):
    """An over-run must return a partial answer that says so, not a clean-looking
    short page — which `scan_exhausted` would otherwise read as "finished"."""
    monkeypatch.setattr(rail, "DEADLINE_SECONDS", -1)
    s = _Session(targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40)
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["stopped_before"] == "event_id=924377"
    assert out["counts"]["events_examined"] == 0
    assert s.writes == []
    assert out["scan_exhausted"] is False, (
        "a page abandoned on the deadline was reported as an exhausted scan — "
        "the operator would stop draining with work still queued"
    )
    assert out["terminal"] == "no_work"


# ---------------------------------------------------------------------------
# Q495-NULL-DATE-CURSOR — and the aggregate-vs-raw-row defect fixing it exposed
# ---------------------------------------------------------------------------


def _keyset_clause(sql: str) -> str:
    """The text the rail put between `WHERE TRUE` and `ORDER BY`.

    Isolating it matters: the bug being guarded produced an EMPTY clause, and a
    call with no keyset succeeds perfectly while re-reading page one — so
    "the query ran" proves nothing and only the clause's presence does.
    """
    m = re.search(r"WHERE TRUE(.*?)ORDER BY", sql, re.IGNORECASE)
    assert m, f"target query no longer has the expected shape: {sql!r}"
    return m.group(1).strip()


@pytest.mark.asyncio
async def test_the_first_call_has_no_keyset(fast, monkeypatch):
    """The positive control for the two tests below. Without it they would pass
    on a rail that emits its keyset unconditionally."""
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    await rail.repair(s, apply=False)

    assert _keyset_clause(s.target_sql) == ""
    assert "after_id" not in s.target_params


@pytest.mark.asyncio
async def test_the_cursor_the_rail_emits_pages_the_next_call(fast, monkeypatch):
    """Round-trip, because the two halves were written apart and drifted before.

    The emitted `next_cursor` is fed straight back in and the second call must
    carry it into the SQL. This is the behavioural form of the `after_commence`
    defect: a cursor the dispatcher cannot pass produces a call that looks
    identical to this one and pages nowhere.
    """
    s1 = _Session(targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40)
    _venue(monkeypatch, {"924377": _TENNIS})
    first = await rail.repair(s1, apply=False)

    cursor = first["next_cursor"]
    assert cursor == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}
    # The cursor's keys must be exactly the parameter names `repair` accepts,
    # or an operator pasting it back gets it silently dropped by FastAPI.
    accepted = inspect.signature(rail.repair).parameters
    for key in cursor:
        assert key in accepted, (
            f"next_cursor emits {key!r}, which repair() does not accept — the "
            f"dispatcher would drop it and the drain would restart at page one"
        )

    s2 = _Session(targets=[], remaining=40)
    await rail.repair(s2, apply=False, **cursor)

    clause = _keyset_clause(s2.target_sql)
    assert clause, "the emitted cursor produced no keyset at all"
    assert s2.target_params["after_id"] == 11
    assert s2.target_params["after_date"] == "2026-08-30T18:00:00+00:00"
    # NULLS LAST puts the whole null region after us, so it must remain
    # reachable from a non-null cursor rather than being filtered away.
    assert "IS NULL" in clause.upper(), (
        "a non-null cursor excludes the null-commence_time region entirely, so "
        "those events can never be reached by paging"
    )


@pytest.mark.asyncio
async def test_a_null_date_cursor_still_activates_the_keyset(fast, monkeypatch):
    """The defect: the gate required a truthy `after_date`.

    `NULLS LAST` puts null-`commence_time` events at the very end of the scan,
    and their cursor carries `after_date: None`. Under the old gate the keyset
    never activated, the next call re-read page ONE, and the drain looped
    forever on rows it had already done — while every response looked healthy.
    """
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    await rail.repair(s, apply=False, after_date=None, after_id=99)

    clause = _keyset_clause(s.target_sql)
    assert clause, (
        "a null-date cursor produced NO keyset — the call succeeds and silently "
        "restarts at page one, which is the bug, not the absence of one"
    )
    assert "IS NULL" in clause.upper()
    assert s.target_params["after_id"] == 99
    assert "after_date" not in s.target_params


@pytest.mark.asyncio
async def test_a_null_commence_time_target_emits_a_usable_cursor(fast, monkeypatch):
    """The other half: the rail must EMIT the cursor the test above accepts."""
    s = _Session(targets=[_Row("924377", None, 11)], remaining=40)
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=False)

    assert out["next_cursor"] == {"after_date": None, "after_id": 11}


@pytest.mark.asyncio
async def test_the_keyset_filters_the_aggregate_not_the_raw_market_rows(fast, monkeypatch):
    """The cursor names two AGGREGATES; filtering their INPUTS filters a
    different quantity.

    An event whose markets straddle the page boundary would lose some rows,
    recompute a different `max(commence_time)`, and move in the ordering between
    pages — a keyset that both repeats events and skips them. Asserted on the
    SQL the rail actually issued, so it cannot be satisfied by a comment.
    """
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    await rail.repair(s, apply=False, after_date="2026-08-30T18:00:00+00:00", after_id=11)

    sql = s.target_sql
    clause = _keyset_clause(sql)
    assert "ev.anchor_id" in clause and "ev.commence_time" in clause, (
        f"the keyset does not name the aggregated columns: {clause!r}"
    )
    inner = sql[: sql.upper().index("WHERE TRUE")]
    assert "GROUP BY" in inner.upper(), "the aggregation no longer precedes the cursor"
    assert "after_date" not in inner and "after_id" not in inner, (
        "the cursor is being applied to the raw market rows, before the "
        "aggregation whose output it names"
    )


# ---------------------------------------------------------------------------
# Q495-TRUE-REMAINING-TERMINAL — both arms, or the guard is worthless
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_drained_population_says_complete_even_though_setka_remains(fast, monkeypatch):
    """The defect: `terminal="complete"` keyed on `remaining_events == 0`.

    `remaining_events` counts the suspect CATEGORY, which legitimately contains
    the Setka control this rail deliberately never moves — so it has a positive
    floor, zero is unreachable, and the success arm was dead code. A finished
    drain reported `no_work`, which reads as "your cursor is wrong".
    """
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(s, apply=True)

    assert out["scan_exhausted"] is True
    assert out["remaining_events"] == 40
    assert out["terminal"] == "complete", (
        "an exhausted scan still reports no_work while legitimate table-tennis "
        "rows remain — the operator can never tell finished from broken"
    )
    assert "remaining_events_note" in out, (
        "the floor is not explained, so a reader treats 40 as a backlog"
    )


@pytest.mark.asyncio
async def test_a_full_page_is_never_reported_as_an_exhausted_scan(fast, monkeypatch):
    """The other arm. A page that came back AT the cap may have more behind it,
    so exhaustion is not provable and the operator must keep paging."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 2)
    s = _Session(
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _SETKA, "2": _SETKA})

    out = await rail.repair(s, apply=True)

    assert out["counts"]["events_examined"] == 2
    assert out["scan_exhausted"] is False, (
        "a page returned at the cap was called exhausted — the operator stops "
        "with the rest of the population untouched"
    )
    assert out["terminal"] == "examined_no_change"


@pytest.mark.asyncio
async def test_a_short_page_of_confirmations_is_the_finished_state(fast, monkeypatch):
    """The end of a real drain: the last page is short, everything on it is
    confirmed in place, and nothing changed. That must read as DONE, not as the
    same `examined_no_change` a mid-drain page of Setka produces."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(targets=[_Row("945534", _Ts("2026-08-30T17:00:00+00:00"), 22)], remaining=40)
    _venue(monkeypatch, {"945534": _SETKA})

    out = await rail.repair(s, apply=True)

    assert out["counts"]["unchanged"] == 1
    assert out["scan_exhausted"] is True
    assert out["terminal"] == "examined_no_change_complete"
    assert s.writes == []


# ---------------------------------------------------------------------------
# Q495-DOC-CURSOR-NAME — the class, not the two words
# ---------------------------------------------------------------------------


def test_no_comment_names_a_query_param_the_dispatcher_cannot_pass():
    """The Q495 defect was PROSE inside a certified diff, and no gate saw it.

    `admin_repairs.py` documents each repair's params in a comment above its
    registration. Q495's said `?after_commence=`, which `run_repair` does not
    declare — and FastAPI drops an unknown query param SILENTLY, so an operator
    following the comment gets an inactive keyset and re-reads page one forever
    while the response looks perfectly busy.

    This guards the whole file rather than the one comment: any repair whose
    documented param the dispatcher cannot forward fails the build.
    """
    import app.routes.admin_repairs as mod

    src = inspect.getsource(mod)
    assert len(src) > 5000, "source unexpectedly short — this guard would be vacuous"

    declared = set(inspect.signature(mod.run_repair).parameters)
    documented = set(re.findall(r"[?&]([a-zA-Z_][a-zA-Z0-9_]*)=", src))

    # Non-vacuity in BOTH directions: the scan must actually be finding params,
    # and it must be finding the ones this repair's own comment names.
    assert len(documented) >= 5, (
        f"the param scan found only {documented!r} — the comment convention "
        f"changed and this guard has stopped seeing its subject"
    )
    assert {"limit", "after_date", "after_id"} <= documented

    undeclarable = sorted(documented - declared)
    assert not undeclarable, (
        f"these params are documented in admin_repairs.py comments but "
        f"{undeclarable} are not declared by run_repair(), so FastAPI will drop "
        f"them silently and an operator following the docs gets a call that "
        f"looks busy and does nothing"
    )


def test_the_q495_registration_comment_names_the_real_cursor():
    """The specific regression, kept alongside the class guard.

    The class guard above would also pass if someone deleted the comment
    entirely; this asserts the operator-facing instruction still exists and is
    the correct one.

    Matched on the PARAM FORM (`?name=` / `&name=`), not the bare word, because
    the block deliberately still discusses `after_commence` in prose — naming
    the trap is how the next reader avoids re-introducing it, and a guard that
    banned the word would delete its own explanation.
    """
    import app.routes.admin_repairs as mod

    src = inspect.getsource(mod)
    block = src[src.index('"polymarket-sport-category-census"') - 4000 :
                src.index('"polymarket-sport-category":')]
    assert re.search(r"[?&]after_commence=", block) is None, (
        "the registration comment documents `after_commence` as a query param "
        "again — the dispatcher does not declare it and FastAPI drops it silently"
    )
    assert re.search(r"[?&]after_date=", block), (
        "the block no longer tells the operator the cursor's real name"
    )


def test_the_rail_still_refuses_to_learn_a_sport_rule():
    """Q496 rewrote the pager and the budget. It must not have smuggled a sport
    rule in with them — re-asserted here because the Q495 guard was written
    against the old file and a reader could reasonably assume it lapsed."""
    import ast

    src = inspect.getsource(rail)
    # Prose in docstrings legitimately says "US Open" at length; executable code
    # may not. Split them with the AST rather than a regex, because a regex over
    # Python source is how a guard like this quietly stops seeing half its
    # subject.
    tree = ast.parse(src)
    literals = [
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc.lower())
    code_literals = [lit for lit in literals if lit not in docstrings]
    assert code_literals, "no non-docstring literals found — guard would be vacuous"
    for banned in ("us open", "atp", "wta", "setka", "wimbledon"):
        offenders = [lit for lit in code_literals if banned in lit]
        assert not offenders, (
            f"the rail has grown a sport rule of its own via {banned!r}: "
            f"{offenders[:3]}"
        )


# ---------------------------------------------------------------------------
# CERT-666 (P1) — a transient venue failure must never be reported as a
# finished drain, and must never be left behind an advanced cursor.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transient_failure_on_a_short_page_is_not_a_finished_drain(fast, monkeypatch):
    """THE CERT-666 DEFECT, reproduced.

    A short page (so no row sorts after it) whose LAST event the venue fails to
    answer for. Before the fix this reported `scan_exhausted=true` and a terminal
    reading "this was the LAST page, so the drain is finished" — while the failed
    event sat unchanged in the suspect category, still mis-filed, still hidden
    from the user, and behind a cursor that guaranteed nothing would look at it
    again.

    A 429/5xx/timeout is not a verdict, and this is the whole ship: the drain may
    only say it reached the end when it actually did.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _SETKA, "2": ("indeterminate", None)})

    out = await rail.repair(s, apply=True)

    assert out["counts"]["indeterminate"] == 1
    assert out["scan_exhausted"] is False, (
        "a short page is NOT an exhausted scan when an event on it went "
        "unresolved — page length proves nothing sorts after the page, not that "
        "everything in it was answered"
    )
    assert out["terminal"] == "paused_unresolved", (
        f"terminal is {out['terminal']!r}; a run holding an unresolved event "
        f"must not present as any kind of completion"
    )
    assert out["stopped_at_unresolved"] == "event_id=2"
    assert "complete" not in out["terminal"]
    assert "finished" not in out["reason"].lower()


@pytest.mark.asyncio
async def test_the_cursor_stops_before_the_unresolved_event_not_after_it(fast, monkeypatch):
    """The cursor is a watermark over RESOLVED work.

    It used to be assigned before the fetch, so it moved past an event the venue
    never answered for. It must name the last event that actually got an answer.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _SETKA, "2": ("indeterminate", None)})

    out = await rail.repair(s, apply=True)

    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}, (
        "the cursor advanced past the event the venue did not answer for — "
        "re-running would skip it forever"
    )


@pytest.mark.asyncio
async def test_the_unresolved_event_is_revisited_by_the_cursor_it_emits(fast, monkeypatch):
    """Two calls, end to end: the cursor from the paused call must bring the
    failed event BACK, and only then may the drain report completion.

    This is the guard CERT-666 asked for. The first call's emitted cursor is fed
    straight back in — not a hand-built one — so an off-by-one in the watermark
    shows up as the failed event never being re-fetched.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    row1 = _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)
    row2 = _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12)

    s1 = _Session(targets=[row1, row2], remaining=40)
    _venue(monkeypatch, {"1": _SETKA, "2": ("indeterminate", None)})
    first = await rail.repair(s1, apply=True)
    assert first["terminal"] == "paused_unresolved"

    cursor = first["next_cursor"]
    assert cursor is not None
    # The emitted cursor must be spellable as repair()'s own parameters, or the
    # operator cannot feed it back at all (the Q495-DOC-CURSOR-NAME class).
    import inspect

    accepted = set(inspect.signature(rail.repair).parameters)
    for key in cursor:
        assert key in accepted, f"next_cursor emits {key!r}, which repair() cannot accept"

    # Page two: the keyset now excludes the resolved row1 but NOT row2.
    s2 = _Session(targets=[row2], remaining=40)
    seen = _venue(monkeypatch, {"2": _SETKA})
    second = await rail.repair(s2, apply=True, **cursor)

    assert "2" in seen, (
        "the event the venue failed on was never re-fetched — the drain skipped "
        "it permanently, which is the defect this guard exists for"
    )
    assert second["scan_exhausted"] is True, (
        "once every event resolves, the short page IS the end and the rail must "
        "still be able to say so — otherwise this fix traded a false completion "
        "for an unreachable one"
    )
    assert second["terminal"] == "examined_no_change_complete"


@pytest.mark.asyncio
async def test_a_first_event_failure_hands_back_the_cursor_it_was_given(fast, monkeypatch):
    """If nothing on the page resolves there is no new watermark — and returning
    `null` would read as "start over", silently sending an attended drain back to
    page one and re-walking everything it already did."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(targets=[_Row("9", _Ts("2026-08-30T12:00:00+00:00"), 90)], remaining=40)
    _venue(monkeypatch, {"9": ("indeterminate", None)})

    out = await rail.repair(
        s, apply=True, after_date="2026-08-30T18:00:00+00:00", after_id=11
    )

    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}, (
        "a page that resolved nothing dropped the operator's cursor — feeding "
        "the response back would restart the drain at page one"
    )
    assert out["terminal"] == "paused_unresolved"


@pytest.mark.asyncio
async def test_work_done_before_the_failure_is_kept_and_reported(fast, monkeypatch):
    """Pausing is not rolling back. Events resolved before the failure were
    written, and the operator must be able to see that rather than assume the
    whole page was lost."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _TENNIS, "2": ("indeterminate", None)})

    out = await rail.repair(s, apply=True)

    assert out["counts"]["changed"] == 1
    assert len(s.writes) == 1, "the resolved event's write was lost by the pause"
    assert s.commits == 1
    assert out["terminal"] == "paused_unresolved"


# ---------------------------------------------------------------------------
# CERT-666 (P2) — the terminal count was the last unbounded statement.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_terminal_count_is_armed_with_a_statement_timeout(fast, monkeypatch):
    """It ran after the deadline had already passed, with no bound of its own, so
    a lock or a bad plan could hold the request past the router wall on its own —
    costing the operator the H12-with-no-body this whole rail is shaped to
    avoid."""
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    await rail.repair(s, apply=False)

    # CERT-667 made this selection specific. It used to take the FIRST
    # statement_timeout in the request, which WAS the count's — until the page
    # SELECT got a bound of its own and became the first. The assertion then
    # passed while measuring an entirely different statement: still green, no
    # longer a guard on the thing it names. Anchor on the count itself.
    sqls = [sql for sql, _ in s.statements]
    count_at = next(
        (i for i, sql in enumerate(sqls) if sql.upper().startswith("SELECT COUNT(")),
        None,
    )
    assert count_at is not None, f"the terminal count never ran. Seen: {sqls!r}"
    preceding = [
        sql for sql in sqls[:count_at] if "STATEMENT_TIMEOUT" in sql.upper()
    ]
    assert preceding, (
        "the terminal count ran with no statement timeout. Statements seen: "
        f"{[sql[:60] for sql in sqls]}"
    )
    ms = int(preceding[-1].rsplit("=", 1)[1].strip())
    assert 0 < ms <= rail.ROUTER_WALL_SECONDS * 1000, (
        f"the count was armed with {ms}ms against a "
        f"{rail.ROUTER_WALL_SECONDS}s wall"
    )


@pytest.mark.asyncio
async def test_a_timing_out_terminal_count_is_unmeasured_not_zero_and_not_a_500(
    fast, monkeypatch
):
    """`remaining_events: 0` means drained. A count that never returned must not
    borrow that meaning, and must not take the response — and therefore the
    cursor — down with it (gotcha #53)."""

    class _CountDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if sql.upper().startswith("SELECT COUNT("):
                self.statements.append((sql, dict(params or {})))
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    s = _CountDies(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(s, apply=False)

    assert out["remaining_events_measured"] is False
    assert out["remaining_events"] is None, (
        "an unmeasured count reported a number — a reader cannot tell it from a "
        "real drain"
    )
    assert s.rollbacks == 1, (
        "a statement timeout aborts the whole TRANSACTION, so the session is "
        "unusable until it is rolled back"
    )
    # The cursor and the terminal still have to survive: losing them is the
    # failure the bound exists to prevent.
    assert "terminal" in out and "scan_exhausted" in out


@pytest.mark.asyncio
async def test_a_measured_terminal_count_still_says_so(fast, monkeypatch):
    """The positive control for the flag above — without it, a rail that always
    reported `measured: false` would pass the timeout test."""
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(s, apply=False)

    assert out["remaining_events_measured"] is True
    assert out["remaining_events"] == 40
    assert s.rollbacks == 0
