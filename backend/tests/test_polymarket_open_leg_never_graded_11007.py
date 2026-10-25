"""#11007 — the Gamma winner rail grades only a leg the venue has closed.

THE SPECIMEN (production, read 2026-10-13). bainluck.com/futures/113883, "Fed
rate cut by...?" (Gamma event ``106884``), printed "This market has been
settled" with **October Meeting — Lost** and **December Meeting — Lost**. The
October FOMC meets Oct 27–28. Our rows:

* parent 113883 and its eight sub-legs ``status='resolved'``, all with
  ``updated_at 2026-07-21 20:15:02Z`` and ``resolution_date 2026-06-17``. The
  venue's own event runs to 2028-01-29.
* every parent outcome ``resolution_source='api_settlement'`` with the same
  ``last_updated 2026-09-28 21:48:51Z``. October is ``is_winner=false`` at
  ``current_probability 0.0095``, December at ``0.023``. Those are quotes, not
  settlement prices.

THE WRITER. ``_backfill_polymarket_winners_from_api`` selects on OUR
``status='resolved'``. Its negRisk/multi-leg branch then walked EVERY venue
sub-market and graded each on its quote (``>= 0.90`` won, anything else lost),
open or not. ``api_settlement`` is authoritative, so no later pass took the
grade back. The single-market branch and the condition-id phase had a terminal
price test but no ``closed`` test, so an open dust-priced leg such as October
at ``["0.0055","0.9945"]`` passed it.

THE FIX. All three branches require Gamma's per-leg ``closed`` (the flag the
champion mint already demanded, ``venue_has_closed_the_leg``) before they
grade or sync a price. An open leg is left untouched and counted
``legs_open_at_venue``.

WHAT THIS FILE DOES NOT CLAIM. It does not repair the stored rows. 113883's
fabricated grades and its July status stay until a reviewed, attended repair
runs. This file only proves that the rail stops writing such grades.

FIXTURE: ``tests/fixtures/polymarket_resolved_zero_legs_5343/gamma-event-106884.json``.
These are the venue's bytes for this event (Gamma ``GET /events/106884``,
2026-10-12T00:49:13Z, sha256 ``5ce0eea1…c224``), reused unedited. Every
negative below is derived from a real leg by changing one field.
"""

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.polymarket_api as poly_api_mod
import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state
import app.utils.polymarket_champion_mint as mint_mod
import app.utils.polymarket_settlement_scan as scan_mod

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_resolved_zero_legs_5343"
    / "gamma-event-106884.json"
)
SPECIMEN_BYTES = FIXTURE.read_bytes()
SPECIMEN = json.loads(SPECIMEN_BYTES)
EVENT_ID = "106884"
PARENT_ID = 113883
OCTOBER_CHILD_ID = 13792808

LEG_BY_TITLE = {m["groupItemTitle"]: m for m in SPECIMEN["markets"]}
OCTOBER = LEG_BY_TITLE["October 2026 Meeting"]
DECEMBER = LEG_BY_TITLE["December 2026 Meeting"]
OCT_CID = OCTOBER["conditionId"]
DEC_CID = DECEMBER["conditionId"]

#: The eight bare condition ids parent 113883 really holds (production read
#: 2026-10-13): six legs the venue closed, plus October and December.
STORED_TITLES = [
    "January Meeting", "March Meeting", "April Meeting", "June Meeting",
    "July Meeting", "September 2026 Meeting",
    "October 2026 Meeting", "December 2026 Meeting",
]
STORED_CIDS = {LEG_BY_TITLE[t]["conditionId"] for t in STORED_TITLES}
CLOSED_STORED_CIDS = STORED_CIDS - {OCT_CID, DEC_CID}
OPEN_AT_VENUE = [m for m in SPECIMEN["markets"] if m["closed"] is not True]


class _Row:
    def __init__(self, id, external_id, group_type=None, poly_event_id=None):
        self.id = id
        self.external_id = external_id
        self.group_type = group_type
        self.poly_event_id = poly_event_id


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


class _Recorder:
    """Every outcome write the rail issues, keyed by the condition id it hit."""

    def __init__(self, stored):
        self.stored = set(stored)
        self.grades = {}  # cid -> (is_winner, resolution_source)
        self.price_syncs = {}  # cid -> price

    def touched(self):
        return set(self.grades) | set(self.price_syncs)


def _install(monkeypatch, recorder, *, rows, event=None, market_by_id=None):
    rc = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)

    async def _execute(stmt, params=None):
        if type(stmt).__name__ == "Update":
            bound = stmt.compile().params
            cid = bound.get("external_id_1")
            if cid in recorder.stored:
                recorder.grades[cid] = (
                    bound.get("is_winner"), bound.get("resolution_source")
                )
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)
        sql = str(getattr(stmt, "text", stmt))
        p = params or {}
        if "FROM futures_markets fm" in sql:
            picked = [r for r in rows if r.id > (p.get("last_id") or 0)]
            return _Result(picked[: (p.get("limit") or len(picked))])
        if "UPDATE futures_outcomes" in sql:
            cid = p.get("cid")
            if cid in recorder.stored:
                if "is_winner" in sql:
                    won = p.get("won")
                    # #698: the negRisk arm's single settling statement carries
                    # its grade and terminal price as SQL literals, not binds.
                    if "SET is_winner = true," in sql:
                        won = True
                    elif "SET is_winner = false," in sql:
                        won = False
                    recorder.grades[cid] = (won, "api_settlement")
                    if "current_probability=1.0" in sql:
                        recorder.price_syncs[cid] = 1.0
                    elif "current_probability=0.0" in sql:
                        recorder.price_syncs[cid] = 0.0
                else:
                    recorder.price_syncs[cid] = p.get("price")
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)
        return MagicMock(rowcount=0)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_market_by_condition(self, cid):
            return (market_by_id or {}).get(str(cid))

        async def get_event_by_id(self, eid):
            return event if (event is not None and str(eid) == EVENT_ID) else None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)


def _parent_rows():
    return [_Row(PARENT_ID, EVENT_ID, None, EVENT_ID)]


async def _run_parent(monkeypatch, event=None):
    recorder = _Recorder(STORED_CIDS)
    _install(monkeypatch, recorder, rows=_parent_rows(), event=event or SPECIMEN)
    stats = await bw._backfill_polymarket_winners_from_api(limit=10)
    return stats, recorder


class TestTheFixtureIsTheSpecimen:
    def test_the_bytes_are_the_ones_read(self):
        assert hashlib.sha256(SPECIMEN_BYTES).hexdigest() == (
            "5ce0eea19067bd1691544f8d650a501bb3a3ef3b31fd2c8f630267883068c224"
        )

    def test_october_and_december_are_open_at_the_venue(self):
        assert str(SPECIMEN["id"]) == EVENT_ID
        assert SPECIMEN["closed"] is False
        for leg in (OCTOBER, DECEMBER):
            assert leg["closed"] is False
            assert leg.get("umaResolutionStatus") in (None, "")
        assert json.loads(OCTOBER["outcomePrices"]) == ["0.0055", "0.9945"]
        assert json.loads(DECEMBER["outcomePrices"]) == ["0.023", "0.977"]

    def test_the_six_other_stored_legs_are_closed_at_the_venue(self):
        for cid in CLOSED_STORED_CIDS:
            leg = next(m for m in SPECIMEN["markets"] if m["conditionId"] == cid)
            assert leg["closed"] is True
            assert json.loads(leg["outcomePrices"]) == ["0", "1"]

    def test_octobers_quote_passes_the_old_terminal_price_test(self):
        # Why the single-market branch needed the flag as well: 0.0055/0.9945
        # is "terminal" by `max >= 0.90 and min <= 0.10`.
        prices = [float(p) for p in json.loads(OCTOBER["outcomePrices"])]
        assert not (max(prices) < 0.90 or min(prices) > 0.10)


@pytest.mark.asyncio
class TestTheParentBranch:
    async def test_open_legs_are_neither_graded_nor_repriced(self, monkeypatch):
        stats, rec = await _run_parent(monkeypatch)
        assert OCT_CID not in rec.touched(), rec.grades
        assert DEC_CID not in rec.touched(), rec.grades
        assert stats["legs_open_at_venue"] == len(OPEN_AT_VENUE) == 7, stats

    async def test_closed_legs_still_grade_from_the_venue(self, monkeypatch):
        # The positive arm. A rule that refused every leg would pass the test
        # above; this pins that the six closed legs still grade as losers from
        # their terminal ["0","1"].
        stats, rec = await _run_parent(monkeypatch)
        assert set(rec.grades) == CLOSED_STORED_CIDS, sorted(rec.grades)
        assert all(g == (False, "api_settlement") for g in rec.grades.values())
        assert stats["losers_set"] == len(CLOSED_STORED_CIDS)

    async def test_control_without_the_gate_reproduces_production(self, monkeypatch):
        # CONTROL: with the flag test forced open AND #698's verified-payout
        # test replaced by the old quote rule (`prices[0] >= 0.90`), the real
        # rail grades what production holds for 113883: October and December
        # `is_winner=false, resolution_source='api_settlement'`.
        #
        # #698 changed two things this control used to pin. Forcing `closed`
        # open alone no longer reproduces it — the payout test refuses October's
        # 0.0055 quote on its own (see the next test) — and the price written
        # beside the grade is now the terminal 0 in the same statement, never
        # the quote, so the quote cannot reappear even under a forced grade.
        monkeypatch.setattr(mint_mod, "venue_has_closed_the_leg", lambda closed: True)

        def _old_quote_rule(m):
            prices = json.loads(m["outcomePrices"])
            return float(prices[0]) >= 0.90

        monkeypatch.setattr(scan_mod, "venue_terminal_leg_result", _old_quote_rule)
        stats, rec = await _run_parent(monkeypatch)
        assert rec.grades[OCT_CID] == (False, "api_settlement")
        assert rec.grades[DEC_CID] == (False, "api_settlement")
        assert rec.price_syncs[OCT_CID] == 0.0
        assert stats["legs_open_at_venue"] == 0

    async def test_forcing_only_the_closed_flag_no_longer_grades_a_quote(
        self, monkeypatch
    ):
        # #698: the two gates are independent. With `closed` forced open, the
        # verified-payout test still refuses October and December (no UMA
        # resolution, a quote rather than a 1/0 payout): nothing is written.
        monkeypatch.setattr(mint_mod, "venue_has_closed_the_leg", lambda closed: True)
        stats, rec = await _run_parent(monkeypatch)
        assert OCT_CID not in rec.touched(), rec.grades
        assert DEC_CID not in rec.touched(), rec.grades
        assert stats["legs_closed_without_verified_result"] == len(OPEN_AT_VENUE)

    async def test_a_string_false_flag_is_open(self, monkeypatch):
        event = copy.deepcopy(SPECIMEN)
        leg = next(m for m in event["markets"] if m["conditionId"] == OCT_CID)
        leg["closed"] = "false"
        _st, rec = await _run_parent(monkeypatch, event)
        assert OCT_CID not in rec.touched()

    async def test_an_absent_flag_is_open(self, monkeypatch):
        event = copy.deepcopy(SPECIMEN)
        leg = next(m for m in event["markets"] if m["conditionId"] == OCT_CID)
        leg.pop("closed")
        _st, rec = await _run_parent(monkeypatch, event)
        assert OCT_CID not in rec.touched()

    async def test_the_same_leg_grades_once_the_venue_closes_it(self, monkeypatch):
        # The venue closing October at ["0","1"] is a result, and the rail
        # writes it. The gate delays a grade; it never strands one.
        event = copy.deepcopy(SPECIMEN)
        leg = next(m for m in event["markets"] if m["conditionId"] == OCT_CID)
        leg["closed"] = True
        leg["outcomePrices"] = json.dumps(["0", "1"])
        # #698: and the venue's UMA resolution, as every settled leg of this
        # event carries — `closed` alone is no longer a result.
        leg["umaResolutionStatus"] = "resolved"
        _st, rec = await _run_parent(monkeypatch, event)
        assert rec.grades[OCT_CID] == (False, "api_settlement")


@pytest.mark.asyncio
class TestTheSingleMarketBranches:
    async def test_the_decomposed_october_child_is_not_graded(self, monkeypatch):
        # Phase B, single-market: the October child row (external_id = its
        # condition id) looked up inside the event payload.
        recorder = _Recorder({OCT_CID})
        _install(
            monkeypatch, recorder,
            rows=[_Row(OCTOBER_CHILD_ID, OCT_CID, None, EVENT_ID)],
            event=SPECIMEN,
        )
        stats = await bw._backfill_polymarket_winners_from_api(limit=10)
        assert recorder.touched() == set(), recorder.grades
        assert stats["legs_open_at_venue"] == 1, stats

    async def test_control_the_child_was_graded_before(self, monkeypatch):
        monkeypatch.setattr(mint_mod, "venue_has_closed_the_leg", lambda closed: True)
        recorder = _Recorder({OCT_CID})
        _install(
            monkeypatch, recorder,
            rows=[_Row(OCTOBER_CHILD_ID, OCT_CID, None, EVENT_ID)],
            event=SPECIMEN,
        )
        await bw._backfill_polymarket_winners_from_api(limit=10)
        assert recorder.grades[OCT_CID] == (False, "api_settlement")

    async def test_the_condition_phase_does_not_grade_an_open_market(self, monkeypatch):
        # Phase A: a row with no event id, addressed by Gamma's numeric market
        # id. Its outcome rows are keyed by that id (`fo.external_id = :cid`).
        gamma_id = str(OCTOBER["id"])
        recorder = _Recorder({gamma_id, f"{gamma_id}_no"})
        _install(
            monkeypatch, recorder,
            rows=[_Row(OCTOBER_CHILD_ID, gamma_id, None, None)],
            market_by_id={gamma_id: OCTOBER},
        )
        stats = await bw._backfill_polymarket_winners_from_api(limit=10)
        assert recorder.touched() == set(), recorder.grades
        assert stats["legs_open_at_venue"] == 1, stats

    async def test_control_the_condition_phase_grades_a_closed_market(self, monkeypatch):
        gamma_id = str(OCTOBER["id"])
        closed = dict(OCTOBER, closed=True, outcomePrices=json.dumps(["0", "1"]))
        recorder = _Recorder({gamma_id, f"{gamma_id}_no"})
        _install(
            monkeypatch, recorder,
            rows=[_Row(OCTOBER_CHILD_ID, gamma_id, None, None)],
            market_by_id={gamma_id: closed},
        )
        stats = await bw._backfill_polymarket_winners_from_api(limit=10)
        assert recorder.grades[gamma_id] == (False, "api_settlement")
        assert recorder.grades[f"{gamma_id}_no"] == (True, "api_settlement")
        assert stats["legs_open_at_venue"] == 0
