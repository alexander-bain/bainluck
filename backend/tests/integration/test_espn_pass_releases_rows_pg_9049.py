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

pytestmark = [pytest.mark.asyncio]


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
