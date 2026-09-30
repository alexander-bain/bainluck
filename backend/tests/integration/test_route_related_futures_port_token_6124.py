"""#6124 — Port Vale's Bigger Picture stops listing the Chinese Super League and
Thai League titles.

WHAT A READER SAW (production, re-read 2026-09-30 05:55Z on
`/api/events/15315471/related-futures`): Port Vale v Northampton Town (League
Two). The Port Vale card served "Chinese Super League Champion" (Shanghai Port
FC, 28644456, `KXCHNSL-26-SHP`), "Chinese Super League: Winner" (Shanghai Port,
46856833) and "Thai League 1 Champion" (Port FC, 29935191). None of those
outcomes carries a `team_id`.

WHY. `_team_name_patterns("Port Vale")` emitted a bare `Port`, a whole token of
all three labels. Neither club has a `teams` row, so #7867's "part of a known
club's name" cover has nothing to cover the token with, and unknown is admitted.
The fix stops emitting the bare place-type word, as #5798 did for `State`.

Named cost (the recall census in the comment above `_GENERIC_PLACE_QUALIFIERS`):
ONE production row — Port FC's bare `Port` leg of Polymarket's AFC Champions
League Elite winner market (231092858) no longer reaches Port FC's own page. The
same bare token handed it to Port Vale, Shanghai Port and AS Port, so it could
never tell them apart.

Harness: `test_route_related_futures_team_paths_7867.py`. Production ids unless
marked constructed.
"""

import pytest

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

from app.routes.events import (
    _GENERIC_PLACE_QUALIFIERS,
    _NON_DISTINCTIVE_BARE_TOKENS,
    _team_name_patterns,
)
from app.utils.team_pattern_match import any_pattern_matches_token

LEAGUE2 = 889601
PORT_VALE = 16797

SOCCER = [
    (PORT_VALE, LEAGUE2, "Port Vale", None, None, ["Valiants"]),
]

FOREIGN_ROWS = {28644456, 46856833, 29935191, 231092858}
PORT_VALES_OWN = 226124001     # constructed id
NORTHAMPTONS_OWN = 226124002   # constructed id


def _outcomes():
    csl_k = _make_market(id=4121166, name="Chinese Super League Champion", source="kalshi")
    csl_p = _make_market(id=8641791, name="Chinese Super League: Winner", source="polymarket")
    thai = _make_market(id=4121831, name="Thai League 1 Champion", source="kalshi")
    acl = _make_market(id=60607650, name="AFC Champions League Elite 2026-27 Winner",
                       source="polymarket")
    l2 = _make_market(id=226124000, name="EFL League Two Winner", source="polymarket")
    return [
        _outcome(28644456, csl_k, "Shanghai Port FC", 0.01, ticker="KXCHNSL-26-SHP"),
        _outcome(46856833, csl_p, "Shanghai Port", 0.01),
        _outcome(29935191, thai, "Port FC", 0.12, ticker="KXTHAIL1-27-POR"),
        _outcome(231092858, acl, "Port", 0.02),
        _outcome(PORT_VALES_OWN, l2, "Port Vale", 0.06),
        _outcome(NORTHAMPTONS_OWN, l2, "Northampton Town", 0.03),
    ]


def _port_vale_v_northampton():
    return _event("Port Vale", "Northampton Town",
                  sport_key="soccer_england_league2", sport_id=LEAGUE2)


async def test_port_vale_loses_shanghai_port_and_port_fc(monkeypatch):
    event = _port_vale_v_northampton()
    body = await _get(
        monkeypatch,
        _session(event, _outcomes(), roster=SOCCER, home_team_id=PORT_VALE,
                 away_team_id=None, sport_ids=[LEAGUE2]),
        event.id,
    )
    assert not FOREIGN_ROWS & _ids(body)
    assert PORT_VALES_OWN in _ids(body, "home_team_futures")
    assert NORTHAMPTONS_OWN in _ids(body, "away_team_futures")


async def test_shanghai_ports_own_page_keeps_its_title_legs(monkeypatch):
    """CONTROL, the other direction: Shanghai Port still reaches both of its
    Chinese Super League legs on its full name and on `Shanghai`."""
    event = _event("Shanghai Port", "Beijing Guoan", sport_key="soccer_other", sport_id=LEAGUE2)
    body = await _get(
        monkeypatch,
        _session(event, _outcomes()[:2], roster=[], home_team_id=None,
                 away_team_id=None, sport_ids=[LEAGUE2]),
        event.id,
    )
    assert {28644456, 46856833} <= _ids(body, "home_team_futures")


class TestThePatterns:
    @pytest.mark.parametrize(
        "team,expected",
        [
            # city half of a two-word name
            ("Port Vale", ["Port Vale", "Vale"]),
            ("Port FC", ["Port FC"]),
            ("Port Adelaide", ["Port Adelaide", "Adelaide"]),
            # mascot slot
            ("Shanghai Port", ["Shanghai Port", "Shanghai"]),
            ("AS Port", ["AS Port"]),
            # the >=3-word loop
            ("Port Adelaide Power",
             ["Port Adelaide Power", "Power", "Port Adelaide", "Adelaide"]),
        ],
    )
    def test_the_bare_port_is_dropped_at_every_slot(self, team, expected):
        assert _team_name_patterns(team) == expected

    @pytest.mark.parametrize(
        "label",
        ["Shanghai Port FC", "Shanghai Port", "Port FC", "Port",
         "Chinese Super League Champion"],
    )
    def test_no_foreign_label_matches_port_vale(self, label):
        assert not any_pattern_matches_token(label, _team_name_patterns("Port Vale"))

    @pytest.mark.parametrize(
        "team,own_label",
        [
            ("Port Vale", "Port Vale FC (-1.5)"),
            ("Port Vale", "Reg Time: Port Vale"),
            ("Port FC", "Port FC wins by more than 1.5 goals"),
            ("Shanghai Port", "Shanghai Port FC"),
            ("AS Port", "AS Port vs. Zamalek SC: O/U 2.5"),
            ("Port Adelaide Power", "Port Adelaide Power vs Sydney Swans"),
        ],
    )
    def test_a_club_still_matches_its_own_row(self, team, own_label):
        assert any_pattern_matches_token(own_label, _team_name_patterns(team))

    def test_port_is_a_place_qualifier_and_the_earlier_ones_stay(self):
        assert "port" in _GENERIC_PLACE_QUALIFIERS
        assert "port" in _NON_DISTINCTIVE_BARE_TOKENS
        assert {"state", "north", "saint"} <= _GENERIC_PLACE_QUALIFIERS
