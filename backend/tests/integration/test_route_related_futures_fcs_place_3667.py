"""#3667 — an FCS game's Bigger Picture describes its own teams, not the FBS
schools their place names were cut down to.

SPECIMEN (production, 2026-10-09 17:55–17:57Z, 390 x 844, issue #3667 comment
6091026276): `/events/15326607`, Florida A&M Rattlers @ Alabama State Hornets.
Bigger Picture served questions 58420064 / 58420073 ("Will Alabama / Florida
make the 2027 College Football Playoff National Championship Game?") and
College Football Playoff paths of 78% on the Hornets and 33% on the Rattlers.

THROUGH THE REAL HANDLER, with the #7867 harness: `GET /api/events/{id}/
related-futures` against `app.main.app`, only the database faked. Two arms
per side — the side resolved to a `teams` row, and neither side resolved
(#8950's name-only identities) — because which one production takes for
these two programs is not established here, and the repair must hold in both.
The question markets carry the specimen ids; every other id is constructed
(9xxxxxx / 36670xxx) and says so. Every assertion names literal outcome ids,
so a mutant that hides every row fails on the controls.
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

NCAAF, NFL, FCS = 700100, 700101, 700102

FOOTBALL = [
    (900310, NCAAF, "Alabama Crimson Tide", "ALA", "Alabama", ["Alabama"]),
    (900311, NCAAF, "Florida Gators", "FLA", "Florida", ["Florida"]),
    (900312, NCAAF, "Florida State Seminoles", "FSU", "Florida State", ["Florida St."]),
    (900320, NFL, "Carolina Panthers", "CAR", "Carolina", ["Carolina", "Panthers"]),
]
FCS_ROWS = [
    (900330, FCS, "Alabama State Hornets", "ALST", "Alabama State", ["Alabama St"]),
    (900331, FCS, "Florida A&M Rattlers", "FAMU", "Florida A&M", ["Florida A&M"]),
    (900333, FCS, "Jackson State Tigers", "JKST", "Jackson State", []),
]

ALABAMA_Q = 58420064   # SPECIMEN market
FLORIDA_Q = 58420073   # SPECIMEN market


def _markets():
    alabama_q = _make_market(
        id=ALABAMA_Q, source="polymarket",
        name="Will Alabama make the 2027 College Football Playoff National Championship Game?",
    )
    florida_q = _make_market(
        id=FLORIDA_Q, source="polymarket",
        name="Will Florida make the 2027 College Football Playoff National Championship Game?",
    )
    cfp = _make_market(id=9366701, name="College Football Playoff", source="kalshi")
    swac = _make_market(id=9366702, name="SWAC Championship Winner", source="kalshi")
    matchup = _make_market(id=9366703, name="SWAC Championship Game Matchup", source="kalshi")
    return alabama_q, florida_q, cfp, swac, matchup


def _outcomes():
    alabama_q, florida_q, cfp, swac, matchup = _markets()
    return [
        # the specimen's associations — REFUSE
        _outcome(36670001, alabama_q, "Yes", 0.78),          # reached by MARKET name
        _outcome(36670002, alabama_q, "No", 0.22),
        _outcome(36670003, florida_q, "Yes", 0.33),
        _outcome(36670004, florida_q, "No", 0.67),
        _outcome(36670005, cfp, "Alabama", 0.78),            # reached by `Alabama`
        _outcome(36670006, cfp, "Florida", 0.33),            # reached by `Florida`
        _outcome(36670007, cfp, "Florida St.", 0.05),
        # the programs' own context — KEEP
        _outcome(36670011, swac, "Alabama St.", 0.31),
        _outcome(36670012, swac, "Florida A&M", 0.18),
        _outcome(36670013, matchup, "Alabama St. vs Jackson St.", 0.22),
        _outcome(36670014, matchup, "Florida A&M vs Jackson State", 0.12),
    ]


REFUSED = {36670001, 36670002, 36670003, 36670004, 36670005, 36670006, 36670007}
HOME_KEPT = {36670011, 36670013}
AWAY_KEPT = {36670012, 36670014}


@pytest.mark.parametrize("resolved", [True, False], ids=["resolved", "neither-resolved"])
async def test_the_fcs_game_keeps_its_own_context_and_loses_the_fbs_paths(monkeypatch, resolved):
    event = _event(
        "Alabama State Hornets", "Florida A&M Rattlers",
        sport_key="americanfootball_ncaaf", sport_id=NCAAF, status="live",
    )
    body = await _get(
        monkeypatch,
        _session(
            event, _outcomes(),
            roster=FOOTBALL + (FCS_ROWS if resolved else []),
            home_team_id=900330 if resolved else None,
            away_team_id=900331 if resolved else None,
            sport_ids=[NCAAF],
        ),
        event.id,
    )
    assert HOME_KEPT <= _ids(body, "home_team_futures")
    assert AWAY_KEPT <= _ids(body, "away_team_futures")
    assert not REFUSED & _ids(body)


async def test_on_alabamas_own_page_the_same_rows_are_alabamas(monkeypatch):
    """The positive control the refusal must not reach: the identical question
    and field rows still belong to the school whose place they name."""
    event = _event(
        "Alabama Crimson Tide", "Florida Gators",
        sport_key="americanfootball_ncaaf", sport_id=NCAAF,
    )
    body = await _get(
        monkeypatch,
        _session(
            event, _outcomes(), roster=FOOTBALL + FCS_ROWS,
            home_team_id=900310, away_team_id=900311, sport_ids=[NCAAF],
        ),
        event.id,
    )
    assert {36670001, 36670005} <= _ids(body, "home_team_futures")
    assert {36670003, 36670006} <= _ids(body, "away_team_futures")
    # …and the FCS programs' own rows are not theirs.
    assert not {36670011, 36670012} & _ids(body)
