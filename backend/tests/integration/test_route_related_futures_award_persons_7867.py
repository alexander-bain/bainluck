"""#7867, person half — an award row lands on a club's card by ROSTER, never by a shared word.

WHAT A READER SEES (production, build v5013, 2026-09-24): the iPhone event page
for Duke v William & Mary (`/events/15317117`, kickoff 2026-09-26 19:30Z)
prints an AWARDS section with `Vaughn Blue` and `Duke Watson` (Doak Walker
Award) under Duke and `William "Pop" Watson III` (Heisman, AP Player of the
Year) under the Tribe. None of them plays for either school; `Blue`, `Duke`
and `William` are whole tokens of the club names `_team_name_patterns` emits.

THROUGH THE REAL HANDLER, on the #7867 club-half harness
(`test_route_related_futures_team_paths_7867.py`): `GET
/api/events/{id}/related-futures` against `app.main.app`, the database faked by
statement text, everything else the shipped code. The only addition here is a
per-team read that carries `roster_players`, because the roster is the
evidence the rule keeps.

Outcome ids 222335562 / 222335588 / 225957971 and market ids 59699635 / 189
are the production rows; the rest are constructed (9xxxxxxx) and say so.
"""

from app.utils.award_person_claim import AWARD_MARKET_TIER

from tests.integration.test_route_related_futures import _make_market, _MockResult
from tests.integration.test_route_related_futures_team_paths_7867 import (
    FOOTBALL,
    NCAAF,
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)
from types import SimpleNamespace

# William & Mary is FCS in life; the family read makes the league immaterial.
TRIBE = 900060
ROSTERED_FOOTBALL = FOOTBALL + [
    (TRIBE, NCAAF, "William and Mary Tribe", "W&M", "William & Mary", ["William & Mary"]),
]

DUKE_ROSTER = [{"name": "Darian Mensah"}, {"name": "Jaquez Moore"}]
TRIBE_ROSTER = [{"name": "Darius Wilson"}]

DOAK = 59699635      # production: Doak Walker Award Winner (tier 3)
HEISMAN = 189        # production: Heisman Trophy Winner (tier 3)
NCAAF_TITLE = 6601311
EXEC_AWARD = 90010001  # constructed: a non-award-tier market holding a person


def _market(id, name, tier):
    m = _make_market(id=id, name=name, source="kalshi")
    m.market_tier = tier
    return m


def _rostered_session(event, outcomes, *, resolved=True):
    """The club-half session, with the two per-team reads carrying rosters.

    ``resolved=False`` is an event whose teams match no `teams` row: no roster,
    no alias index, so only the name fallback can place a row.
    """
    session = _session(
        event, outcomes, roster=ROSTERED_FOOTBALL,
        home_team_id=15311 if resolved else None,
        away_team_id=TRIBE if resolved else None,
        sport_ids=[NCAAF],
    )
    inner = session.execute.side_effect
    per_team = iter([
        SimpleNamespace(id=15311, alternate_names=["Duke", "Blue Devils"], roster_players=DUKE_ROSTER),
        SimpleNamespace(id=TRIBE, alternate_names=["William & Mary"], roster_players=TRIBE_ROSTER),
    ] if resolved else [None, None])

    async def execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "from teams" in s and "teams.roster_players" in s and "teams.logo_url" not in s:
            if "teams.alternate_names" in s:
                return _MockResult(first=next(per_team, None))
            return _MockResult(rows=[])
        return await inner(stmt, *args, **kwargs)

    session.execute.side_effect = execute
    return session


async def _duke_v_tribe(monkeypatch, *, status="scheduled", resolved=True):
    event = _event(
        "Duke Blue Devils", "William and Mary Tribe",
        sport_key="americanfootball_ncaaf", sport_id=NCAAF, status=status,
    )
    doak = _market(DOAK, "Doak Walker Award Winner", AWARD_MARKET_TIER)
    heisman = _market(HEISMAN, "Heisman Trophy Winner", AWARD_MARKET_TIER)
    title = _market(NCAAF_TITLE, "NCAAF Championship Winner", 1)
    exec_award = _market(EXEC_AWARD, "Executive of the Year Winner?", 1)
    outcomes = [
        # production person rows claimed only by a club word — REFUSE
        _outcome(222335562, doak, "Vaughn Blue", 0.01),
        _outcome(222335588, doak, "Duke Watson", 0.01),
        _outcome(225957971, heisman, "William “Pop” Watson III", 0.01),
        # rostered players — KEEP, each on its own side
        _outcome(90000001, heisman, "Darian Mensah", 0.20),
        # (a suffix the roster lacks: the roster name claims it as a token)
        _outcome(90000002, doak, "Darius Wilson Jr.", 0.02),
        # an award outcome that IS the club — KEEP (whole label)
        _outcome(90000003, heisman, "Duke", 0.03),
        # club futures — KEEP, unchanged
        _outcome(34312774, title, "Duke Blue Devils", 0.001012),
        # a person in a NON-award tier — out of scope, unchanged (stays)
        _outcome(90000004, exec_award, "Duke Tobin", 0.19),
    ]
    return await _get(
        monkeypatch, _rostered_session(event, outcomes, resolved=resolved), event.id
    )


async def test_award_people_named_by_a_club_word_leave_both_cards(monkeypatch):
    body = await _duke_v_tribe(monkeypatch)
    assert not {222335562, 222335588, 225957971} & _ids(body)


async def test_rostered_award_people_stay_on_their_own_side(monkeypatch):
    body = await _duke_v_tribe(monkeypatch)
    assert 90000001 in _ids(body, "home_team_futures")
    assert 90000002 in _ids(body, "away_team_futures")


async def test_an_award_outcome_that_is_the_club_itself_stays(monkeypatch):
    body = await _duke_v_tribe(monkeypatch)
    assert 90000003 in _ids(body, "home_team_futures")


async def test_other_tiers_are_untouched(monkeypatch):
    body = await _duke_v_tribe(monkeypatch)
    home = _ids(body, "home_team_futures")
    assert 34312774 in home
    # Deliberately out of scope: the rule reads the AWARD tier only.
    assert 90000004 in home


async def test_a_finished_game_refuses_them_too(monkeypatch):
    # Roster names are not added to the patterns once a game is over, so a
    # finished page keeps only the whole-label club row among award outcomes.
    body = await _duke_v_tribe(monkeypatch, status="completed")
    assert not {222335562, 222335588, 225957971} & _ids(body)
    # Not vacuous: the finished page still serves the club's rows.
    assert {34312774, 90000003} <= _ids(body, "home_team_futures")


async def test_unresolved_teams_keep_the_club_label_and_refuse_the_person(monkeypatch):
    # No `teams` row, so no alias index answers `Duke` first: the whole-label
    # clause alone keeps the club's own award outcome, and nothing but a club
    # word stands behind `Duke Watson`.
    body = await _duke_v_tribe(monkeypatch, resolved=False)
    home = _ids(body, "home_team_futures")
    assert 90000003 in home
    assert 34312774 in home
    assert not {222335562, 222335588, 225957971} & _ids(body)
