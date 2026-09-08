"""lane1/183 — #3948: Kalshi's own spread phrasing becomes readable, on the right axis.

**The defect.** `extract_spread_threshold` cannot read `Dallas wins by over 10.5
points`, so on 2026-09-08 every one of the 25 rungs of `Dallas vs New York:
Spread` (market 58728464, event 14637256) was unreadable as a spread. Population:
57,631 outcomes / 7,134 markets / 4,488 events, units `points` 28,837 /
`runs` 20,547 / `goals` 8,247.

**Why signing the threshold is not the fix.** The issue's acceptance asks only
for "a signed threshold". Measured on the real 25 rungs
(`artifacts-lane1-183/validate_3948_design.py`), that alone is *worse than no
arm*: a Kalshi spread market carries BOTH teams' ladders in one pool, so signing
interleaves two opposing ladders and yields 13 monotonicity violations and a
derived spread of **0.5 points at confidence 0.85** — confident, selected, and
wrong on a game the market prices at 3. Negating *and inverting* the away rungs
puts everything on one home-margin axis: 0 violations, **3.0 at 0.95**.

    P(Dallas wins by over 1.5) = 0.555  ==  P(home margin > -1.5) = 0.445

**The hazard this file exists to guard.** The sign is resolved from the rung's
team text against the event's teams, and getting it backwards inverts every
projected scoreline rather than merely losing it. Two traps, both measured:

  * the market title is no help — all 3 of 3 spread markets measured name the
    AWAY team first (`Dallas vs New York: Spread` on a page whose home team is
    New York; likewise `Minnesota vs Detroit`, `Chicago C vs Milwaukee`);
  * the rungs use Kalshi's disambiguated short forms — `New York G`,
    `Chicago WS`, `Los Angeles D` — never the event's team name, and
    `futures_outcomes.team_id` is 0 of 57,631 populated, so there is no id to
    fall back to.

So every orientation assertion here is made in BOTH directions: a guard that
only checks "Dallas is the favourite" passes just as happily on code that has
lost the sign entirely, because Dallas is favoured either way in some fixtures.
The route tests swap home and away and require the answer to mirror.

Route tests drive the REAL `get_event_odds_history` through the #3921/#3951
harness, for the reason that file states: a re-implemented filter is a filter
that can agree with the test and disagree with production.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import get_event_odds_history
from app.utils.binary_spread import (
    binary_to_implied_spread,
    extract_spread_threshold,
    margin_rung_on_home_axis,
    parse_margin_rung,
    resolve_rung_side,
)

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
)

UTC = timezone.utc
COMMENCE = datetime(2026, 9, 14, 0, 20, tzinfo=UTC)

#: Verbatim from production `futures_outcomes`, market 58728464, 2026-09-08.
#: Home is the Giants, so the `Dallas ...` rungs are the AWAY half.
NFL_RUNGS = (
    ("Dallas wins by over 1.5 points", 0.555),
    ("Dallas wins by over 2.5 points", 0.545),
    ("Dallas wins by over 3.5 points", 0.445),
    ("Dallas wins by over 4.5 points", 0.415),
    ("Dallas wins by over 5.5 points", 0.395),
    ("Dallas wins by over 6.5 points", 0.365),
    ("Dallas wins by over 7.5 points", 0.310),
    ("Dallas wins by over 9.5 points", 0.255),
    ("Dallas wins by over 10.5 points", 0.235),
    ("Dallas wins by over 13.5 points", 0.195),
    ("Dallas wins by over 14.5 points", 0.160),
    ("Dallas wins by over 16.5 points", 0.140),
    ("Dallas wins by over 17.5 points", 0.120),
    ("Dallas wins by over 20.5 points", 0.095),
    ("New York G wins by over 1.5 points", 0.385),
    ("New York G wins by over 2.5 points", 0.370),
    ("New York G wins by over 3.5 points", 0.295),
    ("New York G wins by over 4.5 points", 0.265),
    ("New York G wins by over 5.5 points", 0.255),
    ("New York G wins by over 6.5 points", 0.225),
    ("New York G wins by over 7.5 points", 0.175),
    ("New York G wins by over 9.5 points", 0.155),
    ("New York G wins by over 10.5 points", 0.135),
    ("New York G wins by over 13.5 points", 0.105),
    ("New York G wins by over 14.5 points", 0.085),
)

#: Verbatim from production, market 60405695, event 15307194 (#3951's page).
#: Home is Detroit, so the `Minnesota ...` rungs are the AWAY half.
MLB_RUNGS = (
    ("Detroit wins by over 1.5 runs", 0.375),
    ("Detroit wins by over 2.5 runs", 0.275),
    ("Detroit wins by over 3.5 runs", 0.195),
    ("Minnesota wins by over 1.5 runs", 0.325),
    ("Minnesota wins by over 2.5 runs", 0.225),
    ("Minnesota wins by over 3.5 runs", 0.165),
)

#: Verbatim from production, market 60405708.
MLB_TOTAL_RUNGS = (
    ("Over 2.5 runs scored", 0.955),
    ("Over 3.5 runs scored", 0.895),
    ("Over 4.5 runs scored", 0.845),
    ("Over 5.5 runs scored", 0.745),
    ("Over 6.5 runs scored", 0.665),
    ("Over 7.5 runs scored", 0.545),
    ("Over 8.5 runs scored", 0.475),
    ("Over 9.5 runs scored", 0.370),
    ("Over 10.5 runs scored", 0.305),
    ("Over 11.5 runs scored", 0.225),
    ("Over 12.5 runs scored", 0.185),
)


# ---------------------------------------------------------------------------
# Parsing — the phrasing the shipped extractor cannot read
# ---------------------------------------------------------------------------


def test_the_shipped_extractor_reads_none_of_the_production_rungs():
    """The defect, pinned. If this ever starts passing, #3948 regressed into v1.

    🔴 It must stay `None`. Teaching `extract_spread_threshold` to return a bare
    magnitude here is exactly the sign-only design measured at 13 monotonicity
    violations — the rung has to go through `margin_rung_on_home_axis` so it can
    be placed on an axis, and an unsigned magnitude cannot be.
    """
    for name, _ in NFL_RUNGS + MLB_RUNGS:
        assert extract_spread_threshold(name) is None, name


@pytest.mark.parametrize(
    "text,team,threshold",
    [
        ("Dallas wins by over 10.5 points", "Dallas", 10.5),
        ("New York G wins by over 1.5 points", "New York G", 1.5),
        ("Detroit wins by over 2.5 runs", "Detroit", 2.5),
        ("Chicago C wins by over 3.5 runs", "Chicago C", 3.5),
        # One production row carries a capitalised unit.
        ("Houston wins by over 6.5 Points", "Houston", 6.5),
        ("Arsenal wins by over 1.5 goals", "Arsenal", 1.5),
        ("A's wins by over 1.5 runs", "A's", 1.5),
    ],
)
def test_parse_margin_rung_reads_every_production_shape(text, team, threshold):
    assert parse_margin_rung(text) == (team, threshold)


@pytest.mark.parametrize(
    "text",
    [
        "Over 220.5",
        "Boston Celtics -9.5",
        "Moneyline",
        "1st 5 Innings Spread -1.5",
        # A player prop wearing the same verb. The unit is a closed set so that
        # this cannot reach the game's spread ladder.
        "Dean Kremer wins by over 6.5 outs",
        "",
    ],
)
def test_parse_margin_rung_refuses_everything_else(text):
    assert parse_margin_rung(text) is None


# ---------------------------------------------------------------------------
# Side resolution — the inversion hazard, asserted in both directions
# ---------------------------------------------------------------------------


def test_the_market_title_order_would_resolve_the_sign_backwards():
    """All 3 of 3 measured spread markets name the AWAY team first.

    This is the trap the resolver exists to avoid, stated as a test so the
    reason survives: `Dallas vs New York: Spread` belongs to a page whose HOME
    team is New York. Anything that reads position in the title inverts it.
    """
    home, away = "New York Giants", "Dallas Cowboys"
    title = "Dallas vs New York: Spread"
    assert title.startswith("Dallas")
    assert resolve_rung_side("Dallas", home, away) == "away"
    assert resolve_rung_side("New York G", home, away) == "home"


@pytest.mark.parametrize(
    "rung_team,home,away,expected",
    [
        # Kalshi's disambiguated short forms against real team names.
        ("New York G", "New York Giants", "Dallas Cowboys", "home"),
        ("Dallas", "New York Giants", "Dallas Cowboys", "away"),
        ("Chicago C", "Milwaukee Brewers", "Chicago Cubs", "away"),
        ("Milwaukee", "Milwaukee Brewers", "Chicago Cubs", "home"),
        ("Chicago WS", "Chicago White Sox", "Detroit Tigers", "home"),
        ("New York M", "New York Mets", "New York Yankees", "home"),
        ("New York Y", "New York Mets", "New York Yankees", "away"),
        ("Los Angeles D", "Los Angeles Dodgers", "Los Angeles Angels", "home"),
        ("Los Angeles A", "Los Angeles Dodgers", "Los Angeles Angels", "away"),
        # And the same pairs with the sides swapped: a resolver that has lost
        # the sign passes the rows above and fails these.
        ("New York G", "Dallas Cowboys", "New York Giants", "away"),
        ("Dallas", "Dallas Cowboys", "New York Giants", "home"),
        ("New York Y", "New York Yankees", "New York Mets", "home"),
    ],
)
def test_resolve_rung_side_both_orientations(rung_team, home, away, expected):
    assert resolve_rung_side(rung_team, home, away) == expected


@pytest.mark.parametrize(
    "rung_team,home,away",
    [
        # Ambiguous: matches both sides. Giants v Jets is a real fixture.
        ("New York", "New York Giants", "New York Jets"),
        ("Los Angeles", "Los Angeles Dodgers", "Los Angeles Angels"),
        # Names neither side — a mis-linked market from another game.
        ("Boston", "New York Giants", "Dallas Cowboys"),
        ("", "New York Giants", "Dallas Cowboys"),
        (None, "New York Giants", "Dallas Cowboys"),
        # Missing team names on the event.
        ("Dallas", None, None),
    ],
)
def test_an_unresolvable_rung_refuses_rather_than_guesses(rung_team, home, away):
    """🔴 Dropping a rung costs precision; guessing a side inverts the game."""
    assert resolve_rung_side(rung_team, home, away) is None
    assert margin_rung_on_home_axis(
        f"{rung_team} wins by over 1.5 points", 0.4, home, away
    ) is None


# ---------------------------------------------------------------------------
# The home-margin axis
# ---------------------------------------------------------------------------


def test_an_away_rung_is_negated_AND_inverted():
    """The half that signing alone leaves out.

    `P(Dallas wins by over 1.5) = 0.555` is `P(home margin > -1.5) = 0.445`.
    Both halves are asserted: a mutant that negates without inverting keeps the
    threshold assertion and fails the probability one, and vice versa.
    """
    home, away = "New York Giants", "Dallas Cowboys"

    away_rung = margin_rung_on_home_axis(
        "Dallas wins by over 1.5 points", 0.555, home, away
    )
    assert away_rung == {"threshold": -1.5, "probability": pytest.approx(0.445)}

    home_rung = margin_rung_on_home_axis(
        "New York G wins by over 1.5 points", 0.385, home, away
    )
    assert home_rung == {"threshold": 1.5, "probability": pytest.approx(0.385)}


def _ladder(rungs, home, away):
    built = []
    for name, prob in rungs:
        contract = margin_rung_on_home_axis(name, prob, home, away)
        assert contract is not None, name
        built.append(contract)
    return built


def test_the_real_nfl_ladder_is_monotonic_and_prices_the_game_the_market_prices():
    """25 real rungs, one axis, and the number the hero agrees with.

    Sign-only produces 13 monotonicity violations here and derives -0.5;
    sign-and-invert produces 0 and derives -3.0. Both are asserted, because the
    violation count is what explains the number.
    """
    home, away = "New York Giants", "Dallas Cowboys"
    ladder = _ladder(NFL_RUNGS, home, away)
    assert len(ladder) == 25

    ordered = sorted(ladder, key=lambda c: c["threshold"])
    violations = [
        (lo, hi) for lo, hi in zip(ordered, ordered[1:])
        if hi["probability"] > lo["probability"] + 1e-9
    ]
    assert violations == []

    result = binary_to_implied_spread(ladder)
    assert result is not None
    # Positive => the HOME team (Giants) is the underdog, i.e. Dallas favoured.
    assert result.spread == pytest.approx(3.0, abs=0.05)
    assert result.confidence > 0.3

    # And mirrored: with the sides swapped the same rungs must favour the other
    # way by the same margin. This is what a sign-blind implementation cannot do.
    mirrored = binary_to_implied_spread(_ladder(NFL_RUNGS, away, home))
    assert mirrored is not None
    assert mirrored.spread == pytest.approx(-3.0, abs=0.05)


def test_sign_only_would_have_shipped_a_confident_wrong_number():
    """The rejected design, kept executable so the choice is not just prose.

    This is the measurement that overrode the issue's stated acceptance: it is
    not merely noisier, it brackets [-1.5, +1.5] by accident and reports high
    confidence on a spread that is off by a factor of six.
    """
    home, away = "New York Giants", "Dallas Cowboys"
    sign_only = []
    for name, prob in NFL_RUNGS:
        team, threshold = parse_margin_rung(name)
        side = resolve_rung_side(team, home, away)
        signed = threshold if side == "home" else -threshold
        sign_only.append({"threshold": signed, "probability": prob})

    ordered = sorted(sign_only, key=lambda c: c["threshold"])
    violations = [
        1 for lo, hi in zip(ordered, ordered[1:])
        if hi["probability"] > lo["probability"] + 1e-9
    ]
    assert len(violations) == 13

    bad = binary_to_implied_spread(sign_only)
    assert bad is not None
    assert bad.spread == pytest.approx(0.5, abs=0.05)
    assert bad.confidence > 0.8  # confident, and wrong


# ---------------------------------------------------------------------------
# The real route
# ---------------------------------------------------------------------------


def _event(event_id, home, away, sport_key):
    return SimpleNamespace(
        id=event_id,
        status="scheduled",
        commence_time=COMMENCE,
        completed_at=None,
        home_team_name=home,
        away_team_name=away,
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key=sport_key),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.5}},
    )


async def _projection(event, futures_markets):
    session = _DispatchingSession(event, futures_markets)
    payload = await get_event_odds_history(
        event_id=event.id, hours=720, response=MagicMock(headers={}), db=session
    )
    return payload.get("pm_spread_data") or {}


def _mlb_markets(spread_title):
    return [
        _market(
            "kalshi",
            [_outcome(n, p) for n, p in MLB_RUNGS],
            name=spread_title,
        ),
        _market(
            "kalshi",
            [_outcome(n, p) for n, p in MLB_TOTAL_RUNGS],
            name="Minnesota vs Detroit: Total Runs",
        ),
    ]


async def test_3951s_page_projects_a_real_mlb_scoreline():
    """#3951's first acceptance criterion, which #3948 is what delivers.

    Event 15307194 served `Projected final: 2 – 0` before #3951 and nothing at
    all after it, because Kalshi's spread ladder was unreadable. With the ladder
    on the home-margin axis the page prices at Detroit 4.1 – 3.9 Minnesota.

    🔴 `spread_source` is pinned, not just the sign of the scores: a projection
    that fell back to some other arm could produce two positive numbers and pass
    a nonnegative-only assertion for the wrong reason.
    """
    event = _event(15307194, "Detroit Tigers", "Minnesota Twins", "baseball_mlb")
    data = await _projection(event, _mlb_markets("Minnesota vs Detroit: Spread"))

    projected = data.get("projected_final")
    assert projected is not None
    assert projected["spread_source"] == "kalshi"
    assert projected["total_source"] == "kalshi"
    assert projected["home_score"] > 0 and projected["away_score"] > 0
    assert projected["home_score"] == pytest.approx(4.1, abs=0.15)
    assert projected["away_score"] == pytest.approx(3.9, abs=0.15)

    kalshi_spread = data["implied_spreads"]["kalshi"]
    assert kalshi_spread["confidence"] > 0.3
    assert len(kalshi_spread["contracts"]) == 6


async def test_swapping_home_and_away_mirrors_the_projected_scoreline():
    """The orientation guard on the real route.

    Same six rungs, same market title — only the event's home/away swap. If the
    resolver ever reads the title instead of the event, or loses the sign, this
    is the test that catches it: the favourite must follow the teams, not the
    text.
    """
    upright = await _projection(
        _event(15307194, "Detroit Tigers", "Minnesota Twins", "baseball_mlb"),
        _mlb_markets("Minnesota vs Detroit: Spread"),
    )
    flipped = await _projection(
        _event(15307194, "Minnesota Twins", "Detroit Tigers", "baseball_mlb"),
        _mlb_markets("Minnesota vs Detroit: Spread"),
    )

    a, b = upright["projected_final"], flipped["projected_final"]
    assert a["home_score"] == pytest.approx(b["away_score"], abs=0.05)
    assert a["away_score"] == pytest.approx(b["home_score"], abs=0.05)
    # Detroit is the favourite in both readings — it just changes column.
    assert a["home_score"] > a["away_score"]
    assert b["away_score"] > b["home_score"]


async def test_an_unresolvable_ladder_serves_no_spread_arm_rather_than_a_guess():
    """A mis-linked spread market names neither team: every rung drops.

    The page loses the arm — it does not gain an inverted one.
    """
    event = _event(15307194, "Detroit Tigers", "Minnesota Twins", "baseball_mlb")
    markets = [
        _market(
            "kalshi",
            [
                _outcome("Boston wins by over 1.5 runs", 0.375),
                _outcome("Baltimore wins by over 1.5 runs", 0.325),
                _outcome("Boston wins by over 2.5 runs", 0.275),
            ],
            name="Boston vs Baltimore: Spread",
        ),
        _market(
            "kalshi",
            [_outcome(n, p) for n, p in MLB_TOTAL_RUNGS],
            name="Minnesota vs Detroit: Total Runs",
        ),
    ]
    data = await _projection(event, markets)
    assert "kalshi" not in (data.get("implied_spreads") or {})
    assert not data.get("projected_final")
