"""lane1/182 — a baseball page projected "8 – -6", and the repair CERT-2254 named.

Two things arrive together here because they are one defect seen from two sides.

**What the reader saw (#3951).** On production 2026-09-08 13:10Z the Detroit
Tigers v Minnesota Twins page (`events.id 15307194`) served:

    projected_final: {"home_score": 7.9, "away_score": -6.4,
                      "spread_source": "polymarket", "total_source": "kalshi"}

A team cannot score −6 runs. Polymarket names a market for the matchup alone —
`Detroit Tigers vs. Minnesota Twins` — and puts the scope in the OUTCOME:
`1st 5 Innings Spread -1.5`, `1st 5 Innings O/U 2.5`,
`Luke Keaschall: Home Runs O/U 0.5`. #3921's gate reads the MARKET name, so it
sees a matchup and lets all of it through; 38 home-run rungs then priced the run
total and the 1st-5-innings rungs derived a −14.25 spread. 7.9 − (−6.4) = 14.3.

**What the cert saw (CERT-2254, BLOCK).** The same shape reached through the
selector: `select_projection_source` picks the highest confidence, and a
contaminated pool whose rungs all sit at 1.000 reports confidence 1.0, so it
outranks a real Kalshi total. The grader's counterexample — a valid Kalshi
7.5/8.5 ladder at 0.9, a contaminated Polymarket ladder at 0.99, and a Kalshi
spread — returned `3.0 – -2.5` from `total_source=polymarket`. The required
repair is `3921-PROJECTION-SELECTION-CANNOT-EMIT-NEGATIVE-SCORES`: *"either
restore the prior source priority for this ship, or classify/filter outcome-level
scopes before confidence selection and reject invalid projected pairs with
fallback to the next valid source. Add a route regression containing a valid
Kalshi game total plus matchup-named Polymarket first-five/player-prop outcomes
and assert both displayed scores are nonnegative and the valid total wins."*

The second option is taken, not the first. Restoring the prior priority would
re-break the half of #3921 that was fixed on its own merits (a Kalshi arm at
confidence 0.3 beating a sportsbook arm at 1.0), and — measured — it would leave
`15307194` serving a negative score, because that page's negative was live on
master *before* #3921 and is not a regression #3921 introduced. Both halves of
the named repair are implemented:

  1. **classify/filter outcome-level scopes** — when a market's own name makes no
     quantity claim (`other`/`moneyline`), each outcome name is put through the
     same shipped classifier. This needed `_HALF_PATTERNS` to learn the
     `1st 5 innings` ordinal form, which it did not carry; that classifier is
     read by `_build_game_markets` too, so the change is swept on both surfaces.
  2. **reject invalid pairs with fallback** — `select_projected_final` walks
     (spread, total) pairs best-first and returns the first whose scores are
     renderable. When the preferred pair is renderable it returns exactly what
     picking each arm independently returns, so the walk is invisible except on
     the shape it exists for.

The route tests drive the REAL `get_event_odds_history` against a stubbed
session, the same convention as `test_projection_source_confidence_3921`: a
re-implemented filter is a filter that can agree with the test and disagree with
production.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import (
    _PM_OUTCOME_NEVER_PRICES_THE_GAME,
    _PM_SCOPES_DEFERRING_TO_OUTCOMES,
    _classify_game_market,
    get_event_odds_history,
)
from app.utils.binary_spread import (
    projected_final_score,
    projection_is_renderable,
    rank_projection_sources,
    select_projected_final,
    select_projection_source,
)

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
)

UTC = timezone.utc

#: The production specimen (#3951), so the fixture cannot drift away from it.
_SPECIMEN_ID = 15307194
COMMENCE = datetime(2026, 9, 9, 23, 40, tzinfo=UTC)

#: Kalshi's real ladder for this game — `Minnesota vs Detroit: Total Runs`,
#: 11 monotone rungs crossing 50% at about 8.0 runs.
REAL_MLB_TOTALS = (7.5, 8.5)

#: Polymarket's outcome text, verbatim from `futures_outcomes` on 15307194.
FIRST_FIVE_TOTALS = ("1st 5 Innings O/U 2.5", "1st 5 Innings O/U 3.5")
PLAYER_PROPS = (
    "Luke Keaschall: Home Runs O/U 0.5",
    "Colt Keith: Home Runs O/U 0.5",
)


def _event(sport_key="baseball_mlb", **overrides):
    event = SimpleNamespace(
        id=_SPECIMEN_ID,
        status="scheduled",
        commence_time=COMMENCE,
        completed_at=None,
        home_team_name="Detroit Tigers",
        away_team_name="Minnesota Twins",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key=sport_key),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.5}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


async def _projection(event, futures_markets=()):
    """Serve the real route and hand back its `pm_spread_data`."""
    session = _DispatchingSession(event, futures_markets)
    payload = await get_event_odds_history(
        event_id=event.id, hours=720, response=MagicMock(headers={}), db=session
    )
    return payload.get("pm_spread_data") or {}


def _kalshi_total_market(thresholds=REAL_MLB_TOTALS, *, confidence_probs=(0.70, 0.30)):
    """A real, tight game-total ladder — the one the page should price off."""
    lo_prob, hi_prob = confidence_probs
    return _market(
        "kalshi",
        [
            _outcome(f"Over {t}", lo_prob if i == 0 else hi_prob)
            for i, t in enumerate(thresholds)
        ],
        name="Minnesota vs Detroit: Total Runs",
    )


def _kalshi_spread_market():
    """A derivable Kalshi run-line, so the projection has a second arm."""
    return _market(
        "kalshi",
        [
            _outcome("Detroit win by 0.5+", 0.62),
            _outcome("Detroit win by 1.5+", 0.55),
            _outcome("Detroit win by 2.5+", 0.41),
        ],
        name="Minnesota vs Detroit: Run Line",
    )


def _polymarket_matchup_market():
    """Polymarket's matchup-named market, carrying the scope in its OUTCOMES.

    Every rung sits at 1.000, which is what makes the contaminated pool report
    `confidence: 1.0` and outrank a real arm — the grader's counterexample and
    production's own rows agree on this shape.
    """
    outcomes = [_outcome(name, 1.0) for name in FIRST_FIVE_TOTALS + PLAYER_PROPS]
    outcomes += [
        _outcome("1st 5 Innings Spread -1.5", 1.0),
        _outcome("1st 5 Innings Spread -2.5", 1.0),
    ]
    return _market("polymarket", outcomes, name="Detroit Tigers vs. Minnesota Twins")


# ---------------------------------------------------------------------------
# The regression CERT-2254 named, in the words it named it in
# ---------------------------------------------------------------------------


async def test_a_valid_kalshi_total_beats_matchup_named_polymarket_contamination():
    """The required repair's own acceptance test.

    A valid Kalshi game total plus matchup-named Polymarket first-five and
    player-prop outcomes: both displayed scores are nonnegative and the valid
    total wins. Before the repair the Polymarket pool reported confidence 1.0
    off rungs priced 1.000 and took the total arm, and the page rendered a
    negative score.
    """
    projection = await _projection(
        _event(),
        futures_markets=[
            _kalshi_total_market(),
            _kalshi_spread_market(),
            _polymarket_matchup_market(),
        ],
    )

    final = projection.get("projected_final")
    assert final is not None, "a real Kalshi ladder must still project a score"
    assert final["home_score"] >= 0
    assert final["away_score"] >= 0
    assert final["total_source"] == "kalshi"
    # The scoreline is the game's, not a half's: ~8 combined runs, not ~3.
    assert 6.0 <= final["home_score"] + final["away_score"] <= 10.0


async def test_no_projection_ever_carries_a_negative_component():
    """The invariant, stated where a reader would meet it.

    Whatever the pools contain, the served pair is a scoreline or there is no
    served pair. This is the assertion #3951's acceptance criterion asks for and
    the one that holds when a future venue invents a shape nobody has seen.
    """
    projection = await _projection(
        _event(),
        futures_markets=[
            _kalshi_total_market(),
            _kalshi_spread_market(),
            _polymarket_matchup_market(),
        ],
    )
    final = projection.get("projected_final") or {}
    for key in ("home_score", "away_score"):
        assert final.get(key, 0) >= 0


# ---------------------------------------------------------------------------
# Half 1 of the repair — the outcome-level scope pass
# ---------------------------------------------------------------------------


async def test_first_five_innings_rungs_never_price_a_nine_inning_game():
    """The `_HALF_PATTERNS` half, isolated: no Kalshi arm to hide behind.

    Polymarket alone, whose matchup-named market carries only first-five and
    player-prop rungs. There is no honest projection to make from it, so the
    page must serve none — the alternative it used to serve was `2.5` runs for a
    nine-inning game.
    """
    projection = await _projection(
        _event(), futures_markets=[_polymarket_matchup_market()]
    )
    assert projection.get("projected_final") is None
    assert "polymarket" not in (projection.get("implied_totals") or {})


async def test_a_real_spread_rung_in_a_matchup_named_market_still_reaches_the_spread():
    """The control that stops the outcome pass turning into an allowlist.

    `spread` is deliberately absent from `_PM_OUTCOME_NEVER_PRICES_THE_GAME`: a
    matchup-named Polymarket market is exactly where a game's real spread lives,
    and refusing it there would blank the projection on every page whose only
    spread comes from Polymarket. The rung may price the margin; it may not
    price the total.
    """
    market = _market(
        "polymarket",
        [
            _outcome("Spread -1.5", 0.62),
            _outcome("Spread -2.5", 0.41),
        ],
        name="Detroit Tigers vs. Minnesota Twins",
    )
    projection = await _projection(
        _event(), futures_markets=[market, _kalshi_total_market()]
    )
    assert "polymarket" in (projection.get("implied_spreads") or {}), (
        "a matchup-named market's own spread rungs must still derive a spread"
    )
    final = projection.get("projected_final")
    assert final is not None and final["home_score"] >= 0


async def test_a_market_that_declared_its_quantity_is_not_second_guessed():
    """`_PM_SCOPES_DEFERRING_TO_OUTCOMES` is two names, not "everything else".

    A Kalshi `…: Total Runs` market has already said what it prices, and its
    outcomes are bare `Over 7.5` strings. If the outcome pass ran on those it
    would be re-deciding a settled question on less information — and the day an
    outcome name is worded oddly, a real ladder vanishes.
    """
    assert _PM_SCOPES_DEFERRING_TO_OUTCOMES == frozenset({"other", "moneyline"})
    projection = await _projection(
        _event(),
        futures_markets=[_kalshi_total_market(), _kalshi_spread_market()],
    )
    totals = projection.get("implied_totals") or {}
    assert "kalshi" in totals
    assert 7.0 <= totals["kalshi"]["total"] <= 9.0


def test_the_classifier_reads_polymarkets_ordinal_first_five_form():
    """The `_HALF_PATTERNS` addition, at the classifier `_build_game_markets` shares.

    `first 5 innings` and `f5` were already carried; `1st 5 innings` — the form
    Polymarket actually emits — was not, so its half-game lines read as
    full-game ones. Both spellings must land on the same label, the same way
    `1st half` and `first half` already do.
    """
    assert _classify_game_market("1st 5 Innings O/U 2.5", None) == "half_total"
    assert _classify_game_market("First 5 Innings O/U 2.5", None) == "half_total"
    assert _classify_game_market("1st 5 Innings Spread -1.5", None) == "half_spread"
    # The full-game forms are untouched.
    assert _classify_game_market("Over 7.5", None) == "game_total"
    assert _classify_game_market("Total Runs", None) == "game_total"


def test_a_player_prop_outcome_prices_neither_arm():
    """One athlete's line cannot price the game's total OR its margin.

    This is where the outcome set differs from the market-level one, which
    refuses only the total.
    """
    assert "player_prop" in _PM_OUTCOME_NEVER_PRICES_THE_GAME
    assert "team_total" in _PM_OUTCOME_NEVER_PRICES_THE_GAME
    assert "spread" not in _PM_OUTCOME_NEVER_PRICES_THE_GAME
    assert _classify_game_market("Luke Keaschall: Home Runs O/U 0.5", None) == "player_prop"


# ---------------------------------------------------------------------------
# Half 2 of the repair — the renderable-pair walk
# ---------------------------------------------------------------------------


def test_the_walk_is_invisible_when_the_preferred_pair_is_renderable():
    """The property that makes this safe to ship: no behaviour change otherwise.

    Two independent arms picked by confidence are exactly the head of the
    pair ranking, because the confidences are independent — so on every page
    whose preferred pair is a scoreline, this returns what #3921 returned.
    """
    spreads = {
        "kalshi": {"spread": -3.0, "confidence": 0.9},
        "polymarket": {"spread": -1.0, "confidence": 0.4},
    }
    totals = {
        "kalshi": {"total": 44.0, "confidence": 0.5},
        "polymarket": {"total": 47.0, "confidence": 0.95},
    }
    chosen = select_projected_final(spreads, totals)
    assert chosen is not None
    spread_source, total_source, projection = chosen
    assert spread_source == select_projection_source(spreads)
    assert total_source == select_projection_source(totals)
    assert projection == projected_final_score(-3.0, 47.0)


def test_an_unrenderable_preferred_pair_falls_back_to_the_next_valid_source():
    """The grader's shape, as pure logic: −14.25 against a real 8.0 total.

    The preferred pair is the most confident one and it is not a scoreline, so
    the walk continues rather than serving it.
    """
    spreads = {
        "polymarket": {"spread": -14.25, "confidence": 1.0},
        "kalshi": {"spread": -1.5, "confidence": 0.6},
    }
    totals = {"kalshi": {"total": 8.0, "confidence": 0.9}}
    chosen = select_projected_final(spreads, totals)
    assert chosen is not None
    spread_source, total_source, projection = chosen
    assert (spread_source, total_source) == ("kalshi", "kalshi")
    assert projection.home_score >= 0 and projection.away_score >= 0


def test_when_no_pair_is_a_scoreline_nothing_is_served():
    """Silence beats a false statement about the game.

    A reader who sees no projection has lost a number. A reader who sees
    `8 – -6` has been told something untrue.
    """
    spreads = {"polymarket": {"spread": -14.25, "confidence": 1.0}}
    totals = {"polymarket": {"total": 2.5, "confidence": 1.0}}
    assert select_projected_final(spreads, totals) is None


def test_an_empty_arm_projects_nothing():
    assert select_projected_final({}, {"kalshi": {"total": 8.0}}) is None
    assert select_projected_final({"kalshi": {"spread": -1.5}}, {}) is None
    assert select_projected_final(None, None) is None


def test_renderability_is_the_arithmetic_invariant_not_a_plausibility_rule():
    """It asks only `|spread| <= total`, so it cannot reject a real game.

    A 63-point NFL blowout and a 1–0 soccer game are both renderable; only a
    margin wider than the whole total is not.
    """
    assert projection_is_renderable(projected_final_score(-63.0, 63.0))
    assert projection_is_renderable(projected_final_score(-1.0, 1.0))
    assert not projection_is_renderable(projected_final_score(-14.25, 8.0))
    assert not projection_is_renderable(projected_final_score(14.25, 8.0))


def test_the_ranking_the_walk_uses_is_the_one_the_single_pick_uses():
    """One ranking rule, so the two entry points can never disagree.

    `select_projection_source` is the head of `rank_projection_sources`; if that
    ever stops being true a page's chosen arm and its fallback order come from
    two different opinions.
    """
    implied = {
        "sportsbook": {"confidence": 1.0},
        "kalshi": {"confidence": 0.3},
        "polymarket": {"confidence": 1.0},
    }
    ranked = rank_projection_sources(implied)
    assert ranked[0] == select_projection_source(implied)
    # Confidence first, declared order only as the tie-break.
    assert ranked == ["polymarket", "sportsbook", "kalshi"]
    assert rank_projection_sources({}) == []
    assert rank_projection_sources(None) == []
