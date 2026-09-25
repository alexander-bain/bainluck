"""#7930 — a finished game's Polymarket questions are re-read after the start, not a week later.

THE DEFECT (production, 2026-09-25, issuecomment-5830715391): the sunk-recovery
pass had two six-hour windows that cancel out after first pitch. The poll last
stamps a game parent 0–2h before the start; `SUNK_POLY_STALE_HOURS` (6) holds it
out until about start+6h, which is exactly when the unlinked-game arm's 6h
lookback closes (and the head arm lets go once the event leaves live/scheduled).
The row then falls to the imminent arm, ordered by `resolution_date` — start+7d
— behind a pool at its 300 limit. So the game's questions stayed `open` on our
side while the venue had closed them: 19 of 24 sampled post-start parents read
`closed=true` on Gamma (6/8 at 4–8h, 6/8 at 8–16h, 7/8 at 16–36h).

THE FIX is ordering, no writer: a post-start arm selects open parents whose own
`venue_game_start` is inside the last 48h, linked or not, read after one hour
of staleness instead of six, oldest start first, right after the two game arms.
The writer already settles a closed event (#7930's direct-address half); this
arm only makes the re-read arrive.

The SQL's clauses are executed against real Postgres in
`tests/integration/test_dark_polymarket_selector_real_postgres.py`
(`TestTheSunkPostStartArmAgainstRealPostgres`); this file drives the pass.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager

import pytest

from app.tasks import polymarket as poly
from tests.test_polymarket_sunk_open_events_6758 import (
    _closed,
    _Gamma,
    _literal,
    _market_rows,
    _parent_update_set,
    _Redis,
    _Row,
    _SelectorSession,
    _service,
)
from tests.test_polymarket_sunk_unlinked_game_arm_8373 import SPECIMEN, SPECIMEN_RAW
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession

ROW_ID = 61799932


async def _run(monkeypatch, *, head=(), unlinked=(), post_start=(), imminent=(), rotate=(),
               gamma=None, redis=None):
    """Drive the REAL pass. The selector answers in execution order: imminent,
    rotate, head, unlinked game, then post-start (executed last, read third)."""
    gamma = gamma or _Gamma(by_id={SPECIMEN: SPECIMEN_RAW})
    redis = redis or _Redis()
    selector = _SelectorSession(
        [list(imminent), list(rotate), list(head), list(unlinked), list(post_start)]
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


class TestAFinishedGameIsSettledWhenReached:
    @pytest.mark.asyncio
    async def test_a_closed_game_reached_by_the_arm_is_written_resolved(self, monkeypatch):
        gamma = _Gamma(by_id={SPECIMEN: _closed(SPECIMEN_RAW)})
        stats, writer, *_ = await _run(
            monkeypatch, post_start=[_Row(ROW_ID, SPECIMEN)], gamma=gamma,
        )
        assert stats["post_start_selected"] == 1
        assert stats["events_closed_at_venue"] == 1
        update = _parent_update_set(writer, SPECIMEN)
        assert _literal(update["status"]) == "resolved"
        assert "settled_at" in update

    @pytest.mark.asyncio
    async def test_a_game_still_open_at_the_venue_stays_open(self, monkeypatch):
        # Still being played (or not yet closed): the re-read only restamps it.
        stats, writer, *_ = await _run(monkeypatch, post_start=[_Row(ROW_ID, SPECIMEN)])
        assert stats["events_closed_at_venue"] == 0
        assert _literal(_parent_update_set(writer, SPECIMEN)["status"]) == "open"


class TestThePostStartArmIsReadThird:
    @pytest.mark.asyncio
    async def test_behind_a_full_imminent_arm_it_is_in_the_first_request(self, monkeypatch):
        # Before #7930 this row's only selector was the imminent arm, ordered by
        # a resolution a week out, behind 300 others.
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        _st, _w, _s, gamma, _r = await _run(
            monkeypatch, post_start=[_Row(ROW_ID, SPECIMEN)], imminent=imminent,
        )
        assert _batches(gamma)[0][0] == SPECIMEN

    @pytest.mark.asyncio
    async def test_the_two_game_arms_still_go_first(self, monkeypatch):
        _st, _w, _s, gamma, _r = await _run(
            monkeypatch,
            head=[_Row(1, "1038120")],
            unlinked=[_Row(2, "1058698")],
            post_start=[_Row(ROW_ID, SPECIMEN)],
            imminent=[_Row(3, "4000001")],
        )
        assert _batches(gamma)[0][:4] == ["1038120", "1058698", SPECIMEN, "4000001"]

    @pytest.mark.asyncio
    async def test_an_id_in_two_arms_is_read_once(self, monkeypatch):
        _st, writer, _s, gamma, _r = await _run(
            monkeypatch,
            post_start=[_Row(ROW_ID, SPECIMEN)],
            imminent=[_Row(ROW_ID, SPECIMEN)],
            rotate=[_Row(ROW_ID, SPECIMEN)],
        )
        assert [i for b in _batches(gamma) for i in b] == [SPECIMEN]
        assert len(_market_rows(writer)[SPECIMEN]) == 1

    @pytest.mark.asyncio
    async def test_a_post_start_only_selection_is_not_an_empty_pass(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, post_start=[_Row(ROW_ID, SPECIMEN)])
        assert stats["terminal"] != "no_sunk_open_events"
        assert stats["events_reached"] == 1

    @pytest.mark.asyncio
    async def test_the_pool_limit_is_reported(self, monkeypatch):
        rows = [_Row(i, str(6_000_000 + i)) for i in range(poly._SUNK_POLY_POST_START_MAX)]
        stats, *_ = await _run(monkeypatch, post_start=rows, gamma=_Gamma(by_id={}))
        assert stats["post_start_selected"] == poly._SUNK_POLY_POST_START_MAX
        assert stats["post_start_pool_at_limit"] is True


class TestTheRotateCursor:
    @pytest.mark.asyncio
    async def test_a_post_start_row_that_is_also_a_rotate_row_does_not_jump_the_cursor(self, monkeypatch):
        rotate = [_Row(i, str(5_000_000 + i)) for i in range(1, 26)] + [_Row(9000, SPECIMEN)]
        gamma = _Gamma(by_id={SPECIMEN: SPECIMEN_RAW}, status_for_batch={2: 429})
        stats, _w, _s, _g, redis = await _run(
            monkeypatch, post_start=[_Row(9000, SPECIMEN)], rotate=rotate, gamma=gamma,
        )
        assert stats["rate_limited"]
        assert _batches(gamma)[0][0] == SPECIMEN
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "19"


class TestThePostStartSelector:
    SQL = str(poly._SUNK_POLY_POST_START_SQL)

    def _predicates(self):
        return "\n".join(line.split("--")[0] for line in self.SQL.lower().splitlines())

    def test_every_other_arm_keeps_its_predicate_byte_for_byte(self):
        assert poly._SUNK_POLY_WHERE == poly._sunk_poly_where("stale_hours")
        for sql in (poly._SUNK_POLY_HEAD_SQL, poly._SUNK_POLY_UNLINKED_GAME_SQL,
                    poly._SUNK_POLY_IMMINENT_SQL, poly._SUNK_POLY_ROTATE_SQL):
            assert poly._SUNK_POLY_WHERE in str(sql)
            assert ":post_start_stale_hours" not in str(sql)

    def test_staleness_is_its_own_bound_and_the_floor_is_the_shared_one(self):
        sql = self._predicates()
        assert "fm.volume_updated_at < now() - make_interval(hours => :post_start_stale_hours)" in sql
        assert "fm.resolution_date > now() - make_interval(hours => :stale_hours)" in sql
        assert "volume_updated_at < now() - make_interval(hours => :stale_hours)" not in sql

    def test_it_takes_linked_and_unlinked_parents_alike(self):
        # The head arm lets a linked game go once its event leaves
        # live/scheduled, so a post-start arm that skipped linked rows would
        # leave half the defect in place.
        sql = self._predicates()
        assert "event_id" not in sql
        assert "join" not in sql

    def test_it_is_windowed_behind_the_start_ordered_oldest_first_and_bounded(self):
        sql = self._predicates()
        assert "s.venue_start > now() - make_interval(hours => :post_start_lookback_hours)" in sql
        assert "s.venue_start <= now()" in sql
        assert re.search(r"order by s\.venue_start, s\.id\s+limit :max_rows", sql)

    def test_the_stamp_is_parsed_behind_the_shared_shape_guard(self):
        assert poly._SUNK_POLY_VENUE_START in self.SQL

    def test_text_reads_no_bind_parameter_out_of_the_regex(self):
        assert set(poly._SUNK_POLY_POST_START_SQL.compile().params) == {
            "stale_hours", "post_start_stale_hours", "post_start_lookback_hours",
            "refused", "max_rows",
        }

    def test_the_bounds(self):
        assert poly.SUNK_POLY_POST_START_STALE_HOURS == 1
        assert poly.SUNK_POLY_POST_START_LOOKBACK_HOURS == 48
        assert poly.SUNK_POLY_POST_START_STALE_HOURS < poly.SUNK_POLY_STALE_HOURS
        assert poly._SUNK_POLY_POST_START_MAX == 200
        total = (
            poly._SUNK_POLY_HEAD_MAX + poly._SUNK_POLY_UNLINKED_GAME_MAX
            + poly._SUNK_POLY_POST_START_MAX + poly._SUNK_POLY_IMMINENT_MAX
            + poly._SUNK_POLY_ROTATE_MAX
        )
        assert -(-total // poly._LINKED_POLY_ID_BATCH) == 55

    @pytest.mark.asyncio
    async def test_it_is_sent_its_own_staleness_window_and_ceiling(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch, redis=_Redis(refused={"123"}))
        sql, params = next(c for c in selector.calls if c[0] == self.SQL)
        assert params["post_start_stale_hours"] == poly.SUNK_POLY_POST_START_STALE_HOURS
        assert params["post_start_lookback_hours"] == poly.SUNK_POLY_POST_START_LOOKBACK_HOURS
        assert params["stale_hours"] == poly.SUNK_POLY_STALE_HOURS
        assert params["max_rows"] == poly._SUNK_POLY_POST_START_MAX
        assert params["refused"] == ["123"]
