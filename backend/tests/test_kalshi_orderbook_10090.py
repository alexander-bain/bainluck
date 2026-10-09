from app.utils.kalshi_orderbook import KalshiOrderBook


def snapshot(seq=1, ticker="GAME-A"):
    return {"type": "orderbook_snapshot", "sid": 2, "seq": seq, "msg": {
        "market_ticker": ticker,
        "yes_dollars_fp": [["0.83", "10"], ["0.84", "3.50"]],
        "no_dollars_fp": [["0.15", "5"]],
    }}


def delta(seq, *, price="0.84", quantity="-3.50", ticker="GAME-A"):
    return {"type": "orderbook_delta", "sid": 2, "seq": seq, "msg": {
        "market_ticker": ticker, "side": "yes", "price_dollars": price,
        "delta_fp": quantity, "ts_ms": 12345,
    }}


def test_real_best_level_removal_arrives_without_waiting_for_ticker():
    book = KalshiOrderBook()
    assert book.apply(snapshot())["yes_bid_dollars"] == "0.84"
    changed = book.apply(delta(2))
    assert changed == {"market_ticker": "GAME-A", "yes_bid_dollars": "0.83",
                       "yes_ask_dollars": "0.85", "ts_ms": 12345}
    # Size/deep-book churn produces no fabricated probability movement.
    assert book.apply(delta(3, price="0.80", quantity="12")) is None
    old_ticker = {"market_ticker": "GAME-A", "yes_bid_dollars": "0.84",
                  "yes_ask_dollars": "0.85", "price_dollars": "0.84"}
    assert book.overlay_ticker(old_ticker)["yes_bid_dollars"] == "0.83"
    assert book.overlay_ticker(old_ticker)["price_dollars"] == "0.84"
    assert old_ticker["yes_bid_dollars"] == "0.84"


def test_subscription_gap_invalidates_all_books_once_until_fresh_snapshots():
    book = KalshiOrderBook()
    book.apply(snapshot())
    book.apply(snapshot(2, "GAME-B"))
    assert book.apply(delta(4)) is None
    assert book.take_resnapshot_requests() == {2: ("GAME-A", "GAME-B")}
    assert book.apply(delta(5)) is None
    assert book.take_resnapshot_requests() == {}
    ticker = {"market_ticker": "GAME-A", "yes_bid_dollars": "0.7"}
    assert book.overlay_ticker(ticker) is ticker
    assert book.apply(snapshot(6)) is not None
    assert book.apply(delta(7))["yes_bid_dollars"] == "0.83"
    assert book.apply(delta(7)) is None


def test_unknown_delta_malformed_or_crossed_book_requests_resync():
    book = KalshiOrderBook()
    assert book.apply(delta(1)) is None
    assert book.take_resnapshot_requests() == {2: ("GAME-A",)}
    assert book.apply(snapshot(2))
    assert book.apply(delta(3, quantity="-4")) is None
    assert book.take_resnapshot_requests() == {2: ("GAME-A",)}
    assert book.apply(snapshot(4))
    assert book.apply(delta(5, price="0.90", quantity="1")) is None
    assert book.take_resnapshot_requests() == {2: ("GAME-A",)}


def test_removal_and_reconnect_never_reuse_previous_book():
    book = KalshiOrderBook()
    book.apply(snapshot())
    book.forget(["GAME-A"])
    ticker = {"market_ticker": "GAME-A", "yes_bid_dollars": "0.7"}
    assert book.overlay_ticker(ticker) is ticker
    fresh_connection = KalshiOrderBook()
    assert fresh_connection.apply(delta(2)) is None
    assert fresh_connection.take_resnapshot_requests() == {2: ("GAME-A",)}
