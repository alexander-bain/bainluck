"""One box Postgres refuses does not discard the settled box-score pass. #9713, real Postgres.

``fetch_completed_box_scores`` wrote every finished game's box inside the ESPN
pass's one transaction and swallowed a per-game failure. On Postgres a refused
statement aborts the transaction, so every later game raised and the step's
savepoint (#8796) rolled back the games already written. Production, 9/30:
Red Sox at Yankees (15319563) carried an ERA of ``INF``, Postgres refused its box
as invalid JSON, and as the newest finished game it sat at the head of the
48-hour queue. Every run logged ``box_score_pass: InFailedSQLTransactionError``
and settled nothing. The live pass has had the per-game savepoint since #8913;
this pass did not.

The parser now drops non-finite stats (unit file ``…_9713.py``), so this file
feeds the refusal directly: the first game's box carries ``inf`` and Postgres
refuses it the real way.

* ship: the games before and after the refused one land their settled boxes.
  RED on the parent (all three siblings lost);
* kill control: with no refusal, every game lands its box. A savepoint that
  rolled back healthy writes would leave the siblings empty here too.

Reuses the #8796 file's database and fixture. Runs where
``DELAY_CONTRACT_DATABASE_URL`` is set (CI job ``database-integration``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import null, select, update

from tests.integration.test_espn_pass_survives_one_failed_statement_pg_8796 import (  # noqa: F401 — `db` is the fixture
    db,
    needs_postgres,
)

pytestmark = [pytest.mark.asyncio]

#: The pass reads newest kickoff first; staggered kickoffs pin that order so the
#: refused game has a sibling on each side.
_ORDER = (
    "the_stat_model_row",
    "a_sibling_the_pass_also_writes",
    "the_failing_sports_row",
    "the_next_sports_row",
)
_REFUSED = "a_sibling_the_pass_also_writes"


class _Espn:
    def __init__(self, espn_to_id, refused_id=None):
        self._ids = espn_to_id
        self._refused = refused_id
        self.asked: list = []

    async def get_event_context(self, sport_key, espn_id):
        event_id = self._ids[espn_id]
        self.asked.append(event_id)
        era = float("inf") if event_id == self._refused else 4.5
        return {
            "box_score": {"Pitcher": {"era": era, "earned runs": 2.0}},
            "scoring_plays": [],
            "scores": {"home_period_scores": [0, 1], "away_period_scores": [0, 0]},
        }

    async def close(self):
        pass


async def _finish_and_stagger(maker, ids):
    from app.models.models import Event

    now = datetime.now(timezone.utc)
    async with maker() as session:
        for i, name in enumerate(_ORDER):
            await session.execute(
                update(Event)
                .where(Event.id == ids[name])
                .values(
                    status="completed",
                    completed_at=now - timedelta(minutes=5),
                    commence_time=now - timedelta(hours=3, minutes=10 * i),
                    # SQL NULL, as production stores "no box" (JSONB would
                    # store a bare None as the JSON value `null`).
                    box_score_data=null(),
                )
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
    from app.utils.espn_helpers import fetch_completed_box_scores

    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)
    async with maker() as session:
        try:
            async with _step_savepoint(session):
                await fetch_completed_box_scores(session, stats)
        except Exception as e:  # the task's own handler
            stats.setdefault("errors", []).append(f"box_score_pass: {e}")
        await session.commit()


@needs_postgres
class TestOneRefusedBoxCostsOnlyThatGame:
    async def test_the_siblings_keep_their_settled_boxes(self, db, monkeypatch):
        """THE SHIP. RED before #9713: Postgres refused the `Infinity` box,
        the games after it raised InFailedSQLTransactionError, and the step's
        savepoint rolled back the game written before it too."""
        _, maker, ids = db
        espn_to_id = await _finish_and_stagger(maker, ids)
        espn = _Espn(espn_to_id, refused_id=ids[_REFUSED])

        stats: dict = {}
        await _run_pass(maker, monkeypatch, espn, stats)

        # The order the test is built on actually held.
        assert espn.asked == [ids[name] for name in _ORDER], espn.asked

        boxes = await _boxes(maker, ids)
        assert boxes[_REFUSED] is None, "the refused box landed anyway"
        lost = [
            n for n, b in boxes.items()
            if n != _REFUSED and (b or {}).get("home_period_scores") != [0, 1]
        ]
        assert lost == [], (
            f"one refused box discarded its siblings' settled boxes: {lost}",
            stats,
        )
        assert stats.get("box_scores_fetched") == 3, stats
        assert "errors" not in stats, stats["errors"]

    async def test_a_clean_pass_writes_every_game(self, db, monkeypatch):
        """THE KILL CONTROL."""
        _, maker, ids = db
        espn = _Espn(await _finish_and_stagger(maker, ids))

        stats: dict = {}
        await _run_pass(maker, monkeypatch, espn, stats)

        boxes = await _boxes(maker, ids)
        assert [(b or {}).get("home_period_scores") for b in boxes.values()] == [[0, 1]] * 4, boxes
        assert stats.get("box_scores_fetched") == 4, stats
        assert "errors" not in stats, stats["errors"]
