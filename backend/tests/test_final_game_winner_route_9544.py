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


def test_final_game_removes_the_open_quote_when_the_trailing_ask_refutes_it(monkeypatch):
    from app.tasks.kalshi import _kalshi_yes_probability

    event = fixture._event()
    event.status = "completed"
    monkeypatch.setattr(fixture, "_event", lambda: event)
    market = fixture._market(id=301, name="Boston Celtics vs New York Knicks")
    market.source = "kalshi"
    market.settled_at = None
    market.mutually_exclusive = True
    winner = fixture._outcome(id=31, market_id=301, name="Boston Celtics", prob=0.94)
    trailing = fixture._outcome(id=32, market_id=301, name="New York Knicks", prob=0.06)
    trailing.current_yes_bid, trailing.current_yes_ask = 0.05, 0.07
    before = fixture._payload(markets=[market], outcomes=[winner, trailing])
    assert before["open_winner_quote"]["outcomes"][1]["probability"] == 0.06

    trailing.current_yes_bid, trailing.current_yes_ask = 0, 0.03
    trailing.current_probability = _kalshi_yes_probability(0, 0.03, 0.06)
    after = fixture._payload(markets=[market], outcomes=[winner, trailing])
    assert (after["status"], after["home_score"], after["away_score"]) == ("completed", 88, 82)
    assert after["open_winner_quote"] is None
    assert after["closed_winner_market_ids"] == []
    assert after["stream_market_ids"] == [301]


def _final_pinned_payload(monkeypatch, home, away):
    event = fixture._event()
    event.status = "completed"
    monkeypatch.setattr(fixture, "_event", lambda: event)
    market = fixture._market(id=301, name="Boston Celtics vs New York Knicks")
    market.settled_at = None
    market.mutually_exclusive = True
    outcomes = [fixture._outcome(id=31, market_id=301, name="Boston Celtics", prob=home),
                fixture._outcome(id=32, market_id=301, name="New York Knicks", prob=away)]
    return fixture._payload(markets=[market], outcomes=outcomes)


def test_route_withholds_a_quote_that_repeats_the_recorded_winner(monkeypatch):
    # The fixture's score is Celtics (home) 88 - Knicks 82 (#9544).
    body = _final_pinned_payload(monkeypatch, .999, .001)
    assert (body["status"], body["home_score"], body["away_score"]) == ("completed", 88, 82)
    assert body["open_winner_quote"] is None
    assert body["closed_winner_market_ids"] == []
    assert body["stream_market_ids"] == [301]


def test_route_keeps_a_pinned_quote_that_disagrees_with_the_score(monkeypatch):
    body = _final_pinned_payload(monkeypatch, .001, .999)
    assert body["open_winner_quote"]["outcomes"][1]["probability"] == .999
    assert (body["home_score"], body["away_score"]) == (88, 82)
