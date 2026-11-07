"""#12283: the game-markets body names only markets the live stream would admit.

Atlas, Sat Nov 7 (#12278): a finished NBA game (15342680) served 423
`stream_market_ids`, every one settled or closed. The page opened nine 50-id
`/api/markets/stream` connections; the route answered 409 to each (none
admitted) and 429 to the ninth. A settled event should cost nothing live.

One predicate, `stream_admits`, decides both: the route admits by it and the
envelope only names what it would admit. Settled markets stay BOUND (their
outcomes keep their clocks for the page's reconciler); they are just not
subscribed to.
"""

from types import SimpleNamespace

from app.routes import market_stream
from app.utils.game_market_stream_envelope import game_market_stream_envelope, stream_admits


def _market(mid, source="kalshi", status="open"):
    return SimpleNamespace(id=mid, source=source, status=status)


def _outcome(oid, mid, is_winner=None):
    return SimpleNamespace(id=oid, market_id=mid, is_winner=is_winner, last_updated=None)


def test_a_finished_game_whose_markets_are_all_settled_subscribes_to_nothing():
    markets = [_market(1, status="settled"), _market(2, "polymarket", "closed"),
               _market(3, status="open"), _market(4, status="FINAL")]
    # Kalshi leaves a settled market `open` in our table (gotcha 33); its graded
    # winner is what marks it.
    outcomes = [_outcome(11, 1), _outcome(31, 3, is_winner=True), _outcome(32, 3, is_winner=False),
                _outcome(41, 4)]
    body = game_market_stream_envelope([1, 2, 3, 4], outcomes, {}, markets)
    assert body["stream_market_ids"] == []
    assert body["outcome_market_ids"] == {"11": 1, "31": 3, "32": 3, "41": 4}


def test_open_venue_markets_stay_subscribed_and_a_book_or_unloaded_market_never_is():
    markets = [_market(1), _market(2, "polymarket"), _market(5, "draftkings"), _market(6, status=None)]
    outcomes = [_outcome(11, 1, is_winner=False), _outcome(21, 2)]
    body = game_market_stream_envelope([1, 2, 5, 6, 7], outcomes, {}, markets)
    # 7 was not loaded: nothing says the stream would admit it.
    assert body["stream_market_ids"] == [1, 2, 6]


def test_the_open_winner_market_of_a_finished_game_is_still_streamed():
    """`boundOpenWinnerQuote` (web) needs it in the list until the venue settles it."""
    markets = [_market(9, status="settled"), _market(10)]
    outcomes = [_outcome(91, 9, is_winner=True), _outcome(101, 10), _outcome(102, 10)]
    assert game_market_stream_envelope([9, 10], outcomes, {}, markets)["stream_market_ids"] == [10]


def test_without_markets_the_envelope_keeps_its_old_shape():
    assert game_market_stream_envelope([3, 1], [], {})["stream_market_ids"] == [1, 3]


def test_the_stream_route_admits_by_the_same_predicate():
    assert market_stream.stream_admits is stream_admits
    assert stream_admits("kalshi", "open", False)
    assert stream_admits("polymarket", None, False)
    assert not stream_admits("kalshi", "Settled", False)
    assert not stream_admits("kalshi", "open", True)
    assert not stream_admits("fanduel", "open", False)


def test_the_builder_hands_the_envelope_its_loaded_markets():
    import inspect

    from app.routes import events

    source = inspect.getsource(events._build_game_markets)
    assert "_observed_at_by_outcome, markets\n" in source
