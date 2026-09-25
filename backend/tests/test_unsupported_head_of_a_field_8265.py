"""#8265 — a leg nobody bids on or trades may not head a one-winner field.

WHAT A READER SAW. ``/futures/61308736`` (2027 US Open Men's Singles Winner)
crowned **Carlos Alcaraz at 5%**, and Discover page one repeated it ("Carlos
Alcaraz leads at 5%"). A market maker had pulled a 7¢ bid; the price fell back to
a five-day-old one-contract print; the legs above it were already withheld by
#7747. Every served leg on the board is bid 0.00 with a fresh zero 24-hour volume
reading, so none of them has any support a reader could lean on.

The specimen values below are the production rows, read 2026-09-25 12:51Z from
``futures_outcomes`` for markets 61308736 and 11371643 (Korea KBO Champion).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    leg_has_no_live_support,
    unsupported_legs_above_the_supported_head,
)

KALSHI = "kalshi"
SEEN = datetime(2026, 9, 25, 12, 51, 16, tzinfo=timezone.utc)

#: The production shape verdict on both specimen boards.
FIELD_SHAPE = {
    "v": 2,
    "shape": "field",
    "exhaustive": True,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "classifier_version": 2,
}

#: (name, probability, bid, ask, volume_24h). Every volume reading is fresh.
#: Mensik's 0.25 is the midpoint of his 0.03/0.47 book and #7747 withholds it,
#: which is why he is the first id passed as ``already_withheld`` below.
US_OPEN_MEN = [
    ("Jakub Mensik", 0.25, 0.03, 0.47, 0),
    ("Carlos Alcaraz", 0.05, 0.00, 0.47, 0),
    ("Casper Ruud", 0.03, 0.00, 0.57, 0),
    ("Arthur Fils", 0.01, 0.00, 0.74, 0),
    ("Frances Tiafoe", 0.01, 0.00, 0.01, 0),
    ("Novak Djokovic", 0.01, 0.00, 0.19, 0),
    ("Ben Shelton", 0.01, 0.00, 0.29, 0),
]

KBO = [
    ("KT Wiz", 0.40, 0.00, 0.55, 0),
    ("LG Twins", 0.28, 0.25, 0.31, 25),
    ("Doosan Bears", 0.23, 0.00, 0.28, 0),
    ("NC Dinos", 0.09, 0.00, 0.55, 0),
    ("Samsung Lions", 0.05, 0.05, 0.58, 0),
    ("Hanwha Eagles", 0.01, 0.00, 0.01, 0),
]


def _leg(i, name, p, bid, ask, vol, *, fresh=True, rs=None, is_winner=None):
    return SimpleNamespace(
        id=i,
        name=name,
        current_probability=p,
        current_yes_bid=bid,
        current_yes_ask=ask,
        volume_24h=vol,
        volume_24h_at=SEEN if fresh else SEEN - timedelta(hours=3),
        last_updated=SEEN,
        resolution_source=rs,
        is_winner=is_winner,
    )


def _market(legs, shape=FIELD_SHAPE, source=KALSHI, **leg_kwargs):
    return SimpleNamespace(
        id=1,
        source=source,
        market_type="field",
        market_metadata={"shape": shape},
        outcomes=[_leg(i, *row, **leg_kwargs) for i, row in enumerate(legs)],
    )


def _names(legs, ids):
    return {legs[i][0] for i in ids}


def _no_support(bid, ask, vol, **kw):
    kw.setdefault("source", KALSHI)
    kw.setdefault("resolution_source", None)
    return leg_has_no_live_support(
        kw["source"],
        kw["resolution_source"],
        bid,
        ask,
        volume_24h=vol,
        volume_24h_at=kw.get("volume_24h_at", SEEN),
        last_seen_at=SEEN,
    )


# --------------------------------------------------------------------------
# The per-leg half.
# --------------------------------------------------------------------------


def test_the_specimen_leg_has_no_live_support():
    """Alcaraz: bid 0.00 / ask 0.47, zero 24h volume on our latest look."""
    assert _no_support(0.00, 0.47, 0) is True


@pytest.mark.parametrize(
    "bid,ask,vol",
    [
        (0.03, 0.47, 0),  # Mensik: a real bid, however small
        (0.00, 0.47, 20.21),  # traded today
        (0.00, 0.00, 0),  # no offer either: not a book at all
    ],
)
def test_a_bid_a_trade_today_or_no_book_is_not_this_shape(bid, ask, vol):
    assert _no_support(bid, ask, vol) is False


@pytest.mark.parametrize("bid,ask", [(None, 0.47), (0.00, None)])
def test_an_unrecorded_side_fails_open(bid, ask):
    assert _no_support(bid, ask, 0) is False


def test_an_unread_or_stale_volume_reading_fails_open():
    assert _no_support(0.00, 0.47, None) is False
    assert (
        _no_support(0.00, 0.47, 0, volume_24h_at=SEEN - timedelta(minutes=1))
        is False
    )


def test_a_verdict_is_not_a_quote_but_a_retraction_is():
    assert _no_support(0.00, 0.47, 0, resolution_source="api_settlement") is False
    assert _no_support(0.00, 0.47, 0, resolution_source="ungradeable_result") is True


def test_only_kalshi_is_in_scope():
    assert _no_support(0.00, 0.47, 0, source="polymarket") is False


# --------------------------------------------------------------------------
# The column half.
# --------------------------------------------------------------------------


def test_with_no_supported_leg_every_unsupported_leg_goes():
    assert unsupported_legs_above_the_supported_head(
        [(1, 0.05, True), (2, 0.03, True), (3, 0.01, True)]
    ) == {1, 2, 3}


def test_unsupported_legs_below_the_supported_head_keep_their_number():
    """#8210's honest longshots: served, because something real sits above them."""
    assert unsupported_legs_above_the_supported_head(
        [(1, 0.40, True), (2, 0.28, False), (3, 0.23, True), (4, 0.01, True)]
    ) == {1}


def test_the_ceiling_is_strict_a_tie_keeps_its_number():
    assert unsupported_legs_above_the_supported_head(
        [(1, 0.28, True), (2, 0.28, False)]
    ) == set()


def test_a_supported_leg_is_never_withheld_however_it_ranks():
    assert unsupported_legs_above_the_supported_head(
        [(1, 0.01, False), (2, 0.90, False)]
    ) == set()


def test_an_empty_column_withholds_nothing():
    assert unsupported_legs_above_the_supported_head([]) == set()


def test_a_generator_is_read_once_and_still_answers():
    """The ceiling and the verdict both read the column; a one-shot iterable must
    not be exhausted by the first."""
    served = ((i, p, u) for i, p, u in [(1, 0.40, True), (2, 0.28, False)])
    assert unsupported_legs_above_the_supported_head(served) == {1}


# --------------------------------------------------------------------------
# The route arm.
# --------------------------------------------------------------------------


def test_the_specimen_board_serves_no_number():
    """Mensik is refused upstream, so the column a reader sees has no bid in it."""
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(US_OPEN_MEN)
    withheld = _unsupported_head_outcome_ids(market, {0})
    assert _names(US_OPEN_MEN, withheld) == {row[0] for row in US_OPEN_MEN[1:]}


def test_the_arm_counts_survivors_not_stored_rows():
    """With Mensik's bid still on the page, he is the head and the rest sit below him."""
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(US_OPEN_MEN)
    assert _unsupported_head_outcome_ids(market, set()) == set()


def test_the_kbo_board_hands_the_hero_to_the_team_somebody_is_trading():
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(KBO)
    assert _names(KBO, _unsupported_head_outcome_ids(market, set())) == {"KT Wiz"}


def test_a_leg_with_no_price_is_never_in_the_withheld_set():
    from app.routes.futures import _unsupported_head_outcome_ids

    legs = US_OPEN_MEN + [("never priced", None, 0.00, 0.50, 0)]
    market = _market(legs)
    assert len(legs) - 1 not in _unsupported_head_outcome_ids(market, {0})


def test_a_board_with_a_verdict_is_a_result_and_is_left_alone():
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(US_OPEN_MEN)
    market.outcomes[2].resolution_source = "api_settlement"
    market.outcomes[2].is_winner = True
    assert _unsupported_head_outcome_ids(market, {0}) == set()


@pytest.mark.parametrize(
    "shape",
    [
        {**FIELD_SHAPE, "exhaustive": False},
        {**FIELD_SHAPE, "expected_winners": 2},
        {**FIELD_SHAPE, "outcome_relation": "cumulative_thresholds"},
        {},
        None,
    ],
)
def test_a_market_whose_shape_is_not_proved_exclusive_is_untouched(shape):
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(US_OPEN_MEN, shape=shape)
    assert _unsupported_head_outcome_ids(market, {0}) == set()


def test_absent_volume_columns_withhold_nothing():
    """A caller whose rows never loaded the volume stamp must serve today's page."""
    from app.routes.futures import _unsupported_head_outcome_ids

    market = _market(US_OPEN_MEN)
    for o in market.outcomes:
        del o.volume_24h
        del o.volume_24h_at
    assert _unsupported_head_outcome_ids(market, {0}) == set()


# --------------------------------------------------------------------------
# Composition: the page and the card reach the same set.
# --------------------------------------------------------------------------


class _NoTrades:
    """A session that finds no snapshot rows: the trade-reading arms fail open."""

    async def execute(self, statement):
        return SimpleNamespace(all=lambda: [])


@pytest.mark.asyncio
async def test_the_page_composition_runs_this_arm_over_the_survivors():
    """Pinned on `_withheld_price_outcome_ids`, not the arm: a composition that
    skips the arm, or hands it `set()`, is invisible to the direct tests above.

    With no trade rows #7747 fails open on Mensik, so to exercise the
    survivors hand-off the fixture refuses him through the #6532 book arm instead
    (a price above his own ask), which needs no database.
    """
    from app.routes.futures import _withheld_price_outcome_ids

    legs = [("Jakub Mensik", 0.60, 0.03, 0.47, 0)] + US_OPEN_MEN[1:]
    market = _market(legs)
    withheld = await _withheld_price_outcome_ids(_NoTrades(), market)
    assert _names(legs, withheld) == {row[0] for row in legs}


@pytest.mark.asyncio
async def test_the_card_composition_reaches_the_same_set_as_the_page():
    from app.routes.futures import (
        _withheld_price_outcome_ids,
        withheld_price_outcome_ids_for_markets,
    )

    legs = [("Jakub Mensik", 0.60, 0.03, 0.47, 0)] + US_OPEN_MEN[1:]
    board = _market(legs)
    kbo = _market(KBO)
    kbo.id = 2
    kbo.outcomes = [_leg(100 + i, *row) for i, row in enumerate(KBO)]

    batched = await withheld_price_outcome_ids_for_markets(_NoTrades(), [board, kbo])
    assert batched[1] == await _withheld_price_outcome_ids(_NoTrades(), board)
    assert batched[2] == await _withheld_price_outcome_ids(_NoTrades(), kbo)
    assert batched[2] == {100}
