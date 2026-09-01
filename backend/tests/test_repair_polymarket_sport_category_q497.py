"""Q497 — the two CERT-667 follow-ups on the Q496 drain, and the defect the
second one exposed.

PILLAR: TRUTH. SHIP (inherited from Q496 — this is a hardening queue riding an
already-shipped rail, not a new ship): the operator draining the Table Tennis
backlog can page to the END of it without the rail silently restarting, timing
out with no body, or refusing to admit it has finished.

WHY THIS FILE EXISTS
====================

CERT-667 granted Q496 r2 its token and named two follow-ups in the same breath,
explicitly noting that neither disproves the shipped rail. Both are the same
shape: **the rail derived a budget from the router wall, described what that
budget covered, and then did not enforce it over the two statements that touch
the database.**

* ``Q496-END-TO-END-DB-DEADLINE`` — the reserve was computed from remaining
  request time, but the DB half ran outside it. Two statements, both unbounded:
  the page SELECT (which runs BEFORE any deadline the rail checks, so nothing
  could interrupt it) and the compare-and-set UPDATE (which takes a row lock on
  ``futures_markets``, a table the ordinary poller also writes).
* ``Q496-CENSUS-SET-LOCAL`` — the census's ``SET statement_timeout`` was
  session-level, and ``get_db_rw`` COMMITS, so it survived onto a pooled
  connection and every later request inherited it.

And the third, found while fixing the second: bounding the UPDATE means the
UPDATE can now FAIL in a caught, recoverable way — and the cursor was still
being advanced before it. That is CERT-666 (P1)'s defect exactly, one statement
further along, and it would have been introduced BY the fix if it were not
handled here. **When you make a step failable, ask what already assumed it could
not fail.**

WHAT EACH GUARD HAS TO BE SHAPED LIKE TO BE WORTH ANYTHING
==========================================================

* The two timeouts are invisible from inside the process — an H12 returns no
  body — so they are guarded as BEHAVIOUR (the SET reaches the session, carrying
  the constant, before the statement it bounds) plus ARITHMETIC INVARIANTS over
  the constants, recomputed here rather than restated (gotcha: assert arithmetic
  FROM the constants, never a copied number).
* ``SET`` vs ``SET LOCAL`` is a one-word difference that changes nothing
  observable in a passing run — the leak is on the HEALTHY path — so the guard
  is a whole-module scan for a session-level ``SET``, not a check of the one line
  that was wrong. A guard on that line alone would be satisfied forever by the
  fix and would never see the next one.
* Every cursor guard needs the NEGATIVE arm. "The cursor is correct after a
  successful page" passes on a rail that never advances at all; "the cursor stops
  before the failure" passes on a rail that never advances at all too. Both arms
  are here, and the end-to-end pair feeds the emitted cursor straight back in
  rather than hand-building one.

ROUND TWO — CERT-670 (P1)
=========================

CERT-670 blocked the above and was right. Every bound this file guards is a
PostgreSQL ``statement_timeout``, and the statement that ARMS one is also the
statement that lazily checks a pooled connection out — against a pool whose
``pool_timeout`` is SQLAlchemy's 30s default, which is ``ROUTER_WALL_SECONDS``
exactly. So under saturation the rail could still burn the whole wall before any
bound existed and hand back the H12 with no body that it exists to prevent.
**A bound you can only install over the channel you are trying to bound is not
yet a bound.**

The round-two guards live in their own section at the foot of this file, with
their own note on what shape they had to take. Two things there are worth
carrying forward: the arithmetic is asserted on the DERIVED bound (asserting the
server bound while the client bound is what spends the time repeats the exact
"described but not enforced" gap), and the ranking guard reads the parse tree
rather than source line numbers, because a mutant that left the pool arm on the
first line and merely widened its condition de-ranked it completely while a
position check saw nothing wrong.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.tasks import repair_polymarket_sport_category as rail

# The recording session and the two pinned venue payloads are reused from the
# Q496 guards deliberately: three files asserting on the same rail must not drift
# about what a target row looks like or what the venue says. `fast` is redefined
# below rather than imported — importing a fixture shadows it at every use site.
from tests.test_repair_polymarket_sport_category_q496 import (
    _Row,
    _Session,
    _TENNIS,
    _Ts,
    _venue,
)


@pytest.fixture
def fast(monkeypatch):
    """Remove the deliberate venue pause so the suite is not paced by it.

    `test_the_venue_pause_is_real_in_production` (Q496) keeps the real value
    honest, so this cannot hide its removal.
    """
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


# ---------------------------------------------------------------------------
# Q496-CENSUS-SET-LOCAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_census_scopes_its_timeout_to_the_transaction():
    """A plain ``SET`` outlives the request that issued it.

    ``get_db_rw`` commits when the handler returns, and a session-level ``SET``
    inside a committed transaction becomes a property of the CONNECTION. The
    connection goes back to a pool of 20, so every later request that checks it
    out silently inherits a 12s ``statement_timeout``.

    Note which path leaked: the HEALTHY one. On a timeout the transaction is
    already aborted, the commit degrades to a rollback, and the ``SET`` goes with
    it — so the run that poisons the pool is the run that looks fine, which is
    why no stray cancellation was ever attributed to this line.
    """
    s = _Session()

    await rail.census(s)

    sets = [sql for sql, _p in s.statements if sql.upper().startswith("SET ")]
    assert sets, "the census issued no statement_timeout at all"
    assert sets[0].upper().startswith("SET LOCAL "), (
        f"the census issued a SESSION-level SET ({sets[0]!r}). It survives the "
        "commit `get_db_rw` makes and leaks onto the pooled connection."
    )
    # The bound itself must survive the scoping change — a `SET LOCAL` with the
    # wrong value is not a fix.
    assert f"'{rail.CENSUS_STATEMENT_TIMEOUT_SECONDS}s'" in sets[0]


def test_no_statement_this_rail_issues_is_a_session_level_set():
    """The general form, and the reason this is a module scan rather than a
    check of the one line that was wrong.

    A guard pinned to the census would be satisfied by the fix forever and would
    never see the next ``SET`` somebody adds. The whole point of the defect is
    that a session-level ``SET`` is invisible in the request that makes it and
    only hurts a LATER, unrelated one.
    """
    src = inspect.getsource(rail)
    # Only executable SQL: strip the prose, which discusses the bug using the
    # exact words being banned (a getsource guard goes vacuous when the docstring
    # quotes the thing it forbids).
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"(?m)^\s*#.*$", "", code)

    offenders = [
        m.group(0)
        for m in re.finditer(r'(?i)\bSET\s+(?!LOCAL\b)[a-z_]+\s*=', code)
    ]
    assert not offenders, (
        "a session-level SET reaches the pooled connection and outlives this "
        f"request: {offenders!r}. Use SET LOCAL."
    )


def test_set_local_is_only_safe_because_the_engine_is_not_in_autocommit():
    """``SET LOCAL`` outside a transaction block is a WARNING and a NO-OP.

    That failure mode is worse than the bug being fixed: it does not leak the
    bound, it REMOVES it, and silently. The fix is only correct while the session
    autobegins a real transaction, so the premise is asserted rather than
    assumed.
    """
    from app.services import database

    assert "AUTOCOMMIT" not in inspect.getsource(database).upper(), (
        "the engine or sessionmaker gained an AUTOCOMMIT isolation level. Every "
        "SET LOCAL in this rail silently became a no-op, so the census, the page "
        "SELECT and the UPDATE are all unbounded again."
    )


# ---------------------------------------------------------------------------
# Q496-END-TO-END-DB-DEADLINE — the arithmetic invariants
# ---------------------------------------------------------------------------


def test_the_page_select_budget_cannot_widen_the_worst_case():
    """``started`` is captured BEFORE the page SELECT, so its time already sits
    inside ``DEADLINE_SECONDS``' window: a slow SELECT does not add to the total,
    it just leaves the loop less room and the first deadline check stops it.

    That argument — and therefore ``budget_headroom_seconds()`` being unchanged
    by this constant — holds only while the SELECT cannot outlast the deadline
    itself. Asserted, because the two numbers are edited in different places.
    """
    assert rail.TARGET_SELECT_BUDGET_SECONDS <= rail.DEADLINE_SECONDS, (
        f"the page SELECT may run {rail.TARGET_SELECT_BUDGET_SECONDS}s against a "
        f"{rail.DEADLINE_SECONDS}s loop deadline, so it can push the request past "
        "the worst case budget_headroom_seconds() reports"
    )


def test_the_write_budget_fits_inside_the_reserve_that_already_claimed_it():
    """``POST_LOOP_NON_COUNT_RESERVE_SECONDS`` is documented as covering "the last
    event's write and commit, response serialization, and the request
    dependency's own commit".

    So the write's bound must fit INSIDE it with room left for the other two, or
    the reserve is describing a budget the write can spend on its own — which is
    the class of error being fixed, not a new one.
    """
    assert 0 < rail.WRITE_BUDGET_SECONDS < rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"the write may take {rail.WRITE_BUDGET_SECONDS}s out of a "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve that also has to "
        "cover serialization and the dependency's commit"
    )


def test_the_worst_case_still_fits_under_the_router_wall():
    """The regression arm for both constants at once: neither new bound may eat
    the headroom Q496 and CERT-666 established.

    Recomputed from the constants rather than compared to 2.65 — a restated
    number stops being an assertion the moment someone edits a constant.
    """
    assert rail.budget_headroom_seconds() > 0, (
        "the rail's worst case no longer fits under the router wall: an "
        "over-running call returns H12 with no body, and the drain loses its place"
    )


# ---------------------------------------------------------------------------
# Q496-END-TO-END-DB-DEADLINE — the page SELECT
# ---------------------------------------------------------------------------


def _timeout_before(statements, predicate) -> int | None:
    """The ms value of the last statement_timeout armed before `predicate` hits.

    Anchored on the bounded statement itself rather than on call order, so a rail
    that adds another timeout elsewhere cannot make this read the wrong one — the
    exact way the CERT-666 count guard went vacuous.
    """
    sqls = [sql for sql, _ in statements]
    at = next((i for i, sql in enumerate(sqls) if predicate(sql)), None)
    if at is None:
        return None
    prior = [s for s in sqls[:at] if "STATEMENT_TIMEOUT" in s.upper()]
    if not prior:
        return None
    return int(prior[-1].rsplit("=", 1)[1].strip())


@pytest.mark.asyncio
async def test_the_page_select_is_armed_before_it_runs(fast, monkeypatch):
    """It is the FIRST statement of the request, and ``DEADLINE_SECONDS`` is not
    evaluated until it returns — so nothing in the rail could interrupt it. A
    lock on `futures_markets` held the request to the wall on its own."""
    s = _Session(targets=[], remaining=40)
    _venue(monkeypatch, {})

    await rail.repair(s, apply=False)

    ms = _timeout_before(s.statements, lambda sql: "LIMIT :cap" in sql)
    assert ms is not None, (
        "the page SELECT ran with no statement timeout. Statements seen: "
        f"{[sql[:60] for sql, _ in s.statements]}"
    )
    assert ms == int(rail.TARGET_SELECT_BUDGET_SECONDS * 1000), (
        f"the page SELECT was armed with {ms}ms, not the "
        f"{rail.TARGET_SELECT_BUDGET_SECONDS}s constant"
    )


@pytest.mark.asyncio
async def test_a_timing_out_page_select_is_a_named_pause_not_a_500(fast, monkeypatch):
    """A bare 500 cannot be told from a broken rail and carries NO cursor.

    The dispatcher turns any escape into ``500 Repair '...' failed``, whose detail
    does not distinguish "the database was busy" from "this code is wrong", and
    which an operator mid-drain cannot use to decide between retrying and
    restarting. Same contract the census keeps (gotcha #53/#54): a step that could
    not run says so BY NAME.
    """

    class _TargetDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if "LIMIT :cap" in sql:
                self.statements.append((sql, dict(params or {})))
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    s = _TargetDies(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(
        s, apply=True, after_date="2026-08-30T18:00:00+00:00", after_id=11
    )

    assert out["terminal"] == "paused_target_timeout"
    assert out["scan_exhausted"] is False, (
        "a page that was never selected reported an exhausted scan — the drain "
        "would stop with the whole population untouched"
    )
    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}, (
        "the operator's own cursor was dropped, so feeding the response back "
        "restarts the drain at page one"
    )
    assert s.rollbacks == 1, (
        "a statement timeout aborts the whole TRANSACTION, so the session is "
        "unusable until it is rolled back"
    )
    assert out["counts"]["events_examined"] == 0
    assert out["remaining_events"] is None and out["remaining_events_measured"] is False, (
        "nothing was measured, so the count must not report a number — 0 here "
        "reads as a drained population"
    )
    assert not s.writes, "a page that could not be selected still wrote"


@pytest.mark.asyncio
async def test_a_first_call_that_times_out_reports_no_cursor_rather_than_a_fake_one(
    fast, monkeypatch
):
    """The positive control for the cursor echo above: with no incoming cursor
    there is nothing to hand back, and inventing one would send the operator into
    the middle of a population they have not started."""

    class _TargetDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if "LIMIT :cap" in sql:
                self.statements.append((sql, dict(params or {})))
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    s = _TargetDies(targets=[], remaining=40)
    _venue(monkeypatch, {})

    out = await rail.repair(s, apply=True)

    assert out["terminal"] == "paused_target_timeout"
    assert out["next_cursor"] is None


@pytest.mark.asyncio
async def test_a_page_select_that_answers_is_never_reported_as_paused(fast, monkeypatch):
    """The negative control. Without it, a rail that returned
    ``paused_target_timeout`` unconditionally would pass every assertion above."""
    s = _Session(
        targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=4)],
        remaining=40,
    )
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=False)

    assert out["terminal"] != "paused_target_timeout"
    assert out["counts"]["events_examined"] == 1
    assert s.rollbacks == 0


# ---------------------------------------------------------------------------
# Q496-END-TO-END-DB-DEADLINE — the compare-and-set UPDATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_update_is_armed_before_it_runs(fast, monkeypatch):
    """The UPDATE takes a row lock on `futures_markets`, which the ordinary
    Polymarket poller also writes — so a contended row could block for as long as
    the other transaction lived, with no bound of any kind."""
    s = _Session(targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS})

    await rail.repair(s, apply=True)

    assert s.writes, "the test never reached a write; every assertion below is vacuous"
    ms = _timeout_before(s.statements, lambda sql: sql.upper().startswith("UPDATE"))
    assert ms is not None, (
        "the UPDATE ran with no statement timeout. Statements seen: "
        f"{[sql[:60] for sql, _ in s.statements]}"
    )
    assert ms == int(rail.WRITE_BUDGET_SECONDS * 1000), (
        f"the UPDATE was armed with {ms}ms, not the {rail.WRITE_BUDGET_SECONDS}s "
        "constant"
    )


class _WriteDies(_Session):
    """Fails the UPDATE for one named event, leaving every other statement alone."""

    def __init__(self, fail_eid: str, **kw):
        super().__init__(**kw)
        self.fail_eid = fail_eid

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.upper().startswith("UPDATE") and (params or {}).get("eid") == self.fail_eid:
            self.statements.append((sql, dict(params or {})))
            raise RuntimeError("canceling statement due to statement timeout")
        return await super().execute(stmt, params)


@pytest.mark.asyncio
async def test_a_blocked_write_pauses_the_drain_and_names_itself(fast, monkeypatch):
    """A failed write is not a verdict on the event, and it is not a finished
    page. It gets its own count, its own field and its own terminal."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "1", targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40
    )
    _venue(monkeypatch, {"1": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["terminal"] == "paused_write_timeout"
    assert out["counts"]["write_failed"] == 1
    assert out["stopped_at_write_timeout"] == "event_id=1"
    assert out["counts"]["markets_written"] == 0, (
        "a write that did not land was counted as rows written"
    )
    assert s.rollbacks == 1, (
        "a statement timeout aborts the whole TRANSACTION, so the session is "
        "unusable until it is rolled back"
    )
    assert s.commits == 0


@pytest.mark.asyncio
async def test_a_blocked_write_is_never_reported_as_a_completed_drain(fast, monkeypatch):
    """THE ONE THAT MATTERS FOR THE SHIP.

    The page is short and fully consumed, so every pre-CERT-667 term of
    ``scan_exhausted`` is satisfied — and the classification counts are real, so
    the terminal would have read ``changed``. That is the most reassuring possible
    wording for a page that left a user-visible match exactly as mis-filed as it
    found it, and it is CERT-666's false-completion defect arriving through the
    write instead of the fetch.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "1", targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40
    )
    _venue(monkeypatch, {"1": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["scan_exhausted"] is False, (
        "a short, fully-consumed page whose only write failed reported the drain "
        "finished — the operator stops with the row still hidden from Tennis"
    )
    assert out["terminal"] != "changed"
    assert "NOT A COMPLETED DRAIN" in out["reason"]


@pytest.mark.asyncio
async def test_a_blocked_write_stops_the_page_rather_than_marching_past_it(
    fast, monkeypatch
):
    """The behavioural guard on the ``break``, and it is NOT redundant with the
    ``write_failed`` invariant — the mutation battery is what separated them.

    Turning that ``break`` into a ``continue`` leaves ``scan_exhausted`` correct
    and the terminal correct, because the invariant catches those. What it does
    NOT leave correct is the CURSOR: the next event's write succeeds, advances the
    watermark past the failed one, and the drain skips it forever while reporting
    a state that looks entirely healthy. So the stopping itself has to be pinned,
    not just its reported consequences.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "1",
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    seen = _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert "2" not in seen, (
        "the page continued past a blocked write; the next event's success then "
        "advances the cursor past the failed one, which is skipped forever"
    )
    assert out["counts"]["events_examined"] == 1
    # And the cursor is left where the operator started, since nothing finished.
    assert out["next_cursor"] is None


@pytest.mark.asyncio
async def test_the_cursor_stops_before_the_event_whose_write_failed(fast, monkeypatch):
    """CERT-666 (P1), one statement further along.

    CERT-666 moved the advance from before the FETCH to after it. The write was
    still downstream of the advance, so an event the venue answered for and whose
    UPDATE then failed was left mis-filed with the cursor already past it —
    guaranteeing nothing would ever look at it again. The advance now happens
    per-outcome, after the event is genuinely finished.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "2",
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}, (
        "the cursor advanced past the event whose write failed — re-running "
        "would skip it forever, and it is still filed under the wrong sport"
    )


def _page_after(rows, cursor):
    """Apply the rail's OWN keyset to a row list, the way its SQL does.

    Page two has to be DERIVED from the emitted cursor, not handed over. Supplying
    the rows by hand is the difference between a guard and a decoration: a rail
    that emits a cursor pointing past the failed event still "re-fetches" it if
    the test puts it on the page regardless. Verified against the mutant — with
    the rows hardcoded, advancing the cursor before the write goes undetected.

    Mirrors `ORDER BY commence_time DESC NULLS LAST, anchor_id DESC` and both arms
    of the keyset gate.
    """
    if cursor is None:
        return list(rows)
    after_date, after_id = cursor["after_date"], cursor["after_id"]
    out = []
    for r in rows:
        d = r.commence_time.isoformat() if r.commence_time else None
        if after_date is None:
            # Inside the NULL region: ordering is by anchor_id alone.
            if d is None and r.anchor_id < after_id:
                out.append(r)
        elif d is None or (d, r.anchor_id) < (after_date, after_id):
            out.append(r)
    return out


@pytest.mark.asyncio
async def test_the_event_whose_write_failed_is_revisited_by_the_cursor_it_emits(
    fast, monkeypatch
):
    """Two calls, end to end. The emitted cursor is fed straight back in AND page
    two is derived from it, so an off-by-one in the watermark shows up as the
    failed event never being re-attempted."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    row1 = _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)
    row2 = _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12)

    s1 = _WriteDies("2", targets=[row1, row2], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})
    first = await rail.repair(s1, apply=True)
    assert first["terminal"] == "paused_write_timeout"

    cursor = first["next_cursor"]
    assert cursor is not None
    accepted = set(inspect.signature(rail.repair).parameters)
    for key in cursor:
        assert key in accepted, f"next_cursor emits {key!r}, which repair() cannot accept"

    # Page two is whatever the emitted cursor actually selects — row1 is written
    # and must drop out, row2 failed and must NOT.
    s2 = _Session(targets=_page_after([row1, row2], cursor), remaining=40)
    seen = _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})
    second = await rail.repair(s2, apply=True, **cursor)

    assert "1" not in seen, "the cursor did not advance past the event it wrote"

    assert "2" in seen, (
        "the event whose write failed was never re-attempted — the drain skipped "
        "it permanently, which is the defect this guard exists for"
    )
    assert second["counts"]["markets_written"] > 0, "the retry did not write it either"
    assert second["scan_exhausted"] is True, (
        "once every event resolves AND writes, the short page IS the end and the "
        "rail must still be able to say so — otherwise this fix traded a false "
        "completion for an unreachable one"
    )


@pytest.mark.asyncio
async def test_a_first_event_write_failure_hands_back_the_cursor_it_was_given(
    fast, monkeypatch
):
    """Nothing on the page finished, so there is no new watermark — and returning
    ``null`` reads as "start over", silently re-walking everything already done."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "9", targets=[_Row("9", _Ts("2026-08-30T12:00:00+00:00"), 90)], remaining=40
    )
    _venue(monkeypatch, {"9": _TENNIS})

    out = await rail.repair(
        s, apply=True, after_date="2026-08-30T18:00:00+00:00", after_id=11
    )

    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}
    assert out["terminal"] == "paused_write_timeout"


@pytest.mark.asyncio
async def test_writes_committed_before_the_failure_are_kept_and_reported(fast, monkeypatch):
    """Pausing is not rolling back. The rollback undoes the FAILED transaction
    only; events committed before it are durable, and the operator must be able to
    see that rather than assume the whole page was lost."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _WriteDies(
        "2",
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert s.commits == 1, "the event written before the failure lost its commit"
    assert out["counts"]["markets_written"] == s.update_rowcount
    assert out["counts"]["write_failed"] == 1
    assert out["terminal"] == "paused_write_timeout"


@pytest.mark.asyncio
async def test_a_page_whose_writes_all_land_still_advances_and_completes(fast, monkeypatch):
    """The negative control for every cursor guard above.

    "The cursor stops before the failure" is satisfied by a rail that never
    advances at all, and so is "a blocked write is not a completed drain". This is
    the arm that fails on such a rail.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(
        targets=[
            _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
            _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
        ],
        remaining=40,
    )
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["next_cursor"] == {"after_date": "2026-08-30T17:00:00+00:00", "after_id": 12}, (
        "a page every write of which landed did not advance to its last event"
    )
    assert out["counts"]["write_failed"] == 0
    assert out["stopped_at_write_timeout"] is None
    assert out["scan_exhausted"] is True
    assert out["terminal"] == "changed"
    assert s.commits == 2


@pytest.mark.asyncio
async def test_a_dry_run_still_advances_its_cursor(fast, monkeypatch):
    """The write is where the advance now lives for a changed event, and a dry run
    has no write. If the advance were attached to the UPDATE rather than to the
    event being finished, ``apply=false`` would page forever without moving."""
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    s = _Session(targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS})

    out = await rail.repair(s, apply=False)

    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}
    assert not s.writes
    assert out["terminal"] == "dry_run"


def test_completion_stays_impossible_while_any_write_failed():
    """The invariant, independent of the ``break``.

    ``stopped_at_write_timeout`` is what the loop sets TODAY. If a later change
    turns that ``break`` back into a ``continue``, the field goes quiet and the
    count is the only thing left standing between the operator and a false
    completion — exactly the pairing CERT-666 required for ``indeterminate``.
    """
    src = inspect.getsource(rail.repair)
    start = src.find("scan_exhausted = (")
    assert start != -1, (
        "scan_exhausted is no longer a single parenthesised assignment in "
        "repair(); this guard cannot see what it claims to check and must be "
        "rewritten rather than left to pass vacuously"
    )
    # The closing paren of the assignment, not the first `)` in the expression —
    # `len(targets)` is one of those, and slicing on it silently reduced this
    # guard to matching an empty string.
    end = src.find("\n    )", start)
    assert end != -1, "could not find the end of the scan_exhausted assignment"
    scan = src[start:end]
    assert 'counts["write_failed"] == 0' in scan, (
        "scan_exhausted no longer requires that every write landed; it would "
        "then rest entirely on the loop's `break`, and a `continue` reintroduces "
        "the false completion"
    )
    assert "stopped_at_write_timeout is None" in scan


def test_the_response_publishes_the_two_bounds_it_now_enforces():
    """The rail reports its budget so an operator can audit it without reading the
    source. Two constants it enforces but does not report is the same gap in
    miniature — the numbers become unfalsifiable from outside."""
    src = inspect.getsource(rail.repair)
    assert '"target_select_budget_s"' in src
    assert '"write_budget_s"' in src


# ===========================================================================
# CERT-670 (P1) — ROUND TWO: A BOUND YOU CAN ONLY INSTALL OVER THE CHANNEL YOU
# ARE TRYING TO BOUND IS NOT YET A BOUND.
#
# Every bound the section above added is a PostgreSQL `statement_timeout`, and
# PostgreSQL cannot enforce one it has not been sent. `AsyncSession` acquires its
# connection LAZILY, on the first `execute` of a transaction — which is the very
# `SET LOCAL` that arms the bound. So the arming statement ran unbounded, waiting
# on a pool whose own `pool_timeout` is SQLAlchemy's 30s default: exactly
# `ROUTER_WALL_SECONDS`. Under saturation the rail could still burn the whole
# wall and hand the operator an H12 with no body and no cursor.
#
# WHAT THESE GUARDS HAVE TO BE SHAPED LIKE
# ----------------------------------------
# * The failure is a HANG, not an exception, so every behavioural guard drives a
#   session that never returns and asserts the rail answers anyway. Each one runs
#   under an OUTER `asyncio.wait_for` so that a missing bound fails as a clean
#   TimeoutError instead of wedging the suite — a guard whose failure mode is "the
#   test run stops" gets disabled, and then it guards nothing.
# * They starve the `SET LOCAL` itself, not the statement it arms. That is where
#   the real checkout happens, and a guard that only starved the query would pass
#   on a rail that wrapped the query and left arming outside — which is precisely
#   the shape of the defect.
# * The arithmetic guards assert the DERIVED number against the reserve it is
#   charged to. Asserting the server bound alone is what let the slack go
#   unaccounted; re-making that mistake one level down would be the same bug a
#   third time.
# ===========================================================================


import asyncio  # noqa: E402 — the round-two section's own import, kept local to it
import time as _time  # noqa: E402


@pytest.fixture
def tiny_budgets(monkeypatch):
    """Shrink every bound so a starved unit resolves in milliseconds.

    The constants are read at call time, so patching the module is enough. The
    arithmetic guards below run against the REAL values and are what keep these
    from hiding a bad production number.
    """
    monkeypatch.setattr(rail, "TARGET_SELECT_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(rail, "WRITE_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(rail, "CENSUS_STATEMENT_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(rail, "POOL_ACQUIRE_SLACK_SECONDS", 0.05)
    monkeypatch.setattr(rail, "ROLLBACK_BUDGET_SECONDS", 0.05)


class _ArmStarves(_Session):
    """A session whose connection never comes free.

    Hangs on the Nth ``SET LOCAL`` — the statement that ARMS a bound, which is
    also the statement that checks a connection out. Indexed among the SET LOCALs
    rather than matched on its value so the guard does not depend on two budgets
    being spelled differently, and not indexed among ALL statements so an extra
    query elsewhere cannot silently re-point it at another unit.
    """

    def __init__(self, *args, arm_index: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.arm_index = arm_index
        self._arms = 0
        self.starved_on: str | None = None

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.upper().startswith("SET LOCAL"):
            hit = self._arms == self.arm_index
            self._arms += 1
            if hit:
                self.statements.append((sql, dict(params or {})))
                self.starved_on = sql
                # Never returns. Only a client-side deadline can end this.
                await asyncio.Event().wait()
        return await super().execute(stmt, params)


async def _answers_within(coro, seconds: float = 5.0):
    """Run `coro` under an OUTER deadline and return (result, elapsed).

    The outer deadline is the harness, never the thing under test: it exists so a
    rail with no client bound fails loudly and quickly instead of hanging the
    suite. `elapsed` is asserted separately, against the rail's own bound.
    """
    began = _time.monotonic()
    try:
        out = await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:  # pragma: no cover — the failure this guards
        raise AssertionError(
            f"the rail did not answer within {seconds}s while a pooled connection "
            "was never granted. Nothing in it can end that wait, so on production "
            "the Heroku router ends it instead: H12, no body, no cursor."
        ) from None
    return out, _time.monotonic() - began


# ---------------------------------------------------------------------------
# The arithmetic — asserted on the DERIVED bound, not the server bound
# ---------------------------------------------------------------------------


def test_the_client_bound_not_just_the_write_budget_fits_inside_the_reserve():
    """`test_the_write_budget_fits_inside_the_reserve_that_already_claimed_it`
    above is now weaker than it reads, and this is the guard that carries it.

    What the reserve is actually charged for is no longer `WRITE_BUDGET_SECONDS`
    but the CLIENT bound wrapped around it, which is strictly larger. A guard that
    checks the inner number while the outer one is what spends the time is the
    same "described but not enforced" gap the whole queue exists to close.

    And the reserve is charged for the write's CLEANUP as well. A starved write
    is followed by a bounded rollback, so the worst case the reserve has to
    absorb is the client bound PLUS `ROLLBACK_BUDGET_SECONDS` — the failure path
    costs more than the success path, which is the easy thing to miss when a
    budget is sized against the happy case.
    """
    charged = (
        rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)
        + rail.ROLLBACK_BUDGET_SECONDS
    )
    assert 0 < charged < rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"a failing write can now occupy {charged}s (a "
        f"{rail.WRITE_BUDGET_SECONDS}s server bound, plus "
        f"{rail.POOL_ACQUIRE_SLACK_SECONDS}s of client slack, plus a "
        f"{rail.ROLLBACK_BUDGET_SECONDS}s cleanup rollback) out of a "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve that also has to "
        "cover serialization and the dependency's own commit"
    )


def test_the_client_bound_on_the_page_select_cannot_widen_the_worst_case():
    """Same correction one site over: it is the derived bound that can outlast the
    loop deadline, so it is the derived bound — plus the cleanup that follows a
    starved SELECT — that has to fit under it."""
    charged = (
        rail.client_db_budget_seconds(rail.TARGET_SELECT_BUDGET_SECONDS)
        + rail.ROLLBACK_BUDGET_SECONDS
    )
    assert charged <= rail.DEADLINE_SECONDS, (
        f"a failing page SELECT can now occupy {charged}s against a "
        f"{rail.DEADLINE_SECONDS}s loop deadline, so it can push the request past "
        "the worst case budget_headroom_seconds() reports"
    )


def test_the_census_still_fits_under_the_wall_once_both_queries_are_wrapped():
    """The census runs TWO bounded queries under ONE router wall, and each now
    carries its own client slack. Q496 asserted `2 * CENSUS < WALL`; the quantity
    that actually elapses is `2 * client_bound`."""
    charged = (
        2 * rail.client_db_budget_seconds(rail.CENSUS_STATEMENT_TIMEOUT_SECONDS)
        + rail.ROLLBACK_BUDGET_SECONDS
    )
    assert charged < rail.ROUTER_WALL_SECONDS, (
        f"the census's permitted worst case is now {charged}s against a "
        f"{rail.ROUTER_WALL_SECONDS}s wall — it can H12, and an H12 returns no "
        "body, so the `measured: false` answer never reaches the operator"
    )


def test_the_client_slack_is_slack_and_not_a_second_budget():
    """The slack has to be SMALLER than the smallest server bound it wraps.

    If it were larger, the client deadline would start winning races the server
    timeout should win, and the rail would report pool starvation for what was
    really a slow query — sending the operator to look at connection counts over
    a lock. The direction of this inequality is the whole design.
    """
    smallest = min(
        rail.WRITE_BUDGET_SECONDS,
        rail.TARGET_SELECT_BUDGET_SECONDS,
        rail.CENSUS_STATEMENT_TIMEOUT_SECONDS,
    )
    assert 0 < rail.POOL_ACQUIRE_SLACK_SECONDS < smallest, (
        f"{rail.POOL_ACQUIRE_SLACK_SECONDS}s of client slack against a "
        f"{smallest}s smallest server bound: the client deadline can now fire "
        "first on an ordinary slow statement and misreport it as pool starvation"
    )


# ---------------------------------------------------------------------------
# The structural guard — no fourth unbounded site may appear
# ---------------------------------------------------------------------------


def test_no_database_statement_in_this_rail_escapes_the_bounded_helper():
    """Whole-module scan, not a check of the three lines that were wrong.

    A guard on those three would be satisfied forever by the fix and would never
    see the fourth. Parsed with `ast` rather than grepped, so the prose in this
    module's comments and docstrings — which discusses `execute` at length —
    cannot satisfy or break it.
    """
    import ast

    tree = ast.parse(inspect.getsource(rail))
    funcs = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("repair", "census", "_bounded_statement"):
        assert name in funcs, (
            f"{name}() is gone from this rail, so this scan cannot see what it "
            "claims to check. Rewrite the guard rather than let it pass vacuously."
        )

    def _execute_calls(node):
        return [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "execute"
        ]

    offenders = []
    for name in ("repair", "census"):
        for call in _execute_calls(funcs[name]):
            offenders.append(f"{name}() line {call.lineno}")
    assert not offenders, (
        "these call sites execute SQL directly instead of going through "
        f"`_bounded_statement`, so their `SET LOCAL` can wait out the router wall "
        f"acquiring a connection before any timeout exists: {offenders}"
    )

    # The scan is only meaningful if the helper is where the execution moved TO.
    # Without this, deleting every query in the rail would also pass.
    assert _execute_calls(funcs["_bounded_statement"]), (
        "`_bounded_statement` no longer executes anything, so the scan above is "
        "asserting that a rail which touches no database touches no database"
    )


def test_every_rollback_in_this_rail_is_the_bounded_one():
    """A cleanup rollback is itself a statement on the wedged connection.

    Left bare it can hang exactly as long as the thing it is cleaning up after,
    and it runs on the path whose entire purpose is to return a cursor. The
    module-wide form again, for the same reason: the next failure arm someone adds
    will reach for `session.rollback()`.
    """
    import ast

    tree = ast.parse(inspect.getsource(rail))
    funcs = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("repair", "census", "_safe_rollback"):
        assert name in funcs, f"{name}() is gone; rewrite this guard"

    offenders = []
    for name in ("repair", "census"):
        for n in ast.walk(funcs[name]):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "rollback"
            ):
                offenders.append(f"{name}() line {n.lineno}")
    assert not offenders, (
        "these rollbacks are unbounded; a cleanup that hangs costs the operator "
        f"the very response it was rolling back to produce: {offenders}"
    )


def test_the_pool_pause_outranks_the_venue_pause_in_the_terminal_chain():
    """Ordering, asserted where the ordering lives — as a CONDITION, not a line
    number.

    The three cannot both be set in one run today, because each arm `break`s, so
    no behavioural test can distinguish the orders. The ranking is defensive
    against exactly the change this file already anticipates twice over: a
    `break` becoming a `continue`. Load causes all three at once — a saturated
    pool, a locked row and a timing-out venue are the same bad afternoon — and
    ranked below, the pool arm becomes reachable only when nothing else went
    wrong, so the run reports the venue and buries the cause.

    Written against the parse tree because the first version of this guard
    compared source POSITIONS, and position is not rank: a mutant that left the
    pool arm first and merely added ``stopped_at_unresolved is None`` to its test
    de-ranked it completely and the guard never noticed.
    """
    import ast

    tree = ast.parse(inspect.getsource(rail))
    repair_fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "repair"
        ),
        None,
    )
    assert repair_fn is not None, "repair() is gone; rewrite this guard"

    def _assigns(node, terminal):
        """Does this branch's OWN body assign `terminal` (not a nested branch)?"""
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if (
                    isinstance(sub, ast.Constant)
                    and sub.value == terminal
                    and isinstance(stmt, ast.Assign)
                ):
                    return True
        return False

    head = next(
        (
            n
            for n in ast.walk(repair_fn)
            if isinstance(n, ast.If) and _assigns(n, "paused_pool_timeout")
        ),
        None,
    )
    assert head is not None, (
        "no `if` branch in repair() assigns the `paused_pool_timeout` terminal; "
        "this guard cannot see the chain it claims to rank and must be rewritten "
        "rather than left to pass vacuously"
    )

    # A bare `x is not None`, never a BoolOp. The moment this arm's reachability
    # depends on another stopped_at_* field being unset, it is ranked BELOW that
    # field no matter where its source line sits.
    assert isinstance(head.test, ast.Compare), (
        f"the pool-starvation arm's condition is a {type(head.test).__name__}, "
        "so it fires only when some other terminal did not — that is what being "
        "ranked below something means, whatever the line order says"
    )
    assert (
        isinstance(head.test.left, ast.Name)
        and head.test.left.id == "stopped_at_pool_timeout"
    ), "the pool-starvation arm no longer tests stopped_at_pool_timeout directly"

    # And the other two pauses must hang off ITS else-chain, which is what makes
    # it the head rather than merely an early branch of a different chain.
    chain = ast.dump(ast.Module(body=head.orelse, type_ignores=[]))
    for terminal in ("paused_unresolved", "paused_write_timeout"):
        assert terminal in chain, (
            f"{terminal!r} is no longer in the else-chain below the "
            "pool-starvation arm, so the two are not ranked against each other "
            "at all"
        )

    # BOTH directions. "The others are below it" is only half of being first —
    # a mutant that prepended a duplicate venue arm left every assertion above
    # true, because the original arms were still somewhere underneath. Nothing
    # may sit ABOVE it either, so the chain's head is asserted by identity
    # against the outermost `if` in repair()'s own body.
    PAUSES = ("paused_pool_timeout", "paused_unresolved", "paused_write_timeout")
    outermost = next(
        (
            n
            for n in repair_fn.body
            if isinstance(n, ast.If) and any(p in ast.dump(n) for p in PAUSES)
        ),
        None,
    )
    assert outermost is not None, (
        "the terminal chain is no longer a top-level `if` in repair(); this "
        "guard cannot see what it claims to rank and must be rewritten"
    )
    assert outermost is head, (
        "another pause terminal is evaluated BEFORE the pool-starvation arm, so "
        "the pool arm is reachable only when that one did not fire — it is "
        "ranked below it, whatever its own condition says"
    )


def test_completion_stays_impossible_while_the_pool_starved_a_write():
    """The `scan_exhausted` invariant, extended to the third way a page can end
    with an event still mis-filed behind the cursor."""
    src = inspect.getsource(rail.repair)
    start = src.find("scan_exhausted = (")
    assert start != -1, "scan_exhausted is no longer a single assignment; rewrite"
    end = src.find("\n    )", start)
    assert end != -1, "could not find the end of the scan_exhausted assignment"
    scan = src[start:end]
    assert "stopped_at_pool_timeout is None" in scan, (
        "a page whose write never reached the database can still report an "
        "exhausted scan, so the drain stops with that event permanently skipped"
    )


# ---------------------------------------------------------------------------
# The behaviour — a connection that never comes free
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_page_select_that_never_gets_a_connection_pauses_with_its_cursor(
    fast, tiny_budgets, monkeypatch
):
    """THE guard for this repair.

    Arming is the first statement of the request and it is what checks the
    connection out, so before this fix nothing in the rail could end the wait —
    the router ended it, with H12 and no body. The operator lost the cursor, which
    is the one thing the paused response exists to protect.
    """
    s = _ArmStarves(arm_index=0, targets=[], remaining=40)
    _venue(monkeypatch, {})

    out, elapsed = await _answers_within(
        rail.repair(s, apply=True, after_date="2026-08-30T18:00:00+00:00", after_id=11)
    )

    assert s.starved_on is not None, (
        "the rail never issued a SET LOCAL before its page SELECT, so this test "
        "starved nothing and every assertion below is vacuous"
    )
    assert out["terminal"] == "paused_pool_timeout", (
        f"a starved connection reported {out['terminal']!r}. It is not a "
        "`paused_target_timeout`: no statement reached PostgreSQL, so no server "
        "timeout fired, and telling the operator to blame a slow query sends them "
        "to the wrong place."
    )
    assert out["stopped_at_pool_timeout"] == "target_select"
    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}, (
        "the operator's own cursor was dropped, so feeding the response back "
        "restarts the drain at page one"
    )
    assert out["scan_exhausted"] is False
    assert out["counts"]["events_examined"] == 0
    assert out["remaining_events_measured"] is False
    assert not s.writes
    assert elapsed < rail.ROUTER_WALL_SECONDS, (
        f"the rail took {elapsed:.2f}s against a {rail.ROUTER_WALL_SECONDS}s "
        "router wall — it answered, but not in time for anyone to receive it"
    )


@pytest.mark.asyncio
async def test_a_starved_first_call_reports_no_cursor_rather_than_a_fake_one(
    fast, tiny_budgets, monkeypatch
):
    """The positive control for the echo above: with no incoming cursor there is
    nothing to hand back, and inventing one drops the operator into the middle of
    a population they have not started."""
    s = _ArmStarves(arm_index=0, targets=[], remaining=40)
    _venue(monkeypatch, {})

    out, _ = await _answers_within(rail.repair(s, apply=True))

    assert out["terminal"] == "paused_pool_timeout"
    assert out["next_cursor"] is None


@pytest.mark.asyncio
async def test_a_healthy_page_is_never_reported_as_pool_starved(fast, monkeypatch):
    """The negative control. Without it, a rail that returned
    `paused_pool_timeout` unconditionally would satisfy every guard above."""
    s = _Session(
        targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=4)],
        remaining=40,
    )
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=True)

    assert out["terminal"] != "paused_pool_timeout"
    assert out["stopped_at_pool_timeout"] is None
    assert out["counts"]["write_failed"] == 0


@pytest.mark.asyncio
async def test_a_write_that_never_gets_a_connection_stops_the_page(
    fast, tiny_budgets, monkeypatch
):
    """The write begins a NEW transaction — the previous event's commit released
    the connection — so it checks one out again, unbounded, mid-page.

    Arm index 1: the page SELECT's SET LOCAL is 0, the first event's write is 1.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    row1 = _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)
    row2 = _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12)
    s = _ArmStarves(arm_index=1, targets=[row1, row2], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out, elapsed = await _answers_within(rail.repair(s, apply=True))

    assert s.starved_on is not None, "nothing was starved; this guard is vacuous"
    assert out["terminal"] == "paused_pool_timeout"
    assert out["stopped_at_pool_timeout"] == "event_id=1 (write)"
    assert out["counts"]["write_failed"] == 1, (
        "an event whose UPDATE never reached the database was not counted as a "
        "failed write, so the `write_failed` invariant that backstops "
        "`scan_exhausted` cannot see it"
    )
    assert out["scan_exhausted"] is False
    assert out["next_cursor"] is None, (
        "the cursor advanced past — or invented a position for — an event whose "
        "write never happened; that event is still mis-filed and the drain would "
        "never look at it again"
    )
    assert elapsed < rail.ROUTER_WALL_SECONDS


@pytest.mark.asyncio
async def test_the_event_whose_pool_starved_is_revisited_by_the_cursor_it_emits(
    fast, tiny_budgets, monkeypatch
):
    """Two calls, end to end, with page two DERIVED from the emitted cursor.

    Round one's version of this guard hardcoded page two and therefore "re-fetched"
    an event the cursor had already skipped past. `_page_after` applies the rail's
    own keyset instead, so an off-by-one in the watermark shows up as the starved
    event never being retried.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    row1 = _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)
    row2 = _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12)

    # Arm index 2: page SELECT (0), event 1's write (1), event 2's write (2).
    s1 = _ArmStarves(arm_index=2, targets=[row1, row2], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})
    first, _ = await _answers_within(rail.repair(s1, apply=True))
    assert first["terminal"] == "paused_pool_timeout"
    assert first["stopped_at_pool_timeout"] == "event_id=2 (write)"

    cursor = first["next_cursor"]
    assert cursor is not None, "event 1 wrote and committed, so there IS a watermark"
    accepted = set(inspect.signature(rail.repair).parameters)
    for key in cursor:
        assert key in accepted, f"next_cursor emits {key!r}, which repair() cannot accept"

    s2 = _Session(targets=_page_after([row1, row2], cursor), remaining=40)
    seen = _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})
    second = await rail.repair(s2, apply=True, **cursor)

    assert "1" not in seen, "the cursor did not advance past the event it wrote"
    assert "2" in seen, (
        "the event whose write never got a connection was never re-attempted — "
        "the drain skipped it permanently, which is the defect this guard is for"
    )
    assert second["counts"]["markets_written"] > 0, "the retry did not write it either"
    assert second["scan_exhausted"] is True, (
        "once every event resolves AND writes, the short page IS the end — this "
        "fix must not trade a false completion for an unreachable one"
    )


@pytest.mark.asyncio
async def test_a_starved_terminal_count_does_not_invent_a_paused_drain(
    fast, tiny_budgets, monkeypatch
):
    """The negative arm that keeps the fix from over-applying.

    The count is a decoration on work that has already committed: the writes are
    durable and the cursor is correct. Giving it a pause terminal would turn a
    successful page into a paused one over a missing statistic —
    `remaining_events_measured: false` already says everything true here.
    """
    monkeypatch.setattr(rail, "APPLY_EVENT_CAP", 5)
    # Drive `count_budget_s` to its floor so the count's own bound is tiny.
    monkeypatch.setattr(rail, "ROUTER_WALL_SECONDS", 0)
    row1 = _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)
    # Arm index 1: page SELECT (0), then the count (1) — a dry run makes no write.
    s = _ArmStarves(arm_index=1, targets=[row1], remaining=40)
    _venue(monkeypatch, {"1": _TENNIS})

    out, _ = await _answers_within(rail.repair(s, apply=False))

    assert s.starved_on is not None, "nothing was starved; this guard is vacuous"
    assert out["terminal"] != "paused_pool_timeout", (
        "a starved terminal COUNT paused the drain. Nothing was left undone: the "
        "page was fully examined and the cursor is correct."
    )
    assert out["stopped_at_pool_timeout"] is None
    assert out["remaining_events_measured"] is False, (
        "the count did not run, so it must report itself unmeasured — a number "
        "here would be invented, and a 0 would read as a drained population"
    )
    assert out["remaining_events"] is None
    assert out["next_cursor"] is not None, "the examined page still has a watermark"


@pytest.mark.asyncio
async def test_a_census_that_never_gets_a_connection_says_so_rather_than_a_zero(
    tiny_budgets,
):
    """Gotcha #54 at the point it is hardest to honour. A census that H12s returns
    no body at all, so the honest `measured: false` never reaches the operator —
    the diagnostic's whole contract evaporates exactly when it matters."""
    s = _ArmStarves(arm_index=0)

    out, elapsed = await _answers_within(rail.census(s))

    assert out["measured"] is False, (
        "a census that could not get a connection reported a measurement"
    )
    assert "markets" not in out, "a census that could not look reported a population"
    assert "ClientDeadlineExceeded" in out["reason"], (
        f"the census's reason ({out['reason']!r}) does not name the client "
        "deadline, so 'the query was slow' and 'there was no connection to run "
        "it on' are indistinguishable to whoever reads it"
    )
    assert elapsed < rail.ROUTER_WALL_SECONDS


@pytest.mark.asyncio
async def test_a_rollback_that_hangs_still_leaves_the_operator_a_response(
    fast, tiny_budgets, monkeypatch
):
    """The cleanup path's own failure mode, and it is not hypothetical: the
    connection this rolls back is the one that just refused to answer.

    `get_db_rw` COMMITS after the handler returns, so a session still holding a
    wedged connection turns this carefully built paused response — cursor and all
    — into the bare 500 it exists to replace. Invalidating discards the connection
    instead of negotiating with it.
    """

    class _RollbackHangs(_ArmStarves):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.invalidated = 0

        async def rollback(self):
            await asyncio.Event().wait()

        async def invalidate(self):
            self.invalidated += 1

    s = _RollbackHangs(arm_index=0, targets=[], remaining=40)
    _venue(monkeypatch, {})

    out, elapsed = await _answers_within(
        rail.repair(s, apply=True, after_date="2026-08-30T18:00:00+00:00", after_id=11)
    )

    assert out["terminal"] == "paused_pool_timeout", (
        "a hanging cleanup swallowed the response the failure path had already "
        "built"
    )
    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}
    assert s.invalidated == 1, (
        "the wedged connection was neither rolled back nor invalidated, so it goes "
        "back to `get_db_rw` — whose commit then fails and returns the 500 this "
        "whole path exists to avoid"
    )
    assert elapsed < rail.ROUTER_WALL_SECONDS


def test_the_response_publishes_the_client_slack_it_now_enforces():
    """The rail reports its budget so an operator can audit it from outside. A
    third bound it enforces but does not report is the same gap in miniature."""
    src = inspect.getsource(rail.repair)
    assert '"pool_acquire_slack_s"' in src


def test_the_dispatcher_prose_names_every_pause_terminal_the_rail_can_return():
    """The prose-defect class again, and it recurred the moment a fourth arrived.

    Q496 fixed a registration comment that named a query param the dispatcher
    could not pass, and the lesson taken was that prose needs a gate. CERT-670
    added a fourth pause terminal to a comment that said "three terminals mean
    PAUSED" and enumerated them — a count and a list that go stale silently,
    read by the one person who most needs them right: the operator mid-drain
    deciding whether they are finished.

    Derived from the rail's own source, so it cannot be satisfied by editing the
    number without adding the terminal, and cannot go stale when a fifth lands.
    """
    terminals = set(re.findall(r'"(paused_[a-z_]+)"', inspect.getsource(rail)))
    assert terminals, (
        "no `paused_*` terminal literals found in the rail; this guard cannot "
        "see what it claims to check and must be rewritten"
    )

    from app.routes import admin_repairs

    prose = inspect.getsource(admin_repairs)
    missing = sorted(t for t in terminals if t not in prose)
    assert not missing, (
        "the repair's registration block does not name these pause terminals, so "
        "an operator reading it cannot tell a paused drain from a finished one: "
        f"{missing}"
    )
