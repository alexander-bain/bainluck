from datetime import datetime, timezone
from types import SimpleNamespace

from app.utils.game_market_stream_envelope import game_market_stream_envelope


def test_revision_and_observation_are_independent_precise_and_bound_to_loaded_ids():
    revised = datetime(2030, 1, 1, 0, 0, 0, 123456, timezone.utc)
    observed = datetime(2029, 12, 31, 23, 55, 0, 654321, timezone.utc)
    rows = [SimpleNamespace(id=11, market_id=1, last_updated=revised),
            SimpleNamespace(id=12, market_id=1, last_updated=None),
            SimpleNamespace(id=13, market_id=2, last_updated=revised)]
    result = game_market_stream_envelope([1, 2], rows, {11: observed, 999: revised})
    assert result["outcome_revision_at"]["11"] == revised.isoformat()
    assert result["outcome_observed_at"]["11"] == observed.isoformat()
    assert result["outcome_revision_at"]["12"] is None
    assert result["outcome_observed_at"]["12"] is None
    assert "999" not in result["outcome_observed_at"]
    assert result["outcome_market_ids"] == {"11": 1, "12": 1, "13": 2}


def test_withheld_and_empty_candidate_markets_remain_subscribed_without_inventing_clocks():
    rows = [SimpleNamespace(id=11, market_id=1, current_probability=None),
            SimpleNamespace(id=12, market_id=2, current_probability=None, last_updated="bad")]
    result = game_market_stream_envelope([1, 2, 3, 2], rows, {})
    assert result["stream_market_ids"] == [1, 2, 3]
    assert result["outcome_revision_at"] == {"11": None, "12": None}
    assert result["outcome_observed_at"] == {"11": None, "12": None}


def test_foreign_or_invalid_id_rows_cannot_acquire_a_binding():
    rows = [SimpleNamespace(id=9, market_id=99), SimpleNamespace(id=True, market_id=1)]
    result = game_market_stream_envelope([True, -1, None, 1], rows, {})
    assert result["stream_market_ids"] == [1]
    assert result["outcome_market_ids"] == {}
    assert game_market_stream_envelope([], [], {})["stream_market_ids"] == []


async def test_fresh_read_bypasses_cache_and_keeps_existing_scores_grades_and_identity(monkeypatch):
    from fastapi import Response
    from app.routes import events
    from app.utils import game_markets_cache as gmc
    body = {"event_id": 6, "status": "completed", "home_score": 7,
            "player_props": [{"hit": True, "actual": 2, "over_probability": None}],
            "spreads": [{"probability": .4}], "stream_market_ids": [1]}
    db = object()
    calls = []
    async def build(event_id, session):
        calls.append((event_id, session))
        return body, "completed", [1]
    def forbidden(*args, **kwargs):
        raise AssertionError("fresh read must not touch shared/memo cache")
    monkeypatch.setattr(events, "_build_game_markets", build)
    monkeypatch.setattr(events, "_read_game_markets_memo", forbidden)
    monkeypatch.setattr(events, "_publish_game_markets", forbidden)
    monkeypatch.setattr(gmc, "read", forbidden)
    response = Response()
    result = await events.get_game_markets(7, db=db, fresh=True, response=response)
    assert result is body
    assert result["event_id"] == 6
    assert result["home_score"] == 7
    assert result["player_props"][0] == {"hit": True, "actual": 2, "over_probability": None}
    assert calls == [(7, db)]
    assert response.headers["Cache-Control"] == "no-store"


async def test_ordinary_read_keeps_the_existing_memo_path(monkeypatch):
    from app.routes import events
    body = {"event_id": 7, "spreads": [{"probability": .4}]}
    monkeypatch.setattr(events, "_read_game_markets_memo", lambda event_id: body)
    assert await events.get_game_markets(7, db=object()) is body


def test_real_builder_keeps_all_input_bindings_and_real_quote_age():
    from datetime import timedelta
    from tests.test_a_game_market_row_carries_its_own_price_age_4970 import (
        NOW, _the_page, _payload,
    )
    markets, outcomes = _the_page()
    outcomes[0].last_updated = NOW.replace(microsecond=123456)
    observed = {row.id: NOW - timedelta(hours=7) for row in outcomes}
    body = _payload(markets=markets, outcomes=outcomes, observations=observed)
    assert body["stream_market_ids"] == [m.id for m in markets]
    assert body["outcome_market_ids"] == {str(row.id): row.market_id for row in outcomes}
    assert body["outcome_revision_at"]["1"] == outcomes[0].last_updated.isoformat()
    assert body["outcome_observed_at"]["1"] == observed[1].isoformat()
    assert body["totals"]  # Actual existing projection, not a mocked builder.
    from tests.test_a_game_market_row_carries_its_own_price_age_4970 import _priced_legs
    for path, row in _priced_legs(body):
        assert row.get("contributor_outcome_ids"), path
        for oid in row["contributor_outcome_ids"]:
            assert str(oid) in body["outcome_market_ids"], path


def test_subscription_envelope_never_silently_truncates_at_fifty_markets():
    ids = list(range(1, 81))
    result = game_market_stream_envelope(ids, [], {})
    assert result["stream_market_ids"] == ids


def test_blended_prop_identity_binds_both_actual_quote_rows():
    from tests.test_a_game_market_row_carries_its_own_price_age_4970 import (
        _cross_source_prop, _payload,
    )
    markets, outcomes = _cross_source_prop(kalshi_prob=.4, poly_prob=.6)
    body = _payload(markets=markets, outcomes=outcomes)
    row = body["player_props"][0]
    assert row["over_probability"] == .5
    assert row["contributor_outcome_ids"] == [201, 202]
    assert row["_market_ids"] == [201, 202]
    assert body["outcome_market_ids"] == {"201": 201, "202": 202}


def test_empty_builder_has_explicit_empty_subscription_envelope(monkeypatch):
    from tests import test_a_game_market_row_carries_its_own_price_age_4970 as fixture
    event = fixture._event()
    event.status = "completed"
    monkeypatch.setattr(fixture, "_event", lambda: event)
    body = fixture._payload(markets=[], outcomes=[])
    assert body["status"] == "completed"
    assert body["home_score"] == 88 and body["away_score"] == 82
    assert body["home_team"] == "Boston Celtics"
    assert body["away_team"] == "New York Knicks"
    assert body["stream_market_ids"] == []
    assert body["outcome_market_ids"] == {}
    assert body["outcome_revision_at"] == {}
    assert body["outcome_observed_at"] == {}
