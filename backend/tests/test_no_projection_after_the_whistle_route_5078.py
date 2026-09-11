"""live/146 (#5078, follow-up `5078-REAL-ROUTE-TERMINAL-PAYLOAD-GUARD`): the
route SERVES no projection after the whistle — proven by driving the route.

CERT-2576 granted #5078 its token and named this follow-up nonblocking:

    replace or complement source-scan assertions with a behavioral route test

`test_no_projection_after_the_whistle_5078.py` asserts the *text* of the fix —
`inspect.getsource` plus three substring checks. Those pin something behaviour
cannot see (the gate SHORT-CIRCUITS, so a degenerate ladder is never read at
all, which is invisible from the payload) and they are kept for that reason.
What they cannot do is fail when the gate stops working:

* they pass against dead code — a gate on an unreachable branch still reads
  `None if event_is_final` in the source;
* they fail on a harmless rename of `event_is_final`, so they punish refactors
  while missing regressions.

This module is the other half: what `GET /api/events/{id}/history` actually
puts on the wire.

**The experiment is one variable.** Every test here serves the SAME readable
ladder and changes only `event.status`. That matters both ways round:

* it proves the suppression is the STATE GATE and not the ladder. A test that
  fed the route a post-whistle ladder collapsed to 0/1 would pass against the
  unfixed code — `binary_to_implied_spread` returns `None` for a degenerate
  ladder on its own — and would prove nothing at all;
* it keeps the terminal assertion non-vacuous. `projected_final: null` only
  means something because the pre-whistle control, on the identical ladder,
  is not null.

The specimen is #5078's own: SF@LAR (`events.id 14632820`), final 03:25:31Z on
2026-09-11, actual **7-27**, and at final+11 the page projected the Rams
winning **26-23**.
"""

from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
    _total_market,
)

from app.routes.events import get_event_odds_history

UTC = timezone.utc

#: The specimen's own identity, so the fixture cannot drift away from production.
_SPECIMEN_ID = 14632820
_COMMENCE = datetime(2026, 9, 11, 0, 15, tzinfo=UTC)

#: What the reader could already see on the same payload, two inches away.
_ACTUAL_HOME, _ACTUAL_AWAY = 7, 27


def _event(status, **overrides):
    """The specimen at a given lifecycle state. `status` is the ONLY variable."""
    event = SimpleNamespace(
        id=_SPECIMEN_ID,
        status=status,
        commence_time=_COMMENCE,
        completed_at=None,
        home_team_name="Los Angeles Rams",
        away_team_name="San Francisco 49ers",
        home_score=_ACTUAL_HOME,
        away_score=_ACTUAL_AWAY,
        sport=SimpleNamespace(key="americanfootball_nfl"),
        sport_id=2,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.5}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


def _readable_spread(source="kalshi"):
    """A ladder that DOES cross 50%, so a spread is genuinely derivable.

    Deliberately not the collapsed 0/1 ladder of the real post-whistle window:
    a degenerate ladder is refused upstream by `binary_to_implied_spread`, so a
    fixture built from one could not tell the state gate from that refusal.
    """
    return _market(
        source,
        [
            _outcome("Los Angeles Rams win by 0.5+", 0.66),
            _outcome("Los Angeles Rams win by 3.5+", 0.57),
            _outcome("Los Angeles Rams win by 7.5+", 0.44),
            _outcome("Los Angeles Rams win by 10.5+", 0.31),
        ],
        name="San Francisco 49ers vs Los Angeles Rams: Spread",
    )


def _readable_total(source="kalshi"):
    return _total_market(
        source,
        (41.5, 44.5, 47.5),
        crossover_at=(44.5, 47.5),
        name="San Francisco 49ers vs Los Angeles Rams: Total Points",
    )


async def _pm_spread_data(event):
    """Serve the REAL route and hand back its `pm_spread_data`.

    Driving the route rather than re-implementing the assembly is the whole
    point of this module: a re-implemented payload builder can agree with the
    test and disagree with production.
    """
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        response=MagicMock(headers={}),
        db=_DispatchingSession(event, [_readable_spread(), _readable_total()]),
    )
    return payload.get("pm_spread_data") or {}


# ---------------------------------------------------------------------------
# The control comes first: without it, every assertion below is vacuous.
# ---------------------------------------------------------------------------


async def test_before_the_whistle_this_ladder_does_project():
    """The pre-whistle arm of the experiment — the ladder IS readable.

    If this ever goes null the suppression tests underneath stop proving
    anything, so it is written first and named as the control.
    """
    pm = await _pm_spread_data(_event("live"))
    projected = pm.get("projected_final")

    assert projected is not None, (
        "the control ladder no longer projects, so the terminal-state tests "
        "below are vacuous — fix this fixture before trusting them"
    )
    assert projected.get("home_score") is not None
    assert projected.get("away_score") is not None


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


async def test_a_completed_event_serves_no_projection():
    """The specimen's own state: the game has been played, so nothing is projected."""
    pm = await _pm_spread_data(_event("completed"))

    assert pm.get("projected_final") is None, (
        "a finished game is being projected: "
        f"{pm.get('projected_final')!r} beside an actual "
        f"{_ACTUAL_HOME}-{_ACTUAL_AWAY}"
    )


async def test_a_closed_event_serves_no_projection():
    """`closed` is terminal too — a closed game has also been played."""
    pm = await _pm_spread_data(_event("closed"))

    assert pm.get("projected_final") is None, (
        f"a closed game is being projected: {pm.get('projected_final')!r}"
    )


async def test_the_key_is_present_and_null_not_dropped():
    """The contract is `projected_final: null`, not a missing key.

    `ScoreDifferentialChart` and the page read this key; dropping it entirely
    would be a different payload change than the one #5078 shipped, and the
    route builds `pm_spread_data` with the key unconditionally.
    """
    pm = await _pm_spread_data(_event("completed"))

    assert "projected_final" in pm, "the key was dropped rather than nulled"


# ---------------------------------------------------------------------------
# Controls — the claim is NARROW: no projection, not "no market data on finals"
# ---------------------------------------------------------------------------


async def test_the_charts_own_rungs_survive_the_terminal_gate():
    """A settled game legitimately still draws its implied spread and total.

    This is the control that catches an over-broad fix. Blanking these would be
    a bigger claim than the defect supports, and the payload would lose the
    chart on every finished event.
    """
    pm = await _pm_spread_data(_event("completed"))

    assert pm.get("implied_spreads"), (
        "the terminal gate also suppressed the chart's implied spreads"
    )
    assert pm.get("implied_totals"), (
        "the terminal gate also suppressed the chart's implied totals"
    )


async def test_a_scheduled_event_still_projects():
    """The gate names two terminal states; every other state is untouched.

    Pre-game projection is the feature working as intended, so a gate that
    caught `scheduled` would break the surface it was meant to protect.
    """
    pm = await _pm_spread_data(_event("scheduled"))

    assert pm.get("projected_final") is not None, (
        "a scheduled game lost its projection to the terminal gate"
    )
