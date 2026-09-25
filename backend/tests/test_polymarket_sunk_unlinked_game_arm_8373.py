"""#8373 — a MOVED Polymarket game is re-read before first pitch, not after the final.

THE SPECIMEN (production, 2026-09-24 07:40Z, #8373): Cubs at Red Sox split
doubleheader, 09-25. Game 1 (`/events/15316415`, 17:05Z) read "No price yet"
while Polymarket priced it. Polymarket event 1058697 — slug
`mlb-chc-bos-2026-09-27`, the Sunday game — had been MOVED to game 1: Gamma's
`startTime` now reads 2026-09-25T17:05Z. Our parent row (61799932) still held
the pre-move `venue_game_start` 2026-09-27T19:05Z, `event_id` NULL, 0 children,
last written on its listing day (09-21 20:15Z).

WHY NOTHING RE-READ IT: the sunk-recovery head arm (#837) joins `events`, so it
cannot see an UNLINKED parent — and a moved game is unlinked precisely because
its stored start is stale. It fell to the imminent arm, ordered by
`resolution_date` (10-04), behind thousands of rows at 300 a pass.

THE FIX is ordering again, no writer: an unlinked-game arm selects sunk parents
with no `events` link whose own stored `venue_game_start` sits in the linked
window, soonest first, read right after the head. The poll's writer rewrites the
stamp; the matcher does the rest.

FIXTURE — `tests/fixtures/polymarket_sunk_unlinked_8373/event-1058697.json.gz`:
LOSSLESS venue bytes, `GET gamma-api.polymarket.com/events/1058697` read
2026-09-24 08:47Z (gzip only; decompressed SHA256 `d4ceef50…397f`).
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
    _parent_update_set,
    _Redis,
    _Row,
    _SelectorSession,
    _service,
)
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_sunk_unlinked_8373"
    / "event-1058697.json.gz"
)
SPECIMEN_BYTES = gzip.decompress(FIXTURE.read_bytes())
SPECIMEN_RAW = json.loads(SPECIMEN_BYTES)
SPECIMEN = "1058697"
SPECIMEN_ROW_ID = 61799932
MOVED_TO = "2026-09-25T17:05"
STORED_BEFORE_THE_MOVE = "2026-09-27T19:05"


async def _run(monkeypatch, *, head=(), unlinked=(), imminent=(), rotate=(), gamma=None, redis=None):
    """Drive the REAL pass. The selector answers in execution order: imminent,
    rotate, head, then the unlinked-game arm (executed last, read second)."""
    gamma = gamma or _Gamma(by_id={SPECIMEN: SPECIMEN_RAW})
    redis = redis or _Redis()
    selector = _SelectorSession([list(imminent), list(rotate), list(head), list(unlinked)])
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
        assert hashlib.sha256(SPECIMEN_BYTES).hexdigest().startswith("d4ceef50")

    def test_it_is_the_sunday_slug_moved_to_game_one(self):
        assert str(SPECIMEN_RAW["id"]) == SPECIMEN
        assert SPECIMEN_RAW["slug"] == "mlb-chc-bos-2026-09-27", "the slug still names the pre-move day"
        assert SPECIMEN_RAW["startTime"].startswith(MOVED_TO)
        moneyline = next(m for m in SPECIMEN_RAW["markets"] if m["sportsMarketType"] == "moneyline")
        assert json.loads(moneyline["outcomes"]) == ["Chicago Cubs", "Boston Red Sox"]


class TestTheUnlinkedGameIsReadSecond:
    @pytest.mark.asyncio
    async def test_behind_a_full_imminent_arm_it_is_in_the_first_request(self, monkeypatch):
        # 300 imminent rows = 15 batches. Before #8373 the specimen was not
        # selected by anything ahead of them.
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        stats, _w, _s, gamma, _r = await _run(
            monkeypatch, unlinked=[_Row(SPECIMEN_ROW_ID, SPECIMEN)], imminent=imminent,
        )
        assert stats["unlinked_game_selected"] == 1
        assert _batches(gamma)[0][0] == SPECIMEN

    @pytest.mark.asyncio
    async def test_the_linked_head_still_goes_first(self, monkeypatch):
        stats, _w, _s, gamma, _r = await _run(
            monkeypatch,
            head=[_Row(1, "1038120")],
            unlinked=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            imminent=[_Row(2, "4000001")],
        )
        assert _batches(gamma)[0][:3] == ["1038120", SPECIMEN, "4000001"]

    @pytest.mark.asyncio
    async def test_an_id_in_two_arms_is_read_once(self, monkeypatch):
        _st, writer, _s, gamma, _r = await _run(
            monkeypatch,
            unlinked=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            imminent=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            rotate=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        assert [i for b in _batches(gamma) for i in b] == [SPECIMEN]
        assert len(_market_rows(writer)[SPECIMEN]) == 1

    @pytest.mark.asyncio
    async def test_an_unlinked_only_selection_is_not_an_empty_pass(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, unlinked=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        assert stats["terminal"] != "no_sunk_open_events"
        assert stats["events_reached"] == 1


class TestTheReReadRewritesTheStaleStart:
    """The substrate of the ship: once re-read, the parent carries the venue's
    MOVED instant, which is what the matcher's fixture guard compares."""

    @pytest.mark.asyncio
    async def test_the_parent_update_writes_the_moved_start(self, monkeypatch):
        _st, writer, *_ = await _run(monkeypatch, unlinked=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        # The ON CONFLICT arm — the specimen row already exists — not the INSERT
        # values: `preserve_venue_settled(<new metadata>, <column>)`.
        expr = _parent_update_set(writer, SPECIMEN)["market_metadata"]
        written = [
            v for v in expr.compile().params.values()
            if isinstance(v, dict) and "venue_game_start" in v
        ]
        assert len(written) == 1, written
        assert written[0]["venue_game_start"].startswith(MOVED_TO)
        assert not written[0]["venue_game_start"].startswith(STORED_BEFORE_THE_MOVE)


class TestTheRotateCursor:
    @pytest.mark.asyncio
    async def test_an_unlinked_row_that_is_also_a_rotate_row_does_not_jump_the_cursor(self, monkeypatch):
        # Same hazard #837 closed for the head: read in an early chunk, it must
        # not carry the rotate cursor past r20..r25 when chunk 2 is refused.
        rotate = [_Row(i, str(5_000_000 + i)) for i in range(1, 26)] + [_Row(9000, SPECIMEN)]
        gamma = _Gamma(by_id={SPECIMEN: SPECIMEN_RAW}, status_for_batch={2: 429})
        stats, _w, _s, _g, redis = await _run(
            monkeypatch, unlinked=[_Row(9000, SPECIMEN)], rotate=rotate, gamma=gamma,
        )
        assert stats["rate_limited"]
        assert _batches(gamma)[0][0] == SPECIMEN
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "19"


class TestTheUnlinkedGameSelector:
    SQL = str(poly._SUNK_POLY_UNLINKED_GAME_SQL)

    def _predicates(self):
        return "\n".join(line.split("--")[0] for line in self.SQL.lower().splitlines())

    def test_it_is_the_sunk_predicate_verbatim(self):
        assert poly._SUNK_POLY_WHERE in self.SQL

    def test_it_takes_only_unlinked_parents(self):
        # A linked parent is the head arm's; reading it twice is waste, and a
        # join would make this arm blind to the specimen again.
        assert "fm.event_id is null" in self._predicates()
        assert "join" not in self._predicates()

    def test_it_is_windowed_ordered_and_bounded_on_the_stored_start(self):
        sql = self._predicates()
        assert "s.venue_start > now() - make_interval(hours => :lookback_hours)" in sql
        assert "s.venue_start <= now() + make_interval(days => :horizon_days)" in sql
        assert re.search(r"order by s\.venue_start, s\.id\s+limit :max_rows", sql)

    def test_the_stamp_is_parsed_behind_a_shape_guard(self):
        # A bare cast would let one malformed stamp fail the whole pass.
        assert poly._SUNK_POLY_VENUE_START in self.SQL
        assert re.search(r"case when .* ~ '\^\[0-9\]\{4\}", poly._SUNK_POLY_VENUE_START.lower(), re.S)

    def test_text_reads_no_bind_parameter_out_of_the_regex(self):
        assert set(poly._SUNK_POLY_UNLINKED_GAME_SQL.compile().params) == {
            "stale_hours", "refused", "lookback_hours", "horizon_days", "max_rows",
        }

    @pytest.mark.asyncio
    async def test_it_is_sent_the_linked_window_and_its_own_ceiling(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch, redis=_Redis(refused={"123"}))
        sql, params = next(c for c in selector.calls if c[0] == self.SQL)
        assert params["horizon_days"] == poly.LINKED_POLY_BOOK_HORIZON_DAYS
        assert params["lookback_hours"] == poly.LINKED_POLY_BOOK_LOOKBACK_HOURS
        assert params["stale_hours"] == poly.SUNK_POLY_STALE_HOURS
        assert params["max_rows"] == poly._SUNK_POLY_UNLINKED_GAME_MAX
        assert params["refused"] == ["123"]

    def test_the_arm_adds_ten_gamma_calls_and_takes_none_from_the_others(self):
        assert poly._SUNK_POLY_HEAD_MAX == 100
        assert poly._SUNK_POLY_IMMINENT_MAX == 300
        assert poly._SUNK_POLY_ROTATE_MAX == 300
        total = (
            poly._SUNK_POLY_HEAD_MAX + poly._SUNK_POLY_UNLINKED_GAME_MAX
            + poly._SUNK_POLY_IMMINENT_MAX + poly._SUNK_POLY_ROTATE_MAX
        )
        assert -(-total // poly._LINKED_POLY_ID_BATCH) == 45
