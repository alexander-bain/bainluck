"""#8896 — a settled UNLV page stops showing Ole Miss's national-title chance.

WHAT A READER SAW (production, 2026-09-26 ~19:19Z, shopper pass 0070):
`/events/15315996` UNLV Rebels 38, Akron Zips 10 (NCAAF, final). Bigger
Picture → Rebels → CHAMPIONSHIP PATH read "NCAA Football: 2027 National
Champion — 9%". That is outcome 55309441 `Mississippi Rebels` (market 9962834,
Polymarket), Ole Miss's price, `team_id NULL`: no `teams` row carries that
name, so the ticker, alias, `team_id` and #7867 paths all stay silent and the
bare mascot `Rebels` — listed by UNLV 15359 AND Ole Miss 83 — admitted it.

THE RULE (`app/utils/team_label_identity.label_qualifies_a_shared_mascot`): a
mascot a foreign club also carries, with a word in front of it that is none of
ours, names the other school. Ole Miss keeps the row (`Mississippi` clips to
`Miss`); UNLV keeps every row of its own.

Harness: `test_route_related_futures_team_paths_7867.py` — the real handler
with the database answered by statement text. Production ids where the issue or
db-query gave them; constructed ids in the 88960xx range.
"""

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

NCAAF = 889601

FOOTBALL = [
    (15359, NCAAF, "UNLV Rebels", "UNLV", "UNLV", ["UNLV", "Rebels"]),
    (83, NCAAF, "Ole Miss Rebels", "MISS", "Ole Miss", ["Rebels", "Ole Miss"]),
    (900001, NCAAF, "Akron Zips", "AKR", "Akron", ["Akron", "Zips"]),
    (900002, NCAAF, "Florida Gators", "FLA", "Florida", ["Florida", "Gators"]),
    (9, NCAAF, "LSU Tigers", "LSU", "LSU", ["LSU", "Tigers"]),
]

PM_TITLE = 9962834      # production: NCAA Football: 2027 National Champion
OA_TITLE = 6601311      # production: NCAAF Championship Winner
MW_WINNER = 4121126     # production: College Football Mountain West Championship Winner


def _outcomes():
    pm = _make_market(id=PM_TITLE, name="NCAA Football: 2027 National Champion", source="polymarket")
    oa = _make_market(id=OA_TITLE, name="NCAAF Championship Winner", source="odds_api")
    mw = _make_market(id=MW_WINNER, name="College Football Mountain West Championship Winner",
                      source="kalshi")
    return [
        _outcome(55309441, pm, "Mississippi Rebels", 0.0925),          # production — the specimen
        _outcome(55309451, pm, "LSU Tigers", 0.0875, team_id=9),       # production — control
        _outcome(34312788, oa, "UNLV Rebels", 0.00058),                # production — UNLV's own
        _outcome(34312740, oa, "Ole Miss Rebels", 0.041765),           # production — Ole Miss's own
        _outcome(29928164, mw, "UNLV", 0.13),                          # production — UNLV's own
        _outcome(88960001, mw, "Rebels", 0.13),                        # constructed — bare mascot
    ]


async def test_unlv_loses_ole_misss_title_row_and_keeps_its_own(monkeypatch):
    event = _event("Akron Zips", "UNLV Rebels", sport_key="americanfootball_ncaaf",
                   sport_id=NCAAF, status="completed")
    body = await _get(
        monkeypatch,
        _session(event, _outcomes(), roster=FOOTBALL, home_team_id=900001,
                 away_team_id=15359, sport_ids=[NCAAF]),
        event.id,
    )
    away = _ids(body, "away_team_futures")
    assert 55309441 not in _ids(body)
    assert {34312788, 29928164, 88960001} <= away
    assert not {34312740, 55309451} & _ids(body)


async def test_ole_miss_keeps_its_polymarket_title_row(monkeypatch):
    event = _event("Florida Gators", "Ole Miss Rebels", sport_key="americanfootball_ncaaf",
                   sport_id=NCAAF)
    body = await _get(
        monkeypatch,
        _session(event, _outcomes(), roster=FOOTBALL, home_team_id=900002,
                 away_team_id=83, sport_ids=[NCAAF]),
        event.id,
    )
    away = _ids(body, "away_team_futures")
    assert {55309441, 34312740} <= away
    assert not {34312788, 29928164, 55309451} & _ids(body)
