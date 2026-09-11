"""#5024 — a question the venue decided MID-GAME stops reading as an open ladder.

THE DATED SPECIMEN, read at the venue and in our own table in the same pass
(standing notice 26/27), live SF@LAR 2026-09-11:

* Kyren Williams scored the game's first touchdown at ~01:20Z. Kalshi closed his
  leg at ``01:20:26Z`` and finalized it ``result='yes'``,
  ``settlement_ts=01:22:33Z``, ``settlement_value_dollars=1.0000``; the 25 losing
  legs finalized ``result='no'`` by 01:45Z. Read off
  ``GET /trade-api/v2/markets?event_ticker=KXNFLFIRSTTD-26SEP10SFLAR``:
  31 legs — 26 ``finalized``, 5 ``inactive``.
* At 02:32Z, 70 minutes later and mid-SECOND-QUARTER, our row still read
  ``status='open'`` with every leg ungraded, and the event page drew an open
  26-rung ladder: Kyren Williams 99%, twenty-five others at 1%, summing to
  **124%** on a market where exactly one player can score first. The 99% is not
  a price — the book is empty on both sides (``yes_bid 0.0000 /
  yes_ask 1.0000``), so ``_kalshi_yes_probability`` falls through to
  ``last_price_dollars='0.9900'``, the dead last trade.

TWO INDEPENDENT DEFECTS PUT IT THERE, and either alone keeps the row open:

1. ``settle_kalshi_recent_finals`` selected only ``e.status = 'completed'``.
   Kalshi markets ``can_close_early`` ("This market will close and expire early
   if the event occurs"), so a decided question waits for the whistle.
2. ``derive_venue_settlement`` required EVERY leg terminal, and an ``inactive``
   leg never becomes terminal. So this market would not have settled at the
   whistle either, or on any sweep after it — the withholding is permanent, not
   late.

MEASURED BLAST RADIUS, all 48 live-event rows carrying the empty-book signature
at 02:5xZ: 38 ALL-terminal at the venue, 3 terminal-past-dormant-legs (this
market and both team-first-touchdown siblings), 6 genuinely part-settled, 1
genuinely open. 41 of 48 decided and unreachable.

WHAT THIS SHIP DOES NOT DO, stated so no test below is read as claiming it: it
writes no grade (CAL-P061 / #1852 — inherited unchanged). It makes the market
stop claiming to be open. The verdict a reader sees is a separate write on a
separate rung and #5024 stays open for it.

ON THE SELECTION TESTS. These drive ``run_recent_finals`` end to end against a
faked venue and assert the parameters actually bound, and they parse the
statement as Postgres — but they do NOT execute it against a real table, so they
cannot by themselves prove the predicate matches the specimen. That proof is the
production read recorded in the PR and on the issue, and it is named here rather
than implied.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils.kalshi_resolution_window import derive_venue_settlement

# `VENUE_DORMANT_STATUSES` is imported INSIDE its one test, not here. A
# module-level import of a name the fix introduces makes the whole file fail to
# COLLECT against pre-fix source — pytest exit 2, one error, no test results —
# so every assertion below would be bound to that one import instead of failing
# on its own merits. Red has to be per-test to mean anything (gotcha #124: only
# exit 1 is a result).

#: The specimen's own clock, fixed and offset-first so nothing below can branch
#: on the wall clock (gotcha #44).
NOW = datetime(2026, 9, 11, 2, 32, 0, tzinfo=timezone.utc)

#: Kalshi's backstop for the First Touchdown event — what the dormant legs keep.
BACKSTOP = datetime(2026, 9, 13, 0, 35, 0, tzinfo=timezone.utc)

#: The live SF@LAR row, in the selection's tuple shape.
FIRST_TD_ROW = (
    60249782,
    "KXNFLFIRSTTD-26SEP10SFLAR",
    BACKSTOP,
    datetime(2026, 9, 11, 0, 20, tzinfo=timezone.utc),
    2,
)

#: The venue's own answer for that event ticker, at the leg-status granularity
#: `derive_venue_settlement` reads: 26 finalized + 5 inactive.
FIRST_TD_STATUSES = ["finalized"] * 26 + ["inactive"] * 5


class TestADormantLegIsNotAPendingLeg:
    """`derive_venue_settlement` — defect 2, read straight off the specimen."""

    def test_the_specimen_settles_past_its_dormant_legs(self):
        """RED before #5024: 26 settled of 31 legs answered `partially_settled`,
        and no later sweep could ever change that — the 5 `inactive` legs carry
        the backstop close_time and never become terminal."""
        out = derive_venue_settlement(FIRST_TD_STATUSES)

        assert out.settled is True
        assert out.reason == "settled_past_dormant_legs"
        assert out.legs_total == 31
        assert out.legs_settled == 26

    def test_an_event_of_nothing_but_dormant_legs_does_not_settle(self):
        """The over-reach this fix must not commit. Dormant legs are ignored as
        PENDING; they are not evidence of settlement. With no settled leg at all
        the venue has told us nothing (gotcha #53) and the answer stays False."""
        out = derive_venue_settlement(["inactive", "inactive", "inactive"])

        assert out.settled is False
        assert out.reason == "open_at_venue"
        assert out.legs_settled == 0

    def test_a_still_running_match_with_a_dormant_leg_stays_open(self):
        """The tennis case the original paragraph protects, now carrying a
        dormant leg too: a set-winner event whose match is still running has
        `active` legs, and an `active` leg is PENDING. If this ever flips, a live
        market renders as over — the exact harm #2351 named."""
        out = derive_venue_settlement(["finalized", "active", "inactive"])

        assert out.settled is False
        assert out.reason == "partially_settled"

    def test_a_clean_sweep_is_still_reported_as_plain_settled(self):
        """No dormant legs ⇒ the pre-existing reason string, unchanged, so the
        new branch is legible in a report rather than absorbing the old one."""
        out = derive_venue_settlement(["finalized", "finalized"])

        assert out.settled is True
        assert out.reason == "settled"

    def test_an_absent_status_still_beats_the_dormant_rule(self):
        """Ordering matters: a leg the venue sent with no status at all is an
        unreadable answer, and unreadable outranks every other reading."""
        out = derive_venue_settlement(["finalized", "", "inactive"])

        assert out.settled is False
        assert out.reason == "status_absent"

    def test_the_dormant_vocabulary_is_exactly_the_venues_withdrawn_word(self):
        """One definition of "the venue is not trading this leg". #4356 blocked
        on two writers disagreeing about which legs are real; this asserts the
        set rather than leaving it to a reader to notice it drifted."""
        from app.utils.kalshi_resolution_window import VENUE_DORMANT_STATUSES

        assert VENUE_DORMANT_STATUSES == frozenset({"inactive"})


# ── the selection ──────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    TOTALS = (1, 0, 0, 1)

    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _Result([])
        if "count(*)" in sql:
            return _Result([self.TOTALS])
        return _Result(self._rows)

    async def commit(self):
        return None


class _Venue:
    """Kalshi, answering with the specimen's real leg statuses.

    It must be able to REFUSE — `statuses` is a parameter — or "reached the
    venue" and "wrote the row" become indistinguishable.
    """

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.asked: list[str] = []
        self.closed = False

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        iso = BACKSTOP.isoformat().replace("+00:00", "Z")
        return {
            "markets": [
                {
                    "ticker": f"{ticker}-{i}",
                    "status": s,
                    "close_time": iso,
                    "expiration_time": iso,
                    # The grade rides the same payload. This rail reads it and
                    # must never write it (CAL-P061 / #1852).
                    "result": "yes" if s == "finalized" else "",
                }
                for i, s in enumerate(self._statuses)
            ]
        }

    async def close(self):
        self.closed = True


def _drive(*, rows=(FIRST_TD_ROW,), statuses=FIRST_TD_STATUSES, apply=True, limit=200):
    recorder: list = []
    venue = _Venue(statuses)

    def maker():
        return _Session(recorder, list(rows))

    report = asyncio.run(
        sweep.run_recent_finals(
            limit=limit,
            apply=apply,
            session_maker=maker,
            client_factory=lambda: venue,
            now=NOW,
        )
    )
    selects = [(s, p) for s, p in recorder if not s.strip().upper().startswith("UPDATE")]
    updates = [p for s, p in recorder if s.strip().upper().startswith("UPDATE")]
    return report, selects, updates, venue


class TestTheSelectionReachesALiveGame:
    """Defect 1 — the arm could not see a game that had not finished."""

    def test_it_binds_a_live_floor_beside_the_final_floor(self):
        """RED before #5024: only `final_floor` was bound, because the statement
        had no live branch to bind for."""
        _, selects, _, _ = _drive()

        sql, params = selects[0]
        assert params["live_floor"] == NOW - timedelta(
            hours=sweep.LIVE_EVENT_WINDOW_HOURS
        )
        # The specimen kicked off 2h12m before the read. If the live band were
        # ever tightened below that, SF@LAR would fall out of its own guard.
        assert params["live_floor"] < FIRST_TD_ROW[3], (
            "the specimen's kickoff must be inside the band this arm asks for"
        )

    def test_the_statement_admits_a_live_event_and_screens_it_on_an_empty_book(self):
        """The screen is what keeps the bare `e.status='live'` cost off the
        venue: ~97 rows an NFL night, several hundred on a Sunday slate, most of
        them trading normally."""
        sql = _drive()[1][0][0]

        assert "e.status = 'live'" in sql
        assert "e.commence_time >= :live_floor" in sql
        assert "fo.current_yes_bid = 0" in sql
        assert "fo.current_yes_ask = 1" in sql

    def test_a_finished_game_still_takes_the_batch_before_any_live_one(self):
        """#4655's 30-minute bar is unchanged: `completed_at DESC NULLS LAST`
        sorts every final ahead of every live row, so the live arm can only
        consume capacity a final did not want."""
        sql = _drive()[1][0][0]
        order = sql.split("ORDER BY", 1)[1]

        assert "e.completed_at DESC NULLS LAST" in order
        assert order.index("e.completed_at DESC") < order.index("e.commence_time DESC")
        assert order.index("e.commence_time DESC") < order.index("fm.updated_at ASC")

    def test_the_completed_arm_is_untouched(self):
        """The live branch is additive. If this fails, #4655 regressed."""
        sql, params = _drive()[1][0]

        assert "e.status = 'completed'" in sql
        assert "e.completed_at >= :final_floor" in sql
        assert params["final_floor"] == NOW - timedelta(
            hours=sweep.RECENT_FINAL_WINDOW_HOURS
        )

    def test_the_statement_parses_as_postgres(self):
        """A syntax error here is otherwise found by a beat nobody is reading."""
        sqlglot = pytest.importorskip("sqlglot")
        sqlglot.parse_one(sweep.RECENT_FINAL_SELECT_SQL, dialect="postgres")


class TestTheSpecimenReachesTheWrite:
    """End to end on SF@LAR's own row: asked, derived, written — no grade."""

    def test_the_live_specimen_is_written_resolved(self):
        """RED before #5024 on BOTH counts: the row was never selected, and had
        it been, 26-of-31 answered `partially_settled` and no write followed."""
        _, _, updates, venue = _drive()

        assert venue.asked == ["KXNFLFIRSTTD-26SEP10SFLAR"]
        assert len(updates) == 1, "the live leg reaches the write"
        assert updates[0]["id"] == 60249782
        assert updates[0]["venue_settled"] is True

    def test_the_write_carries_no_grade(self):
        """CAL-P061 / #1852. The venue's `result='yes'` is in the payload this
        rail just read; it must not appear in the write. Asserted over the bound
        parameters, so a future column cannot smuggle one in unnoticed."""
        _, _, updates, _ = _drive()

        bound = updates[0]
        assert "is_winner" not in bound
        assert "resolution_source" not in bound
        assert not any("winner" in k or "result" in k for k in bound)

    def test_a_live_game_still_trading_is_asked_and_not_written(self):
        """The honest-refusal case: an empty book can be a thin market rather
        than a settled one, so the screen costs one question and no write."""
        _, _, updates, venue = _drive(statuses=["active", "active", "finalized"])

        assert venue.asked == ["KXNFLFIRSTTD-26SEP10SFLAR"], "the venue is asked"
        assert updates == [] or updates[0]["venue_settled"] is False, (
            "a still-trading event is never written settled"
        )
