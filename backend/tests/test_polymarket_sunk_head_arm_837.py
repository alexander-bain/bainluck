"""#837 / #5273 — a sunk Polymarket parent whose game is on now is read FIRST.

THE SPECIMEN (measured 2026-09-23 23:30Z, #5273 comment 5804670581): Blue
Jays–Orioles, event 15317724, Polymarket parent 61294015 / Gamma 1038120. The
parent was last stamped by the discovery poll on its listing day (09-17), when
its moneyline book was empty and the child was correctly refused. Nothing minted
the child afterwards: the sunk-recovery pass orders its imminent arm by
`resolution_date`, which for a Polymarket MLB game is Gamma's `endDate` (09-30,
a week after first pitch), and the specimen sat behind 3,515 of 6,324 rows at
300 a pass. So the game was played with no winner price on the page.

THE FIX is ordering, not a writer: a head arm selects sunk parents linked to a
live or imminent event (#3613's window, without its zero-outcomes clause),
soonest kick-off first, and their ids lead the work list. The poll's own writer
does the rest, every refusal included.

FIXTURE — `tests/fixtures/polymarket_sunk_head_837/event-1038120.json.gz`:
LOSSLESS venue bytes, `GET gamma-api.polymarket.com/events/1038120` read
2026-09-23 23:43Z (gzip only; decompressed SHA256 `703bca77…544c`). 27 markets,
the moneyline `0x8eee18ee…` among them, `outcomes` `["Toronto Blue Jays",
"Baltimore Orioles"]` — the exact strings latency/1008 named as the transport's
subscription constraint.
"""
from __future__ import annotations

import gzip
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
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession, _bound_params

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "polymarket_sunk_head_837" / "event-1038120.json.gz"
SPECIMEN_RAW = json.loads(gzip.decompress(FIXTURE.read_bytes()))
SPECIMEN = "1038120"
SPECIMEN_ROW_ID = 61294015
MONEYLINE_CID = "0x8eee18eeea3f5bb9778240b1b41a383b22a51b2edd5004ac25735346100a7370"
MONEYLINE_RAW = next(m for m in SPECIMEN_RAW["markets"] if m["conditionId"] == MONEYLINE_CID)
GAMMA_OUTCOMES = json.loads(MONEYLINE_RAW["outcomes"])
GAMMA_TOKENS = json.loads(MONEYLINE_RAW["clobTokenIds"])


async def _run(monkeypatch, *, head=(), imminent=(), rotate=(), gamma=None, redis=None, **kw):
    """Drive the REAL pass. The selector answers in execution order: imminent,
    rotate, then the head arm (executed last, read first — see the task)."""
    gamma = gamma or _Gamma(by_id={SPECIMEN: SPECIMEN_RAW})
    redis = redis or _Redis()
    selector = _SelectorSession([list(imminent), list(rotate), list(head)])
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
    stats = await poly._recover_sunk_polymarket_events(**kw)
    return stats, writer, selector, gamma, redis


def _batches(gamma):
    return [u.params.get_list("id") for u in gamma.requests if u.params.get_list("id")]


def _child_leg_inserts(writer, condition_id):
    """Bound params of the futures_outcomes INSERTs hung on the CHILD row for one
    condition, in the order the writer emitted them — the order their ids are
    minted, which is the order the transport zips tokens onto.

    Keyed on `market_id`, not an `external_id` prefix: the PARENT's own raw leg
    also carries the bare condition id, and a prefix match would fold it in.
    `RecordingSession` answers statement i (0-based) with id 1001 + i.
    """
    child_ids = {
        1001 + i
        for i, stmt in enumerate(writer.statements)
        if getattr(getattr(stmt, "table", None), "name", None) == "futures_markets"
        and getattr(stmt, "is_insert", False)
        and _bound_params(stmt).get("external_id") == condition_id
    }
    assert len(child_ids) == 1, child_ids
    return [
        _bound_params(stmt)
        for stmt in writer.statements
        if getattr(getattr(stmt, "table", None), "name", None) == "futures_outcomes"
        and getattr(stmt, "is_insert", False)
        and _bound_params(stmt).get("market_id") in child_ids
    ]


class TestTheFixtureIsTheSpecimen:
    def test_it_is_the_named_game_and_its_moneyline(self):
        assert str(SPECIMEN_RAW["id"]) == SPECIMEN
        assert SPECIMEN_RAW["endDate"].startswith("2026-09-30"), (
            "the resolution date a week after first pitch is WHY the imminent arm reached it late"
        )
        assert MONEYLINE_RAW["sportsMarketType"] == "moneyline"
        assert GAMMA_OUTCOMES == ["Toronto Blue Jays", "Baltimore Orioles"]
        assert len(GAMMA_TOKENS) == 2 and GAMMA_TOKENS[0] != GAMMA_TOKENS[1]


class TestTheHeadIsReadFirst:
    @pytest.mark.asyncio
    async def test_a_live_game_behind_a_full_imminent_arm_is_in_the_first_request(self, monkeypatch):
        # 300 imminent rows ahead of it = 15 batches. Without the head arm the
        # specimen would be the 301st id; with it, the first.
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        stats, _w, _s, gamma, _r = await _run(
            monkeypatch, head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)], imminent=imminent,
        )
        assert stats["head_selected"] == 1
        first = _batches(gamma)[0]
        assert first[0] == SPECIMEN

    @pytest.mark.asyncio
    async def test_an_id_in_the_head_and_the_imminent_arm_is_read_once(self, monkeypatch):
        stats, writer, _s, gamma, _r = await _run(
            monkeypatch,
            head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            imminent=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        ids = [i for b in _batches(gamma) for i in b]
        assert ids == [SPECIMEN]
        assert len(_market_rows(writer)[SPECIMEN]) == 1

    @pytest.mark.asyncio
    async def test_a_head_only_selection_is_not_an_empty_pass(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        assert stats["terminal"] != "no_sunk_open_events"
        assert stats["events_reached"] == 1


class TestTheWriterMintsTheMissingChild:
    """The ship: the moneyline child row that never existed now does, and the
    live-price transport can attribute both of its legs.

    latency/1008 (23:00Z): the child's market-level `clob_token_ids` are zipped
    onto its outcomes IN INSERT ORDER, and a leg is subscribed by its exact name.
    A wrong order streams each team the other team's price; a wrong name leaves
    the leg unsubscribed. Both are pinned here on the venue's own bytes.
    """

    @pytest.mark.asyncio
    async def test_the_moneyline_child_is_written(self, monkeypatch):
        _st, writer, *_ = await _run(monkeypatch, head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        rows = _market_rows(writer)
        assert MONEYLINE_CID in rows, "the child #5273 found missing must be minted"
        child = rows[MONEYLINE_CID][0]
        assert child["category"] == "game_prop"
        assert child["group_id"] == f"polymarket:{SPECIMEN}"

    @pytest.mark.asyncio
    async def test_its_tokens_are_the_venues_in_the_venues_order(self, monkeypatch):
        _st, writer, *_ = await _run(monkeypatch, head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        meta = _market_rows(writer)[MONEYLINE_CID][0]["market_metadata"]
        assert meta["clob_token_ids"] == GAMMA_TOKENS

    @pytest.mark.asyncio
    async def test_its_legs_are_inserted_in_token_order_with_the_venues_exact_names(self, monkeypatch):
        _st, writer, *_ = await _run(monkeypatch, head=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        legs = _child_leg_inserts(writer, MONEYLINE_CID)
        assert [p["external_id"] for p in legs] == [f"{MONEYLINE_CID}_yes", f"{MONEYLINE_CID}_no"]
        # Exact equality, not containment: "Baltimore" alone would leave the leg
        # unsubscribed, and a swapped pair would invert the price.
        assert [p["name"] for p in legs] == GAMMA_OUTCOMES


class TestTheRotateCursor:
    @pytest.mark.asyncio
    async def test_a_head_row_that_is_also_a_rotate_row_does_not_jump_the_cursor(self, monkeypatch):
        # A linked game with no resolution date is in BOTH the head and the
        # rotate arm. It is read in the head's chunk; if it counted toward the
        # rotate cursor there, a 429 on the next chunk would leave the cursor at
        # its id (9000) and push r20..r25 a full lap away unread.
        rotate = [_Row(i, str(5_000_000 + i)) for i in range(1, 26)] + [_Row(9000, SPECIMEN)]
        gamma = _Gamma(by_id={SPECIMEN: SPECIMEN_RAW}, status_for_batch={2: 429})
        stats, _w, _s, _g, redis = await _run(
            monkeypatch, head=[_Row(9000, SPECIMEN)], rotate=rotate, gamma=gamma,
        )
        assert stats["rate_limited"]
        assert _batches(gamma)[0][0] == SPECIMEN
        # Chunk 1 = the specimen + r1..r19; chunk 2 (r20..r25) was refused.
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "19"


class TestTheHeadSelector:
    SQL = str(poly._SUNK_POLY_HEAD_SQL)

    def _predicates(self):
        raw = self.SQL.lower()
        return "\n".join(line.split("--")[0] for line in raw.splitlines())

    def test_it_is_the_sunk_predicate_verbatim(self):
        # Stale, open, parent-only, floored, refusals honoured — nothing re-chosen.
        assert poly._SUNK_POLY_WHERE in self.SQL

    def test_it_is_the_linked_window_verbatim(self):
        assert poly._LINKED_POLY_EVENT_WINDOW in self.SQL
        assert poly._LINKED_POLY_EVENT_WINDOW in str(poly._LINKED_POLY_BOOKS_SQL), (
            "one window string for both passes, or they drift on what 'imminent' means"
        )

    def test_it_does_not_require_zero_outcomes(self):
        # The specimen parent HOLDS its raw legs; #3613's anti-join would drop it.
        assert "not exists" not in self._predicates()
        assert "futures_outcomes" not in self._predicates()

    def test_it_is_ordered_by_kickoff_and_bounded(self):
        sql = self._predicates()
        assert re.search(r"order by e\.commence_time, s\.id\s+limit :max_rows", sql)

    @pytest.mark.asyncio
    async def test_it_is_sent_the_linked_window_and_its_own_ceiling(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch, redis=_Redis(refused={"123"}))
        # #8373's unlinked-game arm executes after this one; find the head by its SQL.
        sql, params = next(c for c in selector.calls if c[0] == self.SQL)
        assert params["horizon_days"] == poly.LINKED_POLY_BOOK_HORIZON_DAYS
        assert params["lookback_hours"] == poly.LINKED_POLY_BOOK_LOOKBACK_HOURS
        assert params["stale_hours"] == poly.SUNK_POLY_STALE_HOURS
        assert params["max_rows"] == poly._SUNK_POLY_HEAD_MAX
        assert params["refused"] == ["123"]

    def test_the_head_adds_five_gamma_calls_and_takes_none_from_the_imminent_arm(self):
        assert poly._SUNK_POLY_IMMINENT_MAX == 300, "unlinked fight cards (#6758) keep their reach"
        total = poly._SUNK_POLY_HEAD_MAX + poly._SUNK_POLY_IMMINENT_MAX + poly._SUNK_POLY_ROTATE_MAX
        assert -(-total // poly._LINKED_POLY_ID_BATCH) == 35

