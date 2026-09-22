"""#7546 — the chart's ten slots stop going to legs that cannot draw a line.

WHAT A READER SAW. ``/api/futures/61461681`` (*FedEx Open de France Winner*, a
Kalshi board the Discover sample promoted) served **two** historical lines over a
**133**-outcome field: Oihan Guillamoundeguy and Stefano Mazzoli. Viktor Hovland,
Matthieu Pavon, Ryan Gerard, Cameron Smith and Michael Kim — the only five names
on that board carrying a real bid, the only five a person could trade — were not
on the chart at all, while holding supported points the whole time.

THE CAUSE IS THE SELECTION, NOT THE FILTER. ``current_probability`` is not always
a probability. On this board 128 of 133 legs quote ``yes_bid = 0.0000`` and store
their ASK in that column (127 of 133 have ``current_probability ==
current_yes_ask``), so the column sums to **17.60** over a field the classifier
proved single-winner. Ranking the top ten on it ranks by the size of an untaken
offer: the ten slots went to the ten biggest unsupported asks, #5898's filter then
refused them exactly as the ladder does, eight of the ten lost every point, and
two lines reached the reader. The five legs with a real bid rank **129th to
133rd** on that column and were never candidates.

Measured on production 2026-09-20 19:2xZ. Classifying the market's own rows with
``snapshot_price_is_unsupported`` reproduces the served payload exactly — 7 points
for Guillamoundeguy and 4 for Mazzoli — which is why the rows below are the
argument rather than an illustration of it.

EVERY PRICE IN THIS FILE IS A PRODUCTION ROW, read from ``futures_odds_snapshots``
for market 61461681 at 19:2xZ on 2026-09-20. Only the timestamps are synthesised,
and deliberately: they are offsets from ``now`` that preserve the real spacing, so
the fixture cannot age out of the seven-day window the chart asks for (gotcha
#44 — offset first, never anchor a test on a wall-clock date).

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it rather
than trust it:

- If the fixture stopped carrying the RANK INVERSION — a refused leg priced ABOVE
  a supported one — every route test here would pass on a board that had no
  choice to make. ``TestTheFixtureStillCarriesTheInversion`` asserts the
  inversion and each row's own verdict directly, so that decay is loud.
- If the selection were changed to show refused POINTS rather than to prefer
  chartable LEGS, the control below would grow points it has no right to.
  Guillamoundeguy's count is asserted UNCHANGED at 7 for that reason: the repair
  must move which legs are chosen and nothing about what a chosen leg may show.
- If the preference fired on every market rather than only where a slot was about
  to be wasted, healthy boards would reorder. ``TestTheCommonCaseCannotMove``
  asserts a field whose legs are all chartable keeps today's exact order.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.utils.futures_unsupported_price import snapshot_price_is_unsupported

# ── Production rows, market 61461681 ────────────────────────────────────────
# (probability, yes_bid, yes_ask, last_price), oldest first.
#
# Hovland, outcome 231407130, `current_probability` 0.095, field rank 129.
# Six stamps quoting an empty book, then a real two-sided 0.0200/0.1700 book
# arrives and the last two points become honest. This leg is the ship: two
# supported points that no reader could reach.
_HOVLAND = [
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.200000, 0.0000, 0.2000, 0.0000),
    (0.100000, 0.0200, 0.1800, 0.0000),
    (0.095000, 0.0200, 0.1700, 0.0000),
]
# Bairstow, outcome 231407085, `current_probability` 0.180 — priced ABOVE Hovland
# and charted today because of it. Nobody ever bid: eight stamps, `yes_bid`
# 0.0000 throughout and the venue's own trade price a flat 0.0000. Every point
# is refused, so the slot draws nothing at all.
_BAIRSTOW = [(0.200000, 0.0000, 0.2000, 0.0000)] * 6 + [
    (0.180000, 0.0000, 0.1800, 0.0000),
    (0.180000, 0.0000, 0.1800, 0.0000),
]
# Guillamoundeguy, outcome 231407123, `current_probability` 0.180. Same empty
# book as Bairstow, but the venue reports a 0.2000 TRADE from the second stamp
# on, which supports the price. Seven of its eight points are honest and it is
# one of the two lines production actually serves — the control.
_GUILLAMOUNDEGUY = [(0.200000, 0.0000, 0.2000, 0.0000)] + [
    (0.200000, 0.0000, 0.2000, 0.2000)
] * 5 + [
    (0.180000, 0.0000, 0.1800, 0.2000),
    (0.180000, 0.0000, 0.1800, 0.2000),
]

_HOVLAND_ID = 231407130
_BAIRSTOW_ID = 231407085
_GUILLAMOUNDEGUY_ID = 231407123

# The real spacing: eight captures across ~22.4 hours, most recent ~2.5h old.
_AGES_HOURS = [23.0, 19.0, 17.0, 15.0, 9.0, 7.0, 3.0, 2.5]


def _snap(oid, age_hours, prob, bid, ask, last):
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker="kalshi",
        probability=prob,
        yes_bid=bid,
        yes_ask=ask,
        last_price=last,
        captured_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )


def _series(oid, rows):
    return [_snap(oid, age, *row) for age, row in zip(_AGES_HOURS, rows)]


def _outcome(oid, name, prob, bid, ask):
    return SimpleNamespace(
        id=oid,
        name=name,
        team_id=None,
        probability_change_24h=None,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=None,
        is_winner=None,
        external_id=f"KXDPWORLDTOUR-FEODF26-{oid}",
    )


def _market(outcomes):
    """The production market row, including the shape verdict the rule reads.

    ``market_type='field'`` plus this ``shape`` block is what makes
    ``market_is_proved_exclusive_field`` true, which is the real board's state and
    the reason #6846's ask-only bound applies to these legs at all. Weakening it
    here would quietly test a different rule.
    """
    return SimpleNamespace(
        id=61461681,
        name="FedEx Open de France Winner",
        source="kalshi",
        market_type="field",
        # A real market row HAS one, and #7351's venue-history seam reads it.
        # Without it that seam logs an AttributeError it then swallows, which is
        # noise a later reader would have to re-diagnose.
        external_id="KXDPWORLDTOUR-FEODF26",
        outcomes=outcomes,
        resolution_date=None,
        market_metadata={
            "shape": {
                "shape": "field",
                "exhaustive": True,
                "expected_winners": 1,
                "outcome_relation": "competitors",
                "confidence": "high",
            },
            "kalshi_event_ticker": "KXDPWORLDTOUR-FEODF26",
        },
    )


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats.

    The repeat is what lets the sparse-extend tiers re-ask for a wider window
    without this file having to know how many tiers ran. They get the same rows
    back, so no tier can improve on the initial window and the selection under
    test is the one the assertions describe.

    THE SECOND ENTRY IS EMPTY, AND IS NOT A SNAPSHOT READ (#7747): the handler
    now asks `_unsupported_price_outcome_ids` whether this board withholds a
    leg, before any snapshot read, so the chart can refuse the #23 squeeze on
    the same boards the detail page refuses it on. An empty answer means "no
    trade rows found", which fails OPEN — nothing is withheld — so this board is
    field-complete and every assertion below is about the selection it was
    always about. It sits SECOND rather than last precisely so the repeat above
    still belongs to the snapshot query.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


async def _history(db, top_n):
    """Call the handler the way FastAPI does — every Query parameter RESOLVED.

    Omitting one hands the function the unresolved ``Query`` default object:
    ``top_n`` then raises inside ``min()`` and ``outcome_id`` reads as a
    single-outcome filter that skips the selection this file exists to measure.
    """
    return await futures_route.get_futures_history(
        61461681, outcome_id=None, hours=168, top_n=top_n, champion=None, db=db
    )


def _served(payload):
    return {
        entry["outcome_id"]: len(entry["history"]) for entry in payload["outcomes"]
    }


@pytest.fixture
def board():
    outcomes = [
        _outcome(_HOVLAND_ID, "Viktor Hovland", 0.095, 0.0200, 0.1700),
        _outcome(_BAIRSTOW_ID, "Sam Bairstow", 0.180, 0.0000, 0.1800),
        _outcome(_GUILLAMOUNDEGUY_ID, "Oihan Guillamoundeguy", 0.180, 0.0000, 0.1800),
    ]
    rows = (
        _series(_HOVLAND_ID, _HOVLAND)
        + _series(_BAIRSTOW_ID, _BAIRSTOW)
        + _series(_GUILLAMOUNDEGUY_ID, _GUILLAMOUNDEGUY)
    )
    rows.sort(key=lambda r: r.captured_at)
    return _market(outcomes), rows


class TestTheFixtureStillCarriesTheInversion:
    """The strawman guard. Every route test below is worthless if these rows
    stopped being what the issue described, and that can happen without anyone
    touching this file — the support predicate's arms live elsewhere."""

    def test_the_refused_leg_is_priced_above_the_supported_one(self, board):
        market, _ = board
        by_id = {o.id: o for o in market.outcomes}
        # Without this the board has no slot to misallocate and the repair has
        # nothing to do: Bairstow must OUTRANK Hovland on the column today's
        # selection sorts by.
        assert (
            by_id[_BAIRSTOW_ID].current_probability
            > by_id[_HOVLAND_ID].current_probability
        )

    @pytest.mark.parametrize("prob,bid,ask,last", _BAIRSTOW)
    def test_every_bairstow_row_is_refused_on_its_own_columns(
        self, prob, bid, ask, last
    ):
        assert (
            snapshot_price_is_unsupported(
                "kalshi", None, prob, bid, ask, last, in_exclusive_field=True
            )
            is True
        )

    @pytest.mark.parametrize("prob,bid,ask,last", _HOVLAND[-2:])
    def test_hovlands_two_bid_backed_rows_are_honest(self, prob, bid, ask, last):
        assert (
            snapshot_price_is_unsupported(
                "kalshi", None, prob, bid, ask, last, in_exclusive_field=True
            )
            is False
        )

    @pytest.mark.parametrize("prob,bid,ask,last", _HOVLAND[:6])
    def test_hovlands_empty_book_rows_are_refused(self, prob, bid, ask, last):
        assert (
            snapshot_price_is_unsupported(
                "kalshi", None, prob, bid, ask, last, in_exclusive_field=True
            )
            is True
        )


class TestTheReaderGetsTheContenderInsteadOfTheEmptySlot:
    """The served payload, which is the only thing that proves the wiring.

    These assert the PAYLOAD, never the predicate — #5876's lesson, where every
    test in a file passed with the new arm wired to nothing.
    """

    @pytest.mark.anyio
    async def test_the_two_slots_go_to_the_two_legs_that_can_draw(self, board):
        market, rows = board
        payload = await _history(
            _Session(_Result(value=market), _Result(rows=()), _Result(rows=rows)), top_n=2
        )
        served = _served(payload)

        # THE CHANGED NAMED FIELD: Hovland is charted, with exactly the two
        # points his book supports — not the six it does not.
        assert served.get(_HOVLAND_ID) == 2
        # THE UNCHANGED CONTROL: the leg production already serves keeps exactly
        # the seven points it already had. The repair moves which legs are
        # chosen and nothing about what a chosen leg may show.
        assert served.get(_GUILLAMOUNDEGUY_ID) == 7
        # The slot that drew nothing is the one that was reallocated.
        assert _BAIRSTOW_ID not in served

    @pytest.mark.anyio
    async def test_a_refused_leg_still_never_contributes_a_point(self, board):
        """Widening the board must not smuggle a refused point onto the chart."""
        market, rows = board
        payload = await _history(
            _Session(_Result(value=market), _Result(rows=()), _Result(rows=rows)), top_n=10
        )
        served = _served(payload)
        # With slots to spare Bairstow may be selected — it simply has nothing
        # honest to draw, so it contributes no points either way.
        assert served.get(_BAIRSTOW_ID, 0) == 0
        assert served.get(_HOVLAND_ID) == 2
        assert served.get(_GUILLAMOUNDEGUY_ID) == 7


class TestTheCommonCaseCannotMove:
    @pytest.mark.anyio
    async def test_a_board_whose_legs_all_draw_keeps_todays_order(self, board):
        """When every candidate is chartable the partition carries no
        information, so the order must be exactly today's probability order."""
        market, _ = board
        # Two legs, both fully supported, the lower-priced one listed FIRST so a
        # selection that ignored probability would be caught.
        hovland = _outcome(_HOVLAND_ID, "Viktor Hovland", 0.095, 0.0200, 0.1700)
        leader = _outcome(_GUILLAMOUNDEGUY_ID, "Oihan Guillamoundeguy", 0.180, 0.0000, 0.1800)
        market.outcomes = [hovland, leader]
        rows = _series(_HOVLAND_ID, _HOVLAND[-2:]) + _series(
            _GUILLAMOUNDEGUY_ID, _GUILLAMOUNDEGUY[1:3]
        )
        rows.sort(key=lambda r: r.captured_at)

        payload = await _history(
            _Session(_Result(value=market), _Result(rows=()), _Result(rows=rows)), top_n=1
        )
        served = _served(payload)
        assert _GUILLAMOUNDEGUY_ID in served
        assert _HOVLAND_ID not in served

    @pytest.mark.anyio
    async def test_a_window_with_nothing_supported_falls_back_whole(self, board):
        """With no chartable leg the partition is noise, so today's order stands
        and the sparse tiers below are left to reach further back — that case's
        own repair, not this one's."""
        market, _ = board
        market.outcomes = [
            _outcome(_BAIRSTOW_ID, "Sam Bairstow", 0.180, 0.0000, 0.1800),
            _outcome(_HOVLAND_ID, "Viktor Hovland", 0.095, 0.0000, 0.2000),
        ]
        rows = _series(_BAIRSTOW_ID, _BAIRSTOW) + _series(_HOVLAND_ID, _HOVLAND[:6])
        rows.sort(key=lambda r: r.captured_at)

        payload = await _history(
            _Session(_Result(value=market), _Result(rows=()), _Result(rows=rows)), top_n=1
        )
        # Nothing draws either way; what matters is that the highest-priced leg
        # is still the one selected, exactly as today.
        assert [e["outcome_id"] for e in payload["outcomes"]] in ([], [_BAIRSTOW_ID])
