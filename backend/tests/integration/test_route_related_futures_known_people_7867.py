"""A roster-confirmed person cannot be claimed by a club word in any tier.

Real failure labels/ids: Lindor 2114344 (tier 1) on Giants 15318410 and
Malik Washington 225995556 (tier 4) on Washington State 15315943. Team ids
and unrelated controls below are constructed except where documented by the
shared 7867 harness. The real handler runs; only database replies are faked.
"""

from types import SimpleNamespace

import pytest

from app.routes import events as route
from tests.integration.test_route_related_futures import _MockResult
from tests.integration.test_route_related_futures_award_persons_7867 import _market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    BASEBALL,
    FOOTBALL,
    MLB,
    NCAAF,
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)


@pytest.fixture(autouse=True)
def fresh_roster_index(monkeypatch):
    monkeypatch.setattr(route, "_roster_index", {})
    monkeypatch.setattr(route, "_roster_index_expires_at", 0.0)


async def _page(monkeypatch, *, football=False, status="scheduled", known=True):
    name = "Malik Washington" if football else "Francisco Lindor"
    person_id = 225995556 if football else 2114344
    home = "Washington State Cougars" if football else "San Francisco Giants"
    sport_id = NCAAF if football else MLB
    home_id = 900100 if football else 6609
    team_rows = (
        FOOTBALL
        + [(900100, NCAAF, home, "WSU", "Washington State", ["Washington St."])]
        if football
        else BASEBALL
    )
    event = _event(
        home,
        "Control Opponent",
        sport_key="americanfootball_ncaaf" if football else "baseball_mlb",
        sport_id=sport_id,
        status=status,
    )
    person_market = _market(
        900101,
        (
            "Division I: Passing Touchdowns Leader"
            if football
            else "MLB: 2026 NL Hank Aaron Winner"
        ),
        4 if football else 1,
    )
    team_market = _market(
        900102, "College Football Champion" if football else "MLB Champion", 1
    )
    own_player = "Own Roster Player"
    outcomes = [
        _outcome(person_id, person_market, name, 0.0005),
        _outcome(
            900103,
            team_market,
            "Washington St." if football else "San Francisco Giants",
            0.2,
        ),
        _outcome(900104, person_market, own_player, 0.3),
        # Unknown is not evidence of a person; preserve the prior fallback.
        _outcome(
            900105,
            team_market,
            "Washington Unknown" if football else "Francisco Unknown",
            0.4,
        ),
    ]
    db = _session(
        event,
        outcomes,
        roster=team_rows,
        home_team_id=home_id,
        away_team_id=None,
        sport_ids=[sport_id],
    )
    inner = db.execute.side_effect
    index_reads = []

    async def execute(stmt, *args, **kwargs):
        text = str(stmt).lower()
        if "jsonb_array_elements(t.roster_players)" in text:
            index_reads.append(text)
            # The name can come from another league: identity is personhood,
            # never inferred membership of either club on this event.
            return _MockResult(
                rows=(
                    [
                        (565 if football else 10737, name.lower()),
                        (home_id, own_player.lower()),
                    ]
                    if known
                    else []
                )
            )
        if (
            "teams.alternate_names" in text
            and "teams.roster_players" in text
            and "teams.logo_url" not in text
        ):
            return _MockResult(
                first=SimpleNamespace(
                    id=home_id,
                    alternate_names=["Washington St."] if football else [],
                    roster_players=[{"name": own_player}],
                )
            )
        return await inner(stmt, *args, **kwargs)

    db.execute.side_effect = execute
    return await _get(monkeypatch, db, event.id), person_id, index_reads


@pytest.mark.parametrize("football", [False, True])
@pytest.mark.parametrize("status", ["scheduled", "completed"])
async def test_known_person_cannot_borrow_club_word_in_other_tiers(
    monkeypatch, football, status
):
    body, person_id, reads = await _page(monkeypatch, football=football, status=status)
    assert person_id not in _ids(body)
    assert 900103 in _ids(body, "home_team_futures")
    assert 900105 in _ids(body, "home_team_futures")
    assert len(reads) == 1  # Reuse the existing cache, not a query per outcome.


async def test_own_rostered_player_is_kept_with_its_club(monkeypatch):
    body, _, _ = await _page(monkeypatch)
    assert 900104 in _ids(body, "home_team_futures")


async def test_unestablished_person_identity_does_not_remove_unknown_labels(
    monkeypatch,
):
    body, person_id, _ = await _page(monkeypatch, known=False)
    assert person_id in _ids(body)
    assert {900103, 900105} <= _ids(body, "home_team_futures")
