"""A venue name must not turn a wrong-club fuzzy hit into a durable identity."""

from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.models import Team
from app.services.team_identity import TeamIdentityService, _NAME_WITNESS_LIMIT


def team(tid, name, aliases=(), espn_id=None, *, location=None):
    return Team(
        id=tid,
        name=name,
        sport_id=1,
        alternate_names=list(aliases),
        espn_id=espn_id,
        location=location,
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
        keys = [column.key for column in stmt.selected_columns]
        row = namedtuple("Row", keys)
        rows = [row(*(getattr(t, key) for key in keys)) for t in self.witnesses]
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
async def test_womens_lacrosse_name_cannot_reuse_a_mens_mapping(monkeypatch, caplog):
    session = Session(team(1416, "Army Knights"))
    service = TeamIdentityService()
    lookup = AsyncMock(return_value=session.target)
    monkeypatch.setattr(service, "_lookup_by_source_name", lookup)

    resolved = await service.resolve_team(
        session, "polymarket", "lacrosse_ncaa", source_name="Army Black Knights (W)"
    )

    assert resolved is None
    lookup.assert_not_awaited()
    assert "women's team name in a men's league" in caplog.text


@pytest.mark.asyncio
async def test_verified_source_id_still_resolves_before_the_name_check(monkeypatch):
    session = Session(team(1416, "Army Knights"))
    service = TeamIdentityService()
    lookup = AsyncMock(return_value=session.target)
    monkeypatch.setattr(service, "_lookup_by_source_id", lookup)

    resolved = await service.resolve_team(
        session,
        "polymarket",
        "lacrosse_ncaa",
        source_id="verified-team",
        source_name="Army Black Knights (W)",
    )

    assert resolved is session.target
    lookup.assert_awaited_once_with(session, "polymarket", "verified-team", "lacrosse_ncaa")


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket", "futures"])
async def test_womens_lacrosse_name_cannot_be_registered_in_the_mens_league(source):
    session = Session(team(1416, "Army Knights"))

    admitted = await TeamIdentityService().register_team_identity(
        session, 1416, source, "lacrosse_ncaa", source_name="Army Black Knights (W)"
    )

    assert admitted is False
    assert not session.gets
    assert not session.reads
    assert not session.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sport,name,target",
    [
        ("lacrosse_ncaa", "Army Black Knights", "Army Knights"),
        ("basketball_wncaab", "Army Black Knights (W)", "Army Black Knights"),
        ("soccer_other", "Chelsea (W)", "Chelsea"),
    ],
)
async def test_unmarked_names_and_other_leagues_keep_their_existing_admission(
    sport, name, target
):
    session = Session(team(1, target))

    admitted = await TeamIdentityService().register_team_identity(
        session, 1, "polymarket", sport, source_name=name
    )

    assert admitted is True
    assert len(session.writes) == 1


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


async def register_school(session, name, sport="baseball_ncaa", source="kalshi"):
    return await TeamIdentityService().register_team_identity(
        session,
        session.target.id,
        source,
        sport,
        source_name=name,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sport, school, mascot, target_name, espn_id",
    [
        # Saved mislinks. The additional lacrosse row exercises the second league.
        (
            "baseball_ncaa",
            "Middle Tennessee",
            "Blue Raiders",
            "Sam Houston Bearkats",
            "177",
        ),
        (
            "baseball_ncaa",
            "Cal State Bakersfield",
            "Roadrunners",
            "UC Riverside Highlanders",
            "327",
        ),
        ("lacrosse_ncaa", "Rutgers", "Scarlet Knights", "Hofstra Pride", "164"),
        ("baseball_ncaa", "North Dakota State", "Bison", "Sam Houston Bearkats", "310"),
    ],
)
async def test_exact_espn_school_location_refuses_a_foreign_team_binding(
    sport,
    school,
    mascot,
    target_name,
    espn_id,
):
    target = team(1, target_name)
    witness = team(2, f"{school} {mascot}", espn_id=espn_id, location=school)
    session = Session(target, [target, witness])
    assert await register_school(session, f" {school.upper()} ", sport) is False
    assert not session.writes
    assert session.gets == [target.id]
    assert len(session.reads) == 1
    assert set(session.reads[0].compile().params.values()) == {
        sport,
        _NAME_WITNESS_LIMIT + 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location, espn_id, sport, target_in_league",
    [
        pytest.param(None, "177", "baseball_ncaa", True, id="location-missing"),
        pytest.param(
            "Middle Tennessee", "", "baseball_ncaa", True, id="espn-id-missing"
        ),
        pytest.param(
            "Middle Tennessee",
            "177",
            "baseball_ncaa",
            False,
            id="target-in-another-league",
        ),
        pytest.param(
            "Middle Tennessee",
            "177",
            "basketball_ncaab",
            True,
            id="out-of-scope-league",
        ),
    ],
)
async def test_school_location_requires_a_same_league_espn_record(
    location,
    espn_id,
    sport,
    target_in_league,
):
    target = team(1, "Sam Houston Bearkats")
    witness = team(
        2, "Middle Tennessee Blue Raiders", espn_id=espn_id, location=location
    )
    session = Session(target, [target, witness] if target_in_league else [witness])
    assert await register_school(session, "Middle Tennessee", sport) is True
    assert len(session.writes) == len(session.reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, location, mascot",
    [
        ("Cleveland", "Cleveland State", "Vikings"),
        ("North Dakota", "North Dakota State", "Bison"),
        ("Rutgers Scarlet", "Rutgers", "Scarlet Knights"),
        ("Cal State Bakersfield (Women)", "Cal State Bakersfield", "Roadrunners"),
    ],
)
async def test_school_location_does_not_match_prefixes_or_strip_qualifiers(
    name,
    location,
    mascot,
):
    target = team(1, "Sam Houston Bearkats")
    witness = team(2, f"{location} {mascot}", espn_id="2", location=location)
    session = Session(target, [target, witness])
    assert await register_school(session, name) is True
    assert len(session.writes) == len(session.reads) == 1


@pytest.mark.asyncio
async def test_recognized_school_alias_still_needs_no_witness_query():
    target = team(1, "Middle Tennessee Blue Raiders", ["MTSU"], "177")
    witness = team(2, "Sam Houston Bearkats", espn_id="2534", location="MTSU")
    session = Session(target, [target, witness])
    assert await register_school(session, "MTSU", source="futures") is True
    assert session.gets == [target.id]
    assert not session.reads
    assert len(session.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_id, extra_location_claim",
    [
        pytest.param("177", False, id="duplicate"),
        pytest.param("2534", True, id="ambiguous"),
    ],
)
async def test_school_location_abstains_when_duplicate_or_ambiguous(
    target_id,
    extra_location_claim,
):
    target = team(1, "Sam Houston Bearkats", espn_id=target_id)
    witness = team(
        2,
        "Middle Tennessee Blue Raiders",
        espn_id="177",
        location="Middle Tennessee",
    )
    rows = [target, witness]
    if extra_location_claim:
        rows.append(
            team(3, "Other University", espn_id="3", location="Middle Tennessee")
        )
    session = Session(target, rows)
    assert (
        await register_school(session, "Middle Tennessee", source="polymarket") is True
    )
    assert len(session.writes) == len(session.reads) == 1
