"""#9970: /economics stops hiding a release whose title month has passed but
which has not settled.

From 2026-10-01 00:00Z the route's title-month filter dropped
"Inflation in September 2026 (CPI YoY)" (55686483), "Core inflation in
September 2026 (Core CPI YoY)" (55686484) and "September 2026 CPI MoM Combo"
(61484986) — all three settle 2026-10-14, because September CPI prints in
October. The title names the month a statistic DESCRIBES; `resolution_date`
is when it is decided, and while that is still ahead the market is not past.

The title arm still retires everything else: a past-month market whose
resolution date has gone by, and one with no resolution date at all
(settled Kalshi rows stay `status='open'`, gotcha #33).
"""

import pytest

from .test_economics_one_block_per_release_8018 import (
    ALL_SPECS,
    ARG_POLY,
    COMBO,
    _at,
    _blocks,
    _cpi_market,
    pin_route_clock,
)
from .test_route_economics import _query_result

#: The run that went red: master CI, 2026-10-01 00:39Z.
OCT_1 = _at("2026-10-01T00:39")
#: One minute after the last September print settles (12:29Z on 10-14).
AFTER_THE_PRINT = _at("2026-10-14T12:30")

SEPTEMBER_PRINTS = {55686483, 55686484, COMBO[0]}

AUGUST_SETTLED = (55000001, "kalshi", "Inflation in August 2026 (CPI YoY)", "2026-09-11T12:29", 900000)


async def _ids(client, mock_db, specs, *, extra=()):
    mock_db.execute.return_value = _query_result([_cpi_market(s) for s in specs] + list(extra))
    body = (await client.get("/api/economics")).json()
    return {b["market_id"] for b in body["themes"]["inflation"]["cpi_releases"]}


class TestTheTitleMonthYieldsToAFutureResolution:
    async def test_the_september_prints_are_served_on_october_1(self, client, mock_db, monkeypatch):
        pin_route_clock(monkeypatch, OCT_1)
        ids = await _ids(client, mock_db, ALL_SPECS)
        assert SEPTEMBER_PRINTS <= ids, ids

    async def test_the_six_slots_are_unchanged_on_october_1(self, client, mock_db, monkeypatch):
        # The #8018 card, a month boundary later: the same six releases, not
        # the lower-volume twins the title filter left behind.
        pin_route_clock(monkeypatch, OCT_1)
        ids = {b["market_id"] for b in await _blocks(client, mock_db)}
        assert ids == {ARG_POLY[0], COMBO[0], 364212, 55686485, 55686484, 55686483}


class TestTheTitleArmStillRetires:
    async def test_a_past_month_market_whose_resolution_has_passed_is_dropped(
        self, client, mock_db, monkeypatch
    ):
        pin_route_clock(monkeypatch, OCT_1)
        ids = await _ids(client, mock_db, ALL_SPECS + [AUGUST_SETTLED])
        assert AUGUST_SETTLED[0] not in ids

    async def test_a_past_month_market_with_no_resolution_date_is_dropped(
        self, client, mock_db, monkeypatch
    ):
        pin_route_clock(monkeypatch, OCT_1)
        undated = _cpi_market(AUGUST_SETTLED)
        undated.resolution_date = None
        ids = await _ids(client, mock_db, ALL_SPECS, extra=[undated])
        assert AUGUST_SETTLED[0] not in ids

    async def test_control_the_september_prints_retire_once_they_settle(
        self, client, mock_db, monkeypatch
    ):
        # Same rows, clock moved past their resolution: the title arm takes
        # them again. If this fails, the tests above are not reading the gate
        # that #9970 changed.
        pin_route_clock(monkeypatch, AFTER_THE_PRINT)
        ids = await _ids(client, mock_db, ALL_SPECS)
        assert not (SEPTEMBER_PRINTS & ids), ids

    async def test_the_august_row_reaches_the_card_when_its_title_is_current(
        self, client, mock_db, monkeypatch
    ):
        # Non-vacuity for the two drops above: in August the same row is
        # served, so its absence on Oct 1 is the filter, not the fixture.
        pin_route_clock(monkeypatch, _at("2026-08-20T12:00"))
        ids = await _ids(client, mock_db, [AUGUST_SETTLED])
        assert AUGUST_SETTLED[0] in ids
