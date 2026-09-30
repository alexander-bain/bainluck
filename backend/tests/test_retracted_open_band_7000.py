"""#7000 band 6 — the scheduled grader asks about fully retracted open markets.

The WHERE clause is proved against a real PostgreSQL in
`tests/integration/test_kalshi_settlement_recency_band_pg.py` (the band-6
section). This file proves the other half: the REAL `_backfill_kalshi_winners`
calls band 6 with its own budget and cursor, sends what it selects to the venue,
writes the venue's answer over the retraction, and closes the board.

THE SPECIMEN (production 2026-09-30). `KXMLBBESTRECORD-26`, "Pro Baseball Best
Record": Kalshi finalized all 30 legs at 2026-09-28 01:02Z with
`KXMLBBESTRECORD-26-MIL` = `yes`. We held the row `open` with every leg
`is_winner=false / ungradeable_result`, Milwaukee included, and the Yankees'
team page offered "Worst Record 1%" beside it as an open question.
"""

from __future__ import annotations

import pytest

import app.tasks.backfill_winners as bw
from tests.test_grader_flips_status_when_venue_is_terminal_7870 import (
    _FakeRedis,
    _drive,
    _event,
)

SPECIMEN = "KXMLBBESTRECORD-26"


def _specimen_event() -> dict:
    """Three of the thirty legs, as the venue read them at 08:50Z 9/30."""
    return _event(
        ("KXMLBBESTRECORD-26-MIL", "finalized", "yes"),
        ("KXMLBBESTRECORD-26-NYY", "finalized", "no"),
        ("KXMLBBESTRECORD-26-LAD", "finalized", "no"),
    )


def _outcome_grades(session) -> list[str]:
    """The per-leg grade writes: UPDATE futures_outcomes ... api_settlement."""
    return [
        s
        for s in session.statements
        if s.upper().startswith("UPDATE")
        and "futures_outcomes" in s
        and "api_settlement" in s
    ]


@pytest.mark.asyncio
class TestTheScheduledCallerRunsBandSix:
    async def test_the_pass_asks_band_six_for_its_own_budget_and_cursor(
        self, monkeypatch
    ):
        """Called with `_RETRACTED_OPEN_MAX_TICKERS`, off its OWN key. Taking
        the cycle `limit` would spend bands 1 and 2's allowance (gotcha #34)."""
        rc = _FakeRedis()
        rc.store[bw._RETRACTED_OPEN_CURSOR_KEY] = "KXM"
        calls: dict = {}

        await _drive(
            monkeypatch,
            ticker=SPECIMEN,
            event=_specimen_event(),
            via_band="retracted_open",
            redis=rc,
            calls=calls,
        )

        assert "retracted_open" in calls, "the scheduled pass never ran band 6"
        limit_, cursor_ = calls["retracted_open"]
        assert limit_ == bw._RETRACTED_OPEN_MAX_TICKERS
        assert cursor_ == "KXM", "band 6 must read its OWN cursor key"

    async def test_the_specimen_is_graded_and_closed_through_band_six_alone(
        self, monkeypatch
    ):
        """The ship: selector → venue → grade over the retraction → status.

        Every other band returns nothing here, so the venue call and both
        writes can only have come from band 6.
        """
        stats, session, venue = await _drive(
            monkeypatch,
            ticker=SPECIMEN,
            event=_specimen_event(),
            via_band="retracted_open",
        )

        assert venue.asked == [SPECIMEN]
        assert stats["retracted_open_selected"] == 1
        assert stats["winners_set"] == 1, "Milwaukee's `yes` was not written"
        assert stats["losers_set"] == 2
        assert len(_outcome_grades(session)) == 3
        assert stats["status_resolved"] == 1
        assert (
            session.market_status_updates()
        ), "the venue finalized every leg and the board stayed open"

    async def test_a_still_trading_member_is_asked_and_left_alone(self, monkeypatch):
        """Most of the cohort is still trading (#7000's probe: ~12% finalized).
        The band asks; only the venue settles. No grade, no status."""
        stats, session, _ = await _drive(
            monkeypatch,
            ticker="KXNFLSEED-27",
            event=_event(
                ("KXNFLSEED-27-BUF", "active", ""),
                ("KXNFLSEED-27-KC", "active", ""),
            ),
            via_band="retracted_open",
        )

        assert stats["retracted_open_selected"] == 1
        assert _outcome_grades(session) == []
        assert stats["status_resolved"] == 0
        assert session.market_status_updates() == []

    async def test_a_pass_with_no_band_six_rows_records_a_zero(self, monkeypatch):
        stats, _, _ = await _drive(
            monkeypatch,
            ticker="AAA",
            event=_event(("A", "active", None)),
            via_band="fresh",
        )

        assert stats["retracted_open_selected"] == 0


@pytest.mark.asyncio
class TestBandSixsCursorIsItsOwn:
    async def test_it_advances_its_own_key_and_touches_no_other(self, monkeypatch):
        rc = _FakeRedis()

        await _drive(
            monkeypatch,
            ticker=SPECIMEN,
            event=_specimen_event(),
            via_band="retracted_open",
            redis=rc,
        )

        assert rc.store.get(bw._RETRACTED_OPEN_CURSOR_KEY) == SPECIMEN
        assert bw._STATUS_SYNC_CURSOR_KEY not in rc.store, "band 5's key moved"
        assert bw._LONGDATED_CURSOR_KEY not in rc.store, "band 4's key moved"
        assert (
            "bainluck:kalshi_winner_backfill_cursor" not in rc.store
        ), "band 2's key moved"

    async def test_an_empty_sweep_wraps_the_cursor_so_the_band_restarts(
        self, monkeypatch
    ):
        """Without the wrap the band walks to `Z` and never asks again, and a
        member the venue settles next month is never revisited."""
        rc = _FakeRedis()
        rc.store[bw._RETRACTED_OPEN_CURSOR_KEY] = "ZZZZ"

        await _drive(
            monkeypatch,
            ticker="AAA",
            event=_event(("A", "active", None)),
            via_band="fresh",  # band 6 returns [] on this path
            redis=rc,
        )

        assert bw._RETRACTED_OPEN_CURSOR_KEY not in rc.store

    async def test_an_empty_sweep_on_a_cold_cursor_writes_nothing(self, monkeypatch):
        rc = _FakeRedis()

        await _drive(
            monkeypatch,
            ticker="AAA",
            event=_event(("A", "active", None)),
            via_band="fresh",
            redis=rc,
        )

        assert bw._RETRACTED_OPEN_CURSOR_KEY not in rc.store


@pytest.mark.asyncio
async def test_zero_budget_runs_no_statement():
    """`limit=0` returns `[]` without touching the server, so the band can be
    turned off in an incident by one constant."""

    class _Boom:
        async def execute(self, *a, **k):  # pragma: no cover — must not run
            raise AssertionError("band 6 ran its statement on a zero budget")

    assert await bw._select_kalshi_retracted_open_tickers(_Boom(), 0, "") == []
