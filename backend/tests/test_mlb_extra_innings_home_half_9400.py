"""#9400 — in extra innings the home side still bats in its bottom half.

`parse_baseball_state` counted remaining half-innings against a fixed 9, so from
the 10th on the home side had 0 half-innings in "Top N" / "Mid N". Variance
collapsed and any away lead printed 0.1% on the Bain Luck Model line (it feeds
the blend at weight 1.0) — a real late-game 0↔100 swing on the chart (#1932).

Specimen: `/events/15319731`, Dodgers @ Giants, 2026-09-27, LAD won 5-1 in 10.
The stored `stat_model` rows below are production values; the pre-fix function
reproduced all of them exactly from the row's own inputs (score, period, the
event's opening_home_probability 0.3157). Kalshi / Polymarket traded the same
minutes at 0.425 / 0.415 (Top 10th, 1-1) and 0.36 / 0.155 (Top 10th, 1-2).
"""

import pytest

from app.utils.win_probability import (
    compute_baseball_win_prob,
    compute_statistical_win_prob,
    parse_baseball_state,
)

SPECIMEN_OPENING_HOME_PROB = 0.3157

# (home, away, period, stored stat_model value on 15319731)
SPECIMEN_REGULATION_ROWS = [
    (1, 1, "Middle 8th", 0.5842),
    (2, 1, "Bottom 8th", 0.8262),
    (1, 1, "Bottom 8th", 0.5179),
    (1, 1, "End 9th", 0.513),
]
SPECIMEN_EXTRA_ROWS = [
    (1, 1, "Top 10th", 0.281),
    (1, 2, "Top 10th", 0.0049),
]

# Frozen from origin/master 447a414f80 before the change: (home_hi, away_hi).
# Regulation must not move by a single half-inning.
REGULATION_HALF_INNINGS = {
    "Top 1": (9, 8.5), "Mid 1": (9, 8), "Bottom 1": (8.5, 8), "End 1": (8, 8),
    "Top 2": (8, 7.5), "Mid 2": (8, 7), "Bottom 2": (7.5, 7), "End 2": (7, 7),
    "Top 3": (7, 6.5), "Mid 3": (7, 6), "Bottom 3": (6.5, 6), "End 3": (6, 6),
    "Top 4": (6, 5.5), "Mid 4": (6, 5), "Bottom 4": (5.5, 5), "End 4": (5, 5),
    "Top 5": (5, 4.5), "Mid 5": (5, 4), "Bottom 5": (4.5, 4), "End 5": (4, 4),
    "Top 6": (4, 3.5), "Mid 6": (4, 3), "Bottom 6": (3.5, 3), "End 6": (3, 3),
    "Top 7": (3, 2.5), "Mid 7": (3, 2), "Bottom 7": (2.5, 2), "End 7": (2, 2),
    "Top 8": (2, 1.5), "Mid 8": (2, 1), "Bottom 8": (1.5, 1), "End 8": (1, 1),
    "Top 9": (1, 0.5), "Mid 9": (1, 0), "Bottom 9": (0.5, 0), "End 9": (0, 0),
}


def _half_innings(period: str) -> tuple[float, float]:
    state = parse_baseball_state(period)
    assert state is not None, period
    return state["home_half_innings_remaining"], state["away_half_innings_remaining"]


@pytest.mark.parametrize("period,expected", sorted(REGULATION_HALF_INNINGS.items()))
def test_regulation_half_innings_unchanged(period, expected):
    assert _half_innings(period) == expected


@pytest.mark.parametrize("inning", [10, 11, 12, 15])
@pytest.mark.parametrize(
    "half,expected",
    [("Top", (1, 0.5)), ("Mid", (1, 0)), ("Bottom", (0.5, 0)), ("End", (0, 0))],
)
def test_extra_inning_keeps_the_home_bottom_half(inning, half, expected):
    """Top/Mid of an extra inning: home still has its whole bottom half."""
    assert _half_innings(f"{half} {inning}") == expected


@pytest.mark.parametrize("inning", [10, 11, 13])
@pytest.mark.parametrize("half", ["Top", "Middle", "Bottom", "End"])
@pytest.mark.parametrize("home,away", [(1, 1), (1, 2), (3, 2), (0, 4)])
def test_an_extra_inning_prices_like_the_ninth(inning, half, home, away):
    """Same score, same half: an extra inning is the 9th inning replayed.

    The two states leave identical half-innings to each side, so the model
    must print the same number — the Top 10th away lead may not read 0.1%
    while the Top 9th away lead reads ~20%.
    """
    ninth = compute_baseball_win_prob(
        home, away, f"{half} 9th", opening_home_probability=SPECIMEN_OPENING_HOME_PROB
    )
    extra = compute_baseball_win_prob(
        home, away, f"{half} {inning}th", opening_home_probability=SPECIMEN_OPENING_HOME_PROB
    )
    assert extra == pytest.approx(ninth, abs=1e-12)


@pytest.mark.parametrize("home,away,period,stored", SPECIMEN_REGULATION_ROWS)
def test_specimen_regulation_rows_still_reproduce(home, away, period, stored):
    """Control: every pre-extra-innings row on 15319731 is unchanged."""
    got = compute_baseball_win_prob(
        home, away, period, opening_home_probability=SPECIMEN_OPENING_HOME_PROB
    )
    assert round(got, 4) == stored


@pytest.mark.parametrize("home,away,period,stored", SPECIMEN_EXTRA_ROWS)
def test_specimen_extra_inning_rows_no_longer_collapse(home, away, period, stored):
    got = compute_baseball_win_prob(
        home, away, period, opening_home_probability=SPECIMEN_OPENING_HOME_PROB
    )
    assert round(got, 4) != stored
    # Home still bats: an away lead of one is not a settled game, and a tie
    # with home batting last is not a home underdog.
    if away > home:
        assert 0.10 < got < 0.40
    else:
        assert got > 0.5


def test_specimen_through_the_writer_entry_point():
    """The stat_model writers call `compute_statistical_win_prob`; prove it there."""
    got = compute_statistical_win_prob(
        home_score=1,
        away_score=2,
        clock=None,
        period="Top 10th",
        sport_key="baseball_mlb",
        opening_home_probability=SPECIMEN_OPENING_HOME_PROB,
    )
    assert got is not None
    assert 0.10 < got < 0.40
