"""ux/1036 Tier A — the settled game card's payload carries a per-team prior.

`format_event_data` is the ONE serializer behind every `/api/feed` game card, so
this is where "the card has a number to print" becomes a fact rather than a hope.

The two things asserted here that the pure-ladder tests cannot: that the new key
does not disturb `opening_odds` (three clients and the upset/confidence logic read
it), and that the pair is rounded ONCE — UX-P114's rule, on its third strip.
"""

from datetime import datetime, timezone

import pytest

from app.utils.feed_scoring import format_event_data


def _event(**overrides):
    kwargs = dict(
        event_id=1,
        external_id="x",
        sport_key="baseball_mlb",
        sport_name="MLB",
        home_team="Cincinnati Reds",
        away_team="San Diego Padres",
        commence_time=datetime(2026, 9, 2, 23, 10, tzinfo=timezone.utc),
        status="completed",
        home_score=3,
        away_score=5,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )
    kwargs.update(overrides)
    return format_event_data(**kwargs)


def test_a_settled_card_gets_a_per_team_prior_from_the_prediction_market():
    data = _event(
        prematch_by_source={"kalshi": (0.60, 0.40), "polymarket": (0.65, 0.35)},
        opening_home_prob=0.55,
        opening_away_prob=0.45,
        win_probability_sources={"kalshi": {"value": 0.60, "updated_at": "2026-09-02T22:59:00Z"}},
    )
    assert data["prematch_odds"]["home_probability"] == 0.60
    assert data["prematch_odds"]["away_probability"] == 0.40
    assert data["prematch_odds"]["source"] == "kalshi"
    for field, probability in (("source_mark", 0.60), ("away_source_mark", 0.40)):
        assert data["prematch_odds"][field] == {
            "state": "single",
            "sources": [{
                "key": "kalshi", "name": "Kalshi", "probability": probability,
                "observed_at": None, "reason": "observation_unknown",
            }],
        }


def test_the_books_opening_still_reaches_the_card_when_it_is_all_we_hold():
    """This is the 40/60 that used to be the `Opened` footnote — same number,
    now attributable and now attachable to a name."""
    data = _event(opening_home_prob=0.60, opening_away_prob=0.40)
    assert data["prematch_odds"]["source"] == "books"
    assert data["prematch_odds"]["home_probability"] == 0.60
    for field, probability in (("source_mark", 0.60), ("away_source_mark", 0.40)):
        assert data["prematch_odds"][field]["sources"] == [{
            "key": "betting", "name": "Sportsbooks", "probability": probability,
            "observed_at": None, "reason": "observation_unknown",
        }]


@pytest.mark.parametrize("away", [None, 0.20])
def test_rebuilt_away_odds_do_not_credit_the_selected_rung_with_the_substitute(away):
    data = _event(prematch_by_source={
        "kalshi": (0.61, away),
        "polymarket": (0.61, 0.39),
    })
    prior = data["prematch_odds"]
    assert prior["home_probability"] == 0.61
    assert prior["away_probability"] == 0.39
    assert prior["source_mark"]["sources"][0]["key"] == "kalshi"
    assert prior["away_source_mark"] == {
        "state": "none", "sources": [], "reason": "source_evidence_incomplete",
    }


def test_opening_odds_is_untouched_by_any_of_this():
    """`opening_odds` is read by the upset reason, the confidence signal, the
    native arms and the widget. The new key is additive or it is a regression
    wearing a feature's name."""
    data = _event(
        prematch_by_source={"kalshi": (0.60, 0.40)},
        opening_home_prob=0.55,
        opening_away_prob=0.45,
        opening_favorite="home",
    )
    assert data["opening_odds"] == {
        "home_probability": 0.55,
        "away_probability": 0.45,
        "favorite": "home",
    }


def test_the_pair_is_rounded_once_so_it_cannot_print_101():
    """UX-P114 / #2060, third strip. A normalized pair on a half-cent grid puts
    BOTH sides on a `.5` boundary at once and half-up rounds both UP: 73.5 -> 74
    beside 26.5 -> 27. Two individually-correct numbers, one impossible card."""
    data = _event(prematch_by_source={"polymarket": (0.735, 0.265)})
    served = data["prematch_odds"]
    assert served["home_rendered_percent"] + served["away_rendered_percent"] == 100


def test_no_reading_anywhere_emits_no_key_at_all():
    """An absent key is how the card knows to leave the space empty. An empty
    object would be a reading of nothing."""
    assert "prematch_odds" not in _event()


def test_a_live_card_still_carries_its_prior_across_the_status_flip():
    """Emitted for any status, not only settled ones. A status is a moment and
    the feed payload is CACHED, so a card that turns FINAL between two pulls must
    not lose its prior on the way."""
    data = _event(status="live", opening_home_prob=0.60, opening_away_prob=0.40)
    assert data["prematch_odds"]["source"] == "books"
