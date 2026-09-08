"""lane1/181 (#3921): an NFL game projected to finish 2 – 1.

`GET /api/events/{id}/history` serves `pm_spread_data.projected_final`, which the
event page renders as "Projected final: H – A". On production 2026-09-08 the
Giants v Cowboys page (`events.id 14637256`) rendered:

    Projected final: 2 – 1

on a page whose own hero said Dallas 60%. The payload, read at 12:05Z:

    projected_final : {"home_score": 1.5, "away_score": 1.0,
                       "spread_source": "kalshi", "total_source": "kalshi"}
    implied_totals  : kalshi {"total": 2.5, "confidence": 1.0,
                              contracts at thresholds 1.5 / 2.5 / 3.5 / 4.5 ...}

Two independent defects put it there, and this module covers both.

**B — the pool that priced the total was not the game's total.** This is the one
the reader saw. The route asked for every `FuturesMarket` linked to the event and
poured every outcome that parsed into ONE bucket per source. The filing blamed a
wrong-series attachment; that was wrong, and the correction is the point of this
module. All 31 markets linked to 14637256 are genuinely Dallas v New York — the
event graph is correct and no matching defect is involved. What the bucket mixed
was *quantities*:

    Dallas vs New York: Spread              25 rungs  ("Dallas wins by over 10.5
                                                       points" — read as a TOTAL)
    Dallas vs New York: Total Points        19 rungs  <- the only real one
    DAL Cowboys vs NY Giants: 1st Half …    27 rungs
    DAL Cowboys vs NY Giants: 2nd Half …     8 rungs

The real total was outvoted 60 rungs to 19, and the derivation crossed 50% down
among the half-point rungs at 2.5. Read alone it gives 48.1 — Kalshi's actual
line for the game. So the fix is a scope gate, not a suppression: a market prices
the game's combined total or it contributes none. `_classify_game_market` is the
same shipped classifier `_build_game_markets` sorts its own totals with (step 7),
borrowed rather than re-derived so both surfaces move together.

`_SPORT_TOTAL_RANGE` (step 7a) is mirrored here too, but it is the *second* half
of a pair and it could never have fixed this alone: a team total of 17.5 and a
half total of 20.5 are both inside NFL's (15, 120). Measured on the 49ers v Rams
page, the team-total rungs alone drag a real 47.9 down to 19.7. The range guard
catches a different contaminant — a market from another *sport*, whose scope
label is perfectly correct and so invisible to the scope gate.

**A — the source choice ignored the confidence computed beside it.** The pick was
`for src in ["kalshi", "polymarket", "sportsbook"]: ... break` — first present
wins. At filing time (10:10Z) the same event carried a Kalshi spread at
confidence 0.3 *and* a sportsbook spread at confidence 1.0, and took the 0.3.
The confidence field was computed, serialised, and never read. Only B was live on
the specimen by 12:05Z — the sportsbook arm had gone, leaving Kalshi the sole arm,
which wins on confidence exactly as it won on position. A is a real defect either
way and reappears the moment a second arm returns, so it is fixed on its own
merits and covered here by its own tests rather than by the specimen.

The route tests drive the REAL `get_event_odds_history` against a stubbed
session, reusing the harness convention of `test_history_end_cap_hides_every_point`:
a re-implemented filter is a filter that can agree with the test and disagree
with production. The controls are the point of the file — the projection has a
real job on the sports where it works, and this change must be invisible there.
The load-bearing one is `test_a_matchup_named_market_still_prices_both_quantities`:
Polymarket packs a game's spread AND total into one market named only for the
matchup, so an allowlist of "known-good" scopes blanks every NCAAF page. Measured
against 931 events before and after, this change loses 0 projections.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import (
    _PM_NON_GAME_TOTAL_SCOPES,
    _PM_PERIOD_SCOPES,
    _SPORT_TOTAL_RANGE,
    _classify_game_market,
    get_event_odds_history,
)
from app.utils.binary_spread import (
    PROJECTION_SOURCE_ORDER,
    select_projection_source,
)

UTC = timezone.utc

# The specimen's own identity, so the fixture cannot drift away from production.
_SPECIMEN_ID = 14637256
COMMENCE = datetime(2026, 9, 13, 20, 25, tzinfo=UTC)

#: The thresholds production actually served for this NFL game (#3921).
CONTAMINATED_TOTALS = (1.5, 2.5, 3.5, 4.5)
#: What an NFL game total really looks like — inside `_SPORT_TOTAL_RANGE`.
REAL_NFL_TOTALS = (44.5, 47.5)
#: Kalshi's per-team rungs for the same game (49ers v Rams, read 2026-09-08).
#: Inside the sport range and still not the combined score — which is exactly
#: why the range guard alone could never catch them.
TEAM_TOTALS = (17.5, 20.5, 21.5, 24.5)


# ---------------------------------------------------------------------------
# A session stub that answers the route's own queries
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _DispatchingSession:
    """Answers each query by the table it reads."""

    def __init__(self, event, futures_markets=()):
        self.event = event
        self.futures_markets = list(futures_markets)

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if "FROM futures_markets" in sql:
            return _Result(self.futures_markets)
        if _is_series_fold(sql):
            return _Result([_fold_row(self.event)])
        if _is_blend_fold(sql):
            return _Result([_blend_fold_row(self.event)])
        # Match the FROM clause, never a bare substring: `events` carries a
        # `win_probability_sources` column, so a substring test on "win_prob"
        # routes the event lookup itself into the snapshot arm and the route 404s.
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


# #3810/#3911 put two extra reads of `events` on this route; these tell them
# apart from the route's own entity lookup.
from tests.test_series_fold_3810 import fold_row as _fold_row  # noqa: E402
from tests.test_series_fold_3810 import is_series_fold as _is_series_fold  # noqa: E402
from tests.test_series_fold_3810 import blend_fold_row as _blend_fold_row  # noqa: E402
from tests.test_series_fold_3810 import is_blend_fold as _is_blend_fold  # noqa: E402


def _outcome(name, probability):
    return SimpleNamespace(name=name, current_probability=probability)


def _market(source, outcomes, name="Dallas vs New York", external_id=None):
    # `name`/`external_id` are what `_classify_game_market` reads to decide which
    # quantity a market prices, so the fixture carries Kalshi's real naming.
    return SimpleNamespace(
        source=source, outcomes=list(outcomes), name=name, external_id=external_id
    )


def _total_market(source, thresholds, *, crossover_at,
                  name="Dallas vs New York: Total Points"):
    """Totals whose probabilities cross 50% between the two `crossover_at` rungs.

    `binary_to_implied_total` interpolates at the crossover and scores its
    confidence off the bracket width, so the bracket — not the absolute
    thresholds — is what sets the confidence a test wants to control.
    """
    lo, hi = crossover_at
    outcomes = []
    for t in thresholds:
        if t <= lo:
            prob = 0.70
        elif t >= hi:
            prob = 0.30
        else:
            prob = 0.50
        outcomes.append(_outcome(f"Over {t}", prob))
    return _market(source, outcomes, name=name)


def _spread_market(source, thresholds, name="Dallas vs New York: Spread"):
    """"Wins by X+" contracts, decreasing through 50% so a spread is derivable."""
    step = 0.9 / max(len(thresholds), 1)
    return _market(
        source,
        [
            _outcome(f"Dallas win by {t}+", round(0.95 - step * i, 4))
            for i, t in enumerate(thresholds)
        ],
        name=name,
    )


def _kalshi_margin_market(thresholds, name="Dallas vs New York: Spread"):
    """Kalshi's OWN spread phrasing — the one `extract_spread_threshold` misses.

    "Dallas wins by over 10.5 points" is a margin, but the spread extractor does
    not read that form, so before #3921 every rung fell through to the total
    extractor and was banked as a game total of 10.5 points. This fixture is the
    production text verbatim; if the extractor ever learns the form (#3948) these
    rungs become spreads and the scope gate still keeps them out of the totals.
    """
    step = 0.6 / max(len(thresholds), 1)
    return _market(
        "kalshi",
        [
            _outcome(f"Dallas wins by over {t} points", round(0.70 - step * i, 4))
            for i, t in enumerate(thresholds)
        ],
        name=name,
    )


def _event(sport_key="americanfootball_nfl", **overrides):
    event = SimpleNamespace(
        id=_SPECIMEN_ID,
        status="scheduled",
        commence_time=COMMENCE,
        completed_at=None,
        home_team_name="New York Giants",
        away_team_name="Dallas Cowboys",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key=sport_key),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.4}},
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


# ---------------------------------------------------------------------------
# B — the ship: an impossible total renders nothing, not a score
# ---------------------------------------------------------------------------


async def test_the_nfl_game_stops_printing_an_impossible_projected_score():
    """The specimen, rebuilt from the 31 markets production actually links.

    Every market here is genuinely Dallas v New York — the event graph is
    correct and no matching defect is involved. The projection was wrong because
    it poured every outcome that parsed into ONE pool per source, so the real
    total (19 rungs) was outvoted by 47 rungs that price something else. Fixing
    it must produce a real NFL scoreline, not merely suppress a wrong one.
    """
    pm = await _projection(
        _event(),
        [
            # The one market that IS the game's total.
            _total_market("kalshi", REAL_NFL_TOTALS, crossover_at=REAL_NFL_TOTALS),
            # The spread arm production actually derives from: the "Spread"
            # market's own rungs are unreadable to the spread extractor (#3948),
            # so "Winning Margin" is what supplies it.
            _spread_market(
                "kalshi", (1.0, 3.5, 7.5),
                name="Dallas vs New York G: Winning Margin",
            ),
            # …and the total was outvoted, before the fix, by all of these.
            _kalshi_margin_market(CONTAMINATED_TOTALS),
            _total_market(
                "kalshi", CONTAMINATED_TOTALS, crossover_at=(1.5, 3.5),
                name="DAL Cowboys vs NY Giants: 1st Half Total",
            ),
            _total_market(
                "kalshi", CONTAMINATED_TOTALS, crossover_at=(1.5, 3.5),
                name="DAL Cowboys vs NY Giants: 2nd Half Total",
            ),
            _total_market(
                "kalshi", TEAM_TOTALS, crossover_at=(17.5, 20.5),
                name="DAL Cowboys vs NY Giants: Team Total",
            ),
        ],
    )
    projected = pm.get("projected_final")
    assert projected is not None, "the fix must project a score, not delete one"
    combined = projected["home_score"] + projected["away_score"]
    # The rebuttal of "Projected final: 2 – 1": the number now sits on the scale
    # an NFL game is played on, which is the whole of what the reader saw wrong.
    assert 40 <= combined <= 55, f"expected a real NFL total, got {combined}"
    lo, hi = _SPORT_TOTAL_RANGE["americanfootball"]
    assert lo <= pm["implied_totals"]["kalshi"]["total"] <= hi


async def test_a_real_nfl_total_still_projects_a_score():
    """The control that keeps the feature working where it works.

    Same shape, same source, thresholds inside the sport's range — this must
    still render, or the guard has deleted the feature rather than fixed it.
    """
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", REAL_NFL_TOTALS, crossover_at=REAL_NFL_TOTALS),
        ],
    )
    projected = pm.get("projected_final")
    assert projected is not None
    # A plausible NFL scoreline, not a soccer one.
    assert projected["home_score"] + projected["away_score"] >= 15


async def test_the_spread_arm_is_left_alone_by_the_totals_guard():
    """A 0.5-point NFL spread is a pick'em, not contamination.

    `_SPORT_TOTAL_RANGE` bounds totals. Nothing here may start bounding spreads
    off the same numbers — a low spread is ordinary and a legitimate one must
    survive.
    """
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (0.5, 1.5)),
            _total_market("kalshi", REAL_NFL_TOTALS, crossover_at=REAL_NFL_TOTALS),
        ],
    )
    assert "kalshi" in (pm.get("implied_spreads") or {})


async def test_a_period_market_never_prices_the_full_game():
    """A half is not the match. 35 of the specimen's 79 rungs were halves."""
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", REAL_NFL_TOTALS, crossover_at=REAL_NFL_TOTALS),
            _total_market(
                "kalshi", (20.5, 21.5), crossover_at=(20.5, 21.5),
                name="DAL Cowboys vs NY Giants: 1st Half Total",
            ),
        ],
    )
    # The half's rungs are inside the sport range, so ONLY the scope gate can
    # keep them out — the range guard cannot see them.
    lo, hi = _SPORT_TOTAL_RANGE["americanfootball"]
    assert all(lo <= t <= hi for t in (20.5, 21.5))
    assert pm["implied_totals"]["kalshi"]["total"] >= 40


async def test_a_team_total_never_prices_the_combined_score():
    """One side's points are not both sides' points (49ers v Rams: 47.9 → 19.7)."""
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", REAL_NFL_TOTALS, crossover_at=REAL_NFL_TOTALS),
            _total_market(
                "kalshi", TEAM_TOTALS, crossover_at=(17.5, 20.5),
                name="SF 49ers vs LA Rams: Team Total",
            ),
        ],
    )
    lo, hi = _SPORT_TOTAL_RANGE["americanfootball"]
    assert all(lo <= t <= hi for t in TEAM_TOTALS)
    assert pm["implied_totals"]["kalshi"]["total"] >= 40


async def test_a_spread_markets_rungs_never_become_a_total():
    """"Dallas wins by over 10.5 points" is a margin, whatever the parser thinks.

    With no game-total market present there is nothing legitimate to read, so
    the margin rungs must yield NO total rather than a 10-point NFL game.
    """
    pm = await _projection(
        _event(),
        [_kalshi_margin_market((10.5, 13.5, 16.5, 17.5))],
    )
    assert "kalshi" not in (pm.get("implied_totals") or {})
    assert pm.get("projected_final") is None


async def test_a_matchup_named_market_still_prices_both_quantities():
    """The regression control for every NCAAF page (measured: 13 of 13 lost).

    Polymarket packs a game's spread AND total into one market named only for
    the matchup, which classifies as `other`. An allowlist of "known-good"
    scopes blanks the projection there, so labels that make no quantity claim
    must stay eligible for both.
    """
    matchup = "Old Dominion vs. Virginia Tech"
    assert _classify_game_market(matchup, None) not in (
        _PM_PERIOD_SCOPES | _PM_NON_GAME_TOTAL_SCOPES
    )
    pm = await _projection(
        _event(),
        [
            _market(
                "polymarket",
                [_outcome(f"Over {t}", p) for t, p in ((44.5, 0.70), (49.5, 0.30))]
                + [_outcome("Dallas win by 1.0+", 0.62),
                   _outcome("Dallas win by 7.5+", 0.28)],
                name=matchup,
            )
        ],
    )
    assert pm.get("projected_final") is not None


async def test_another_sports_totals_are_dropped_even_wearing_the_right_label():
    """The half of the pair the scope gate cannot do.

    This market is correctly labelled the game's total — it simply belongs to a
    different sport, mis-linked onto an NFL event. Its scope is `game_total` and
    always will be, so only `_SPORT_TOTAL_RANGE` can catch it. Nothing else in
    this module fails if the range guard is deleted, which is why this test
    exists.
    """
    hockey_scale = (5.5, 6.5)
    lo, _hi = _SPORT_TOTAL_RANGE["americanfootball"]
    assert all(t < lo for t in hockey_scale)
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", hockey_scale, crossover_at=hockey_scale),
        ],
    )
    assert "kalshi" not in (pm.get("implied_totals") or {})
    assert pm.get("projected_final") is None


async def test_a_sport_with_no_declared_range_keeps_its_contracts():
    """Fail open on a scale we do not hold.

    The guard suppresses; suppressing a projection we cannot fault is the worse
    error, so an unrecognised sport prefix is left exactly as it was.
    """
    unknown = "quidditch_league"
    assert unknown.split("_")[0] not in _SPORT_TOTAL_RANGE
    pm = await _projection(
        _event(sport_key=unknown),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", CONTAMINATED_TOTALS, crossover_at=(1.5, 3.5)),
        ],
    )
    assert pm.get("projected_final") is not None


# ---------------------------------------------------------------------------
# A — the pick reads the confidence it computed
# ---------------------------------------------------------------------------


async def test_the_route_prefers_the_more_confident_arm_over_the_earlier_one():
    """Kalshi is first in the fallback order and must still lose on confidence.

    Both arms are in range and both are real totals; Kalshi's bracket is wide
    (low confidence) and Polymarket's is tight. The old code took Kalshi because
    it was first in a hardcoded list.
    """
    pm = await _projection(
        _event(),
        [
            _spread_market("kalshi", (1.0, 3.5, 7.5)),
            _total_market("kalshi", (30.5, 50.5), crossover_at=(30.5, 50.5)),
            _total_market("polymarket", (44.5, 45.5), crossover_at=(44.5, 45.5)),
        ],
    )
    totals = pm.get("implied_totals") or {}
    assert totals["polymarket"]["confidence"] > totals["kalshi"]["confidence"]
    assert pm["projected_final"]["total_source"] == "polymarket"


def test_confidence_beats_position():
    """The defect, at the unit: 0.3 first in the order must lose to 1.0."""
    implied = {
        "kalshi": {"spread": -0.5, "confidence": 0.3},
        "sportsbook": {"spread": 2.5, "confidence": 1.0},
    }
    assert select_projection_source(implied) == "sportsbook"


def test_position_still_breaks_a_tie():
    """The old order is retained as the tie-break, not discarded."""
    implied = {
        "sportsbook": {"total": 45.5, "confidence": 0.9},
        "kalshi": {"total": 44.0, "confidence": 0.9},
        "polymarket": {"total": 46.0, "confidence": 0.9},
    }
    assert select_projection_source(implied) == "kalshi"
    assert PROJECTION_SOURCE_ORDER[0] == "kalshi"


def test_a_sole_low_confidence_arm_is_still_used():
    """Coverage must not shrink: one arm at 0.3 is still the best arm there is."""
    implied = {"kalshi": {"spread": -0.5, "confidence": 0.3}}
    assert select_projection_source(implied) == "kalshi"


def test_a_source_the_order_never_heard_of_is_eligible():
    """A venue added after this list was written must not be silently dropped."""
    implied = {
        "kalshi": {"total": 44.0, "confidence": 0.4},
        "some_new_venue": {"total": 45.0, "confidence": 0.9},
    }
    assert select_projection_source(implied) == "some_new_venue"


def test_an_unknown_source_still_loses_to_a_known_one_at_equal_confidence():
    """Eligible, but never preferred — the known order wins the tie."""
    implied = {
        "some_new_venue": {"total": 45.0, "confidence": 0.9},
        "polymarket": {"total": 44.0, "confidence": 0.9},
    }
    assert select_projection_source(implied) == "polymarket"


def test_a_missing_or_unparseable_confidence_sorts_last_but_stays_eligible():
    implied = {
        "kalshi": {"spread": -0.5},
        "polymarket": {"spread": -3.0, "confidence": "not a number"},
        "sportsbook": {"spread": 2.5, "confidence": 0.1},
    }
    assert select_projection_source(implied) == "sportsbook"
    assert select_projection_source({"kalshi": {"spread": -0.5}}) == "kalshi"


def test_no_arms_at_all_picks_nothing():
    assert select_projection_source({}) is None
    assert select_projection_source(None) is None


def test_the_nfl_range_is_the_one_build_game_markets_already_uses():
    """This guard borrows a shipped constant; it does not invent a threshold.

    If `_SPORT_TOTAL_RANGE` is ever retuned, both surfaces move together — which
    is the whole point of reusing it rather than writing a second table.
    """
    lo, hi = _SPORT_TOTAL_RANGE["americanfootball"]
    assert all(t < lo for t in CONTAMINATED_TOTALS)
    assert all(lo <= t <= hi for t in REAL_NFL_TOTALS)
