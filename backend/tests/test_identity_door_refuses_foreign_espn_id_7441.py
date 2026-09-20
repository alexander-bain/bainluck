"""#7441 — the identity door refuses to file one club's ESPN id under another club's row.

`team_identity_mapping` is read FIRST by every source's team lookup, and
`resolve_team` auto-registers its fuzzy hits into it, so a wrong bind that
reaches this door becomes a permanent EXACT hit. The witness that it is wrong is
already in the row being pointed at: two clubs cannot share an ESPN id.

The refusal takes TWO witnesses — the ids disagree AND the names name a
different club. Each alone is a shape that must still be admitted, and there is
a test below for each:

* ids disagree, names AGREE  -> #7419's row (the team's stored id is the wrong
  one, and the mapping is the thing that becomes correct when it is fixed);
* names disagree, ids AGREE  -> an ordinary spelling the matcher misses.
"""

import pytest

from app.models.models import Team
from app.services.team_identity import TeamIdentityService
from app.utils.name_normalization import names_a_different_club


class _RecordingSession:
    """A session that answers `get` with one team and records every execute.

    Deliberately NOT an `AsyncMock`: a mock answers `get` with a mock whose
    `.name` and `.espn_id` are also mocks, so the guard would be exercised
    against values no production row can hold and a pass would mean nothing.
    """

    def __init__(self, team):
        self._team = team
        self.executed = []

    async def get(self, model, pk):
        assert model is Team
        return self._team if self._team is not None and self._team.id == pk else None

    async def execute(self, statement):
        self.executed.append(statement)
        return None


def _team(team_id, name, espn_id):
    team = Team(name=name, sport_id=1, espn_id=espn_id)
    team.id = team_id
    return team


async def _register(team, *, source="espn", source_id=None, source_name=None):
    session = _RecordingSession(team)
    result = await TeamIdentityService().register_team_identity(
        session,
        team.id if team is not None else 1,
        source,
        "soccer_epl",
        source_id=source_id,
        source_name=source_name,
    )
    return session, result


# =============================================================================
# The refusal
# =============================================================================


class TestTheDoorRefusesAForeignEspnId:
    @pytest.mark.asyncio
    async def test_coventry_city_does_not_become_manchester_city(self):
        """The production row that started this: espn 388 filed under club 382."""
        session, result = await _register(
            _team(188, "Manchester City", "382"),
            source_id="388",
            source_name="Coventry City",
        )
        assert session.executed == [], (
            "a mapping claiming ESPN id 388 IS Manchester City (382) was written"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_a_pair_sharing_no_token_is_refused_too(self):
        """`shared_token_rivals` declines to judge these; the matcher catches them.

        This is the arm a rivals-only guard would miss, and it is the worst row
        in the measured population: NHL, `Toronto Maple Leafs` -> Montreal
        Canadiens.
        """
        session, _ = await _register(
            _team(568, "Montreal Canadiens", "10"),
            source_id="21",
            source_name="Toronto Maple Leafs",
        )
        assert session.executed == []

    @pytest.mark.asyncio
    async def test_a_shared_mascot_is_refused(self):
        """`BYU Cougars` -> Houston Cougars: `names_match` reads True here."""
        session, _ = await _register(
            _team(14126, "Houston Cougars", "248"),
            source_id="252",
            source_name="BYU Cougars",
        )
        assert session.executed == []


# =============================================================================
# What it must still admit — one test per witness, plus the scope bounds
# =============================================================================


class TestTheDoorStillAdmits:
    @pytest.mark.asyncio
    async def test_the_7419_shape_where_the_stored_id_is_the_wrong_one(self):
        """Ids disagree, names AGREE. The mapping is right; the row's id is not.

        Team 837 really is Ohio State and really does hold Texas State's id
        (#7419). Refusing this mapping would refuse the row that becomes correct
        the moment `upsert_team`'s correction lands.
        """
        session, _ = await _register(
            _team(837, "Ohio State Buckeyes", "326"),
            source_id="194",
            source_name="Ohio State Buckeyes",
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_an_alias_spelling_is_not_another_club(self):
        """`Army Black Knights` / `Army Knights` — one club, two spellings."""
        session, _ = await _register(
            _team(2396, "Army Knights", "161"),
            source_id="349",
            source_name="Army Black Knights",
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_agreeing_ids_are_never_name_tested(self):
        """Names disagree, ids AGREE. The id is the authority and it says yes.

        Without this the guard would be a name matcher wearing an id's clothes,
        and every legitimate alias the matcher misses would be refused.

        THE PAIR HAS TO BE ONE THE PREDICATE ACTUALLY CALLS DIFFERENT, or the
        control is vacuous and a guard that dropped the id comparison entirely
        would still pass it. `LA Clippers`/`Los Angeles Clippers` was the first
        draft and was exactly that — the matcher accepts it, so no arm fires.
        `Inter Milan`/`Internazionale` is the pair `shared_token_rivals`'s own
        docstring names as the legitimate alias `names_match` refuses.
        """
        assert names_a_different_club("Inter Milan", "Internazionale") is True

        session, _ = await _register(
            _team(110, "Internazionale", "110"),
            source_id="110",
            source_name="Inter Milan",
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_a_row_with_no_stored_id_has_nothing_to_contradict(self):
        session, _ = await _register(
            _team(1813, "Coventry City", None),
            source_id="388",
            source_name="Coventry City",
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_a_registration_with_no_source_name_is_admitted(self):
        """Absence of a name is not evidence of difference — fail OPEN here.

        `not names_match(None, "Manchester City")` is True, so a guard that let
        the empty case fall through its predicates would refuse every id-only
        registration in the table.
        """
        session, _ = await _register(
            _team(188, "Manchester City", "382"),
            source_id="388",
            source_name=None,
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_a_non_espn_source_is_out_of_scope(self):
        """Kalshi's `source_id` is not an ESPN id, so it cannot contradict one."""
        session, _ = await _register(
            _team(188, "Manchester City", "382"),
            source="kalshi",
            source_id="388",
            source_name="Coventry City",
        )
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_a_registration_with_neither_id_nor_name_is_still_a_noop(self):
        session, _ = await _register(_team(188, "Manchester City", "382"))
        assert session.executed == []


# =============================================================================
# The measured population — the claim in the commit body, pinned
# =============================================================================

#: Every ESPN mapping in production on 2026-09-20 whose `source_id` contradicts
#: the `espn_id` of the team row it points at: 45 rows, as
#: ``(source_name, team_name, refuses)``. The split is 38/7 and the seven
#: admitted are each a real alias or #7419's own shape — the whole reason the
#: guard reads the names rather than the ids alone.
_PRODUCTION_CONTRADICTIONS = [
    ("Arizona Wildcats", "Bethune-Cookman Wildcats", True),
    ("BYU Cougars", "Houston Cougars", True),
    ("Delaware State Hornets", "Sacramento State Hornets", True),
    ("Eastern Washington Eagles", "Eastern Michigan Eagles", True),
    ("East Texas A&M Lions", "Texas A&M Aggies", True),
    ("Georgia Southern Eagles", "Southern Mississippi Golden Eagles", True),
    ("Grambling Tigers", "Tennessee State Tigers", True),
    ("Kentucky Wildcats", "Bethune-Cookman Wildcats", True),
    ("Lamar Cardinals", "Louisville Cardinals", True),
    ("Mercer Bears", "Baylor Bears", True),
    ("Montana State Bobcats", "Texas State Bobcats", True),
    ("Morgan State Bears", "Missouri State Bears", True),
    ("Norfolk State Spartans", "San Jose State Spartans", True),
    ("North Dakota Fighting Hawks", "North Dakota State Bison", True),
    ("Northwestern Wildcats", "Bethune-Cookman Wildcats", True),
    ("Ohio State Buckeyes", "Ohio State Buckeyes", False),
    ("Rice Owls", "Temple Owls", True),
    ("San Diego State Aztecs", "San Jose State Spartans", True),
    ("South Dakota State Jackrabbits", "North Dakota State Bison", True),
    ("Southeast Missouri State Redhawks", "Missouri State Bears", True),
    ("Towson Tigers", "Auburn Tigers", True),
    ("UConn Huskies", "Washington Huskies", True),
    ("UNLV Rebels", "Ole Miss Rebels", True),
    ("Utah State Aggies", "New Mexico State Aggies", True),
    ("Villanova Wildcats", "Bethune-Cookman Wildcats", True),
    ("Virginia Cavaliers", "West Virginia Mountaineers", True),
    ("West Virginia Mountaineers", "Virginia Cavaliers", True),
    ("Wisconsin Badgers", "Wisconsin Badgers", False),
    ("Mississippi State Bulldogs", "Mississippi State", False),
    ("St. John's Red Storm", "St. John's", False),
    ("NC State Wolfpack", "Texas Longhorns", True),
    ("Army Black Knights", "Army Knights", False),
    ("Hampton Lady Pirates", "Hampton Pirates", False),
    ("Richmond Spiders", "Richmond Spiders", False),
    ("Toronto Maple Leafs", "Montreal Canadiens", True),
    ("Colgate Raiders", "Loyola (MD) Greyhounds", True),
    ("Lehigh Mountain Hawks", "Army Knights", True),
    ("Mercer Bears", "Jacksonville Dolphins", True),
    ("Saint Joseph's Hawks", "Richmond Spiders", True),
    ("Siena Saints", "Marist Red Foxes", True),
    ("Coventry City", "Manchester City", True),
    ("Hull City", "Manchester City", True),
    ("Manchester United", "Newcastle United", True),
    ("Real Betis", "Real Madrid", True),
    ("Sabah FK", "Qarabağ FK", True),
]


class TestTheMeasuredPopulation:
    @pytest.mark.parametrize("source_name,team_name,refuses", _PRODUCTION_CONTRADICTIONS)
    def test_each_production_pair(self, source_name, team_name, refuses):
        assert names_a_different_club(source_name, team_name) is refuses

    def test_the_split_is_thirty_eight_and_seven(self):
        """The count in the commit body is a fact about this list, not a memory."""
        refused = sum(
            1 for a, b, _ in _PRODUCTION_CONTRADICTIONS if names_a_different_club(a, b)
        )
        assert (refused, len(_PRODUCTION_CONTRADICTIONS) - refused) == (38, 7)
        assert len(_PRODUCTION_CONTRADICTIONS) == 45


# =============================================================================
# The predicate itself
# =============================================================================


class TestNamesADifferentClub:
    def test_rivals_arm(self):
        """`names_match` reads True here — the rivals veto is what refuses it."""
        from app.utils.name_normalization import names_match

        assert names_match("Coventry City", "Manchester City") is True
        assert names_a_different_club("Coventry City", "Manchester City") is True

    def test_no_shared_token_arm(self):
        """`shared_token_rivals` reads False here — the matcher is what refuses."""
        from app.utils.name_normalization import shared_token_rivals

        assert shared_token_rivals("Toronto Maple Leafs", "Montreal Canadiens") is False
        assert names_a_different_club("Toronto Maple Leafs", "Montreal Canadiens") is True

    def test_identical_names_are_one_club(self):
        assert names_a_different_club("Ohio State Buckeyes", "Ohio State Buckeyes") is False

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_a_missing_name_is_not_evidence(self, missing):
        assert names_a_different_club(missing, "Manchester City") is False
        assert names_a_different_club("Manchester City", missing) is False
