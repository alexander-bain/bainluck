"""Guards for #7262 — a school's card is drawn from its OWN sport's row.

## What a reader saw

`GET /api/leagues/americanfootball_ncaaf`, production 2026-09-19:

    Syracuse Orange        team_id=1432  abbr=SYRACUSE  record=13-6   <- lacrosse_ncaa
    North Texas Mean Green team_id=6518  abbr=UNT       record=19-13  <- basketball_wncaab
    Oregon Ducks           team_data=NULL
    Miami Hurricanes       team_data=NULL
    ... 27 of 32 sides NULL

A football team cannot be 13-6 in week 4. Syracuse football is **1-2** and that
row (17075) exists; North Texas football is **1-1** (15314) and that row exists.

## Two mechanisms, one cause: the map can hold only one answer per NAME

`_dedupe_team_name_lookup` is keyed on the name alone, and the event's sport was
never a term. A university has one enriched row per sport, all carrying the
school's single ESPN crest, so:

* **Crests agree** (Syracuse: four rows, all `.../500/183.png`) -> `_crest_is_shared`
  keeps the key and `_crest_row_preference`'s alphabetical tie-break on
  `sport_key` picks the last one: `lacrosse_ncaa` > `basketball_*` >
  `americanfootball_ncaaf`. The reader gets lacrosse's record on a football card.
* **Crests disagree** (Oregon: `ncaaf` and `wncaab` both `.../500/2483.png`, but
  the `baseball_ncaa` row carries the blank shield `.../default.png` and its own
  colour) -> the key is DROPPED and the card falls back to derived initials.
  **431 of production's 1,630 enriched rows carry that placeholder.**

## The fix, and the rail that keeps it honest

`by_league` is a SECOND answer, keyed on the league, so a caller that knows the
event's sport can ask for the row belonging to it. `.get(name)` is untouched —
a caller with no sport in hand cannot be made worse off.

A row is eligible only when another row under the same key carries the SAME
crest. That rail is why this fix cannot serve the wrong-identity rows: the
`americanfootball_ncaaf` row named "Ohio State Buckeyes" (837) carries `TXST`,
Texas State's maroon `#501214` and Texas State's crest, corroborated by nobody.
Serving it on an Ohio State football card would be strictly worse than the null
it replaced, so the key stays dropped. That row is a `teams` defect (#7262's
third arm), not a lookup rule, and no test here papers over it.

## The shape of the guards

Order independence is asserted by running every specimen through **all**
arrival permutations, per the #4978/#7132 convention: an unordered query yields
these rows arbitrarily, and a one-order test proves nothing. Both directions are
asserted throughout (gotcha #43) — the right row is served AND the unsafe row
is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import permutations

import pytest

from app.routes.events import (
    TeamNameLookup,
    _dedupe_team_name_lookup,
    _team_for_event,
)

SYRACUSE_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/183.png"
OREGON_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png"
OHIO_STATE_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/194.png"
TEXAS_STATE_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/326.png"
#: ESPN's blank shield. Not a crest, and it must never vouch for another.
PLACEHOLDER_CREST = "https://a.espncdn.com/i/teamlogos/default.png"

NCAAF = "americanfootball_ncaaf"
NCAAB = "basketball_ncaab"
WNCAAB = "basketball_wncaab"
LACROSSE = "lacrosse_ncaa"
BASEBALL_NCAA = "baseball_ncaa"

#: `sport_id` is a row id and is NEVER the discriminator (#4945) — distinct ids
#: here only so a fixture cannot accidentally pass by sharing one.
_SPORT_IDS = {
    NCAAF: 9001,
    NCAAB: 9002,
    WNCAAB: 9003,
    LACROSSE: 9004,
    BASEBALL_NCAA: 9005,
}


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


def _row(row_id, name, sport_key, crest, *, record=None, abbr=None, color="#000e54", alt=None):
    return _Row(
        row_id,
        name,
        sport_id=_SPORT_IDS.get(sport_key, 9999),
        sport_key=sport_key,
        logo_url_small=crest,
        primary_color=color,
        abbreviation=abbr,
        current_record=record,
        alternate_names=list(alt or []),
    )


def _every_order(rows):
    """One lookup per arrival order. An unordered query yields any of them."""
    return [_dedupe_team_name_lookup(list(order)) for order in permutations(rows)]


# ── The production specimens, verbatim ───────────────────────────────────────


#: Syracuse Orange as production held it on 2026-09-19. One crest, four sports.
SYRACUSE_ROWS = [
    _row(17075, "Syracuse Orange", NCAAF, SYRACUSE_CREST, record="1-2", abbr="SYR"),
    _row(162, "Syracuse Orange", NCAAB, SYRACUSE_CREST, record="15-13", abbr="SYR"),
    _row(195, "Syracuse Orange", WNCAAB, SYRACUSE_CREST, record="24-9", abbr="SYR"),
    _row(
        1432,
        "Syracuse Orange",
        LACROSSE,
        SYRACUSE_CREST,
        record="13-6",
        abbr="SYRACUSE",
        color="#1A3E86",
    ),
]

#: Oregon Ducks: two real crests plus the `baseball_ncaa` blank shield, whose
#: own colour is what makes the key ambiguous today.
OREGON_ROWS = [
    _row(15260, "Oregon Ducks", NCAAF, OREGON_CREST, record="2-1", abbr="ORE", color="#00934b"),
    _row(194, "Oregon Ducks", WNCAAB, OREGON_CREST, record="23-13", abbr="ORE", color="#00934b"),
    _row(
        2542,
        "Oregon Ducks",
        BASEBALL_NCAA,
        PLACEHOLDER_CREST,
        record="43-17",
        abbr="ORE",
        color="#044520",
    ),
]

#: Ohio State Buckeyes. Row 837 is a WRONG-IDENTITY row: Texas State's
#: abbreviation, maroon and crest, stored on an Ohio State name.
OHIO_STATE_ROWS = [
    _row(
        837,
        "Ohio State Buckeyes",
        NCAAF,
        TEXAS_STATE_CREST,
        record="0-0",
        abbr="TXST",
        color="#501214",
    ),
    _row(198, "Ohio State Buckeyes", NCAAB, OHIO_STATE_CREST, record="21-13", abbr="OSU"),
    _row(68, "Ohio State Buckeyes", WNCAAB, OHIO_STATE_CREST, record="27-8", abbr="OSU"),
    _row(
        1424,
        "Ohio State Buckeyes",
        LACROSSE,
        OHIO_STATE_CREST,
        record="10-4",
        abbr="OHIO STATE",
    ),
]


# ── 1. The reported defect: the shared-crest arm ─────────────────────────────


def test_syracuse_on_a_football_card_is_the_football_row():
    """The headline defect, verbatim: 13-6 is lacrosse; football is 1-2."""
    for lookup in _every_order(SYRACUSE_ROWS):
        team = _team_for_event(lookup, "Syracuse Orange", NCAAF)
        assert team is not None
        assert team.id == 17075, "the football row exists and was not chosen"
        assert team.current_record == "1-2"
        assert team.abbreviation == "SYR"


def test_syracuse_on_a_lacrosse_card_is_still_the_lacrosse_row():
    """The other direction — this is a redirect, not a demotion of one sport."""
    for lookup in _every_order(SYRACUSE_ROWS):
        team = _team_for_event(lookup, "Syracuse Orange", LACROSSE)
        assert team is not None and team.id == 1432
        assert team.current_record == "13-6"


@pytest.mark.parametrize(
    "sport_key,expected_id,expected_record",
    [
        (NCAAF, 17075, "1-2"),
        (NCAAB, 162, "15-13"),
        (WNCAAB, 195, "24-9"),
        (LACROSSE, 1432, "13-6"),
    ],
)
def test_each_of_the_four_syracuse_sports_gets_its_own_row(
    sport_key, expected_id, expected_record
):
    for lookup in _every_order(SYRACUSE_ROWS):
        team = _team_for_event(lookup, "Syracuse Orange", sport_key)
        assert team.id == expected_id
        assert team.current_record == expected_record


def test_north_texas_football_is_not_its_womens_basketball_row():
    """The second specimen on the same route: 19-13 is `basketball_wncaab`."""
    rows = [
        _row(15314, "North Texas Mean Green", NCAAF, OREGON_CREST, record="1-1", abbr="UNT"),
        _row(6518, "North Texas Mean Green", WNCAAB, OREGON_CREST, record="19-13", abbr="UNT"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "North Texas Mean Green", NCAAF).current_record == "1-1"
        assert _team_for_event(lookup, "North Texas Mean Green", WNCAAB).current_record == "19-13"


# ── 2. The dropped-key arm: 27 of 32 sides on the reported route ─────────────


def test_a_key_the_blank_shield_made_ambiguous_still_answers_its_own_sport():
    """Oregon: dropped on a bare `.get`, served on a football card."""
    for lookup in _every_order(OREGON_ROWS):
        assert lookup.get("Oregon Ducks") is None, (
            "the cross-league guard's own answer must not change — a caller with "
            "no sport in hand is still protected"
        )
        team = _team_for_event(lookup, "Oregon Ducks", NCAAF)
        assert team is not None, "this null is the 27-of-32 arm"
        assert team.id == 15260 and team.current_record == "2-1"
        assert team.logo_url_small == OREGON_CREST


def test_the_blank_shield_row_is_never_the_answer_for_its_own_sport():
    """Its crest is uncorroborated, so it is not eligible even on a baseball card."""
    for lookup in _every_order(OREGON_ROWS):
        assert _team_for_event(lookup, "Oregon Ducks", BASEBALL_NCAA) is None


def test_two_placeholders_cannot_corroborate_each_other():
    """Otherwise the blank shield becomes a crest on the strength of a second copy.

    Note what this does NOT assert: `_crest_is_shared` compares logo strings, so
    two identical placeholders already read as "shared" and the key survives on
    a bare `.get`. That is pre-existing and is not this fix's to change — what
    must hold is that the per-league map stays empty, so nothing here promotes a
    blank shield from "the row we fell back to" into "the row we chose".
    """
    rows = [
        _row(1, "Blank State", NCAAF, PLACEHOLDER_CREST, record="1-1", color="#111111"),
        _row(2, "Blank State", BASEBALL_NCAA, PLACEHOLDER_CREST, record="9-9", color="#222222"),
    ]
    for lookup in _every_order(rows):
        assert "Blank State" not in lookup.by_league
        assert _team_for_event(lookup, "Blank State", NCAAF) is lookup.get("Blank State")


# ── 3. The safety rail: a wrong-identity row is refused ──────────────────────


def test_the_texas_state_row_is_never_served_on_an_ohio_state_football_card():
    """🔴 The load-bearing guard.

    Sport-awareness alone would hand an NCAAF event row 837 — Texas State's
    abbreviation, maroon and crest — where today the reader sees derived
    initials. Corroboration refuses it: nothing else under this key carries
    `.../326.png`.
    """
    for lookup in _every_order(OHIO_STATE_ROWS):
        assert _team_for_event(lookup, "Ohio State Buckeyes", NCAAF) is None
        for served in lookup.by_league.get("Ohio State Buckeyes", {}).values():
            assert served.abbreviation != "TXST"
            assert served.logo_url_small != TEXAS_STATE_CREST


def test_the_corroborated_ohio_state_sports_are_still_served():
    """The refusal is scoped to the uncorroborated row, not to the school."""
    for lookup in _every_order(OHIO_STATE_ROWS):
        assert _team_for_event(lookup, "Ohio State Buckeyes", NCAAB).id == 198
        assert _team_for_event(lookup, "Ohio State Buckeyes", LACROSSE).id == 1424


def test_two_different_clubs_sharing_a_mascot_stay_unanswered():
    """Queue #238's collision, untouched: neither crest corroborates the other.

    This is a RESIDUAL, asserted so that widening it later is a deliberate
    change with a test to edit rather than a silent consequence.
    """
    rows = [
        _row(
            10,
            "Carolina Panthers",
            "americanfootball_nfl",
            "https://a.espncdn.com/i/teamlogos/nfl/500/car.png",
            alt=["Panthers"],
        ),
        _row(
            11,
            "Florida Panthers",
            "icehockey_nhl",
            "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png",
            alt=["Panthers"],
        ),
    ]
    for lookup in _every_order(rows):
        assert lookup.get("Panthers") is None
        assert _team_for_event(lookup, "Panthers", "americanfootball_nfl") is None
        assert _team_for_event(lookup, "Panthers", "icehockey_nhl") is None
        # The full names were never ambiguous and must still resolve.
        assert _team_for_event(lookup, "Carolina Panthers", "americanfootball_nfl").id == 10


# ── 4. Nothing above may change the existing answers ─────────────────────────


def test_a_club_in_two_competitions_is_unaffected_4978():
    """AS Roma keeps the crest #4978 won it, on `.get` and through the new path."""
    crest = "https://a.espncdn.com/i/teamlogos/soccer/500/104.png"
    rows = [
        _row(1, "AS Roma", "soccer_italy_serie_a", crest, record="20-8-6"),
        _row(2, "AS Roma", "soccer_uefa_champs_league", crest, record="3-1-2"),
    ]
    for lookup in _every_order(rows):
        assert lookup["AS Roma"].logo_url_small == crest
        assert _team_for_event(lookup, "AS Roma", "soccer_uefa_champs_league").id == 2
        assert _team_for_event(lookup, "AS Roma", "soccer_italy_serie_a").id == 1


def test_a_league_with_no_row_falls_back_to_todays_answer():
    """A third competition is not a reason to withhold a club's own crest."""
    crest = "https://a.espncdn.com/i/teamlogos/soccer/500/104.png"
    rows = [
        _row(1, "AS Roma", "soccer_italy_serie_a", crest),
        _row(2, "AS Roma", "soccer_uefa_champs_league", crest),
    ]
    for lookup in _every_order(rows):
        fallback = _team_for_event(lookup, "AS Roma", "soccer_fa_cup")
        assert fallback is lookup["AS Roma"]


def test_a_season_variant_answers_its_parent_league():
    """`league_identity` collapses the variant, so #4945's pair is one league."""
    crest = "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png"
    rows = [
        _row(1, "Boston Red Sox", "baseball_mlb", crest, record="81-81"),
        _row(2, "Boston Red Sox", "baseball_mlb_preseason", crest),
    ]
    for lookup in _every_order(rows):
        team = _team_for_event(lookup, "Boston Red Sox", "baseball_mlb_preseason")
        assert team.current_record == "81-81", "the parent league's board, per #4945"


def test_an_event_with_no_sport_key_gets_todays_answer():
    for lookup in _every_order(SYRACUSE_ROWS):
        assert _team_for_event(lookup, "Syracuse Orange", None) is lookup["Syracuse Orange"]


def test_an_unknown_name_is_none_not_an_error():
    for lookup in _every_order(SYRACUSE_ROWS):
        assert _team_for_event(lookup, "Nobody United", NCAAF) is None
        assert _team_for_event(lookup, None, NCAAF) is None
        assert _team_for_event(None, "Syracuse Orange", NCAAF) is None


# ── 5. The map has to survive the path that serves almost every request ──────


def test_subset_keeps_the_per_league_map_for_a_DROPPED_key():
    """🔴 The inertness trap.

    `_build_team_lookup`'s warm path filters the process-global cache down to the
    requested names. Filtering `by_league` on the SURVIVING keys instead of the
    REQUESTED ones discards every entry for a name the cross-league guard
    dropped — which is exactly the Oregon/Miami population this fix exists for —
    and every test above still passes, because they never go through the cache.
    """
    lookup = _dedupe_team_name_lookup(list(OREGON_ROWS))
    assert "Oregon Ducks" not in lookup, "precondition: the key is dropped"

    served = lookup.subset({"Oregon Ducks"})
    assert isinstance(served, TeamNameLookup)
    assert _team_for_event(served, "Oregon Ducks", NCAAF).id == 15260


def test_subset_drops_the_map_for_names_nobody_asked_for():
    lookup = _dedupe_team_name_lookup(list(OREGON_ROWS) + list(SYRACUSE_ROWS))
    served = lookup.subset({"Oregon Ducks"})
    assert "Syracuse Orange" not in served.by_league
    assert _team_for_event(served, "Syracuse Orange", NCAAF) is None


def test_equality_sees_the_per_league_map():
    """Otherwise a warm/cold parity guard (LAT-P115) is vacuous about the new field.

    `dict.__eq__` compares only the name→row pairs, so two lookups that disagree
    about every per-league row would compare EQUAL — and the one test this class
    invites is exactly "does the refresh-behind build match the blocking one?".
    """
    a = _dedupe_team_name_lookup(list(SYRACUSE_ROWS))
    b = _dedupe_team_name_lookup(list(reversed(SYRACUSE_ROWS)))
    assert a == b, "the two build orders must agree, map included"

    stripped = TeamNameLookup(dict(a))
    assert dict(stripped) == dict(a), "precondition: the name→row pairs are identical"
    assert stripped != a, "a lookup that lost its per-league map is not the same value"
    assert a != dict(a), "and neither is a bare dict with the same pairs"


def test_a_plain_dict_degrades_to_todays_answer():
    """The no-`by_league` branch. Noted as the path NO production caller takes:
    every one of them passes a `TeamNameLookup`, so a suite that exercised only
    this shape would be testing the branch nothing runs."""
    plain = {"Syracuse Orange": SYRACUSE_ROWS[3]}
    assert _team_for_event(plain, "Syracuse Orange", NCAAF).id == 1432


# ── 6. Does it reach the reader? Drive the rail's own formatter ──────────────


class _RailEvent:
    """The columns `_format_game_brief` reads for a scheduled NCAAF fixture."""

    def __init__(self, home, away):
        self.id = 15311499
        self.external_id = "espn-401752000"
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc)
        self.completed_at = None
        self.status = "scheduled"
        self.home_score = None
        self.away_score = None
        self.win_probability_sources = {}
        self.opening_home_probability = None
        self.opening_away_probability = None
        self.period = None
        self.game_clock = None
        self.broadcast_info = None
        self.espn_id = "401752000"
        self.venue = None


def test_the_league_rail_serves_the_football_record_not_the_lacrosse_one():
    """The payload the reported route actually builds, both sides at once."""
    from app.routes.league_futures import _format_game_brief

    lookup = _dedupe_team_name_lookup(list(SYRACUSE_ROWS) + list(OREGON_ROWS))
    brief = _format_game_brief(
        _RailEvent("Syracuse Orange", "Oregon Ducks"),
        sport_key=NCAAF,
        team_lookup=lookup,
    )

    assert brief["home_team_data"]["record"] == "1-2"
    assert brief["home_team_data"]["abbreviation"] == "SYR"
    assert brief["away_team_data"]["record"] == "2-1", (
        "Oregon's key is dropped today, so this side is `team_data: null` on "
        "production — 27 of 32 sides on the reported route"
    )
    assert brief["away_team_data"]["logo_small"] == OREGON_CREST


def test_the_league_rail_still_refuses_the_wrong_identity_row():
    """The rail gets the refusal too — the safety rail is not helper-local."""
    from app.routes.league_futures import _format_game_brief

    lookup = _dedupe_team_name_lookup(list(OHIO_STATE_ROWS))
    brief = _format_game_brief(
        _RailEvent("Ohio State Buckeyes", "Nobody United"),
        sport_key=NCAAF,
        team_lookup=lookup,
    )
    assert "home_team_data" not in brief
    assert "away_team_data" not in brief
