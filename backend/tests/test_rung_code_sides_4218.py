"""lane1/202 (#4218): a spread rung is placed by the team code Kalshi gives it,
not by whether we can spell its name.

#3981 shipped fix (a) — an alias so `A's` reaches the club stored as
`Athletics`. #4218 is fix (b), the one that retires the class instead of one
instance. The class is this: `resolve_rung_side` matches the rung's short team
text against `events.home_team_name` / `away_team_name`, and every short form
Kalshi mints that the prefix/initials rule cannot reach is another #3981. The
resolver refuses (correctly — the market title names the away team first, so
guessing resolves the sign backwards), the caller drops the rung, and the ladder
is then built from ONE side. The served numbers stay internally consistent, so
neither a reader nor a monotonicity check can report it.

The fix does not spell anything better. Kalshi already tells us which rungs
belong to the same team, in the rung's own ticker:

    KXSERIEASPREAD-26FEB22ROMCRE-CRE1   <- market ticker, then `CRE`, then the index

Two things follow from the code that do not follow from the text:

1. **A code inherits a side from its own siblings.** `SF`'s rungs read both
   "San Francisco" and "SF"; only the first resolves, so today half a team's
   ladder is served and half is dropped.
2. **The second team is the one the first is not.** Where one code resolves and
   the other does not, the other names the opposite side by elimination.

Measured over all 5,901 linked Kalshi spread markets on production
(2026-09-09, `artifacts-lane1-202/phrasing_and_code_census.py`, run against
these shipped functions rather than a model of them):

| | |
|---|---|
| rungs placed on the home axis | 40,429 -> **43,559** (+3,130) |
| markets gaining rungs | 980 |
| **markets gaining a spread arm where the page shows NONE today** | **460** |
| markets whose derived spread or confidence MOVES | **0** |
| markets losing their arm | 2, both mis-linked (below) |

🔴 The zero is the safety property, and it is why this is additive: not one rung
that is placed today is placed differently. The change either adds a rung or
refuses a whole market.

**The two refusals are a fix, not a cost.** Where both codes resolve to the same
side, both ladders are being poured onto one axis. Both live cases are
mis-linked markets — a Texas-Texas A&M market attached to a Virginia Tech-Texas
A&M event, and a Michigan St.-Michigan market attached to a Michigan St.-Ohio
St. event. A ladder built from two teams that are not playing each other is
exactly the confident wrong answer `margin_rung_on_home_axis` exists to avoid.
The mis-link itself is a matching defect and is filed, not patched here (D35).

Both route specimens below are production rows read at 2026-09-09, verbatim.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime, timezone

from tests.test_projection_source_confidence_3921 import (
    _DispatchingSession,
    _market,
    _outcome,
)

from app.routes.events import get_event_odds_history
from app.utils.binary_spread import (
    margin_rung_on_home_axis,
    margin_rung_on_home_axis_for_side,
    resolve_rung_sides_by_code,
    rung_provider_code,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# The code itself
# ---------------------------------------------------------------------------


def test_the_code_is_the_ticker_minus_the_market_and_the_rung_index():
    assert (
        rung_provider_code(
            "KXSERIEASPREAD-26FEB22ROMCRE-CRE1", "KXSERIEASPREAD-26FEB22ROMCRE"
        )
        == "CRE"
    )
    # A two-digit index is still just an index.
    assert (
        rung_provider_code(
            "KXNCAAMBSPREAD-26FEB28TEXTXAM-TXAM18", "KXNCAAMBSPREAD-26FEB28TEXTXAM"
        )
        == "TXAM"
    )


def test_a_code_is_only_read_from_this_markets_own_ticker():
    """D55: the key is explicit, never pattern-guessed off a neighbouring market."""
    assert (
        rung_provider_code(
            "KXSERIEASPREAD-26FEB22ROMCRE-CRE1", "KXSERIEASPREAD-26FEB22MILINT"
        )
        is None
    ), "a rung from another market must not yield a code here"
    assert rung_provider_code("CRE1", "KXSERIEASPREAD-26FEB22ROMCRE") is None
    assert rung_provider_code(None, "KX-X") is None
    assert rung_provider_code("KX-X-CRE1", None) is None


def test_an_all_digit_suffix_is_an_index_with_no_team_in_it():
    """The code is never inferred from digit count (D55) — no digits, no code."""
    assert rung_provider_code("KXMLBSPREAD-26MAY051840ATHPHI-3",
                              "KXMLBSPREAD-26MAY051840ATHPHI") is None


# ---------------------------------------------------------------------------
# The ship: elimination, and sibling inheritance
# ---------------------------------------------------------------------------

#: Production market 110983, event 2186051 (Cremonese at AS Roma, 22 Feb 2026,
#: final 3-0). `Roma` does not reach `AS Roma`: the token rule compares in
#: place, so "roma" is asked to equal "as". Cremonese resolves; Roma does not.
_ROMA_TICKER = "KXSERIEASPREAD-26FEB22ROMCRE"
_ROMA_RUNGS = (
    ("Cremonese wins by over 1.5 goals", 0.015, f"{_ROMA_TICKER}-CRE1"),
    ("Cremonese wins by over 2.5 goals", 0.010, f"{_ROMA_TICKER}-CRE2"),
    ("Roma wins by over 1.5 goals", 0.470, f"{_ROMA_TICKER}-ROM1"),
    ("Roma wins by over 2.5 goals", 0.245, f"{_ROMA_TICKER}-ROM2"),
)


def test_the_unreachable_code_takes_the_side_the_other_code_did_not():
    """The acceptance criterion: resolved by id, with the name deliberately unreadable.

    `resolve_rung_side("Roma", ...)` refuses — pin that first, so this test
    cannot pass because someone taught the token rule to spell Roma. The side
    must come from `CRE` being away.
    """
    from app.utils.binary_spread import resolve_rung_side

    assert (
        resolve_rung_side("Roma", "AS Roma", "Cremonese") is None
    ), "the token rule now reads this name, so this test no longer proves the id path"

    sides = resolve_rung_sides_by_code(
        _ROMA_TICKER,
        [(name, ext) for name, _, ext in _ROMA_RUNGS],
        "AS Roma",
        "Cremonese",
    )
    assert sides == {"CRE": "away", "ROM": "home"}


#: Production market 12929439, event 14595887 (Seattle at St. Louis, 25 Apr
#: 2026). Kalshi switches from the city to the nickname partway up EACH ladder —
#: "Seattle" for 1.5-3.5, then "Mariners" at 4.5 — and a nickname reaches
#: neither stored name, so today the tail of both ladders is dropped.
_SEA_TICKER = "KXMLBSPREAD-26APR251415SEASTL"
_SEA_RUNGS = (
    ("Seattle wins by over 1.5 runs", 0.230, f"{_SEA_TICKER}-SEA2"),
    ("Seattle wins by over 2.5 runs", 0.100, f"{_SEA_TICKER}-SEA3"),
    ("Seattle wins by over 3.5 runs", 0.055, f"{_SEA_TICKER}-SEA4"),
    ("Mariners wins by over 4.5 runs", 0.015, f"{_SEA_TICKER}-SEA5"),
    ("St. Louis wins by over 1.5 runs", 0.115, f"{_SEA_TICKER}-STL2"),
    ("St. Louis wins by over 2.5 runs", 0.055, f"{_SEA_TICKER}-STL3"),
    ("St. Louis wins by over 3.5 runs", 0.025, f"{_SEA_TICKER}-STL4"),
    ("Cardinals wins by over 4.5 runs", 0.035, f"{_SEA_TICKER}-STL5"),
    ("Cardinals wins by over 5.5 runs", 0.010, f"{_SEA_TICKER}-STL6"),
)


def test_a_rung_inherits_the_side_its_own_sibling_established():
    """70 markets on production have this shape, and elimination cannot save them.

    BOTH codes here carry a readable text and an unreadable one, so neither side
    is the "unknown" one — there is nothing to eliminate against. The three tail
    rungs are recoverable only because `SEA5` shares a code with `SEA2`.
    """
    from app.utils.binary_spread import resolve_rung_side

    assert resolve_rung_side("Mariners", "St. Louis Cardinals", "Seattle Mariners") is None
    assert resolve_rung_side("Cardinals", "St. Louis Cardinals", "Seattle Mariners") is None

    sides = resolve_rung_sides_by_code(
        _SEA_TICKER,
        [(name, ext) for name, _, ext in _SEA_RUNGS],
        "St. Louis Cardinals",
        "Seattle Mariners",
    )
    assert sides == {"SEA": "away", "STL": "home"}


# ---------------------------------------------------------------------------
# Refusal, which #4218's body requires be kept intact
# ---------------------------------------------------------------------------


def test_two_codes_on_the_same_side_refuses_the_whole_market():
    """Production market 1935695 — a Texas-Texas A&M market on a Virginia Tech
    event. Both codes prefix-match "Texas A&M Aggies", so today both ladders are
    poured onto the home axis. Refusing beats serving eleven rungs of a game
    that is not being played."""
    ticker = "KXNCAAMBSPREAD-26FEB28TEXTXAM"
    rungs = [
        ("Texas wins by over 1.5 Points", f"{ticker}-TEX1"),
        ("Texas A&M wins by over 3.5 Points", f"{ticker}-TXAM3"),
    ]
    assert resolve_rung_sides_by_code(
        ticker, rungs, "Texas A&M Aggies", "Virginia Tech Hokies"
    ) == {"TEX": None, "TXAM": None}


def test_neither_code_anchored_is_still_a_refusal():
    """258 markets are here — mostly German clubs whose codes and stored names
    share nothing. Elimination needs one anchor; with none, guessing which of
    two unknowns is home is exactly the coin-flip #3981 forbids."""
    ticker = "KXBUNDESLIGASPREAD-26MAR14RBLBVB"
    rungs = [
        ("BVB wins by over 1.5 goals", f"{ticker}-BVB1"),
        ("RBL wins by over 1.5 goals", f"{ticker}-RBL1"),
    ]
    assert resolve_rung_sides_by_code(
        ticker, rungs, "RB Leipzig", "Borussia Dortmund"
    ) == {"BVB": None, "RBL": None}


def test_one_code_contradicting_itself_refuses_rather_than_taking_a_majority():
    """A defensive guard, and deliberately a synthetic fixture.

    No market on production reaches this branch today (counted over all 5,901:
    `artifacts-lane1-202/contradiction_branch_reach.py`). It is here because the
    branch is what makes "a code is one team" an assertion rather than an
    assumption — if Kalshi ever reuses a suffix across both sides of a market,
    the map must refuse rather than let whichever text sorted first decide.
    """
    ticker = "KXSYNTHETIC-26SEP09ALPBET"
    rungs = [
        ("Alpha wins by over 1.5 points", f"{ticker}-DUP1"),
        ("Beta wins by over 1.5 points", f"{ticker}-DUP2"),
        ("Gamma wins by over 1.5 points", f"{ticker}-GAM1"),
    ]
    assert resolve_rung_sides_by_code(
        ticker, rungs, "Alpha United", "Beta City"
    ) == {"DUP": None, "GAM": None}


# ---------------------------------------------------------------------------
# When the rule does not apply, today's behaviour must be exactly unchanged
# ---------------------------------------------------------------------------


def test_a_one_sided_ladder_has_nothing_to_eliminate_against():
    ticker = "KXMLBSPREAD-26MAY051840ATHPHI"
    rungs = [("Athletics wins by over 1.5 runs", f"{ticker}-ATH1")]
    assert (
        resolve_rung_sides_by_code(ticker, rungs, "Philadelphia Phillies", "Athletics")
        is None
    ), "None means 'not applicable' — the caller keeps resolving each rung's text"


def test_a_margin_rung_with_no_code_makes_the_partition_incomplete():
    """`None`, not a partial map — and the fixture must make that distinguishable.

    Two coded rungs plus an uncoded one. Skipping the uncoded rung would leave a
    perfectly good two-code partition and a map would be returned; the rule
    instead declines the whole market, because a rung outside the partition is a
    rung the partition cannot speak for.

    Defensive, and said plainly: 0 margin rungs on production fail the ticker
    prefix today (counted 2026-09-09), so this shape is guarded, not observed.
    """
    ticker = "KXMLBSPREAD-26MAY051840ATHPHI"
    rungs = [
        ("Athletics wins by over 1.5 runs", f"{ticker}-ATH1"),
        ("Philadelphia wins by over 1.5 runs", f"{ticker}-PHI1"),
        ("Philadelphia wins by over 2.5 runs", None),
    ]
    assert (
        resolve_rung_sides_by_code(ticker, rungs, "Philadelphia Phillies", "Athletics")
        is None
    )


def test_three_codes_is_not_the_two_team_shape_this_reasoning_describes():
    ticker = "KXTHREE"
    rungs = [
        ("Alpha wins by over 1.5 points", f"{ticker}-A1"),
        ("Beta wins by over 1.5 points", f"{ticker}-B1"),
        ("Gamma wins by over 1.5 points", f"{ticker}-C1"),
    ]
    assert resolve_rung_sides_by_code(ticker, rungs, "Alpha", "Beta") is None


def test_a_side_from_a_code_is_placed_by_the_same_arithmetic_as_a_side_from_a_name():
    """One home-axis rule, not two: an away rung is negated AND inverted."""
    text, prob = "Cremonese wins by over 2.5 goals", 0.01
    assert margin_rung_on_home_axis_for_side(text, prob, "away") == {
        "threshold": -2.5,
        "probability": 0.99,
    }
    assert margin_rung_on_home_axis_for_side(text, prob, "home") == {
        "threshold": 2.5,
        "probability": 0.01,
    }
    # ...and it agrees with the text path on a rung the text path can read.
    assert margin_rung_on_home_axis_for_side(text, prob, "away") == (
        margin_rung_on_home_axis(text, prob, "AS Roma", "Cremonese")
    )


def test_an_authoritative_refusal_drops_the_rung():
    assert (
        margin_rung_on_home_axis_for_side("Roma wins by over 1.5 goals", 0.47, None)
        is None
    )


# ---------------------------------------------------------------------------
# The real route
# ---------------------------------------------------------------------------


def _event(event_id, home, away, commence, **overrides):
    event = SimpleNamespace(
        id=event_id,
        status="completed",
        commence_time=commence,
        completed_at=None,
        home_team_name=home,
        away_team_name=away,
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="soccer_italy_serie_a"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.47}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


async def _kalshi_arm(event, markets):
    """Drive the REAL route and hand back its Kalshi spread arm.

    Re-implementing the payload assembly is what let #3981 through: the resolver
    was covered and the payload was not.
    """
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        response=MagicMock(headers={}),
        db=_DispatchingSession(event, markets),
    )
    spreads = (payload.get("pm_spread_data") or {}).get("implied_spreads") or {}
    return spreads.get("kalshi")


async def test_the_served_ladder_carries_the_roma_side_too():
    """The ship, on the real route: production event 2186051.

    Today this page serves two contracts, both Cremonese rungs inverted onto the
    home axis, and no spread at all — one side cannot cross 50%. A POSITIVE
    threshold is the proof: it is unreachable from a Cremonese rung under any
    orientation the route applies, so it can only come from `ROM` resolving.
    """
    market = _market(
        "kalshi",
        [_outcome(name, prob, external_id=ext) for name, prob, ext in _ROMA_RUNGS],
        name="Cremonese at Roma: Spreads",
        external_id=_ROMA_TICKER,
    )
    arm = await _kalshi_arm(
        _event(2186051, "AS Roma", "Cremonese", datetime(2026, 2, 22, 19, 45, tzinfo=UTC)),
        [market],
    )

    assert arm is not None, "the page still shows no Kalshi spread at all"
    thresholds = sorted(c["threshold"] for c in arm["contracts"])
    assert thresholds == [-2.5, -1.5, 1.5, 2.5], (
        f"the ladder is not built from both sides: {thresholds}"
    )
    assert arm["spread"] is not None


async def test_the_mislinked_market_stops_serving_a_ladder_for_a_game_nobody_played():
    """Production event 6586945 with market 1935695, verbatim.

    Both codes prefix-match the home name, so before this change the route
    served eleven contracts built from two teams that are not playing each
    other. The assertion is that the arm is gone — an empty space beats a
    confident wrong spread.
    """
    ticker = "KXNCAAMBSPREAD-26FEB28TEXTXAM"
    rungs = (
        ("Texas wins by over 1.5 Points", 0.565, f"{ticker}-TEX1"),
        ("Texas wins by over 3.5 Points", 0.445, f"{ticker}-TEX3"),
        ("Texas wins by over 6.5 Points", 0.280, f"{ticker}-TEX6"),
        ("Texas wins by over 9.5 Points", 0.165, f"{ticker}-TEX9"),
        ("Texas wins by over 12.5 Points", 0.085, f"{ticker}-TEX12"),
        ("Texas A&M wins by over 3.5 Points", 0.235, f"{ticker}-TXAM3"),
        ("Texas A&M wins by over 6.5 Points", 0.160, f"{ticker}-TXAM6"),
        ("Texas A&M wins by over 9.5 Points", 0.070, f"{ticker}-TXAM9"),
        ("Texas A&M wins by over 12.5 Points", 0.050, f"{ticker}-TXAM12"),
        ("Texas A&M wins by over 15.5 Points", 0.035, f"{ticker}-TXAM15"),
        ("Texas A&M wins by over 18.5 Points", 0.055, f"{ticker}-TXAM18"),
    )
    market = _market(
        "kalshi",
        [_outcome(name, prob, external_id=ext) for name, prob, ext in rungs],
        name="Texas at Texas A&M: Spread",
        external_id=ticker,
    )
    arm = await _kalshi_arm(
        _event(
            6586945,
            "Texas A&M Aggies",
            "Virginia Tech Hokies",
            datetime(2026, 2, 28, 1, 0, tzinfo=UTC),
            sport=SimpleNamespace(key="basketball_ncaab"),
        ),
        [market],
    )
    assert arm is None, (
        "a spread is still being served for a market whose two ladders both "
        f"resolve to the home side: {arm}"
    )


async def test_a_market_with_no_rung_codes_is_served_exactly_as_before():
    """The control. Every fixture that predates #4218 carries no `external_id`,
    so the code map must decline and the token rule must still serve the ladder
    it serves today — here through #3981's alias, on the real route."""
    ticker = "KXMLBSPREAD-26SEP082140TORATH"
    rungs = (
        ("A's wins by over 1.5 runs", 0.01),
        ("A's wins by over 2.5 runs", 0.01),
        ("A's wins by over 3.5 runs", 0.01),
        ("Toronto wins by over 1.5 runs", 0.99),
        ("Toronto wins by over 2.5 runs", 0.03),
        ("Toronto wins by over 3.5 runs", 0.01),
    )
    market = _market(
        "kalshi",
        [_outcome(name, prob) for name, prob in rungs],  # no external_id, as before
        name="Toronto vs A's: Spread",
        external_id=ticker,
    )
    arm = await _kalshi_arm(
        _event(
            15307209,
            "Athletics",
            "Toronto Blue Jays",
            datetime(2026, 9, 9, 1, 40, tzinfo=UTC),
            sport=SimpleNamespace(key="baseball_mlb"),
        ),
        [market],
    )
    assert arm is not None
    thresholds = sorted(c["threshold"] for c in arm["contracts"])
    assert thresholds == [-3.5, -2.5, -1.5, 1.5, 2.5, 3.5], (
        f"the codeless path no longer serves #3981's six rungs: {thresholds}"
    )
