"""#8192 — the Champion column stops printing Polymarket numbers nothing stands behind.

## what a reader saw

``/playoffs/ncaa-basketball``, Champion column, per-source marks under each
headline: UConn ``P19``, Illinois ``P15``, North Carolina ``P11``, VCU ``P8``,
beside sportsbook and Kalshi marks of 1-5%. Seventeen Polymarket legs summed to
**1.58** for one title.

## the cases are production's rows

Every book below is the stored row on market 59698973 (``polymarket:927445``,
"2027 Men's College Basketball National Champion"), read 2026-09-30 ~06:30Z, and
every ``last_price`` is that leg's newest Polymarket snapshot. The market's
fresh, ungraded legs sum to **2.03**. The six other grids' Polymarket champion
markets, read the same hour, sum to 1.02-1.07. That gap is the control.

## what this file cannot see

Every assertion here is a unit call. A mutant that deletes the call site in
``get_playoff_grid`` leaves all of it green; that is
``tests/integration/test_grid_polymarket_unbacked_8192_pg.py``'s job.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.playoffs import (
    _SINGLE_WINNER_COLUMNS,
    _grid_polymarket_leg_is_unbacked,
    _grid_polymarket_leg_needs_backing,
    _grid_venue_column_sum,
)
from app.utils.feed_market_quality import EMPTY_BOOK_MAX_BID, FEED_EXCLUSIVE_SUM_MAX
from app.utils.playoff_grid import EXPECTED_COLUMN_SUMS

#: The specimen market's stored column (fresh, ungraded legs).
BROKEN_SUM = 2.03
#: NHL's Polymarket champion market, the highest of the six sound boards.
SOUND_SUM = 1.0715

#: ``(team, probability, bid, ask, newest last_price or None, withheld)``.
#: ``None`` for last_price is production's NULL: the venue reported no trade.
SPECIMEN = (
    # Withheld: no bid at all, one 18c offer, no trade. The midpoint of nothing
    # and an upper bound.
    ("VCU", 0.09, None, 0.18, None, True),
    # Withheld: a 4c bid is under the empty-book floor, 21c ask, no trade.
    ("North Carolina", 0.125, 0.04, 0.21, None, True),
    ("Houston", 0.115, 0.03, 0.20, None, True),
    ("Texas", 0.11, 0.02, 0.20, None, True),
    ("Gonzaga", 0.05, None, 0.10, None, True),
    # Withheld: it HAS a trade, at 74c, and serves 7%. A trade backs a price
    # only when it prints as that price.
    ("Alabama", 0.07, None, 0.14, 0.74, True),
    # Kept: a real trade at 22c on 2026-09-29, served at 0.22. Bid 1c, ask 59c.
    ("UConn", 0.22, 0.01, 0.59, 0.22, False),
    # Kept: a buyer at 10c. The only leg with volume ($17).
    ("Illinois", 0.175, 0.10, 0.25, None, False),
    # Kept: a buyer at 8c.
    ("Florida", 0.155, 0.08, 0.23, None, False),
)


def _unbacked(col, source, rs, p, bid, ask, last, *, evidence=None, total=BROKEN_SUM):
    return _grid_polymarket_leg_is_unbacked(
        col,
        source,
        rs,
        p,
        bid,
        ask,
        last,
        has_trade_evidence=(last is not None) if evidence is None else evidence,
        venue_column_sum=total,
    )


@pytest.mark.parametrize(
    "team,p,bid,ask,last,withheld", SPECIMEN, ids=[r[0] for r in SPECIMEN]
)
def test_the_specimen_board(team, p, bid, ask, last, withheld):
    assert _unbacked("championship", "polymarket", None, p, bid, ask, last) is withheld


def test_the_served_column_falls_to_the_legs_something_stands_behind():
    """The reader's sentence: three legs keep a Polymarket mark and they are the
    three with a buyer or a trade. Seventeen served legs summed to 1.58."""
    kept = {
        team
        for team, p, bid, ask, last, _ in SPECIMEN
        if not _unbacked("championship", "polymarket", None, p, bid, ask, last)
    }
    assert kept == {"UConn", "Illinois", "Florida"}


@pytest.mark.parametrize(
    "team,p,bid,ask,last,_withheld", SPECIMEN, ids=[r[0] for r in SPECIMEN]
)
def test_a_column_that_adds_up_asks_nothing(team, p, bid, ask, last, _withheld):
    """🔴 THE LOAD-BEARING GATE. The same books on a board that sums to 1.07.

    The six sound boards carry 25-26 unbid legs each (honest longshots). A
    mutant that drops the sum clause withholds every one of them.
    """
    assert (
        _unbacked("championship", "polymarket", None, p, bid, ask, last, total=SOUND_SUM)
        is False
    )


def test_the_sum_gate_is_strict_at_the_band_edge():
    """``> FEED_EXCLUSIVE_SUM_MAX``, matching #7808: a column AT the band's edge
    is still inside the band this codebase calls definitional."""
    assert _unbacked(
        "championship", "polymarket", None, 0.09, None, 0.18, None,
        total=FEED_EXCLUSIVE_SUM_MAX,
    ) is False
    assert _unbacked(
        "championship", "polymarket", None, 0.09, None, 0.18, None,
        total=FEED_EXCLUSIVE_SUM_MAX + 0.01,
    ) is True


def test_an_absent_column_sum_fails_open():
    assert _unbacked(
        "championship", "polymarket", None, 0.09, None, 0.18, None, total=None
    ) is False


def test_the_buyer_floor_is_the_shared_constant():
    """A bid AT the floor is no buyer; one tick above it is (``book_has_a_buyer``)."""
    at = _unbacked("championship", "polymarket", None, 0.12, EMPTY_BOOK_MAX_BID, 0.20, None)
    above = _unbacked(
        "championship", "polymarket", None, 0.13, EMPTY_BOOK_MAX_BID + 0.01, 0.20, None
    )
    assert (at, above) == (True, False)


def test_only_the_polymarket_leg_is_asked():
    """Kalshi and sportsbook legs on the same cell are other arms' business."""
    for source in ("kalshi", "odds_api", "datagolf_model", None):
        assert _unbacked("championship", source, None, 0.09, None, 0.18, None) is False
    assert _unbacked("championship", " Polymarket ", None, 0.09, None, 0.18, None) is True


@pytest.mark.parametrize(
    "col", ["title_game", "final_four", "conference", "pennant", "make_playoffs"]
)
def test_only_the_one_winner_column_is_asked(col):
    """A four-seat column sums past 1.25 honestly. Conference/pennant seat two and
    were not measured."""
    assert _unbacked(col, "polymarket", None, 0.09, None, 0.18, None) is False


def test_the_frame_is_the_grids_own_one_winner_columns():
    """The frame is not a guess: it is every column the grid normalises to 1.0."""
    one_winner = {k for k, v in EXPECTED_COLUMN_SUMS.items() if v == 1.0}
    assert _SINGLE_WINNER_COLUMNS == one_winner == {"championship"}


def test_a_verdict_is_never_withheld():
    """Settled means settled: a graded leg's number is a result."""
    assert _unbacked("championship", "polymarket", "api_settlement", 0.09, None, 0.18, None) is False


def test_no_book_at_all_passes_through():
    """Both sides NULL is a model price or a derived complement, not a book."""
    assert _unbacked("championship", "polymarket", None, 0.09, None, None, None) is False


def test_no_price_is_not_asked():
    assert _unbacked("championship", "polymarket", None, None, None, 0.18, None) is False


def test_the_trade_must_print_as_the_served_price():
    """Half a point (``_DISPLAY_ROUNDING``): 0.224 prints as 22%, 0.226 as 23%."""
    assert _unbacked("championship", "polymarket", None, 0.22, 0.01, 0.59, 0.224) is False
    assert _unbacked("championship", "polymarket", None, 0.22, 0.01, 0.59, 0.226) is True


def test_a_leg_the_trade_read_never_saw_is_not_backed():
    """Unlike #8243's Kalshi arm, absence does NOT spare the leg here: this runs
    only on a column already shown impossible, where a number needs positive
    support. A stray ``last_price`` with the evidence flag off must not back it."""
    assert _unbacked(
        "championship", "polymarket", None, 0.22, 0.01, 0.59, 0.22, evidence=False
    ) is True


@pytest.mark.parametrize(
    "team,p,bid,ask,last,withheld", SPECIMEN, ids=[r[0] for r in SPECIMEN]
)
def test_the_screen_never_misses_a_leg_the_verdict_withholds(
    team, p, bid, ask, last, withheld
):
    """The batched read fetches trades for exactly the screen's legs. A leg the
    verdict withholds but the screen skipped would be withheld with no trade
    looked up, which is how UConn would lose a number it has earned."""
    screened = _grid_polymarket_leg_needs_backing(
        "championship", "polymarket", None, p, bid, ask, venue_column_sum=BROKEN_SUM
    )
    if withheld:
        assert screened
    if not screened:
        assert not withheld


def _o(p, rs=None, age_days=0):
    return SimpleNamespace(
        current_probability=p,
        resolution_source=rs,
        last_updated=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


def test_the_venue_column_sum_reads_fresh_priced_quotes_only():
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    legs = [
        _o(0.5),
        _o(0.25),
        _o(None),                    # unpriced: not part of the column
        _o(1.0, rs="api_settlement"),  # a verdict is not a quote
        _o(0.9, age_days=30),        # the poller stopped touching it
    ]
    assert _grid_venue_column_sum(legs, cutoff) == pytest.approx(0.75)
