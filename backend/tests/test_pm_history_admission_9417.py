"""#9417 — the Phase 3 history backfill writes only what the blend may hear.

``_backfill_polymarket_win_prob_history`` runs for every newly linked Polymarket
market and used to ask no admission rule, so a ``Halftime Result`` book's
history landed in ``win_prob_snapshots`` as the match line (Braga v Sporting,
0.225 between match prices of 0.27), and a ``Completed Match`` novelty's "Yes"
would have too. It now asks ``admissible_as_blend_speaker`` — the rule the live
poll and the matcher ask — before fetching anything.

Both directions: the derivative writes nothing, the real match market still
writes its full history (a gate that refuses everything passes the first test).
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.models import Event, FuturesMarket
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import prediction_market_matching as matching

MONEYLINE_LABEL = {"content_understanding_v1": {
    "v": 1, "venue_type": "moneyline", "semantic_type": "moneyline",
}}
NOVELTY_LABEL = {"content_understanding_v1": {
    "v": 1, "venue_type": "tennis_completed_match", "semantic_type": "moneyline",
}}


async def run_backfill(monkeypatch, *, name, outcomes, home, away, metadata):
    rows = [
        SimpleNamespace(name=n, current_probability=0.5, external_id=f"cond-{i}")
        for i, n in enumerate(outcomes)
    ]
    market = SimpleNamespace(
        id=62583723, source="polymarket", name=name, external_id="1016059",
        status="open", market_metadata=metadata,
    )
    event = SimpleNamespace(
        id=15317139, home_team_name=home, away_team_name=away,
        opening_home_probability=None, win_probability_sources={},
    )
    written = []

    class Session:
        async def get(self, model, key):
            return market if model is FuturesMarket else event if model is Event else None

        async def execute(self, statement):
            if "futures_outcomes" in str(statement):
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def add(self, row):
            written.append(row)

        async def commit(self):
            pass

    @asynccontextmanager
    async def session():
        yield Session()

    fetch = AsyncMock(return_value={"markets": [
        {"conditionId": r.external_id, "clobTokenIds": [f"tok-{i}", f"no-{i}"]}
        for i, r in enumerate(rows)
    ]})
    history = AsyncMock(return_value=[
        {"t": 1780000000 + i * 1800, "p": p} for i, p in enumerate((0.22, 0.225, 0.23))
    ])
    monkeypatch.setattr(matching, "get_task_session", session)
    monkeypatch.setattr(PolymarketAPIService, "get_event_by_id", fetch)
    monkeypatch.setattr(PolymarketAPIService, "get_prices_history", history)
    monkeypatch.setattr(PolymarketAPIService, "close", AsyncMock())
    stats = await matching._backfill_polymarket_win_prob_history(market.id, event.id)
    return stats, written, fetch


@pytest.mark.asyncio
async def test_a_halftime_result_book_writes_no_history_9417(monkeypatch):
    stats, rows, fetch = await run_backfill(
        monkeypatch,
        name="SC Braga vs. Sporting CP - Halftime Result",
        outcomes=["SC Braga", "Draw", "Sporting CP"],
        home="SC Braga", away="Sporting CP", metadata=None,
    )
    assert rows == []
    assert stats["snapshots_created"] == 0
    assert stats["errors"] == ["not admissible as a blend speaker"]
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_completed_match_novelty_writes_no_history_9417(monkeypatch):
    # The title recognizer ADMITS this name (it reads "Completed Match" as a
    # competition prefix); only the venue label refutes it — #9348's clause.
    stats, rows, fetch = await run_backfill(
        monkeypatch,
        name="Jingshan: Completed Match: Amelia Rajecki vs Yuhan Wang",
        outcomes=["Yes", "No"],
        home="Amelia Rajecki", away="Yuhan Wang", metadata=NOVELTY_LABEL,
    )
    assert rows == []
    assert stats["errors"] == ["not admissible as a blend speaker"]
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [MONEYLINE_LABEL, None])
async def test_the_real_match_market_still_writes_its_history_9417(monkeypatch, metadata):
    stats, rows, _ = await run_backfill(
        monkeypatch,
        name="SC Braga vs. Sporting CP",
        outcomes=["SC Braga", "Draw", "Sporting CP"],
        home="SC Braga", away="Sporting CP", metadata=metadata,
    )
    assert stats == {"snapshots_created": 3, "errors": []}
    assert [r.home_win_probability for r in rows] == [0.22, 0.225, 0.23]
