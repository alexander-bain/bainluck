"""lane1/192 (#3965, follow-up `NO-CROSSOVER-ROUTE-CONTRACT-3965`): the route
omits the arm, it does not serve a null one.

CERT-2283 granted #3965 its token and named this follow-up nonblocking: the unit
tests in `test_binary_spread_no_crossover_3965.py` prove
`binary_to_implied_spread` returns `None` for a one-sided ladder, but nothing
proved what `GET /api/events/{id}/history` then *serves*. That gap is not
cosmetic. The route's line is

    result = binary_to_implied_spread(contracts)
    if result:
        implied_spreads[source] = {...}

so `None` means the key is never created — but a future edit that switched the
guard to `if result is not None` or that pre-seeded `implied_spreads` with a
`None` placeholder would keep every unit test green while the payload grew a
`"polymarket": null` arm. `ScoreDifferentialChart` draws non-sportsbook arms on
presence, so a null arm is a rendered defect the unit layer cannot see. This
module pins the payload contract: **absent, not null, and the other arm
survives.**

The fixture is the production specimen read at 2026-09-08 20:23Z, event
`15307194` (Minnesota Twins at Detroit Tigers, first pitch 22:40Z), whose
Polymarket ladder carried **20 rungs from 1.5 to 9.5 priced only at 0.84 and
1.000** — every rung above the crossover. The retired `-last * 1.5` branch turned
that into `-9.5 * 1.5 = -14.25`, and the same `-14.25` was served on event
`15307207` as well: two different games, one number, which is what a degenerate
arm looks like from outside.

The controls carry the weight. A refusal that also removed the Kalshi spread, or
the Polymarket *total*, would pass the ship assertion and break the page — on the
specimen the totals arm is a real 10.5 off 27 rungs, and `binary_to_implied_total`
never had the extrapolating branches, so it must be untouched.
"""

from types import SimpleNamespace

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
    _total_market,
)

from app.routes.events import get_event_odds_history
from datetime import datetime, timezone
from unittest.mock import MagicMock

UTC = timezone.utc

#: The specimen's own identity, so the fixture cannot drift away from production.
_SPECIMEN_ID = 15307194
_COMMENCE = datetime(2026, 9, 8, 22, 40, tzinfo=UTC)

#: The 20 rungs production served, at the two prices it served them at. Every
#: one sits above 0.50, so no adjacent pair straddles the crossover.
_NO_CROSSOVER_RUNGS = (
    (1.5, 1.0), (1.5, 1.0), (1.5, 1.0), (2.5, 1.0), (2.5, 1.0),
    (3.5, 1.0), (3.5, 1.0), (4.5, 1.0), (4.5, 1.0), (5.5, 1.0),
    (5.5, 1.0), (6.5, 1.0), (6.5, 0.84), (7.5, 1.0), (7.5, 0.84),
    (8.5, 1.0), (8.5, 0.84), (9.5, 1.0), (9.5, 0.84), (9.5, 1.0),
)

#: What the retired `-last * 1.5` branch produced from those rungs.
_FABRICATED_SPREAD = -14.25


def _spread_rungs(source, rungs, name="Minnesota Twins vs Detroit Tigers: Spread"):
    """A spread market from explicit (threshold, probability) pairs.

    The 3921 helper spaces its own probabilities evenly through 50%, which is
    the one shape this module must NOT use — the whole subject is a ladder that
    never crosses.
    """
    return _market(
        source,
        [_outcome(f"Detroit win by {t}+", p) for t, p in rungs],
        name=name,
    )


def _event(**overrides):
    event = SimpleNamespace(
        id=_SPECIMEN_ID,
        status="scheduled",
        commence_time=_COMMENCE,
        completed_at=None,
        home_team_name="Detroit Tigers",
        away_team_name="Minnesota Twins",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.52}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


async def _pm_spread_data(event, futures_markets=()):
    """Serve the REAL route and hand back its `pm_spread_data`.

    Driving the route rather than re-implementing its assembly is the point: a
    re-implemented payload builder can agree with this test and disagree with
    production.
    """
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        response=MagicMock(headers={}),
        db=_DispatchingSession(event, futures_markets),
    )
    return payload.get("pm_spread_data") or {}


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


async def test_the_no_crossover_polymarket_arm_is_absent_from_the_served_payload():
    """The specimen: Polymarket implies nothing, Kalshi still implies -0.2."""
    pm = await _pm_spread_data(
        _event(),
        [
            _spread_rungs("polymarket", _NO_CROSSOVER_RUNGS),
            # Kalshi's arm on the same game does cross, at -0.2.
            _spread_rungs(
                "kalshi",
                ((0.5, 0.62), (1.5, 0.55), (2.5, 0.48), (3.5, 0.41)),
            ),
        ],
    )
    spreads = pm.get("implied_spreads") or {}

    # Absent — not present-and-null. `in` is the assertion, because a `None`
    # placeholder would satisfy any truthiness check written on `.get()`.
    assert "polymarket" not in spreads, (
        f"the no-crossover arm is still served: {spreads.get('polymarket')!r}"
    )
    assert "kalshi" in spreads, "the refusal took the valid Kalshi arm with it"
    assert spreads["kalshi"]["spread"] != _FABRICATED_SPREAD


async def test_the_projection_still_names_kalshi_after_the_refusal():
    """`projected_final` keeps its source; the page keeps its projected score."""
    pm = await _pm_spread_data(
        _event(),
        [
            _spread_rungs("polymarket", _NO_CROSSOVER_RUNGS),
            _spread_rungs(
                "kalshi",
                ((0.5, 0.62), (1.5, 0.55), (2.5, 0.48), (3.5, 0.41)),
            ),
            _total_market(
                "kalshi", (7.5, 8.5, 9.5), crossover_at=(8.5, 9.5),
                name="Minnesota Twins vs Detroit Tigers: Total Runs",
            ),
        ],
    )
    projected = (pm.get("projected_final") or {})
    assert projected.get("spread_source") == "kalshi", (
        f"projection lost its spread source: {projected!r}"
    )
    assert projected.get("home_score") is not None


async def test_an_all_below_ladder_is_refused_by_the_same_route_path():
    """The other one-sided shape — every rung under 50% — is also omitted.

    Measured as firing 0 times in the ±48h window, so no production specimen
    exists; it is covered here because the retired code had a branch for it
    (`-first * 0.5`) and a re-introduction would be silent.
    """
    pm = await _pm_spread_data(
        _event(),
        [_spread_rungs("polymarket", ((1.5, 0.31), (2.5, 0.22), (3.5, 0.09)))],
    )
    assert "polymarket" not in (pm.get("implied_spreads") or {})


# ---------------------------------------------------------------------------
# Controls — the refusal must be narrow
# ---------------------------------------------------------------------------


async def test_a_polymarket_ladder_that_does_cross_still_serves_its_arm():
    """The refusal is about the crossover, not about Polymarket."""
    pm = await _pm_spread_data(
        _event(),
        [_spread_rungs("polymarket", ((0.5, 0.66), (1.5, 0.57), (2.5, 0.44)))],
    )
    spreads = pm.get("implied_spreads") or {}
    assert "polymarket" in spreads, "a crossing Polymarket ladder lost its arm"
    assert spreads["polymarket"]["spread"] != _FABRICATED_SPREAD


async def test_the_polymarket_totals_arm_survives_the_spread_refusal():
    """Totals are a different derivation and must not move.

    On the specimen the Polymarket totals arm is a real 10.5 off 27 rungs.
    `binary_to_implied_total` never carried the extrapolating branches, so a
    change that also blanked the total would be over-reach — and would blank a
    correct number the page renders.

    This asserts the totals arm and nothing else, deliberately: it passes on
    BOTH sides of the fix, so it measures narrowness rather than re-asserting
    the ship. The spread's absence is covered above.
    """
    pm = await _pm_spread_data(
        _event(),
        [
            _spread_rungs("polymarket", _NO_CROSSOVER_RUNGS),
            _total_market(
                "polymarket", (9.5, 10.5, 11.5), crossover_at=(10.5, 11.5),
                name="Minnesota Twins vs Detroit Tigers: Total Runs",
            ),
        ],
    )
    assert "polymarket" in (pm.get("implied_totals") or {}), (
        "the spread refusal also removed the (valid) totals arm"
    )
