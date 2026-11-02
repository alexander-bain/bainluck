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


def test_optional_empty_side_accepts_its_later_first_offer():
    book = KalshiOrderBook()
    frame = snapshot()
    del frame["msg"]["yes_dollars_fp"]
    assert book.apply(frame)["yes_bid_dollars"] is None
    assert book.take_resnapshot_requests() == {}
    assert book.apply(delta(2, price="0.80", quantity="5"))["yes_bid_dollars"] == "0.80"


def test_the_cached_quote_follows_every_book_change_and_callers_get_their_own_dict():
    """#10090 CPU: `_quote` is computed once per book change, then served from
    a cache. Every frame that changes the book, an invalidation and a forget
    must drop it; a caller adding fields (apply's `ts_ms`, the observation
    marker) must never write them into the cache."""
    book = KalshiOrderBook()
    book.apply(snapshot())
    first = book._quote("GAME-A")
    first["ts_ms"] = 1
    first["_observation_only"] = True
    assert book._quote("GAME-A") == {"market_ticker": "GAME-A", "yes_bid_dollars": "0.84",
                                     "yes_ask_dollars": "0.85"}
    # A delta that moves the best bid is read at once, not from the cache.
    book.apply(delta(2))
    assert book._quote("GAME-A")["yes_bid_dollars"] == "0.83"
    # Deep-book churn leaves the best quote, and the overlay reads the same.
    book.apply(delta(3, price="0.80", quantity="12"))
    assert book.overlay_ticker({"market_ticker": "GAME-A"})["yes_bid_dollars"] == "0.83"
    # A fresh snapshot replaces the cached quote.
    snap = snapshot(4)
    snap["msg"]["yes_dollars_fp"] = [["0.70", "1"]]
    book.apply(snap)
    assert book._quote("GAME-A")["yes_bid_dollars"] == "0.70"
    # A gap invalidates the book: no cached quote outlives it.
    assert book.apply(delta(9)) is None
    assert book.overlay_ticker({"market_ticker": "GAME-A"}) == {"market_ticker": "GAME-A"}
    # Forget drops it too.
    book.apply(snapshot(10))
    assert book._quote("GAME-A")["yes_bid_dollars"] == "0.84"
    book.forget(["GAME-A"])
    assert "GAME-A" not in book._quote_cache
