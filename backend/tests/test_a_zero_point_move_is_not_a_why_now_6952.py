"""#6952 — a card stops saying "Down 0 points since Sep 18".

Found mystery-shopping page one, production 2026-09-18 12:50Z, 390px. Two 2027
Stanley Cup cards, one above the other:

    Down 0 points since Sep 18 — now 41% chance
    Down 0 points since Sep 18 — now 58% chance

and a third, past the news horizon: `87% chance, down 0 points since Sep 10`.
Three of 100 served items (`/api/feed?limit=100`).

The rows behind them have `current_probability == opening_probability`
EXACTLY — `61380701` is 0.415000 / 0.415000 with `opening_captured_at`
2026-09-18 11:29:22Z, 81 minutes before the shot — so this is not a rounding
artifact. It is a market that opened this morning and has not traded.

One missing guard produced three false claims at once:

1. a move that did not happen, printed as the reason the card is here;
2. a DIRECTION on it — `"Up" if change > 0 else "Down"` sends every zero down;
3. a "since" measured against today.

The dated rungs gated on `top_surprise_change is not None`, which asks whether
we HAVE a number, not whether anything happened. `_is_printable_move` asks the
second question, and the refused rung falls through to #4056's empty caption —
the supported state for a card with nothing to say.
"""

from datetime import datetime, timezone

import pytest

from app.utils.feed_reasons import (
    _is_printable_move,
    compose_binary_card_copy,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)

NOW = datetime(2026, 9, 18, 12, 50, tzinfo=timezone.utc)

# The two specimens, with the values the page actually served.
STARS = "Will Dallas Stars advance to the Second Round of the 2027 Stanley Cup Playoffs?"
CANES = (
    "Will Carolina Hurricanes advance to the Second Round of the 2027 Stanley Cup "
    "Playoffs?"
)
OPENED_TODAY = datetime(2026, 9, 18, 11, 29, 22, tzinfo=timezone.utc)
# The third specimen: same zero, baseline past the news horizon.
TESTIFY = "Will Jacob Coxon publicly testify before congress by December 31, 2026?"
SEP_10 = datetime(2026, 9, 10, 2, 15, tzinfo=timezone.utc)


def _binary(market_name, probability, change, opened_at=OPENED_TODAY):
    return compose_binary_card_copy(
        market_name=market_name,
        highlight_reasons=["major_surprise"],
        affirmative_probability=probability,
        top_surprise_change=change,
        top_surprise_opened_at=opened_at,
        now=NOW,
    )


class TestTheZeroMoveIsNeverPrinted:
    @pytest.mark.parametrize(
        "name,probability,opened_at",
        [
            (STARS, 0.415, OPENED_TODAY),
            (CANES, 0.575, OPENED_TODAY),
            (TESTIFY, 0.87, SEP_10),
        ],
    )
    def test_no_slot_claims_a_move(self, name, probability, opened_at):
        copy = _binary(name, probability, 0.0, opened_at)
        for slot in ("headline", "context_summary", "reason"):
            text = (getattr(copy, slot, None) or "") if copy else ""
            if not text and isinstance(copy, dict):
                text = copy.get(slot) or ""
            assert "0 points" not in text, (slot, text)
            assert "0 point" not in text, (slot, text)

    def test_the_direction_word_goes_with_it(self):
        # "Down" was the `else` of `> 0`, so an unmoved market always fell.
        copy = _binary(STARS, 0.415, 0.0)
        blob = " ".join(
            str(getattr(copy, slot, "") or "")
            for slot in ("headline", "context_summary", "reason")
        )
        assert "Down 0" not in blob
        assert "down 0" not in blob

    def test_the_todays_date_baseline_goes_with_it(self):
        # `opening_captured_at` 81 minutes ago cannot be what a "since" reads
        # against; killing the rung removes the date claim too.
        copy = _binary(STARS, 0.415, 0.0)
        blob = " ".join(
            str(getattr(copy, slot, "") or "")
            for slot in ("headline", "context_summary", "reason")
        )
        assert "since Sep 18" not in blob


class TestARealMoveStillPrints:
    """The fix keys on what ROUNDS to zero, not on a new interest threshold."""

    def test_a_tenth_of_a_point_survives(self):
        copy = _binary(STARS, 0.415, -0.001)
        blob = " ".join(
            str(getattr(copy, slot, "") or "")
            for slot in ("headline", "context_summary", "reason")
        )
        assert "0.1 points" in blob

    def test_the_production_taiwan_card_is_untouched(self):
        # The strongest why-now shape on the same page, from #6482's specimen.
        copy = compose_binary_card_copy(
            market_name="Will China invade Taiwan by end of 2026?",
            highlight_reasons=["major_surprise"],
            affirmative_probability=0.04,
            top_surprise_change=-0.077,
            top_surprise_opened_at=datetime(2026, 2, 19, 12, tzinfo=timezone.utc),
            now=NOW,
        )
        blob = " ".join(
            str(getattr(copy, slot, "") or "")
            for slot in ("headline", "context_summary", "reason")
        )
        assert "7.7 points since Feb 19" in blob


class TestThePredicateItself:
    @pytest.mark.parametrize("value", [None, 0.0, -0.0, 0.0004, -0.0004])
    def test_nothing_that_prints_as_zero_is_a_move(self, value):
        assert not _is_printable_move(value)

    @pytest.mark.parametrize("value", [0.001, -0.001, 0.077, -0.655, 1.0])
    def test_anything_that_prints_a_number_is(self, value):
        assert _is_printable_move(value)


class TestTheMultiOutcomeGeneratorsToo:
    """The same rung exists three more times; the reader reads all of them.

    The board specimen is the third Brazil card from the same morning's page
    one, whose served caption was `Augusto Cury odds shifted down 2.1 points
    today in Brazil Presidential Election First Round: 3rd Place`.
    """

    MARKET = "Brazil Presidential Election First Round: 3rd Place"
    COMMON = dict(
        highlight_reasons=["major_surprise"],
        top_surprise_name="Augusto Cury",
        top_surprise_is_printed=True,
        leader_name="Renan Santos",
        leader_probability=0.53,
        top_surprise_opened_at=OPENED_TODAY,
        now=NOW,
    )

    def _all_three(self, change):
        reason = generate_futures_reason(
            market_name=self.MARKET, top_surprise_change=change, **self.COMMON
        )
        headline = generate_futures_headline(
            market_name=self.MARKET, top_surprise_change=change, **self.COMMON
        )
        context = generate_futures_context_summary(
            headline=headline,
            highlight_reasons=self.COMMON["highlight_reasons"],
            market_name=self.MARKET,
            leader_name=self.COMMON["leader_name"],
            leader_probability=self.COMMON["leader_probability"],
            top_surprise_change=change,
            top_surprise_opened_at=OPENED_TODAY,
            now=NOW,
        )
        return {"reason": reason, "headline": headline, "context": context}

    def test_no_generator_prints_a_zero_move(self):
        for slot, text in self._all_three(0.0).items():
            assert "0 points" not in (text or ""), (slot, text)
            assert "Shifted since" not in (text or ""), (slot, text)
            assert "since Sep 18" not in (text or ""), (slot, text)

    def test_a_real_move_still_reaches_every_generator(self):
        served = self._all_three(-0.021)
        assert "2.1 points" in (served["reason"] or ""), served["reason"]
        assert "2.1 points" in (served["headline"] or ""), served["headline"]
