"""#8980 — every Miami Hurricanes game was missing its Kalshi price.

Kalshi names the school ``Miami (FL)`` ("Miami (FL) vs Clemson"); ESPN names the
event row ``Miami Hurricanes``. ``_fuzzy_team_match`` found no bridge, so
``_score_candidates``' two-sided name gate refused every candidate: 14 of 14
Miami (FL) game markets unlinked on production (26 Sep 2026), including
Clemson–Miami on 3 Oct (62384059 → 14870012).

The bridge is an exact whole-name pair, not a rule: dropping the qualifier
would let ``Miami (OH)`` reach the Hurricanes too, and the RedHawks are a
different school. So every test here runs in BOTH directions — the Florida form
reaches the Hurricanes, and neither Miami ever reaches the other.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import _score_candidates
from app.utils.prediction_market_matching import (
    _fuzzy_team_match,
    extract_matchup,
)

HURRICANES = "Miami Hurricanes"
REDHAWKS = "Miami (OH) RedHawks"


class TestTheNameGate:
    @pytest.mark.parametrize("a,b", [("Miami (FL)", HURRICANES), (HURRICANES, "Miami (FL)")])
    def test_miami_fl_is_the_hurricanes(self, a, b):
        assert _fuzzy_team_match(a, b)

    @pytest.mark.parametrize("a,b", [
        ("Miami (FL)", REDHAWKS), (REDHAWKS, "Miami (FL)"),
        ("Miami (OH)", HURRICANES), (HURRICANES, "Miami (OH)"),
        ("Miami (FL)", "Miami RedHawks"), ("Miami (OH)", "Miami (FL)"),
    ])
    def test_neither_miami_reaches_the_other(self, a, b):
        assert not _fuzzy_team_match(a, b)

    def test_miami_oh_still_reaches_its_own_row(self):
        assert _fuzzy_team_match("Miami (OH)", REDHAWKS)


def _event(eid, home, away, commence):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key="americanfootball_ncaaf"),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status="scheduled",
        external_id=f"oddsapi:{eid}",
        sport_id=7,
    )


def _market(name, ticker):
    return SimpleNamespace(
        external_id=ticker, name=name, source="kalshi",
        llm_sport_category="football", commence_time=None,
    )


NOW = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)
# Production's row 14870012 carries ESPN's 04:00Z TBD placeholder.
OCT3 = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)


class TestTheGameLinks:
    """Assert the decision the matcher makes, not only the helper."""

    def test_clemson_miami_binds_to_its_event(self):
        name, ticker = "Miami (FL) vs Clemson", "KXNCAAFGAME-26OCT03MIACLEM"
        result = _score_candidates(
            [_event(14870012, "Clemson Tigers", HURRICANES, OCT3)],
            extract_matchup(name, ticker), _market(name, ticker), NOW, OCT3,
        )
        assert result is not None and result["event_id"] == 14870012

    def test_miami_fl_market_takes_the_hurricanes_not_the_redhawks(self):
        """Same day, a Miami on each row: the Florida market takes the Florida row."""
        name, ticker = "Miami (FL) vs Clemson", "KXNCAAFGAME-26OCT03MIACLEM"
        decoy = _event(1, REDHAWKS, "Clemson Tigers", OCT3)
        real = _event(2, "Clemson Tigers", HURRICANES, OCT3)
        result = _score_candidates(
            [decoy, real], extract_matchup(name, ticker), _market(name, ticker),
            NOW, OCT3,
        )
        assert result is not None and result["event_id"] == 2

    def test_miami_oh_market_never_takes_a_hurricanes_row(self):
        name, ticker = "Bowling Green vs Miami (OH)", "KXNCAAFGAME-26OCT03BGSUMOH"
        wrong = _event(3, HURRICANES, "Bowling Green Falcons", OCT3)
        assert _score_candidates(
            [wrong], extract_matchup(name, ticker), _market(name, ticker), NOW, OCT3,
        ) is None

    def test_miami_oh_market_still_takes_its_own_row(self):
        name, ticker = "Bowling Green vs Miami (OH)", "KXNCAAFGAME-26OCT03BGSUMOH"
        own = _event(4, REDHAWKS, "Bowling Green Falcons", OCT3)
        result = _score_candidates(
            [own], extract_matchup(name, ticker), _market(name, ticker), NOW, OCT3,
        )
        assert result is not None and result["event_id"] == 4
