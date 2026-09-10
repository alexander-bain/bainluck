"""Guard tests for cross-league team-name logo collisions (Queue #238).

A bare mascot ("Panthers", "Saints") is an alternate name for teams across
multiple leagues. The team-name → logo lookup must NOT resolve such a bare
name to an arbitrary cross-league team (which produced wrong logos — e.g. a
college Panthers logo on an NFL card — in Alex's native Discover screenshot).
"""

from dataclasses import dataclass, field

from app.routes.events import _dedupe_team_name_lookup
from app.utils.sport_keys import league_identity


@dataclass
class _FakeTeam:
    id: int
    name: str
    sport_id: int
    alternate_names: list = field(default_factory=list)
    sport_key: str | None = None


def test_bare_mascot_across_leagues_is_dropped():
    """'Panthers' maps to teams in NFL, NHL and NCAAF → ambiguous → no logo."""
    teams = [
        _FakeTeam(1, "Carolina Panthers", sport_id=1, alternate_names=["Panthers"]),
        _FakeTeam(2, "Florida Panthers", sport_id=4, alternate_names=["Panthers"]),
        _FakeTeam(3, "Pittsburgh Panthers", sport_id=760, alternate_names=["Panthers"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    # Bare mascot must be absent (colored-box fallback, never a wrong logo).
    assert "Panthers" not in lookup
    # Full, unambiguous names still resolve to the correct team.
    assert lookup["Carolina Panthers"].id == 1
    assert lookup["Florida Panthers"].id == 2
    assert lookup["Pittsburgh Panthers"].id == 3


def test_saints_collision_dropped():
    teams = [
        _FakeTeam(10, "New Orleans Saints", sport_id=1, alternate_names=["Saints"]),
        _FakeTeam(11, "Siena Saints", sport_id=3, alternate_names=["Saints"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert "Saints" not in lookup
    assert lookup["New Orleans Saints"].id == 10
    assert lookup["Siena Saints"].id == 11


def test_same_league_duplicate_name_kept():
    """A name shared within ONE league is not ambiguous — first wins, kept."""
    teams = [
        _FakeTeam(20, "Rangers", sport_id=4, alternate_names=[]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert lookup["Rangers"].id == 20


def test_unique_mascot_still_resolves():
    """A mascot unique to one league must still resolve to that team's logo."""
    teams = [
        _FakeTeam(30, "Green Bay Packers", sport_id=1, alternate_names=["Packers"]),
        _FakeTeam(31, "Chicago Bears", sport_id=1, alternate_names=["Bears"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert lookup["Packers"].id == 30
    assert lookup["Bears"].id == 31


# ---------------------------------------------------------------------------
# #4945 — the guard's comparison is a LEAGUE, not a `sport_id`.
#
# Every MLB club has two enriched `teams` rows (#1798): `baseball_mlb` (53232)
# and `baseball_mlb_preseason` (33178). Comparing row ids read one league under
# a season variant as a cross-league collision and dropped all 30 clubs, so
# every MLB card on the site rendered with no crest and no colours.
#
# These tests pin BOTH directions. The season variant must be kept AND the
# Queue #238 collisions above must still be dropped — a fix that only widens
# the guard trades a missing logo for a wrong one.
# ---------------------------------------------------------------------------


def test_mlb_season_variant_is_one_league_and_keeps_its_key():
    """The #4945 case: two rows, two sport_ids, ONE league → crest survives."""
    teams = [
        _FakeTeam(100, "Boston Red Sox", sport_id=53232,
                  sport_key="baseball_mlb", alternate_names=["Red Sox"]),
        _FakeTeam(101, "Boston Red Sox", sport_id=33178,
                  sport_key="baseball_mlb_preseason", alternate_names=["Red Sox"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert "Boston Red Sox" in lookup, (
        "a season variant is not a second league — dropping this key is what "
        "left every MLB card with no crest (#4945)"
    )
    assert "Red Sox" in lookup


def test_the_parent_league_row_wins_not_whichever_loaded_first():
    """`baseball_mlb_preseason` carries a logo but no standings on all 30 clubs.

    Query order is arbitrary, so without an explicit preference the card's
    `standings` would coin-flip per process. Asserted in BOTH input orders —
    with only one order this passes on a first-write-wins implementation.
    """
    parent = _FakeTeam(100, "Boston Red Sox", sport_id=53232,
                       sport_key="baseball_mlb")
    variant = _FakeTeam(101, "Boston Red Sox", sport_id=33178,
                        sport_key="baseball_mlb_preseason")
    assert _dedupe_team_name_lookup([parent, variant])["Boston Red Sox"].id == 100
    assert _dedupe_team_name_lookup([variant, parent])["Boston Red Sox"].id == 100


def test_cross_league_mascot_still_dropped_when_sport_keys_are_present():
    """Queue #238 must not regress once real keys travel with the rows."""
    teams = [
        _FakeTeam(1, "Carolina Panthers", sport_id=1,
                  sport_key="americanfootball_nfl", alternate_names=["Panthers"]),
        _FakeTeam(2, "Florida Panthers", sport_id=4,
                  sport_key="icehockey_nhl", alternate_names=["Panthers"]),
        _FakeTeam(3, "Pittsburgh Panthers", sport_id=760,
                  sport_key="americanfootball_ncaaf", alternate_names=["Panthers"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert "Panthers" not in lookup, "a wrong crest is worse than no crest"
    assert lookup["Carolina Panthers"].id == 1
    assert lookup["Florida Panthers"].id == 2
    assert lookup["Pittsburgh Panthers"].id == 3


def test_two_college_leagues_under_one_sport_are_still_two_leagues():
    """The identity must not collapse a whole SPORT: mens/womens college
    basketball share `basketball_` and are different leagues."""
    teams = [
        _FakeTeam(50, "Tigers", sport_id=3, sport_key="basketball_ncaab"),
        _FakeTeam(51, "Tigers", sport_id=14, sport_key="basketball_wncaab"),
    ]
    assert "Tigers" not in _dedupe_team_name_lookup(teams)


def test_rows_with_no_sport_key_fall_back_to_sport_id():
    """A caller that never set a key keeps the exact pre-#4945 behaviour."""
    teams = [
        _FakeTeam(60, "New Orleans Saints", sport_id=1, alternate_names=["Saints"]),
        _FakeTeam(61, "Siena Saints", sport_id=3, alternate_names=["Saints"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert "Saints" not in lookup
    assert lookup["New Orleans Saints"].id == 60


def test_an_unmapped_key_is_no_less_discriminating_than_a_sport_id():
    """`sports.key` is UNIQUE, so falling back to the key itself can only ever
    MERGE keys the map calls one league — never split, never over-merge."""
    teams = [
        _FakeTeam(70, "Rovers", sport_id=901, sport_key="soccer_madeup_league_a"),
        _FakeTeam(71, "Rovers", sport_id=902, sport_key="soccer_madeup_league_b"),
    ]
    assert "Rovers" not in _dedupe_team_name_lookup(teams)


class TestLeagueIdentity:
    """The collapse rule itself, independent of the lookup that consumes it."""

    def test_season_variants_share_their_parents_identity(self):
        for variant, parent in [
            ("baseball_mlb_preseason", "baseball_mlb"),
            ("americanfootball_nfl_preseason", "americanfootball_nfl"),
            ("basketball_nba_summer_league", "basketball_nba"),
        ]:
            assert league_identity(variant) == league_identity(parent), variant

    def test_different_leagues_keep_different_identities(self):
        keys = [
            "americanfootball_nfl",
            "americanfootball_ncaaf",
            "icehockey_nhl",
            "basketball_nba",
            "basketball_ncaab",
            "basketball_wncaab",
            "baseball_mlb",
            "baseball_ncaa",
        ]
        identities = [league_identity(k) for k in keys]
        assert len(set(identities)) == len(keys), dict(zip(keys, identities))

    def test_a_missing_key_is_none_not_a_shared_identity(self):
        assert league_identity(None) is None
        assert league_identity("") is None

    def test_a_bare_suffix_is_not_stripped_to_nothing(self):
        assert league_identity("_preseason") == "_preseason"
