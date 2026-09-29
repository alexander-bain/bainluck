"""#9572 — an NFL game whose Polymarket parent never got its children is re-read days before kickoff.

THE SPECIMEN (production, 2026-09-29 08:00Z, #9572): Rams @ Eagles, Sun Oct 4
(`/events/14781137`). The page blended sportsbooks + Kalshi only. Our Polymarket
parent 59552330 (Gamma 909441, `nfl-la-phi-2026-10-04`) was linked correctly but
held 0 outcomes and NO child row; its last write was 09-20 02:31Z. The venue
listed 328 markets, 78 priced, moneyline 3871423 at 61.5 / 38.5. Ten more Week 5
games had the same shape.

WHY NOTHING RE-READ IT: the poll sees only the newest 2,000 listings, and the
sunk pass's head arm reads 100 stale linked parents a pass, soonest kick-off
first, at its limit — 1,221 of 4,000 kicked off before Oct 4 17:00Z.

THE FIX is ordering again, no writer: a childless-game arm selects stale linked
`polymarket_event` parents whose group holds no `polymarket_sub_market` row,
soonest kick-off first, read right after the head. The poll's writer mints the
children; the aggregator does the rest.

FIXTURE — `tests/fixtures/polymarket_sunk_childless_9572/event-909441.json.gz`:
LOSSLESS venue bytes, `GET gamma-api.polymarket.com/events/909441` read
2026-09-29 08:15Z (gzip only; decompressed SHA256 `273a9037…af57`).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.tasks import polymarket as poly
from tests.test_polymarket_sunk_open_events_6758 import (
    _Gamma,
    _market_rows,
    _Redis,
    _Row,
    _SelectorSession,
    _service,
)
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_sunk_childless_9572"
    / "event-909441.json.gz"
)
SPECIMEN_BYTES = gzip.decompress(FIXTURE.read_bytes())
SPECIMEN_RAW = json.loads(SPECIMEN_BYTES)
SPECIMEN = "909441"
SPECIMEN_ROW_ID = 59552330
MONEYLINE = next(m for m in SPECIMEN_RAW["markets"] if m["sportsMarketType"] == "moneyline")


async def _run(
    monkeypatch, *, head=(), childless=(), unlinked=(), imminent=(), rotate=(),
    gamma=None, redis=None,
):
    """Drive the REAL pass. The selector answers in execution order: imminent,
    rotate, head, unlinked-game, post-start, then the childless-game arm
    (executed last, read second)."""
    gamma = gamma or _Gamma(by_id={SPECIMEN: SPECIMEN_RAW})
    redis = redis or _Redis()
    selector = _SelectorSession(
        [list(imminent), list(rotate), list(head), list(unlinked), [], list(childless)]
    )
    writer = RecordingSession()
    sessions = iter([selector])

    @asynccontextmanager
    async def _fake_session():
        yield next(sessions, writer)

    async def _no_link():
        return 0

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(poly, "link_polymarket_sub_markets", _no_link)
    monkeypatch.setattr(poly, "_SUNK_POLY_DIRECT_PAUSE_S", 0)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: _service(gamma))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
    stats = await poly._recover_sunk_polymarket_events()
    return stats, writer, selector, gamma, redis


def _batches(gamma):
    return [u.params.get_list("id") for u in gamma.requests if u.params.get_list("id")]


class TestTheFixtureIsTheSpecimen:
    def test_the_bytes_are_the_ones_read(self):
        assert hashlib.sha256(SPECIMEN_BYTES).hexdigest().startswith("273a9037")

    def test_it_is_the_week_5_game_the_venue_prices(self):
        assert str(SPECIMEN_RAW["id"]) == SPECIMEN
        assert SPECIMEN_RAW["slug"] == "nfl-la-phi-2026-10-04"
        assert len(SPECIMEN_RAW["markets"]) == 328
        assert json.loads(MONEYLINE["outcomes"]) == ["Rams", "Eagles"]
        assert json.loads(MONEYLINE["outcomePrices"]) == ["0.615", "0.385"]

    def test_the_writer_would_find_priced_children(self):
        # The pass's own census on the parsed event: this is a reach defect,
        # not a venue that has nothing to price.
        event = _service(_Gamma())._parse_event(SPECIMEN_RAW)
        assert poly.sunk_event_is_open(event)
        assert poly.sunk_event_child_census(event) == (328, 78)


class TestTheChildlessGameIsReadSecond:
    @pytest.mark.asyncio
    async def test_behind_a_full_imminent_arm_it_is_in_the_first_request(self, monkeypatch):
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        stats, _w, _s, gamma, _r = await _run(
            monkeypatch, childless=[_Row(SPECIMEN_ROW_ID, SPECIMEN)], imminent=imminent,
        )
        assert stats["childless_game_selected"] == 1
        assert _batches(gamma)[0][0] == SPECIMEN

    @pytest.mark.asyncio
    async def test_it_goes_after_the_head_and_before_the_unlinked_arm(self, monkeypatch):
        _st, _w, _s, gamma, _r = await _run(
            monkeypatch,
            head=[_Row(1, "1038120")],
            childless=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            unlinked=[_Row(3, "1058697")],
            imminent=[_Row(2, "4000001")],
        )
        assert _batches(gamma)[0][:4] == ["1038120", SPECIMEN, "1058697", "4000001"]

    @pytest.mark.asyncio
    async def test_an_id_in_the_head_and_this_arm_is_read_once(self, monkeypatch):
        _st, writer, _s, gamma, _r = await _run(
            monkeypatch,
            head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            childless=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            imminent=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        assert [i for b in _batches(gamma) for i in b] == [SPECIMEN]
        assert len(_market_rows(writer)[SPECIMEN]) == 1

    @pytest.mark.asyncio
    async def test_a_childless_only_selection_is_not_an_empty_pass(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, childless=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        assert stats["terminal"] != "no_sunk_open_events"
        assert stats["events_reached"] == 1

    @pytest.mark.asyncio
    async def test_the_pool_limit_is_reported(self, monkeypatch):
        full = [_Row(i, str(6_000_000 + i)) for i in range(poly._SUNK_POLY_CHILDLESS_GAME_MAX)]
        stats, *_ = await _run(monkeypatch, childless=full, gamma=_Gamma())
        assert stats["childless_game_pool_at_limit"] is True
        stats, *_ = await _run(monkeypatch, childless=full[:-1], gamma=_Gamma())
        assert stats["childless_game_pool_at_limit"] is False


class TestTheReReadMintsTheMoneyline:
    """The substrate of the ship: once re-read, the moneyline exists as a child
    row, which is the row the blend reads."""

    @pytest.mark.asyncio
    async def test_the_writer_upserts_the_moneyline_child(self, monkeypatch):
        _st, writer, *_ = await _run(monkeypatch, childless=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        rows = _market_rows(writer)
        assert SPECIMEN in rows, "the parent itself is re-written (stamps volume_updated_at)"
        assert MONEYLINE["conditionId"] in rows, sorted(rows)[:5]
        child = rows[MONEYLINE["conditionId"]][0]
        assert child["group_id"] == f"polymarket:{SPECIMEN}"
        assert child["group_type"] == "polymarket_sub_market"

    @pytest.mark.asyncio
    async def test_without_the_arm_a_full_head_never_reaches_it(self, monkeypatch):
        # CONTROL: the same pass with the specimen where production had it —
        # not in the head's 100 — reads everything else and not the specimen.
        head = [_Row(i, str(7_000_000 + i)) for i in range(poly._SUNK_POLY_HEAD_MAX)]
        _st, writer, _s, gamma, _r = await _run(monkeypatch, head=head, gamma=_Gamma(by_id={SPECIMEN: SPECIMEN_RAW}))
        assert SPECIMEN not in [i for b in _batches(gamma) for i in b]
        assert MONEYLINE["conditionId"] not in _market_rows(writer)


class TestTheRotateCursor:
    @pytest.mark.asyncio
    async def test_a_childless_row_that_is_also_a_rotate_row_does_not_jump_the_cursor(self, monkeypatch):
        rotate = [_Row(i, str(5_000_000 + i)) for i in range(1, 26)] + [_Row(9000, SPECIMEN)]
        gamma = _Gamma(by_id={SPECIMEN: SPECIMEN_RAW}, status_for_batch={2: 429})
        stats, _w, _s, _g, redis = await _run(
            monkeypatch, childless=[_Row(9000, SPECIMEN)], rotate=rotate, gamma=gamma,
        )
        assert stats["rate_limited"]
        assert _batches(gamma)[0][0] == SPECIMEN
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "19"


class TestTheChildlessGameSelector:
    SQL = str(poly._SUNK_POLY_CHILDLESS_GAME_SQL)

    def _predicates(self):
        return "\n".join(line.split("--")[0] for line in self.SQL.lower().splitlines())

    def test_it_is_the_sunk_predicate_verbatim(self):
        assert poly._SUNK_POLY_WHERE in self.SQL

    def test_it_is_the_linked_game_window_verbatim(self):
        # The head arm's window, so the two arms never disagree about which
        # games are on now or soon.
        assert poly._LINKED_POLY_EVENT_WINDOW in self.SQL
        assert "join events e on e.id = s.event_id" in self._predicates()

    def test_it_takes_only_game_parents(self):
        assert "fm.group_type = 'polymarket_event'" in self._predicates()

    def test_childless_means_no_sub_market_row_in_the_group_of_any_status(self):
        sql = self._predicates()
        m = re.search(r"and not exists \((.*?)\)\s+order by", sql, re.S)
        assert m, sql
        inner = m.group(1)
        assert "c.group_id = s.group_id" in inner
        assert "c.group_type = 'polymarket_sub_market'" in inner
        # A resolved child still proves the writer reached the game.
        assert "status" not in inner

    def test_it_is_ordered_soonest_and_bounded(self):
        assert re.search(r"order by e\.commence_time, s\.id\s+limit :max_rows", self._predicates())

    def test_text_reads_only_the_expected_bind_parameters(self):
        assert set(poly._SUNK_POLY_CHILDLESS_GAME_SQL.compile().params) == {
            "stale_hours", "refused", "lookback_hours", "horizon_days", "max_rows",
        }

    @pytest.mark.asyncio
    async def test_it_is_sent_the_linked_window_and_its_own_ceiling(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch, redis=_Redis(refused={"123"}))
        sql, params = next(c for c in selector.calls if c[0] == self.SQL)
        assert params["horizon_days"] == poly.LINKED_POLY_BOOK_HORIZON_DAYS
        assert params["lookback_hours"] == poly.LINKED_POLY_BOOK_LOOKBACK_HOURS
        assert params["stale_hours"] == poly.SUNK_POLY_STALE_HOURS
        assert params["max_rows"] == poly._SUNK_POLY_CHILDLESS_GAME_MAX
        assert params["refused"] == ["123"]

    @pytest.mark.asyncio
    async def test_it_is_executed_last_so_the_other_arms_keep_their_order(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch)
        assert selector.calls[-1][0] == self.SQL
        assert len(selector.calls) == 6

    def test_the_arm_adds_five_gamma_calls(self):
        assert poly._SUNK_POLY_CHILDLESS_GAME_MAX == 100
        assert -(-poly._SUNK_POLY_CHILDLESS_GAME_MAX // poly._LINKED_POLY_ID_BATCH) == 5
