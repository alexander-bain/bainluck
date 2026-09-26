"""Guards for #8787 — a card never wears ANOTHER SPORT's team that nothing vouches for.

## What a reader saw

Live Liga MX card, event 15314808, Tijuana v Atlas, production `/api/feed`
2026-09-26 03:22Z and 03:45Z: the Atlas side carried the New York Atlas
(Premier Lacrosse League) crest and the lacrosse record "3-9".

## Mechanism

`teams` held three rows answering to "Atlas": Liga MX 2112 and Leagues Cup
17512, neither enriched, and PLL 3582 "New York Atlas" (enriched, alias
`['Atlas']`). The lookup loads enriched rows only, so the PLL alias was the only
answer, the cross-league guard had nobody to compare it with, and
`_team_for_event` fell back to `.get(name)` although the event's sport key names
a soccer league.

## The rule, and its controls

Refused on SPORT, not league: a Champions League fixture drawing a club's
domestic-league row is the right crest (#4978), and a school's crest carried by
another of its sports' rows is corroborated (#7262) and stays. Both directions
are asserted over every arrival order (gotcha #43).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from app.routes.events import _dedupe_team_name_lookup, _team_for_event

LIGA_MX = "soccer_mexico_ligamx"
LEAGUES_CUP = "soccer_concacaf_leagues_cup"
EPL = "soccer_epl"
UCL = "soccer_uefa_champs_league"
PLL = "lacrosse_pll"
NCAAF = "americanfootball_ncaaf"
NCAAB = "basketball_ncaab"
LACROSSE_NCAA = "lacrosse_ncaa"
BASEBALL_NCAA = "baseball_ncaa"

PLL_ATLAS_CREST = "https://a.espncdn.com/i/teamlogos/pll/500/scoreboard/127632.png"
ATLAS_FC_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/216.png"
ARSENAL_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/359.png"
SYRACUSE_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/183.png"


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
    standings_updated_at: object = None
    season_stats: dict | None = None


_SPORT_IDS = {LIGA_MX: 101, EPL: 102, UCL: 103, PLL: 201, NCAAF: 301,
              NCAAB: 302, LACROSSE_NCAA: 303, BASEBALL_NCAA: 304}


def _row(row_id, name, sport_key, crest, *, record=None, abbr=None, alt=None):
    return _Row(
        row_id,
        name,
        sport_id=_SPORT_IDS.get(sport_key, 999),
        sport_key=sport_key,
        alternate_names=list(alt or []),
        logo_url_small=crest,
        primary_color="#011e41",
        abbreviation=abbr,
        current_record=record,
    )


def _every_order(rows):
    return [_dedupe_team_name_lookup(list(order)) for order in permutations(rows)]


#: Production on 2026-09-26: the only ENRICHED row answering to "Atlas".
NEW_YORK_ATLAS = _row(3582, "New York Atlas", PLL, PLL_ATLAS_CREST,
                      record="3-9", abbr="ATL", alt=["Atlas"])


def test_the_live_liga_mx_card_does_not_wear_the_lacrosse_crest():
    """🔴 The specimen, verbatim: Tijuana v Atlas in Liga MX gets no Atlas row."""
    for lookup in _every_order([NEW_YORK_ATLAS]):
        assert lookup.get("Atlas") is NEW_YORK_ATLAS  # bare `.get` unchanged
        assert _team_for_event(lookup, "Atlas", LIGA_MX) is None
        assert _team_for_event(lookup, "Atlas", LEAGUES_CUP) is None


def test_the_lacrosse_card_keeps_its_own_crest():
    """Control: the same row on its OWN sport's fixture is still served."""
    for lookup in _every_order([NEW_YORK_ATLAS]):
        assert _team_for_event(lookup, "Atlas", PLL) is NEW_YORK_ATLAS
        assert _team_for_event(lookup, "New York Atlas", PLL) is NEW_YORK_ATLAS


def test_an_event_with_no_sport_key_keeps_todays_answer():
    """Control: nothing to compare against, so `.get` stands."""
    for lookup in _every_order([NEW_YORK_ATLAS]):
        assert _team_for_event(lookup, "Atlas", None) is NEW_YORK_ATLAS


def test_an_enriched_liga_mx_row_wins_its_own_fixture():
    """Once Atlas FC is enriched, its crest is the answer on the Liga MX card,
    and the lacrosse card still gets the lacrosse row."""
    atlas_fc = _row(2112, "Atlas", LIGA_MX, ATLAS_FC_CREST, record="2-3-4", abbr="ATL")
    for lookup in _every_order([NEW_YORK_ATLAS, atlas_fc]):
        liga = _team_for_event(lookup, "Atlas", LIGA_MX)
        assert liga is None or liga is atlas_fc  # the cross-league guard may drop the key
        assert _team_for_event(lookup, "Atlas", LIGA_MX) is not NEW_YORK_ATLAS
        assert _team_for_event(lookup, "Atlas", PLL) is not atlas_fc


def test_a_champions_league_fixture_keeps_the_domestic_league_crest():
    """#4978's single-enriched-row clubs render ONLY through this fallback: a
    league-level refusal would have stripped every such UCL crest."""
    arsenal = _row(359, "Arsenal", EPL, ARSENAL_CREST, record="4-1-0", abbr="ARS")
    for lookup in _every_order([arsenal]):
        assert _team_for_event(lookup, "Arsenal", UCL) is arsenal


def test_a_schools_corroborated_crest_from_another_sport_stays():
    """#7262: one school, one crest across its sports. A fixture in a sport with
    no row of its own keeps the corroborated row — the crest is the school's."""
    rows = [
        _row(17075, "Syracuse Orange", NCAAF, SYRACUSE_CREST, record="1-2", abbr="SYR"),
        _row(1432, "Syracuse Orange", LACROSSE_NCAA, SYRACUSE_CREST, record="13-6", abbr="SYR"),
    ]
    for lookup in _every_order(rows):
        default = lookup.get("Syracuse Orange")
        assert default is not None
        assert _team_for_event(lookup, "Syracuse Orange", BASEBALL_NCAA) is default
        assert _team_for_event(lookup, "Syracuse Orange", NCAAF).id == 17075
