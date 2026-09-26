"""The actual Phase 3 writer must not reorient named history using today's odds."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.models import Event, FuturesMarket
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import prediction_market_matching as matching


async def run_backfill(
    monkeypatch, names, *, consensus=0.70, prices=(0.30, 0.335, 0.40)
):
    outcomes = [
        SimpleNamespace(
            name=name, current_probability=price, external_id=f"condition-{i}"
        )
        for i, (name, price) in enumerate(names)
    ]
    market = SimpleNamespace(
        id=60933567,
        source="polymarket",
        name="Bulgaria vs. Luxembourg",
        external_id="1016059",
    )
    event = SimpleNamespace(
        id=15290678,
        home_team_name="Bulgaria",
        away_team_name="Luxembourg",
        opening_home_probability=None,
        win_probability_sources={},
    )
    written = []
    book_reads = []

    class Session:
        async def get(self, model, key):
            return (
                market if model is FuturesMarket else event if model is Event else None
            )

        async def execute(self, statement):
            if "futures_outcomes" in str(statement):
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: outcomes)
                )
            book_reads.append(statement)
            return SimpleNamespace(scalar_one_or_none=lambda: consensus)

        def add(self, row):
            written.append(row)

        async def commit(self):
            pass

    @asynccontextmanager
    async def session():
        yield Session()

    monkeypatch.setattr(matching, "get_task_session", session)
    monkeypatch.setattr(
        PolymarketAPIService,
        "get_event_by_id",
        AsyncMock(
            return_value={
                "markets": [
                    {
                        "conditionId": outcome.external_id,
                        "clobTokenIds": [f"token-{i}", f"no-{i}"],
                    }
                    for i, outcome in enumerate(outcomes)
                ]
            }
        ),
    )
    history = AsyncMock(
        return_value=[
            {"t": 1780000000 + i * 1800, "p": price} for i, price in enumerate(prices)
        ]
    )
    monkeypatch.setattr(PolymarketAPIService, "get_prices_history", history)
    monkeypatch.setattr(PolymarketAPIService, "close", AsyncMock())
    stats = await matching._backfill_polymarket_win_prob_history(market.id, event.id)
    return stats, written, book_reads, history


@pytest.mark.asyncio
async def test_ce6_actual_writer_keeps_entire_named_home_history(monkeypatch):
    stats, rows, book_reads, history = await run_backfill(
        monkeypatch,
        [
            ("Draw (Bulgaria vs. Luxembourg)", 0.42),
            ("Bulgaria", 0.335),
            ("Luxembourg", 0.255),
        ],
    )
    assert stats == {"snapshots_created": 3, "errors": []}
    assert [row.home_win_probability for row in rows] == [0.30, 0.335, 0.40]
    assert [int(row.captured_at.timestamp()) for row in rows] == [
        1780000000,
        1780001800,
        1780003600,
    ]
    assert history.await_args.kwargs["token_id"] == "token-1"
    assert not book_reads


@pytest.mark.asyncio
async def test_named_away_binary_is_complemented_exactly_once(monkeypatch):
    _, rows, book_reads, _ = await run_backfill(
        monkeypatch, [("Luxembourg", 0.335)], consensus=0.30
    )
    assert [row.home_win_probability for row in rows] == [0.70, 0.665, 0.60]
    assert [row.away_win_probability for row in rows] == [0.30, 0.335, 0.40]
    assert not book_reads


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "names",
    [
        [("Yes", 0.335), ("No", 0.665)],
        [("Bulgaria vs. Luxembourg", 0.335)],
        [("Bulgaria", 0.335), ("Bulgaria", 0.30)],
    ],
)
async def test_unproven_identity_retains_legacy_inversion_guard(monkeypatch, names):
    _, rows, book_reads, _ = await run_backfill(monkeypatch, names)
    assert [row.home_win_probability for row in rows] == [0.70, 0.665, 0.60]
    assert len(book_reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra", [("Bulgaria -1.5", 0.2), ("Bulgaria", 1.0), ("Bulgaria", None)]
)
async def test_resolver_rejected_siblings_cannot_withdraw_named_identity(
    monkeypatch, extra
):
    _, rows, book_reads, _ = await run_backfill(
        monkeypatch, [("Bulgaria", 0.335), extra]
    )
    assert [row.home_win_probability for row in rows] == [0.30, 0.335, 0.40]
    assert not book_reads
