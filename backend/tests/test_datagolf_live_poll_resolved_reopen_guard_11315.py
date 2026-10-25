"""#11315 — a finished golf board stays finished; the live poll's recovery
branch no longer reopens it.

WHAT WAS WRONG. `_poll_datagolf_live` reads only OPEN datagolf markets for a
tour. When it finds none while the in-play endpoint still answers, it enters
schedule recovery: the first schedule row whose status is set and not
"completed" becomes `current_event`, and every existing market for that event
was assigned `status = "open"` with no look at the stored status. DataGolf's
status string lags the result (the reason #1076 and #144 exist), so after a
tournament ended — its markets resolved — a lagging status plus a still-
answering in-play board put the finished board back in the open set. The live
writer then priced it again (new current price, snapshot or dedup stretch,
fresh stamps, newcomer legs, the withdrawal null-out, a re-rank), and once the
live phase ended the hourly poll — whose own #11315 guard reads `resolved` —
saw an OPEN board and wrote the pre-tournament field over the final journey.

The fix refuses the reopen for a TRULY resolved row: `resolved` with a null or
past `resolution_date`. A future-dated resolved row is the #1076 class (resolved
by mistake before its end date) and keeps the reopen; a `closed` row reopens as
before; a missing row is still created.

This is PREVENTION ONLY. Nothing here cleans stored history, grades a market,
decides finality, or claims which execution produced any stored reset.

THE RIG. The real `_poll_datagolf_live`, the real ORM models and payload
dataclasses, and a session that answers each SELECT by its OWN bound
parameters — including the `status` filter on the per-tour scan, so a row the
recovery did not reopen is genuinely invisible to the writer below it, exactly
as in PostgreSQL. Identity values (Baycurrent Classic, event 527) are taken
from the retained #11315 fixture; every price and stamp is constructed.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.sql.dml import Update

import app.services.datagolf_api as datagolf_api
import app.tasks.base as task_base
import app.tasks.datagolf as datagolf
import app.tasks.redis_state as redis_state
from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

DataGolfPlayer = datagolf_api.DataGolfPlayer
DataGolfTournament = datagolf_api.DataGolfTournament

PGA_EVENT_ID = "527"
PGA_EVENT_NAME = "Baycurrent Classic"
EURO_EVENT_ID = "2026150"
EURO_EVENT_NAME = "Open de France"

WINNER_ID = 18417
RUNNER_UP_ID = 22085
VANISHED_ID = 77777
NEWCOMER_ID = 99999
EURO_PLAYER_ID = 12345

OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)
OLD_CHANGE = 0.42
SETTLED_AT = datetime(2026, 1, 3, tzinfo=timezone.utc)
SNAP_VALID_UNTIL = datetime(2026, 1, 2, tzinfo=timezone.utc)
SNAP_READINGS = 7

#: The graded values on the finished board, per market type.
WINNER_GRADED = 1.0
LOSER_GRADED = 0.0
#: The prices on the in-play board the provider is still answering with.
LAGGING_WIN = 0.083
LAGGING_OTHER = 0.61


def _midnight(dt: datetime) -> datetime:
    """Offset FIRST, then truncate (gotcha #44)."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _past_resolution() -> datetime:
    return _midnight(datetime.now(timezone.utc) - timedelta(days=1))


def _future_resolution() -> datetime:
    return _midnight(datetime.now(timezone.utc) + timedelta(days=2))


def _started() -> datetime:
    return _midnight(datetime.now(timezone.utc) - timedelta(days=4))


# --------------------------------------------------------------- the rig --


class _FakeResult:
    def __init__(self, rows=(), rowcount: int = 0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        assert len(self._rows) <= 1, "scalar_one_or_none on several rows"
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


def _bound(stmt) -> dict:
    return dict(stmt.compile().params)


def _param(params: dict, column: str):
    """The value bound against `column` (SQLAlchemy names it `<column>_N`)."""
    hits = [v for k, v in params.items() if k.rsplit("_", 1)[0] == column]
    assert len(hits) <= 1, f"{column} bound twice: {params}"
    return hits[0] if hits else None


class _LiveSession:
    """Answers `_poll_datagolf_live`'s statements by their bound parameters.

    The per-tour market scan honours its `status` filter, and the recovery's
    lookup by `external_id` does not filter status — both as the real queries
    are written — so whether a row reaches the writer is decided by the row's
    stored status, not by the fake.
    """

    def __init__(self, markets, outcomes, snapshots):
        #: ext_id -> FuturesMarket
        self.markets = markets
        #: (market_id, ext_id) -> FuturesOutcome
        self.outcomes = outcomes
        #: outcome_id -> FuturesOddsSnapshot (the latest the dedup reads)
        self.snapshots = snapshots
        self.added: list[object] = []
        self.reranked: list[Update] = []
        self.market_updates: list[Update] = []
        self.selects = 0
        self._next_id = 9000

    def add(self, obj) -> None:
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1
        if isinstance(obj, FuturesMarket):
            self.markets[obj.external_id] = obj
        elif isinstance(obj, FuturesOutcome):
            self.outcomes[(obj.market_id, obj.external_id)] = obj
        elif isinstance(obj, FuturesOddsSnapshot):
            self.snapshots[obj.outcome_id] = obj

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:  # pragma: no cover - the ctx commits
        return None

    async def rollback(self) -> None:  # pragma: no cover - defensive
        return None

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            if stmt.table.name == "futures_outcomes":
                self.reranked.append(stmt)
                return _FakeResult(rowcount=0)
            if stmt.table.name == "futures_markets":
                # Only the no-in-play completed-event resolve issues this, and
                # no case here takes that branch for a tour it asserts on.
                self.market_updates.append(stmt)
                return _FakeResult(rowcount=0)
            raise AssertionError(f"unexpected update: {stmt.table.name}")

        self.selects += 1
        entity = stmt.column_descriptions[0]["entity"]
        params = _bound(stmt)

        if entity is FuturesMarket:
            assert _param(params, "source") == "datagolf"
            ext = _param(params, "external_id")
            status = _param(params, "status")
            if ext.endswith("%"):
                head = ext[:-1]
                assert status is not None, "the per-tour scan lost its status filter"
                return _FakeResult([
                    m for e, m in self.markets.items()
                    if e.startswith(head) and m.status == status
                ])
            assert status is None
            market = self.markets.get(ext)
            return _FakeResult([market] if market else [])

        if entity is FuturesOutcome:
            market_id = _param(params, "market_id")
            ext = _param(params, "external_id")
            if "current_probability IS NOT NULL" in str(stmt):
                fresh = set(ext)
                return _FakeResult([
                    o for (mid, e), o in self.outcomes.items()
                    if mid == market_id
                    and o.current_probability is not None
                    and e not in fresh
                ])
            outcome = self.outcomes.get((market_id, ext))
            return _FakeResult([outcome] if outcome else [])

        if entity is FuturesOddsSnapshot:
            assert _param(params, "bookmaker") == "datagolf_model"
            snap = self.snapshots.get(_param(params, "outcome_id"))
            return _FakeResult([snap] if snap else [])

        raise AssertionError(f"unexpected select: {entity}")  # pragma: no cover


class _LiveRedis:
    def __init__(self):
        self.present: dict[str, str] = {}

    def get(self, key):
        return self.present.get(key)

    def set(self, key, value, ex=None):
        self.present[key] = value

    def delete(self, key):
        self.present.pop(key, None)


class _LiveService:
    def __init__(self, boards, schedules):
        #: tour -> (players, event_name)
        self._boards = boards
        #: tour -> [DataGolfTournament]
        self._schedules = schedules
        self.schedule_reads: list[str] = []

    async def get_in_play_with_info(self, tour: str):
        players, name = self._boards.get(tour, ([], ""))
        return list(players), ({"event_name": name} if players else {})

    async def get_schedule(self, tour: str):
        self.schedule_reads.append(tour)
        return list(self._schedules.get(tour, []))

    async def close(self):
        return None


def _player(dg_id: int, name: str, win: float, other: float) -> DataGolfPlayer:
    return DataGolfPlayer(
        dg_id=dg_id,
        player_name=name,
        win=win,
        top_5=other,
        top_10=other,
        top_20=other,
        make_cut=other,
        current_round=4,
        position="T1",
    )


#: The board the provider is still answering with after the result.
LAGGING_BOARD = [
    _player(WINNER_ID, "Brennan", LAGGING_WIN, LAGGING_OTHER),
    _player(RUNNER_UP_ID, "Bridgeman", LAGGING_WIN, LAGGING_OTHER),
    _player(NEWCOMER_ID, "Newcomer", LAGGING_WIN, LAGGING_OTHER),
]

#: The provider still answering with the FINAL board (every win 0 or 1).
FINAL_BOARD = [
    _player(WINNER_ID, "Brennan", 1.0, 1.0),
    _player(RUNNER_UP_ID, "Bridgeman", 0.0, 1.0),
    _player(NEWCOMER_ID, "Newcomer", 0.0, 0.0),
]

BOARDS = {"lagging_board": LAGGING_BOARD, "final_board": FINAL_BOARD}


def _schedule_row(tour, event_id, name, status):
    return DataGolfTournament(
        event_id=event_id,
        event_name=name,
        course="Baycurrent",
        start_date=_started().strftime("%Y-%m-%d"),
        end_date=_past_resolution().strftime("%Y-%m-%d"),
        status=status,
        tour=tour,
    )


#: How the schedule still names the finished tournament current: a status set
#: and not "completed". Both are the provider's own strings.
LAGGING_STATUSES = ["in_progress", "upcoming"]


def _seed_event(
    markets, outcomes, snapshots, *, tour, event_id, event_name, status,
    resolution_date, first_id, graded=True,
):
    """Five markets for one event, each with three legs and one snapshot."""
    market_id = first_id
    for market_type, category in datagolf.MARKET_TYPES:
        ext = datagolf._external_id(tour, event_id, market_type)
        market = FuturesMarket(
            source="datagolf",
            external_id=ext,
            name=f"{event_name} - {datagolf._market_label(market_type)}",
            category=category,
            status=status,
        )
        market.id = market_id
        market.commence_time = _started()
        market.resolution_date = resolution_date
        market.settled_at = SETTLED_AT if status == "resolved" else None
        market.market_metadata = {
            "datagolf_event_id": event_id,
            "course": "Baycurrent",
            "tour": tour,
            "leaderboard": [{"dg_id": WINNER_ID, "position": "1"}],
            "leaderboard_updated_at": OLD.isoformat(),
            "round_history": [{"round": 3, "timestamp": OLD.isoformat(), "label": "R3"}],
        }
        markets[ext] = market
        for i, (dg_id, name, value) in enumerate([
            (WINNER_ID, "Brennan", WINNER_GRADED),
            (RUNNER_UP_ID, "Bridgeman", LOSER_GRADED),
            (VANISHED_ID, "Withdrawn", LOSER_GRADED),
        ]):
            outcome = FuturesOutcome(
                market_id=market_id,
                external_id=f"dg_{dg_id}",
                name=name,
                current_probability=value,
                opening_probability=0.05,
                is_winner=(value == WINNER_GRADED) if graded else None,
                resolution_source="datagolf_backfill" if graded else None,
            )
            outcome.id = market_id * 10 + i
            outcome.last_updated = OLD
            outcome.price_changed_at = OLD
            outcome.probability_change_24h = OLD_CHANGE
            outcomes[(market_id, outcome.external_id)] = outcome
            snapshots[outcome.id] = FuturesOddsSnapshot(
                outcome_id=outcome.id,
                bookmaker="datagolf_model",
                probability=value,
                captured_at=OLD,
                valid_until=SNAP_VALID_UNTIL,
                reading_count=SNAP_READINGS,
            )
        market_id += 1


def _world(*, pga_status, pga_resolution_date=None, with_euro=False, per_type=None):
    markets: dict = {}
    outcomes: dict = {}
    snapshots: dict = {}
    if pga_status is not None:
        _seed_event(
            markets, outcomes, snapshots, tour="pga", event_id=PGA_EVENT_ID,
            event_name=PGA_EVENT_NAME, status=pga_status,
            resolution_date=pga_resolution_date or _past_resolution(),
            first_id=40, graded=(pga_status == "resolved"),
        )
        for market_type, status in (per_type or {}).items():
            m = markets[datagolf._external_id("pga", PGA_EVENT_ID, market_type)]
            m.status = status
            m.settled_at = SETTLED_AT if status == "resolved" else None
    if with_euro:
        _seed_event(
            markets, outcomes, snapshots, tour="euro", event_id=EURO_EVENT_ID,
            event_name=EURO_EVENT_NAME, status="open",
            resolution_date=_future_resolution(), first_id=60, graded=False,
        )
    return markets, outcomes, snapshots


def _run(
    monkeypatch, world, *, board=LAGGING_BOARD, schedule_status="in_progress",
    schedule_name=PGA_EVENT_NAME, with_euro=False,
):
    markets, outcomes, snapshots = world
    session = _LiveSession(markets, outcomes, snapshots)
    redis = _LiveRedis()
    boards = {"pga": (board, PGA_EVENT_NAME)}
    schedules = {
        "pga": [_schedule_row("pga", PGA_EVENT_ID, schedule_name, schedule_status)]
    }
    if with_euro:
        boards["euro"] = (
            [_player(EURO_PLAYER_ID, "Euro", 0.31, 0.5)], EURO_EVENT_NAME,
        )
    service = _LiveService(boards, schedules)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)

    stats = asyncio.run(datagolf._poll_datagolf_live())
    return stats, session, redis, service


def _pga(markets):
    return [
        markets[datagolf._external_id("pga", PGA_EVENT_ID, t)]
        for t, _ in datagolf.MARKET_TYPES
    ]


def _frozen(world):
    """Deep copies of every stored field the refusal must leave untouched."""
    markets, outcomes, snapshots = world
    return (
        {
            e: (m.status, m.settled_at, m.name, copy.deepcopy(m.market_metadata),
                m.commence_time, m.resolution_date)
            for e, m in markets.items()
        },
        {
            k: (o.current_probability, o.opening_probability, o.is_winner,
                o.resolution_source, o.last_updated, o.price_changed_at,
                o.probability_change_24h)
            for k, o in outcomes.items()
        },
        {
            k: (s.probability, s.captured_at, s.valid_until, s.reading_count)
            for k, s in snapshots.items()
        },
    )


def _assert_untouched(world, before, session, *, tour_prefix="datagolf:pga:"):
    after = _frozen(world)
    for ext, fields in before[0].items():
        if ext.startswith(tour_prefix):
            assert after[0][ext] == fields, ext
    markets = world[0]
    ids = {m.id for e, m in markets.items() if e.startswith(tour_prefix)}
    for key, fields in before[1].items():
        if key[0] in ids:
            assert after[1][key] == fields, key
    for key, fields in before[2].items():
        if key // 10 in ids:
            assert after[2][key] == fields, key
    for obj in session.added:
        if isinstance(obj, FuturesOutcome):
            assert obj.market_id not in ids, "a leg was born on the finished board"
        if isinstance(obj, FuturesOddsSnapshot):
            assert obj.outcome_id // 10 not in ids, "a snapshot drawn on the finished board"
        assert not (
            isinstance(obj, FuturesMarket) and obj.external_id.startswith(tour_prefix)
        ), "a second market was created beside the finished one"
    for stmt in session.reranked:
        reranked_ids = set(_param(_bound(stmt), "market_id"))
        assert not (reranked_ids & ids), "the settled board was re-ranked"


# -------------------------------------------------------- the refusal arm --


class TestAFinishedBoardIsNotReopenedByTheLivePoll:
    @pytest.mark.parametrize("board", list(BOARDS), ids=list(BOARDS))
    @pytest.mark.parametrize("schedule_status", LAGGING_STATUSES)
    def test_the_resolved_board_is_left_exactly_as_stored(
        self, monkeypatch, board, schedule_status
    ):
        world = _world(pga_status="resolved")
        before = _frozen(world)

        stats, session, redis, service = _run(
            monkeypatch, world, board=BOARDS[board], schedule_status=schedule_status
        )

        # The recovery ran — the specimen reached the guarded line …
        assert "pga" in service.schedule_reads
        # … and every stored field on the finished board is as it was.
        _assert_untouched(world, before, session)
        assert all(m.status == "resolved" for m in _pga(world[0]))
        assert stats["resolved_market_reopen_refused"] == len(datagolf.MARKET_TYPES)
        assert stats["snapshots_written"] == 0
        assert stats.get("markets_created") == 0
        assert session.reranked == []
        # Writing nothing, the beat claims no ownership of the finished board.
        assert "pga" not in stats["inplay_owned"]
        assert redis.get(f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:pga") is None

    def test_a_resolved_market_with_no_resolution_date_is_also_refused(
        self, monkeypatch
    ):
        # The #1076 restore needs a date to call a resolution premature, so a
        # dateless resolved row is truly resolved on its terms too.
        world = _world(pga_status="resolved")
        for m in _pga(world[0]):
            m.resolution_date = None
        before = _frozen(world)

        stats, session, _redis, _service = _run(monkeypatch, world)

        _assert_untouched(world, before, session)
        assert stats["resolved_market_reopen_refused"] == len(datagolf.MARKET_TYPES)

    def test_each_row_is_decided_on_its_own_stored_status(self, monkeypatch):
        # Win resolved, the rest closed: only the closed rows reopen and write.
        per_type = {t: "closed" for t, _ in datagolf.MARKET_TYPES if t != "win"}
        world = _world(pga_status="resolved", per_type=per_type)
        win = world[0][datagolf._external_id("pga", PGA_EVENT_ID, "win")]
        before = _frozen(world)

        stats, session, _redis, _service = _run(monkeypatch, world)

        assert win.status == "resolved"
        assert _frozen(world)[0][win.external_id] == before[0][win.external_id]
        for (mid, _ext), o in world[1].items():
            if mid == win.id:
                assert o.current_probability == before[1][(mid, _ext)][0]
        others = [m for m in _pga(world[0]) if m is not win]
        assert all(m.status == "open" for m in others)
        top5 = world[0][datagolf._external_id("pga", PGA_EVENT_ID, "top_5")]
        assert world[1][(top5.id, f"dg_{WINNER_ID}")].current_probability == LAGGING_OTHER
        assert sorted(
            i for stmt in session.reranked for i in _param(_bound(stmt), "market_id")
        ) == sorted(m.id for m in others)
        assert stats["resolved_market_reopen_refused"] == 1

    def test_an_unrelated_open_tour_is_still_written_in_the_same_pass(
        self, monkeypatch
    ):
        world = _world(pga_status="resolved", with_euro=True)
        before = _frozen(world)

        stats, session, redis, _service = _run(monkeypatch, world, with_euro=True)

        _assert_untouched(world, before, session)
        euro_win = world[0][datagolf._external_id("euro", EURO_EVENT_ID, "win")]
        assert world[1][(euro_win.id, f"dg_{EURO_PLAYER_ID}")].current_probability == 0.31
        assert stats["inplay_owned"] == {"euro": [EURO_EVENT_ID]}
        assert redis.get(f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:euro") == EURO_EVENT_ID


# ------------------------------------------------- unchanged positive arms --


def _assert_written(world, session, stats):
    markets, outcomes, _snapshots = world
    pga = _pga(markets)
    assert all(m.status == "open" for m in pga)
    win = markets[datagolf._external_id("pga", PGA_EVENT_ID, "win")]
    assert outcomes[(win.id, f"dg_{WINNER_ID}")].current_probability == LAGGING_WIN
    assert (win.id, f"dg_{NEWCOMER_ID}") in outcomes
    assert win.market_metadata["leaderboard"][0]["dg_id"] == WINNER_ID
    assert win.market_metadata["leaderboard_updated_at"] != OLD.isoformat()
    assert stats["snapshots_written"] > 0
    assert sorted(
        i for stmt in session.reranked for i in _param(_bound(stmt), "market_id")
    ) == sorted(m.id for m in pga)
    assert stats["inplay_owned"] == {"pga": [PGA_EVENT_ID]}
    assert not stats.get("resolved_market_reopen_refused")


class TestTheLiveWriterStillWritesWhereItShould:
    def test_open_markets_are_written_without_entering_recovery(self, monkeypatch):
        world = _world(pga_status="open")
        stats, session, _redis, service = _run(monkeypatch, world)

        # Other tours (no in-play board) read the schedule in their own branch.
        assert "pga" not in service.schedule_reads
        _assert_written(world, session, stats)
        # The withdrawn player's price leaves the open board (#4958 arm).
        win = world[0][datagolf._external_id("pga", PGA_EVENT_ID, "win")]
        assert world[1][(win.id, f"dg_{VANISHED_ID}")].current_probability is None

    def test_markets_are_created_when_none_exist(self, monkeypatch):
        world = _world(pga_status=None)
        stats, session, _redis, _service = _run(monkeypatch, world)

        assert stats["markets_created"] == len(datagolf.MARKET_TYPES)
        _assert_written(world, session, stats)

    def test_a_closed_board_is_still_reopened_and_written(self, monkeypatch):
        world = _world(pga_status="closed")
        stats, session, _redis, _service = _run(monkeypatch, world)

        assert stats["markets_created"] == 0
        _assert_written(world, session, stats)

    def test_a_future_dated_resolution_keeps_its_1076_reopen(self, monkeypatch):
        # Resolved by mistake before its end date: the live recovery reopens it
        # exactly as it did before this change.
        world = _world(pga_status="resolved", pga_resolution_date=_future_resolution())
        stats, session, _redis, _service = _run(monkeypatch, world)

        _assert_written(world, session, stats)

    def test_team_match_play_is_still_neither_created_nor_reopened(self, monkeypatch):
        world = _world(pga_status="closed")
        before = _frozen(world)
        stats, session, _redis, _service = _run(
            monkeypatch, world, schedule_name="Presidents Cup"
        )

        assert all(m.status == "closed" for m in _pga(world[0]))
        _assert_untouched(world, before, session)
        assert not stats.get("resolved_market_reopen_refused")


# ------------------------------------------------------- rig self-checks --


def test_the_rig_scan_hides_a_row_whose_status_is_not_open(monkeypatch):
    """A resolved row reaches the writer ONLY by being reopened — and an
    open row is read straight from the scan. Without this the refusal arm
    could pass because the fake hid nothing or everything."""
    markets, outcomes, snapshots = _world(pga_status="resolved")
    session = _LiveSession(markets, outcomes, snapshots)
    stmt = datagolf.select(FuturesMarket).where(
        FuturesMarket.source == "datagolf",
        FuturesMarket.external_id.like("datagolf:pga:%"),
        FuturesMarket.status == "open",
    )
    assert asyncio.run(session.execute(stmt)).all() == []
    for m in markets.values():
        m.status = "open"
    assert len(asyncio.run(session.execute(stmt)).all()) == len(datagolf.MARKET_TYPES)
