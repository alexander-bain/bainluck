from tests import test_a_game_market_row_carries_its_own_price_age_4970 as fixture


def test_final_route_exposes_separate_open_quote_without_changing_result(monkeypatch):
    event = fixture._event()
    event.status = "completed"
    monkeypatch.setattr(fixture, "_event", lambda: event)
    market = fixture._market(id=301, name="Boston Celtics vs New York Knicks")
    market.settled_at = None
    market.mutually_exclusive = True
    outcomes = [fixture._outcome(id=31, market_id=301, name="Boston Celtics", prob=.65),
                fixture._outcome(id=32, market_id=301, name="New York Knicks", prob=.55)]
    body = fixture._payload(markets=[market], outcomes=outcomes)
    assert body["status"] == "completed"
    assert (body["home_score"], body["away_score"]) == (88, 82)
    assert body["open_winner_quote"]["market_id"] == 301
    assert body["open_winner_quote"]["outcomes"][0]["probability"] != .65
    assert body["stream_market_ids"] == [301]
    assert body["outcome_market_ids"] == {"31": 301, "32": 301}
    outcomes[0].is_winner = True
    outcomes[0].resolution_source = "api_settlement"
    closed = fixture._payload(markets=[market], outcomes=outcomes)
    assert closed["open_winner_quote"] is None
    assert closed["closed_winner_market_ids"] == [301]
    assert (closed["home_score"], closed["away_score"]) == (88, 82)


def test_empty_route_does_not_invent_contract_settlement():
    body = fixture._payload(markets=[], outcomes=[])
    assert body["open_winner_quote"] is None
    assert body["closed_winner_market_ids"] == []
