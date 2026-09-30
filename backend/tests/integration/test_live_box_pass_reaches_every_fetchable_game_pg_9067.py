"""The live box-score pass spends its 10 slots on games it will fetch. #9067, real Postgres.

``fetch_live_box_scores`` took 10 live ESPN-linked rows, ordered by
``box_score_data->>'fetched_at'`` nulls first, and then its loop skipped every
row it would not fetch: a sport with no ``ESPN_SPORT_MAPPING`` path, or a box
that is not a live box. Nothing was written to a skipped row, so it held its
slot for good. Measured on production 9/30 03:23Z: 29 of 32 live ESPN-linked
rows were tennis (10 carrying only the tennis anchor's ``{"tennis": ...}``
line, which has no ``fetched_at`` and sorts first; 19 with no box at all), and
the other three were never reached. Red Sox at Yankees (15319563) kept its
01:59Z line score, NYY 2, until it finished 9–0 at 03:18Z (rage shake #165).

The defect is the ORDER BY + LIMIT against the JSONB column, so this file runs
the pass's own query on the real database:

* ship: a stale MLB box behind twelve tennis rows and a non-live NHL box is
  refreshed. RED before #9067 (ESPN was asked about nothing);
* control: a box fetched 30 s ago is still not re-asked. The 2-minute rule is
  unchanged, and a filter that dropped the staleness clause would fail here.

Reuses the #8796 file's database and fixture. Runs where
``DELAY_CONTRACT_DATABASE_URL`` is set (CI job ``database-integration``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text, update

from tests.integration.test_espn_pass_survives_one_failed_statement_pg_8796 import (  # noqa: F401 — `db` is the fixture
    db,
    needs_postgres,
)

pytestmark = [pytest.mark.asyncio]

_THE_GAME = "the_failing_sports_row"  # the fixture's MLB row
_NOT_LIVE_BOX = "the_next_sports_row"  # an NHL row whose box is no longer live


class _Espn:
    def __init__(self):
        self.asked: list = []

    async def get_event_context(self, sport_key, espn_id):
        self.asked.append(espn_id)
        return {
            "box_score": {"P": {"h": 1}},
            "scoring_plays": [],
            "scores": {"home_period_scores": [0, 1, 0, 0, 1, 0, 3, 4],
                       "away_period_scores": [0] * 8},
        }

    async def close(self):
        pass


async def _set_box(session, event_id, box):
    from app.models.models import Event

    await session.execute(
        update(Event).where(Event.id == event_id).values(box_score_data=box)
    )


async def _live_box(fetched_ago: timedelta) -> dict:
    fetched = datetime.now(timezone.utc) - fetched_ago
    return {
        "source": "espn",
        "fetched_at": fetched.isoformat(),
        "players": {},
        "scoring_plays": [],
        "home_period_scores": [0, 1, 0, 0, 1],
        "away_period_scores": [0, 0, 0, 0, 0],
        "live": True,
    }


async def _slate(maker, ids, the_games_box: dict) -> str:
    """Twelve live tennis rows, a non-live NHL box, and the MLB game under test."""
    from app.models.models import Event, Sport

    now = datetime.now(timezone.utc)
    async with maker() as session:
        tennis = Sport(key="tennis_atp", name="ATP")
        session.add(tennis)
        await session.flush()
        for i in range(12):
            session.add(
                Event(
                    sport_id=tennis.id,
                    home_team_name=f"Player H{i}",
                    away_team_name=f"Player A{i}",
                    # Newer than every sports row, so kickoff breaks no tie
                    # in the game's favour.
                    commence_time=now - timedelta(minutes=5),
                    commence_time_source="espn",
                    status="live",
                    espn_id=f"9067-t{i}",
                    win_probability_sources={},
                    # Half carry the ESPN tennis anchor's line (no top-level
                    # `fetched_at`), half carry nothing: the two shapes seen.
                    box_score_data=(
                        {"tennis": {"sets": [[1, 0]], "source": "espn"}}
                        if i % 2 == 0
                        else None
                    ),
                )
            )
        await _set_box(session, ids[_THE_GAME], the_games_box)
        not_live = await _live_box(timedelta(hours=3))
        not_live["live"] = False
        await _set_box(session, ids[_NOT_LIVE_BOX], not_live)
        # The other two NHL rows were just fetched and are not due.
        for name in ("the_stat_model_row", "a_sibling_the_pass_also_writes"):
            await _set_box(session, ids[name], await _live_box(timedelta(seconds=10)))
        espn_id = (
            await session.execute(select(Event.espn_id).where(Event.id == ids[_THE_GAME]))
        ).scalar_one()
        await session.commit()
    return espn_id


async def _run_pass(maker, monkeypatch, espn):
    import app.services.espn_api as espn_api
    from app.utils.espn_helpers import fetch_live_box_scores

    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)
    stats: dict = {}
    async with maker() as session:
        await fetch_live_box_scores(session, stats)
        await session.commit()
    return stats


async def _the_games_box(maker, ids):
    async with maker() as session:
        raw = (
            await session.execute(
                text("SELECT box_score_data::text FROM events WHERE id = :id"),
                {"id": ids[_THE_GAME]},
            )
        ).scalar_one()
    return json.loads(raw)


@needs_postgres
class TestTheLiveBoxPassReachesEveryFetchableGame:
    async def test_a_stale_game_behind_tennis_rows_is_refreshed(self, db, monkeypatch):
        """THE SHIP. RED before #9067: the twelve tennis rows took all ten
        slots, the loop skipped them, and ESPN was asked about nothing."""
        _, maker, ids = db
        espn_id = await _slate(maker, ids, await _live_box(timedelta(minutes=80)))
        espn = _Espn()

        stats = await _run_pass(maker, monkeypatch, espn)

        assert espn.asked == [espn_id], (
            "the pass asked ESPN about the wrong rows, or none",
            espn.asked,
            stats,
        )
        box = await _the_games_box(maker, ids)
        assert box["home_period_scores"] == [0, 1, 0, 0, 1, 0, 3, 4], box
        assert box["live"] is True
        assert stats.get("live_box_scores_fetched") == 1, stats

    async def test_a_box_fetched_seconds_ago_is_not_asked_again(self, db, monkeypatch):
        """THE CONTROL. A rewrite that dropped the staleness clause would ask
        ESPN about the game every minute; the 2-minute rule stands."""
        _, maker, ids = db
        await _slate(maker, ids, await _live_box(timedelta(seconds=30)))
        espn = _Espn()

        stats = await _run_pass(maker, monkeypatch, espn)

        assert espn.asked == [], (espn.asked, stats)
        assert (await _the_games_box(maker, ids))["home_period_scores"] == [0, 1, 0, 0, 1]
