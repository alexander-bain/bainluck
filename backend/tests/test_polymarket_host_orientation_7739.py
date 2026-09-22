"""#7739 — a Polymarket-minted US-sport game stops naming the away team as host.

`_create_event_from_prediction_market` stamps `home_team_name = team_a`, the club
Polymarket names FIRST in "A vs. B". Measured against ESPN's explicit `homeAway`
on 2026-09-22, Polymarket mirrors each sport's own listing habit rather than one
convention — WNBA/NHL 87 of 87 name the AWAY club first, soccer 34 of 34 name the
HOST first — so `team_a` is right for world football and wrong for the US leagues.

These guards pin the two halves that a later change is most likely to break:

  * the LEAGUE list stays a list of leagues that were actually measured, and the
    fail-closed default is preserved (the unmeasured population is dominated by
    world football, where a flip would MANUFACTURE this defect);
  * the repair's `classify` writes only when ESPN and the measured convention
    agree — the same-minute home-and-home pair that defeats a name-and-time join
    must come out AMBIGUOUS, never as a swap.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.prediction_market_matching import (
    POLYMARKET_AWAY_FIRST_LEAGUES,
    orient_matchup_for_venue,
    polymarket_lists_away_first,
)

REPAIR_PATH = (Path(__file__).resolve().parents[1]
               / "scripts" / "repair_polymarket_event_orientation.py")


def _load_repair():
    """Import the repair script by path — `backend/scripts` is not a package."""
    spec = importlib.util.spec_from_file_location("repair_7739", REPAIR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The measured convention
# --------------------------------------------------------------------------

@pytest.mark.parametrize("league", sorted(POLYMARKET_AWAY_FIRST_LEAGUES))
def test_every_listed_league_is_away_first(league):
    assert polymarket_lists_away_first(league) is True


@pytest.mark.parametrize("league", [
    # World football, measured 34/34 HOME-first. A flip here is the defect.
    "soccer_uefa_nations_league", "soccer_usa_mls", "soccer_spain_segunda_division",
    # European club basketball: `basketball_other` looks like a US bucket and is
    # not — its Polymarket rows are Lithuanian/Serbian/Italian/German/Spanish.
    "basketball_other", "icehockey_liiga", "baseball_npb",
    # Never measured, so never flipped, however plausible the habit.
    "basketball_nba", "americanfootball_nfl", "baseball_mlb",
])
def test_unmeasured_and_home_first_leagues_are_left_alone(league):
    assert polymarket_lists_away_first(league) is False


def test_absent_league_fails_closed():
    """An unresolved league keeps the stored orientation.

    This is the common case, not an edge one: the rows this ship repairs exist
    BECAUSE their clubs did not resolve. Defaulting to a flip would rewrite every
    unresolvable soccer fixture in the same sweep.
    """
    assert polymarket_lists_away_first(None) is False
    assert polymarket_lists_away_first("") is False


def test_the_league_list_carries_only_measured_leagues():
    """A tripwire on the set itself, not on behaviour.

    `polymarket_lists_away_first` is a membership test, so every test above
    passes automatically for whatever is in the set — including a league somebody
    appends on the strength of "US sport, same habit". The measurement is the
    price of entry; adding NBA/NFL/MLB means re-running
    `artifacts-lane1-591/measure_pm_orientation.py` on a live slate and amending
    this list with the counts.
    """
    assert POLYMARKET_AWAY_FIRST_LEAGUES == frozenset({
        "basketball_wnba", "icehockey_nhl", "icehockey_nhl_preseason",
    })


# --------------------------------------------------------------------------
# Orientation at the seam
# --------------------------------------------------------------------------

def test_polymarket_us_league_names_the_second_club_as_host():
    # The live specimen: Polymarket "Toronto Tempo vs. Connecticut Sun",
    # ESPN 401857215 home=Connecticut Sun.
    assert orient_matchup_for_venue(
        "polymarket", "basketball_wnba", "Toronto Tempo", "Connecticut Sun",
    ) == ("Connecticut Sun", "Toronto Tempo")


def test_polymarket_soccer_is_untouched():
    assert orient_matchup_for_venue(
        "polymarket", "soccer_uefa_nations_league", "Netherlands", "Germany",
    ) == ("Netherlands", "Germany")


def test_kalshi_is_untouched_even_in_a_listed_league():
    """Kalshi titles and tickers are a separate convention this ship did not
    measure. Sharing the mint path is not evidence of sharing the habit."""
    assert orient_matchup_for_venue(
        "kalshi", "basketball_wnba", "Toronto Tempo", "Connecticut Sun",
    ) == ("Toronto Tempo", "Connecticut Sun")


def test_unresolved_league_is_untouched():
    assert orient_matchup_for_venue(
        "polymarket", None, "Capitals", "Hurricanes",
    ) == ("Capitals", "Hurricanes")


# --------------------------------------------------------------------------
# The repair's verdict, which is what actually writes
# --------------------------------------------------------------------------

KICK = datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc)


def _row(home, away, kickoff=KICK):
    return {"id": 15310072, "home_team_name": home, "away_team_name": away,
            "commence_time": kickoff, "status": "scheduled"}


def _fixture(home, away, kickoff=KICK, neutral=False, espn_id="401857215"):
    return {"espn_id": espn_id, "kickoff": kickoff, "home": home, "away": away,
            "neutral": neutral}


def test_reversed_row_is_the_only_thing_that_writes():
    repair = _load_repair()
    verdict, hit = repair.classify(
        _row("Toronto Tempo", "Connecticut Sun"),
        [_fixture(home="Connecticut Sun", away="Toronto Tempo")],
        90, "basketball_wnba",
    )
    assert verdict == "REVERSED"
    assert hit["espn_id"] == "401857215"


def test_a_correct_row_is_left_alone():
    repair = _load_repair()
    verdict, _ = repair.classify(
        _row("Connecticut Sun", "Toronto Tempo"),
        [_fixture(home="Connecticut Sun", away="Toronto Tempo")],
        90, "basketball_wnba",
    )
    assert verdict == "CORRECT"


def test_same_minute_home_and_home_is_ambiguous_not_a_swap():
    """The real shape that defeats a name-and-time join.

    ESPN carried Ottawa/Montreal TWICE at 2026-09-26T23:00Z — a split-squad
    home-and-home, opposite orientations, same two clubs, same minute. Picking
    either leg is a coin toss on a truth field, and picking the wrong one
    "corrects" a row that was already right.
    """
    repair = _load_repair()
    verdict, hit = repair.classify(
        _row("Senators", "Canadiens"),
        [_fixture(home="Ottawa Senators", away="Montreal Canadiens",
                  espn_id="401879651"),
         _fixture(home="Montreal Canadiens", away="Ottawa Senators",
                  espn_id="401881724")],
        90, "icehockey_nhl_preseason",
    )
    assert verdict == "AMBIGUOUS"
    assert hit is None


def test_espn_alone_cannot_write_when_the_convention_disagrees():
    """Both signals are required. With the league absent from the measured set
    the convention predicts no flip, so an ESPN-only reversal is reported and
    skipped rather than written."""
    repair = _load_repair()
    verdict, _ = repair.classify(
        _row("Netherlands", "Germany"),
        [_fixture(home="Germany", away="Netherlands")],
        90, "soccer_uefa_nations_league",
    )
    assert verdict == "DISAGREE"


def test_a_fixture_outside_the_kickoff_window_is_not_a_match():
    """The window has to bind on BOTH the straight and the flipped branch.

    Written as one chained `and`/`or` expression, Python binds it so the time
    test guards only the first branch — and a reversed fixture DAYS away then
    matches. These clubs meet repeatedly in a season, so that is not theoretical.
    """
    repair = _load_repair()
    verdict, _ = repair.classify(
        _row("Toronto Tempo", "Connecticut Sun"),
        [_fixture(home="Connecticut Sun", away="Toronto Tempo",
                  kickoff=KICK + timedelta(days=3))],
        90, "basketball_wnba",
    )
    assert verdict == "NO-ESPN-FIXTURE"


def test_a_neutral_site_fixture_is_never_swapped():
    repair = _load_repair()
    verdict, _ = repair.classify(
        _row("Toronto Tempo", "Connecticut Sun"),
        [_fixture(home="Connecticut Sun", away="Toronto Tempo", neutral=True)],
        90, "basketball_wnba",
    )
    assert verdict == "NEUTRAL-SITE"


def test_nickname_only_titles_still_join_to_the_authority():
    """Polymarket titles an NHL club `Capitals`; ESPN says `Washington Capitals`.
    Exact equality matches none of those rows, and the miss reads as "ESPN does
    not list this fixture" — the quietest possible wrong answer."""
    repair = _load_repair()
    verdict, _ = repair.classify(
        _row("Capitals", "Hurricanes"),
        [_fixture(home="Carolina Hurricanes", away="Washington Capitals")],
        90, "icehockey_nhl",
    )
    assert verdict == "REVERSED"


# --------------------------------------------------------------------------
# League resolution — the step that decides how much of the defect is reached
# --------------------------------------------------------------------------

CLUBS = [
    {"league": "basketball_wnba", "name": "Connecticut Sun"},
    {"league": "basketball_wnba", "name": "Toronto Tempo"},
    {"league": "icehockey_nhl", "name": "Washington Capitals"},
    {"league": "icehockey_nhl", "name": "Carolina Hurricanes"},
    {"league": "icehockey_nhl", "name": "Los Angeles Kings"},
    {"league": "icehockey_nhl_preseason", "name": "Washington Capitals"},
    {"league": "icehockey_nhl_preseason", "name": "Carolina Hurricanes"},
]


def test_full_names_resolve():
    repair = _load_repair()
    assert repair.resolve_league(
        CLUBS, "Toronto Tempo", "Connecticut Sun") == "basketball_wnba"


def test_bare_nicknames_resolve():
    """Exact-on-`teams` left 493 of 500 production candidates UNRESOLVED and
    skipped every NHL row, because Polymarket titles them `Capitals vs.
    Hurricanes`. That reported as a clean run over a seventh of the defect."""
    repair = _load_repair()
    assert repair.resolve_league(CLUBS, "Capitals", "Hurricanes") is not None


def test_a_tie_between_leagues_sharing_one_scoreboard_still_resolves():
    """Every NHL club is carried twice, under `icehockey_nhl` AND
    `icehockey_nhl_preseason` (production: `Pittsburgh Penguins` is team 60 and
    team 19703). An "exactly one shared league" rule therefore resolves every
    NHL pair to nothing — the entire hockey half of this defect, skipped while
    the run reports clean. The tie is immaterial because both keys are
    away-first and both name `hockey/nhl`."""
    repair = _load_repair()
    shared = (repair.leagues_for_club(CLUBS, "Capitals")
              & repair.leagues_for_club(CLUBS, "Hurricanes"))
    assert len(shared) == 2
    assert {repair.ESPN_PATHS[lg] for lg in shared} == {"hockey/nhl"}
    assert repair.resolve_league(CLUBS, "Capitals", "Hurricanes") is not None


def test_a_tie_across_two_scoreboards_does_not_resolve():
    """The half of the tie rule that must NOT relax: if the shared leagues would
    send us to different ESPN scoreboards, there is no single authority to ask."""
    repair = _load_repair()
    clubs = CLUBS + [
        {"league": "basketball_wnba", "name": "Union Club"},
        {"league": "icehockey_nhl", "name": "Union Club"},
        {"league": "basketball_wnba", "name": "Harbor Club"},
        {"league": "icehockey_nhl", "name": "Harbor Club"},
    ]
    shared = (repair.leagues_for_club(clubs, "Union Club")
              & repair.leagues_for_club(clubs, "Harbor Club"))
    assert {repair.ESPN_PATHS[lg] for lg in shared} == {
        "basketball/wnba", "hockey/nhl"}
    assert repair.resolve_league(clubs, "Union Club", "Harbor Club") is None


def test_an_unknown_club_resolves_to_nothing():
    repair = _load_repair()
    assert repair.resolve_league(CLUBS, "Iwaki FC", "Ventforet Kofu") is None
    assert repair.resolve_league(CLUBS, "Connecticut Sun", "Iwaki FC") is None


def test_a_cross_league_pair_resolves_to_nothing():
    repair = _load_repair()
    assert repair.resolve_league(
        CLUBS, "Connecticut Sun", "Washington Capitals") is None


def test_apply_refuses_without_backup():
    """D51(b): the undo has to exist before the write does."""
    repair = _load_repair()
    source = REPAIR_PATH.read_text()
    assert "REFUSING: --apply requires --backup" in source
    assert repair.BACKUP_TABLE == "backup_event_orientation_7739"


# --------------------------------------------------------------------------
# The swap is a TRANSPOSITION — the half that turns a label bug into a price bug
# --------------------------------------------------------------------------

def test_a_clean_row_has_no_unhandled_reasons():
    repair = _load_repair()
    assert repair.unhandled_reasons({
        "has_score": False, "has_opening": False,
        "has_closing": False, "odds_snapshots": 0,
    }) == []


@pytest.mark.parametrize("field,expected", [
    ("has_score", "score"),
    ("has_opening", "opening-probability"),
    ("has_closing", "closing-probability"),
])
def test_orientation_dependent_data_blocks_the_swap(field, expected):
    """Every stored probability for a game is HOME-oriented. Renaming the clubs
    without moving them serves the market's price on the wrong club — a wrong
    label becomes a wrong number, which is strictly worse."""
    repair = _load_repair()
    row = {"has_score": False, "has_opening": False,
           "has_closing": False, "odds_snapshots": 0, field: True}
    assert repair.unhandled_reasons(row) == [expected]


def test_odds_snapshots_block_the_swap_and_are_counted():
    repair = _load_repair()
    reasons = repair.unhandled_reasons({
        "has_score": False, "has_opening": False,
        "has_closing": False, "odds_snapshots": 4,
    })
    assert reasons == ["4 odds snapshots"]


def test_the_swap_moves_the_price_with_the_names():
    """A source-scanning assertion, because the transposition is SQL.

    The event statement must invert `win_probability_sources.*.value` in the
    same statement that swaps the names, and the snapshot statement must swap
    home/away. Specimen 15310072 stores 0.585 against `Toronto Tempo` as home;
    after the swap Connecticut Sun is home and the stored value must read 0.415.
    """
    source = REPAIR_PATH.read_text()
    swap = source.split("SWAP_EVENT_SQL = ")[1].split('"""')[1]
    assert "home_team_name = away_team_name" in swap
    assert "away_team_name = home_team_name" in swap
    assert "win_probability_sources" in swap
    assert "1 - (val ->> 'value')::numeric" in swap

    snaps = source.split("SWAP_SNAPSHOTS_SQL = ")[1].split('"""')[1]
    assert "home_win_probability = away_win_probability" in snaps
    assert "away_win_probability = home_win_probability" in snaps


def test_the_backup_carries_the_probabilities_it_rewrites():
    """A backup of the names alone cannot undo a transposition of the prices."""
    source = REPAIR_PATH.read_text()
    create = source.split(f"CREATE TABLE IF NOT EXISTS {{BACKUP_TABLE}} (")[1]
    assert "win_probability_sources jsonb" in create.split(")")[0]
