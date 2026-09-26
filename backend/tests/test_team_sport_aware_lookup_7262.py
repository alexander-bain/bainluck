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
        # #8787: the bare `.get` still keeps the key, but on a football card
        # that answer is the BASEBALL row (blank shield, 9-9) and nothing
        # vouches for it, so the sport-aware reader refuses it.
        assert lookup.get("Blank State") is not None
        assert _team_for_event(lookup, "Blank State", NCAAF) is None


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
    """A third competition is not a reason to withhold a club's own crest.

    It is a reason to withhold that competition's SEASON (#5697): the fallback
    row is another league's, so its record never reaches this card.
    """
    crest = "https://a.espncdn.com/i/teamlogos/soccer/500/104.png"
    rows = [
        _row(1, "AS Roma", "soccer_italy_serie_a", crest, record="3-1-1"),
        _row(2, "AS Roma", "soccer_uefa_champs_league", crest, record="1-0-0"),
    ]
    for lookup in _every_order(rows):
        fallback = _team_for_event(lookup, "AS Roma", "soccer_fa_cup")
        assert fallback.logo_url_small == lookup["AS Roma"].logo_url_small == crest
        assert fallback.current_record is None


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
    plain = {"Syracuse Orange": SYRACUSE_ROWS[0]}
    assert _team_for_event(plain, "Syracuse Orange", NCAAF).id == 17075
    # #8787: with no per-league map nothing can vouch for another sport's row.
    plain = {"Syracuse Orange": SYRACUSE_ROWS[3]}
    assert _team_for_event(plain, "Syracuse Orange", NCAAF) is None


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


# ── #8682: the sole real crest under a key, checked against its own ESPN id ──
#
# Production 2026-09-25, `/api/leagues/americanfootball_ncaaf` at 390px: Coastal
# Carolina, Fresno State, Northern Illinois and Arkansas State drew grey
# initials on every card. Each football row carries its own ESPN badge
# (`.../500/324.png` beside `espn_id` 324); its only sibling under the name is a
# `baseball_ncaa` row with the blank shield. Nothing could corroborate, so the
# rail refused — a disagreement with a placeholder, read as one with a crest.

COASTAL_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/324.png"
BASEBALL_BLANK_SHIELD = (
    "https://a.espncdn.com/guid/2c3c8cc1-efab-3ad5-9815-4550421a8e2a/logos/default.png"
)


def _espn_row(row_id, name, sport_key, crest, espn_id, **kw):
    row = _row(row_id, name, sport_key, crest, **kw)
    row.espn_id = espn_id
    return row


COASTAL_ROWS = [
    _espn_row(
        15322, "Coastal Carolina Chanticleers", NCAAF, COASTAL_CREST, "324",
        record="1-3", abbr="CCU", color="#006f71",
    ),
    _espn_row(
        908, "Coastal Carolina Chanticleers", BASEBALL_NCAA, BASEBALL_BLANK_SHIELD, "146",
        record="40-20", abbr="CCU", color="#59A0A0",
    ),
]


def test_a_sole_crest_that_is_its_own_espn_badge_is_served_on_its_sport_8682():
    for lookup in _every_order(COASTAL_ROWS):
        assert lookup.get("Coastal Carolina Chanticleers") is None, (
            "a caller with no sport in hand keeps the cross-league guard's answer"
        )
        team = _team_for_event(lookup, "Coastal Carolina Chanticleers", NCAAF)
        assert team is not None, "this null is the grey-initials card"
        assert team.id == 15322 and team.logo_url_small == COASTAL_CREST
        # The blank-shield row is still nobody's answer, even on its own sport.
        assert _team_for_event(lookup, "Coastal Carolina Chanticleers", BASEBALL_NCAA) is None


def test_a_sole_crest_that_is_ANOTHER_clubs_badge_is_refused_8682():
    """The second signal is load-bearing: a crest whose number is not the row's id."""
    rows = [
        _espn_row(1, "Coastal Carolina Chanticleers", NCAAF, TEXAS_STATE_CREST, "324"),
        COASTAL_ROWS[1],
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Coastal Carolina Chanticleers", NCAAF) is None


def test_a_sole_crest_with_no_espn_id_is_refused_8682():
    rows = [
        _espn_row(1, "Coastal Carolina Chanticleers", NCAAF, COASTAL_CREST, None),
        COASTAL_ROWS[1],
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Coastal Carolina Chanticleers", NCAAF) is None


def test_a_self_consistent_crest_beside_a_DIFFERENT_real_crest_is_refused_8682():
    """837's shape with ids attached: the exception never overrides a real disagreement."""
    rows = [
        _espn_row(837, "Ohio State Buckeyes", NCAAF, TEXAS_STATE_CREST, "326", abbr="TXST"),
        _espn_row(198, "Ohio State Buckeyes", NCAAB, OHIO_STATE_CREST, "194", abbr="OSU"),
        _espn_row(879, "Ohio State Buckeyes", BASEBALL_NCAA, BASEBALL_BLANK_SHIELD, "108"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Ohio State Buckeyes", NCAAF) is None
        # ...and a lone different real crest with NO corroboration refuses both.
        assert _team_for_event(lookup, "Ohio State Buckeyes", NCAAB) is None


def test_an_unnumbered_crest_never_takes_the_exception_8682():
    rows = [
        _espn_row(10, "Panthers FC", "americanfootball_nfl",
                  "https://a.espncdn.com/i/teamlogos/nfl/500/car.png", "29"),
        _espn_row(11, "Panthers FC", BASEBALL_NCAA, BASEBALL_BLANK_SHIELD, "7"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Panthers FC", "americanfootball_nfl") is None


def test_the_snapshot_carries_espn_id_so_the_exception_is_reachable_8682():
    """A test-only `_Row` with `espn_id` proves nothing if the cache strips it."""
    from types import SimpleNamespace

    from app.routes.events import _snapshot_team

    live = SimpleNamespace(
        id=15322, sport_id=760, name="Coastal Carolina Chanticleers", slug=None,
        abbreviation="CCU", primary_color="#006f71", secondary_color=None,
        logo_url_small=COASTAL_CREST, logo_url_large=COASTAL_CREST,
        current_record="1-3", alternate_names=[], standings_data=None,
        standings_updated_at=None, season_stats=None, espn_id="324",
    )
    snap = _snapshot_team(live, sport_key=NCAAF)
    assert snap.espn_id == "324"
    lookup = _dedupe_team_name_lookup(
        [snap, _snapshot_team(SimpleNamespace(**{**vars(live), "id": 908,
            "logo_url_small": BASEBALL_BLANK_SHIELD, "espn_id": "146",
            "primary_color": "#59A0A0"}), sport_key=BASEBALL_NCAA)]
    )
    assert _team_for_event(lookup, "Coastal Carolina Chanticleers", NCAAF).id == 15322


def test_a_self_consistent_crest_with_ANOTHER_clubs_abbreviation_is_refused_8682():
    """Production's contaminated rows keep their own crest: Northern Kentucky as `TEX`."""
    rows = [
        _espn_row(2593, "Northern Kentucky Norse", NCAAB,
                  "https://a.espncdn.com/i/teamlogos/ncaa/500/94.png", "94", abbr="TEX"),
        _espn_row(3001, "Northern Kentucky Norse", BASEBALL_NCAA, BASEBALL_BLANK_SHIELD,
                  "2001", abbr="NKU"),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Northern Kentucky Norse", NCAAB) is None


def test_a_bare_mascot_shared_by_two_schools_takes_no_exception_8682():
    """'Lumberjacks': Northern Arizona football beside Stephen F. Austin baseball."""
    rows = [
        _espn_row(17069, "Northern Arizona Lumberjacks", NCAAF,
                  "https://a.espncdn.com/i/teamlogos/ncaa/500/2464.png", "2464",
                  abbr="NAU", alt=["Lumberjacks"]),
        _espn_row(4001, "Stephen F. Austin Lumberjacks", BASEBALL_NCAA, BASEBALL_BLANK_SHIELD,
                  "301", abbr="SFA", alt=["Lumberjacks"]),
    ]
    for lookup in _every_order(rows):
        assert _team_for_event(lookup, "Lumberjacks", NCAAF) is None
