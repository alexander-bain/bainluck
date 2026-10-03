"""#9844 — the Sports strip stops printing exact-score cards nobody has priced.

WHAT A READER SAW. ``/sports`` at 390px, 2026-09-30 14:25Z, *Player Props &
Progressions*: eight Championship "Exact Score" cards, each led by
"2–2 9% · 3–3 8% · 2–5 6% · 4–4 6%", none showing 1–0, 1–1 or 0–0. Wrexham and
Birmingham then appeared a second time as plain market cards.

The fixture rows are production's, read by db-query that morning:

* SPECIMEN ``63369299`` Wrexham v West Brom: five legs, every one bid at the 1¢
  floor, asks 10–17¢, summing to 0.34. Polymarket's own book (event 1106734)
  has 37 legs, all 1¢ bids, none traded.
* CONTROL ``61369936`` Denmark v Portugal: 17 legs, sum 0.988, a real book.
  It must keep its card, and appear exactly once.
* CONTROL ``61369947`` Germany v Serbia: 16 legs summing to only 0.72 (clause 1
  holds), but six legs are bid above 5¢, so clause 2 keeps it.

Driven through the real ``grouped_feed`` coroutine with a stub session because
half the defect (the duplicate) lives in the route's assembly.
"""

from decimal import Decimal

import pytest

from app.routes.futures import _exact_score_field_nobody_prices, grouped_feed
from app.utils.feed_market_quality import EMPTY_BOOK_MAX_BID, FEED_EXCLUSIVE_SUM_MIN
from tests._grouped_feed_slate import NO_SLATE, is_slate_read

D = Decimal

WREXHAM = (
    63369299,
    "Wrexham AFC vs. West Bromwich Albion FC - Exact Score",
    "polymarket:1106734",
    [
        (238778702, "Wrexham AFC 2 - 2 West Bromwich Albion FC", "0.090000", "0.0100", "0.1700"),
        (238778703, "Wrexham AFC 3 - 3 West Bromwich Albion FC", "0.075000", "0.0100", "0.1400"),
        (238821978, "Wrexham AFC 2 - 5 West Bromwich Albion FC", "0.060000", "0.0100", "0.1100"),
        (238778704, "Wrexham AFC 4 - 4 West Bromwich Albion FC", "0.060000", "0.0100", "0.1100"),
        (238778705, "Wrexham AFC 5 - 5 West Bromwich Albion FC", "0.055000", "0.0100", "0.1000"),
    ],
)

DENMARK = (
    61369936,
    "Denmark vs. Portugal - Exact Score",
    "polymarket:1042386",
    [
        (236170576, "Denmark 1 - 1 Portugal", "0.120000", "0.1100", "0.1300"),
        (237753136, "Any Other Score", "0.105000", "0.0200", "0.1900"),
        (236170580, "Denmark 1 - 2 Portugal", "0.095000", "0.0900", "0.1000"),
        (236170577, "Denmark 0 - 1 Portugal", "0.090000", "0.0800", "0.1000"),
        (236170579, "Denmark 0 - 2 Portugal", "0.070000", "0.0600", "0.0800"),
        (236170582, "Denmark 2 - 1 Portugal", "0.070000", "0.0600", "0.0800"),
        (236170581, "Denmark 1 - 0 Portugal", "0.065000", "0.0600", "0.0700"),
        (236170584, "Denmark 2 - 2 Portugal", "0.065000", "0.0620", "0.0680"),
        (236170578, "Denmark 0 - 0 Portugal", "0.055500", "0.0530", "0.0580"),
        (236170583, "Denmark 1 - 3 Portugal", "0.052500", "0.0510", "0.0540"),
        (236170586, "Denmark 0 - 3 Portugal", "0.041000", "0.0390", "0.0430"),
        (236170585, "Denmark 2 - 0 Portugal", "0.038500", "0.0370", "0.0400"),
        (236170589, "Denmark 2 - 3 Portugal", "0.033500", "0.0310", "0.0360"),
        (236170588, "Denmark 3 - 1 Portugal", "0.028000", "0.0260", "0.0300"),
        (236170590, "Denmark 3 - 2 Portugal", "0.025000", "0.0230", "0.0270"),
        (236170587, "Denmark 3 - 0 Portugal", "0.017500", "0.0150", "0.0200"),
        (236170591, "Denmark 3 - 3 Portugal", "0.016500", "0.0140", "0.0190"),
    ],
)

GERMANY = (
    61369947,
    "Germany vs. Serbia - Exact Score",
    "polymarket:1042374",
    [
        (236320488, "Germany 2 - 0 Serbia", "0.115000", "0.1100", "0.1200"),
        (236320491, "Germany 3 - 0 Serbia", "0.105000", "0.1000", "0.1100"),
        (236320489, "Germany 2 - 1 Serbia", "0.090000", "0.0800", "0.1000"),
        (236320490, "Germany 1 - 0 Serbia", "0.085000", "0.0800", "0.0900"),
        (236320492, "Germany 3 - 1 Serbia", "0.080000", "0.0700", "0.0900"),
        (236320493, "Germany 1 - 1 Serbia", "0.065000", "0.0600", "0.0700"),
        (236320494, "Germany 2 - 2 Serbia", "0.037500", "0.0340", "0.0410"),
        (236320496, "Germany 3 - 2 Serbia", "0.034000", "0.0310", "0.0370"),
        (236320495, "Germany 0 - 0 Serbia", "0.029000", "0.0260", "0.0320"),
        (236320498, "Germany 1 - 2 Serbia", "0.022000", "0.0190", "0.0250"),
        (236320497, "Germany 0 - 1 Serbia", "0.020000", "0.0170", "0.0230"),
        (236320500, "Germany 2 - 3 Serbia", "0.009500", "0.0070", "0.0120"),
        (236320502, "Germany 3 - 3 Serbia", "0.009000", "0.0070", "0.0110"),
        (236320501, "Germany 0 - 2 Serbia", "0.008500", "0.0060", "0.0110"),
        (236320499, "Germany 1 - 3 Serbia", "0.007000", "0.0050", "0.0090"),
        (236320503, "Germany 0 - 3 Serbia", "0.003000", "0.0010", "0.0050"),
    ],
)


def _field(spec):
    return [(D(p), D(b), D(a)) for _id, _n, p, b, a in spec[3]]


# ── the predicate ──────────────────────────────────────────────────────────


def test_the_specimen_is_nobody_priced():
    assert _exact_score_field_nobody_prices(_field(WREXHAM)) is True


def test_a_real_book_is_priced():
    assert _exact_score_field_nobody_prices(_field(DENMARK)) is False


def test_clause_two_keeps_a_short_field_with_real_buyers():
    """Germany v Serbia sums to 0.72, under the floor, so only the bids keep it."""
    field = _field(GERMANY)
    assert sum(p for p, _b, _a in field) < D(str(FEED_EXCLUSIVE_SUM_MIN))
    assert _exact_score_field_nobody_prices(field) is False


def test_clause_one_keeps_an_unbid_field_that_adds_up():
    """Nobody bids, but the legs cover the match: not this defect."""
    field = [(D("0.20"), D("0.01"), D("0.39"))] * 4  # sums to 0.80
    assert _exact_score_field_nobody_prices(field) is False


def test_the_sum_floor_is_exclusive_at_the_boundary():
    at_floor = [(D(str(FEED_EXCLUSIVE_SUM_MIN / 3)), D("0.01"), D("0.5"))] * 3
    assert _exact_score_field_nobody_prices(at_floor) is False


def test_a_bid_at_the_empty_book_floor_is_not_a_buyer():
    field = _field(WREXHAM)
    field[0] = (field[0][0], D(str(EMPTY_BOOK_MAX_BID)), field[0][2])
    assert _exact_score_field_nobody_prices(field) is True
    field[0] = (field[0][0], D("0.06"), field[0][2])
    assert _exact_score_field_nobody_prices(field) is False


def test_a_bookless_leg_is_a_model_price_and_is_left_alone():
    field = _field(WREXHAM) + [(D("0.10"), None, None)]
    assert _exact_score_field_nobody_prices(field) is False


def test_an_empty_field_is_not_judged():
    assert _exact_score_field_nobody_prices([]) is False


# ── the route ──────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    """One canned read: the market pool. A second read fails loudly."""

    def __init__(self, rows):
        self._results = [rows]
        self.calls = 0

    async def execute(self, _stmt):
        if is_slate_read(_stmt):  # #10208: no slate in this pool
            return NO_SLATE
        self.calls += 1
        if not self._results:
            raise AssertionError(f"the route made read {self.calls}; none canned")
        return _Result(self._results.pop(0))


class _Outcome:
    def __init__(self, oid, name, probability, bid, ask):
        self.id = oid
        self.name = name
        self.probability = D(probability)
        self.current_probability = D(probability)
        self.current_yes_bid = D(bid)
        self.current_yes_ask = D(ask)
        self.american_odds = None
        self.external_id = None


class _Market:
    def __init__(self, spec):
        mid, name, group_id, legs = spec
        self.id = mid
        self.name = name
        self.source = "polymarket"
        self.category = "championship"
        self.llm_sport_category = "soccer"
        self.status = "open"
        self.group_id = group_id
        self.group_type = None
        self.market_type = "field"
        self.event_id = None
        self.mutually_exclusive = True
        self.outcomes = [_Outcome(*leg) for leg in legs]


INNING = (
    63369352,
    "Boston Red Sox vs. New York Yankees - 1st Inning Winner",
    "polymarket:1106800",
    [
        (1, "Draw", "0.590000", "0.5800", "0.6000"),
        (2, "New York Yankees", "0.210000", "0.2000", "0.2200"),
        (3, "Boston Red Sox", "0.170000", "0.1600", "0.1800"),
    ],
)


async def _serve(rows):
    return await grouped_feed(
        request=type("R", (), {"scope": {}})(),
        response=type("S", (), {"headers": {}})(),
        category=None,
        sport=None,
        sports_only=True,
        limit=20,
        db=_Session(rows),
    )


def _exact_titles(payload):
    return [c["title"] for c in payload["feed"] if c.get("kind") == "exact_score"]


def _market_card_ids(payload):
    return [c["market"]["id"] for c in payload["feed"] if c.get("type") == "market"]


@pytest.mark.asyncio
async def test_the_specimen_card_is_withheld_and_does_not_come_back_as_a_market():
    payload = await _serve([_Market(WREXHAM), _Market(DENMARK), _Market(INNING)])
    assert not any("Wrexham" in t for t in _exact_titles(payload))
    assert WREXHAM[0] not in _market_card_ids(payload)


@pytest.mark.asyncio
async def test_a_priced_exact_score_card_ships_once():
    payload = await _serve([_Market(WREXHAM), _Market(DENMARK), _Market(INNING)])
    assert sum("Denmark" in t for t in _exact_titles(payload)) == 1
    # The duplicate half: its market no longer ships again as a plain card.
    assert DENMARK[0] not in _market_card_ids(payload)
    denmark = next(c for c in payload["feed"] if "Denmark" in c.get("title", ""))
    assert denmark["points"][0]["label"] == "1–1"


@pytest.mark.asyncio
async def test_a_short_field_with_buyers_keeps_its_card():
    payload = await _serve([_Market(GERMANY)])
    assert sum("Germany" in t for t in _exact_titles(payload)) == 1


@pytest.mark.asyncio
async def test_a_market_that_is_no_exact_score_is_untouched():
    payload = await _serve([_Market(WREXHAM), _Market(INNING)])
    assert _market_card_ids(payload) == [INNING[0]]
