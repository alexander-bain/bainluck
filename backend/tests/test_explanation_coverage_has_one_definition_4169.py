"""#4169 (D1, #4066) — `explanation-coverage@20` had two definitions of "explained".

`type == "event"` cards took an early-return branch in `diagnose_feed_items` with
their own predicate:

    "explanation_ok": bool(item.get("headline") or item.get("reason")),

while every other type reached `has_specific_explanation(...)`. So the hero card
of #4150 — `headline="Live"`, `reason=""`, nothing else — scored as explained,
because an empty reason costs nothing on the far side of an `or` and a state word
satisfies a bare `bool()`. **Coverage read 20/20 on a page whose top card was
blank**, twice measured on production (`f16be6ed`, then `25ca8741`).

🔴 EVERY ASSERTION HERE PINS THE ELIGIBLE DENOMINATOR. A coverage test that only
counts hits passes vacuously the moment fewer cards are diagnosed, so each one
says how many cards went in as well as how many scored.
"""

from app.utils.feed_market_quality import (
    classify_market_quality,
    has_specific_explanation,
)
from app.utils.feed_quality_debug import diagnose_feed_items, summarize_feed_diagnostics

# The card that was on production page one, verbatim in the fields the metric
# reads. A tidied fixture would stop testing the thing that failed.
BLANK_LIVE_EVENT = {
    "type": "event",
    "headline": "Live",
    "reason": "",
    "score": 35,
    "data": {
        "id": 15311182,
        "home_team": "San Francisco Giants",
        "away_team": "St. Louis Cardinals",
        "sport_name": "MLB",
        "home_team_data": {},
        "away_team_data": {"abbreviation": "STL"},
    },
}


def _futures(name: str, headline: str, reason: str) -> dict:
    return {
        "type": "futures",
        "headline": headline,
        "reason": reason,
        "score": 80,
        "data": {"name": name, "top_outcomes": [{"name": "Yes", "probability": 0.4}]},
    }


def _concept(name: str, headline: str, reason: str) -> dict:
    return {
        "type": "concept",
        "headline": headline,
        "reason": reason,
        "score": 80,
        "data": {"name": name, "top_outcomes": []},
    }


def _bundle(title: str, headline: str, reason: str) -> dict:
    return {
        "type": "bundle",
        "headline": headline,
        "reason": reason,
        "score": 85,
        "data": {"title": title, "items": [], "top_outcomes": []},
    }


def test_a_live_event_with_an_empty_reason_is_not_explained():
    """The exact card, and the exact number the metric printed over it."""
    top20 = [BLANK_LIVE_EVENT] + [
        _futures(
            f"Market {i}",
            f"Contender {i} leads at {40 + i}%",
            f"Contender {i} (4{i}%) leads Market {i}",
        )
        for i in range(19)
    ]
    diagnosed = diagnose_feed_items(top20)
    summary = summarize_feed_diagnostics(diagnosed, top_n=20)

    # The denominator, asserted: twenty cards went in and twenty were diagnosed,
    # so 19/20 below is a real miss and not a card that got skipped.
    assert len(top20) == 20
    assert summary["items"] == 20
    assert summary["top_n"] == 20

    assert diagnosed[0]["type"] == "event"
    assert diagnosed[0]["explanation_ok"] is False
    assert summary["explanation_ok_count"] == 19


def test_every_card_type_reaches_the_same_predicate():
    """The assertion that would have failed the day the branch was written.

    Not a source scan — each type is fed a card that is blank in exactly the way
    the event branch used to forgive, and each must be scored the same.
    """
    blank_by_type = [
        BLANK_LIVE_EVENT,
        _futures("Some Market", "Live", ""),
        _concept("Some Tournament", "Live", ""),
        _bundle("Some Bundle", "Live", ""),
    ]
    diagnosed = diagnose_feed_items(blank_by_type)

    assert len(diagnosed) == 4, "a type was dropped instead of scored"
    assert {c["type"] for c in diagnosed} == {"event", "futures", "concept", "bundle"}
    verdicts = {c["type"]: c["explanation_ok"] for c in diagnosed}
    assert verdicts == {
        "event": False,
        "futures": False,
        "concept": False,
        "bundle": False,
    }, f"types disagree about the same blank card: {verdicts}"


def test_an_event_that_says_something_still_counts():
    """The other direction — a metric that never passes is not a metric either."""
    explained = dict(BLANK_LIVE_EVENT, reason="Cardinals lead 4-2 in the 7th")
    diagnosed = diagnose_feed_items([explained])
    assert len(diagnosed) == 1
    assert diagnosed[0]["explanation_ok"] is True


def test_the_ranking_path_is_unchanged_by_the_new_argument():
    """`reason` is optional because the scorer does not have one yet.

    `apply_explanation_quality_score` runs before the reason line is composed. It
    passes no `reason`, and for every headline shape that matters the verdict
    must be identical to the pre-#4169 rule (`headline not in _GENERIC_HEADLINES`).
    """
    quality = classify_market_quality(
        market_name="MLB World Series Winner",
        sport_category="baseball",
        outcome_names=["Los Angeles Dodgers", "New York Yankees"],
    )
    for headline, expected in [
        ("Los Angeles Dodgers leads at 30%", True),
        ("New favorite: Hike 25bps (55%)", True),
        ("Live", True),  # unchanged WITHOUT a reason: the scorer has no copy yet
        ("Big odds movement", False),
        ("", False),
        (None, False),
    ]:
        assert (
            has_specific_explanation(
                hook_description=None, headline=headline, quality=quality
            )
            is expected
        ), f"ranking-path verdict moved for headline {headline!r}"


def test_a_state_word_needs_the_copy_beneath_it():
    """The rule the measuring path adds, stated on its own."""
    quality = classify_market_quality(
        market_name="Vuelta a España 2026",
        sport_category="cycling",
        outcome_names=["Jonas Vingegaard"],
    )
    assert not has_specific_explanation(
        hook_description=None, headline="Live", quality=quality, reason=""
    )
    assert not has_specific_explanation(
        hook_description=None, headline="Final", quality=quality, reason="   "
    )
    assert has_specific_explanation(
        hook_description=None,
        headline="Live",
        quality=quality,
        reason="General classification winner",
    )
    # A reason that is itself only a state word is the same blank card.
    assert not has_specific_explanation(
        hook_description=None, headline="Live", quality=quality, reason="Final"
    )
