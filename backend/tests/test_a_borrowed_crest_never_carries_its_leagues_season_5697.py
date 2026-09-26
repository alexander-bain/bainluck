"""Guards for #5697's crest half — a school's football card never prints its lacrosse record.

## What a reader saw

`/api/events/15317759` Harvard @ Brown (FCS, completed 14-10), production
2026-09-26 18:15Z: `away_team_data` served slug `harvard-crimson-ncaa`, record
**9-5**. That is team 1429, the `lacrosse_ncaa` row. The event's own
`away_team_id` is 19284, the `americanfootball_ncaaf_fcs` Harvard row, which
carries no crest, record or slug, so it is not in the enriched lookup at all.

## Why

`_team_for_event` found no FCS row under "Harvard Crimson", so it fell back to
`.get(name)` — the lacrosse row — and `_refuse_other_sport_row` KEPT it, because
another Harvard row carries the same crest (#7262: one school, one badge). That
is right for the crest and wrong for everything that describes one league's
season: the record, the standings board, the season stats, the team page.

## The fix

A row borrowed from another LEAGUE lends only its crest, colours and
abbreviation. `_crest_only` clears the league-bound fields on a fresh snapshot
(the cached row is shared and frozen). Compared by league identity, not sport:
an FBS row's record on an FCS card is another league's season too.

Every specimen runs through all arrival orders (#4978/#7132 convention), both
directions are asserted (gotcha #43), and each of the three consumers is driven
through its own formatter, not the helper alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import permutations

import pytest

from app.models.models import Event, Sport
from app.routes.events import (
    TeamSnapshot,
    _dedupe_team_name_lookup,
    _format_event,
    _team_for_event,
)

FCS = "americanfootball_ncaaf_fcs"
FBS = "americanfootball_ncaaf"
LACROSSE = "lacrosse_ncaa"
NCAAB = "basketball_ncaab"

HARVARD_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/108.png"
BROWN_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/225.png"

_SPORT_IDS = {FCS: 401, FBS: 402, LACROSSE: 303, NCAAB: 104}


@dataclass
class _Row:
    id: int
    name: str
    sport_id: int
    sport_key: str
    logo_url_small: str | None = None
    logo_url_large: str | None = None
    primary_color: str | None = "#a51c30"
    secondary_color: str | None = None
    abbreviation: str | None = "HARV"
    current_record: str | None = None
    slug: str | None = None
    alternate_names: list = field(default_factory=list)
    standings_data: dict | None = None
    standings_updated_at: object | None = None
    season_stats: dict | None = None
    espn_id: str | None = None


def _row(row_id, name, sport_key, crest, **kw):
    return _Row(row_id, name, _SPORT_IDS[sport_key], sport_key, logo_url_small=crest, **kw)


def _every_order(rows):
    return [_dedupe_team_name_lookup(list(order)) for order in permutations(rows)]


#: Harvard as the lookup held it: the lacrosse row (production, 2026-09-26)
#: plus a second sport carrying the same crest — the corroboration that made
#: the lacrosse row servable at all.
HARVARD_LACROSSE = _row(
    1429, "Harvard Crimson", LACROSSE, HARVARD_CREST,
    current_record="9-5", slug="harvard-crimson-ncaa", espn_id="108",
    standings_data={"wins": 9, "losses": 5}, season_stats={"goals": 140},
)
HARVARD_HOOPS = _row(
    1030, "Harvard Crimson", NCAAB, HARVARD_CREST,
    current_record="15-13", slug="harvard-crimson-ncaab", espn_id="108",
)
HARVARD_ROWS = [HARVARD_LACROSSE, HARVARD_HOOPS]

#: The league-bound fields. None of these may cross from another league's row.
_LEAGUE_BOUND = ("id", "slug", "current_record", "standings_data", "season_stats", "espn_id")


# ── 1. The ship: the FCS card borrows the crest, not the season ─────────────


def test_the_specimen_would_have_leaked_the_lacrosse_record():
    """Strawman: the row the lookup falls back to really carries a non-football season.

    Without this, every assertion below could pass on a fixture whose default
    row had no record to leak.
    """
    for lookup in _every_order(HARVARD_ROWS):
        default = lookup.get("Harvard Crimson")
        assert default is not None
        assert default.sport_key != FCS
        assert default.current_record in {"9-5", "15-13"}
        assert default.slug is not None


def test_an_fcs_card_gets_harvards_crest_and_no_other_leagues_season():
    for lookup in _every_order(HARVARD_ROWS):
        team = _team_for_event(lookup, "Harvard Crimson", FCS)
        assert team is not None, "the crest is the school's and stays"
        assert team.logo_url_small == HARVARD_CREST
        assert team.primary_color == "#a51c30"
        assert team.abbreviation == "HARV"
        for name in _LEAGUE_BOUND:
            assert getattr(team, name) is None, f"{name} crossed from another league"


def test_the_borrow_never_edits_the_cached_row():
    """The lookup is a process-global cache (#2107): the borrow is a new object."""
    for lookup in _every_order(HARVARD_ROWS):
        _team_for_event(lookup, "Harvard Crimson", FCS)
        assert lookup.get("Harvard Crimson").current_record in {"9-5", "15-13"}
    assert HARVARD_LACROSSE.current_record == "9-5"
    assert HARVARD_LACROSSE.slug == "harvard-crimson-ncaa"


def test_the_crest_only_view_is_a_snapshot_even_from_a_live_row():
    team = _team_for_event(_dedupe_team_name_lookup(HARVARD_ROWS), "Harvard Crimson", FCS)
    assert isinstance(team, TeamSnapshot)


# ── 2. Both directions: a same-league row keeps everything ──────────────────


def test_the_lacrosse_card_keeps_the_lacrosse_record():
    for lookup in _every_order(HARVARD_ROWS):
        team = _team_for_event(lookup, "Harvard Crimson", LACROSSE)
        assert team is HARVARD_LACROSSE
        assert team.current_record == "9-5"
        assert team.slug == "harvard-crimson-ncaa"


def test_an_fcs_row_once_enriched_is_served_whole():
    football = _row(
        19284, "Harvard Crimson", FCS, HARVARD_CREST,
        current_record="2-1", slug="harvard-crimson-ncaaf_fcs", espn_id="108",
    )
    for lookup in _every_order(HARVARD_ROWS + [football]):
        team = _team_for_event(lookup, "Harvard Crimson", FCS)
        assert team is football
        assert team.current_record == "2-1"
        assert team.id == 19284


def test_a_sole_same_league_row_answered_by_name_keeps_its_record():
    """The fallback path, same league: not a borrow, so nothing is cleared."""
    only = _row(19284, "Harvard Crimson", FCS, HARVARD_CREST, current_record="2-1")
    for lookup in _every_order([only]):
        assert _team_for_event(lookup, "Harvard Crimson", FCS) is only


def test_an_fbs_row_on_an_fcs_card_is_another_leagues_season():
    """League, not sport: same sport family, different league, record withheld."""
    fbs = _row(17075, "Harvard Crimson", FBS, HARVARD_CREST, current_record="1-2")
    for lookup in _every_order([fbs, HARVARD_HOOPS]):
        team = _team_for_event(lookup, "Harvard Crimson", FCS)
        assert team is not None and team.logo_url_small == HARVARD_CREST
        assert team.current_record is None


def test_an_event_with_no_sport_key_keeps_todays_answer():
    """Nothing to compare against, so `.get` stands — untouched by this fix."""
    for lookup in _every_order(HARVARD_ROWS):
        assert _team_for_event(lookup, "Harvard Crimson", None) is lookup.get("Harvard Crimson")


# ── 3. Does it reach the reader? All three consumers, through their formatters ─


def _harvard_at_brown_lookup():
    brown_lax = _row(
        1428, "Brown Bears", LACROSSE, BROWN_CREST, abbreviation="BRWN",
        current_record="7-8", slug="brown-bears-ncaa",
    )
    brown_hoops = _row(1031, "Brown Bears", NCAAB, BROWN_CREST, abbreviation="BRWN")
    return _dedupe_team_name_lookup(HARVARD_ROWS + [brown_lax, brown_hoops])


def _assert_crest_without_season(team_data: dict):
    assert team_data["logo_small"] == HARVARD_CREST
    assert team_data["abbreviation"] == "HARV"
    assert team_data["record"] is None, "the lacrosse 9-5 on a football card"
    assert team_data["slug"] is None
    assert team_data["team_id"] is None
    assert "standings" not in team_data
    assert "season_stats" not in team_data


def test_the_event_page_payload_carries_the_crest_without_the_lacrosse_record():
    """`_format_event`, the formatter behind `/api/events/{id}` — the specimen's route."""
    event = Event(
        id=15317759,
        sport_id=_SPORT_IDS[FCS],
        sport=Sport(id=_SPORT_IDS[FCS], key=FCS, name="NCAAF FCS"),
        home_team_name="Brown Bears",
        away_team_name="Harvard Crimson",
        commence_time=datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc),
        status="completed",
        home_score=10,
        away_score=14,
        win_probability_sources={},
    )
    served = _format_event(event, team_lookup=_harvard_at_brown_lookup())
    _assert_crest_without_season(served["away_team_data"])
    assert served["home_team_data"]["record"] is None
    assert served["home_team_data"]["logo_small"] == BROWN_CREST


@pytest.mark.asyncio
async def test_the_feed_card_carries_the_crest_without_the_lacrosse_record(monkeypatch):
    from app.routes import feed

    lookup = _harvard_at_brown_lookup()

    async def _lookup(db, names):
        return lookup

    monkeypatch.setattr(feed, "_build_team_lookup", _lookup)
    items = [{
        "type": "event",
        "data": {"home_team": "Brown Bears", "away_team": "Harvard Crimson", "sport": FCS},
    }]
    await feed.enrich_event_team_data(None, items)
    _assert_crest_without_season(items[0]["data"]["away_team_data"])


def test_the_league_rail_carries_the_crest_without_the_lacrosse_record():
    from app.routes.league_futures import _format_game_brief

    class _RailEvent:
        id = 15317759
        external_id = "espn-401867806"
        home_team_name = "Brown Bears"
        away_team_name = "Harvard Crimson"
        commence_time = datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc)
        completed_at = None
        status = "scheduled"
        home_score = None
        away_score = None
        win_probability_sources = {}
        opening_home_probability = None
        opening_away_probability = None
        period = None
        game_clock = None
        broadcast_info = None
        espn_id = "401867806"
        venue = None

    brief = _format_game_brief(
        _RailEvent(), sport_key=FCS, team_lookup=_harvard_at_brown_lookup()
    )
    _assert_crest_without_season(brief["away_team_data"])
