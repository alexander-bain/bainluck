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
