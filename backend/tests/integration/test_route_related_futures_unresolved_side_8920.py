"""#8920 — Brown's page stops showing the Chicago Bears' Super Bowl odds.

WHAT A READER SAW (production, 2026-09-26 ~20:31Z, lane1 LOOK after #5697):
`/events/15317759` Brown Bears 10, Harvard Crimson 14 (FCS, final). Bigger
Picture → "Bears" → Champion 2% · NFC Champion 7%: Polymarket 129037/129171,
outcome "Chicago Bears". The served `home_team_futures` also carried the NFL
Super Bowl "Chicago Bears" (1309498) and NCAAF title "Baylor Bears"
(34312763). Brown has NO `teams` row in any football sport (`home_team_id`
NULL), so its identity was unarmed and every "Bears" label was Brown's.

Harvard (19284) resolves, so the family roster is read; Brown's side now gets
the name-only identity (`app/utils/team_label_identity._name_only_identity`).

Harness: `test_route_related_futures_team_paths_7867.py`. Production ids.
"""

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

NCAAF, FCS, NFL = 889201, 889202, 889203

FOOTBALL = [
    (8, NCAAF, "Baylor Bears", "BAY", "Baylor", ["Baylor", "Bears"]),
    (561, NFL, "Chicago Bears", "CHI", "Chicago", ["Bears"]),
    (18635, FCS, "Northern Colorado Bears", "UNCO", "Northern Colorado", ["N Colorado", "Bears"]),
    (19284, FCS, "Harvard Crimson", None, None, None),
]


def _outcomes():
    sb = _make_market(id=86832, name="NFL Super Bowl Winner", source="odds_api")
    champ = _make_market(id=129037, name="Pro Football: 2027 Champion", source="polymarket")
    oa = _make_market(id=6601311, name="NCAAF Championship Winner", source="odds_api")
    fcs = _make_market(id=59693654, name="College Football FCS National Championship Winner",
                       source="kalshi")
    return [
        _outcome(1309498, sb, "Chicago Bears", 0.025842),    # the specimen
        _outcome(1709113, champ, "Chicago Bears", 0.02),      # the "Champion 2%" leg
        _outcome(34312763, oa, "Baylor Bears", 0.00116),
        _outcome(225952161, fcs, "Brown", 0.01),              # Brown's own
        _outcome(225952162, fcs, "Harvard", 0.02),            # constructed id — Harvard's own
    ]


async def test_brown_loses_the_chicago_and_baylor_bears_and_keeps_its_own(monkeypatch):
    event = _event("Brown Bears", "Harvard Crimson", sport_key="americanfootball_ncaaf_fcs",
                   sport_id=FCS, status="completed")
    body = await _get(
        monkeypatch,
        _session(event, _outcomes(), roster=FOOTBALL, home_team_id=None,
                 away_team_id=19284, sport_ids=[FCS, NCAAF, NFL]),
        event.id,
    )
    assert not {1309498, 1709113, 34312763} & _ids(body)
    assert 225952161 in _ids(body, "home_team_futures")
    assert 225952162 in _ids(body, "away_team_futures")
