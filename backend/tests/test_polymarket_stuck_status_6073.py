"""A venue-dated fixture may not stand `live`/`suspended` over a future kickoff.

## the defect this gate exists for

#6073 has two writers that correct a Polymarket fixture's start, and they live in
different files on different release trains:

* `redate_polymarket_listing_stamped_events()` (this lane, `poll_polymarket_
  markets`, MAIN app) — group-keyed, repairs `commence_time_source='polymarket'`,
  and writes the date AND the status in one statement;
* Phase 1.5 in the event registry (lane1, `match_prediction_markets`, which is in
  `HEAVY_TASKS`) — per-market, reaches already-linked rows the group-keyed sweep
  structurally cannot, and writes the DATE ONLY.

Measured on production 2026-09-14: **47 events in 26 multi-event groups** are
reachable only by the second writer, and **12 of them have a venue start still in
the future**. On those 12 the date becomes honest and the status does not, and
nothing drains the result:

* the sweep's band requires `commence_time_source='polymarket'`, and Phase 1.5's
  write sets that column to `polymarket_venue` — so the sweep can never
  re-select a row the other writer has touched;
* `transition_event_statuses` has no `suspended → scheduled` edge. Its four are
  scheduled→live, live→suspended, suspended→live, suspended→retired.

So the reader gets "No result reported" over a match nine days away, permanently.
The class is **0 rows across every source today** (measured 11:52Z) and arrives
the moment `bainluck-heavy` carries the second writer — which is why the drain
ships on the main app, ahead of it.

## why the repair is keyed on the row and not on either writer

`stuck_status_target()` reads no provider, no market, no group and no stamp. It
asks the row a question the row alone can answer: *you say you are live or stale,
and you say you start next week; which is it?* That makes the repair independent
of which writer produced the contradiction and of the order the two ran in — and
it keeps working if a third writer appears. A rail keyed on "rows Phase 1.5
touched" would have to know Phase 1.5, and would go stale the day it changed.

The arms below are the four refusals and both directions of the repair. The
refusals matter more than the repair: a rail that flips `live` to `scheduled` too
eagerly un-starts real games, which is #6073's own defect wearing the other face.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.polymarket import (
    STUCK_FUTURE_STATUS_SQL,
    STUCK_STATUS_WRITE_SQL,
    _STUCK_STATUS_UNCHANGED_WHERE,
    rescue_stuck_future_status_events,
    stuck_status_target,
)

UTC = timezone.utc

#: ⏰ #7611 — THIS WAS A DATETIME LITERAL AND IT WAS DUE TO RED MASTER ON
#: **2026-09-24T10:00:00Z**. Found by the clock sweep that followed
#: `test_settled_champion_point_stamp_6360.py` doing exactly this at
#: 2026-09-20T21:33:24Z and blocking every lane's merge.
#:
#: Offsets are taken FROM it and nothing here branches on the wall clock — that
#: much was already true, and it is not enough. `test_the_pass_rescues_the_row_
#: and_commits` and its sibling go through `rescue_stuck_future_status_events`,
#: which supplies the REAL clock; only the `stuck_status_target` arms get
#: `now=NOW`. So `FUTURE` had to be genuinely ahead of wall time, and
#: `NOW + 9d22h` off a literal 2026-09-14 stopped being ahead of it on the 24th.
#: `clock_sweep.py` on the unfixed file: 2/12 points FAILED at the far-future
#: marks, and a `--at 2026-09-24T12:00` point reproduces it exactly.
#:
#: Offset from the clock, no branch, no truncation — the shape gotcha #44
#: prescribes. `TestTheAnchorCannotAgeOut` in the 6360 file is the worked
#: example of the guard; here the sweep is the guard, and this file is now
#: invariant at all 12 of its points.
ANCHOR_LAG = timedelta(days=1)  # < FUTURE's 9d22h, so FUTURE stays ahead of now
NOW = datetime.now(UTC) - ANCHOR_LAG

FUTURE = NOW + timedelta(days=9, hours=22)
PAST = NOW - timedelta(hours=6)


def _target(**kw):
    """`stuck_status_target` over the shape of the 12: the defect, by default."""
    base = dict(
        status="suspended",
        event_commence=FUTURE,
        now=NOW,
        completed_at=None,
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
    )
    base.update(kw)
    return stuck_status_target(**base)


# --------------------------------------------------------------------------
# the repair
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["suspended", "live"])
def test_a_status_refuted_by_its_own_future_kickoff_becomes_scheduled(status):
    """Both refutable statuses, because both assert the match has begun.

    `suspended` is the shape of the measured 12. `live` is the worse-reading
    sibling — a live badge over a match nine days away — and is included because
    nothing in either writer prevents it: the registry's date write does not read
    `status`, so whatever the row was badged when the date was wrong, it stays.
    """
    assert _target(status=status) == "scheduled"


def test_the_repair_needs_no_provider_market_group_or_stamp():
    """The whole design claim, asserted rather than described.

    `stuck_status_target` is called here with ONLY the row's own columns — the
    same call the pass makes. If a future edit made the decision depend on a
    group, a stamp or a source, this call would not compile, and the rail would
    have quietly become order-dependent again.
    """
    assert (
        stuck_status_target(
            status="suspended",
            event_commence=FUTURE,
            now=NOW,
            completed_at=None,
            home_score=None,
            away_score=None,
            period=None,
            game_clock=None,
        )
        == "scheduled"
    )


def test_a_naive_kickoff_is_read_as_utc_and_not_as_a_crash():
    """`timestamptz` comes back aware, but a caller or a fixture may not.

    Compared naive-to-aware Python raises `TypeError`, and inside the pass's own
    try/except that is a rail dead in production and green in CI.
    """
    assert _target(event_commence=FUTURE.replace(tzinfo=None)) == "scheduled"
    assert _target(event_commence=PAST.replace(tzinfo=None)) is None
    assert _target(now=NOW.replace(tzinfo=None)) == "scheduled"


# --------------------------------------------------------------------------
# the refusals
# --------------------------------------------------------------------------


def test_a_kickoff_in_the_past_leaves_the_status_alone():
    """The evidence IS the future start. Without it there is no contradiction.

    A start in the past makes `live` and `suspended` perfectly honest, and this
    is the arm standing between the rail and un-starting real games.
    """
    assert _target(event_commence=PAST) is None


def test_a_kickoff_exactly_at_now_is_not_in_the_future():
    """The boundary, stated explicitly because `>` vs `>=` is the whole rule.

    At the kickoff instant `live` is honest. A boundary-inclusive test would
    re-badge a match as upcoming at the exact second it starts.
    """
    assert _target(event_commence=NOW) is None


@pytest.mark.parametrize(
    "column,value",
    [
        ("home_score", 0),
        ("away_score", 0),
        ("home_score", 3),
        ("away_score", 1),
        ("period", "1H"),
        ("game_clock", "12:00"),
    ],
)
def test_any_evidence_of_play_refuses_the_row(column, value):
    """Four columns, and `0` is evidence.

    A score of `0` is the trap: it is falsy in Python and it means the game is
    being watched. If any of these is set, something reported on this match, and
    a row something reported on may not be badged as not yet begun — whatever its
    `commence_time` says. The disagreement is then a MATCHING defect to file, not
    a status to tidy.
    """
    assert _target(**{column: value}) is None


def test_a_completed_match_dated_into_the_future_is_reported_not_tidied():
    """Gotcha #46: `completed_at >= commence_time` is an invariant.

    Its violation means a cross-event data merge. Re-badging the row as upcoming
    would erase the symptom and keep the merge.
    """
    assert _target(completed_at=NOW - timedelta(hours=2)) is None


@pytest.mark.parametrize(
    "status", ["scheduled", "closed", "completed", "retired", "voided", "", None]
)
def test_only_live_and_suspended_are_refutable(status):
    """Every other state is one this rail has no standing to reopen.

    `scheduled` already agrees with a future start — returning it would be a
    no-op write, and `skipped_not_refuted` is the honest accounting. The settled
    family is `backfill_winners`' and the settlement sweep's; a future date on a
    closed row is again a matching symptom, not a status bug.
    """
    assert _target(status=status) is None


# --------------------------------------------------------------------------
# the write's own guard
# --------------------------------------------------------------------------
# These derive their expectations FROM the shipped SQL rather than listing
# columns by hand: a column added to the band tomorrow joins this assertion
# automatically. A hand-written list would pass forever while the band grew.


def _band_columns():
    """Every column the band SELECTs off `events`, read out of the shipped SQL."""
    import re

    return set(re.findall(r"e\.(\w+)\s+AS\s+\w+", STUCK_FUTURE_STATUS_SQL))


def test_the_write_re_asserts_every_column_the_band_read():
    """CERT-2834's finding, transplanted — selection is not permission to write.

    The realtime score poll writes into exactly this band. A score landing
    between the SELECT and the UPDATE is read by nobody, and the repair then
    commits `scheduled` over a game a reader can see has started. The only place
    the guard can live is the write's own WHERE.
    """
    band = _band_columns() - {"id"}
    assert band, "the band selects nothing — this guard would be vacuous"
    missing = [
        c
        for c in band
        if f"e.{c} IS NOT DISTINCT FROM" not in _STUCK_STATUS_UNCHANGED_WHERE
    ]
    assert not missing, f"selected but not re-asserted in the write: {missing}"


def test_the_band_carries_every_refusal_the_pure_function_makes():
    """The SQL and the function must state the SAME four refusals.

    ADDED AFTER A MUTATION SURVIVED. Deleting `status IN ('live','suspended')`
    from the band left all 30 arms green: the pure function still refused every
    row, so behaviour was unchanged and nothing failed. But the band is then a
    scan of every event in the table on every poll, and the contract it is
    supposed to state — "these are the refutable rows" — had no guard at all. A
    refusal held in only one of the two places is one edit from being held in
    neither.
    """
    for clause in (
        "status IN ('live', 'suspended')",
        "e.commence_time > now()",
        "e.completed_at IS NULL",
        "e.home_score IS NULL",
        "e.away_score IS NULL",
        "e.period IS NULL",
        "e.game_clock IS NULL",
    ):
        assert clause in STUCK_FUTURE_STATUS_SQL, f"band lost its refusal: {clause}"


def test_the_premise_columns_are_re_asserted_even_though_nothing_writes_them():
    """`commence_time` and `commence_time_source` ARE the premise.

    The band means "a venue-established kickoff, in the future". If either moves
    under the pass the premise is gone, even though this statement writes
    neither. A repair that reconciles exactly while a column it never looked at
    moves underneath is a failure this codebase has already had once.
    """
    for column in ("commence_time", "commence_time_source"):
        assert f"e.{column} IS NOT DISTINCT FROM" in _STUCK_STATUS_UNCHANGED_WHERE


def test_the_guard_is_null_safe_and_every_bind_is_cast():
    """Six of the seven compared columns are nullable, and NULL is the common
    value — an `=` form would match nothing and the rail would repair zero rows
    while reporting success. That half is also proven against a real server, in
    `tests/integration/test_polymarket_stuck_status_atomicity_6073_pg.py`.

    The cast half is held HERE and only here, and it is worth saying why the
    wording is weaker than the sibling suite's. Measured 2026-09-14: removing all
    eight casts from the shipped guard leaves every real-Postgres arm green,
    because each bind sits opposite a typed column Postgres can infer from. So
    this is a consistency arm, not a "the rail dies without it" arm — the claim
    it inherited from `_REDATE_UNCHANGED_WHERE`, where binds meet `jsonb->>`
    expressions and it is true.
    """
    import re

    comparisons = re.findall(r"e\.\w+ IS NOT DISTINCT FROM ([^\n]+)", _STUCK_STATUS_UNCHANGED_WHERE)
    assert len(comparisons) >= 7
    uncast = [c for c in comparisons if "CAST(" not in c]
    assert not uncast, f"bind with no cast: {uncast}"
    assert " = :was_" not in _STUCK_STATUS_UNCHANGED_WHERE


def test_the_write_re_checks_the_kickoff_against_a_clock_that_actually_moves():
    """CERT-2858's follow-up, and the reason the obvious spelling is wrong.

    The tuple guard preserves the SELECTED kickoff but does not re-evaluate that
    it is STILL future if wall time crosses it between the select and the write.
    The review asked for `e.commence_time > now()`.

    `now()` is `transaction_timestamp()`, and this pass runs its SELECT and all
    of its UPDATEs in ONE transaction — so that form compares the kickoff against
    the very instant the band already compared it against and can never decline
    anything. Measured on a real server across a 1-second sleep inside one
    transaction: `now()` identical before and after, `clock_timestamp()` moved a
    full second.

    So this arm asserts the working spelling AND forbids the inert one. A guard
    that cannot fire is worse than no guard: it reads as coverage.
    """
    assert "e.commence_time > clock_timestamp()" in _STUCK_STATUS_UNCHANGED_WHERE
    assert "> now()" not in _STUCK_STATUS_UNCHANGED_WHERE


def test_the_write_touches_status_and_nothing_else():
    """The date is correct by the band's own premise, so moving it would
    overwrite the venue's own statement. Asserted because the sibling statement
    one screen up DOES write the date, and copying it is the easy mistake.
    """
    body = STUCK_STATUS_WRITE_SQL.split("WHERE", 1)[0]
    assert "SET status = :status" in body
    assert "commence_time" not in body


# --------------------------------------------------------------------------
# the pass
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Session:
    """Canned SELECT rows, then records what the pass writes.

    `write_rowcount=0` stands for the row having moved under the pass. That
    models the ACCOUNTING only — whether the shipped WHERE actually declines a
    changed row is a question about what a server decides, answered by
    `tests/integration/test_polymarket_stuck_status_atomicity_6073_pg.py`.
    """

    def __init__(self, rows, write_rowcount=1):
        self._rows = rows
        self.write_rowcount = write_rowcount
        self.selected_params = None
        self.writes = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        if "UPDATE events" in str(stmt):
            self.writes.append(params)
            return _Result([], rowcount=self.write_rowcount)
        self.selected_params = params
        return _Result(self._rows)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _band_row(**kw):
    base = dict(
        event_id=15312165,
        event_commence=FUTURE,
        completed_at=None,
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
        status="suspended",
    )
    base.update(kw)
    return _Row(**base)


def _drive(monkeypatch, session):
    import app.tasks.polymarket as poly

    monkeypatch.setattr(poly, "get_task_session", lambda: _Ctx(session))
    return rescue_stuck_future_status_events()


@pytest.mark.asyncio
async def test_the_pass_rescues_the_row_and_commits(monkeypatch):
    session = _Session([_band_row()])
    stats = await _drive(monkeypatch, session)

    assert stats["scanned"] == 1
    assert stats["rescheduled"] == 1
    assert stats["skipped_raced"] == 0
    assert session.commits == 1
    assert session.writes[0]["status"] == "scheduled"
    assert session.writes[0]["id"] == 15312165


@pytest.mark.asyncio
async def test_the_band_is_scoped_to_the_venue_source(monkeypatch):
    """Not to every source, and the other branch was counted before choosing.

    The contradiction is decidable for any source, and the class is 0 rows
    across all of them today. Widening would adopt other providers' status
    semantics — a postponed ESPN fixture carrying a future rescheduled date may
    mean `suspended` honestly — on a population this lane has never measured.
    """
    session = _Session([])
    await _drive(monkeypatch, session)

    assert session.selected_params == {"venue_src": "polymarket_venue"}
    assert "commence_time_source = :venue_src" in STUCK_FUTURE_STATUS_SQL


@pytest.mark.asyncio
async def test_a_row_that_moved_under_the_pass_is_counted_and_never_silent(
    monkeypatch,
):
    """`app/utils/task_verdict.py`: "it returned" is not "it worked".

    A repair whose write matched zero rows must not read as one that worked, and
    must not commit on the strength of it.
    """
    session = _Session([_band_row()], write_rowcount=0)
    stats = await _drive(monkeypatch, session)

    assert stats["skipped_raced"] == 1
    assert stats["rescheduled"] == 0
    assert session.commits == 0


@pytest.mark.asyncio
async def test_the_pass_re_applies_every_refusal_the_band_already_made(monkeypatch):
    """The band's WHERE and the pure function both refuse these rows.

    Belt and braces on purpose: the SQL cannot be unit-tested without a server,
    and an edit to either place must not be able to quietly drop a refusal. A
    refused row is `skipped_not_refuted`, writes nothing, and commits nothing.
    """
    session = _Session(
        [
            _band_row(event_id=1, event_commence=PAST),
            _band_row(event_id=2, home_score=0),
            _band_row(event_id=3, completed_at=NOW),
            _band_row(event_id=4, status="closed"),
        ]
    )
    stats = await _drive(monkeypatch, session)

    assert stats["scanned"] == 4
    assert stats["skipped_not_refuted"] == 4
    assert stats["rescheduled"] == 0
    assert session.writes == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_a_zero_yield_sweep_reports_its_zero(monkeypatch):
    """The expected reading today, and the reason the counters exist.

    The class is empty until the heavy deploy lands. `scanned: 0` going to 12 and
    back to 0 is the evidence this rail works; a sweep that logged only when it
    found something could not tell "nothing to do" from "never ran".
    """
    session = _Session([])
    stats = await _drive(monkeypatch, session)

    assert stats == {
        "scanned": 0,
        "rescheduled": 0,
        "skipped_not_refuted": 0,
        "skipped_raced": 0,
    }


@pytest.mark.asyncio
async def test_the_poll_reports_the_sweep_and_survives_its_failure(monkeypatch):
    """One repair must not cost the poll its stats (the sibling sweep's rule).

    The wrapper is asserted here rather than trusted: a rail wired into a poll
    behind a bare `try` is exactly the shape that runs, raises, and reports
    success for months.
    """
    import inspect

    import app.tasks.polymarket as poly

    src = inspect.getsource(poly._poll_polymarket_markets)
    assert 'stats["stuck_future_status"] = await rescue_stuck_future_status_events()' in src
    assert 'stats["errors"].append(f"stuck_status: {e}")' in src
