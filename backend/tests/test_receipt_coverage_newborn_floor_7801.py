"""#7801 — the coverage alarm stops firing on markets nothing has had a turn at.

THE DEFECT, MEASURED ON PRODUCTION 2026-09-21. ``check_receipt_coverage``
counted every open unlinked market with no receipt, including ones ingested
seconds earlier. Polymarket polls hourly; Pass 3 runs every matcher cycle. So
the check went RED on the cycle after each poll and GREEN on the next one, and
the filing rail did exactly what it was built to do with that — opened an issue
and closed it again, about twenty times a day:

    #7789  opened 11:29:15Z  closed 11:42:05Z  count=50
    #7779  opened 10:58:02Z  closed 11:12:11Z  count=2
    #7774  opened 10:28:29Z  closed 10:42:07Z  count=24
    #7760  opened 09:27:33Z  closed 09:42:09Z  count=8
    #7751  opened 08:29:15Z  closed 08:42:09Z  count=3

Every one of them open for 13-14 minutes — one matcher cycle — and one of them
filed a p1 issue about **two** markets. That is not a check with an occasional
false positive; it is a check whose output carries no information. The 8/28
ingest wave it exists to catch would have arrived as the twenty-first identical
issue that day, and the module docstring's own bar ("nothing ... for more than
an hour without an issue existing") would have been met by an issue nobody could
read.

THE SPECIMEN, and it is the fixture below. At 12:33:05Z the raw count was 223.
All 223 were born inside a 34-second window at 12:26:14-12:26:48Z, six minutes
AFTER the backlog pass last ran (12:20:00.062114Z). Measured with the proposed
predicate in the same query: ``past_pass_floor`` 0, ``past_2h_grace`` 0, NULL
``created_at`` 0. So the fix removes the race and nothing else.

WHAT THESE TESTS HOLD:

1. **A newborn wave is not a finding, and the 8/28 wave still is.** Both run the
   check's REAL SQL against planted rows — the point is worthless asserted on a
   string.
2. **The floor fails OPEN.** The pass-run arm alone is the trap: if Pass 3 dies,
   ``last_run_at`` freezes, every later market is forever younger than the
   floor, and the check goes quiet exactly when the backlog has stopped
   draining. The grace arm is why it cannot.
3. **The base denominator did not move.** One clause was added. A fix that also
   narrowed the population to game-shaped rows would pass (1) and (2) and be a
   different bug.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.matching_reconciliation as mrec
from app.utils.matcher_pass_runs import (
    NEVER_ATTEMPTED_MAX_GRACE_S,
    PassRunFact,
    never_attempted_floor,
)

#: The production reading this file is built from, held as OFFSETS from one
#: captured instant rather than as absolute wall-clock literals.
#:
#: The literals were 2026-09-21 12:20:00.062114Z / 12:33:05Z / 12:26:14.130773Z
#: / 2026-08-28 04:00Z, and they were unconditional — no `if`, so gotcha #44's
#: "an anchor that branches on the clock is not an anchor" was satisfied. What
#: they could not survive is that HALF this file's subject reads the real clock:
#: `never_attempted_floor` takes the LATER of the pass's own run and
#: `now - NEVER_ATTEMPTED_MAX_GRACE_S`, and `check_receipt_coverage` calls it
#: with no `now=`. So the whole file was green for exactly the two hours after
#: 12:20Z and went red at 14:20:00Z on 2026-09-21 — on a byte-identical tree,
#: which is the tell that the variable is the clock. It reddened master's CI
#: within the hour (run 35611423327) and skipped the deploy job behind it.
#:
#: Offsets first, then the anchors derived from them (gotcha #44's positive
#: half): the pass ran 13m05s ago, so it is the later arm and the pass arm binds
#: at every wall-clock time; the newborn wave is 6m51s old, inside that; the
#: 8/28 wave is 24 days old, far outside it. Every relationship the fixture
#: asserts is preserved exactly, and now it holds at 03:00Z as well as 13:00Z.
NOW = datetime.now(timezone.utc)
PASS_RAN_AT = NOW - timedelta(minutes=13, seconds=4, microseconds=937886)
NEWBORN_AT = NOW - timedelta(minutes=6, seconds=50, microseconds=869227)
WAVE_828_AT = NOW - timedelta(days=24, hours=8, minutes=33, seconds=5)


# =============================================================================
# The policy, as a pure function
# =============================================================================


class TestTheFloorIsTheLaterOfTwoArms:
    def test_the_healthy_path_is_the_passes_own_last_run(self):
        """Precise and self-calibrating: no cadence is hardcoded anywhere."""
        assert never_attempted_floor(PASS_RAN_AT, now=NOW) == PASS_RAN_AT

    def test_the_grace_arm_never_binds_while_the_pass_is_healthy(self):
        """If it ever did, the constant would be setting the policy instead of
        backstopping it — and a two-hour blind spot would open on every cycle."""
        floor = never_attempted_floor(PASS_RAN_AT, now=NOW)
        assert floor != NOW - timedelta(seconds=NEVER_ATTEMPTED_MAX_GRACE_S)
        assert floor == PASS_RAN_AT

    def test_an_unknown_last_run_leaves_the_grace_arm_alone(self):
        """``last_run_at`` is None when there is no durable row OR the store did
        not answer. Neither is "it never ran" (CERT-824), and neither is a
        reason to stop counting — so the conservative arm holds the floor."""
        assert never_attempted_floor(None, now=NOW) == NOW - timedelta(
            seconds=NEVER_ATTEMPTED_MAX_GRACE_S
        )

    def test_a_dead_pass_cannot_buy_permanent_silence(self):
        """THE KILL TEST FOR THE ONE-ARM IMPLEMENTATION.

        Pass 3 last ran three days ago and has not run since. Under a floor of
        ``last_run_at`` alone, every market ingested in those three days is
        younger than the floor, the count is 0, and the check is GREEN — while
        the backlog it watches drains not at all. That is the failure mode the
        alarm exists to catch, reported as health.
        """
        died_at = NOW - timedelta(days=3)
        floor = never_attempted_floor(died_at, now=NOW)

        assert floor != died_at, "the pass-run arm alone fails CLOSED"
        assert floor == NOW - timedelta(seconds=NEVER_ATTEMPTED_MAX_GRACE_S)
        # A market ingested two days into the outage is now countable again.
        stranded = NOW - timedelta(days=2)
        assert stranded < floor

    def test_the_silence_a_dead_pass_buys_is_bounded_by_the_grace(self):
        """It is not zero — it cannot be, or the newborn race comes back. What
        matters is that it is a fixed bound and not "until someone looks"."""
        died_at = NOW - timedelta(days=3)
        floor = never_attempted_floor(died_at, now=NOW)
        assert (NOW - floor).total_seconds() == NEVER_ATTEMPTED_MAX_GRACE_S

    def test_a_naive_last_run_at_is_read_as_utc_not_raised_on(self):
        """The durable store has handed back naive datetimes before. A
        TypeError here would take the whole check to `unmeasurable`, which the
        module's first line says must never read as GREEN."""
        naive = PASS_RAN_AT.replace(tzinfo=None)
        assert never_attempted_floor(naive, now=NOW) == PASS_RAN_AT

    def test_the_grace_is_wider_than_a_matcher_cycle_and_narrower_than_the_stall(
        self,
    ):
        """Both bounds matter. Under ~15 minutes a slow cycle trips it and the
        flap returns; over a day the 8/28 wave hides inside it."""
        assert NEVER_ATTEMPTED_MAX_GRACE_S > 4 * 15 * 60
        assert NEVER_ATTEMPTED_MAX_GRACE_S < 24 * 60 * 60


# =============================================================================
# The check's real SQL, against planted rows
# =============================================================================

#: (id, source, status, event_id, created_at, has_receipt, counts, why)
COVERAGE_ROWS = [
    (1, "polymarket", "open", None, NEWBORN_AT, False, False,
     "the specimen: born 12:26:14Z, six minutes after the pass ran. No receipt "
     "because nothing has had a turn at it — a race, not a skip (#7801)"),
    (2, "polymarket", "open", None, NEWBORN_AT, False, False,
     "its sibling from the same 34-second ingest window"),
    (3, "kalshi", "open", None, NEWBORN_AT, False, False,
     "newborns are newborns on either source"),
    (4, "polymarket", "open", None, WAVE_828_AT, False, True,
     "THE 8/28 WAVE: existed when the pass ran and still has no receipt. This "
     "is the finding the check is for, and the floor must not hide it"),
    (5, "kalshi", "open", None, PASS_RAN_AT - timedelta(seconds=1), False, True,
     "born one second before the pass ran: the pass had its turn and wrote "
     "nothing. Counts — this is the boundary, asserted rather than inherited"),
    (6, "polymarket", "open", None, None, False, True,
     "NULL birth time. Not evidence of youth, and it cannot be excused by a "
     "floor it cannot be compared against, so it counts (gotcha #53)"),
    (7, "polymarket", "open", None, WAVE_828_AT, True, False,
     "old and unlinked, but it HAS a receipt: it has been looked at"),
    (8, "polymarket", "open", 15299723, WAVE_828_AT, False, False,
     "already linked: the sweep is for unattached markets"),
    (9, "polymarket", "closed", None, WAVE_828_AT, False, False,
     "closed: a settled market is not waiting to be attached"),
    (10, "odds_api", "open", None, WAVE_828_AT, False, False,
     "not a prediction market source"),
]


class _Capturing:
    """Records the statement instead of answering it."""

    def __init__(self):
        self.statements = []

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    async def execute(self, stmt, params=None):  # pragma: no cover - unused here
        raise AssertionError("check_receipt_coverage should issue one scalar")


def _coverage_sql(last_run_at=PASS_RAN_AT):
    """The statement the check actually built, with its floor bound inlined."""
    session = _Capturing()

    async def _fake_read(_db, _phase, **_kw):
        return PassRunFact(
            phase="pass3_backlog",
            has_run=None if last_run_at is None else True,
            status="no_record" if last_run_at is None else "ok",
            last_run_at=last_run_at,
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.utils.matcher_pass_runs.read_pass_run", _fake_read)
        asyncio.run(mrec.check_receipt_coverage(session))

    assert len(session.statements) == 1, "the check issued more than one query"
    stmt = session.statements[0]
    floor = stmt.compile().params["floor"]
    # Bound here rather than by SQLAlchemy's literal_binds: the parameter is a
    # tz-aware datetime and sqlite compares TEXT, so the test must plant and
    # compare in ONE format or the whole replay is decided by string ordering.
    return str(stmt).replace(":floor", "'" + _iso(floor) + "'"), floor


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _plant(conn):
    conn.execute(
        "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, source TEXT, "
        "status TEXT, event_id INTEGER, created_at TEXT, name TEXT)"
    )
    conn.execute(
        "CREATE TABLE market_match_receipts (id INTEGER PRIMARY KEY, "
        "market_id INTEGER)"
    )
    for mid, source, status, event_id, created, has_receipt, _c, _why in COVERAGE_ROWS:
        conn.execute(
            "INSERT INTO futures_markets (id, source, status, event_id, "
            "created_at, name) VALUES (?,?,?,?,?,?)",
            (mid, source, status, event_id,
             None if created is None else _iso(created), f"market {mid}"),
        )
        if has_receipt:
            conn.execute(
                "INSERT INTO market_match_receipts (market_id) VALUES (?)", (mid,)
            )
    conn.commit()


def _select_ids(sql):
    """Turn the count into the ids it counted, so a row can be named."""
    ids_sql = sql.replace("SELECT count(*)", "SELECT fm.id", 1)
    conn = sqlite3.connect(":memory:")
    _plant(conn)
    try:
        return {r[0] for r in conn.execute(ids_sql).fetchall()}
    finally:
        conn.close()


class TestTheCheckCountsWhatItShould:
    def test_it_counts_exactly_the_rows_the_fixture_names(self):
        """Run the real SELECT. One expectation per row, each with its reason
        in the fixture — a count alone cannot tell a right answer from two
        offsetting wrong ones."""
        sql, _ = _coverage_sql()
        got = _select_ids(sql)
        expected = {r[0] for r in COVERAGE_ROWS if r[6]}
        assert got == expected, "\n".join(
            f"  {r[0]}: expected={'count' if r[6] else 'skip':5s} "
            f"got={'count' if r[0] in got else 'skip':5s}  {r[7]}"
            for r in COVERAGE_ROWS
            if (r[0] in got) != r[6]
        )

    def test_a_newborn_wave_alone_is_green(self):
        """The 12:26Z specimen, on its own: three markets, no receipts, and
        nothing wrong. This is what fired twenty times on 2026-09-21."""
        sql, _ = _coverage_sql()
        newborns = {r[0] for r in COVERAGE_ROWS if r[4] == NEWBORN_AT}
        assert newborns, "the fixture lost its specimen"
        assert not (newborns & _select_ids(sql))

    def test_the_828_wave_is_still_a_finding(self):
        """The floor must not buy silence for the thing the check is FOR."""
        sql, _ = _coverage_sql()
        assert 4 in _select_ids(sql)

    def test_a_null_birth_time_counts(self):
        sql, _ = _coverage_sql()
        assert 6 in _select_ids(sql)

    def test_the_base_denominator_did_not_move(self):
        """Exactly one clause was added. A fix that ALSO narrowed the
        population — to game-shaped names, to one source — would satisfy every
        other test here and be a different bug (#2803's lesson)."""
        sql, _ = _coverage_sql()
        got = _select_ids(sql)
        for mid in (7, 8, 9, 10):
            assert mid not in got
        # And the clause that was added is the only one mentioning created_at.
        assert sql.count("created_at") == 2, sql

    def test_the_check_binds_the_policy_and_not_last_run_at_raw(self):
        """THE SEAM. Every row test above is decided by the floor VALUE, so a
        check that passed ``backlog_run.last_run_at`` straight into the SQL
        would satisfy all of them on the healthy path (where the two are equal)
        and carry the one-arm fail-closed bug into production unseen.

        Not clock-frozen, deliberately: the check reads the real clock for its
        grace arm, so this compares the bound value against the policy called
        with that same real clock and asserts only what cannot drift.
        """
        died_at = datetime.now(timezone.utc) - timedelta(days=3)
        _sql, bound = _coverage_sql(last_run_at=died_at)

        assert bound != died_at, "the raw last_run_at was bound: fails CLOSED"
        drift = abs((bound - never_attempted_floor(died_at)).total_seconds())
        assert drift < 5, f"bound floor is not the policy's answer ({drift}s off)"

        # And on the healthy path the two ARE equal — which is why the seam
        # needs its own test rather than being inferred from the rows.
        _sql2, healthy = _coverage_sql(last_run_at=PASS_RAN_AT)
        assert healthy == PASS_RAN_AT

    def test_an_unknown_pass_run_still_binds_a_floor(self):
        """``last_run_at`` None must not bind NULL — `created_at < NULL` is
        NULL for every row, which silently counts nothing and reads as GREEN."""
        _sql, bound = _coverage_sql(last_run_at=None)
        assert bound is not None
        assert isinstance(bound, datetime)


class TestTheFindingSaysWhatItIsScopedTo:
    def _finding(self, count, last_run_at=PASS_RAN_AT):
        class _S:
            async def scalar(self, stmt):
                return count

        async def _fake_read(_db, _phase, **_kw):
            return PassRunFact(
                phase="pass3_backlog", has_run=True, status="ok",
                last_run_at=last_run_at,
            )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.utils.matcher_pass_runs.read_pass_run", _fake_read)
            return asyncio.run(mrec.check_receipt_coverage(_S()))

    def test_the_detail_names_the_floor_it_counted_against(self):
        """A reader triaging the issue cannot reproduce the number without it,
        and the endpoint publishes a DIFFERENT (unscoped) count beside it."""
        out = self._finding(17)
        assert PASS_RAN_AT.isoformat() in out["detail"]

    def test_it_is_still_red_above_zero_and_green_at_zero(self):
        assert self._finding(17)["red"] is True
        assert self._finding(17)["count"] == 17
        assert self._finding(0)["red"] is False

    def test_the_receipt_hint_sends_the_reader_to_the_scoped_field(self):
        """Pointing at `open_unlinked_without_receipt` now points at a number
        that disagrees with the issue's own count for an hour after each poll."""
        hint = mrec.receipts_hint_for({"key": "receipt_coverage", "rows": []})
        assert "never_attempted_past_floor" in hint
        assert "never_attempted_floor" in hint
