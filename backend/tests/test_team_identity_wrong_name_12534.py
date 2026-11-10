"""A venue name must not turn a wrong-club fuzzy hit into a durable identity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.models import Team
from app.services.team_identity import TeamIdentityService, _NAME_WITNESS_LIMIT


def team(tid, name, aliases=(), espn_id=None):
    return Team(
        id=tid,
        name=name,
        sport_id=1,
        alternate_names=list(aliases),
        espn_id=espn_id,
    )


class Session:
    """Real Team values and statement capture; SQL scoping has a PG test too."""

    def __init__(self, target, witnesses=()):
        self.target = target
        self.witnesses = list(witnesses)
        self.reads = []
        self.writes = []
        self.gets = []

    async def get(self, model, pk):
        assert model is Team
        self.gets.append(pk)
        return self.target if self.target and self.target.id == pk else None

    async def execute(self, stmt):
        if stmt.is_insert:
            self.writes.append(stmt)
            return None
        self.reads.append(stmt)
        rows = [(t.id, t.name, t.alternate_names, t.espn_id) for t in self.witnesses]
        return SimpleNamespace(all=lambda: rows)


# Nov 10 adjudicated specimens, names only; these never connect to production.
BAD_LINKS = [
    ("Western Bulldogs", "Richmond", [], "Western Bulldogs", [], "aussierules_afl"),
    (
        "PSG",
        "Stade Brest",
        ["Brest"],
        "Paris Saint-Germain",
        ["PSG"],
        "soccer_france_ligue_one",
    ),
    (
        "Le Mans FC",
        "Le Havre AC",
        [],
        "Le Mans FC",
        ["Le Mans"],
        "soccer_france_ligue_one",
    ),
    (
        "Chiefs",
        "Indianapolis Colts",
        ["Colts"],
        "Kansas City Chiefs",
        ["Chiefs"],
        "americanfootball_nfl",
    ),
    (
        "Bills",
        "Detroit Lions",
        ["Lions"],
        "Buffalo Bills",
        ["Bills"],
        "americanfootball_nfl",
    ),
    ("Stars", "St Louis Blues", ["Blues"], "Dallas Stars", ["Stars"], "icehockey_nhl"),
    (
        "Lightning",
        "Montreal Canadiens",
        ["Canadiens"],
        "Tampa Bay Lightning",
        ["Lightning"],
        "icehockey_nhl",
    ),
    (
        "Geelong Cats",
        "Fremantle Dockers",
        ["Fremantle"],
        "Geelong Cats",
        ["Geelong"],
        "aussierules_afl",
    ),
    (
        "Kentucky Wildcats",
        "Bethune-Cookman Wildcats",
        ["Wildcats"],
        "Kentucky Wildcats",
        ["Wildcats"],
        "basketball_ncaab",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket", "futures"])
@pytest.mark.parametrize("name,target,aliases,other,other_aliases,sport", BAD_LINKS)
async def test_wrong_club_writes_nothing(
    source, name, target, aliases, other, other_aliases, sport
):
    session = Session(team(1, target, aliases), [team(2, other, other_aliases)])
    admitted = await TeamIdentityService().register_team_identity(
        session,
        1,
        source,
        sport,
        source_name=name,
    )
    assert admitted is False
    assert not session.writes
    assert len(session.reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,target,aliases",
    [
        ("Bears", "Chicago Bears", ["Bears"]),
        ("Hawks", "Seattle Seahawks", ["Seahawks"]),
        ("Inter Milan", "Internazionale", ["Inter Milan"]),
        ("Army Black Knights", "Army Knights", []),
        ("Los Angeles C", "Los Angeles Chargers", ["Chargers"]),
        ("St.Louis Blues", "St. Louis Blues", ["Blues"]),
        ("Montréal Canadiens", "Montreal Canadiens", ["Canadiens"]),
    ],
)
async def test_legitimate_name_needs_no_witness_pool(name, target, aliases):
    session = Session(team(1, target, aliases))
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "kalshi",
            "test_league",
            source_name=name,
        )
        is True
    )
    assert len(session.writes) == 1
    assert not session.reads


@pytest.mark.asyncio
async def test_unrecognized_alias_without_a_witness_is_not_evidence_of_a_different_club():
    session = Session(team(1, "Internazionale"))
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "polymarket",
            "soccer_italy_serie_a",
            source_name="Inter Milan",
        )
        is True
    )
    assert len(session.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_id", [True, False])
async def test_an_alias_on_a_duplicate_of_this_club_is_not_a_foreign_witness(shared_id):
    target = team(1, "Internazionale", espn_id="110")
    other = team(
        2,
        "Inter Milan",
        [] if shared_id else ["Internazionale"],
        "110" if shared_id else None,
    )
    session = Session(target, [other])
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "kalshi",
            "soccer_italy_serie_a",
            source_name="Inter Milan",
        )
        is True
    )
    assert len(session.writes) == 1


@pytest.mark.asyncio
async def test_multiple_foreign_witnesses_refuse_without_picking_a_destination():
    session = Session(
        team(1, "Chicago Bears"),
        [
            team(2, "Detroit Lions", ["Lions"]),
            team(3, "British and Irish Lions", ["Lions"]),
        ],
    )
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "kalshi",
            "test_league",
            source_name="Lions",
        )
        is False
    )
    assert not session.writes
    assert session.gets == [1]


@pytest.mark.asyncio
async def test_uninspected_pool_tail_refuses_and_names_the_limit(caplog):
    session = Session(
        team(1, "Stade Brest"),
        [team(i + 2, "Unrelated") for i in range(_NAME_WITNESS_LIMIT + 1)],
    )
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "kalshi",
            "soccer_france_ligue_one",
            source_name="PSG",
        )
        is False
    )
    assert not session.writes
    assert "witness limit exceeded" in caplog.text
    params = session.reads[0].compile().params
    assert set(params.values()) == {"soccer_france_ligue_one", _NAME_WITNESS_LIMIT + 1}


@pytest.mark.asyncio
async def test_read_failure_cannot_become_an_admission():
    session = Session(team(1, "Stade Brest"))
    session.execute = AsyncMock(side_effect=RuntimeError("witness read failed"))
    with pytest.raises(RuntimeError, match="witness read failed"):
        await TeamIdentityService().register_team_identity(
            session,
            1,
            "kalshi",
            "soccer_france_ligue_one",
            source_name="PSG",
        )
    assert not session.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,source_id,source_name,sport",
    [
        ("kalshi", "id-only", None, "soccer_france_ligue_one"),
        ("kalshi", None, "PSG", ""),
        ("odds_api", None, "PSG", "soccer_france_ligue_one"),
        ("statpal", None, "PSG", "soccer_france_ligue_one"),
    ],
)
async def test_other_registration_contracts_are_preserved(
    source, source_id, source_name, sport
):
    session = Session(team(1, "Stade Brest"))
    assert (
        await TeamIdentityService().register_team_identity(
            session,
            1,
            source,
            sport,
            source_id=source_id,
            source_name=source_name,
        )
        is True
    )
    assert not session.gets and not session.reads
    assert len(session.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("step", [3, 4])
@pytest.mark.parametrize("source", ["kalshi", "espn"])
async def test_the_fuzzy_resolver_preserves_a_real_registration_refusal(step, source):
    service = TeamIdentityService()
    target = team(1, "Manchester City", espn_id="382")
    session = Session(target, [team(2, "Coventry City", espn_id="388")])
    service._lookup_by_source_id = AsyncMock(return_value=None)
    service._lookup_by_source_name = AsyncMock(return_value=None)
    service._fuzzy_match_mappings = AsyncMock(
        return_value=target if step == 3 else None
    )
    service._fuzzy_match_teams = AsyncMock(return_value=target)
    result = await service.resolve_team(
        session,
        source,
        "soccer_epl",
        source_name="Coventry City",
        source_id="388",
    )
    assert result is None
    assert not session.writes
    if step == 3:
        service._fuzzy_match_teams.assert_not_called()


@pytest.mark.asyncio
async def test_abbreviation_only_resolution_is_admitted_without_a_write():
    service = TeamIdentityService()
    target = team(1, "Chicago Bears")
    session = Session(target)
    service._fuzzy_match_mappings = AsyncMock(return_value=target)
    assert (
        await service.resolve_team(
            session,
            "kalshi",
            "americanfootball_nfl",
            source_abbreviation="Bears",
        )
        is target
    )
    assert not session.writes and not session.reads


@pytest.mark.asyncio
async def test_direct_futures_fallback_cannot_return_a_refused_team(monkeypatch):
    from app.services.team_identity import team_identity_service
    from app.tasks.team_linking import link_outcome_to_team
    from app.utils import team_linking

    monkeypatch.setattr(
        team_identity_service, "resolve_team", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(team_linking, "match_outcome_to_team", lambda *_: 1)
    session = Session(team(1, "Stade Brest"), [team(2, "Paris Saint-Germain", ["PSG"])])
    assert (
        await link_outcome_to_team(
            session,
            "PSG",
            "soccer",
            "French league winner",
            [{"id": 1, "sport_key": "soccer_france_ligue_one"}],
            use_llm=False,
        )
        is None
    )
    assert not session.writes


@pytest.mark.asyncio
async def test_espn_registration_cache_does_not_claim_a_refused_identity():
    from app.utils.espn_helpers import register_espn_team_identities

    target = team(1, "Manchester City", espn_id="382")
    session = Session(target)
    event = SimpleNamespace(
        home_team=SimpleNamespace(
            espn_id="388",
            display_name="Coventry City",
            name="Coventry City",
        ),
        away_team=None,
    )
    cache = set()
    await register_espn_team_identities(
        session, target, None, event, "soccer_epl", cache
    )
    assert not cache and not session.writes
