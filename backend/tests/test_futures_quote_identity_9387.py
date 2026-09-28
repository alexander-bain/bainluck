"""Current source identity survives the real parser and poll writer (#9387)."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.services.odds_api import OddsAPIService
from app.utils.futures_quote_identity import current_quote_identity

SPORT = "americanfootball_nfl_super_bowl_winner"
STAMP = datetime(2026, 9, 28, 16, tzinfo=timezone.utc)


def payload(event_id="270f600435a20d2046a59fc89fe8e9b8", commence="2027-02-14T23:35:00Z"):
    return [{"id": event_id, "commence_time": commence, "sport_title": "NFL Super Bowl Winner",
             "bookmakers": [{"key": "draftkings", "markets": [{"key": "outrights", "outcomes": [
                 {"name": "Buffalo Bills", "price": 800}, {"name": "Other team", "price": -900},
             ]}]}]}]


def parsed(response):
    return OddsAPIService._parse_futures(None, response, SPORT)


def test_real_parser_retains_provider_identity_without_changing_prices():
    books = parsed(payload())
    identity = current_quote_identity(books, SPORT, STAMP)
    assert identity == {
        "event_id": "270f600435a20d2046a59fc89fe8e9b8",
        "commence_time": "2027-02-14T23:35:00+00:00", "sport_key": SPORT,
        "polled_at": STAMP.isoformat(), "scope": "current_quotes_only",
    }
    assert books[0].outcomes[0].probability == pytest.approx(1 / 9)


@pytest.mark.parametrize("event_id,commence", [
    (None, "2027-02-14T23:35:00Z"), ("", "2027-02-14T23:35:00Z"),
    (1, "2027-02-14T23:35:00Z"), ("event", None), ("event", 2027),
    ("event", "bad date"), ("event", "2027-02-14T23:35:00"),
])
def test_missing_invalid_or_naive_anchor_is_unknown_but_quotes_survive(event_id, commence):
    books = parsed(payload(event_id, commence))
    assert books[0].outcomes[0].probability == pytest.approx(1 / 9)
    assert current_quote_identity(books, SPORT, STAMP) is None


def test_mixed_provider_events_or_dates_cannot_claim_single_edition():
    first = parsed(payload())
    assert current_quote_identity(first + parsed(payload("different")), SPORT, STAMP) is None
    assert current_quote_identity(first + parsed(payload(commence="2028-02-14T23:35:00Z")), SPORT, STAMP) is None
    assert current_quote_identity(first, "basketball_nba_championship", STAMP) is None
    assert current_quote_identity([], SPORT, STAMP) is None


def test_same_instant_across_books_and_new_edition_are_provider_derived():
    books = parsed(payload()) + parsed(payload(commence="2027-02-14T18:35:00-05:00"))
    assert current_quote_identity(books, SPORT, STAMP)["commence_time"] == "2027-02-14T23:35:00+00:00"
    new = current_quote_identity(parsed(payload("next", "2028-02-13T23:30:00Z")), SPORT, STAMP)
    assert new["event_id"] == "next"
    assert new["commence_time"].startswith("2028-")  # never derived from poll year


@pytest.mark.asyncio
@pytest.mark.parametrize("response,expected_id", [(payload(), "270f600435a20d2046a59fc89fe8e9b8"), (payload(None), None)])
async def test_real_poll_upsert_carries_or_clears_current_anchor(response, expected_id):
    """Drive the real task to its SQL boundary, no database or network involved."""
    from app.tasks.futures import _poll_futures_odds

    statements = []

    async def execute(stmt):
        statements.append(stmt)
        return SimpleNamespace(all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []), scalar_one=lambda: 9387)

    session = SimpleNamespace(execute=execute, commit=AsyncMock())

    @asynccontextmanager
    async def session_cm():
        yield session

    service = SimpleNamespace(
        get_sports_with_outrights=AsyncMock(return_value=[{"key": SPORT}]),
        get_futures_odds=AsyncMock(return_value=response),
        _parse_futures=lambda response, sport: parsed(response),
        last_requests_used=1, last_requests_remaining=None, close=AsyncMock(),
    )
    with patch("app.tasks.futures.OddsAPIService", return_value=service), \
         patch("app.tasks.futures.get_task_session", session_cm), \
         patch("app.tasks.redis_state.check_quota_guard", return_value=(True, "test")):
        result = await _poll_futures_odds()
    assert result["errors"] == []
    assert result["markets_processed"] == 1
    assert result["outcomes_updated"] == 2
    upsert = next(s for s in statements if getattr(s, "is_insert", False) and s.table.name == "futures_markets")
    compiled = upsert.compile(dialect=postgresql.dialect())
    metadata_values = [value for value in compiled.params.values()
                       if isinstance(value, dict) and "odds_api_current_event" in value]
    assert len(metadata_values) == 2  # both INSERT and conflict UPDATE
    assert metadata_values[0] == metadata_values[1]
    identity = metadata_values[0]["odds_api_current_event"]
    if expected_id is None:
        assert identity is None  # overwrite old identity with unknown, not stale carry
    else:
        assert identity["event_id"] == expected_id
        assert identity["scope"] == "current_quotes_only"
    assert "coalesce(futures_markets.market_metadata" in str(compiled)
    assert "||" in str(compiled)  # other metadata survives the scoped key replacement
    assert "canonical_market_key" not in (identity or {})
    assert "resolution_date =" not in str(compiled)
