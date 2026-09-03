"""#2798 — a settled market leaves the scan, and says so once.

WHAT WAS WRONG. Measured on production 2026-09-03, over one hour of the
15-minute matcher:

    SELECT r.phase, fm.status, count(*), max(r.attempt_count)
    FROM market_match_receipts r JOIN futures_markets fm ON fm.id = r.market_id
    WHERE r.last_attempted_at > now() - interval '1 hour' GROUP BY 1,2;
    -- pass1_ticker | resolved | 7,464 | 40
    -- pass1_ticker | open     |   178 | 40

Two findings in four rows. The obvious one: 97.7% of the matcher's work was
re-attempting markets that had already resolved, some of them for the 40th time,
against an event population for a past date that cannot change. The one that
costs more: **``pass1_ticker`` is the only phase in the table at all** — 8,987
receipts, one phase — so Pass 2 and Pass 3 had never written a single row. Pass 1
is the one scan with no status predicate and no LIMIT; it pulled all 138,676
unlinked ticker-shaped Kalshi rows (131,229 of them resolved), worked down them
by ``updated_at DESC``, and hit its time floor before yielding. The backlog sweep
built in #2705 to make "never attempted" impossible had never run in production.

SO THE FIX IS TWO HALVES AND THE TESTS HOLD BOTH:

1. **Pass 1 stops selecting resolved markets.** Its population drops from 138,676
   to 7,447 and the passes behind it get to start. Tested by compiling the real
   SELECT and running it over planted rows — a fake session returns whatever it
   was handed no matter what the predicate says.
2. **Every market that leaves the scan says why, once.** An exclusion with no
   record re-creates the exact silence receipts exist to abolish: "we refuse it"
   and "we no longer look at it" become the same NULL again. The settled sweep
   stamps ``settled`` on the markets that had a receipt and have since resolved,
   and its own selection skips rows already carrying it — which is what makes it
   once-per-market instead of another every-pass re-touch.

The coupling between the two is itself a test: a row Pass 1 has stopped
selecting must be a row the sweep picks up. Half a fix here is worse than none,
because it would delete the evidence along with the work.
"""

import asyncio
import inspect
import re
import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as mr

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class _CapturingSession:
    """Records statements, returns nothing, so a pass's SQL can be read off."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)

        class _Empty:
            def all(self_inner):
                return []

            def scalars(self_inner):
                return self_inner

            def unique(self_inner):
                return self_inner

        return _Empty()

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _sqlite(stmt) -> str:
    return stmt.compile(
        dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True}
    ).string


def _only_id(sql: str) -> str:
    """Project to ``id`` so a planted table needs no column beyond the predicate."""
    return re.sub(
        r"^SELECT .*? FROM futures_markets", "SELECT futures_markets.id FROM futures_markets",
        sql, count=1, flags=re.DOTALL,
    )


# =============================================================================
# The planted population. One row per state the two predicates have to split,
# with the expectation written beside it — Pass 1 attempts it, the sweep stamps
# it, or neither.
# =============================================================================

#: (id, source, status, event_id, receipt_reason, external_id,
#:  pass1_selects, sweep_selects, why)
ROWS = [
    (1, "kalshi", "open", None, None, "KXNHLGAME-26SEP03MINCOL", True, False,
     "open, unlinked, ticker-shaped: the live population Pass 1 is for"),
    (2, "kalshi", "resolved", None, "name_mismatch", "KXNHLGAME-25MAY14MINCOL",
     False, True,
     "THE 7,464. Resolved, so Pass 1 must not attempt it again; it carries a "
     "live reject reason from when it was open, so the sweep must overwrite it"),
    (3, "kalshi", "resolved", None, "settled", "KXNHLGAME-25MAY13MINCOL",
     False, False,
     "already stamped: the sweep is once per market, not every pass — this row "
     "being selected again IS the bug the sweep would otherwise become"),
    (4, "kalshi", "suspended", None, None, "KXNHLGAME-26SEP04MINCOL", True, False,
     "suspended is a paused market, not a decided one — still a candidate"),
    (5, "kalshi", "resolved", 15299723, "name_mismatch", "KXNHLGAME-25MAY12MINCOL",
     False, False,
     "resolved but LINKED: it needs no explanation, it has an event"),
    (6, "kalshi", "open", None, "name_mismatch", "KXNHLGAME-26SEP05MINCOL",
     True, False,
     "open with a receipt: the sweep must not stamp a market still being tried"),
    (7, "kalshi", "resolved", None, None, "KXNHLGAME-24MAY12MINCOL", False, False,
     "resolved and never attempted: the 460k archive tail, deliberately out of "
     "scope — it never entered the population, so nothing left it"),
    (8, "polymarket", "resolved", None, "no_candidate", "0xabc", False, True,
     "the sweep is source-agnostic: Pass 2's population settles too"),
    (9, "kalshi", "open", None, None, "KXPRESIDENT-28", False, False,
     "not a game-ticker prefix: Pass 1 never covered it (Pass 2/3 do)"),
]


def _plant(conn):
    conn.execute(
        "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, source TEXT, "
        "status TEXT, event_id INTEGER, updated_at TEXT, external_id TEXT, "
        "name TEXT, category TEXT, llm_sport_category TEXT, commence_time TEXT)"
    )
    conn.execute(
        "CREATE TABLE market_match_receipts (id INTEGER PRIMARY KEY, "
        "market_id INTEGER, last_attempted_at TEXT, reject_reason TEXT)"
    )
    for mid, source, status, event_id, reason, ext, _p1, _sw, _why in ROWS:
        conn.execute(
            "INSERT INTO futures_markets (id, source, status, event_id, "
            "updated_at, external_id, name, category, llm_sport_category, "
            "commence_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (mid, source, status, event_id, "2026-09-03T00:00:00", ext,
             "A vs B", "game", "hockey", "2026-09-03T20:00:00"),
        )
        if reason is not None:
            conn.execute(
                "INSERT INTO market_match_receipts (market_id, "
                "last_attempted_at, reject_reason) VALUES (?,?,?)",
                (mid, "2026-09-03T11:05:00", reason),
            )
    conn.commit()


def _run(sql: str) -> set[int]:
    conn = sqlite3.connect(":memory:")
    _plant(conn)
    try:
        return {r[0] for r in conn.execute(_only_id(sql)).fetchall()}
    finally:
        conn.close()


def _pass1_sql() -> str:
    """The population SELECT Pass 1 really issues."""
    stats = {"funnel": {"game_level_detected": 0}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    asyncio.run(
        pmm._phase1_pass1_ticker_scan(session, stats, NOW, [], lambda: 700.0)
    )
    assert session.statements, "Pass 1 issued no query at all"
    return _sqlite(session.statements[0])


def _sweep_sql_and_stats():
    stats = {"funnel": {}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    asyncio.run(pmm._settled_sweep(session, stats, NOW, lambda: 700.0))
    assert session.statements, "the settled sweep issued no query at all"
    return _sqlite(session.statements[0]), stats


# =============================================================================
# Half 1 — Pass 1 stops spending the task on markets that cannot change.
# =============================================================================


def test_pass1_no_longer_selects_resolved_markets():
    """Run the real SELECT over planted rows, one expectation per row."""
    got = _run(_pass1_sql())
    for mid, _s, _st, _e, _r, _x, selected, _sw, why in ROWS:
        assert (mid in got) is selected, f"market {mid} — {why}"


def test_pass1_still_selects_the_live_population_it_exists_for():
    """The exclusion must not be a quiet way of turning the pass off.

    A predicate that narrowed too far would pass the test above and take the
    matcher's Kalshi game coverage with it. The open rows are the ship.
    """
    got = _run(_pass1_sql())
    assert 1 in got and 4 in got, (
        "Pass 1 stopped selecting open ticker-shaped Kalshi markets — that is "
        "the population it exists to link, not the one #2798 is about"
    )


def test_pass1_is_still_unbounded_over_the_live_population():
    """No LIMIT. The point of the exclusion is that it no longer needs one.

    Capping the pass would trade one silent truncation for another: the rows
    past the cap would go unattempted with nothing anywhere saying so, which is
    the failure #2705 exists to end.
    """
    assert " LIMIT " not in _pass1_sql().upper()


# =============================================================================
# Half 2 — the market that leaves the scan says why, ONCE.
# =============================================================================


def test_the_sweep_selects_exactly_the_markets_that_left_the_population():
    sql, _ = _sweep_sql_and_stats()
    got = _run(sql)
    for mid, _s, _st, _e, _r, _x, _p1, selected, why in ROWS:
        assert (mid in got) is selected, f"market {mid} — {why}"


def _reason_of(market_id: int):
    return next(r[4] for r in ROWS if r[0] == market_id)


def test_no_attempted_market_is_dropped_from_the_scan_without_a_record():
    """The coupling. An exclusion with no receipt is the old NULL, renamed.

    Every row the matcher HAS attempted and now will not attempt again must be a
    row the sweep picks up. This is the test that fails if a later edit keeps the
    cheap half of the fix — the exclusion — and drops the honest half.
    """
    pass1 = _run(_pass1_sql())
    sweep_sql, _ = _sweep_sql_and_stats()
    sweep = _run(sweep_sql)

    # Rows Pass 1 used to select: unlinked, ticker-shaped Kalshi, any status.
    old_population = {
        mid for mid, source, _st, event_id, _r, ext, _p1, _sw, _why in ROWS
        if source == "kalshi" and event_id is None and ext.startswith("KXNHL")
    }
    dropped = old_population - pass1
    assert dropped, "the planted set no longer exercises the exclusion at all"
    unexplained = {
        mid for mid in dropped
        # Attempted at least once (it has a receipt) and the receipt does not
        # already say `settled` — a row carrying the stamp is explained by the
        # stamp it has, and the sweep skipping it is the once-per-market rule.
        if _reason_of(mid) is not None
        and _reason_of(mid) != mr.REJECT_SETTLED
        and mid not in sweep
    }
    assert not unexplained, (
        f"markets {sorted(unexplained)} left Pass 1's population with no "
        f"receipt to say why — that is the silence #2705 abolished, restored"
    )


def test_the_never_attempted_settled_cohort_is_a_stated_boundary_not_an_oversight():
    """Market 7: resolved, unlinked, and never attempted. The sweep skips it.

    THIS IS THE HONEST LIMIT OF THE FIX AND IT IS WRITTEN DOWN HERE SO NOBODY
    HAS TO REDISCOVER IT. Widening the sweep to cover it means selecting every
    unlinked resolved market — ~460k rows on production, almost all of them
    archive nobody will ever ask about — and the selection would then have to
    walk the whole settled tail on every run forever just to find nothing left
    to stamp. The cost is permanent; the answer it buys is about markets that
    resolved before we ever looked at them.

    What makes the boundary safe is the other half of this change: Pass 1 now
    covers its whole open population every run (7,447 rows, no LIMIT — see the
    tests above), so an open ticker market is attempted, and therefore carries a
    receipt, before it can ever settle. The cohort is legacy: it stops being
    produced, it does not grow.

    If Pass 1 ever gains a cap, this test's premise dies with it, and the two
    tests that hold it — ``test_pass1_is_still_unbounded_over_the_live_
    population`` and ``test_pass1_still_selects_the_live_population_it_exists_
    for`` — are what will say so.
    """
    sweep_sql, _ = _sweep_sql_and_stats()
    assert 7 not in _run(sweep_sql)
    assert _reason_of(7) is None
    assert " LIMIT " not in _pass1_sql().upper()


def test_the_sweep_is_once_per_market_not_every_pass():
    """The selection itself is the once — nothing else enforces it.

    Market 3 already carries the reason and must not come back. Without this,
    the sweep re-stamps 131k rows every 15 minutes and reproduces #2798's second
    harm exactly: dead rows whose ``last_attempted_at`` keeps looking fresh, so
    any census counted off receipts reads them as today's top defect.
    """
    sql, _ = _sweep_sql_and_stats()
    assert 3 not in _run(sql)


def test_the_stamp_is_the_closed_enum_value_and_the_outcome_is_rejected():
    receipt = mr.MatchReceipt(
        market_id=2, source="kalshi", external_id="KXNHLGAME-25MAY14MINCOL",
        market_name="A vs B", phase=mr.PHASE_SETTLED_SWEEP, attempted_at=NOW,
    ).reject(mr.REJECT_SETTLED, market_status="resolved")

    assert mr.REJECT_SETTLED in mr.REJECT_REASONS
    assert mr.PHASE_SETTLED_SWEEP in mr.PHASES
    row = receipt.to_row()
    assert row["reject_reason"] == "settled"
    assert row["outcome"] == mr.OUTCOME_REJECTED
    assert row["phase"] == "settled_sweep"


def test_the_stamp_never_appends_to_link_history():
    """A settlement is not a link change, and must not be counted as one.

    ``market_link_changes`` is the table that answers "did tonight drop 261
    links". A sweep that appended to it would invent a loss per settled market
    and drown the signal it was built to carry.
    """
    receipt = mr.MatchReceipt(
        market_id=2, source="kalshi", external_id="x", market_name="A vs B",
        phase=mr.PHASE_SETTLED_SWEEP, attempted_at=NOW,
    ).reject(mr.REJECT_SETTLED)
    assert mr.link_change_row(receipt) is None


def test_the_sweep_orders_newest_attempt_first():
    """Gotcha #41: ask what the ordering STARTS on.

    The bus asks about the market that settled last night. Ascending would start
    the drain on the oldest archive row and answer that question days later; the
    tail is not starved either way, because a stamped row is permanently out of
    the selection.
    """
    sql, _ = _sweep_sql_and_stats()
    assert "last_attempted_at DESC" in sql


def test_the_sweep_is_bounded_per_run():
    sql, _ = _sweep_sql_and_stats()
    assert f"LIMIT {pmm._SETTLED_SWEEP_MAX}" in sql


def test_the_sweep_stands_down_when_the_task_is_out_of_time():
    """The record must never cost the thing it records."""
    stats = {"funnel": {}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    written = asyncio.run(pmm._settled_sweep(session, stats, NOW, lambda: 30.0))
    assert written == 0
    assert session.statements == []
    assert stats["funnel"]["settled_sweep_skipped_budget"] is True


def test_the_sweep_reports_what_it_stamped():
    """A pass whose output nobody can see reads as "nothing to report"."""
    _, stats = _sweep_sql_and_stats()
    assert "settled_receipted" in stats["funnel"]
    assert stats["funnel"]["settled_sweep_skipped_budget"] is False


def test_the_sweep_runs_before_anything_that_attempts_a_link():
    """Ordering inside the task, read off the source.

    Written last, the record of an exclusion is the first thing a busy night
    drops — and a busy night is when it is wanted.
    """
    src = inspect.getsource(pmm._match_prediction_markets)
    assert "_settled_sweep(" in src
    assert src.index("_settled_sweep(") < src.index("_phase1_pass1_ticker_scan(")


@pytest.mark.parametrize("name", ["_SETTLED_SWEEP_MAX", "_SETTLED_SWEEP_MIN_SECONDS_REMAINING"])
def test_the_bounds_are_named_constants(name):
    assert isinstance(getattr(pmm, name), int)
