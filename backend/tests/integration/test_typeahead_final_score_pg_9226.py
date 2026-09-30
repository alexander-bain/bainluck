"""#9226 — the dropdown's finished row carries its result.

THE DEFECT, production 2026-09-27 22:52Z, the #9211 after-check LOOK at 390 px:
`chiefs` offered *Kansas City Chiefs at Miami Dolphins · Final* with no score. The
payload row was `{type, text, event_id, status: completed, sport_key,
commence_time, logos}`, so no client could print 24–10.

THE TARGET: today's final carries `home_score`/`away_score` exactly as stored.
THE STRAWMAN swaps the rule for one that returns nothing: the row is production's
bare `Final` again, so the target case testifies.
THE CONTROLS: the next game (scheduled) and a live game carry no score keys at all.

Reuses #9211's seed and fixture. The finished row only exists because that arm
fetched it, and a session double sees neither the arm nor the pool cut.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_final_score_pg_9226.py -v
"""

from __future__ import annotations

import os

import pytest

from tests.integration.test_typeahead_todays_final_pg_9211 import (  # noqa: F401
    NEXT,
    RED_SOX_GAME_1,
    RED_SOX_LIVE,
    TODAYS_FINAL,
    typeahead,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9226 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]


def _row(body: dict, text: str) -> dict:
    rows = [r for r in body["suggestions"] if r.get("text") == text]
    assert rows, f"{text!r} not offered: {[r.get('text') for r in body['suggestions']]}"
    return rows[0]


async def test_todays_final_carries_its_result(typeahead):
    """The production specimen: Chiefs 24, Dolphins 10 (Miami at home)."""
    final = _row(await typeahead("chiefs"), TODAYS_FINAL)
    assert final["status"] == "completed", final
    assert (final.get("home_score"), final.get("away_score")) == (10, 24), final


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """With the rule returning nothing, the row is production's bare `Final`."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_typeahead_final_score", lambda *a: {})
    final = _row(await typeahead("chiefs"), TODAYS_FINAL)
    assert final["status"] == "completed", final
    assert "home_score" not in final and "away_score" not in final, final


async def test_the_next_game_carries_no_score(typeahead):
    nxt = _row(await typeahead("chiefs"), NEXT)
    assert nxt["status"] == "scheduled", nxt
    assert "home_score" not in nxt and "away_score" not in nxt, nxt


async def test_a_live_game_carries_no_score_and_game_one_carries_its_result(typeahead):
    """The doubleheader: game 2 is being played, game 1 finished 3–2 this afternoon."""
    body = await typeahead("red sox")
    live = _row(body, RED_SOX_LIVE)
    assert live["status"] == "live", live
    assert "home_score" not in live and "away_score" not in live, live
    game_1 = _row(body, RED_SOX_GAME_1)
    assert (game_1.get("home_score"), game_1.get("away_score")) == (3, 2), game_1
