"""Execute exact-event ingest through normal SQL construction with bounded fakes."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.kalshi_api import KalshiAPIService
from app.tasks import kalshi
from app.tasks import redis_state


@pytest.mark.asyncio
async def test_exact_contract_upserts_both_legs_without_global_work(monkeypatch):
    ticker = "KXEUROLEAGUEGAME-26OCT081200CZVDUB"
    provider_calls, sql, commits = [], [], []
    payload = {
        "event_ticker": ticker,
        "title": "KK Crvena zvezda Belgrade vs Dubai Basketball",
        "category": "Sports",
        "mutually_exclusive": True,
        "markets": [
            {
                "ticker": f"{ticker}-{code}", "event_ticker": ticker,
                "title": f"{name} wins", "yes_sub_title": name,
                "status": "active", "yes_bid_dollars": "0.49",
                "yes_ask_dollars": "0.51", "last_price_dollars": "0.50",
                "close_time": "2026-10-10T16:00:00Z",
                "expected_expiration_time": "2026-10-08T19:00:00Z",
            }
            for code, name in [("DUB", "Dubai Basketball"),
                               ("CZV", "KK Crvena zvezda Belgrade")]
        ],
    }

    async def get_event(self, event_ticker, with_nested_markets=True):
        provider_calls.append((event_ticker, with_nested_markets))
        return payload

    async def forbidden(*args, **kwargs):
        raise AssertionError("Exact ingest reached global provider/maintenance work")

    class Session:
        async def execute(self, stmt, params=None):
            compiled = stmt.compile(dialect=postgresql.dialect())
            sql.append((str(compiled), compiled.params))
            return SimpleNamespace(scalar_one=lambda: 7, rowcount=1)

        async def begin_nested(self):
            return SimpleNamespace(commit=self.commit, rollback=self.rollback)

        async def commit(self):
            commits.append(True)

        async def rollback(self):
            pass

    @asynccontextmanager
    async def session_scope(**kwargs):
        yield Session()

    monkeypatch.setenv("KALSHI_API_KEY", "source-proof-only")
    monkeypatch.setattr(KalshiAPIService, "get_event", get_event)
    monkeypatch.setattr(KalshiAPIService, "get_all_events", forbidden)
    monkeypatch.setattr(kalshi, "get_task_session", session_scope)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda **kwargs: None)
    for name in ("_fix_golf_commence_times", "_fix_golf_round_leader_dates",
                 "_fix_hockey_commence_times", "_fix_tennis_commence_times",
                 "_refine_stand_in_event_starts"):
        monkeypatch.setattr(kalshi, name, forbidden)

    result = await kalshi._poll_kalshi_markets(event_ticker=ticker)
    assert result["errors"] == []
    assert result["selection"] == "exact_event"
    assert result["events_processed"] == 1
    assert result["outcomes_updated"] == 2
    assert result["snapshots_created"] == 2
    assert provider_calls == [(ticker, True)]
    assert commits
    assert not any(s.lstrip().startswith(("SELECT", "DELETE")) for s, _ in sql)
    market_params = next(p for s, p in sql if s.startswith("INSERT INTO futures_markets"))
    assert market_params["external_id"] == ticker
    outcome_params = [p for s, p in sql if s.startswith("INSERT INTO futures_outcomes")]
    assert {p["external_id"] for p in outcome_params} == {f"{ticker}-DUB", f"{ticker}-CZV"}

    # A provider response for a different event fails before a DB write.
    writes_before = len(sql)
    payload["event_ticker"] = "KXEUROLEAGUEGAME-26OCT071200CZVDUB"
    failed = await kalshi._poll_kalshi_markets(event_ticker=ticker)
    assert failed["errors"]
    assert len(sql) == writes_before
    for invalid in ("KXEUROLEAGUEGAME", ticker + "-DUB", "KXEUROLEAGUEGAME-*"):
        with pytest.raises(ValueError):
            kalshi._validate_exact_kalshi_game_event_ticker(invalid)
