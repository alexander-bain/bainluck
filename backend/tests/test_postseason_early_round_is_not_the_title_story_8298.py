"""#8298 — one round of the playoffs is not the postseason story.

Production, 2026-09-23 22:16Z, /discover at 390px: two cards a few slots apart
asked the same question about two teams —

    Will Dallas Stars advance to the Second Round of the 2027 Stanley Cup Playoffs?     40%
    Will Florida Panthers advance to the Second Round of the 2027 Stanley Cup Playoffs? 54%

Both served at 93 (trace: highlight 81.5 = category_base_hockey 18.5 +
sports_postseason_story 40 + tier_1 10 + major_league 8, then quality +12).
Dallas's assembled rank was 6. The Panthers market had no 24h volume at all.

`_SPORTS_POSTSEASON_STORY_RE` needs a verb plus an anchor phrase, and the anchor
phrases `stanley cup` / `college football playoff` also sit inside the name of an
EARLIER round ("... of the 2027 Stanley Cup Playoffs", "make College Football
Playoff Quarterfinals"). #4161 bounded the boost in time; these resolve May 2027,
inside that bound. So the fix bounds it by round.

BOTH DIRECTIONS: every demotion below has a sibling proving the title-story
markets (win the Cup, reach the Finals, make the championship game) keep it —
deleting the boost outright must fail this file.
"""

from datetime import datetime, timezone

import pytest

from app.utils.futures_highlights import (
    SPORTS_POSTSEASON_STORY_BOOST,
    compute_futures_highlight,
)

#: Fixed anchor (gotcha #44) — the day the defect was seen.
NOW = datetime(2026, 9, 23, 22, 16, tzinfo=timezone.utc)

#: The two served specimens' real resolution date (production row, 2027-05-05).
SECOND_ROUND_RESOLUTION = datetime(2027, 5, 5, 4, 0, tzinfo=timezone.utc)

#: Verbatim production names of per-team early-round rungs (open, 2026-09-23).
EARLY_ROUND_NAMES = [
    "Will Dallas Stars advance to the Second Round of the 2027 Stanley Cup Playoffs?",
    "Will Florida Panthers advance to the Second Round of the 2027 Stanley Cup Playoffs?",
    "Will Seattle Kraken advance to the Western Conference Finals of the 2027 Stanley Cup Playoffs?",
    "Will Buffalo Sabres advance to the Eastern Conference Finals of the 2027 Stanley Cup Playoffs?",
    "Will Alabama make College Football Playoff Quarterfinals?",
    "Will LSU make College Football Playoff Semifinals?",
]

#: The title story: markets the boost exists for. Verbatim production names.
TITLE_STORY_NAMES = [
    "Will Notre Dame Make the 2027 College Football Playoff National Championship Game?",
    "2026-27 Stanley Cup® Finals Winner",
    "Who will win Super Bowl LXI?",
    "Will the Knicks reach the NBA Finals?",
    "Who will win the World Series?",
    "Will Indiana Make the 2027 College Football Playoff National Championship Game?",
]


def score(name, resolution_date=SECOND_ROUND_RESOLUTION, *, category="hockey"):
    return compute_futures_highlight(
        market_tier=1,
        sport_category=category,
        resolution_date=resolution_date,
        outcomes=[{"name": "Yes", "probability": 0.40, "rank": 1}],
        source_count=1,
        now=NOW,
        market_name=name,
    )


@pytest.mark.parametrize("name", EARLY_ROUND_NAMES)
def test_an_early_round_rung_loses_the_title_boost(name):
    result = score(name)
    assert "sports_postseason_story" not in result.reasons
    assert "postseason_story_early_round" in result.reasons


@pytest.mark.parametrize("name", EARLY_ROUND_NAMES)
def test_an_early_round_rung_loses_it_with_no_resolution_date_too(name):
    """Most CFP rungs carry no resolution_date; the round, not the date, decides."""
    result = score(name, None)
    assert "sports_postseason_story" not in result.reasons
    assert "postseason_story_early_round" in result.reasons


@pytest.mark.parametrize("name", TITLE_STORY_NAMES)
def test_the_title_story_keeps_its_boost(name):
    result = score(name)
    assert "sports_postseason_story" in result.reasons
    assert "postseason_story_early_round" not in result.reasons


def test_the_served_card_drops_by_exactly_the_boost():
    """Same name with the round swapped for the title: the delta is the boost and
    nothing else, so the change touches one term."""
    early = score(EARLY_ROUND_NAMES[0]).score
    title = score(
        "Will Dallas Stars win the 2027 Stanley Cup?", SECOND_ROUND_RESOLUTION
    ).score
    assert title - early == SPORTS_POSTSEASON_STORY_BOOST


def test_the_served_card_leaves_headline_range():
    """81.5 on production; well under the high-70s/80s page-one neighbourhood now."""
    assert score(EARLY_ROUND_NAMES[0]).score < 50


@pytest.mark.parametrize(
    "name,category",
    [
        ("Champions League semifinal: who advances?", "soccer"),
        ("US Open Men's Singles Quarterfinal winner", "tennis"),
    ],
)
def test_an_early_round_word_without_the_anchor_is_untouched(name, category):
    """The round words only matter inside the postseason pattern."""
    result = score(name, category=category)
    assert "postseason_story_early_round" not in result.reasons
