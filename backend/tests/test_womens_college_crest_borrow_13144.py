"""Guard tests: women's college basketball crest/colour/short-name borrow (298: A, #13144).

When a `basketball_wncaab` game's own team row has no real crest (or is absent
from the enriched team lookup), it takes the crest, colours and short name from
the same school's `basketball_ncaab` row — and NEVER the men's record or
standings.
"""

from dataclasses import dataclass, field

from app.routes.events import (
    TeamSnapshot,
    _dedupe_team_name_lookup,
    _format_team_data,
    _team_for_event,
)


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
    standings_updated_at: object = None
    primary_color: str | None = None
    secondary_color: str | None = None
    logo_url_small: str | None = None
    logo_url_large: str | None = None
    season_stats: dict | None = None
    espn_id: str | None = None


def test_texas_state_womens_borrows_mens_basketball_crest_colors_and_short_name_never_record():
    """Fable's #13144 specimen: Texas State Bobcats WNCAAB has no enriched row;
    men's basketball row 702 carries TXST, crest, colours, and a 17-11 record."""
    mens_txst = _FakeTeam(
        702,
        "Texas State Bobcats",
        sport_id=20,
        sport_key="basketball_ncaab",
        slug="texas-state-bobcats",
        abbreviation="TXST",
        primary_color="#501214",
        secondary_color="#8d734a",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/326.png",
        logo_url_large="https://a.espncdn.com/i/teamlogos/ncaa/500/326.png",
        current_record="17-11",
        standings_data={"wins": 17, "losses": 11, "div_rank": 3},
        espn_id="326",
    )
    # Cross-league baseball row carrying blank shield (causes cross-league drop without 298: A).
    baseball_blank = _FakeTeam(
        9001,
        "Texas State Bobcats",
        sport_id=30,
        sport_key="baseball_ncaa",
        abbreviation="TXST",
        primary_color="#501214",
        logo_url_small="https://a.espncdn.com/guid/abc/logos/default.png",
    )

    lookup = _dedupe_team_name_lookup([mens_txst, baseball_blank]).subset(
        {"Texas State Bobcats"}
    )
    resolved = _team_for_event(lookup, "Texas State Bobcats", "basketball_wncaab")
    assert resolved is not None
    payload = _format_team_data(resolved)
    assert payload["abbreviation"] == "TXST"
    assert payload["primary_color"] == "#501214"
    assert payload["secondary_color"] == "#8d734a"
    assert payload["logo_small"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/326.png"
    assert payload["record"] is None
    assert "standings" not in payload
    assert payload["team_id"] is None
    assert payload["slug"] is None


def test_grambling_st_vs_state_womens_borrows_from_mens_basketball():
    """Fable's #13144 specimen: event says 'Grambling State Tigers', men's row
    says 'Grambling St Tigers'."""
    mens_gram = _FakeTeam(
        801,
        "Grambling St Tigers",
        sport_id=20,
        sport_key="basketball_ncaab",
        slug="grambling-st-tigers",
        abbreviation="GRAM",
        primary_color="#ee8601",
        secondary_color="#000000",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
        logo_url_large="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
        current_record="15-12",
    )
    lookup = _dedupe_team_name_lookup([mens_gram]).subset({"Grambling State Tigers"})
    resolved = _team_for_event(
        lookup, "Grambling State Tigers", "basketball_wncaab", team_id=3046
    )
    assert resolved is not None
    payload = _format_team_data(resolved)
    assert payload["abbreviation"] == "GRAM"
    assert payload["primary_color"] == "#ee8601"
    assert payload["logo_small"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png"
    assert payload["record"] is None


def test_crestless_womens_row_keeps_its_own_id_and_record_while_borrowing_mens_crest():
    """When the women's row IS in the lookup (has colour) but has NO crest,
    it borrows crest/colours/short name from men's basketball and keeps its own
    team_id, slug, and women's record."""
    womens = TeamSnapshot(
        id=3046,
        sport_id=21,
        sport_key="basketball_wncaab",
        name="Grambling St Tigers",
        slug="grambling-st-tigers-w",
        abbreviation=None,
        primary_color="#cccccc",
        secondary_color=None,
        logo_url_small=None,
        logo_url_large=None,
        current_record="3-1",
        alternate_names=("Grambling State Tigers",),
        standings_data={"wins": 3, "losses": 1},
        standings_updated_at=None,
        season_stats=None,
        espn_id=None,
    )
    mens = TeamSnapshot(
        id=801,
        sport_id=20,
        sport_key="basketball_ncaab",
        name="Grambling St Tigers",
        slug="grambling-st-tigers",
        abbreviation="GRAM",
        primary_color="#ee8601",
        secondary_color="#000000",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
        logo_url_large="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
        current_record="15-12",
        alternate_names=(),
        standings_data={"wins": 15, "losses": 12},
        standings_updated_at=None,
        season_stats=None,
        espn_id="2755",
    )
    lookup = _dedupe_team_name_lookup([womens, mens])
    resolved = _team_for_event(lookup, "Grambling State Tigers", "basketball_wncaab")
    assert resolved is not None
    payload = _format_team_data(resolved)
    assert payload["team_id"] == 3046
    assert payload["slug"] == "grambling-st-tigers-w"
    assert payload["record"] == "3-1"
    assert payload["standings"]["wins"] == 3
    assert payload["abbreviation"] == "GRAM"
    assert payload["primary_color"] == "#ee8601"
    assert payload["logo_small"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png"


def test_womens_row_with_own_crest_is_untouched():
    """A women's row that already has a real crest never borrows from men's."""
    womens = _FakeTeam(
        8556,
        "Jacksonville St Gamecocks",
        sport_id=21,
        sport_key="basketball_wncaab",
        slug="jacksonville-st-gamecocks-w",
        abbreviation="JXST",
        primary_color="#cc0000",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/55.png",
        current_record="4-0",
    )
    mens = _FakeTeam(
        999,
        "Jacksonville St Gamecocks",
        sport_id=20,
        sport_key="basketball_ncaab",
        slug="jacksonville-st-gamecocks",
        abbreviation="JSU",
        primary_color="#111111",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/55.png",
        current_record="1-3",
    )
    lookup = _dedupe_team_name_lookup([womens, mens])
    resolved = _team_for_event(lookup, "Jacksonville St Gamecocks", "basketball_wncaab")
    assert resolved is not None and resolved.id == 8556
    assert resolved.abbreviation == "JXST"
    assert resolved.current_record == "4-0"


def test_womens_prefers_mens_basketball_over_lacrosse_full_word_abbreviation():
    """Game 15347943 shape: lacrosse row 1436 carries 'MASSACHUSETTS', men's
    basketball carries 'UMASS'; WNCAAB borrows from men's basketball."""
    lacrosse = _FakeTeam(
        1436,
        "Massachusetts Minutemen",
        sport_id=40,
        sport_key="lacrosse_ncaa",
        abbreviation="MASSACHUSETTS",
        primary_color="#ac0d1e",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/113.png",
    )
    mens = _FakeTeam(
        500,
        "Massachusetts Minutemen",
        sport_id=20,
        sport_key="basketball_ncaab",
        abbreviation="UMASS",
        primary_color="#881c1c",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/113.png",
        current_record="14-16",
    )
    lookup = _dedupe_team_name_lookup([lacrosse, mens])
    resolved = _team_for_event(lookup, "Massachusetts Minutemen", "basketball_wncaab")
    assert resolved is not None
    payload = _format_team_data(resolved)
    assert payload["abbreviation"] == "UMASS"
    assert payload["record"] is None


def test_ambiguous_mascot_and_non_wncaab_sports_never_borrow():
    """Shared mascots like 'Tigers' drop out of the men's borrow map, and
    non-WNCAAB sports do not trigger 298: A."""
    auburn = _FakeTeam(
        1,
        "Auburn Tigers",
        sport_id=20,
        sport_key="basketball_ncaab",
        abbreviation="AUB",
        alternate_names=["Tigers"],
        primary_color="#0c2340",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2.png",
    )
    lsu = _FakeTeam(
        2,
        "LSU Tigers",
        sport_id=20,
        sport_key="basketball_ncaab",
        abbreviation="LSU",
        alternate_names=["Tigers"],
        primary_color="#461d7c",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/99.png",
    )
    mlb = _FakeTeam(
        3,
        "Detroit Tigers",
        sport_id=50,
        sport_key="baseball_mlb",
        abbreviation="DET",
        alternate_names=["Tigers"],
        primary_color="#0c2340",
        logo_url_small="https://a.espncdn.com/i/teamlogos/mlb/500/det.png",
    )
    lookup = _dedupe_team_name_lookup([auburn, lsu, mlb])
    assert "tigers" not in lookup.mens_college_basketball
    assert _team_for_event(lookup, "Tigers", "basketball_wncaab") is None
    # "LSU Lady Tigers" cleanly resolves to LSU Tigers, never Auburn.
    lady_lsu = _team_for_event(lookup, "LSU Lady Tigers", "basketball_wncaab")
    assert lady_lsu is not None and lady_lsu.abbreviation == "LSU"
    # Non-WNCAAB sport does NOT use the men's borrow fallback.
    assert _team_for_event(lookup, "LSU Lady Tigers", "soccer_usa_mls") is None
