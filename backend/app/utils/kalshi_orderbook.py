"""Current Kalshi best quotes from sequenced CLOB snapshots and deltas.

This only reconstructs quotes. The existing Kalshi probability/eligibility
policy still decides whether a quote may enter the event blend. Instantiate
one owner per WebSocket connection; discard it on reconnect. Callers consume
resnapshot requests with the existing subscription's get_snapshot action.
"""

from decimal import Decimal, InvalidOperation


def _number(value) -> Decimal:
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError("non-finite book value")
    return value


class KalshiOrderBook:
    def __init__(self):
        self._books: dict[str, dict[str, dict[Decimal, Decimal]]] = {}
        self._owners: dict[str, int] = {}
        self._sequences: dict[int, int] = {}
        self._last_quotes: dict[str, tuple] = {}
        self._awaiting: set[str] = set()
        self._resnapshots: dict[int, set[str]] = {}

    def forget(self, tickers) -> None:
        """Remove departed subscriptions, including their queued resync work."""
        for ticker in tickers:
            self._books.pop(ticker, None)
            self._owners.pop(ticker, None)
            self._last_quotes.pop(ticker, None)
            self._awaiting.discard(ticker)
            for pending in self._resnapshots.values():
                pending.discard(ticker)

    def take_resnapshot_requests(self) -> dict[int, tuple[str, ...]]:
        requests = {sid: tuple(sorted(v)) for sid, v in self._resnapshots.items() if v}
        self._resnapshots.clear()
        return requests

    def _invalidate(self, ticker: str, sid: int) -> None:
        self._books.pop(ticker, None)
        self._last_quotes.pop(ticker, None)
        if ticker not in self._awaiting:
            self._resnapshots.setdefault(sid, set()).add(ticker)
            self._awaiting.add(ticker)

    def _quote(self, ticker: str) -> dict:
        book = self._books[ticker]
        bid = max(book["yes"], default=None)
        no_bid = max(book["no"], default=None)
        ask = None if no_bid is None else Decimal(1) - no_bid
        return {
            "market_ticker": ticker,
            "yes_bid_dollars": None if bid is None else str(bid),
            "yes_ask_dollars": None if ask is None else str(ask),
        }

    def overlay_ticker(self, payload: dict) -> dict:
        """Keep a delayed ticker summary from replacing a newer healthy book.

        Genuine last-trade/volume fields remain available to the original price
        policy. A missing/gapped book leaves the ordinary ticker fallback alone.
        """
        ticker = (payload.get("market_ticker") or payload.get("ticker") or "").upper()
        if ticker not in self._books:
            return payload
        return {**payload, **self._quote(ticker)}

    def apply(self, frame: dict) -> dict | None:
        """Return changed BBO fields only; never synthesize a last trade/price."""
        kind = frame.get("type")
        if kind not in {"orderbook_snapshot", "orderbook_delta"}:
            return None
        msg = frame.get("msg")
        if not isinstance(msg, dict):
            return None
        ticker = msg.get("market_ticker")
        sid, seq = frame.get("sid"), frame.get("seq")
        if not isinstance(ticker, str) or not ticker:
            return None
        ticker = ticker.upper()
        if type(sid) is not int or type(seq) is not int or sid < 0 or seq < 0:
            # Without a subscription identity no trustworthy resync can be sent.
            # Drop any known book rather than continuing from an unsequenced delta.
            owner = self._owners.get(ticker)
            if owner is not None:
                self._invalidate(ticker, owner)
            return None
        previous = self._sequences.get(sid)
        if previous is not None and seq <= previous:
            return None  # duplicate/late frame cannot rewind a current book
        self._sequences[sid] = seq
        if previous is not None and seq != previous + 1:
            for other, owner in list(self._owners.items()):
                if owner == sid:
                    self._invalidate(other, sid)
        self._owners[ticker] = sid
        try:
            if kind == "orderbook_snapshot":
                book = {}
                for side in ("yes", "no"):
                    levels = {}
                    # Kalshi omits a side when it has no resting offers.
                    for price, quantity in msg.get(side + "_dollars_fp", []):
                        price, quantity = _number(price), _number(quantity)
                        if not 0 <= price <= 1 or quantity < 0 or price in levels:
                            raise ValueError("invalid snapshot level")
                        if quantity:
                            levels[price] = quantity
                    book[side] = levels
                self._books[ticker] = book
            else:
                if ticker not in self._books:
                    self._invalidate(ticker, sid)
                    return None
                side = msg["side"]
                price, delta = _number(msg["price_dollars"]), _number(msg["delta_fp"])
                if side not in {"yes", "no"} or not 0 <= price <= 1:
                    raise ValueError("invalid delta level")
                levels = self._books[ticker][side]
                quantity = levels.get(price, Decimal(0)) + delta
                if quantity < 0:
                    raise ValueError("negative level after delta")
                if quantity:
                    levels[price] = quantity
                else:
                    levels.pop(price, None)
            quote = self._quote(ticker)
            bid, ask = quote["yes_bid_dollars"], quote["yes_ask_dollars"]
            if bid is not None and ask is not None and Decimal(bid) > Decimal(ask):
                raise ValueError("crossed reconstructed book")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            self._invalidate(ticker, sid)
            return None
        if kind == "orderbook_snapshot":
            self._awaiting.discard(ticker)
            self._resnapshots.get(sid, set()).discard(ticker)
        value = (bid, ask)
        if self._last_quotes.get(ticker) == value:
            return None
        self._last_quotes[ticker] = value
        # These are provider observation fields when present, never local time
        # dressed up as an exchange timestamp. Snapshot messages may omit them.
        for key in ("ts", "ts_ms"):
            if key in msg:
                quote[key] = msg[key]
        return quote
