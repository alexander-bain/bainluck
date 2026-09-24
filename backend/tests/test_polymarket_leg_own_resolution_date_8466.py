"""#8466 — a decomposed Polymarket leg resolves on its OWN date, not its event's.

PILLAR: TRUTH. SHIP: "US x Iran ceasefire continues through September 30?"
stops reading "Resolves Oct 31, 2026" on Discover.

Every leg was stamped with ``event.end_date`` on the belief, written into the
hindsight helper's docstring, that "decomposed sub-markets carry no per-market
date". Gamma carries one on every leg. The fixture is Gamma's own bytes for the
filed event (PROVENANCE.md), driven through the REAL parser: the load-bearing
claim is that ``endDate`` reaches the DTO from a venue payload at all, and a
hand-built ``PolymarketMarket(end_date=...)`` would pass if the parser dropped it.

The upsert itself (insert stamps the leg date; re-ingest repairs an open leg and
leaves a settled one) is graded on real Postgres in
``tests/integration/test_polymarket_leg_resolution_date_8466_pg.py``.
"""

import inspect
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_leg_dates_8466"
    / "gamma-event-1038648.json"
)


def _utc(y, m, d):
    return datetime(y, m, d, 23, 59, tzinfo=timezone.utc)


EVENT_END = _utc(2026, 10, 31)
LEG_ENDS = {
    "September 20?": _utc(2026, 9, 20),
    "September 25?": _utc(2026, 9, 25),
    "September 30?": _utc(2026, 9, 30),
    "October 31?": _utc(2026, 10, 31),
    "November 30?": _utc(2026, 11, 30),
    "December 31?": _utc(2026, 12, 31),
}


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())


def _parsed(raw=None):
    event = PolymarketAPIService()._parse_event(raw or _raw())
    assert event is not None, "the parser refused Gamma's own payload"
    assert len(event.markets) == 6, "the parser dropped a leg"
    return event


def _leg(event, suffix):
    hits = [m for m in event.markets if m.question.endswith(suffix)]
    assert len(hits) == 1, suffix
    return hits[0]


class TestTheLegDateSurvivesTheRealParser:
    def test_every_leg_carries_its_own_end_date(self):
        event = _parsed()
        assert {s: _leg(event, s).end_date for s in LEG_ENDS} == LEG_ENDS

    def test_the_event_keeps_its_own_separately(self):
        assert _parsed().end_date == EVENT_END

    def test_a_leg_gamma_serves_without_one_parses_to_none(self):
        raw = _raw()
        for m in raw["markets"]:
            m.pop("endDate", None)
        assert all(m.end_date is None for m in _parsed(raw).markets)


class TestSubmarketResolutionDate:
    def test_the_filed_leg_resolves_on_september_30_not_the_events_october_31(self):
        event = _parsed()
        assert poly.submarket_resolution_date(event, _leg(event, "September 30?")) == _utc(
            2026, 9, 30
        )

    def test_a_leg_ending_after_its_event_is_not_pulled_earlier(self):
        """The other direction: stored as Oct 31, a Dec 31 leg read as over on Nov 1."""
        event = _parsed()
        assert poly.submarket_resolution_date(event, _leg(event, "December 31?")) == _utc(
            2026, 12, 31
        )

    def test_every_leg_takes_its_own_and_none_takes_the_events(self):
        event = _parsed()
        got = {s: poly.submarket_resolution_date(event, _leg(event, s)) for s in LEG_ENDS}
        assert got == LEG_ENDS
        assert sum(1 for v in got.values() if v == EVENT_END) == 1  # only the Oct 31 leg

    def test_a_leg_without_its_own_date_falls_back_to_the_event(self):
        raw = _raw()
        for m in raw["markets"]:
            m.pop("endDate", None)
        event = _parsed(raw)
        assert all(
            poly.submarket_resolution_date(event, m) == EVENT_END for m in event.markets
        )

    def test_no_market_and_a_bare_caller_fall_back_to_the_event(self):
        class _Bare:
            end_date = EVENT_END

        assert poly.submarket_resolution_date(_Bare(), None) == EVENT_END
        assert poly.submarket_resolution_date(_Bare(), object()) == EVENT_END

    def test_the_hindsight_predicate_now_sees_the_legs_own_end(self):
        """#2027 arm: a capture after Sep 30 on the Sep 30 leg is hindsight even
        while its event runs to Oct 31; the same capture on the Dec 31 leg is not."""
        event = _parsed()
        oct_5 = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        sep30, dec31 = _leg(event, "September 30?"), _leg(event, "December 31?")
        assert poly.opening_capture_is_hindsight(
            event, sep30, poly.submarket_resolution_date(event, sep30), oct_5
        ) is True
        assert poly.opening_capture_is_hindsight(
            event, dec31, poly.submarket_resolution_date(event, dec31), oct_5
        ) is False


class TestTheWriterUsesIt:
    """Source-level, comments stripped so prose cannot satisfy or break it."""

    @staticmethod
    def _code() -> str:
        src = inspect.getsource(poly._process_event_batch)
        return "\n".join(line.split("#")[0] for line in src.splitlines())

    def test_the_leg_insert_stamps_the_leg_date(self):
        code = self._code()
        assert "sub_resolution_date = submarket_resolution_date(" in code
        assert len(re.findall(r"resolution_date=sub_resolution_date,", code)) == 1

    def test_the_leg_hindsight_check_reads_the_leg_date(self):
        assert re.search(
            r"opening_capture_is_hindsight\(\s*event, market, sub_resolution_date, now\s*\)",
            self._code(),
        )

    def test_the_repair_is_gated_on_an_open_leg_with_its_own_date(self):
        code = self._code()
        assert re.search(
            r'if sub_open and getattr\(market, "end_date", None\) is not None:\s*'
            r'sub_set\["resolution_date"\] = market\.end_date',
            code,
        )

    def test_the_parent_row_still_takes_the_events_date(self):
        assert "resolution_date = event.end_date" in self._code()
