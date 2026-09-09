"""lane1/201 (#3981, follow-up `3981-ATHLETICS-REAL-ROUTE-GUARD`): the served
ladder carries BOTH teams' rungs, proved on the real route.

CERT-2332 granted #3981 its token and named this follow-up nonblocking. The gap
it names is precise. `test_athletics_rung_alias_3981.py` proves the alias and
proves `resolve_rung_side` resolves an `A's` rung — but every one of those tests
stops at the resolver. Nothing committed to the tree proved what
`GET /api/events/{id}/history` then *serves*, and the grader closed that hole
with a disposable probe that is now gone. This module makes the specimen
permanent.

The gap is not cosmetic, because of how this defect presented. Before the fix,
production served three contracts for event `15307209` and **every one of them
was an away rung inverted onto the home axis**:

    stored rung              p       served
    Toronto by over 1.5     0.99     -1.5 @ 0.01
    Toronto by over 2.5     0.03     -2.5 @ 0.97
    Toronto by over 3.5     0.01     -3.5 @ 0.99
    A's by over 1.5/2.5/3.5 0.01     dropped

Note which side is which, because it is the whole reason guessing is unsafe: the
**Athletics are the home team** here and Toronto is the away team, while the
market is titled "Toronto vs A's". A rung appended on position would land on the
wrong side of the axis every time.

Toronto won by exactly 2, so "by 1.5+" settles YES and "by 2.5+" NO: **the served
numbers were internally consistent.** A reader could not see it, and neither
could a monotonicity check — a ladder built from one side is a confident answer
on half the evidence, not a broken-looking one. That is exactly the class of
defect a unit test on the resolver cannot report, because the resolver returning
a side is not the same claim as the route serving that side's rung.

The fixture is the production specimen read at 2026-09-09 07:05Z, event
`15307209` (Toronto Blue Jays at Athletics, first pitch 2026-09-09 01:40Z, final
4-2 Toronto), Kalshi market `KXMLBSPREAD-26SEP082140TORATH` — its six real
outcome names at their six real prices, and the event row's real orientation.
After the fix the same endpoint served six contracts at thresholds
`[-3.5, -2.5, -1.5, +1.5, +2.5, +3.5]`.

**A positive threshold appearing is the assertion, not the count.** A contract
count can move for unrelated ingest reasons; a `+` threshold on this specimen
can only come from an Athletics rung resolving.

The controls carry the rest. #3981's body is explicit that refusal is the
current safety property and must not be traded away for coverage — guessing is
worse than dropping here, because the market title names the away team first, so
position resolves the sign backwards. So this module also pins that an
unresolvable rung is still dropped by the same route path.
"""

from types import SimpleNamespace

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
)

from app.routes.events import get_event_odds_history
from datetime import datetime, timezone
from unittest.mock import MagicMock

UTC = timezone.utc

#: The specimen's own identity, so the fixture cannot drift away from production.
_SPECIMEN_ID = 15307209
_COMMENCE = datetime(2026, 9, 9, 1, 40, tzinfo=UTC)

#: Kalshi's real market label and ticker for the specimen. `_classify_game_market`
#: reads both to decide which quantity the market prices, so a fixture that
#: paraphrased them would be testing a different route branch.
_SPECIMEN_MARKET = "Toronto vs A's: Spread"
_SPECIMEN_TICKER = "KXMLBSPREAD-26SEP082140TORATH"

#: The six rungs production stores, verbatim, at the prices it stores them at.
#: Three name the home side and three name the away side by the short form that
#: `_name_tokens` reduces to "as" — the whole subject of #3981.
_SPECIMEN_RUNGS = (
    ("A's wins by over 1.5 runs", 0.01),
    ("A's wins by over 2.5 runs", 0.01),
    ("A's wins by over 3.5 runs", 0.01),
    ("Toronto wins by over 1.5 runs", 0.99),
    ("Toronto wins by over 2.5 runs", 0.03),
    ("Toronto wins by over 3.5 runs", 0.01),
)

#: What production served BEFORE the fix: the opponent's three rungs only.
_ONE_SIDED_THRESHOLDS = [-3.5, -2.5, -1.5]


def _event(**overrides):
    event = SimpleNamespace(
        id=_SPECIMEN_ID,
        status="completed",
        commence_time=_COMMENCE,
        completed_at=None,
        # The event row's real orientation, read from production: the Athletics
        # are HOME. The market is titled "Toronto vs A's", naming the away team
        # first — which is why a rung resolved by position resolves it backwards.
        home_team_name="Athletics",
        away_team_name="Toronto Blue Jays",
        home_score=2,
        away_score=4,
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.01}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


def _specimen_market(rungs=_SPECIMEN_RUNGS):
    return _market(
        "kalshi",
        [_outcome(name, prob) for name, prob in rungs],
        name=_SPECIMEN_MARKET,
        external_id=_SPECIMEN_TICKER,
    )


async def _kalshi_contracts(event, futures_markets):
    """Serve the REAL route and hand back its Kalshi spread contracts.

    Driving the route rather than re-implementing its assembly is the point: a
    re-implemented payload builder can agree with this test and disagree with
    production. That is precisely the hole #3981 fell through — the resolver was
    covered, the payload was not.
    """
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        response=MagicMock(headers={}),
        db=_DispatchingSession(event, futures_markets),
    )
    spreads = (payload.get("pm_spread_data") or {}).get("implied_spreads") or {}
    arm = spreads.get("kalshi")
    return arm["contracts"] if arm else None


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


async def test_the_served_ladder_carries_a_rung_from_the_athletics_side():
    """The one assertion the disposable probe made, made permanently.

    A POSITIVE threshold is the proof. It cannot be produced by the opponent's
    rungs under any orientation the route applies to them, so it is reachable
    only by an `A's` rung resolving to a side.
    """
    contracts = await _kalshi_contracts(_event(), [_specimen_market()])

    assert contracts is not None, "the specimen lost its Kalshi arm entirely"
    thresholds = sorted(c["threshold"] for c in contracts)
    assert any(t > 0 for t in thresholds), (
        "the ladder is still built from one side — no Athletics rung reached the "
        f"payload: {thresholds}"
    )


async def test_the_served_ladder_is_not_the_one_sided_shape_production_served():
    """Pin the regression by its exact pre-fix signature.

    Asserting the old shape by value, rather than asserting a count, means a
    future change that drops the Athletics rungs again fails here even if it
    happens to add rungs elsewhere.
    """
    contracts = await _kalshi_contracts(_event(), [_specimen_market()])
    thresholds = sorted(c["threshold"] for c in contracts)

    assert (
        thresholds != _ONE_SIDED_THRESHOLDS
    ), "the served ladder is byte-for-byte the pre-fix opponent-only shape"
    assert len(thresholds) == len(
        _SPECIMEN_RUNGS
    ), f"expected all {len(_SPECIMEN_RUNGS)} specimen rungs served, got {thresholds}"


async def test_both_sides_of_the_specimen_reach_the_payload():
    """Three rungs each way — the shape that makes a two-sided ladder.

    Counting per side rather than in total is deliberate: a total of six could
    also be six rungs from one side, which is the very failure being guarded.
    """
    contracts = await _kalshi_contracts(_event(), [_specimen_market()])
    thresholds = [c["threshold"] for c in contracts]

    assert (
        len([t for t in thresholds if t < 0]) == 3
    ), f"Toronto (away) side incomplete: {thresholds}"
    assert (
        len([t for t in thresholds if t > 0]) == 3
    ), f"Athletics (home) side incomplete: {thresholds}"


async def test_the_athletics_rungs_keep_the_prices_production_stores():
    """The rungs arrive priced, not merely present.

    All three `A's` rungs are stored at 0.01. A rung that reached the payload
    with a fabricated or defaulted price would satisfy every assertion above
    while feeding the chart a number nobody quoted.
    """
    contracts = await _kalshi_contracts(_event(), [_specimen_market()])
    athletics = {
        c["threshold"]: c["probability"] for c in contracts if c["threshold"] > 0
    }

    assert sorted(athletics) == [
        1.5,
        2.5,
        3.5,
    ], f"Athletics thresholds: {sorted(athletics)}"
    for threshold, probability in athletics.items():
        assert probability == 0.01, (
            f"the {threshold} Athletics rung is served at {probability}, "
            "not the 0.01 production stores"
        )


# ---------------------------------------------------------------------------
# Controls — the coverage must not have been bought with the refusal
# ---------------------------------------------------------------------------


async def test_a_rung_naming_neither_side_is_still_dropped_by_this_route():
    """#3981's stated safety property, asserted where it is actually spent.

    The resolver's refusal is already unit-tested. This asserts the route still
    *honours* it: an unresolvable rung must not be appended on position, because
    the market title names the away team first and position inverts the sign.

    Written as a DELTA — same specimen with and without the intruder — so it
    passes on both sides of the fix and measures only the refusal. Asserting a
    contract count here instead would go red whenever the ship goes red, which
    would make it a second copy of the ship assertion wearing a control's name.
    """
    without = await _kalshi_contracts(_event(), [_specimen_market()])
    with_intruder = await _kalshi_contracts(
        _event(),
        [
            _specimen_market(
                _SPECIMEN_RUNGS + (("Milwaukee wins by over 1.5 runs", 0.44),),
            )
        ],
    )

    assert sorted(c["threshold"] for c in with_intruder) == sorted(
        c["threshold"] for c in without
    ), "a rung naming neither side was guessed onto the axis"


async def test_an_opponent_only_ladder_still_serves_its_own_side():
    """The fix added a side; it must not have made the other side conditional.

    This passes on BOTH sides of the fix by design — it measures narrowness, not
    the ship. The ship is asserted above.
    """
    contracts = await _kalshi_contracts(
        _event(),
        [
            _specimen_market(
                tuple(r for r in _SPECIMEN_RUNGS if r[0].startswith("Toronto"))
            )
        ],
    )

    assert contracts is not None, "an opponent-only ladder lost its arm"
    assert sorted(c["threshold"] for c in contracts) == _ONE_SIDED_THRESHOLDS
