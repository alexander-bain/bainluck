"""Guard tests: records from an earlier season must never be printed (#13229).

Tottenham (`14545` 10-11-17), Newcastle (`15292` 14-7-17) and Nottingham Forest
(`14533` 11-11-16) showed last season's 38-match record on game pages beside
current-season 10-match records (`IPS 3-2-5`). In leagues without a standings
board, `_standings_vintage` tied and the higher-id duplicate won on the final
id tie-break; and for Nottingham Forest or single-row stragglers (Mainz 7-9-11
in Bundesliga, Paris FC 11-11-12 in Ligue 1) the enriched row had no fresher
twin at all.

The fix works at two layers without writing to production:
1. A league's own median games played establishes a current-season ceiling
   (`league_season_games_ceiling`); any record or standings board above that
   ceiling is refused rather than printed.
2. In `_same_league_row_preference`, a row carrying this season's data beats a
   same-league duplicate whose only record belonged to an earlier season — in
   both arrival orders.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.events import (
    TeamSnapshot,
    _dedupe_team_name_lookup,
    _format_team_data,
    _team_for_event,
)
from app.routes.teams import _format_team
from app.utils.standings_shape import (
    league_season_games_ceiling,
    record_exceeds_season_ceiling,
    record_leads_fresh_board,
    standings_exceeds_season_ceiling,
)

NOW = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
LAST_SEASON_STAMP = NOW - timedelta(days=180)


@dataclass
class _FakeTeam:
    id: int
    name: str
    sport_id: int
    sport_key: str | None = None
    slug: str | None = None
    abbreviation: str | None = None
    alternate_names: list = field(default_factory=list)
    current_record: str | None = None
    standings_data: dict | None = None
    standings_updated_at: datetime | None = None
    primary_color: str | None = "#132257"
    secondary_color: str | None = "#ffffff"
    logo_url_small: str | None = "https://cdn.example/crest.png"
    logo_url_large: str | None = "https://cdn.example/crest-lg.png"
    season_stats: dict | None = None
    espn_id: str | None = None


def _epl_cohort() -> list[_FakeTeam]:
    """Ten-matchday EPL peers establishing the league's current-season cohort."""
    peers = [
        (133, "Arsenal", "ARS", "9-0-1"),
        (134, "Sunderland", "SUN", "2-2-6"),
        (135, "Fulham", "FUL", "2-4-4"),
        (137, "Bournemouth", "BOU", "4-3-3"),
        (138, "Aston Villa", "AVL", "3-4-3"),
        (142, "Chelsea", "CHE", "5-1-4"),
        (188, "Manchester City", "MCI", "7-0-3"),
        (16211, "Ipswich Town", "IPS", "3-2-5"),
    ]
    return [
        _FakeTeam(
            tid,
            name,
            sport_id=10,
            sport_key="soccer_epl",
            slug=name.lower().replace(" ", "-"),
            abbreviation=abbr,
            current_record=rec,
            logo_url_small=f"https://cdn.example/{abbr.lower()}.png",
        )
        for tid, name, abbr, rec in peers
    ]


def _tottenham_pair():
    live = _FakeTeam(
        146,
        "Tottenham Hotspur",
        sport_id=10,
        sport_key="soccer_epl",
        slug="tottenham-hotspur",
        abbreviation="TOT",
        alternate_names=["Tottenham", "Spurs"],
        current_record="3-3-4",
        logo_url_small="https://cdn.example/tot.png",
    )
    stale = _FakeTeam(
        14545,
        "Tottenham",
        sport_id=10,
        sport_key="soccer_epl",
        slug="tottenham-epl",
        abbreviation="TOT",
        alternate_names=["Tottenham Hotspur", "Spurs"],
        current_record="10-11-17",
        logo_url_small="https://cdn.example/tot.png",
    )
    return live, stale


def _newcastle_pair():
    live = _FakeTeam(
        143,
        "Newcastle United",
        sport_id=10,
        sport_key="soccer_epl",
        slug="newcastle-united",
        abbreviation="NEW",
        alternate_names=["Newcastle"],
        current_record="3-3-4",
        logo_url_small="https://cdn.example/new.png",
    )
    stale = _FakeTeam(
        15292,
        "Newcastle",
        sport_id=10,
        sport_key="soccer_epl",
        slug="newcastle-epl",
        abbreviation="NEW",
        alternate_names=["Newcastle United"],
        current_record="14-7-17",
        logo_url_small="https://cdn.example/new.png",
    )
    return live, stale


def test_tottenham_and_newcastle_pick_live_row_in_both_arrival_orders():
    """The #13229 specimen: Tottenham 146 (3-3-4) and Newcastle 143 (3-3-4)
    beat higher-id stale duplicates 14545 (10-11-17) and 15292 (14-7-17)."""
    peers = _epl_cohort()
    tot_live, tot_stale = _tottenham_pair()
    new_live, new_stale = _newcastle_pair()

    for order in (
        peers + [tot_live, tot_stale, new_live, new_stale],
        list(reversed(peers + [tot_live, tot_stale, new_live, new_stale])),
    ):
        lookup = _dedupe_team_name_lookup(order)
        tot = _team_for_event(lookup, "Tottenham Hotspur", "soccer_epl")
        new = _team_for_event(lookup, "Newcastle United", "soccer_epl")
        ips = _team_for_event(lookup, "Ipswich Town", "soccer_epl")

        assert tot is not None and tot.id == 146
        assert _format_team_data(tot)["record"] == "3-3-4"
        assert new is not None and new.id == 143
        assert _format_team_data(new)["record"] == "3-3-4"
        assert ips is not None and _format_team_data(ips)["record"] == "3-2-5"

        # Input rows must never be mutated in place.
        assert tot_stale.current_record == "10-11-17"
        assert new_stale.current_record == "14-7-17"


def test_single_enriched_row_with_prior_season_record_is_withheld_not_dropped():
    """Nottingham Forest (14533, 11-11-16) is the ONLY enriched row for the
    club — its crest and abbreviation stay, its 38-match record is refused."""
    peers = _epl_cohort()
    forest = _FakeTeam(
        14533,
        "Nottingham",
        sport_id=10,
        sport_key="soccer_epl",
        slug="nottingham-epl",
        abbreviation="NFO",
        alternate_names=["Nottingham Forest"],
        current_record="11-11-16",
        logo_url_small="https://cdn.example/nfo.png",
    )

    lookup = _dedupe_team_name_lookup(peers + [forest])
    resolved = _team_for_event(lookup, "Nottingham Forest", "soccer_epl")
    assert resolved is not None
    payload = _format_team_data(resolved)
    assert payload["abbreviation"] == "NFO"
    assert payload["logo_small"] == "https://cdn.example/nfo.png"
    assert payload["record"] is None
    assert forest.current_record == "11-11-16"


def test_bundesliga_mainz_single_row_prior_season_record_is_withheld():
    """Live Bundesliga specimen: 9-matchday league, Mainz 05 carrying 7-9-11 (27)."""
    peers = [
        _FakeTeam(1979 + i, f"Club {i}", sport_id=11, sport_key="soccer_germany_bundesliga", current_record="4-2-3")
        for i in range(8)
    ]
    mainz = _FakeTeam(
        1984,
        "FSV Mainz 05",
        sport_id=11,
        sport_key="soccer_germany_bundesliga",
        abbreviation="M05",
        current_record="7-9-11",
    )
    lookup = _dedupe_team_name_lookup(peers + [mainz])
    assert _format_team_data(lookup["FSV Mainz 05"])["record"] is None
    assert _format_team_data(lookup["Club 0"])["record"] == "4-2-3"


def test_nhl_ottawa_pair_keeps_fresh_board_and_strips_stale_halves():
    """Ottawa 13381 carries a fresh 22-game board + stale 81-game current_record;
    Ottawa 56 carries a stale 71-game board + fresh 23-game current_record."""
    peers = [
        TeamSnapshot(
            id=50 + i,
            sport_id=4,
            sport_key="icehockey_nhl",
            name=f"NHL Team {i}",
            slug=f"nhl-team-{i}",
            abbreviation=f"T{i}",
            primary_color="#111111",
            secondary_color="#ffffff",
            logo_url_small=f"https://cdn.example/nhl-{i}.png",
            logo_url_large=f"https://cdn.example/nhl-{i}-lg.png",
            current_record="12-8-2",
            alternate_names=(),
            standings_data={"wins": 12, "losses": 8, "points": 26},
            standings_updated_at=NOW,
            season_stats=None,
            espn_id=str(i),
        )
        for i in range(8)
    ]
    row_13381 = TeamSnapshot(
        id=13381,
        sport_id=4,
        sport_key="icehockey_nhl",
        name="Ottawa",
        slug="ottawa-nhl",
        abbreviation="OTT",
        primary_color="#c52032",
        secondary_color="#ffffff",
        logo_url_small="https://cdn.example/ott.png",
        logo_url_large="https://cdn.example/ott-lg.png",
        current_record="43-27-11",
        alternate_names=("Ottawa Senators", "Senators"),
        standings_data={
            "wins": 14,
            "losses": 6,
            "points": 30,
            "home_record": "8-3-1",
            "road_record": "6-3-1",
        },
        standings_updated_at=NOW,
        season_stats=None,
        espn_id="14",
    )
    row_56 = TeamSnapshot(
        id=56,
        sport_id=4,
        sport_key="icehockey_nhl",
        name="Ottawa Senators",
        slug="ottawa-senators",
        abbreviation="OTT",
        primary_color="#c52032",
        secondary_color="#ffffff",
        logo_url_small="https://cdn.example/ott.png",
        logo_url_large="https://cdn.example/ott-lg.png",
        current_record="14-6-3",
        alternate_names=("Ottawa", "Senators"),
        standings_data={"wins": 44, "losses": 27, "points": 99},
        standings_updated_at=LAST_SEASON_STAMP,
        season_stats=None,
        espn_id="14",
    )

    for order in (peers + [row_13381, row_56], list(reversed(peers + [row_13381, row_56]))):
        lookup = _dedupe_team_name_lookup(order)
        chosen = _team_for_event(lookup, "Ottawa Senators", "icehockey_nhl")
        assert chosen is not None and chosen.id == 13381
        assert chosen.current_record is None  # stale 43-27-11 stripped
        payload = _format_team_data(chosen)
        assert payload["record"] == "14-6-2"


def test_team_page_refuses_prior_season_record_and_standings():
    """`/api/teams/{id}` withholds prior-season records and boards too."""
    tottenham_orphan = SimpleNamespace(
        id=14545,
        sport_id=10,
        slug="tottenham-epl",
        name="Tottenham",
        abbreviation="TOT",
        location="London",
        primary_color="#132257",
        secondary_color="#ffffff",
        logo_url_small="s.png",
        logo_url_large="l.png",
        current_record="10-11-17",
        standings_data=None,
        standings_updated_at=None,
        season_stats=None,
        roster_players=None,
        sport=SimpleNamespace(key="soccer_epl", name="Premier League"),
    )
    out = _format_team(tottenham_orphan, now=NOW, season_games_ceiling=16)
    assert out["record"] is None

    ottawa_13381 = SimpleNamespace(
        id=13381,
        sport_id=4,
        slug="ottawa-nhl",
        name="Ottawa",
        abbreviation="OTT",
        location="Ottawa",
        primary_color="#c52032",
        secondary_color="#ffffff",
        logo_url_small="s.png",
        logo_url_large="l.png",
        current_record="43-27-11",
        standings_data={
            "wins": 14,
            "losses": 6,
            "points": 30,
            "home_record": "8-3-1",
            "road_record": "6-3-1",
        },
        standings_updated_at=NOW,
        season_stats=None,
        roster_players=None,
        sport=SimpleNamespace(key="icehockey_nhl", name="NHL"),
    )
    # Works even without a warm cache ceiling via `record_leads_fresh_board`.
    out_ott = _format_team(ottawa_13381, now=NOW, season_games_ceiling=None)
    assert out_ott["record"] == "14-6-2"

    ottawa_56 = SimpleNamespace(
        id=56,
        sport_id=4,
        slug="ottawa-senators",
        name="Ottawa Senators",
        abbreviation="OTT",
        location="Ottawa",
        primary_color="#c52032",
        secondary_color="#ffffff",
        logo_url_small="s.png",
        logo_url_large="l.png",
        current_record="14-6-3",
        standings_data={"wins": 44, "losses": 27, "points": 99},
        standings_updated_at=LAST_SEASON_STAMP,
        season_stats=None,
        roster_players=None,
        sport=SimpleNamespace(key="icehockey_nhl", name="NHL"),
    )
    out_56 = _format_team(ottawa_56, now=NOW, season_games_ceiling=29)
    assert out_56["record"] == "14-6-3"
    assert out_56["standings"] is None


def test_nearest_wrong_neighbors_keep_their_records():
    """Schedule variance, promoted sides, March Madness, cups, individual sports,
    and small leagues must never be falsely refused."""
    # La Liga: 1 promoted team at 2 games, 10 teams at 12 games -> median 12, ceiling 18.
    laliga_ceiling = league_season_games_ceiling(
        [2, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12], sport_key="soccer_spain_la_liga"
    )
    assert laliga_ceiling == 18
    assert not record_exceeds_season_ceiling("0-2-0", laliga_ceiling)
    assert not record_exceeds_season_ceiling("11-0-1", laliga_ceiling)
    assert record_exceeds_season_ceiling("20-10-8", laliga_ceiling)

    # March Madness: median 30 regular-season games, finalist at 40 games.
    ncaab_ceiling = league_season_games_ceiling(
        [30] * 10 + [40], sport_key="basketball_ncaab"
    )
    assert ncaab_ceiling == 40
    assert not record_exceeds_season_ceiling("35-5", ncaab_ceiling)

    # Knockout tournaments and individual sports fail open (no ceiling).
    assert league_season_games_ceiling([8] * 10 + [17], sport_key="soccer_uefa_champs_league") is None
    assert league_season_games_ceiling([5] * 10 + [28], sport_key="mma_ufc") is None
    assert league_season_games_ceiling([5] * 10 + [28], sport_key="tennis_atp") is None

    # Sparse league (< 6 recorded rows) fails open.
    assert league_season_games_ceiling([10, 10, 10, 10, 38], sport_key="soccer_epl") is None

    # Rolled-over 0-0 record next to stale 32-36 board is NOT flagged by `record_leads_fresh_board`.
    assert not record_leads_fresh_board("0-0-0", {"wins": 32, "losses": 36}, LAST_SEASON_STAMP, NOW)
    assert not standings_exceeds_season_ceiling({"wins": 5, "losses": 5}, 16)
    assert standings_exceeds_season_ceiling({"wins": 44, "losses": 27}, 29)


def test_subset_preserves_league_ceilings_and_equality_checks_it():
    peers = _epl_cohort()
    full = _dedupe_team_name_lookup(peers)
    assert full.league_ceilings
    sub = full.subset({"Arsenal"})
    assert sub.league_ceilings == full.league_ceilings
    assert sub == full.subset({"Arsenal"})
