"""#12091 (Decide 32-A): movement orders the concept cards in Discover's opening.

Pinned here:

* the theme bundles trade SEATS by movement — moved first (biggest first), the
  unmoved after in their current order — and every non-bundle card keeps its
  exact seat, so no single card is promoted into the opening;
* an unmoved bundle in the opening yields to a moved one from lower down, and
  stays on the page in the seat that one left;
* a move under the card floor, or no reading at all, is "not moved";
* nothing changes → the very same list (the capture-abandon check reads `is`);
* the reading: cached answer while it serves (no SQL), one bounded read
  otherwise, a failed read falls back to the stale answer and then to no
  order change; switch off → nothing is read;
* the SQL compares one venue to itself at the price in force 24 h ago;
* get_feed runs the stage on the Discover deck after the display chain and
  before collections, round-ups and the opening seating.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from datetime import datetime, timezone


import app.utils.concept_movement as cm

NOW = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)


def bundle(title: str, *legs: int) -> dict:
    members = [
        {"type": "futures", "data": {"id": 1000 + leg, "top_outcomes": [{"id": leg}]}}
        for leg in legs
    ]
    return {"type": "bundle", "data": {"kind": "theme", "title": title, "items": members}}


def card(name: str, kind: str = "futures") -> dict:
    return {"type": kind, "data": {"id": name}}


def titles(items):
    return [(i["data"].get("title") or i["data"]["id"]) for i in items]


class TestOrder:
    def test_bundles_trade_seats_by_movement_and_other_cards_keep_theirs(self):
        deck = [
            bundle("AI", 1, 2),
            bundle("Awards", 3),
            card("mlb"),
            bundle("Middle East", 4),
            bundle("Fed", 5),
            card("oilers", "event"),
        ]
        moves = {1: 0.01, 2: -0.005, 3: 0.03, 4: -0.12, 5: 0.0}
        out = cm.order_concepts_by_movement(deck, moves)
        assert titles(out) == ["Middle East", "Awards", "mlb", "AI", "Fed", "oilers"]
        assert out[2] is deck[2] and out[5] is deck[5]
        assert len(out) == len(deck) and {id(i) for i in out} == {id(i) for i in deck}

    def test_an_unmoved_opening_bundle_yields_to_a_moved_one_from_lower_down(self):
        deck = [bundle("AI", 1), card("a"), bundle("IPOs", 2)] + [card(f"c{i}") for i in range(30)]
        deck.append(bundle("Tennis", 3))
        out = cm.order_concepts_by_movement(deck, {1: 0.0, 2: 0.004, 3: 0.25})
        assert titles(out)[0] == "Tennis"
        assert titles(out)[2] == "AI"
        assert titles(out)[-1] == "IPOs"  # still on the page, lower

    def test_under_the_floor_or_no_reading_is_not_moved(self):
        deck = [bundle("A", 1), bundle("B", 2), bundle("C", 3)]
        moves = {1: 0.019, 3: 0.02}
        assert titles(cm.order_concepts_by_movement(deck, moves)) == ["C", "A", "B"]

    def test_nothing_moves_returns_the_same_list(self):
        deck = [bundle("A", 1), card("x"), bundle("B", 2)]
        assert cm.order_concepts_by_movement(deck, {}) is deck
        assert cm.order_concepts_by_movement(deck, {1: 0.3, 2: 0.1}) is deck
        assert cm.order_concepts_by_movement([bundle("A", 1)], {1: 0.5})[0]["data"]["title"] == "A"

    def test_ties_keep_the_current_order(self):
        deck = [bundle("A", 1), bundle("B", 2), bundle("C", 3)]
        assert titles(cm.order_concepts_by_movement(deck, {2: 0.05, 3: -0.05})) == ["B", "C", "A"]

    def test_only_theme_bundles_and_futures_legs_count(self):
        comparison = {"type": "bundle", "data": {"kind": "comparison", "items": []}}
        assert not cm.is_concept_bundle(comparison) and cm.is_concept_bundle(bundle("A", 1))
        mixed = bundle("A", 1)
        mixed["data"]["items"].append({"type": "event", "data": {"top_outcomes": [{"id": 9}]}})
        mixed["data"]["items"].append({"type": "futures", "data": {"top_outcomes": [{"id": True}, {"id": "7"}]}})
        assert cm.concept_leg_ids(mixed) == [1]
        assert cm.wanted_leg_ids([mixed, bundle("B", 1, 4), card("x")]) == [1, 4]


class FakeRedis:
    def __init__(self, raw=None):
        self.raw, self.sets = raw, []

    async def get(self, key):
        return self.raw

    async def set(self, key, value, ex=None):
        self.sets.append((key, json.loads(value), ex))


class FakeDB:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.calls, self.rolled_back = list(rows), fail, 0, False

    async def execute(self, stmt, params=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("statement timeout")
        self.params = params

        class R:
            def __init__(s, rows):
                s._rows = rows

            def all(s):
                return s._rows

        return R(self.rows)

    async def rollback(self):
        self.rolled_back = True


def cache_blob(at, moves, legs):
    return json.dumps({"at": at, "moves": {str(k): v for k, v in moves.items()}, "legs": legs})


class TestReading:
    def test_a_fresh_covering_cache_serves_without_sql(self):
        redis = FakeRedis(cache_blob(NOW.timestamp() - 60, {1: 0.1}, [1, 2]))
        db = FakeDB()
        out = asyncio.run(cm.load_leg_moves(db, [1, 2], now=NOW, redis=redis))
        assert out == {1: 0.1} and db.calls == 0 and redis.sets == []

    def test_stale_or_thin_cache_reads_once_and_caches(self):
        for raw in (
            cache_blob(NOW.timestamp() - cm.CACHE_TTL_S - 1, {1: 0.1}, [1, 2]),
            cache_blob(NOW.timestamp() - 60, {1: 0.1}, [1]),  # covers 1 of 2
            None,
        ):
            redis, db = FakeRedis(raw), FakeDB(rows=[(1, 0.2), (2, None)])
            out = asyncio.run(cm.load_leg_moves(db, [1, 2], now=NOW, redis=redis))
            assert out == {1: 0.2} and db.calls == 1
            assert db.params == {"ids": [1, 2], "now": NOW}
            key, doc, ex = redis.sets[0]
            assert key == cm.CACHE_KEY and doc["legs"] == [1, 2] and ex == cm.CACHE_KEEP_S

    def test_a_failed_read_keeps_the_stale_answer_then_nothing(self):
        stale = cache_blob(NOW.timestamp() - 1200, {1: 0.3}, [1])
        db = FakeDB(fail=True)
        assert asyncio.run(cm.load_leg_moves(db, [1], now=NOW, redis=FakeRedis(stale))) == {1: 0.3}
        assert db.rolled_back
        too_old = cache_blob(NOW.timestamp() - cm.CACHE_KEEP_S - 1, {1: 0.3}, [1])
        assert asyncio.run(cm.load_leg_moves(FakeDB(fail=True), [1], now=NOW, redis=FakeRedis(too_old))) == {}
        assert asyncio.run(cm.load_leg_moves(FakeDB(fail=True), [1], now=NOW, redis=FakeRedis("junk"))) == {}

    def test_switch_off_reads_nothing(self, monkeypatch):
        monkeypatch.delenv(cm.CONCEPT_MOVEMENT_ENV, raising=False)

        class Boom:
            async def execute(self, *a, **k):
                raise AssertionError("read while off")

        deck = [bundle("A", 1), bundle("B", 2)]
        assert asyncio.run(cm.apply_concept_movement(Boom(), deck, now=NOW, redis=FakeRedis())) is deck

    def test_switch_on_reorders(self, monkeypatch):
        monkeypatch.setenv(cm.CONCEPT_MOVEMENT_ENV, "true")
        deck = [bundle("A", 1), card("x"), bundle("B", 2)]
        out = asyncio.run(
            cm.apply_concept_movement(FakeDB(rows=[(1, 0.0), (2, 0.07)]), deck, now=NOW, redis=FakeRedis())
        )
        assert titles(out) == ["B", "x", "A"]

    def test_the_sql_reads_one_venue_against_itself_24h_ago(self):
        sql = " ".join(cm.MOVE_SQL.split())
        assert "s.bookmaker = cur.bookmaker" in sql
        assert "s.captured_at <= CAST(:now AS timestamptz) - INTERVAL '24 hours'" in sql
        assert sql.count("ORDER BY s.captured_at DESC LIMIT 1") == 2
        assert "WHERE o.id IN :ids" in sql


class TestWiring:
    def test_discover_deck_predicate(self):
        from app.routes.feed import _feed_is_discover_deck

        base = dict(mode=None, sport=None, category=None, tags=None, my_teams_only=False,
                    include_events=True, include_futures=True)
        assert _feed_is_discover_deck(**base)
        assert _feed_is_discover_deck(**{**base, "mode": "Discover"})
        for change in ({"mode": "sports"}, {"sport": "nfl"}, {"category": "tech"}, {"tags": "x"},
                       {"my_teams_only": True}, {"include_futures": False}):
            assert not _feed_is_discover_deck(**{**base, **change})

    def test_the_stage_sits_after_the_chain_and_before_collections_and_seating(self):
        from app.routes import feed

        src = inspect.getsource(feed.get_feed)
        chain = src.index("_capture.record_chain_exit(feed_items, _chain_meta)")
        stage = src.index("feed_items = await apply_concept_movement(")
        collections = src.index("feed_items = await add_feed_collections(", stage)
        seating = src.index("_opening = compose_opening_edition(", collections)
        assert chain < stage < collections < seating
        assert src.count("await apply_concept_movement(") == 1
        gate = src.rindex("if concept_movement_enabled() and _feed_is_discover_deck(", 0, stage)
        assert chain < gate
        ast.parse(inspect.getsource(feed))  # the module still parses
