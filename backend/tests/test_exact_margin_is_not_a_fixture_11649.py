"""#11649 — a Polymarket margin prop is not a fixture, so it must not mint one.

WHAT A READER SAW (2026-11-08 15:30 PT). Searching "lakers" listed a LIVE game
"Pistons - Exact Margin" @ "Lakers" (event 15344441); searching "celtics" listed
"Bucks - Exact Margin" @ "Celtics" (15344447). Production held 237 such
`basketball_other` events commencing within 30 days of that date, 13 of them
created in the previous day, each minted by auto-create from a market named
"Lakers vs. Pistons - Exact Margin". "Cardinals vs. Rams - First Touchdown
Scorer" had minted 20 more, filed under `baseball_other`, until 2026-10-18.

WHY #2871 LET IT THROUGH. `_DERIVATIVE_SUFFIX_RE` refuses a dash-introduced
market TYPE from a vocabulary, and neither label was in it — "Exact Score" was,
"Exact Margin" was not. So `is_derivative_market_name` answered False and
`extract_matchup` glued "- Exact Margin" to team_b, which auto-create stamped
as the away team's name.

The one-vocabulary contract is #8854's: the same pattern is the auto-create
refusal, the link-search copy (#6134) and the repair population, so each
consumer is pinned here for the new labels.
"""

import importlib.util
import pathlib
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.live_blend import _class_says_game_winner
from app.utils.prediction_market_matching import (
    extract_matchup,
    is_derivative_market_name,
    matchup_for_link_search,
)

# (production market name, the away team a link search must look for)
MARGIN_PROPS = [
    ("Lakers vs. Pistons - Exact Margin", "Pistons"),
    ("Celtics vs. Bucks - Exact Margin", "Bucks"),
    ("76ers vs. Bulls - Exact Margin", "Bulls"),
    ("James Madison vs. UConn - Exact Margin", "UConn"),
    ("Wisconsin vs. Maryland - Exact Margin", "Maryland"),
    ("Cardinals vs. Rams - First Touchdown Scorer", "Rams"),
]

# Real fixtures, three of them clubs whose own name holds a spaced dash
# (production events 15341581 and 15341158).
FIXTURES = [
    "Lakers vs. Pistons",
    "James Madison vs. UConn",
    "FC Seoul vs. The Cong - Viettel FC",
    "Saint-Sébastien FC vs. US La Baule - Le Pouliguen",
    "Mets vs. Dodgers - Game 4",
    "FC Seoul vs. The Cong - Viettel FC - More Markets",
]


@pytest.mark.parametrize("name,_away", MARGIN_PROPS)
def test_a_margin_prop_is_a_derivative(name, _away):
    assert is_derivative_market_name(name) is True


@pytest.mark.parametrize("name", FIXTURES)
def test_the_fixtures_themselves_are_not(name):
    assert is_derivative_market_name(name) is False


@pytest.mark.parametrize(
    "name,away",
    MARGIN_PROPS + [("FC Seoul vs. The Cong - Viettel FC - Exact Score", "The Cong - Viettel FC")],
)
def test_the_link_search_looks_for_the_real_away_team(name, away):
    """#6134's half: the prop may attach to the game we hold. The last case pins
    that only the market type comes off, never part of a club's own name."""
    search = matchup_for_link_search(extract_matchup(name), name)
    assert search is not None
    assert search.team_b == away


@pytest.mark.parametrize("name,_away", MARGIN_PROPS)
def test_an_attached_margin_prop_never_speaks_for_the_winner(name, _away):
    """Once these can attach to the real game, the blend must still refuse them,
    or a margin price would reach the hero (#5031)."""
    assert _class_says_game_winner(SimpleNamespace(name=name, external_id=None)) is False


NOW = datetime(2026, 11, 8, 23, 0, tzinfo=timezone.utc)


class _Market:
    """The fields `_create_event_from_prediction_market` reads before refusing."""

    def __init__(self, name):
        self.source = "polymarket"
        self.external_id = None
        self.name = name
        self.llm_sport_category = "basketball"
        self.commence_time = NOW


@pytest.mark.asyncio
@pytest.mark.parametrize("name,_away", MARGIN_PROPS)
async def test_auto_create_mints_nothing(name, _away):
    """`session=None` is the assertion: the refusal lands before the registry."""
    from app.tasks.prediction_market_matching import (
        _create_event_from_prediction_market,
    )

    matchup = extract_matchup(name)
    assert matchup is not None, "the parse changed — this test is now vacuous"
    result = await _create_event_from_prediction_market(
        None, matchup, _Market(name), now=NOW
    )
    assert result is None


@pytest.mark.asyncio
async def test_the_real_game_control_runs_past_the_refusal():
    """Without this, a function that returned None for everything would pass."""
    from app.tasks.prediction_market_matching import (
        _create_event_from_prediction_market,
    )

    with pytest.raises(AttributeError):
        await _create_event_from_prediction_market(
            None,
            extract_matchup("Lakers vs. Pistons"),
            _Market("Lakers vs. Pistons"),
            now=NOW,
        )


def test_the_repair_population_cleans_the_new_labels():
    scripts = pathlib.Path(__file__).resolve().parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location(
        "repair_2871_phantom_derivative_events",
        scripts / "repair_2871_phantom_derivative_events.py",
    )
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)

    for away, clean in [
        ("Pistons - Exact Margin", "Pistons"),
        ("Rams - First Touchdown Scorer", "Rams"),
    ]:
        assert re.sub(repair.DERIV_RE, "", away, flags=re.IGNORECASE) == clean
