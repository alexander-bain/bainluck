"""The NBA/NHL stamper's decision, driven by REAL StatPal payloads. #2867 / D50 step 3.

`app/tasks/stamp_v1_statpal_fixtures.classify_fixture` is the whole judgement the
task makes: which of our rows, if any, is this StatPal contest, and what state is
that row in. It is pure — no session, no clock, no network — so these tests drive
the code that runs rather than a mock that agrees with whatever it is told.

## the corpus is a real response and the rows are real rows

`tests/fixtures/statpal_{nba,nhl}_season_schedule_20260904.json` are slices of the
actual `/v1/{nba,nhl}/season-schedule` bodies of 2026-09-04, cut from the live
1206- and 1404-game payloads with the tournament wrapper intact and parsed through
the same `_parse_v1_season_schedule` production uses. Every game in them is there
for a reason:

  * **the 23-hour back-to-backs** — NBA `Oklahoma City @ Portland` (`1051930`
    2026-11-11 04:00Z, `1051940` 2026-11-12 03:00Z) and NHL `Dallas @ Winnipeg`
    (`653442` 2026-12-20 00:00Z, `653448` 23:00Z). These are the closest two
    same-pair, same-orientation meetings in either league's whole season, and
    they are what bounds `MATCH_WINDOW` from above;
  * **the split-squad pair** — NHL `649052`/`649053`, Toronto at Montreal and
    Montreal at Toronto at the same minute, which is what orientation is for;
  * **the five NHL rows our side stamps at `04:00:00Z`** (midnight US Eastern) —
    `652877`, `652878`, `652879`, `652881`, `652885` — where StatPal has a real
    puck-drop 18.5 to 22 hours later;
  * **the two honest small offsets** — `652882` at +0:30 and `652884` at +1:00,
    which the window must still accept;
  * six NBA games matching production rows exactly to the minute.

The event rows below are production as it stood 2026-09-04 (`commence_time >=
2026-09-01`: 41 NBA rows, 32 NHL).

## what these tests can fail on

* the window being widened past the point where a back-to-back is unambiguous;
* orientation being relaxed, which would pair a game with its own reverse fixture;
* an already-correct column being treated as "nothing to do", which is how these
  two sports would keep their 691 columns and zero anchors forever;
* a column holding a DIFFERENT id being overwritten instead of receipted;
* the anchor key being derived from the id's digit count, which D55 forbids and
  which NBA's own numbering would punish.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_v1_statpal_fixtures import (
    BACK_TO_BACK_SEPARATION,
    LEAGUES,
    MATCH_WINDOW,
    MAX_SAFE_WINDOW,
    NBA,
    NHL,
    VERDICT_AMBIGUOUS,
    VERDICT_ANCHOR_ONLY,
    VERDICT_CONTRADICTION,
    VERDICT_POLLUTED,
    VERDICT_STAMP,
    VERDICT_UNMATCHED,
    StampRun,
    classify_fixture,
    is_statpal_contest_id,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    SOURCE_STATPAL,
    statpal_anchor_key,
    statpal_id_space,
)
from app.utils.statpal_league_rosters import (
    NBA_TEAM_NAMES,
    NHL_TEAM_NAMES,
    is_dead_city_only_name,
    is_known_league_team,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PAYLOADS = {
    "nba": FIXTURES_DIR / "statpal_nba_season_schedule_20260904.json",
    "nhl": FIXTURES_DIR / "statpal_nhl_season_schedule_20260904.json",
}


def _service():
    return StatPalAPIService.__new__(StatPalAPIService)  # no HTTP client needed


def _fixtures(sport: str):
    return _service()._parse_v1_season_schedule(
        json.loads(PAYLOADS[sport].read_text()), sport
    )


def _by_id(sport: str, contest_id: str):
    for f in _fixtures(sport):
        if f.fixture_id == contest_id:
            return f
    raise AssertionError(f"contest {contest_id} not in the pinned {sport} payload")


def _row(event_id, home, away, when, statpal_fixture_id=None, status="scheduled"):
    return {
        "id": event_id,
        "home": home,
        "away": away,
        "commence_time": when,
        "statpal_fixture_id": statpal_fixture_id,
        "status": status,
    }


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# the corpus itself, checked first
#
# A drifted or truncated fixture must fail as a CORPUS problem, not slip through
# as a silent 0-of-0 pass on every test below.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport,least", [("nba", 9), ("nhl", 16)])
def test_the_pinned_payload_still_parses(sport, least):
    fixtures = _fixtures(sport)
    assert len(fixtures) >= least, f"{sport} payload shrank to {len(fixtures)}"
    assert all(f.fixture_id and f.fixture_id.isdigit() for f in fixtures)
    assert all(f.start_time is not None for f in fixtures)
    assert all(f.home_team and f.away_team for f in fixtures)
    # The tournament wrapper is what `_parse_v1_season_schedule` exists for: the
    # shared ingestion parser flattens it away and every fixture it builds has
    # league=None and season=None.
    assert all(f.season == "2026/2027" for f in fixtures)


def test_time_is_read_as_utc_not_venue_local():
    """Toronto's opener reads 23:00, which is 7:00 PM Eastern.

    NBA and NHL serve no `datetime_utc` — the NFL is the only sport that does —
    so a parser that treated `time` as venue-local would be silently four hours
    wrong on every game, and every match would then miss by exactly one window.
    """
    assert _by_id("nba", "1043639").start_time == _utc("2026-10-03T23:00:00")
    assert _by_id("nhl", "649052").start_time == _utc("2026-09-19T23:00:00")


def test_nba_serves_no_second_id_and_nhl_serves_one_on_every_game():
    """The capabilities doc credits both sports with `id` + `stats_id`. Measured
    2026-09-04 that is wrong for NBA: the key is present and EMPTY on all 1206.
    """
    assert all(not f.stats_id for f in _fixtures("nba"))
    assert all(f.stats_id for f in _fixtures("nhl"))


def test_nhl_stats_id_is_not_unique_per_contest_and_so_cannot_anchor():
    """The measurement that answers step 5's question for the NHL.

    Over the live 1404-game season, `id` is distinct on all 1404 and `stats_id`
    is not: three values are each shared by TWO different contests. Two of them
    are split-squad preseason doubles played at the same minute, the third is a
    genuine back-to-back 23 hours apart. Anchoring on `stats_id` would therefore
    merge two real games — exactly what the `(source, source_id, id_kind)` unique
    index exists to prevent — so the anchor is keyed on `id` and `stats_id` rides
    in the claim context where it stays visible.
    """
    split_a, split_b = _by_id("nhl", "649052"), _by_id("nhl", "649053")
    assert split_a.fixture_id != split_b.fixture_id
    assert split_a.stats_id == split_b.stats_id == "68933"

    b2b_a, b2b_b = _by_id("nhl", "653442"), _by_id("nhl", "653448")
    assert b2b_a.fixture_id != b2b_b.fixture_id
    assert b2b_a.stats_id == b2b_b.stats_id == "69529"


# ---------------------------------------------------------------------------
# the window, and what bounds it
# ---------------------------------------------------------------------------


def test_the_window_is_under_the_separation_the_schedule_itself_imposes():
    """±1h is not inherited from the NFL — it is under a measured ceiling.

    If `MATCH_WINDOW` ever grows past half the closest same-pair separation, one
    of our rows can reach BOTH meetings of a back-to-back and the second silently
    loses a race instead of being reported.
    """
    assert MAX_SAFE_WINDOW == BACK_TO_BACK_SEPARATION / 2
    assert MATCH_WINDOW < MAX_SAFE_WINDOW


@pytest.mark.parametrize(
    "sport,first_id,second_id",
    [("nba", "1051930", "1051940"), ("nhl", "653442", "653448")],
)
def test_the_closest_two_meetings_in_the_season_really_are_that_close(
    sport, first_id, second_id
):
    first, second = _by_id(sport, first_id), _by_id(sport, second_id)
    assert (first.home_team, first.away_team) == (second.home_team, second.away_team)
    assert second.start_time - first.start_time == BACK_TO_BACK_SEPARATION


def test_a_back_to_back_row_matches_its_own_night_and_only_its_own_night():
    first, second = _by_id("nba", "1051930"), _by_id("nba", "1051940")
    night_one = _row(
        1, "Portland Trail Blazers", "Oklahoma City Thunder", first.start_time
    )
    night_two = _row(
        2, "Portland Trail Blazers", "Oklahoma City Thunder", second.start_time
    )
    pool = [night_one, night_two]

    assert classify_fixture(first, pool) == (VERDICT_STAMP, [night_one])
    assert classify_fixture(second, pool) == (VERDICT_STAMP, [night_two])


def test_a_row_halfway_between_a_back_to_back_matches_neither():
    """The proof that the window CANNOT reach both meetings.

    A row placed 11.5h from each game is equidistant. Under any window at or
    above `MAX_SAFE_WINDOW` it would match both and the pass would report an
    ambiguity that is really a guess; under the window that ships it matches
    nothing and is receipted as a row whose start time nobody can vouch for.
    """
    first, second = _by_id("nba", "1051930"), _by_id("nba", "1051940")
    midpoint = first.start_time + MAX_SAFE_WINDOW
    pool = [_row(1, "Portland Trail Blazers", "Oklahoma City Thunder", midpoint)]

    assert classify_fixture(first, pool) == (VERDICT_UNMATCHED, [])
    assert classify_fixture(second, pool) == (VERDICT_UNMATCHED, [])


def test_orientation_is_not_negotiable_on_a_split_squad_double():
    """`649052` and `649053` are two contests at the same minute, and the only
    thing that tells them apart is which side is at home."""
    at_montreal = _by_id("nhl", "649052")   # Toronto @ Montreal
    at_toronto = _by_id("nhl", "649053")    # Montreal @ Toronto
    assert at_montreal.start_time == at_toronto.start_time

    ours = _row(
        15168032, "Toronto Maple Leafs", "Montréal Canadiens", at_toronto.start_time
    )
    assert classify_fixture(at_toronto, [ours]) == (VERDICT_STAMP, [ours])
    assert classify_fixture(at_montreal, [ours]) == (VERDICT_UNMATCHED, [])


# ---------------------------------------------------------------------------
# production rows, exactly as they stood
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "contest,home,away,when",
    [
        ("1050110", "Detroit Pistons", "Boston Celtics", "2026-10-20T19:00:00"),
        ("1050112", "New York Knicks", "Philadelphia 76ers", "2026-10-20T23:00:00"),
        ("1050114", "San Antonio Spurs", "Oklahoma City Thunder", "2026-10-21T01:30:00"),
        ("1051781", "Orlando Magic", "Atlanta Hawks", "2026-10-21T23:00:00"),
        ("1051783", "Washington Wizards", "Milwaukee Bucks", "2026-10-21T23:00:00"),
        ("1050116", "Miami Heat", "Minnesota Timberwolves", "2026-10-21T23:30:00"),
    ],
)
def test_a_real_nba_row_is_stamped_by_its_real_contest(contest, home, away, when):
    """All 41 of our in-window NBA rows agree with StatPal to the minute; these
    are six of them, with the ids and times production actually held."""
    fixture = _by_id("nba", contest)
    ours = _row(1, home, away, _utc(when))
    assert fixture.start_time == _utc(when)
    assert classify_fixture(fixture, [ours]) == (VERDICT_STAMP, [ours])


@pytest.mark.parametrize(
    "contest,home,away,gap_hours",
    [
        ("652878", "Nashville Predators", "Minnesota Wild", 20.0),
        ("652877", "Columbus Blue Jackets", "Buffalo Sabres", 19.0),
        ("652879", "New Jersey Devils", "Philadelphia Flyers", 19.0),
        ("652881", "San Jose Sharks", "Florida Panthers", 22.0),
        ("652885", "Detroit Red Wings", "New York Rangers", 18.5),
    ],
)
def test_our_midnight_eastern_placeholder_is_not_stamped_by_a_wider_window(
    contest, home, away, gap_hours
):
    """Five real NHL rows sit at exactly 04:00Z — midnight US Eastern — where
    StatPal has a real puck-drop 18.5 to 22 hours later.

    Every one of those gaps is ABOVE `MAX_SAFE_WINDOW`, so no window that stays
    safe against a 23h back-to-back can reach them. They are unmatched on
    purpose, and this test exists so that "just widen it a bit" fails here rather
    than in production, where it would start pairing back-to-backs.
    """
    fixture = _by_id("nhl", contest)
    gap = timedelta(hours=gap_hours)
    assert gap > MAX_SAFE_WINDOW
    ours = _row(1, home, away, fixture.start_time - gap)
    assert classify_fixture(fixture, [ours]) == (VERDICT_UNMATCHED, [])


@pytest.mark.parametrize(
    "contest,home,away,gap_minutes",
    [("652882", "Utah Mammoth", "Chicago Blackhawks", 30), ("652884", "Dallas Stars", "St Louis Blues", 60)],
)
def test_the_two_honest_small_offsets_are_still_stamped(
    contest, home, away, gap_minutes
):
    """+0:30 and +1:00, the only sub-day disagreements either league serves.

    The hour is INCLUSIVE — `652884` is exactly at the boundary — and this row
    also carries `St Louis Blues` against StatPal's `St. Louis Blues`, which is
    the punctuation the shared normalizer is there for.
    """
    fixture = _by_id("nhl", contest)
    ours = _row(1, home, away, fixture.start_time - timedelta(minutes=gap_minutes))
    assert classify_fixture(fixture, [ours]) == (VERDICT_STAMP, [ours])


def test_the_accent_on_montreal_is_not_a_different_franchise():
    """Production spells it both ways — `Montreal Canadiens` and `Montréal
    Canadiens` — and the pair must fold onto one franchise before anything else
    happens."""
    fixture = _by_id("nhl", "649052")  # Toronto @ Montreal
    ours = _row(1, "Montréal Canadiens", "Toronto Maple Leafs", fixture.start_time)
    assert classify_fixture(fixture, [ours]) == (VERDICT_STAMP, [ours])


# ---------------------------------------------------------------------------
# the four states a matched row can be in
# ---------------------------------------------------------------------------


def test_a_column_that_already_holds_this_contest_gets_its_anchor_not_a_shrug():
    """The state these two sports are ALREADY in, and the NFL never was.

    `statpal_sync` writes `events.statpal_fixture_id` for NBA and NHL — 691 rows
    on 2026-09-04 — and has never written an anchor. Zero. A stamper that read a
    correct column as "already linked" would leave every one of those rows with a
    column that says linked and an anchor table that says nothing, which
    `anchor_channel.anchor_is_current` reads as STALE on every lookup.
    """
    fixture = _by_id("nba", "1050110")
    ours = _row(
        1,
        "Detroit Pistons",
        "Boston Celtics",
        fixture.start_time,
        statpal_fixture_id="1050110",
    )
    assert classify_fixture(fixture, [ours]) == (VERDICT_ANCHOR_ONLY, [ours])


def test_a_column_holding_a_different_id_is_a_contradiction_not_a_link():
    """The ingestion path picked another contest for this row.

    One of the two rules is wrong and this task does not get to say which.
    Folding it into "already linked" would spend the only evidence that they
    disagreed at all; overwriting would destroy it.
    """
    fixture = _by_id("nba", "1050110")
    ours = _row(
        1,
        "Detroit Pistons",
        "Boston Celtics",
        fixture.start_time,
        statpal_fixture_id="1050999",
    )
    assert classify_fixture(fixture, [ours]) == (VERDICT_CONTRADICTION, [ours])


def test_a_fabricated_statpal_live_value_is_polluted_and_never_written_to():
    """#2963. The column says linked and holds a sentence containing team names —
    the one thing in this system that can merge two real fixtures if anchored."""
    fixture = _by_id("nhl", "652874")
    ours = _row(
        1,
        "Philadelphia Flyers",
        "Pittsburgh Penguins",
        fixture.start_time,
        statpal_fixture_id="statpal_live_Philadelphia Flyers_Pittsburgh Penguins",
    )
    assert classify_fixture(fixture, [ours]) == (VERDICT_POLLUTED, [ours])


def test_two_of_our_rows_for_one_contest_is_filed_with_both_ids_and_written_to_neither():
    """D35: matching symptoms are filed until lane1/#2693 lands. Picking one
    hides the finding while stamping half of it."""
    fixture = _by_id("nba", "1050112")
    a = _row(101, "New York Knicks", "Philadelphia 76ers", fixture.start_time)
    b = _row(
        102,
        "New York Knicks",
        "Philadelphia 76ers",
        fixture.start_time + timedelta(minutes=5),
    )
    verdict, matches = classify_fixture(fixture, [a, b])
    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {101, 102}


def test_a_contest_with_no_start_time_matches_nothing():
    """No start is not a wide window, it is no window: two teams meet two to four
    times a season and names alone would pair November with March."""
    fixture = _by_id("nba", "1050110")
    fixture.start_time = None
    ours = _row(1, "Detroit Pistons", "Boston Celtics", _utc("2026-10-20T19:00:00"))
    assert classify_fixture(fixture, [ours]) == (VERDICT_UNMATCHED, [])


# ---------------------------------------------------------------------------
# ids, spaces and D55
# ---------------------------------------------------------------------------


def test_a_six_digit_and_a_seven_digit_nba_id_are_both_ids():
    """Our column holds 6-digit NBA ids on games up to 2026-04-11 and 7-digit
    from 2026-04-12 on. That is not two namespaces — it is one counter that
    crossed a million on 2026-04-05 — so a length rule would give a confident
    wrong answer on one side of that date. D55 forbids inferring the key from the
    digit count for exactly this reason.
    """
    assert is_statpal_contest_id("987857")     # 2026-03, six digits
    assert is_statpal_contest_id("1043639")    # 2026-10, seven digits
    assert is_statpal_contest_id("649052")     # NHL, six digits
    assert not is_statpal_contest_id("statpal_live_Utah Mammoth_Chicago Blackhawks")
    assert not is_statpal_contest_id("")
    assert not is_statpal_contest_id(None)


@pytest.mark.parametrize(
    "spec,contest,expected",
    [
        (NBA, "1043639", "basketball_nba:1043639"),
        (NHL, "649052", "icehockey_nhl:649052"),
    ],
)
def test_the_anchor_key_is_qualified_by_our_sport_key(spec, contest, expected):
    key = statpal_anchor_key(contest, statpal_id_space(spec.sport_key))
    assert key is not None
    assert (key.source, key.source_id, key.id_kind) == (
        SOURCE_STATPAL,
        expected,
        ANCHOR_KIND_GAME,
    )


def test_the_two_leagues_cannot_collide_even_on_the_same_number():
    """StatPal numbers every sport out of one growing sequence, so an NBA and an
    NHL contest CAN share digits. Unqualified, that is a merge across two sports;
    qualified, the unique index still catches a real duplicate inside one."""
    nba = statpal_anchor_key("649052", statpal_id_space(NBA.sport_key))
    nhl = statpal_anchor_key("649052", statpal_id_space(NHL.sport_key))
    assert nba.source_id != nhl.source_id


# ---------------------------------------------------------------------------
# the rosters, and the vocabulary that is dead
# ---------------------------------------------------------------------------


def test_both_sides_spell_every_franchise_the_same_way():
    assert len(NBA_TEAM_NAMES) == 30
    assert len(NHL_TEAM_NAMES) == 32
    for sport, spec in (("nba", NBA), ("nhl", NHL)):
        for f in _fixtures(sport):
            assert is_known_league_team(spec.sport_key, f.home_team), f.home_team
            assert is_known_league_team(spec.sport_key, f.away_team), f.away_team


def test_the_retired_city_only_names_are_recognised_and_never_matchable():
    """242 production rows carry `Toronto`, `Los Angeles C`, `New York I` and the
    rest. Nothing has written one since 2026-03-25 and none covers a game after
    2026-05-20, so they are out of every window this task sees — but if one comes
    back it must be reported BY NAME, not bridged by guessing a franchise from a
    single letter."""
    for name in ("Los Angeles C", "New York I", "Golden State", "Toronto"):
        assert is_dead_city_only_name(name)
    assert not is_known_league_team("basketball_nba", "Los Angeles C")
    assert not is_known_league_team("icehockey_nhl", "New York I")
    # And a franchise's real name is never mistaken for the dead vocabulary.
    assert not is_dead_city_only_name("Toronto Raptors")


def test_a_sport_with_no_measured_roster_answers_no_rather_than_guessing():
    assert not is_known_league_team("baseball_mlb", "Boston Red Sox")
    assert not is_known_league_team(None, "Boston Celtics")


# ---------------------------------------------------------------------------
# the run's own report
# ---------------------------------------------------------------------------


def test_the_two_leagues_are_registered_under_our_own_sport_keys():
    assert set(LEAGUES) == {"basketball_nba", "icehockey_nhl"}
    assert LEAGUES["basketball_nba"].statpal_sport == "nba"
    assert LEAGUES["icehockey_nhl"].statpal_sport == "nhl"
    assert LEAGUES["basketball_nba"].serves_stats_id is False
    assert LEAGUES["icehockey_nhl"].serves_stats_id is True


def test_stats_id_coverage_is_reported_against_what_the_league_was_measured_to_serve():
    """All-or-nothing on purpose: NHL serves it on 1404/1404 and NBA on 0/1206, so
    a partial answer from either is a change worth a receipt rather than noise
    under a threshold nobody measured."""
    nhl = StampRun(sport_key=NHL.sport_key, stats_id_expected=True)
    nhl.stats_id_present = 1404
    assert nhl.stats_id_as_expected
    nhl.stats_id_absent = 1
    assert not nhl.stats_id_as_expected

    nba = StampRun(sport_key=NBA.sport_key, stats_id_expected=False)
    nba.stats_id_absent = 1206
    assert nba.stats_id_as_expected
    nba.stats_id_present = 1
    assert not nba.stats_id_as_expected


def test_the_summary_names_its_sport_so_two_leagues_cannot_be_read_as_one():
    summary = StampRun(sport_key=NBA.sport_key).summary()
    assert summary["sport_key"] == "basketball_nba"
    assert summary["stats_id"]["expected"] == "on none"
