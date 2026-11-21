"""The Other Soccer reader gets a small page from its existing game window."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("league_page", "offset", "expected_next"),
    [(True, 0, 50), (True, 150, None), (False, 0, None)],
)
async def test_league_window_is_paged_before_enrichment(
    monkeypatch, league_page, offset, expected_next
):
    # All 50 fetched rows are suppressed by a later identity check. The next
    # request still needs to advance by the raw page size.
    rows = [SimpleNamespace(id=event_id) for event_id in range(50)]
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    reader_order = Mock(wraps=events.live_scheduled_settled_order)
    monkeypatch.setattr(events, "live_scheduled_settled_order", reader_order)
    monkeypatch.setattr(events, "recover_kalshi_expiration_starts", AsyncMock())
    monkeypatch.setattr(
        events, "fold_twin_events", lambda _: SimpleNamespace(dropped_ids=())
    )
    monkeypatch.setattr(
        events, "market_born_duplicates_on_page",
        AsyncMock(return_value={row.id for row in rows}),
    )
    for helper in (
        "same_instant_refuted_on_page", "_load_gei_percentiles", "_build_team_lookup",
        "folded_card_numbers_batch", "attach_venue_settlement",
        "attach_settled_prematch_odds", "read_pregame_projections",
    ):
        monkeypatch.setattr(events, helper, AsyncMock(return_value={}))

    response = await events.list_events(
        sport="soccer_other", status=None, days=14, past_days=1, limit=200,
        offset=offset, db=db, league_page=league_page,
    )
    (query,) = db.execute.await_args.args
    sql = str(query.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "sports.key = 'soccer_other'" in sql
    assert response["count"] == 0
    if league_page:
        assert "LIMIT 200" in sql and f"LIMIT 50 OFFSET {offset}" in sql
        reader_order.assert_called_once()
        assert "ORDER BY CASE WHEN" in sql
        assert response["next_offset"] == expected_next
    else:
        reader_order.assert_not_called()
        assert "ORDER BY events.commence_time" in sql
        assert "LIMIT 50" not in sql
        assert "next_offset" not in response
