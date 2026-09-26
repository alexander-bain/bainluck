"""Guards for #8740 — a Nations League card wears its nation's flag.

## What a reader saw

`/events/15195323` Türkiye 0-1 France (final), 390px, 2026-09-25: Türkiye's
flag beside a grey "FRA" letter tile. `/events/15196508` Italy 0-2 Belgium: two
tiles. Replayed over production's 1,683 enriched team rows on 2026-09-26,
**28 of 56 Nations League sides this week** served `team_data: null` —
England, France, Spain, Germany, Portugal, the Netherlands among them.

## Why

France has four enriched rows. Three (rugby, World Cup, cricket) carry
flagcdn's `fr.png`; the Nations League row carries ESPN's `countries/500/fra.png`.
The per-league map (#7262) serves a row only when another row under the name
carries the SAME crest — compared as a URL. France's three flagcdn rows vouched
for each other and nobody vouched for the ESPN one, so the one row the Nations
League card needed was refused. Two CDNs, one flag.

## The fix, and the rail it keeps

`_crest_for_corroboration` compares a national flag as the NATION it depicts
(`nation_flags.flag_nation`). A different nation's flag is still a different
crest: a "France" row wearing Germany's flag is corroborated by nobody, exactly
as before. A club crest never becomes a flag, and an ESPN code the curated
table does not know stays a plain URL.

Every specimen runs through all arrival orders (#4978/#7132 convention) and
both directions are asserted (gotcha #43).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import permutations

from app.models.models import Event, Sport
from app.routes.events import (
    _crest_for_corroboration,
    _dedupe_team_name_lookup,
    _format_event,
    _team_for_event,
)
from app.utils.nation_flags import (
    _ESPN_FLAG_CODE_TO_ISO,
    _NATION_TO_ISO,
    flag_nation,
)

UNL = "soccer_uefa_nations_league"
WORLD_CUP = "soccer_fifa_world_cup"
RUGBY = "rugbyunion_six_nations"
CRICKET = "cricket_international_t20"
BASEBALL_NCAA = "baseball_ncaa"

ESPN_FRA = "https://a.espncdn.com/i/teamlogos/countries/500/fra.png"
ESPN_GER = "https://a.espncdn.com/i/teamlogos/countries/500/ger.png"
ESPN_GEO = "https://a.espncdn.com/i/teamlogos/countries/500/geo.png"
FLAGCDN_FR = "https://flagcdn.com/w80/fr.png"


@dataclass
class _Row:
    """A `TeamSnapshot`-shaped row: attribute surface only, no ORM."""

    id: int
    name: str
    sport_id: int
    sport_key: str | None = None
    alternate_names: list = field(default_factory=list)
    logo_url_small: str | None = None
    logo_url_large: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    abbreviation: str | None = None
    current_record: str | None = None
    slug: str | None = None
    standings_data: dict | None = None
    standings_updated_at: object | None = None
    season_stats: dict | None = None
    espn_id: str | None = None


_SPORT_IDS = {UNL: 101, WORLD_CUP: 102, RUGBY: 103, CRICKET: 104, BASEBALL_NCAA: 105}


def _row(row_id, name, sport_key, crest, *, abbr=None, color=None, record=None, espn_id=None):
    return _Row(
        row_id,
        name,
        sport_id=_SPORT_IDS[sport_key],
        sport_key=sport_key,
        logo_url_small=crest,
        abbreviation=abbr,
        primary_color=color,
        current_record=record,
        espn_id=espn_id,
    )


def _every_order(rows):
    return [_dedupe_team_name_lookup(list(order)) for order in permutations(rows)]


#: France as production held it on 2026-09-26 (db-query, read-only).
FRANCE_ROWS = [
    _row(1642, "France", RUGBY, FLAGCDN_FR),
    _row(1897, "France", WORLD_CUP, FLAGCDN_FR),
    _row(12967, "France", CRICKET, FLAGCDN_FR),
    _row(17804, "France", UNL, ESPN_FRA, abbr="FRA", color="#000080", record="1-0-0",
         espn_id="478"),
]


# ── 1. The ship: the Nations League card gets France's own row ───────────────


def test_the_nations_league_card_is_served_its_own_row_with_the_flag():
    for lookup in _every_order(FRANCE_ROWS):
        team = _team_for_event(lookup, "France", UNL)
        assert team is not None, "this null is the grey 'FRA' tile on /events/15195323"
        assert team.id == 17804
        assert team.logo_url_small == ESPN_FRA
        assert team.current_record == "1-0-0"


def test_the_world_cup_card_keeps_its_own_row():
    """Both directions: the other leagues under the key still answer their own row."""
    for lookup in _every_order(FRANCE_ROWS):
        assert _team_for_event(lookup, "France", WORLD_CUP).id == 1897


def test_the_payload_the_event_page_reads_carries_both_flags():
    """Drive `_format_event` — the formatter behind `/api/events/{id}` — not the helper."""
    turkey = [
        _row(1936, "Turkey", "soccer_fifa_world_cup", "https://flagcdn.com/w80/tr.png"),
        _row(17805, "Turkey", UNL, "https://a.espncdn.com/i/teamlogos/countries/500/tur.png",
             abbr="TUR", color="#ffffff", record="0-0-1", espn_id="465"),
    ]
    lookup = _dedupe_team_name_lookup(FRANCE_ROWS + turkey)
    event = Event(
        id=15195323,
        sport_id=1,
        sport=Sport(id=1, key=UNL, name="UEFA Nations League"),
        home_team_name="Turkey",
        away_team_name="France",
        commence_time=datetime(2026, 9, 25, 18, 45, tzinfo=timezone.utc),
        status="completed",
        home_score=0,
        away_score=1,
        win_probability_sources={},
    )
    served = _format_event(event, team_lookup=lookup)
    assert served["away_team_data"]["team_id"] == 17804, "France's grey tile"
    assert served["home_team_data"]["team_id"] == 17805


# ── 2. The rail: a flag vouches only for its own nation ──────────────────────


def test_a_row_wearing_ANOTHER_nations_flag_is_refused():
    """837's shape for nations: a 'France' row carrying Germany's flag."""
    rows = FRANCE_ROWS[:3] + [
        _row(17804, "France", UNL, ESPN_GER, abbr="GER", espn_id="481"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "France", UNL) is None


def test_a_club_crest_under_a_nation_name_stays_refused():
    """'Georgia': the nation is not in the curated map and its sibling is a school.

    Georgia State baseball's row answers to "Georgia" and carries a real crest.
    Nothing can say ESPN's `geo.png` is the same thing, so the card keeps its
    tile — no crest is better than a wrong one — and the school's row is never
    served on a Nations League card.
    """
    rows = [
        _row(14637, "Georgia", BASEBALL_NCAA,
             "https://a.espncdn.com/i/teamlogos/ncaa/500/2247.png", abbr="GAST", espn_id="358"),
        _row(18260, "Georgia", UNL, ESPN_GEO, abbr="GEO", espn_id="584"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Georgia", UNL) is None


def test_the_corroboration_key_is_the_nation_for_flags_and_the_url_otherwise():
    assert _crest_for_corroboration(FRANCE_ROWS[0]) == "flag:fr"
    assert _crest_for_corroboration(FRANCE_ROWS[3]) == "flag:fr"
    club = _row(1, "Paris", WORLD_CUP, "https://a.espncdn.com/i/teamlogos/soccer/500/160.png")
    assert _crest_for_corroboration(club) == club.logo_url_small
    blank = _row(2, "X", BASEBALL_NCAA, "https://a.espncdn.com/i/teamlogos/default.png")
    assert _crest_for_corroboration(blank) is None


# ── 3. The table: curated, and only ever maps onto a curated nation ──────────


def test_two_cdns_one_flag():
    assert flag_nation(FLAGCDN_FR) == flag_nation(ESPN_FRA) == "fr"
    assert flag_nation("https://flagcdn.com/w160/fr.png") == "fr"
    assert flag_nation("https://flagcdn.com/w80/gb-nir.png") == "gb-nir"
    assert flag_nation("https://a.espncdn.com/i/teamlogos/countries/500/nir.png") == "gb-nir"


def test_an_unknown_code_or_a_club_crest_is_not_a_flag():
    # Malta is a real ESPN flag no curated nation maps to — it stays a URL.
    assert flag_nation("https://a.espncdn.com/i/teamlogos/countries/500/mlt.png") is None
    assert flag_nation("https://flagcdn.com/w80/zz.png") is None
    assert flag_nation("https://a.espncdn.com/i/teamlogos/soccer/500/160.png") is None
    assert flag_nation("https://a.espncdn.com/i/teamlogos/ncaa/500/478.png") is None
    assert flag_nation(None) is None
    assert flag_nation("") is None


def test_every_espn_code_maps_onto_a_curated_nation():
    known = set(_NATION_TO_ISO.values())
    stray = {code: iso for code, iso in _ESPN_FLAG_CODE_TO_ISO.items() if iso not in known}
    assert not stray, f"an ESPN code that maps outside the curated nations: {stray}"
