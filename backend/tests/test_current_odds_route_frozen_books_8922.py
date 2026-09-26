"""#8922 follow-up `8922-SERVED-ROUTE-CONTRACT-GUARD` (CERT-3583).

`test_stale_bookmaker_filter.py` proves the filter and the aggregate. This
proves the SERVED payload: `GET /api/events/{id}` → `current_odds` on a live
blowout whose live books have all pulled the moneyline, beside books frozen at
kickoff that still carry one. If a later edit re-wires the route around the
filter (or restores a moneyline-only probe inside it), the reader-visible
numbers move and this file says so.

Specimen: production 2026-09-26 20:30Z, /events/15315949 (Notre Dame 35–3
Purdue, end of Q3). `current_odds` served spread 36.5 / total 54.2, the mean of
seven live books (ND −40.5…−43.5, 52.5) and four pre-game ones (ND −27, 57),
and the margin map printed `PROJECTION ND by 36.1+` under `Projected final:
6 – 47`. Trimmed here to two live books and two frozen ones, which is enough to
separate the two answers.

Reuses #7221's detail-route harness (a mocked session behind the real route).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.test_current_odds_serves_the_books_7221 import (
    EVENT_ID,
    _detail_event,
    _detail_session,
    _offset,
)

KICKOFF_HOURS_AGO = 2.5


def _book(
    bookmaker: str,
    *,
    live: bool,
    home_spread: float,
    over_under: float,
    home_prob: float | None,
) -> MagicMock:
    snap = MagicMock()
    snap.bookmaker = bookmaker
    snap.home_win_probability = home_prob
    snap.away_win_probability = round(1.0 - home_prob, 4) if home_prob is not None else None
    if live:
        snap.captured_at = _offset(-0.05)
        snap.valid_until = _offset(-0.01)
    else:
        # last confirmed 24 minutes before kickoff, never again
        snap.captured_at = _offset(-KICKOFF_HOURS_AGO - 0.4)
        snap.valid_until = _offset(-KICKOFF_HOURS_AGO - 0.4)
    snap.home_moneyline = 1592 if home_prob is not None else None
    snap.away_moneyline = -6000 if home_prob is not None else None
    snap.home_spread = home_spread
    snap.over_under = over_under
    # consistent with the spread/total, like the real rows
    snap.projected_home_score = round((over_under - home_spread) / 2, 1)
    snap.projected_away_score = round((over_under + home_spread) / 2, 1)
    return snap


SNAPSHOTS = [
    _book("draftkings", live=True, home_spread=41.5, over_under=52.5, home_prob=None),
    _book("fanduel", live=True, home_spread=42.5, over_under=52.5, home_prob=None),
    _book("betrivers", live=False, home_spread=27.5, over_under=57.5, home_prob=0.0561),
    _book("lowvig", live=False, home_spread=27.0, over_under=57.0, home_prob=0.0567),
]


def _blowout_event():
    event = _detail_event(bag={"betting_book_count": 2})
    event.commence_time = _offset(-KICKOFF_HOURS_AGO)
    event.home_score = 3
    event.away_score = 35
    return event


@pytest.fixture
async def blowout_client():
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    _game_markets_cache.clear()
    _event_detail_cache.clear()
    session = _detail_session(_blowout_event(), SNAPSHOTS)

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            yield ac
        finally:
            await ac.aclose()
            _game_markets_cache.clear()
            _event_detail_cache.clear()
            app.dependency_overrides.clear()


class TestTheServedBlowout:
    async def test_current_odds_is_the_live_books_not_the_pregame_mean(self, blowout_client):
        resp = await blowout_client.get(f"/api/events/{EVENT_ID}")
        assert resp.status_code == 200
        current = resp.json()["current_odds"]
        # live books only: (41.5 + 42.5) / 2, 52.5 — not the four-book 34.6 / 54.9
        assert current["spread"] == 42.0
        assert current["over_under"] == 52.5

    async def test_the_frozen_moneyline_is_not_served_as_the_consensus(self, blowout_client):
        """No live book prices the winner; the frozen 5.6% must not stand in."""
        current = (await blowout_client.get(f"/api/events/{EVENT_ID}")).json()["current_odds"]
        assert current["home_probability"] not in (0.0561, 0.0564, 0.0567)

    async def test_the_table_still_lists_every_book(self, blowout_client):
        """The filter scopes the consensus, never the per-book table."""
        payload = (await blowout_client.get(f"/api/events/{EVENT_ID}")).json()
        assert sorted(b["bookmaker"] for b in payload["bookmaker_odds"]) == [
            "betrivers", "draftkings", "fanduel", "lowvig",
        ]

    def test_strawman_the_four_book_mean_is_what_production_served_in_kind(self):
        """Control: the unfiltered mean of these rows is the defect's number."""
        spreads = [s.home_spread for s in SNAPSHOTS]
        assert round(sum(spreads) / len(spreads), 1) == 34.6
