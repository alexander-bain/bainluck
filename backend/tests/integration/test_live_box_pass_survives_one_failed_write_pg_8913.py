"""One game's failed write does not discard the live box-score pass. #8913, real Postgres.

``fetch_live_box_scores`` writes each live game's box score inside the ESPN
pass's one transaction and swallows a per-game failure. Measured on production
9/26 (``task-metrics/espn_sync``, college football slate): 2 of ~60 passes
logged ``live_box_score_pass: InFailedSQLTransactionError … UPDATE events SET
box_score_data``, each behind a lost row lock. On Postgres the failed UPDATE
aborts the transaction, so every later game raised, and the step's own
savepoint (#8796) rolled back the box scores already written that pass —
readers' box scores froze for a pass whenever one game's row was contended.

Only Postgres aborts a transaction, so this file uses the real statement failing
the real way: a second connection holds one game's row ``FOR UPDATE`` and the
pass runs under a short ``lock_timeout``, inside the same ``_step_savepoint``
the task wraps it in.

* ship: the games written before AND after the contended one keep their box
  scores — RED before #8913 (all three siblings lost);
* kill control: uncontended, every game lands its box score (a savepoint that
  swallowed every write would pass the ship on the contended game alone).

Reuses the #8796 file's database and fixture. Runs where
``DELAY_CONTRACT_DATABASE_URL`` is set (CI job ``search-recall``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text, update

from tests.integration.test_espn_pass_survives_one_failed_statement_pg_8796 import (  # noqa: F401 — `db` is the fixture
    db,
    needs_postgres,
)

pytestmark = [pytest.mark.asyncio]

#: Write order is `fetched_at` nulls first, then newest kickoff first. Staggered
#: kickoffs pin it, so the contended game has a sibling on each side.
_ORDER = (
    "the_stat_model_row",
    "a_sibling_the_pass_also_writes",
    "the_failing_sports_row",
    "the_next_sports_row",
)
_CONTENDED = "a_sibling_the_pass_also_writes"


class _Espn:
    def __init__(self, espn_to_id):
        self._ids = espn_to_id
        self.asked: list = []

    async def get_event_context(self, sport_key, espn_id):
        self.asked.append(self._ids[espn_id])
        return {"box_score": {"P": {"h": 1}}, "scoring_plays": [], "scores": {}}

    async def close(self):
        pass


async def _stagger(maker, ids):
    from app.models.models import Event

    now = datetime.now(timezone.utc)
    async with maker() as session:
        for i, name in enumerate(_ORDER):
            await session.execute(
                update(Event)
                .where(Event.id == ids[name])
                .values(commence_time=now - timedelta(minutes=10 * (i + 1)))
            )
        espn_to_id = dict(
            (
                await session.execute(
                    select(Event.espn_id, Event.id).where(
                        Event.id.in_(list(ids.values()))
                    )
                )
            ).all()
        )
        await session.commit()
    return espn_to_id


async def _boxes(maker, ids):
    from app.models.models import Event

    async with maker() as session:
        rows = dict(
            (
                await session.execute(
                    select(Event.id, Event.box_score_data).where(
                        Event.id.in_(list(ids.values()))
                    )
                )
            ).all()
        )
    return {name: rows[ids[name]] for name in _ORDER}


async def _run_pass(maker, monkeypatch, espn, stats):
    """The pass as `_sync_espn_live_events` runs it: inside `_step_savepoint`,
    one COMMIT at the end."""
    import app.services.espn_api as espn_api
    from app.tasks.espn_sync import _step_savepoint
    from app.utils.espn_helpers import fetch_live_box_scores

    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)
    async with maker() as session:
        await session.execute(text("SET LOCAL lock_timeout = '300ms'"))
        try:
            async with _step_savepoint(session):
                await fetch_live_box_scores(session, stats)
        except Exception as e:  # the task's own handler
            stats.setdefault("errors", []).append(f"live_box_score_pass: {e}")
        await session.commit()


@needs_postgres
class TestOneGamesFailedWriteCostsOnlyThatGame:
    async def test_the_siblings_keep_their_box_scores(self, db, monkeypatch):
        """THE SHIP. RED before #8913: the contended game's UPDATE lost its lock,
        the games after it raised InFailedSQLTransactionError, and the step's
        savepoint rolled back the game written before it too."""
        engine, maker, ids = db
        espn = _Espn(await _stagger(maker, ids))

        holder = await engine.connect()
        holder_tx = await holder.begin()
        await holder.execute(
            text("SELECT id FROM events WHERE id = :id FOR UPDATE"),
            {"id": ids[_CONTENDED]},
        )
        stats: dict = {}
        try:
            await _run_pass(maker, monkeypatch, espn, stats)
        finally:
            await holder_tx.rollback()
            await holder.close()

        # The order the test is built on actually held.
        assert espn.asked == [ids[name] for name in _ORDER], espn.asked

        boxes = await _boxes(maker, ids)
        assert boxes[_CONTENDED] is None, "the failed write landed anyway"
        lost = [n for n, b in boxes.items() if n != _CONTENDED and not (b or {}).get("live")]
        assert lost == [], (
            f"one game's failed write discarded its siblings' box scores: {lost}",
            stats,
        )
        assert stats.get("live_box_scores_fetched") == 3, stats
        assert "errors" not in stats, stats["errors"]

    async def test_an_uncontended_pass_writes_every_game(self, db, monkeypatch):
        """THE KILL CONTROL. A savepoint that rolled back healthy writes would
        leave the siblings empty here with no lock held."""
        _, maker, ids = db
        espn = _Espn(await _stagger(maker, ids))

        stats: dict = {}
        await _run_pass(maker, monkeypatch, espn, stats)

        boxes = await _boxes(maker, ids)
        assert [bool((b or {}).get("live")) for b in boxes.values()] == [True] * 4, boxes
        assert stats.get("live_box_scores_fetched") == 4, stats
        assert "errors" not in stats, stats["errors"]
