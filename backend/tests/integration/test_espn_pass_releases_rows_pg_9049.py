"""#9049 — the ESPN live pass does not hold a game's row across ESPN calls. Real Postgres.

## the ship

A new live price and a new live score reach the page without queueing behind
the ESPN live sync.

## why real Postgres

The defect is a lock, and only Postgres holds one. On production 9/27
04:14–04:21Z this pass sat idle in transaction for 11.9–22.8 s holding `events`
row locks, and the socket's price write waited 10.65 s behind it. A
`_step_savepoint` (#8796) releases a SAVEPOINT, not a row lock, so a row the
live loop wrote stayed locked until the one COMMIT at the end of the pass —
through every later sport and every box-score fetch.

## the arms

Each probe is a second connection taking the row `FOR UPDATE NOWAIT`, the lock
the socket's and the poll's writes need; it either gets the row or it fails at
once.

* task: while the NEXT sport's step and the live box-score step run, the row an
  earlier sport wrote is free — RED before #9049;
* box pass: while ESPN is asked about game 2, game 1's row is free — RED before
  #9049 (game 1 was written before game 2 was fetched);
* one sport (CERT-3611): while the pass asks ESPN for game B's dated board,
  game A — on the undated board, same sport — is free. RED at 0fd0bd5ea3 (A was
  written first and stayed locked, same savepoint, through the wait);
* StatPal livescores (#10090): while the writer reads the next sport's board,
  the row the previous sport confirm-stamped takes a venue stamp under a 500 ms
  lock budget. RED at 76013097 (one transaction over every sport);
* straggler arms (#10090): while the deep and unstarted arms ask ESPN, the
  row the shallow arm wrote is free, and no board read of
  `_ask_boards_by_espn_id` finds a row that arm wrote locked. RED at 765e1e1d
  (the three arms asked ESPN between writes and committed once, after the third);
* controls: the probe DOES see a lock that is held (else every arm passes on a
  blind probe), and every write still commits.

Reuses the #8796 file's database and fixture. Runs where
`DELAY_CONTRACT_DATABASE_URL` is set (CI job `search-recall`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from tests.integration.test_espn_pass_survives_one_failed_statement_pg_8796 import (  # noqa: F401 — `db` is the fixture
    MLB,
    NHL,
    _wire,
    db,
    needs_postgres,
)
from tests.integration.test_nonvenue_live_push_pg_8761 import sink  # noqa: F401

pytestmark = [pytest.mark.asyncio]


@needs_postgres
@pytest.mark.parametrize("upcoming_result", ["empty", "error", "cancel"])
async def test_live_probability_publishes_before_upcoming_only_board(
    db, monkeypatch, sink, upcoming_result  # noqa: F811 — imported pytest fixtures
):
    """A scheduled-only network wait cannot retain a healthy live update."""
    import asyncio
    import app.services.espn_api as espn_api
    import app.tasks.espn_sync as task
    from app.models.models import Event
    from app.utils.nonvenue_live_push import write_nonvenue_probability

    engine, maker, ids = db
    target = ids["the_failing_sports_row"]
    seen, calls, services, decisions = [], [], [], []
    board = [object()]

    async def known(session, event_id):
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.72)
        assert not await _is_free(engine, target)
        assert not sink

    _wire(monkeypatch, maker, ids, known)

    async def keys(session):
        # MLB appears in both sets but must be fetched only once.
        return [MLB], [MLB, NHL]

    class Scoreboards:
        rate_limit_delay = 0

        def __init__(self):
            self.closed = False
            services.append(self)

        async def get_scoreboard(self, sport_key, **kwargs):
            assert not self.closed
            calls.append(sport_key)
            if sport_key == MLB:
                return board
            async with maker() as reader:
                sources = await reader.scalar(
                    select(Event.win_probability_sources).where(Event.id == target)
                )
            seen.append((sources.get("espn", {}).get("value"), list(sink)))
            assert await _is_free(engine, target)
            if upcoming_result == "error":
                raise RuntimeError("upcoming board unavailable")
            if upcoming_result == "cancel":
                raise asyncio.CancelledError()
            return []

        async def close(self):
            self.closed = True

    async def decide(data, fetch_keys, stats):
        decisions.append((dict(data), set(fetch_keys)))
        return {}

    monkeypatch.setattr(task, "_find_sport_keys_to_sync", keys)
    monkeypatch.setattr(task, "_decide_failovers", decide)
    monkeypatch.setattr(espn_api, "ESPNAPIService", Scoreboards)
    if upcoming_result == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await task._sync_espn_live_events()
        assert not decisions
    else:
        stats = await task._sync_espn_live_events()
        assert decisions == [(
            {MLB: board, **({NHL: []} if upcoming_result == "empty" else {})},
            {MLB, NHL},
        )]
        assert len(stats["errors"]) == (1 if upcoming_result == "error" else 0)
    assert sorted(calls) == sorted([MLB, NHL])
    assert all(service.closed for service in services)
    assert len(seen) == 1
    assert seen[0][0] == 0.72, seen
    assert len(seen[0][1]) == len(sink) == 1, seen
    frame = seen[0][1][0][1]
    assert frame["event_id"] == target and frame["source_value"] == 0.72


@needs_postgres
@pytest.mark.parametrize("failure", [None, "standby", "known"])
async def test_healthy_live_probability_publishes_before_dark_sport_check(
    db, monkeypatch, sink, failure  # noqa: F811 — imported pytest fixtures
):
    """An unrelated failover check cannot hold an already-read healthy blend.

    Inspect the real committed row and publication payload at the boundary
    where the real task enters the standby decision. No sleep or timing proxy.
    """
    import app.services.espn_api as espn_api
    import app.tasks.espn_sync as task
    from app.models.models import Event
    from app.utils.nonvenue_live_push import write_nonvenue_probability

    engine, maker, ids = db
    target = ids["the_failing_sports_row"]
    seen, acted = [], []
    board = [object()]
    decisions = {NHL: object()}

    async def known(session, event_id):
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.72)
        assert not await _is_free(engine, target)
        assert not sink  # never publish before commit
        if failure == "known":
            await session.execute(text("SELECT 1 / 0"))

    _wire(monkeypatch, maker, ids, known)

    class Scoreboards:
        async def get_scoreboard(self, sport_key, **kwargs):
            return board if sport_key == MLB else None

        async def close(self):
            pass

    async def decide(data, keys, stats):
        assert data == {MLB: board}  # dark is absent, never an empty slate
        assert set(keys) == {MLB, NHL}
        async with maker() as reader:
            sources = await reader.scalar(
                select(Event.win_probability_sources).where(Event.id == target)
            )
        seen.append((sources.get("espn", {}).get("value"), list(sink)))
        assert await _is_free(engine, target)
        if failure == "standby":
            raise RuntimeError("standby unavailable")
        return decisions

    async def act(value, stats):
        assert value is decisions
        acted.append(value)

    monkeypatch.setattr(espn_api, "ESPNAPIService", Scoreboards)
    monkeypatch.setattr(task, "_decide_failovers", decide)
    monkeypatch.setattr(task, "_act_on_failovers", act)
    stats = await task._sync_espn_live_events()
    assert len(seen) == 1
    if failure == "known":
        assert seen == [(None, [])]
        assert sink == []
    else:
        assert seen[0][0] == 0.72, seen
        assert len(seen[0][1]) == len(sink) == 1, seen
        frame = seen[0][1][0][1]
        assert frame["event_id"] == target and frame["source_value"] == 0.72
    assert len(acted) == (0 if failure == "standby" else 1)
    assert len(stats["errors"]) == (0 if failure is None else 1), stats
    assert stats["authority_dark_sports"] == 1


@needs_postgres
@pytest.mark.parametrize("failure", [None, "creation", "known"])
async def test_known_game_publishes_before_unmatched_creation(
    db, monkeypatch, sink, failure  # noqa: F811 — imported pytest fixtures
):
    """#10090: a delayed/new-game writer cannot pin an already-read live price.

    Actual PG writes, savepoints, commit hooks and publication drain; the Redis
    sink records the real EVAL payload. Hold at creator entry, without a sleep.
    """
    import inspect

    import app.tasks.espn_sync as task
    import app.utils.espn_helpers as helpers
    from app.models.models import Event
    from app.utils.nonvenue_live_push import write_nonvenue_probability

    engine, maker, ids = db
    target = ids["the_failing_sports_row"]
    sibling = ids["the_next_sports_row"]
    signature = inspect.signature(task._process_live_sport)
    seen = []

    async def noop(*a, **k):
        pass

    _wire(monkeypatch, maker, ids, noop)

    async def known(*args, **kwargs):
        bound = signature.bind(*args, **kwargs).arguments
        if bound["sport_key"] != MLB:
            return
        session = bound["session"]
        event = await session.get(Event, target)
        await write_nonvenue_probability(session, event, "espn", 0.72)
        assert not await _is_free(engine, target)  # positive lock control
        assert sink == []  # never publish before commit
        await bound["create_unmatched_fn"](
            session, [event], bound["espn_events"], MLB, bound["stats"]
        )
        if failure == "known":
            await session.execute(text("SELECT 1 / 0"))

    async def create(session, rows, board, sport_key, stats):
        async with maker() as reader:
            sources = await reader.scalar(
                select(Event.win_probability_sources).where(Event.id == target)
            )
        seen.append({
            "free": await _is_free(engine, target),
            "committed": sources.get("espn", {}).get("value"),
            "frames": [frame for _, frame in sink],
            "ids": tuple(row.espn_id for row in rows),
            "orm": any(inspect.isclass(type(row)) and hasattr(row, "_sa_instance_state") for row in rows),
            "board": tuple(board),
        })
        await session.execute(
            update(Event).where(Event.id == sibling).values(period="created")
        )
        if failure == "creation":
            await session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(task, "_process_live_sport", known)
    monkeypatch.setattr(helpers, "create_events_from_unmatched_espn", create)
    stats = await task._sync_espn_live_events()
    async with maker() as reader:
        sources = await reader.scalar(
            select(Event.win_probability_sources).where(Event.id == target)
        )
        period = await reader.scalar(select(Event.period).where(Event.id == sibling))
    if failure == "known":
        assert seen == []  # rolled-back matching context must never create
        assert sink == []
        assert "espn" not in sources
        assert period is None
    else:
        assert len(seen) == 1
        assert seen[0]["free"] is True, seen
        assert seen[0]["committed"] == 0.72, seen
        assert len(seen[0]["frames"]) == 1, seen
        frame = seen[0]["frames"][0]
        assert frame["event_id"] == target and frame["source_value"] == 0.72
        assert seen[0]["ids"] == ("8796-3",)
        assert seen[0]["orm"] is False
        assert seen[0]["board"]  # full supplied board survives the boundary
        assert sources["espn"]["value"] == 0.72
        assert period == (None if failure else "created")
        assert len(sink) == 1  # no duplicate commit publication
    assert len(stats["errors"]) == (1 if failure else 0), stats


# Retained independent #11671 P1/P4 controls: release and rollback are both
# load-bearing when moving known-game publication ahead of new-game creation.
@needs_postgres
async def test_creation_commits_and_publishes_before_next_sport(db, monkeypatch, sink):  # noqa: F811
    """Creation's own writes/frames are released before the NEXT sport runs."""
    import inspect

    import app.tasks.espn_sync as task
    import app.utils.espn_helpers as helpers
    from app.models.models import Event
    from app.utils.nonvenue_live_push import write_nonvenue_probability

    engine, maker, ids = db
    target, sibling = ids["the_failing_sports_row"], ids["the_next_sports_row"]
    sig = inspect.signature(task._process_live_sport)
    seen = {}
    async def noop(*a, **k):
        pass

    _wire(monkeypatch, maker, ids, noop)

    async def known(*args, **kwargs):
        b = sig.bind(*args, **kwargs).arguments
        s = b["session"]
        if b["sport_key"] == MLB:
            ev = await s.get(Event, target)
            await write_nonvenue_probability(s, ev, "espn", 0.72)
            await b["create_unmatched_fn"](s, [ev], b["espn_events"], MLB, b["stats"])
        else:
            async with maker() as r:
                seen["period"] = await r.scalar(select(Event.period).where(Event.id == sibling))
            seen["free"] = await _is_free(engine, sibling)
            seen["frames"] = [(f["event_id"], f["source_value"]) for _, f in sink]

    async def create(session, rows, board, key, stats):
        if key != MLB:
            return
        await session.execute(update(Event).where(Event.id == sibling).values(period="created"))
        ev = await session.get(Event, sibling)
        await write_nonvenue_probability(session, ev, "espn", 0.61)

    monkeypatch.setattr(task, "_process_live_sport", known)
    monkeypatch.setattr(helpers, "create_events_from_unmatched_espn", create)
    stats = await task._sync_espn_live_events()
    assert stats["errors"] == [], stats["errors"]
    assert seen["period"] == "created", seen
    assert seen["free"] is True, seen
    assert (target, 0.72) in seen["frames"] and (sibling, 0.61) in seen["frames"], seen
    assert len(sink) == 2


@needs_postgres
async def test_swallowed_creation_failure_publishes_nothing_it_wrote(db, monkeypatch, sink):  # noqa: F811
    """The real creator's shape: per-item failure caught and logged AFTER a
    queued probability frame. The creation savepoint must roll it back, publish
    no frame for it, and receipt one creation error; known MLB stays."""
    import inspect

    import app.tasks.espn_sync as task
    import app.utils.espn_helpers as helpers
    from app.models.models import Event
    from app.utils.nonvenue_live_push import write_nonvenue_probability

    engine, maker, ids = db
    target, sibling = ids["the_failing_sports_row"], ids["the_next_sports_row"]
    sig = inspect.signature(task._process_live_sport)
    async def noop(*a, **k):
        pass

    _wire(monkeypatch, maker, ids, noop)

    async def known(*args, **kwargs):
        b = sig.bind(*args, **kwargs).arguments
        s = b["session"]
        if b["sport_key"] == MLB:
            ev = await s.get(Event, target)
            await write_nonvenue_probability(s, ev, "espn", 0.72)
            await b["create_unmatched_fn"](s, [ev], b["espn_events"], MLB, b["stats"])

    async def create(session, rows, board, key, stats):
        ev = await session.get(Event, sibling)
        await write_nonvenue_probability(session, ev, "espn", 0.33)
        try:
            await session.execute(text("SELECT 1 / 0"))
        except Exception:
            pass  # create_events_from_unmatched_espn's per-item swallow

    monkeypatch.setattr(task, "_process_live_sport", known)
    monkeypatch.setattr(helpers, "create_events_from_unmatched_espn", create)
    stats = await task._sync_espn_live_events()
    async with maker() as r:
        t = await r.scalar(select(Event.win_probability_sources).where(Event.id == target))
        s = await r.scalar(select(Event.win_probability_sources).where(Event.id == sibling))
    assert t["espn"]["value"] == 0.72
    assert "espn" not in (s or {}), s
    assert [(f["event_id"], f["source_value"]) for _, f in sink] == [(target, 0.72)], sink
    assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(f"{MLB} creation:"), stats["errors"]

async def _is_free(engine, event_id) -> bool:
    """Can another writer take this row right now?"""
    async with engine.connect() as conn:
        tx = await conn.begin()
        try:
            await conn.execute(
                text("SELECT id FROM events WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": event_id},
            )
            return True
        except DBAPIError:
            return False
        finally:
            await tx.rollback()


@needs_postgres
class TestTheProbe:
    async def test_the_probe_sees_a_held_row(self, db):
        """INSTRUMENT CONTROL. A probe that always answered "free" would pass
        every arm below; here an open transaction has written the row."""
        from app.models.models import Event

        engine, maker, ids = db
        row = ids["the_failing_sports_row"]
        async with maker() as session:
            await session.execute(
                update(Event).where(Event.id == row).values(period="Top 9th")
            )
            assert await _is_free(engine, row) is False
            await session.rollback()
        assert await _is_free(engine, row) is True


@needs_postgres
class TestTheTaskReleasesEachSportsRows:
    async def test_an_earlier_sports_row_is_free_while_the_pass_goes_on(
        self, db, monkeypatch
    ):
        """THE SHIP, at the task. RED before #9049: MLB's row stayed locked
        through NHL's step and through the live box-score step."""
        import app.tasks.espn_sync as espn_sync
        import app.utils.espn_helpers as helpers
        from app.models.models import Event
        from app.tasks.espn_sync import _sync_espn_live_events

        engine, maker, ids = db
        mlb_row, nhl_row = ids["the_failing_sports_row"], ids["the_next_sports_row"]
        seen: dict = {}

        async def _clean(session, event_id):
            await session.execute(
                update(Event).where(Event.id == event_id).values(period="Top 9th")
            )

        _wire(monkeypatch, maker, ids, _clean)

        async def _live(session, sport_key, *a, **k):
            if sport_key == MLB:
                await _clean(session, mlb_row)
            else:
                seen["mlb_during_nhl"] = await _is_free(engine, mlb_row)
                await session.execute(
                    update(Event).where(Event.id == nhl_row).values(period="2nd Period")
                )

        async def _live_box(session, stats):
            seen["mlb_during_box"] = await _is_free(engine, mlb_row)
            seen["nhl_during_box"] = await _is_free(engine, nhl_row)

        monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
        monkeypatch.setattr(helpers, "fetch_live_box_scores", _live_box)

        stats = await _sync_espn_live_events()

        assert stats["errors"] == [], stats["errors"]
        assert seen == {
            "mlb_during_nhl": True,
            "mlb_during_box": True,
            "nhl_during_box": True,
        }, seen

        async with maker() as session:
            periods = dict(
                (
                    await session.execute(
                        select(Event.id, Event.period).where(
                            Event.id.in_([mlb_row, nhl_row])
                        )
                    )
                ).all()
            )
        # WRITE CONTROL: releasing early must not cost the writes.
        assert periods == {mlb_row: "Top 9th", nhl_row: "2nd Period"}, periods


class _SlowEspn:
    """ESPN that, while answering each game, lets the test probe every game it
    answered before."""

    def __init__(self, engine, espn_to_id):
        self._engine = engine
        self._ids = espn_to_id
        self.asked: list = []
        self.locked_during_fetch: list = []

    async def get_event_context(self, sport_key, espn_id):
        for earlier in self.asked:
            if not await _is_free(self._engine, earlier):
                self.locked_during_fetch.append(earlier)
        self.asked.append(self._ids[espn_id])
        return {"box_score": {"P": {"h": 1}}, "scoring_plays": [], "scores": {}}

    async def close(self):
        pass


@needs_postgres
class TestTheBoxPassWritesAfterItFetches:
    async def test_no_game_is_locked_while_another_is_fetched(self, db, monkeypatch):
        """THE SHIP, in the box pass. RED before #9049: each game was written as
        soon as it was fetched, so game 1 was locked while 2, 3, 4 were asked."""
        import app.services.espn_api as espn_api
        from app.models.models import Event
        from app.utils.espn_helpers import fetch_live_box_scores

        engine, maker, ids = db
        async with maker() as session:
            espn_to_id = dict(
                (
                    await session.execute(
                        select(Event.espn_id, Event.id).where(
                            Event.id.in_(list(ids.values()))
                        )
                    )
                ).all()
            )
        espn = _SlowEspn(engine, espn_to_id)
        monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)

        stats: dict = {}
        async with maker() as session:
            await fetch_live_box_scores(session, stats)
            await session.commit()

        assert len(espn.asked) == 4, espn.asked
        assert espn.locked_during_fetch == [], espn.locked_during_fetch

        # WRITE CONTROL: every game fetched landed its box score.
        assert stats["live_box_scores_fetched"] == 4
        async with maker() as session:
            boxes = (
                await session.execute(
                    select(Event.box_score_data).where(Event.id.in_(espn.asked))
                )
            ).scalars().all()
        assert [b["live"] for b in boxes] == [True] * 4, boxes


def _live_board_row(espn_id):
    """An in-progress ESPN board entry (not final: this arm is about the lock,
    not the settle door)."""
    from app.services.espn_api import ESPNEvent
    from tests.test_undated_board_is_a_slice_5697 import _team

    return ESPNEvent(
        espn_id=espn_id,
        name=f"{espn_id} away at home",
        short_name=espn_id,
        date=None,
        status="in",
        status_detail="2nd Period",
        period=2,
        clock="10:00",
        home_team=_team(f"Home {espn_id}", f"H{espn_id}"),
        away_team=_team(f"Away {espn_id}", f"A{espn_id}"),
        home_score=1,
        away_score=0,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


@needs_postgres
class TestOneSportsDatedBoardWaitsForNoWrittenRow:
    async def test_a_written_game_is_free_while_a_sibling_waits_on_the_dated_board(
        self, db
    ):
        """CERT-3611's path, on real rows. Game A is on the undated board and is
        written; game B is not, so the pass asks ESPN for B's dated board. RED at
        0fd0bd5ea3: A was written first, and its row stayed locked (same
        sport, same savepoint, no commit) for the whole ESPN wait."""
        from datetime import datetime, timedelta, timezone

        from app.models.models import Event
        from app.tasks.espn_sync import _process_live_sport, _step_savepoint

        engine, maker, ids = db
        a, b = ids["the_stat_model_row"], ids["a_sibling_the_pass_also_writes"]
        async with maker() as session:
            espn_of = dict(
                (
                    await session.execute(
                        select(Event.id, Event.espn_id).where(Event.id.in_([a, b]))
                    )
                ).all()
            )
        undated = [_live_board_row(espn_of[a])]
        dated = undated + [_live_board_row(espn_of[b])]

        written: list = []
        at_fetch: list = []

        def _match(event, pool, by_id, claimed, names_match):
            # By id only: the widening, not the name matcher, is under test.
            if event.espn_id in by_id:
                return by_id[event.espn_id], "espn_id"
            return None, None

        async def _update_fields(session, event, ee, claimed, stats, *, observed_at=None):
            await session.execute(
                update(Event).where(Event.id == event.id).values(period="2nd Period")
            )
            written.append(event.id)
            return True

        async def _dated(sport_key, board_day):
            at_fetch.append(
                {row: await _is_free(engine, row) for row in (a, *written)}
            )
            return dated

        async def _none(*a_, **k):
            return None

        async def _false(*a_, **k):
            return False

        now = datetime.now(timezone.utc)
        stats = {"events_synced": 0, "events_updated": 0, "errors": []}
        async with maker() as session:
            async with _step_savepoint(session):
                await _process_live_sport(
                    session, NHL, undated, stats,
                    now - timedelta(hours=6), now - timedelta(hours=5),
                    lambda *x: False, _none, _none,
                    _match, _update_fields, _false, _false, _none,
                    dated_board_fetcher=_dated,
                )
            await session.commit()

        assert at_fetch, "the dated board was never asked — the arm tested nothing"
        assert all(all(free.values()) for free in at_fetch), at_fetch
        # WIDENING + WRITE CONTROL: B still matched on the dated board, and both
        # writes committed.
        assert stats.get("events_matched_on_dated_board", 0) >= 1, stats
        assert a in written and b in written, written
        async with maker() as session:
            periods = dict(
                (
                    await session.execute(
                        select(Event.id, Event.period).where(Event.id.in_([a, b]))
                    )
                ).all()
            )
        assert periods == {a: "2nd Period", b: "2nd Period"}, periods


# ── #10090: the StatPal livescore writer, the same class on the 30 s beat ──
#
# Production 10/28 00:00-00:02Z: three holders from the realtime dyno sat idle
# in transaction 14.0-18.5 s, each last statement the confirm-only score stamp
# (`UPDATE events SET score_source=…, score_observed_at=… WHERE id AND period
# AND game_clock AND home_score AND away_score`), with 5-9 venue price stamps
# refused behind each under their 500 ms lock budget. `_sync_statpal_livescores`
# held one transaction over every sport and read the next sport's StatPal board
# with the previous sport's rows still locked.


class _StatPalBoardRow:
    """One in-progress StatPal live-board row (the 6056 file's `_Fixture` shape)."""

    def __init__(self, home, away, *, raw_status, game_clock, scores, clocked):
        self.start_time = None
        self.home_team, self.away_team = home, away
        self.status = "live"
        self.fixture_id = f"10090-{home}"
        self.odds_id = None
        self.home_score, self.away_score = scores
        self.raw_status = raw_status
        self.game_clock = game_clock
        self.clock_field_served = clocked


async def _venue_stamp_lands(engine, event_id) -> bool:
    """Can the venue arm's stamp take this row inside its 500 ms lock budget?"""
    async with engine.connect() as conn:
        tx = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await conn.execute(
                text(
                    "UPDATE events SET win_probability_sources = "
                    "win_probability_sources WHERE id = :id"
                ),
                {"id": event_id},
            )
            return True
        except DBAPIError:
            return False
        finally:
            await tx.rollback()


@needs_postgres
class TestStatPalLivescoresHoldNoRowAcrossTheNextBoard:
    async def test_a_confirmed_row_takes_a_venue_stamp_while_the_next_board_is_read(
        self, db, monkeypatch  # noqa: F811 — imported pytest fixture
    ):
        """RED at 76013097: the first sport's confirm-only stamp held its row
        through the second sport's StatPal read, so the venue stamp timed out."""
        from contextlib import asynccontextmanager

        import app.services.statpal_api as statpal_api
        import app.tasks.statpal_sync as statpal_sync
        from app.models.models import Event
        from app.utils.score_observation import SCORE_SOURCE_STATPAL

        engine, maker, ids = db
        nhl_row, mlb_row = ids["the_stat_model_row"], ids["the_failing_sports_row"]
        boards = {
            "nhl": _StatPalBoardRow(
                "San Jose Sharks", "Anaheim Ducks",
                raw_status="2nd Period", game_clock="10:00", scores=(1, 0),
                clocked=True,
            ),
            "mlb": _StatPalBoardRow(
                "Seattle Mariners", "Los Angeles Angels",
                raw_status="Top 5th", game_clock=None, scores=(2, 1),
                clocked=False,
            ),
        }
        # Each row already holds what its board says (and NHL its anchor), so
        # the pass's only write is the confirm-only stamp — production's holder
        # statement exactly. MLB's live board carries no anchor field (#3094).
        async with maker() as session:
            await session.execute(
                update(Event).where(Event.id == nhl_row).values(
                    period="10:00 - 2nd Period", game_clock="10:00",
                    home_score=1, away_score=0,
                    statpal_fixture_id=boards["nhl"].fixture_id,
                )
            )
            await session.execute(
                update(Event).where(Event.id == mlb_row).values(
                    period="Top 5th", game_clock=None, home_score=2, away_score=1,
                )
            )
            await session.commit()

        written: list = []
        held_after_write: list = []
        at_read: list = []

        @asynccontextmanager
        async def _session(**_kwargs):
            async with maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        real_write = statpal_sync.write_live_state_if_unmoved

        async def _write_then_probe(session, event, values, **kwargs):
            landed = await real_write(session, event, values, **kwargs)
            written.append(event.id)
            # POSITIVE LOCK CONTROL, in this run: the writer's own uncommitted
            # stamp IS visible to the probe, so a "free" below is not blindness.
            held_after_write.append(not await _venue_stamp_lands(engine, event.id))
            return landed

        class _Service:
            async def get_live_scores(self, sport):
                at_read.append(
                    (sport, {row: await _venue_stamp_lands(engine, row) for row in written})
                )
                board = boards.get(sport)
                return [board] if board else []

            async def close(self):
                pass

        monkeypatch.setattr(statpal_sync, "get_task_session", _session)
        monkeypatch.setattr(statpal_sync, "write_live_state_if_unmoved", _write_then_probe)
        monkeypatch.setattr(statpal_api, "is_available", lambda: True)
        monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

        result = await statpal_sync._sync_statpal_livescores()

        assert sorted(s for s, _ in at_read) == ["mlb", "nhl"], at_read
        assert sorted(written) == sorted([nhl_row, mlb_row]), written
        assert held_after_write == [True, True], held_after_write
        # The arm reached its question: the second read had a written row to probe.
        assert at_read[1][1], at_read
        assert all(all(free.values()) for _, free in at_read), at_read
        # WRITE CONTROL: confirmation only, and both stamps committed.
        assert result["events_updated"] == 0, result
        assert result["livescore_confirmation_lost_race"] == 0, result
        async with maker() as session:
            stamps = dict(
                (
                    await session.execute(
                        select(Event.id, Event.score_source).where(
                            Event.id.in_([nhl_row, mlb_row])
                        )
                    )
                ).all()
            )
        assert stamps == {
            nhl_row: SCORE_SOURCE_STATPAL, mlb_row: SCORE_SOURCE_STATPAL,
        }, stamps


@needs_postgres
class TestTheStragglerArmsHoldNoRowAcrossAnEspnRead:
    """#10090, lock watch 4 (2026-10-29 04:38:57–04:39:03Z): the pass's first
    transaction sat idle in transaction 6.2 s between whole-column
    `win_probability_sources` writes, the socket's stamps queued behind it. The
    three straggler arms asked ESPN, wrote, asked again, and committed once,
    after the third — and the shallow arm's rows are live games once ESPN's
    board rolls at Eastern midnight."""

    async def test_the_shallow_arms_row_is_free_while_the_later_arms_ask_espn(
        self, db, monkeypatch
    ):
        """RED before #10090: `[False, False]`."""
        import app.tasks.espn_sync as espn_sync
        from app.models.models import Event

        engine, maker, ids = db
        live_row = ids["the_stat_model_row"]
        seen = []

        async def _no_write(session, event_id):
            return None

        async def _shallow(session, espn, now, stats, door):
            await session.execute(
                update(Event).where(Event.id == live_row).values(home_score=3)
            )

        async def _asks_espn(session, espn, now, stats, *a):
            seen.append(await _is_free(engine, live_row))

        _wire(monkeypatch, maker, ids, _no_write)
        monkeypatch.setattr(espn_sync, "_settle_authority_stragglers", _shallow)
        monkeypatch.setattr(espn_sync, "_settle_deep_authority_stragglers", _asks_espn)
        monkeypatch.setattr(
            espn_sync, "_recover_unstarted_authority_fixtures", _asks_espn
        )

        stats = await espn_sync._sync_espn_live_events()

        assert stats["errors"] == [], stats["errors"]
        assert seen == [True, True]
        # WRITE CONTROL: the shallow arm's write committed.
        async with maker() as session:
            score = (
                await session.execute(
                    select(Event.home_score).where(Event.id == live_row)
                )
            ).scalar_one()
        assert score == 3

    async def test_no_row_an_arm_wrote_is_locked_while_it_reads_a_board(self, db):
        """`_ask_boards_by_espn_id` on a real session. RED before #10090:
        `[[], [False], [False, False]]` — each board read found the earlier
        groups' rows locked."""
        from types import SimpleNamespace

        from app.models.models import Event
        from app.tasks.espn_sync import _ask_boards_by_espn_id

        engine, maker, ids = db
        rows = [
            ids["the_stat_model_row"],
            ids["a_sibling_the_pass_also_writes"],
            ids["the_next_sports_row"],
        ]
        written: list = []
        probes: list = []

        class _Espn:
            async def get_scoreboard(self, sport_key, date=None):
                probes.append([await _is_free(engine, r) for r in written])
                return [SimpleNamespace(espn_id=date)]

        async def _door(
            session, event, matched, claimed, stats, *, allow_unstarted, observed_at
        ):
            await session.execute(
                update(Event).where(Event.id == event.id).values(game_clock="0:00")
            )
            written.append(event.id)

        groups = [
            (
                ("icehockey_nhl", f"2026102{n}"),
                [SimpleNamespace(id=row, espn_id=f"2026102{n}", status="live")],
            )
            for n, row in enumerate(rows)
        ]
        stats = {"errors": [], "authority_dark_sports": 0, "straggler_boards_fetched": 0}
        async with maker() as session:
            await _ask_boards_by_espn_id(
                session, _Espn(), groups, stats, _door,
                stat_prefix="straggler", log_tag="%s",
            )
            await session.commit()

        assert len(probes) == 3
        assert all(all(free) for free in probes), probes
        # WRITE CONTROL: every group was written, in order, and committed.
        assert written == rows
        async with maker() as session:
            clocks = (
                await session.execute(
                    select(Event.game_clock).where(Event.id.in_(rows))
                )
            ).scalars().all()
        assert clocks == ["0:00"] * 3
