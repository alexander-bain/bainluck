"""#9121 — a half/quarter leg serves its LINE as `threshold`, never the period.

## The ship

The installed iPhone build (1.0.1(26), built from `6448d6d805`, which does not
carry native's reader half #9134) places a half-margin rung at the served
`threshold`. On `/events/15315795` (Cruz Azul 3-3 Toluca) every Kalshi half row
served the period's digit:

    Cruz Azul wins the 1H by more than 1.5 goals   threshold 1.0   (line 1.5)
    Toluca wins 2nd Half                           threshold 2.0   (no line)

so the 1st-half margin band sat at "Azul by 1". NFL quarter spreads ("CIN Bengals
wins 3Q by over 6.5 points") served 3.0 the same way. After this change a spread
leg serves its line and a winner leg serves None.

## Vacuity

The route tests drive the REAL `_build_game_markets`. Mutants, each killed:

  * call site reverted to `_extract_threshold`  → every route test
  * winner arm deleted (winners fall through)   → the digit-team winner tests
    alone (on ordinary names the strip already leaves no number)
  * margin-wording read deleted                 → the digit-team spread tests
  * period-token strip deleted                  → the '2nd Quarter -2.5' test

Controls that must NOT move: a Kalshi 1H spread leg whose name carries no period
token ("wins by over 3.5 points") and a Polymarket leg with no number ("Bengals").
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _extract_period_threshold, _game_markets_cache

NOW = datetime.now(timezone.utc).replace(microsecond=0)
KICKOFF = NOW + timedelta(hours=3)


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# The helper, on the production wordings
# ─────────────────────────────────────────────────────────────────────────────


class TestThePeriodTokenIsNotTheLine:
    @pytest.mark.parametrize(
        "name, market_type, line",
        [
            ("Cruz Azul wins the 1H by more than 1.5 goals", "half_spread", 1.5),
            ("Toluca wins the 2H by more than 1.5 goals", "half_spread", 1.5),
            ("CIN Bengals wins 2H by over 3.5 points", "half_spread", 3.5),
            ("CIN Bengals wins 3Q by over 6.5 points", "quarter_spread", 6.5),
            ("PIT Steelers wins 4Q by over 10.5 points", "quarter_spread", 10.5),
            ("Dallas wins 2nd Quarter by over 7.5 points", "quarter_spread", 7.5),
            ("Dallas wins first half by over 2.5 points", "half_spread", 2.5),
            ("Atlanta wins first 5 innings by over 1.5 runs", "half_spread", 1.5),
            # a team name's digits are not the line either
            ("SF 49ers wins 2H by over 3.5 points", "half_spread", 3.5),
            ("SF 49ers wins by over 7.5 points", "half_spread", 7.5),
            # no margin wording: the period strip alone carries it
            ("Atlanta Braves -1.5 first 5 innings", "half_spread", 1.5),
            ("Dallas Cowboys 2nd Quarter -2.5", "quarter_spread", 2.5),
        ],
    )
    def test_a_spread_leg_serves_the_line(self, name, market_type, line):
        assert _extract_period_threshold(name, market_type) == line

    @pytest.mark.parametrize(
        "name, market_type",
        [
            ("Cruz Azul wins 1st Half", "half_winner"),
            ("Tie 2nd Half", "half_winner"),
            ("Cincinnati wins 3rd Quarter", "quarter_winner"),
            ("Tie 4th Quarter", "quarter_winner"),
            # the strip alone would leave "76" and serve it as a line
            ("Philadelphia 76ers wins 1st Quarter", "quarter_winner"),
            ("San Francisco 49ers wins 2nd Half", "half_winner"),
        ],
    )
    def test_a_winner_leg_serves_no_line(self, name, market_type):
        assert _extract_period_threshold(name, market_type) is None

    def test_a_leg_with_no_period_token_is_unchanged(self):
        """Control: Kalshi's 1H NFL wording names no period; it already worked."""
        assert _extract_period_threshold(
            "CIN Bengals wins by over 3.5 points", "half_spread"
        ) == 3.5

    def test_a_leg_with_no_number_stays_none(self):
        """Control: Polymarket's leg is the team name; the line is elsewhere."""
        assert _extract_period_threshold("Bengals", "half_spread") is None


# ─────────────────────────────────────────────────────────────────────────────
# The served payload
# ─────────────────────────────────────────────────────────────────────────────


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _market(*, id, name, external_id, sport_category="soccer"):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", "open"
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = sport_category
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = prob
    outcome.is_winner = None
    outcome.resolution_source = None
    outcome.last_updated = NOW
    return outcome


def _event(*, sport_key, home, away):
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "scheduled", 1
    event.sport = MagicMock()
    event.sport.key = sport_key
    event.home_team_name, event.away_team_name = home, away
    event.home_score = event.away_score = None
    event.commence_time = KICKOFF
    event.completed_at = None
    event.box_score_data = None
    event.period, event.game_clock = None, None
    return event


def _payload(event, markets, outcomes):
    obs = [
        SimpleNamespace(
            id=o.id,
            observed_at=NOW - timedelta(minutes=2),
            price_changed_at=None,
            resolution_source=None,
            current_probability=None,
        )
        for o in outcomes
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=event),
            _result(),                 # #3391 serve-fold sports read
            _result(rows=[]),          # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),      # polymarket parent groups
            _result(rows=[]),          # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=obs),     # #4970 the observation load
        ]
    )
    response, _status, _ids = asyncio.run(events_route._build_game_markets(42, db))
    return response


def _served(payload):
    return {
        pm["outcome_name"]: pm
        for pm in payload.get("period_markets", [])
    }


def _soccer_specimen():
    """`/events/15315795`'s Kalshi half markets, pre-match."""
    event = _event(sport_key="soccer_mexico_ligamx", home="Cruz Azul", away="Toluca")
    spread = _market(
        id=801,
        name="Cruz Azul vs Toluca: 1st Half Spread",
        external_id="KXLIGAMX1HSPREAD-26SEP27CAZTOL",
    )
    winner = _market(
        id=802,
        name="Cruz Azul vs Toluca: 1st Half Winner",
        external_id="KXLIGAMX1HWINNER-26SEP27CAZTOL",
    )
    outcomes = [
        _outcome(id=901, market_id=801,
                 name="Cruz Azul wins the 1H by more than 1.5 goals", prob=0.12),
        _outcome(id=902, market_id=801,
                 name="Toluca wins the 1H by more than 1.5 goals", prob=0.09),
        _outcome(id=903, market_id=802, name="Cruz Azul wins 1st Half", prob=0.36),
        _outcome(id=904, market_id=802, name="Tie 1st Half", prob=0.40),
        _outcome(id=905, market_id=802, name="Toluca wins 1st Half", prob=0.24),
    ]
    return event, [spread, winner], outcomes


class TestTheServedPeriodRows:
    def test_the_soccer_half_spread_serves_1_5_not_1(self):
        served = _served(_payload(*_soccer_specimen()))
        for name in (
            "Cruz Azul wins the 1H by more than 1.5 goals",
            "Toluca wins the 1H by more than 1.5 goals",
        ):
            assert name in served, f"specimen leg not served; got {sorted(served)}"
            assert served[name]["threshold"] == 1.5, served[name]

    def test_the_soccer_half_winner_serves_no_line(self):
        served = _served(_payload(*_soccer_specimen()))
        for name in ("Cruz Azul wins 1st Half", "Tie 1st Half", "Toluca wins 1st Half"):
            assert name in served, f"specimen leg not served; got {sorted(served)}"
            assert served[name]["market_type"] == "half_winner"
            assert served[name]["threshold"] is None, served[name]

    def test_the_nfl_quarter_spread_serves_its_line_and_the_1h_control_holds(self):
        event = _event(sport_key="americanfootball_nfl",
                       home="Cincinnati Bengals", away="Pittsburgh Steelers")
        q3 = _market(id=811, name="Pittsburgh at Cincinnati: 3rd Quarter Spread",
                     external_id="KXNFL3QSPREAD-26SEP27PITCIN",
                     sport_category="americanfootball")
        h1 = _market(id=812, name="Pittsburgh at Cincinnati: 1st Half Spread",
                     external_id="KXNFL1HSPREAD-26SEP27PITCIN",
                     sport_category="americanfootball")
        outcomes = [
            _outcome(id=911, market_id=811,
                     name="CIN Bengals wins 3Q by over 6.5 points", prob=0.2),
            _outcome(id=912, market_id=812,
                     name="CIN Bengals wins by over 3.5 points", prob=0.4),
        ]
        served = _served(_payload(event, [q3, h1], outcomes))
        assert served["CIN Bengals wins 3Q by over 6.5 points"]["threshold"] == 6.5
        assert served["CIN Bengals wins by over 3.5 points"]["threshold"] == 3.5
