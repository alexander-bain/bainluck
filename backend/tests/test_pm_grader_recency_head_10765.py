"""#10765 — a Polymarket market that settled today is graded today.

THE SPECIMEN (#10762, read on production 2026-10-08 17:25Z). Polymarket
63849227 "MLB Playoffs: Who Will Win Series? - Brewers vs. Padres" (Gamma event
1120859, one market, legs ``{cid}`` Brewers + ``{cid}_side1`` Padres) and
63849229 "... Series Spread" (Gamma event 1120857, four markets) were stamped
``status='resolved'`` at 13:12:50Z by the ingest, which writes 0/1 prices and no
grade. Brewers and Brewers (-1.5) sat at 1.000 with ``is_winner`` NULL, and the
series card printed "Lost" one card below Kalshi's "Milwaukee Won".

Phase 3 grades both shapes correctly; it simply never reached them, because it
walks ~353k eligible rows ascending by id and these ids are the frontier. The
recency head selects what settled in the last 72h first.

These tests EXECUTE the real ``_backfill_polymarket_winners_from_api`` against a
recording session and the venue's own wire shape (``outcomePrices`` is a JSON
STRING on Gamma), the same way ``test_polymarket_champion_leg_minted_6110`` and
``test_gamma_cursor_after_work_p086a`` drive it. The fake SELECT tells the head
from the cursor by the task's OWN binds (``head_hours`` vs ``last_id``), so the
selection under test is the task's and not the double's.
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.services.polymarket_api as poly_api_mod
import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state

OFFSET_KEY = "bainluck:pm_winner_backfill_offset"

# --- the specimen, by its production ids -------------------------------------
SERIES_MARKET = 63849227
SERIES_EVENT = "1120859"
SERIES_CID = "0x42367ed0a72e904f17435fe25b8fa75fb16557cafd74e73f93bd3faa74663bb4"

SPREAD_MARKET = 63849229
SPREAD_EVENT = "1120857"
SPREAD_LEGS = {
    # cid -> (name, venue yes-price at settlement)
    "0x19deeb23f8967551bf88a945e21564238426275f1f0e616b8bab8044ce84b133": ("Brewers (-1.5)", 1.0),
    "0xc50e1703844e91f9502a16f1116a26bdd4f2d7bea2989175efffba506ab75aca": ("Padres (-1.5)", 0.0),
    "0xd45ff6813c886b2c1bf3d6ef00ff393bbb29acabe1c0cdde914ddf1fbc6772b7": ("Brewers (-2.5)", 0.0),
    "0xe8e39ed4a80f806180b93a4aab6bac0efe218a559c433c35958766a9a052686e": ("Padres (-2.5)", 0.0),
}
SPREAD_WINNER_CID = "0x19deeb23f8967551bf88a945e21564238426275f1f0e616b8bab8044ce84b133"


def _gamma_market(cid, yes_price, question):
    return {
        "conditionId": cid,
        "question": question,
        "outcomePrices": json.dumps([str(yes_price), str(1 - yes_price)]),
        "closed": True,
    }


def _series_event():
    return {
        "id": SERIES_EVENT,
        "closed": True,
        "markets": [_gamma_market(SERIES_CID, 1, "Brewers vs. Padres series winner")],
    }


def _spread_event():
    return {
        "id": SPREAD_EVENT,
        "closed": True,
        "markets": [
            _gamma_market(cid, p, name) for cid, (name, p) in SPREAD_LEGS.items()
        ],
    }


class _Row:
    def __init__(self, id, external_id, group_type, poly_event_id):
        self.id = id
        self.external_id = external_id
        self.group_type = group_type
        self.poly_event_id = poly_event_id


SERIES_ROW = _Row(SERIES_MARKET, SERIES_EVENT, "polymarket_single", SERIES_EVENT)
SPREAD_ROW = _Row(SPREAD_MARKET, SPREAD_EVENT, "polymarket_event", SPREAD_EVENT)

#: The legs each market really stores: (market_id, external_id).
STORED = {
    (SERIES_MARKET, SERIES_CID),
    (SERIES_MARKET, f"{SERIES_CID}_side1"),
    *((SPREAD_MARKET, cid) for cid in SPREAD_LEGS),
}


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.deletes = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        self.deletes.append(key)
        return 1 if self.store.pop(key, None) is not None else 0

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


class _Rig:
    """The database and the venue, reduced to what this rail can observe."""

    def __init__(self, *, head=(), cursor=(), events=None, head_raises=None,
                 extra_stored=()):
        self.head = list(head)
        self.cursor = list(cursor)
        self.events = events if events is not None else {
            SERIES_EVENT: _series_event(),
            SPREAD_EVENT: _spread_event(),
        }
        self.head_raises = head_raises
        self.stored = set(STORED) | set(extra_stored)
        self.head_selects = []
        self.cursor_selects = []
        self.event_calls = []
        # (market_id, external_id) -> is_winner, last write wins
        self.grades = {}


def _install(monkeypatch, rig, rc=None):
    rc = rc or _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)

    async def _execute(stmt, params=None):
        if type(stmt).__name__ == "Update":
            bound = stmt.compile().params
            key = (bound.get("market_id_1"), bound.get("external_id_1"))
            if key in rig.stored:
                rig.grades[key] = bound.get("is_winner")
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)

        sql = str(getattr(stmt, "text", stmt))
        p = params or {}
        if "head_hours" in p:
            rig.head_selects.append((sql, dict(p)))
            if rig.head_raises is not None:
                raise rig.head_raises
            return _Result(rig.head[: p["head_limit"]])
        if "FROM futures_markets fm" in sql:
            rig.cursor_selects.append(dict(p))
            picked = [r for r in rig.cursor if r.id > (p.get("last_id") or 0)]
            if "target_ids" in p:
                picked = [r for r in picked if r.id in set(p["target_ids"])]
            return _Result(picked[: (p.get("limit") or len(picked))])
        if "UPDATE futures_outcomes" in sql:
            key = (p.get("mid"), p.get("cid"))
            return MagicMock(rowcount=1 if key in rig.stored else 0)
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
            return None

        async def get_event_by_id(self, eid):
            rig.event_calls.append(str(eid))
            return rig.events.get(str(eid))

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
    return rc


# ---------------------------------------------------------------------------
# The specimen, executed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheBrewersSeriesIsGraded:
    async def test_the_series_winner_and_its_companion_are_graded(self, monkeypatch):
        rig = _Rig(head=[SERIES_ROW, SPREAD_ROW])
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=100, recency_head=True
        )

        assert rig.grades[(SERIES_MARKET, SERIES_CID)] is True, rig.grades
        # #7505's companion: Padres is the other half of the same answer.
        assert rig.grades[(SERIES_MARKET, f"{SERIES_CID}_side1")] is False
        assert stats["head_selected"] == 2, stats

    async def test_the_spread_winner_is_graded_and_its_losers_stay_losers(
        self, monkeypatch
    ):
        rig = _Rig(head=[SPREAD_ROW])
        _install(monkeypatch, rig)

        await bw._backfill_polymarket_winners_from_api(limit=100, recency_head=True)

        assert rig.grades[(SPREAD_MARKET, SPREAD_WINNER_CID)] is True, rig.grades
        losers = [cid for cid in SPREAD_LEGS if cid != SPREAD_WINNER_CID]
        assert all(rig.grades[(SPREAD_MARKET, cid)] is False for cid in losers)

    async def test_the_grade_comes_from_the_venue_not_from_our_price(
        self, monkeypatch
    ):
        # The head SELECTS on our stored terminal price; the verdict must still
        # be Gamma's. A venue that says the Padres won is believed over a stored
        # Brewers 1.000.
        flipped = {
            "id": SERIES_EVENT,
            "closed": True,
            "markets": [_gamma_market(SERIES_CID, 0, "Brewers vs. Padres")],
        }
        rig = _Rig(head=[SERIES_ROW], events={SERIES_EVENT: flipped})
        _install(monkeypatch, rig)

        await bw._backfill_polymarket_winners_from_api(limit=100, recency_head=True)

        assert rig.grades[(SERIES_MARKET, SERIES_CID)] is False
        assert rig.grades[(SERIES_MARKET, f"{SERIES_CID}_side1")] is True

    async def test_an_undecided_venue_price_grades_nothing(self, monkeypatch):
        open_book = {
            "id": SERIES_EVENT,
            "closed": True,
            "markets": [_gamma_market(SERIES_CID, 0.6, "Brewers vs. Padres")],
        }
        rig = _Rig(head=[SERIES_ROW], events={SERIES_EVENT: open_book})
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=100, recency_head=True
        )

        assert rig.grades == {}
        assert stats["not_settled"] == 1, stats


# ---------------------------------------------------------------------------
# The head never moves, holds or wraps the backlog cursor
# ---------------------------------------------------------------------------


def _backlog_event(eid):
    return {"id": eid, "closed": True, "markets": []}


@pytest.mark.asyncio
class TestTheCursorIsTheCursorsAlone:
    async def test_head_ids_never_become_the_cursor(self, monkeypatch):
        backlog = [_Row(10, "910", "negrisk", "910"), _Row(11, "911", "negrisk", "911")]
        events = {
            SERIES_EVENT: _series_event(),
            "910": _backlog_event("910"),
            "911": _backlog_event("911"),
        }
        rig = _Rig(head=[SERIES_ROW], cursor=backlog, events=events)
        rc = _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=2, recency_head=True
        )

        # A full clean page of two advances to the page's own max — never to
        # the head's frontier id, which would declare 353k rows swept.
        assert rc.store.get(OFFSET_KEY) == "11", rc.store
        assert stats["selected"] == 2
        assert stats["completed"] == 2
        assert stats["head_completed"] == 1
        assert rig.grades[(SERIES_MARKET, SERIES_CID)] is True

    async def test_a_head_row_also_on_the_cursor_page_is_counted_once_as_cursor(
        self, monkeypatch
    ):
        rig = _Rig(head=[SERIES_ROW], cursor=[SERIES_ROW])
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert stats["head_selected"] == 0
        assert stats["selected"] == 1
        assert rig.event_calls.count(SERIES_EVENT) == 1

    async def test_a_wrapped_backlog_still_processes_the_head(self, monkeypatch):
        rig = _Rig(head=[SERIES_ROW], cursor=[])
        rc = _install(monkeypatch, rig, _FakeRedis({OFFSET_KEY: "999"}))

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        # The wrap is exactly what it was before the head existed ...
        assert OFFSET_KEY in rc.deletes
        assert OFFSET_KEY not in rc.store
        # ... and the fresh settlement is graded in the same run.
        assert rig.grades[(SERIES_MARKET, SERIES_CID)] is True
        assert stats["cursor_op"] == "noop", stats


# ---------------------------------------------------------------------------
# Who takes the head, and who does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOnlyTheScheduledSweepTakesTheHead:
    async def test_the_default_call_never_issues_the_head_select(self, monkeypatch):
        # Control: every existing caller that does not opt in sees exactly the
        # old selection — and the specimen stays ungraded, which is the defect.
        rig = _Rig(head=[SERIES_ROW], cursor=[])
        _install(monkeypatch, rig)

        await bw._backfill_polymarket_winners_from_api(limit=5)

        assert rig.head_selects == []
        assert rig.grades == {}

    async def test_a_targeted_run_never_takes_the_head(self, monkeypatch):
        rig = _Rig(head=[SPREAD_ROW], cursor=[SERIES_ROW])
        _install(monkeypatch, rig)

        await bw._backfill_polymarket_winners_from_api(
            limit=5, market_ids=[SERIES_MARKET], recency_head=True
        )

        assert rig.head_selects == []
        assert SPREAD_EVENT not in rig.event_calls

    async def test_the_head_select_binds_its_own_bounds(self, monkeypatch):
        rig = _Rig(head=[SERIES_ROW])
        _install(monkeypatch, rig)

        await bw._backfill_polymarket_winners_from_api(limit=5, recency_head=True)

        (_sql, binds), = rig.head_selects
        assert binds == {
            "head_hours": bw._GAMMA_HEAD_WINDOW_HOURS,
            "head_terminal": bw._GAMMA_HEAD_TERMINAL_PRICE,
            "head_limit": bw._GAMMA_HEAD_LIMIT,
        }

    async def test_a_head_that_cannot_be_read_never_costs_the_backlog_its_page(
        self, monkeypatch
    ):
        backlog = [_Row(10, "910", "negrisk", "910")]
        rig = _Rig(
            head=[SERIES_ROW], cursor=backlog,
            events={"910": _backlog_event("910")},
            head_raises=RuntimeError("canceling statement due to statement timeout"),
        )
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert any(e.startswith("head:") for e in stats["errors"]), stats["errors"]
        assert "910" in rig.event_calls
        assert stats["completed"] == 1


# ---------------------------------------------------------------------------
# The head's time share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheHeadYieldsToTheBacklog:
    async def test_a_spent_head_share_skips_head_events_but_not_the_cursors(
        self, monkeypatch
    ):
        backlog = [_Row(10, "910", "negrisk", "910")]
        rig = _Rig(
            head=[SERIES_ROW, SPREAD_ROW], cursor=backlog,
            events={SERIES_EVENT: _series_event(), SPREAD_EVENT: _spread_event(),
                    "910": _backlog_event("910")},
        )
        _install(monkeypatch, rig)
        # A share that is already over when Phase B starts.
        monkeypatch.setattr(bw, "_gamma_head_stop_at", lambda t0, stop_at: 0.0)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert stats["head_events_skipped"] == 2, stats
        assert SERIES_EVENT not in rig.event_calls
        assert SPREAD_EVENT not in rig.event_calls
        assert "910" in rig.event_calls
        assert stats["completed"] == 1


    async def test_a_head_that_runs_reports_how_far_into_its_share_it_got(
        self, monkeypatch
    ):
        rig = _Rig(head=[SERIES_ROW, SPREAD_ROW])
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert stats["head_events_skipped"] == 0, stats
        assert isinstance(stats["head_reached_s"], float), stats
        assert 0.0 <= stats["head_reached_s"] < bw._GAMMA_HEAD_BUDGET_S

    async def test_no_head_reports_no_reach(self, monkeypatch):
        rig = _Rig(cursor=[_Row(10, "910", "negrisk", "910")],
                   events={"910": _backlog_event("910")})
        _install(monkeypatch, rig)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert stats["head_reached_s"] is None, stats

    async def test_when_the_clock_binds_the_oldest_head_event_is_the_one_skipped(
        self, monkeypatch
    ):
        # The select is newest-first, so SERIES (first) is the newer event.
        rig = _Rig(head=[SERIES_ROW, SPREAD_ROW])
        _install(monkeypatch, rig)
        base = poly_api_mod.PolymarketAPIService

        class _SlowNewest(base):
            async def get_event_by_id(self, eid):
                if str(eid) == SERIES_EVENT:
                    await asyncio.sleep(0.2)
                return await super().get_event_by_id(eid)

        monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _SlowNewest)
        # A share of 50ms: spent by the first event's 200ms Gamma call.
        monkeypatch.setattr(bw, "_gamma_head_stop_at", lambda t0, stop_at: t0 + 0.05)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=5, recency_head=True
        )

        assert rig.event_calls == [SERIES_EVENT], rig.event_calls
        assert stats["head_events_skipped"] == 1, stats
        assert stats["head_reached_s"] is not None


class TestTheClockBindsTheHeadNotTheSelect:
    # Measured on production 2026-10-09 (v5609's first head run): 500 rows were
    # 130 events (~3.8 rows/event) and Gamma answered an event in ~0.3s. At
    # 500 the select ran dry with the share a third spent and nothing skipped.
    ROWS_PER_EVENT = 3.8
    GAMMA_EVENT_S = 0.3

    def test_the_select_can_fill_the_share_at_the_measured_density(self):
        events_the_share_fits = bw._GAMMA_HEAD_BUDGET_S / self.GAMMA_EVENT_S
        assert bw._GAMMA_HEAD_LIMIT >= events_the_share_fits * self.ROWS_PER_EVENT


class TestPureHelpers:
    def test_the_head_takes_at_most_half_of_what_is_left(self):
        assert bw._gamma_head_stop_at(100.0, 160.0) == 130.0

    def test_the_head_is_capped_by_its_own_budget_on_a_long_wall(self):
        assert bw._gamma_head_stop_at(0.0, 10_000.0) == bw._GAMMA_HEAD_BUDGET_S

    def test_a_wall_already_passed_gives_the_head_nothing(self):
        assert bw._gamma_head_stop_at(50.0, 40.0) == 50.0

    def test_merge_puts_head_first_and_keeps_a_shared_row_as_cursor(self):
        a, b, c = _Row(1, "x", None, "e1"), _Row(2, "y", None, "e2"), _Row(3, "z", None, "e3")
        rows, head_only = bw._merge_head_into_page([c, a], [a, b])
        assert [r.id for r in rows] == [3, 1, 2]
        assert head_only == {3}


# ---------------------------------------------------------------------------
# The head's population is a subset of the cursor's, by construction
# ---------------------------------------------------------------------------


class TestTheHeadSelectsOnlyWhatTheCursorWould:
    SQL = " ".join(bw._GAMMA_HEAD_SQL.split())

    def test_resolved_polymarket_only(self):
        assert "fm.source = 'polymarket'" in self.SQL
        assert "fm.status = 'resolved'" in self.SQL

    def test_an_ungraded_leg_which_the_cursors_first_arm_admits(self):
        # The cursor admits `COALESCE(resolution_source,'') NOT IN
        # ('api_settlement','clean_resolution')`; NULL satisfies it.
        assert "fo.resolution_source IS NULL" in self.SQL

    def test_never_a_market_that_already_crowns_someone(self):
        assert "NOT EXISTS ( SELECT 1 FROM futures_outcomes fw WHERE fw.market_id = fm.id AND fw.is_winner )" in self.SQL

    def test_inside_the_window_newest_first(self):
        assert "fm.settled_at > NOW() - make_interval(hours => :head_hours)" in self.SQL
        assert "ORDER BY fm.settled_at DESC, fm.id DESC" in self.SQL

    def test_event_keyed_so_the_head_share_governs_every_head_row(self):
        assert "fm.market_metadata->>'polymarket_event_id' IS NOT NULL" in self.SQL

    def test_exists_not_a_join(self):
        # A JOIN + GROUP BY planned a seq scan over all outcomes on production.
        assert "JOIN futures_outcomes" not in self.SQL
        assert "GROUP BY" not in self.SQL


# ---------------------------------------------------------------------------
# The scheduled callers opt in; nothing else does
# ---------------------------------------------------------------------------


def _calls(path, name):
    tree = ast.parse(Path(path).read_text())
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", None)) == name
    ]


def _kw(call, name):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


class TestTheScheduledCallersTakeTheHead:
    BW = Path(bw.__file__)
    TASKS = BW.parent / "__init__.py"

    def test_both_backfill_winners_pipelines_opt_in(self):
        calls = _calls(self.BW, "_backfill_polymarket_winners_from_api")
        assert len(calls) == 2, len(calls)
        for c in calls:
            v = _kw(c, "recency_head")
            assert isinstance(v, ast.Constant) and v.value is True, ast.dump(c)

    def test_the_standalone_task_opts_in_unless_targeted(self):
        (call,) = _calls(self.TASKS, "_backfill_polymarket_winners_from_api")
        v = _kw(call, "recency_head")
        assert v is not None
        assert ast.unparse(v) == "not market_ids"
