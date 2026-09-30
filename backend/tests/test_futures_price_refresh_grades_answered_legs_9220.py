"""#9220: a leg Kalshi settled on a board that is still open stops printing its
pre-settlement price.

WHAT A READER SAW, 2026-09-28 00:1xZ. New York won Game 1 of a best-of-3, so
Kalshi finalized ``KXWNBASERIESSCORE-26NYMINR1-MIN20`` ("MIN wins 2-0") NO. The
hourly refresh re-priced the board's three live legs at 23:50:34Z — and
``/events/15318132`` still led its Series card with **MIN wins 2-0 43.5%**, the
2026-09-26 05:02Z price, because ``_fetch_kalshi_prices`` dropped an answered
leg with a bare ``continue`` and no grader reaches a leg whose EVENT is still
open (every Kalshi grader reads ``status="settled"`` events, or markets we
already hold ``resolved``).

THE POPULATION, venue-read 2026-09-28 00:2xZ: over the 166 open Kalshi boards
this task priced in the prior two hours, legs frozen ≥6h behind their board's
newest stamp, each looked up on Kalshi's own event payload —

    active, no verdict      635   (the #7582 clear's population, untouched here)
    ticker not on payload   294
    finalized / no           39   ┐ 71 legs on 13 boards: eliminated ATP
    finalized / yes          32   ┘ Chengdu players at 29-48%, settled NFL and
                                    NCAAF win-count rungs, both WNBA sweep legs

None of the 71 carried a ``calibration_probability``.

═══ WHAT THESE TESTS CAN AND CANNOT PROVE ═══

``_ClearSession`` (borrowed from #7582's module) records statements and answers
``rowcount=1`` without evaluating a WHERE, so a behavioural assertion on it is
vacuous for the guard clause. The guard is therefore pinned on the COMPILED
statement (``TestTheGradeStatement``), and the control flow — flag routing, the
None verdict, the missing ``written`` gate — is asserted behaviourally, which
the fake can answer.
"""

import asyncio
import inspect

import pytest
from sqlalchemy.dialects import postgresql

from app.services.kalshi_api import KalshiAPIService
from app.tasks import futures_price_refresh as fpr
from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES
from tests.test_futures_price_refresh_clears_venue_unpriced_7582 import _ClearSession


def _leg(ticker, status, result, bid, ask, last):
    return {
        "ticker": ticker,
        "status": status,
        "result": result,
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "last_price_dollars": last,
        "close_time": "2026-10-02T00:00:00Z",
    }


#: The specimen as Kalshi served it 2026-09-28 00:1xZ, to the cent.
NYMIN_SCORE = {
    "event_ticker": "KXWNBASERIESSCORE-26NYMINR1",
    "title": "Series Exact Score: New York vs Minnesota",
    "markets": [
        _leg("KXWNBASERIESSCORE-26NYMINR1-NY21", "active", "", "0.1300", "0.2300", "0.1900"),
        _leg("KXWNBASERIESSCORE-26NYMINR1-MIN21", "active", "", "0.3000", "0.4000", "0.4000"),
        _leg("KXWNBASERIESSCORE-26NYMINR1-NY20", "active", "", "0.2200", "0.4100", "0.4700"),
        _leg("KXWNBASERIESSCORE-26NYMINR1-MIN20", "finalized", "no", "0.0000", "1.0000", "0.0600"),
    ],
}


class _Venue:
    """`get_event` over a fixed payload; the PARSER is the real one."""

    def __init__(self, raw):
        self._raw = raw
        self._svc = KalshiAPIService(api_key=None)

    async def get_event(self, ticker, with_nested_markets=True):
        return self._raw

    def _parse_event(self, raw):
        return self._svc._parse_event(raw)


def _fetch(raw):
    return asyncio.run(fpr._fetch_kalshi_prices(_Venue(raw), raw["event_ticker"]))


class TestTheFetchCarriesTheVerdict:
    def test_the_specimen_carries_min20_with_the_venues_no(self):
        items = _fetch(NYMIN_SCORE)
        (min20,) = [i for i in items if i["external_id"].endswith("-MIN20")]
        assert min20["venue_answered"] is True
        assert min20["venue_won"] is False
        assert min20["probability"] is None, "a settlement is never carried as a price"

    def test_the_live_legs_are_priced_exactly_as_before(self):
        items = _fetch(NYMIN_SCORE)
        priced = {i["external_id"]: i for i in items if not i.get("venue_answered")}
        assert set(priced) == {
            "KXWNBASERIESSCORE-26NYMINR1-NY21",
            "KXWNBASERIESSCORE-26NYMINR1-MIN21",
            "KXWNBASERIESSCORE-26NYMINR1-NY20",
        }
        assert all(i["probability"] is not None for i in priced.values())

    def test_a_yes_verdict_is_carried_as_a_win(self):
        raw = dict(NYMIN_SCORE)
        raw["markets"] = [
            NYMIN_SCORE["markets"][0],
            _leg("KXWNBASERIESSCORE-26NYMINR1-NY20", "finalized", "yes", "0.0000", "1.0000", "0.9900"),
        ]
        (ny20,) = [i for i in _fetch(raw) if i.get("venue_answered")]
        assert ny20["venue_won"] is True

    def test_a_scalar_settlement_carries_no_verdict(self):
        """`gradeable_winner`'s None survives the trip: a settlement on a NUMBER
        is not a side, and #1852 forbids recording it as a loss."""
        raw = dict(NYMIN_SCORE)
        raw["markets"] = [
            NYMIN_SCORE["markets"][0],
            _leg("KXWNBASERIESSCORE-26NYMINR1-MIN20", "finalized", "scalar", "0.0000", "1.0000", "0.0600"),
        ]
        (leg,) = [i for i in _fetch(raw) if i.get("venue_answered")]
        assert leg["venue_won"] is None

    def test_an_all_answered_event_is_still_venue_settled_not_graded_here(self):
        """The #5771 whole-event verdict is unchanged: it returns before any leg
        is carried, and that path has its own withdrawal."""
        raw = dict(NYMIN_SCORE)
        raw["markets"] = [NYMIN_SCORE["markets"][3]]
        assert _fetch(raw) is fpr.VENUE_SETTLED


_BOARD = 62383747
_ROWS = (
    (235705711, "KXWNBASERIESSCORE-26NYMINR1-MIN20"),
    (235705712, "KXWNBASERIESSCORE-26NYMINR1-MIN21"),
)


def _min21():
    return {
        "external_id": "KXWNBASERIESSCORE-26NYMINR1-MIN21",
        "probability": 0.37,
        "yes_bid": 0.17,
        "yes_ask": 0.57,
        "last_price": 0.40,
    }


def _min20(won=False):
    return {
        "external_id": "KXWNBASERIESSCORE-26NYMINR1-MIN20",
        "probability": None,
        "venue_answered": True,
        "venue_won": won,
    }


def _grades(session):
    """The UPDATEs that are grades — the ones writing `resolution_source`."""
    out = []
    for st in session.updates:
        compiled = st.compile(dialect=postgresql.dialect())
        if "resolution_source=" in str(compiled).replace(" ", ""):
            out.append(compiled)
    return out


def _write(items, rows=_ROWS):
    session = _ClearSession(rows)
    stats: dict = {}
    written = asyncio.run(fpr._write_prices(session, _BOARD, "kalshi", items, stats))
    return session, stats, written


class TestTheWriterGrades:
    def test_the_specimen_leg_is_graded(self):
        session, stats, written = _write([_min21(), _min20()])
        assert written == 1, "only the live leg is a price"
        assert len(_grades(session)) == 1
        assert stats["answered_legs_graded"] == 1

    def test_no_snapshot_is_written_for_a_graded_leg(self):
        """A settlement is not an observed price, and the graders write none."""
        session, _, _ = _write([_min21(), _min20()])
        assert session.inserts == 1, "exactly one snapshot — MIN 2-1's"

    def test_the_grade_is_not_gated_on_a_priced_sibling(self):
        """🔴 The opposite of #7582's clear, on purpose. That clear waits for a
        split because SILENCE is not evidence; a declared result is. A board
        whose only item this pass is an answered leg is still graded."""
        session, stats, written = _write([_min20()])
        assert written == 0
        assert len(_grades(session)) == 1
        assert stats["answered_legs_graded"] == 1

    def test_a_none_verdict_is_counted_and_nothing_is_written(self):
        session, stats, _ = _write([_min21(), _min20(won=None)])
        assert _grades(session) == []
        assert stats["answered_legs_ungradeable"] == 1
        assert stats.get("answered_legs_graded", 0) == 0

    def test_an_answered_leg_is_never_cleared_as_unpriced(self):
        """The two flags stay two paths: the clear is #7582's, keyed on silence."""
        session, stats, _ = _write([_min21(), _min20()])
        assert session.clears() == []
        assert stats.get("legs_cleared_venue_unpriced", 0) == 0

    def test_a_leg_we_do_not_hold_is_not_graded(self):
        """`existing` excludes a crowned or `api_settlement` leg, so a graded leg
        is not re-graded every hour — and a ticker we never held is not minted."""
        session, stats, _ = _write([_min21(), _min20()], rows=_ROWS[1:])
        assert _grades(session) == []
        assert stats.get("answered_legs_graded", 0) == 0


class TestTheGradeStatement:
    """Pinned on the compiled SQL — see the module docstring for why."""

    def _compiled(self, won=False):
        session, _, _ = _write([_min21(), _min20(won)])
        (grade,) = _grades(session)
        return grade

    def test_a_no_writes_the_loss_and_the_zero_together(self):
        c = self._compiled(False)
        assert c.params["is_winner"] is False
        assert c.params["resolution_source"] == "api_settlement"
        assert c.params["current_probability"] == 0.0
        assert c.params["current_american_odds"] is None

    def test_a_yes_writes_the_win_and_the_one_together(self):
        c = self._compiled(True)
        assert c.params["is_winner"] is True
        assert c.params["current_probability"] == 1.0

    def test_it_overwrites_only_an_ungraded_row_or_a_guess(self):
        text = str(self._compiled())
        assert "futures_outcomes.resolution_source IS NULL" in text
        assert "futures_outcomes.resolution_source IN" in text
        bound = [v for v in self._compiled().params.values() if isinstance(v, (list, tuple))]
        assert list(OVERWRITABLE_WINNER_SOURCES) in [list(b) for b in bound], (
            "the graders' own overwritable set, imported — not a local list"
        )

    def test_the_compiled_read_can_fail(self):
        """Control: the substring test above is not satisfied by anything that is
        always in an UPDATE of this table: the price write on the same board
        carries no such clause."""
        session, _, _ = _write([_min21()])
        assert session.updates, "the control must have a statement to read"
        for st in session.updates:
            assert "resolution_source IS NULL" not in str(
                st.compile(dialect=postgresql.dialect())
            )

    @pytest.mark.parametrize(
        "column", ["calibration_probability", "opening_probability", "opening_captured_at"]
    )
    def test_no_calibration_input_is_in_the_set_list(self, column):
        """Gotcha #144: the curve price is COALESCE(calibration, opening). A grade
        moves neither."""
        set_clause = str(self._compiled()).split(" WHERE ")[0]
        assert column not in set_clause

    def test_the_price_change_stamp_is_maintained(self):
        """`tests/test_price_stamp_writer_scan_4958.py`'s contract: every price
        write against FuturesOutcome maintains `price_changed_at`."""
        assert "price_changed_at=CASE" in str(self._compiled()).replace(" ", "")


def test_the_counters_are_named_in_the_writer_not_only_in_comments():
    source = inspect.getsource(fpr._write_prices)
    assert '"answered_legs_graded"' in source
    assert '"answered_legs_ungradeable"' in source
