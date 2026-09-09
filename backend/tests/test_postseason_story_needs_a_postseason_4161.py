"""#4161 — a market four years out does not hold a page-one Discover slot.

On the morning edition of 2026-09-09 (`GET /api/feed?limit=60`, production
`1e1650ee`), slot 16 was:

    score 81   Canadian Team to Win the Stanley Cup® Before the 2030-31 Season
               resolution_date 2030-06-30   (1,389 days out)   category hockey

It was filed as "Discover's ranking has no time-to-resolution term at all", and
that is true — `resolution_date` reached `compute_futures_highlight` as a
parameter and was read only for the `micro_bet` penalty (<=1 day) and the
`is_resolving_soon` flag (<=30 days). Past 30 days, a market resolving in two
months and a market resolving in four years scored identically.

🔴 BUT THE CAUSE IS SHARPER THAN THE ABSENCE, and the sharper reading is what
this fix is aimed at. Decomposed, that card's 81.5 was:

    category_base_hockey        18.5
    sports_postseason_story    +40      <-- half the card
    tier_1                     +10
    major_league                +8

`SPORTS_POSTSEASON_STORY_BOOST` is the largest single term in the file. It fires
on "<advance|reach|make|win|winner> ... <stanley cup|nba finals|world series|
super bowl|college football playoff>", and it exists because those read as
genuinely interesting even outside a marquee game. Nothing bounded it in time,
so it also paid +40 to a multi-season futures bet resolving in 2030. The card was
not merely un-penalised for being far away; it was actively boosted for being a
postseason story about a postseason four years from now.

So the fix bounds the boost rather than adding a blanket horizon penalty, and
that choice is what keeps the blast radius honest. Measured over every open
market matching the pattern (2026-09-09):

    no resolution_date     153   <- keeps the boost (unknown is not far)
    within 18 months         5   <- keeps the boost
    beyond 18 months         2   <- loses it, both multi-season hockey futures

A blanket time penalty would instead have reached the 2028 election cards, the
2030 World Cup card and eight MTV VMA categories, all of which are marquee
content the feed is right to carry.

THE TWO DIRECTIONS BOTH MATTER. A guard that only proves the far card is demoted
would pass if the boost were deleted outright, which would silently drop five
current-season Stanley Cup / Super Bowl markets off page one. Every test below
that asserts a demotion has a sibling asserting a survival.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.futures_highlights import (
    SPORTS_POSTSEASON_STORY_BOOST,
    SPORTS_POSTSEASON_STORY_HORIZON_DAYS,
    compute_futures_highlight,
)

#: A FIXED anchor. Gotcha #44: a test anchor must not branch on the clock, so
#: every horizon below is expressed as an offset FROM this constant and the
#: function is always handed the same `now`.
NOW = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)

#: The filed card, verbatim from the served payload.
FILED_NAME = "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season"
FILED_RESOLUTION = datetime(2030, 6, 30, 3, 59, tzinfo=timezone.utc)

#: Names that DO match the postseason-story pattern — the population this rule
#: can reach at all. Anything outside this set is untouched by the change and a
#: test using it would prove nothing.
POSTSEASON_NAMES = [
    "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season",
    "2026-27 Stanley Cup® Finals Winner",
    "Who will win Super Bowl LXI?",
    "Will the Knicks reach the NBA Finals?",
    "Who will win the World Series?",
]


def score(name, resolution_date, *, category="hockey", tier=1):
    return compute_futures_highlight(
        market_tier=tier,
        sport_category=category,
        resolution_date=resolution_date,
        outcomes=[{"name": "Yes", "probability": 0.42, "rank": 1}],
        source_count=1,
        now=NOW,
        market_name=name,
    )


# ── REACHABILITY: the specimens actually reach the rule ──────────────────────


@pytest.mark.parametrize("name", POSTSEASON_NAMES)
def test_every_specimen_really_is_a_postseason_story(name):
    """Asserted FIRST, because every test below is meaningless without it.

    If the pattern stopped matching these names, the demotion tests would still
    pass — the boost would be absent for the wrong reason — and the survival
    tests would fail confusingly. This pins the population the rule operates on.
    """
    result = score(name, NOW + timedelta(days=30))
    assert "sports_postseason_story" in result.reasons, (
        f"{name!r} no longer matches the postseason-story pattern, so the "
        "horizon tests below are not testing what they claim to test"
    )


# ── THE DEMOTION (the filed defect) ──────────────────────────────────────────


def test_the_filed_card_loses_the_postseason_boost():
    """The exact card from #4161, at its real resolution date."""
    result = score(FILED_NAME, FILED_RESOLUTION)
    assert "sports_postseason_story" not in result.reasons
    assert "postseason_story_beyond_horizon" in result.reasons


def test_the_filed_card_falls_out_of_page_one_range():
    """Not just 'lower' — low enough to stop being a page-one card.

    A demotion that moves a card from 81 to 79 would satisfy an inequality and
    change nothing a reader sees. The card scored 81.5 while its neighbours on
    the morning edition sat in the high 70s and 80s; what makes this a ship is
    that it lands well below them.
    """
    before = score(FILED_NAME, NOW + timedelta(days=30)).score
    after = score(FILED_NAME, FILED_RESOLUTION).score
    assert before - after == SPORTS_POSTSEASON_STORY_BOOST
    assert after < 50, f"expected a real demotion, got {after} (from {before})"


# ── THE SURVIVALS (what must not regress) ────────────────────────────────────


@pytest.mark.parametrize("name", POSTSEASON_NAMES)
def test_a_market_with_no_resolution_date_is_never_demoted(name):
    """UNKNOWN IS NOT FAR, and this is the big population.

    153 of the 160 open markets matching this pattern carry no `resolution_date`
    at all. Treating a missing date as a far horizon would have demoted almost
    every postseason market on the site — the failure direction that turns a
    two-market fix into an outage.
    """
    result = score(name, None)
    assert "sports_postseason_story" in result.reasons
    assert "postseason_story_beyond_horizon" not in result.reasons


@pytest.mark.parametrize(
    "days",
    [1, 30, 90, 200, 365, SPORTS_POSTSEASON_STORY_HORIZON_DAYS],
)
def test_a_postseason_inside_the_horizon_keeps_its_boost(days):
    """Current season and the one after it, including the boundary day itself."""
    result = score(FILED_NAME, NOW + timedelta(days=days))
    assert "sports_postseason_story" in result.reasons


@pytest.mark.parametrize("days", [SPORTS_POSTSEASON_STORY_HORIZON_DAYS + 1, 1025, 1389])
def test_a_postseason_beyond_the_horizon_loses_its_boost(days):
    """The far side of the boundary, and the two real markets (1,025d / 1,389d)."""
    result = score(FILED_NAME, NOW + timedelta(days=days))
    assert "sports_postseason_story" not in result.reasons


def test_the_boundary_is_a_single_day_wide():
    """Pins the comparison as `<=`, so an off-by-one is a failing test.

    Written as a delta between two adjacent days rather than two absolute
    scores, so it keeps meaning if the boost's magnitude changes.
    """
    inside = score(
        FILED_NAME, NOW + timedelta(days=SPORTS_POSTSEASON_STORY_HORIZON_DAYS)
    )
    outside = score(
        FILED_NAME, NOW + timedelta(days=SPORTS_POSTSEASON_STORY_HORIZON_DAYS + 1)
    )
    assert inside.score - outside.score == SPORTS_POSTSEASON_STORY_BOOST


# ── THE RULE REACHES NOTHING ELSE ────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,category",
    [
        ("2028 U.S. Presidential Election winner?", "politics"),
        ("2030 FIFA World Cup Champion", "soccer"),
        ("MTV Video Music Awards: Best Hip-Hop", "entertainment"),
        ("Brazil Presidential election winner?", "politics"),
    ],
)
def test_a_far_dated_market_that_is_not_a_postseason_story_is_untouched(name, category):
    """The reason this is a bounded boost and not a blanket horizon penalty.

    These are all far-dated — the 2030 World Cup card is 1,588 days out, further
    than the filed card — and all of them are marquee content the feed is right
    to carry. A time-to-resolution penalty applied to every futures market would
    have demoted the lot. Scoring them at a near date and a far date must give
    the same answer.
    """
    near = score(name, NOW + timedelta(days=30), category=category)
    far = score(name, NOW + timedelta(days=1588), category=category)
    assert near.score == far.score
    assert "postseason_story_beyond_horizon" not in far.reasons


def test_the_micro_bet_penalty_still_fires():
    """The other resolution-proximity rung, which now shares `days_until`.

    The hoist that gave the boost access to the horizon rewrote this ladder's
    guard from `resolution_date is not None` to `days_until is not None`. Those
    are the same condition, and this asserts they stayed the same condition.
    """
    result = score("Who will win the World Series?", NOW + timedelta(hours=12))
    assert "micro_bet" in result.reasons


def test_a_naive_resolution_date_is_still_understood():
    """The tz-normalisation moved with the hoist; it must still happen.

    A naive datetime reaching `(resolution_date - now)` raises, so a regression
    here is an exception on the serve path, not a wrong score.
    """
    naive = FILED_RESOLUTION.replace(tzinfo=None)
    result = score(FILED_NAME, naive)
    assert "postseason_story_beyond_horizon" in result.reasons
