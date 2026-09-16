"""#6482 — a binary card stops leading its caption with a seven-month-old move.

D1 clause (a) of #4066, verbatim: *"'From opening' becomes context and always
carries its date; it is never the headline reason."* The dated-and-demoted
branch in `compose_binary_card_copy` already runs after every time-anchored
signal, so a card only reaches it when nothing has happened lately — and then
it led its caption with the move anyway, because the move was the only sentence
it had.

Measured on production 2026-09-16 (v4610, `/api/feed?limit=60`, 390px): the top
two cards of page one read

    Down 22.5 points since Feb 3 — now 42% chance
    Down 7.7 points since Feb 19 — now 4% chance

and of the eight dated baselines served, seven were older than 30 days, five of
them citing one day — Feb 19, a bulk `opening_captured_at` capture date of
57,122 outcomes, i.e. when we first saw the row rather than a day anything
happened to it.

THE TWO SLOTS ARE NOT INTERCHANGEABLE, which is what makes this fixable without
a ranking change:

* a binary card RENDERS `context_summary` (the Taiwan card's whole DOM text is
  that caption and nothing else);
* `routes/feed.py` feeds `headline` to `explanation_score_rank`, where
  `has_specific_explanation` picks between the raw score and a 93/80/60 cap.

So every test below that pins a caption also pins that the headline did NOT
move. A future edit that "simplifies" the two arms into one string would be
caught by `test_the_headline_is_byte_identical_on_both_sides_of_the_horizon`.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.feed_reasons import (
    _LIFETIME_MOVE_NEWS_HORIZON_DAYS,
    compose_binary_card_copy,
)

NOW = datetime(2026, 9, 16, 5, 0, tzinfo=timezone.utc)

# The two specimens, with the values the page actually served.
STANLEY_CUP = "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season"
FEB_3 = datetime(2026, 2, 3, tzinfo=timezone.utc)
TAIWAN = "Will China invade Taiwan by end of 2026?"
FEB_19 = datetime(2026, 2, 19, tzinfo=timezone.utc)
# The one card on the same page whose baseline was inside the horizon.
OBAMACARE = "Will Trump issue Obamacare rebates before Election Day?"
SEP_10 = datetime(2026, 9, 10, tzinfo=timezone.utc)


def _copy(market_name, probability, change, opened_at, now=NOW):
    return compose_binary_card_copy(
        market_name=market_name,
        highlight_reasons=["major_surprise"],
        affirmative_probability=probability,
        top_surprise_change=change,
        top_surprise_opened_at=opened_at,
        now=now,
    )


# ---------------------------------------------------------------------------
# the ship: the stale move stops being the lead
# ---------------------------------------------------------------------------


def test_the_stanley_cup_card_states_its_answer_before_a_february_move():
    """Page one, position 1, exactly as served."""
    copy = _copy(STANLEY_CUP, 0.42, -0.225, FEB_3)
    assert copy.context_summary == "42% chance, down 22.5 points since Feb 3"


def test_the_taiwan_card_states_its_answer_before_a_february_move():
    """Page one, position 2, exactly as served."""
    copy = _copy(TAIWAN, 0.04, -0.077, FEB_19)
    assert copy.context_summary == "4% chance, down 7.7 points since Feb 19"


def test_a_recent_baseline_still_leads_with_the_move():
    """Inside the horizon the sentence is about this week and is unchanged.

    The point of the ship is not that a dated move is bad copy — it is that a
    SEVEN-MONTH-OLD one is not news. This is the control that keeps the fix from
    flattening the good case along with the bad.
    """
    copy = _copy(OBAMACARE, 0.58, -0.05, SEP_10)
    assert copy.context_summary == "Down 5 points since Sep 10 — now 58% chance"


def test_the_move_is_never_dropped_and_never_loses_its_date():
    """Demoted to context, not deleted. Both halves survive in both arms."""
    for opened_at in (FEB_3, SEP_10):
        copy = _copy(STANLEY_CUP, 0.42, -0.225, opened_at)
        assert "22.5 points" in copy.context_summary
        assert "since " in copy.context_summary
        assert "42% chance" in copy.context_summary


def test_the_direction_word_survives_the_reorder():
    """A collapsed affirmative still says DOWN (the #4758 contradiction)."""
    copy = _copy(TAIWAN, 0.065, -0.84, FEB_19)
    assert "down 84 points" in copy.context_summary
    assert "up 84 points" not in copy.context_summary.lower()

    rise = _copy(TAIWAN, 0.90, 0.39, FEB_19)
    assert "up 39 points" in rise.context_summary
    assert "down 39 points" not in rise.context_summary.lower()


# ---------------------------------------------------------------------------
# the ranking input must not move — this is what makes the change Tier A
# ---------------------------------------------------------------------------


def test_the_headline_is_byte_identical_on_both_sides_of_the_horizon():
    """The ONE assertion that licenses shipping this without a ranking review.

    Same move, same market, two baselines that differ only in falling either
    side of the horizon: the reader-visible caption differs and the headline —
    the string `explanation_score_rank` reads — does not. Written against the
    horizon constant rather than fixed dates so that moving the horizon cannot
    silently make this vacuous.
    """
    inside = NOW - timedelta(days=_LIFETIME_MOVE_NEWS_HORIZON_DAYS - 1)
    outside = NOW - timedelta(days=_LIFETIME_MOVE_NEWS_HORIZON_DAYS + 1)

    near = _copy(TAIWAN, 0.50, -0.05, inside)
    far = _copy(TAIWAN, 0.50, -0.05, outside)

    # The captions really do differ — otherwise this test proves nothing.
    assert near.context_summary != far.context_summary
    assert far.context_summary.startswith("50% chance,")
    assert near.context_summary.startswith("Down 5 points")

    # And the ranking input carries the move in both, in the same shape.
    assert near.headline.startswith("Down 5 points since ")
    assert far.headline.startswith("Down 5 points since ")


@pytest.mark.parametrize("days", [0, 1, 6, 7])
def test_the_horizon_boundary_is_inclusive_of_seven_days(days):
    """A baseline exactly ON the horizon is still news; day eight is not.

    Pinned because an off-by-one here is invisible on the page — it just moves
    one day's worth of cards between two sentences that both read fine.
    """
    copy = _copy(TAIWAN, 0.50, -0.05, NOW - timedelta(days=days))
    assert copy.context_summary.startswith("Down 5 points")


def test_day_eight_is_past_the_horizon():
    copy = _copy(TAIWAN, 0.50, -0.05, NOW - timedelta(days=8))
    assert copy.context_summary.startswith("50% chance,")


# ---------------------------------------------------------------------------
# the branch's existing guards still hold
# ---------------------------------------------------------------------------


def test_a_card_with_no_dateable_baseline_says_nothing_here():
    """An undated baseline is not "old" — it is unsayable, and the clause drops.

    `_baseline_is_older_than_news(None)` returning False must not be read as
    "recent": the caller never reaches the new arm at all, because
    `format_baseline_date` already returned None and the branch is skipped.
    """
    copy = compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["major_surprise"],
        affirmative_probability=0.42,
        top_surprise_change=-0.225,
        top_surprise_opened_at=None,
        now=NOW,
    )
    assert copy.context_summary == ""
    assert copy.headline == ""


def test_a_live_signal_still_outranks_the_lifetime_move():
    """Today's movement beats a stale baseline, reordered or not."""
    copy = compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["major_movement_24h", "major_surprise"],
        affirmative_probability=0.42,
        top_mover_change=0.06,
        top_surprise_change=-0.225,
        top_surprise_opened_at=FEB_3,
        now=NOW,
    )
    assert "today" in copy.context_summary
    assert "Feb 3" not in copy.context_summary


def test_the_reader_never_sees_the_words_from_opening():
    for opened_at in (FEB_3, SEP_10):
        copy = _copy(STANLEY_CUP, 0.42, -0.225, opened_at)
        assert "from opening" not in copy.context_summary
        assert "from opening" not in copy.headline
        assert "from opening" not in copy.reason
