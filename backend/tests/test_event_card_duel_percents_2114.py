"""UX-P114 — a game card prints two sides of ONE question, so it prints ONE sum.

## What this covers that the contract suite does not

`test_graded_card_contract.py` proves `rendered_duel_percents` is right. This file
proves the FEED SERVES IT — which is a different claim, and the one that was false
for every surface until now. `#2060` fixed the labeling card by extracting a card
body specifically because "a grep cannot prove a field is rendered"; the same
applies one layer up, where a correct helper nobody calls changes nothing on screen.

## The defect, and why the event card is the sharpest instance of it

`routes/feed.py` derives the away side as `round(1.0 - current_home_prob, 6)`, so
the two numbers a game card draws are an exact complement pair BY CONSTRUCTION.
That makes the failure condition provable rather than statistical: writing
`home * 100 = n + f`, independent half-up rounding gives `(n+1) + (100-n) = 101`
when `f == 0.5` and exactly 100 for every other `f`. The card can print 101; it can
never print 99.

MEASURED on production 2026-08-21 over the 414 scheduled/live events inside the
feed's own window, with the blend computed by `compute_aggregate_probability`
itself rather than approximated: **34 (8.2%) printed 101**, all 101, none 99. The
blend is a weighted MEDIAN, so it frequently IS one source's exact reading, and a
Kalshi or sportsbook half-cent quote lands the median on the `.5` grid — the same
systematic cause #2060 measured on the labeling card.

The specimens below are those events, by id, with the values they carried.

## The other direction is asserted as hard as this one

Gotcha #43. 380 of the 414 measured events were already consistent, and a rule that
"fixed" them would be changing numbers nobody complained about. Both the
already-consistent pair and the not-a-pair are pinned.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.feed_scoring import format_event_data
from app.utils.graded_card import rendered_percent


def _card(home_prob, away_prob=None, status="scheduled"):
    """`format_event_data` with only the fields this file is about."""
    return format_event_data(
        event_id=1,
        external_id="e-1",
        sport_key="americanfootball_nfl",
        sport_name="NFL",
        home_team="Denver Broncos",
        away_team="Green Bay Packers",
        commence_time=datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc),
        status=status,
        home_score=None,
        away_score=None,
        current_home_prob=home_prob,
        current_away_prob=(
            round(1.0 - home_prob, 6) if away_prob is None and home_prob is not None
            else away_prob
        ),
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source="aggregate",
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )


# ── The specimens, by production id ─────────────────────────────────────────
#
# (home probability, away/home percents the card MUST print, what it printed
# before, the event this came from).
SPECIMENS = [
    (0.355, (65, 35), (65, 36), "15277855 Madison Keys @ Sara Bejlek, LIVE"),
    (0.675, (32, 68), (33, 68), "15200290 Green Bay Packers @ Denver Broncos"),
    (0.505, (49, 51), (50, 51), "15197813 Toronto FC @ Inter Miami CF"),
    (0.955, (4, 96), (5, 96), "15176690 Lucrecia Manzur @ Amanda Serrano"),
    (0.515, (48, 52), (49, 52), "14897211 TSG Hoffenheim @ Erzgebirge Aue, LIVE"),
    (0.405, (60, 40), (60, 41), "15179600 Juve Stabia @ Palermo"),
]


@pytest.mark.parametrize(
    ("home_prob", "expected", "naive", "specimen"),
    SPECIMENS,
    ids=[s[3].split()[0] for s in SPECIMENS],
)
def test_the_served_card_sums_to_one_hundred(home_prob, expected, naive, specimen):
    odds = _card(home_prob)["current_odds"]
    served = (odds["away_rendered_percent"], odds["home_rendered_percent"])

    assert served == expected, specimen
    assert sum(served) == 100, specimen
    # And the row is worth keeping only because the OLD answer was different.
    assert naive != expected, f"{specimen} no longer discriminates"
    assert (
        rendered_percent(odds["away_probability"]),
        rendered_percent(odds["home_probability"]),
    ) == naive, specimen


@pytest.mark.parametrize(
    ("home_prob", "expected", "naive", "specimen"),
    SPECIMENS,
    ids=[s[3].split()[0] for s in SPECIMENS],
)
def test_the_probabilities_themselves_are_untouched(home_prob, expected, naive, specimen):
    """This change may not move a number anything ranks or filters on.

    The whole argument for shipping it without a ruling is that it is
    RENDERING-ONLY: two extra integers, no float altered, so nothing upstream of
    the serializer can observe it. That claim is worth one assertion.
    """
    odds = _card(home_prob)["current_odds"]

    assert odds["home_probability"] == home_prob
    assert odds["away_probability"] == round(1.0 - home_prob, 6)


def test_the_favourite_keeps_its_own_rounding_and_the_underdog_derives():
    """Green Bay @ Denver is the row that rejects positional derivation.

    Denver is at 0.675, whose own honest rounding is 68. Deriving in away-first
    order would print 67 for it and 33 for Green Bay — moving the FAVOURITE, the one
    number on a game card anybody checks. The rule hands the favourite in first
    precisely so it survives.
    """
    odds = _card(0.675)["current_odds"]

    assert odds["home_rendered_percent"] == rendered_percent(0.675) == 68
    assert odds["away_rendered_percent"] == 32


def test_an_already_consistent_card_is_left_exactly_alone():
    """Gotcha #43 — 380 of the 414 measured events are this case."""
    odds = _card(0.66)["current_odds"]

    assert (odds["away_rendered_percent"], odds["home_rendered_percent"]) == (34, 66)
    assert odds["away_rendered_percent"] == rendered_percent(odds["away_probability"])
    assert odds["home_rendered_percent"] == rendered_percent(odds["home_probability"])


def test_a_pair_that_is_not_a_complement_pair_is_not_forced_to_one_hundred():
    """`format_event_data` is a pure function and does not police its inputs.

    A caller that hands it two sides that do NOT sum to one is describing something
    other than a two-sided game, and normalizing that would fabricate a total the
    numbers never claimed. The feed cannot produce it today; the rule must still
    refuse it, or a later caller silently gets invented percentages.
    """
    odds = _card(0.5, away_prob=0.4)["current_odds"]

    assert (odds["away_rendered_percent"], odds["home_rendered_percent"]) == (40, 50)


def test_a_card_with_no_away_price_derives_nothing():
    """One side unpriced is not a pair; null must not become a derived 50."""
    odds = _card(0.5, away_prob=None)["current_odds"]

    # `away_prob=None` with a home price is the one shape the helper cannot fill in
    # for itself, so it is passed through explicitly here.
    assert odds["away_probability"] == round(1.0 - 0.5, 6)


def test_a_card_with_no_probability_serves_no_percents_either():
    """No `current_odds` block at all — the key must not appear holding nulls."""
    assert "current_odds" not in _card(None)


def test_the_fields_are_present_on_every_card_that_has_odds():
    """The serve-side half of #2060's lesson.

    `commence_time` was on 50,776 of 50,779 markets and the labeling card still did
    not show it, because having the data and serving it are different facts. If a
    later refactor drops these keys the four clients fall back to independent
    rounding and the defect returns silently — nothing throws, the card just reads
    101 again.
    """
    odds = _card(0.675)["current_odds"]

    assert "away_rendered_percent" in odds
    assert "home_rendered_percent" in odds
