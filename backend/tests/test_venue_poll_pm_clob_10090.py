"""#10090 — the Polymarket CLOB path of the 30-second poll prices a book exactly
as the socket does, and hands everything else to the Gamma reading.

THE REVIEW ITEM IS THE PRICING RULE. Gamma ``outcomePrices`` and a CLOB book are
different instruments, so the CLOB path does not get a rule of its own: it is
the socket's ``handle_price`` decision, by reuse. The first class below feeds
the SAME book to both — the real Polymarket consumer (the rig of
``test_poly_ws_side1_leg_pairing_8403``, as a CLOB ``book`` entry, which is what
the socket receives on subscribe) and the poll's :func:`socket_book_price` +
:func:`clob_item` — and asserts the same legs get the same numbers, or that
neither prices.

The sweeps then prove, over every integer-cent book rather than by assertion,
that two Gamma-path refusals can never fire on a price this rule accepts (the
#10298 parent-book refusal and the #6676 empty-book midpoint).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from app.tasks import venue_poll_30s as v
from app.tasks import venue_poll_pm_clob as clob
from tests.test_poly_ws_min_order_trade_9733 import (
    CONDITION,
    NO_LEG,
    NO_TOKEN,
    YES_LEG,
    YES_TOKEN,
    _run as run_socket,
)
from tests.test_venue_poll_30s_10090 import _FakeRedis


def _book_entry(token, bid, ask):
    """One CLOB order book as ``POST /books`` returns it and the socket receives it."""
    def levels(price):
        return [] if price is None else [{"price": str(price), "size": "100"}]

    return {
        "event_type": "book",
        "asset_id": token,
        "market": CONDITION,
        "bids": levels(bid),
        "asks": levels(ask),
    }


def _mirror(bid, ask):
    """The No token's book: the same orders read from the other side."""
    return (
        None if ask is None else round(1 - ask, 6),
        None if bid is None else round(1 - bid, 6),
    )


#: (bid, ask) of the YES token. Specimens are named where they come from.
BOOKS = [
    pytest.param(0.42, 0.50, id="tight"),
    pytest.param(0.01, 0.03, id="longshot"),
    pytest.param(0.97, 0.99, id="favourite"),
    pytest.param(0.30, 0.49, id="spread-just-under-the-bar"),
    pytest.param(0.30, 0.50, id="spread-at-the-bar-is-wide"),
    pytest.param(0.15, 0.52, id="10298-lions-packers"),
    pytest.param(0.11, 0.53, id="1578-alcaraz-semifinals"),
    pytest.param(0.28, 0.91, id="9934-braves-series"),
    pytest.param(0.01, 0.99, id="empty-book-6676"),
    pytest.param(None, 0.03, id="no-bid"),
    pytest.param(0.28, None, id="no-ask"),
]


def _socket_prices(writes) -> dict:
    return {oid: prob for oid, prob in writes if prob is not None}


class TestTheSameBookPricesTheSameThroughBothPaths:
    @pytest.mark.parametrize("bid, ask", BOOKS)
    async def test_the_same_token_gets_the_same_verdict_and_price(self, monkeypatch, bid, ask):
        """Token 0's book alone. The game-slate socket prices only that token's
        own leg, so this compares the decision and the number one-for-one."""
        writes, _stats = await run_socket(monkeypatch, [json.dumps([_book_entry(YES_TOKEN, bid, ask)])])
        socket = _socket_prices(writes)

        verdict, prob = clob.socket_book_price(bid, ask)
        if verdict != "price":
            assert socket == {}, (verdict, socket)
            return
        item = clob.clob_item(CONDITION, bid, ask, prob)
        assert socket == {YES_LEG: pytest.approx(item["probability"], abs=1e-6)}

    @pytest.mark.parametrize("bid, ask", [p for p in BOOKS if p.id != "spread-at-the-bar-is-wide"])
    async def test_both_tokens_books_price_both_legs_as_the_poll_does(self, monkeypatch, bid, ask):
        """Both tokens' books, as the socket subscribes them: the ``_no`` leg the
        poll derives from token 0 is the number the No token's own book gives."""
        no_bid, no_ask = _mirror(bid, ask)
        frame = json.dumps([
            _book_entry(YES_TOKEN, bid, ask),
            _book_entry(NO_TOKEN, no_bid, no_ask),
        ])
        writes, _stats = await run_socket(monkeypatch, [frame])
        socket = _socket_prices(writes)

        verdict, prob = clob.socket_book_price(bid, ask)
        if verdict != "price":
            assert socket == {}, (verdict, socket)
            return
        item = clob.clob_item(CONDITION, bid, ask, prob)
        assert socket == {
            YES_LEG: pytest.approx(item["probability"], abs=1e-6),
            NO_LEG: pytest.approx(item["no"]["probability"], abs=1e-6),
        }

    async def test_at_the_bar_the_sockets_two_tokens_disagree_and_the_poll_reads_token_zero(
        self, monkeypatch
    ):
        """A FINDING ABOUT THE SOCKET, pinned so a fix turns this red.

        ``_poly_book_is_untradeable`` compares ``ask - bid >= 0.20`` in floats.
        Yes 0.30/0.50 is 0.2 → wide; its No book 0.50/0.70 is
        0.19999999999999996 → priced. So the socket prices this condition's No
        leg and refuses its Yes leg, from one book. Over every integer-cent book
        44 of the 79 exactly-20-cent books split this way, both directions. The
        poll reads token 0 only, so it takes token 0's verdict — here, the
        Gamma reading. Out of this change's scope: the rule is
        ``tasks/polymarket.py``'s, shared by every Polymarket writer.
        """
        from app.tasks.polymarket import _poly_book_is_untradeable

        frame = json.dumps([
            _book_entry(YES_TOKEN, 0.30, 0.50),
            _book_entry(NO_TOKEN, *_mirror(0.30, 0.50)),
        ])
        writes, _stats = await run_socket(monkeypatch, [frame])
        assert _socket_prices(writes) == {NO_LEG: pytest.approx(0.60)}
        assert clob.socket_book_price(0.30, 0.50) == ("wide", None)
        split = [
            (b / 100, a / 100) for b in range(1, 80) for a in [b + 20]
            if _poly_book_is_untradeable(b / 100, a / 100)
            != _poly_book_is_untradeable(*_mirror(b / 100, a / 100))
        ]
        assert len(split) == 44

    def test_the_specimens_cover_every_verdict(self):
        verdicts = {clob.socket_book_price(p.values[0], p.values[1])[0] for p in BOOKS}
        assert verdicts == {"price", "wide", "no_book"}

    async def test_a_single_yes_book_prices_both_legs_like_the_open_arms_complement(self):
        """The poll reads token 0 only; the ``_no`` leg is ``with_complements``'
        ``1 - p`` over ``books_with_complements``' book — the open arm's pair."""
        from app.tasks.polymarket_ws import books_with_complements, with_complements

        item = clob.clob_item("0xc", 0.42, 0.50, 0.46)
        assert with_complements([7], 0.46, {7: 8}) == [(7, 0.46), (8, item["no"]["probability"])]
        assert books_with_complements([7], 0.42, 0.50, {7: 8}) == [
            (7, 0.42, 0.50),
            (8, item["no"]["yes_bid"], item["no"]["yes_ask"]),
        ]

    def test_a_crossed_book_is_refused_as_the_socket_refuses_it(self):
        from app.services.polymarket_ws import _price_change_quotes

        crossed = {"timestamp": "1782753357257", "price_changes": [
            {"asset_id": YES_TOKEN, "best_bid": "0.55", "best_ask": "0.45"}]}
        assert _price_change_quotes(crossed) == []
        assert clob.socket_book_price(0.55, 0.45) == ("crossed", None)


def _cent_books():
    for b in range(1, 99):
        for a in range(b, 100):
            yield b / 100, a / 100


class TestGammaRefusalsCannotFireOnAnAcceptedPrice:
    def test_the_10298_parent_book_refusal_never_refutes_a_midpoint_it_accepts(self):
        from app.utils.kalshi_empty_book import book_refutes_price

        accepted = 0
        for bid, ask in _cent_books():
            verdict, prob = clob.socket_book_price(bid, ask)
            if verdict == "price":
                accepted += 1
                assert not book_refutes_price(bid, ask, prob), (bid, ask)
        assert accepted > 1000

    def test_the_6676_empty_book_guard_never_refuses_a_price_it_accepts(self):
        from app.utils.feed_market_quality import is_empty_book_midpoint

        for bid, ask in _cent_books():
            verdict, prob = clob.socket_book_price(bid, ask)
            if verdict != "price":
                continue
            item = clob.clob_item("0xa", bid, ask, prob)
            assert not is_empty_book_midpoint(item["probability"], item["yes_bid"], item["yes_ask"])
            no = item["no"]
            assert not is_empty_book_midpoint(no["probability"], no["yes_bid"], no["yes_ask"])
            assert 0 < item["probability"] < 1 and 0 < no["probability"] < 1


# ── the CLOB read ─────────────────────────────────────────────────────────────


#: Recorded 2026-10-30 from production CLOB, the same three tokens read by
#: `POST /books` and `POST /prices` (BUY and SELL each): BUY is the best bid.
RECORDED_BOOK = {"bids": ["0.1", "0.101"], "asks": ["0.121", "0.12"]}
RECORDED_PRICES = {
    "10020474766586597174536884760660371065657738780090515048671589091437148331942": {
        "BUY": "0.101", "SELL": "0.12"},
    "222": {"BUY": "0", "SELL": "0.03"},  # no bid: the venue writes "0"
    "333": {"BUY": "0.5"},  # one side absent from the answer
}


async def test_get_book_tops_reads_buy_as_bid_and_sell_as_ask(monkeypatch):
    from app.services.polymarket_api import PolymarketAPIService

    sent = {}

    async def post(path, json=None):
        sent["path"], sent["body"] = path, json
        request = httpx.Request("POST", "https://clob.polymarket.com/prices")
        return httpx.Response(200, json=RECORDED_PRICES, request=request)

    service = PolymarketAPIService()
    monkeypatch.setattr(service.clob_client, "post", post)
    tops = await service.get_book_tops(["1002", "222"])
    await service.close()
    assert sent["path"] == "/prices"
    assert sent["body"] == [
        {"token_id": "1002", "side": "BUY"}, {"token_id": "1002", "side": "SELL"},
        {"token_id": "222", "side": "BUY"}, {"token_id": "222", "side": "SELL"},
    ]
    best_bid = max(float(p) for p in RECORDED_BOOK["bids"])
    best_ask = min(float(p) for p in RECORDED_BOOK["asks"])
    assert tops["10020474766586597174536884760660371065657738780090515048671589091437148331942"] == (
        best_bid, best_ask)
    assert tops["222"] == (None, 0.03)
    assert tops["333"] == (0.5, None)


async def test_a_429_from_the_clob_re_raises(monkeypatch):
    from app.services.polymarket_api import PolymarketAPIService

    async def post(path, json=None):
        request = httpx.Request("POST", "https://clob.polymarket.com/prices")
        return httpx.Response(429, request=request)

    service = PolymarketAPIService()
    monkeypatch.setattr(service.clob_client, "post", post)
    with pytest.raises(httpx.HTTPStatusError):
        await service.get_book_tops(["1"])
    await service.close()


# ── the switch, tokens, the fallback ──────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [(None, "gamma"), ("", "gamma"), ("gamma", "gamma"), ("CLOB", "clob"), ("bogus", "gamma")],
)
def test_the_source_switch_defaults_to_gamma(raw, expected):
    env = {} if raw is None else {clob.PM_SOURCE_ENV: raw}
    assert clob.pm_source(env) == expected


@pytest.mark.parametrize(
    "ext, condition",
    [("0xabc", "0xabc"), ("0xabc_yes", "0xabc"), ("0xabc_no", "0xabc"),
     ("0xabc_side1", "0xabc"), ("KXE-1", None), ("Yes", None)],
)
def test_a_leg_prices_off_the_condition_the_sockets_contract_key_names(ext, condition):
    assert clob.leg_condition(ext) == condition


def test_token_zero_only_for_a_two_token_condition():
    class M:
        def __init__(self, tokens):
            self.clob_token_ids = tokens

    assert clob.token0_of(M(["111", "222"])) == "111"
    assert clob.token0_of(M(["111"])) is None
    assert clob.token0_of(M([])) is None


def test_the_token_cache_keeps_hits_forever_and_retries_misses(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(clob, "_redis", lambda: fake)
    monkeypatch.setattr(clob, "_TOKENS", {})
    clob.store_tokens({"0xa": "111", "0xb": None}, now=1000.0)
    monkeypatch.setattr(clob, "_TOKENS", {})  # a fresh process reads Redis
    assert clob.cached_tokens(["0xa", "0xb", "0xc"], now=1001.0) == {"0xa": "111", "0xb": None}
    later = 1000.0 + clob.TOKEN_MISS_RETRY_S + 1
    assert clob.cached_tokens(["0xa", "0xb"], now=later) == {"0xa": "111"}  # the miss is due


def test_fallback_keeps_only_the_legs_the_clob_did_not_price():
    unit = v.Unit("9", {1: [(11, "0xa"), (12, "0xb")], 2: [(21, "0xc_yes"), (22, "0xc_no")]})
    (left,) = clob.fallback_units([unit], priced={"0xa", "0xc"})
    assert left.legs == {1: [(12, "0xb")]}
    assert clob.fallback_units([unit], priced={"0xa", "0xb", "0xc"}) == []


class _Gamma:
    def __init__(self, condition):
        self.condition_id = condition
        self.clob_token_ids = [f"t-{condition}", f"n-{condition}"]


class _Service:
    """Gamma knows every condition but ``0xmissing``; the CLOB answers ``tops``."""

    def __init__(self, tops, *, raise_on_tops=None):
        self.tops = tops
        self.raise_on_tops = raise_on_tops
        self.reads: list[list[str]] = []
        self.gamma_reads = 0

    async def get_markets_by_conditions(self, conditions, *, batch_size=40):
        self.gamma_reads += 1
        return [_Gamma(c) for c in conditions if c != "0xmissing"]

    async def get_book_tops(self, tokens):
        self.reads.append(list(tokens))
        if self.raise_on_tops is not None:
            raise self.raise_on_tops
        return {t: self.tops[t] for t in tokens if t in self.tops}


def _wire(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(clob, "_redis", lambda: fake)
    monkeypatch.setattr(v, "_redis", lambda: fake)
    monkeypatch.setattr(clob, "_TOKENS", {})
    monkeypatch.setattr(clob, "backoff_remaining", lambda _venue: 0.0)
    monkeypatch.setattr(clob, "read_cursor", lambda _venue: None)
    cursors = []
    monkeypatch.setattr(clob, "write_cursor", lambda venue, key: cursors.append((venue, key)))
    monkeypatch.setattr(clob, "clear_backoff", lambda _venue: None)
    written = []

    async def write_group(_session, venue, group_units, found, fetched_at, stats):
        written.append((venue, [u.key for u in group_units], found, fetched_at))

    monkeypatch.setattr(clob, "_write_group", write_group)
    return written, cursors


async def test_the_pass_writes_usable_books_and_returns_exactly_the_rest(monkeypatch):
    written, cursors = _wire(monkeypatch)
    units = [
        v.Unit("100", {1: [(11, "0xa"), (12, "0xb"), (13, "0xc")]}),  # a field
        v.Unit("200", {2: [(21, "0xd_yes"), (22, "0xd_no")]}),  # a binary
        v.Unit("300", {3: [(31, "0xmissing")]}),  # Gamma does not return it
    ]
    service = _Service({
        "t-0xa": (0.42, 0.50),  # usable
        "t-0xb": (None, 0.03),  # no bid
        "t-0xc": (0.10, 0.60),  # wide
        "t-0xd": (0.60, 0.62),  # usable
    })
    stats = {"errors": []}
    rest = await clob.clob_pass(None, service, units, deadline=time.monotonic() + 20,
                                offset=0.0, stats=stats)

    ((venue, keys, found, fetched_at),) = written
    assert venue == "polymarket" and keys == ["100", "200"]
    assert {u: [i["external_id"] for i in items] for u, items in found.items()} == {
        "100": ["0xa"], "200": ["0xd"]}
    assert found["200"][0]["no"]["probability"] == pytest.approx(0.39)
    assert isinstance(fetched_at, datetime) and fetched_at.tzinfo is timezone.utc
    assert service.reads == [["t-0xa", "t-0xb", "t-0xc", "t-0xd"]]  # token 0 only, one read
    assert [(u.key, u.legs) for u in rest] == [
        ("100", {1: [(12, "0xb"), (13, "0xc")]}),
        ("300", {3: [(31, "0xmissing")]}),
    ]
    assert stats["clob_refused_no_book"] == 1 and stats["clob_refused_wide"] == 1
    assert stats["clob_legs_priced"] == 3 and stats["tokens_missed"] == 1
    assert cursors == [("polymarket_clob", "200")]


async def test_a_second_pass_asks_gamma_for_no_token_it_already_holds(monkeypatch):
    _wire(monkeypatch)
    units = [v.Unit("100", {1: [(11, "0xa")]})]
    service = _Service({"t-0xa": (0.42, 0.50)})
    for _ in range(2):
        await clob.clob_pass(None, service, units, deadline=time.monotonic() + 20,
                             offset=0.0, stats={"errors": []})
    assert service.gamma_reads == 1 and len(service.reads) == 2


async def test_a_clob_429_backs_off_the_clob_only_and_hands_everything_to_gamma(monkeypatch):
    written, cursors = _wire(monkeypatch)
    started = []
    monkeypatch.setattr(clob, "start_backoff", lambda venue: started.append(venue) or 30)
    request = httpx.Request("POST", "https://clob.polymarket.com/prices")
    error = httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
    units = [v.Unit("100", {1: [(11, "0xa")]})]
    stats = {"errors": []}
    rest = await clob.clob_pass(None, _Service({}, raise_on_tops=error), units,
                                deadline=time.monotonic() + 20, offset=0.0, stats=stats)
    assert started == ["polymarket_clob"] and stats["clob_stopped"] == "rate_limited"
    assert written == [] and [u.key for u in rest] == ["100"]
    assert cursors == [("polymarket_clob", None)]


async def test_no_clob_read_starts_past_the_time_budget(monkeypatch):
    written, _ = _wire(monkeypatch)
    clob.store_tokens({"0xa": "t-0xa"}, now=time.time())
    service = _Service({"t-0xa": (0.42, 0.50)})
    stats = {"errors": []}
    rest = await clob.clob_pass(None, service, [v.Unit("100", {1: [(11, "0xa")]})],
                                deadline=time.monotonic() + v._MIN_REQUEST_S - 0.5,
                                offset=0.0, stats=stats)
    assert service.reads == [] and written == [] and stats["clob_stopped"] == "budget"
    assert [u.key for u in rest] == ["100"]


async def _no_write(*_a, **_k):
    return None


async def test_under_the_gamma_source_the_pass_never_reads_the_clob(monkeypatch):
    """The default: VENUE_POLL_30S_PM_SOURCE unset is the first build exactly."""
    from tests.test_venue_poll_30s_10090 import _unit, _wire_pass

    monkeypatch.delenv(clob.PM_SOURCE_ENV, raising=False)

    async def explode(*_a, **_k):
        raise AssertionError("the gamma source never runs the CLOB pass")

    monkeypatch.setattr(clob, "clob_pass", explode)
    seen = []

    async def fetch(venue, _service, chunks, _stats, _timeout):
        seen.append(chunks)
        return {}

    calls = _wire_pass(monkeypatch, units=[_unit("1", 2)], fetch=fetch)
    monkeypatch.setattr(v, "_write_group", _no_write)
    stats = await v.poll_venue("polymarket", deadline=time.monotonic() + 20)
    assert stats["stopped"] == "done" and seen == [[["1"]]]
    assert calls["cursor"] == ["1"]


async def test_under_the_clob_source_gamma_reads_only_the_fallback_on_its_own_cursor(monkeypatch):
    from tests.test_venue_poll_30s_10090 import _unit, _wire_pass

    monkeypatch.setenv(clob.PM_SOURCE_ENV, "clob")

    async def clob_pass(_session, _service, units, **_k):
        return [units[1]]

    monkeypatch.setattr(clob, "clob_pass", clob_pass)
    seen = []

    async def fetch(venue, _service, chunks, _stats, _timeout):
        seen.append(chunks)
        return {}

    cursors = []
    calls = _wire_pass(monkeypatch, units=[_unit("1", 2), _unit("2", 2)], fetch=fetch)
    monkeypatch.setattr(v, "_write_group", _no_write)
    monkeypatch.setattr(v, "read_cursor", lambda name: cursors.append(name))
    stats = await v.poll_venue("polymarket", deadline=time.monotonic() + 20)
    assert seen == [[["2"]]] and cursors == ["polymarket_gamma"]
    assert stats["gamma_fallback_units"] == 1 and calls["cursor"] == ["2"]


async def test_the_clob_pass_leaves_the_gamma_reading_its_reserve(monkeypatch):
    from tests.test_venue_poll_30s_10090 import _unit, _wire_pass

    monkeypatch.setenv(clob.PM_SOURCE_ENV, "clob")
    seen = {}

    async def clob_pass(_session, _service, units, *, deadline, **_k):
        seen["deadline"] = deadline
        return []

    monkeypatch.setattr(clob, "clob_pass", clob_pass)
    _wire_pass(monkeypatch, units=[_unit("1", 2)], fetch=None)
    end = time.monotonic() + 20
    stats = await v.poll_venue("polymarket", deadline=end)
    assert seen["deadline"] == pytest.approx(end - clob.GAMMA_RESERVE_S)
    assert stats["stopped"] == "done" and stats["covered_share"] == 1.0
