"""#8632 — Gargzdai Basketball's card stops carrying every NBA/WNBA market.

Production `/api/events/15318532/related-futures` (2026-09-25 ~14:00Z): 775 rows on
Gargzdai's side over 37 markets; ONE was Gargzdai's own game line. Neither team
resolves to a `teams` row, so this is the unresolved-event path #7867/#8620 leave
alone by design — the defect is the bare `Basketball` pattern. Ids and names
below are production's, verbatim from that payload.

Harness: `test_route_related_futures_team_paths_7867.py` — the real handler with
the database answered by statement text.
"""

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

BASKETBALL_OTHER = 863201       # constructed; no `teams` rows for either side

NBA_CUP = 52755817              # "2026 Pro Basketball Cup Champion"
FINALS_MVP = 60629712           # "Pro Basketball Finals MVP Winner"
WNBA_TITLE = 12046267           # "Women's Pro Basketball Champion"
ATLANTIC = 52755689             # "Pro Basketball Atlantic Division Winner"
THIS_GAME = 62270799            # "Gargzdai Basketball vs. BC Neptunas Klaipeda"


def _gargzdai():
    return _event("Gargzdai Basketball", "BC Neptunas Klaipeda",
                  sport_key="basketball_other", sport_id=BASKETBALL_OTHER)


def _pro_basketball_rows():
    cup = _make_market(id=NBA_CUP, name="2026 Pro Basketball Cup Champion", source="kalshi")
    fmvp = _make_market(id=FINALS_MVP, name="Pro Basketball Finals MVP Winner", source="kalshi")
    wnba = _make_market(id=WNBA_TITLE, name="Women's Pro Basketball Champion", source="kalshi")
    atl = _make_market(id=ATLANTIC, name="Pro Basketball Atlantic Division Winner", source="kalshi")
    return [
        _outcome(198633611, cup, "Oklahoma City", 0.265, ticker="KXNBACUP-26-OKC"),
        _outcome(198633612, cup, "Charlotte", 0.21, ticker="KXNBACUP-26-CHA"),
        _outcome(226832334, fmvp, "Shai Gilgeous-Alexander", 0.47,
                 ticker="KXNBAFINMVP-27-SGILGEOUSALEXANDER2"),
        _outcome(68804163, wnba, "Las Vegas", 0.145, ticker="KXWNBA-26-LV"),
        _outcome(198632823, atl, "New York", 0.345, ticker="KXNBAATLANTIC-26-NYK"),
    ]


FOREIGN_IDS = {198633611, 198633612, 226832334, 68804163, 198632823}


async def test_gargzdai_loses_the_pro_basketball_markets_and_keeps_its_game(monkeypatch):
    event = _gargzdai()
    game = _make_market(id=THIS_GAME, name="Gargzdai Basketball vs. BC Neptunas Klaipeda",
                        source="polymarket")
    outcomes = _pro_basketball_rows() + [
        _outcome(235265546, game, "Gargzdai Basketball", 0.355),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=[], home_team_id=None, away_team_id=None,
                 sport_ids=[BASKETBALL_OTHER]),
        event.id,
    )
    assert not FOREIGN_IDS & _ids(body)
    assert 235265546 in _ids(body, "home_team_futures")


async def test_a_market_that_names_the_club_still_reaches_its_side(monkeypatch):
    """Recall: a market titled with the club's own word keeps every answer on
    that side through the market-name fallback — only the sport word stopped."""
    event = _gargzdai()
    lkl = _make_market(id=863210, name="Will Gargzdai make the LKL playoffs?", source="polymarket")
    nep = _make_market(id=863211, name="Neptunas Klaipeda to win the LKL?", source="polymarket")
    outcomes = [
        _outcome(863220, lkl, "Yes", 0.4),
        _outcome(863221, nep, "Yes", 0.3),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=[], home_team_id=None, away_team_id=None,
                 sport_ids=[BASKETBALL_OTHER]),
        event.id,
    )
    assert 863220 in _ids(body, "home_team_futures")
    assert 863221 in _ids(body, "away_team_futures")
