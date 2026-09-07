"""Soccer's anchor id, decided from payloads instead of from the obvious field.

authority/062, under D55 and #3366. The soccer shadow stamper does not exist
yet; this file is the evidence it will be built on, pinned so that it cannot
quietly stop being true.

The question is MLB's three-id problem (#3094) in a new sport: StatPal's v2
soccer feed publishes four id spaces per match and the one named like a primary
key is the one that is not an identity. Two full payloads are pinned verbatim:

    statpal_soccer_matches_live_20260907_fullcensus.json        195 rows, 113 leagues
    statpal_soccer_matches_daily_offset1_20260907_fullcensus.json  274 rows, 92 leagues

Both were captured from the venue's own API at ~05:00Z on 2026-09-07 (notice
26: a question about what a venue serves is answered against the venue). They
are censuses, not samples, because every claim here is a rate over a whole
board — "collides once in 188" is not a fact a trimmed fixture can carry.

What is deliberately NOT asserted: that `soccer` belongs in
`STATPAL_LIVE_ANCHOR_FIELD`. That map is the LIVE INGESTION writer's, and
`test_statpal_live_anchor_entrypoint_3094.py` requires a sport in it to be
driven through the task. Soccer's live ingestion is dark on purpose
(`LIVESCORES_INGESTION_DARK_SPORTS`), so it cannot meet that condition and does
not get an exemption from it; it joins when #3348 gives it a writer.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.utils.provider_anchor_keys import (
    STATPAL_ID_SPACE_SOCCER,
    statpal_anchor_key,
    statpal_id_space,
)
from app.utils.sport_keys import STATPAL_LIVE_ANCHOR_FIELD, STATPAL_SPORT_MAPPING

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_CENSUS = FIXTURES / "statpal_soccer_matches_live_20260907_fullcensus.json"
DAILY1_CENSUS = (
    FIXTURES / "statpal_soccer_matches_daily_offset1_20260907_fullcensus.json"
)

#: Every id space the v2 soccer feed publishes per match.
ID_FIELDS = ("main_id", "fallback_id_1", "fallback_id_2", "fallback_id_3")

#: The one that is complete and unique. The whole point of this file.
ANCHOR_FIELD = "fallback_id_3"


def _load(path: Path) -> list[dict]:
    """Every match row in a v2 soccer payload, whatever the section is called.

    The section name is not stable — `matches/live` serves `live_matches` and
    `matches/daily` serves a DATE-STAMPED key (`matches_08_09_2026`), so a
    reader that hardcodes either only reads half the evidence.
    """
    data = json.loads(path.read_text())
    section = next(
        (v for v in data.values() if isinstance(v, dict) and "league" in v), None
    )
    assert section is not None, f"{path.name}: no league-bearing section"
    leagues = section["league"]
    leagues = leagues if isinstance(leagues, list) else [leagues]
    rows: list[dict] = []
    for league in leagues:
        matches = league.get("match")
        # A one-game league collapses `match` to a bare dict.
        matches = matches if isinstance(matches, list) else [matches] if matches else []
        rows.extend(m for m in matches if isinstance(m, dict))
    return rows


def _values(rows: list[dict], field: str) -> list[str]:
    return [str(r.get(field) or "").strip() for r in rows]


def _present(rows: list[dict], field: str) -> list[str]:
    return [v for v in _values(rows, field) if v]


def _pair(row: dict) -> tuple[str, str]:
    home = row.get("home") if isinstance(row.get("home"), dict) else {}
    away = row.get("away") if isinstance(row.get("away"), dict) else {}
    return (
        str(home.get("name") or "").strip(),
        str(away.get("name") or "").strip(),
    )


@pytest.fixture(scope="module")
def live_rows() -> list[dict]:
    return _load(LIVE_CENSUS)


@pytest.fixture(scope="module")
def daily1_rows() -> list[dict]:
    return _load(DAILY1_CENSUS)


# ---------------------------------------------------------------------------
# 1. The census is the census
# ---------------------------------------------------------------------------


def test_the_pinned_payloads_are_the_boards_they_claim_to_be(live_rows, daily1_rows):
    """Guard the denominators, because every other test here is a rate over them."""
    assert len(live_rows) == 195
    assert len(daily1_rows) == 274


# ---------------------------------------------------------------------------
# 2. main_id is not an identity — three independent disqualifications
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "which,expected_collisions",
    [("live_rows", 1), ("daily1_rows", 2)],
)
def test_main_id_collides_on_every_board(which, expected_collisions, request):
    """Two different matches, one `main_id`. Measured, not feared.

    This is the finding. A stamper that took `main_id` for an anchor would
    write one key for two games — #2963 is the 8,272-row repair that shape
    causes, and it is cheaper to never start.
    """
    rows = request.getfixturevalue(which)
    counts = collections.Counter(_present(rows, "main_id"))
    collisions = {v: n for v, n in counts.items() if n > 1}

    assert (
        len(collisions) == expected_collisions
    ), f"main_id collisions changed: {collisions}"

    # And the colliding rows really are different matches, not one row served
    # twice — which is what makes this an id defect rather than a dedup bug.
    for value in collisions:
        pairs = {_pair(r) for r in rows if str(r.get("main_id") or "").strip() == value}
        assert len(pairs) > 1, f"{value} is one match served twice, not a collision"


def test_the_live_collision_spans_two_competitions(daily1_rows):
    """Why the collisions happen: one id sequence across all the leagues.

    `2026090846246` is an England National League Cup tie AND an FA Cup
    qualifier. A per-league sequence could not do that, so the space is global
    — which is separately the reason `statpal_id_space` must not qualify soccer
    by our league key.
    """
    colliding = [
        r for r in daily1_rows if str(r.get("main_id") or "").strip() == "2026090846246"
    ]
    assert len(colliding) == 2
    assert {_pair(r) for r in colliding} == {
        ("Scunthorpe", "Nottingham U21"),
        ("Buckhurst Hill", "Yaxley"),
    }


@pytest.mark.parametrize("which,blank", [("live_rows", 7), ("daily1_rows", 12)])
def test_main_id_is_blank_on_real_rows(which, blank, request):
    """The second disqualification: it is absent, on real fixtures we carry."""
    rows = request.getfixturevalue(which)
    assert _values(rows, "main_id").count("") == blank


def test_main_id_encodes_the_date_so_a_postponement_changes_it(live_rows, daily1_rows):
    """The third: it is composite, not opaque — `YYYYMMDD` + 5 digits.

    An id whose prefix is the kickoff date is an id that a rescheduled fixture
    cannot keep. Asserted as agreement with the row's OWN date rather than as a
    regex, because the claim that matters is the coupling, not the shape.
    """
    checked = 0
    for row in live_rows + daily1_rows:
        main_id = str(row.get("main_id") or "").strip()
        date = str(row.get("date") or "").strip()
        if len(main_id) != 13 or len(date) != 10:
            continue
        day, month, year = date.split(".")
        assert main_id[:8] == f"{year}{month}{day}", (main_id, date)
        assert main_id[8:].isdigit()
        checked += 1
    assert checked == 450, f"expected 450 datable rows, checked {checked}"


# ---------------------------------------------------------------------------
# 3. fallback_id_3 is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["live_rows", "daily1_rows"])
def test_the_anchor_field_is_complete_and_unique(which, request):
    """Present on every row, and never twice. Neither is true of any other space."""
    rows = request.getfixturevalue(which)
    values = _values(rows, ANCHOR_FIELD)

    assert "" not in values, "the anchor space is blank on a row"
    assert len(set(values)) == len(rows), "the anchor space collides"


@pytest.mark.parametrize("which", ["live_rows", "daily1_rows"])
def test_the_anchor_field_is_the_only_complete_space(which, request):
    """Stated as a comparison so that a regression in ANY space fails here.

    If StatPal ever starts filling `main_id` completely, this test fails and
    the choice gets re-argued from a fresh census — which is the right outcome,
    not a false alarm.
    """
    rows = request.getfixturevalue(which)
    complete = {f for f in ID_FIELDS if len(_present(rows, f)) == len(rows)}
    assert complete == {ANCHOR_FIELD}


def test_the_ids_are_stable_across_the_two_endpoints(live_rows, daily1_rows):
    """The cross-endpoint half of the question: does an id SURVIVE the journey?

    Nine matches are served by both the live board and the next day's schedule
    (late kickoffs that cross midnight UTC). Joined on the team pair — the one
    key that is definitionally independent of the ids under test — all four id
    spaces agree on all nine. So the ids are stable; `fallback_id_3` is chosen
    for being complete and unique, not for being the only one that travels.
    """
    live_by_pair = {_pair(r): r for r in live_rows}
    daily_by_pair = {_pair(r): r for r in daily1_rows}
    both = sorted(set(live_by_pair) & set(daily_by_pair))

    assert len(both) == 9, f"the overlap moved: {both}"

    for pair in both:
        for field in ID_FIELDS:
            left = str(live_by_pair[pair].get(field) or "").strip()
            right = str(daily_by_pair[pair].get(field) or "").strip()
            assert left == right, f"{pair} disagrees on {field}: {left!r} vs {right!r}"
        # Vacuous agreement on a pair of blanks would prove nothing.
        assert str(live_by_pair[pair].get(ANCHOR_FIELD) or "").strip()


# ---------------------------------------------------------------------------
# 4. The parser carries it, and still substitutes nothing
# ---------------------------------------------------------------------------


def test_the_parser_carries_the_anchor_space_for_every_row(live_rows):
    """D55: carried, never substituted.

    The whole board must arrive with the anchor id attached — a parser that
    carried it on most rows would hand the stamper a silent hole.
    """
    service = StatPalAPIService(api_key="test")
    fixtures = service._parse_soccer_live_matches(json.loads(LIVE_CENSUS.read_text()))

    assert len(fixtures) == len(live_rows)
    assert all(f.fallback_id_3 for f in fixtures)
    assert len({f.fallback_id_3 for f in fixtures}) == len(fixtures)

    # And it is the payload's value, not something derived.
    by_pair = {(f.home_team, f.away_team): f.fallback_id_3 for f in fixtures}
    for row in live_rows:
        assert by_pair[_pair(row)] == str(row[ANCHOR_FIELD]).strip()


def test_fixture_id_still_holds_main_id_and_still_admits_blanks(live_rows):
    """The shipped door does not change behaviour.

    `get_live_fixtures` feeds `espn_sync`'s standby check, which is keyed on the
    team pair; blank-`main_id` rows are emitted blank on purpose so that
    StatPal's coverage of exactly the games ESPN went dark on is not
    under-reported. Carrying a better id must not have quietly promoted it into
    `fixture_id` — that would be the substitution D55 forbids, and it would put
    a real id where a downstream reader has been taught to expect a blank.
    """
    service = StatPalAPIService(api_key="test")
    fixtures = service._parse_soccer_live_matches(json.loads(LIVE_CENSUS.read_text()))

    blank = [f for f in fixtures if not f.fixture_id]
    assert len(blank) == 7
    # Every one of them still carries the anchor space — which is the payoff.
    assert all(f.fallback_id_3 for f in blank)


# ---------------------------------------------------------------------------
# 5. The anchor KEY qualifier
# ---------------------------------------------------------------------------


def test_every_soccer_key_maps_to_one_id_space():
    """Our seven mapped league keys, StatPal's one sequence, one qualifier."""
    soccer_keys = [k for k, v in STATPAL_SPORT_MAPPING.items() if v == "soccer"]
    assert len(soccer_keys) == 7

    for key in soccer_keys:
        assert statpal_id_space(key) == STATPAL_ID_SPACE_SOCCER


def test_an_unmapped_soccer_league_maps_to_the_same_space():
    """Matched as a prefix, so the next league added is spaced right by default.

    This is the case an enumeration would miss, and soccer's key vocabulary
    grows per league — `STATPAL_SPORT_MAPPING`'s seven are a subset of the
    `soccer_*` keys `events` actually carries.
    """
    assert statpal_id_space("soccer_netherlands_eredivisie") == STATPAL_ID_SPACE_SOCCER
    assert statpal_id_space("soccer_brazil_campeonato") == STATPAL_ID_SPACE_SOCCER


def test_two_leagues_one_match_is_one_anchor_key():
    """The defect this prevents, written as the two keys it would have written."""
    epl = statpal_anchor_key("9541291", statpal_id_space("soccer_epl"))
    ucl = statpal_anchor_key("9541291", statpal_id_space("soccer_uefa_champs_league"))

    assert epl is not None and ucl is not None
    assert epl.source_id == ucl.source_id == "soccer:9541291"


def test_the_prefix_is_the_whole_sport_word_not_a_letter_of_it():
    """A prefix rule's real risk is being too SHORT, and no other test sees it.

    Found by mutation: trimming the constant to `"s"` collapsed every sport
    beginning with that letter into the soccer bucket and the whole suite still
    passed, because nothing we carry today starts with `s` except soccer. That
    is luck, not a guard — collapsing ACROSS provider sports is the #2879
    defect, and it would arrive silently the first time a key like these is
    minted.
    """
    from app.utils.provider_anchor_keys import _SOCCER_SPORT_KEY_PREFIX

    assert _SOCCER_SPORT_KEY_PREFIX == "soccer"

    for neighbour in (
        "softball_ncaa",
        "snooker_world_championship",
        "sumo_grand_tournament",
        "surfing_wsl",
        "soccer",  # the bare sport is its own space already; must not change
    ):
        assert statpal_id_space(neighbour) == (
            STATPAL_ID_SPACE_SOCCER if neighbour == "soccer" else neighbour
        )


def test_the_other_sports_are_untouched():
    """A prefix rule is a blunt instrument; prove it stayed inside soccer."""
    assert statpal_id_space("baseball_mlb") == "baseball_mlb"
    assert statpal_id_space("americanfootball_nfl") == "americanfootball_nfl"
    assert statpal_id_space("basketball_nba") == "basketball_nba"
    assert statpal_id_space("icehockey_nhl") == "icehockey_nhl"
    assert statpal_id_space("tennis_atp_us_open") == "tennis"
    assert statpal_id_space(None) is None
    assert statpal_id_space("") == ""


# ---------------------------------------------------------------------------
# 6. What this change is NOT
# ---------------------------------------------------------------------------


def test_soccer_did_not_join_the_live_ingestion_declaration():
    """`STATPAL_LIVE_ANCHOR_FIELD` is the live WRITER's map, and soccer has none.

    Its guard requires a declared sport to be driven through the task, and
    soccer's live ingestion is dark by construction. Carrying the id on the
    fixture is not a licence to declare it here; that happens when #3348 gives
    soccer a writer to prove. Asserted so that a future session reaching for
    the obvious one-line edit reads the reason first.
    """
    assert "soccer" not in STATPAL_LIVE_ANCHOR_FIELD
