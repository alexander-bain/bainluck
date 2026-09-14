"""Guard: a preseason game and its regular-season twin are ONE card (#2866).

THE PAGE THIS EXISTS FOR. `bainluck.com/search?q=Chiefs`, 390px, 2026-09-14
03:30Z (authority/196). Three pairs adjacent on ONE screen, each pair the same
date and the same final score, one card badged **NFL** and one **NFL
PRESEASON**:

    Aug 28   9–9    Chiefs / Seahawks
    Aug 22   16–15  Buccaneers / Chiefs
    Aug 15   12–20  Chiefs / Rams

WHY THE FOLD THAT EXISTS WAS BLIND TO ALL 47 PAIRS. `twin_fold_key` was
`(sport_id, away, home, minute)`. On the driven specimen `15200299` / `15277456`
elements 1–3 are byte-identical and element 0 is `190411` against `1`, because
`americanfootball_nfl_preseason` and `americanfootball_nfl` are two `sports`
rows for ONE league (#1798). `fold_twin_events` returned `dropped_ids: []`.

WHAT EACH TEST HERE DEFENDS — the four ways this repair could reach a reader as
a worse page than two cards:

* it never fires, because the league element was not actually consulted
  (`test_the_chiefs_preseason_pair_folds_to_one_card`, and its strawman
  `test_with_no_sport_loaded_the_pair_still_serves_two_cards`, which is the
  behaviour on master and must stay the behaviour when nothing can answer);
* it fires too widely and merges two genuinely different sports that share a
  catch-all key and a team name — the 1,038-fixture population the census found
  beside the 47 (`test_two_catch_all_keys_are_not_one_league`);
* it SPLITS a group master folded, because two rows of one league answered the
  league question differently inside one request
  (`test_a_half_loaded_pair_still_folds`);
* it eats a second real game between the same two clubs
  (`test_a_second_game_the_same_day_keeps_its_own_card`).

THE POPULATION, measured on production 2026-09-14 by grouping every row on
squashed club names and the minute: 32 key combinations span two `sport_id`s,
and exactly ONE collapses under `league_identity` — NFL × NFL preseason, 47
fixtures. All-time across every season-variant family in the `sports` table the
total is 48, the extra being the MLB pair pinned below. Two objective
false-fold controls over the 47 are clean: no group holds two scorelines, and
no group holds two `espn_id`s.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_twin_fold import fold_twin_events, twin_fold_key

KICKOFF = datetime(2026, 8, 22, 23, 0, tzinfo=timezone.utc)

#: The two `sports` rows one NFL game is ingested under, with the ids the
#: production specimen carries — the point of the issue is that these differ.
NFL_SPORT_ID = 1
NFL_PRESEASON_SPORT_ID = 190411


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Deliberately not a MagicMock, for the reason #5918's file gives: an
    auto-attribute mock makes every `espn_id` truthy and every `sport.key` a
    string by accident, and this whole file would then pass with the league
    element deleted. `sport_key=None` leaves `Event.sport` genuinely absent,
    which is what an unloaded relationship looks like to `loaded_sport_key`.
    """

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport_key="americanfootball_nfl",
        sport_id=NFL_SPORT_ID,
        commence_time=KICKOFF,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        commence_time_source="espn",
        sources=None,
    ):
        self.id = id
        self.sport_id = sport_id
        if sport_key is not None:
            self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.win_probability_sources = sources


def _ids(result):
    return [row.id for row in result.events]


def _chiefs_pair(*, sport_loaded=True):
    """The Aug 22 specimen: `15200299` (regular) and `15277456` (preseason).

    Both rows carry the same `16–15` final, which is what makes them provably
    one game rather than two; the ESPN anchor sits on one of them only, which
    is true of all 47 pairs. `sport_loaded=False` is the unloaded-relationship
    case — the rows are otherwise identical.
    """
    regular = _Row(
        15200299,
        "Kansas City Chiefs",
        "Tampa Bay Buccaneers",
        sport_key="americanfootball_nfl" if sport_loaded else None,
        sport_id=NFL_SPORT_ID,
        home_score=15,
        away_score=16,
        espn_id="401773011",
        external_id="espn:401773011",
        sources={"espn": {"probability": 0.44}, "betting": {"probability": 0.47}},
    )
    preseason = _Row(
        15277456,
        "Kansas City Chiefs",
        "Tampa Bay Buccaneers",
        sport_key="americanfootball_nfl_preseason" if sport_loaded else None,
        sport_id=NFL_PRESEASON_SPORT_ID,
        home_score=15,
        away_score=16,
        sources={"kalshi": {"probability": 0.52}},
    )
    return regular, preseason


# ── the ship ────────────────────────────────────────────────────────────────


def test_the_chiefs_preseason_pair_folds_to_one_card():
    regular, preseason = _chiefs_pair()

    result = fold_twin_events([regular, preseason])

    assert _ids(result) == [15200299]
    assert result.dropped_ids == [15277456]
    assert result.survivor_of == {15277456: 15200299}


def test_the_surviving_card_keeps_the_price_only_the_preseason_row_held():
    """The fold merges, it never hides (#5918's rule, applied to this pair).

    On the measured pairs the Kalshi price sits on the preseason row and the
    ESPN anchor on the regular-season one, so dropping either row outright
    costs the reader something. The survivor must carry the union.
    """
    regular, preseason = _chiefs_pair()

    result = fold_twin_events([regular, preseason])

    assert result.merged_sources[15200299] == {
        "espn": {"probability": 0.44},
        "betting": {"probability": 0.47},
        "kalshi": {"probability": 0.52},
    }


def test_the_anchored_row_is_the_one_that_survives():
    """47 of 47 groups hold exactly one ESPN-anchored row, so this is decidable.

    Order is reversed here because a survivor that depends on the order the
    caller handed us the rows is a card whose `id` flickers between two polls.
    """
    regular, preseason = _chiefs_pair()

    assert _ids(fold_twin_events([preseason, regular])) == [15200299]


def test_the_may_23_mlb_pair_folds_on_the_same_rule():
    """The 48th fixture, and the only non-NFL one in the whole table.

    `14787332` (`baseball_mlb`, six venues, ESPN-anchored) and `9016349`
    (`baseball_mlb_preseason`, three venues, no anchor), both `4–9`, both
    2026-05-23 02:15Z. Pinned because it is the evidence that this repair is
    keyed on the season-variant RULE and not on a football special case.
    """
    stamp = datetime(2026, 5, 23, 2, 15, tzinfo=timezone.utc)
    regular = _Row(
        14787332,
        "San Francisco Giants",
        "Chicago White Sox",
        sport_key="baseball_mlb",
        sport_id=53232,
        commence_time=stamp,
        home_score=4,
        away_score=9,
        espn_id="401815453",
    )
    preseason = _Row(
        9016349,
        "San Francisco Giants",
        "Chicago White Sox",
        sport_key="baseball_mlb_preseason",
        sport_id=33178,
        commence_time=stamp,
        home_score=4,
        away_score=9,
    )

    assert _ids(fold_twin_events([regular, preseason])) == [14787332]


# ── the strawman: with nothing to answer the league question, master's page ──


def test_with_no_sport_loaded_the_pair_still_serves_two_cards():
    """The non-vacuity control, and a real contract.

    `loaded_sport_key` refuses to emit IO for an unloaded relationship
    (gotcha #42), so a caller that did not eager-load `Event.sport` gets the
    `sport_id` key this fold has always used — two cards, exactly as production
    serves today. If this test ever folds, the league element stopped being
    what fires the fold above and the ship is unmeasured.
    """
    regular, preseason = _chiefs_pair(sport_loaded=False)

    result = fold_twin_events([regular, preseason])

    assert _ids(result) == [15200299, 15277456]
    assert result.dropped_ids == []


def test_the_key_reads_the_league_without_a_batch_map():
    """`league_futures._twin_key_or_none` calls this per row, with no map.

    Element 0 must come from the row's own sport there, or the Final check on
    the league page's past rails would compare a league key against a
    `sport_id` and never match.
    """
    regular, preseason = _chiefs_pair()

    assert twin_fold_key(regular)[0] == "football/nfl"
    assert twin_fold_key(regular) == twin_fold_key(preseason)


def test_an_unmapped_key_is_exactly_as_discriminating_as_the_sport_id_was():
    """`sports.key` is UNIQUE, so an unknown key can only ever equal itself."""
    row = _Row(1, "A", "B", sport_key="americanfootball_other", sport_id=99)

    assert twin_fold_key(row)[0] == "americanfootball_other"


# ── the ways it must NOT widen ──────────────────────────────────────────────


def test_two_catch_all_keys_are_not_one_league():
    """The 1,038-fixture population sitting beside the 47 in the same census.

    `americanfootball_other` and `baseball_other` pair up constantly on names
    and minutes — 614 fixtures in 90 days — and they are different sports. A
    league element that collapsed unmapped keys would merge every one of them.
    """
    gridiron = _Row(
        1,
        "Dallas",
        "Houston",
        sport_key="americanfootball_other",
        sport_id=501,
        home_score=3,
        away_score=0,
    )
    ballpark = _Row(
        2,
        "Dallas",
        "Houston",
        sport_key="baseball_other",
        sport_id=502,
        home_score=3,
        away_score=0,
    )

    assert _ids(fold_twin_events([gridiron, ballpark])) == [1, 2]


def test_a_second_game_the_same_day_keeps_its_own_card():
    """Exact-minute equality is untouched, which is what bounds this repair.

    Two real games between one pair on one day — a doubleheader, a cup replay —
    are two groups because element 3 still demands the same minute, which #2866
    did not touch.
    """
    leg_one = _Row(
        1,
        "Chicago White Sox",
        "Detroit Tigers",
        sport_key="baseball_mlb",
        sport_id=53232,
        home_score=2,
        away_score=1,
    )
    leg_two = _Row(
        2,
        "Chicago White Sox",
        "Detroit Tigers",
        sport_key="baseball_mlb_preseason",
        sport_id=33178,
        commence_time=KICKOFF + timedelta(hours=4),
    )

    assert _ids(fold_twin_events([leg_one, leg_two])) == [1, 2]


def test_a_different_league_in_the_same_sport_never_folds():
    """Two clubs of the same name in two competitions stay two fixtures."""
    epl = _Row(
        1,
        "Newcastle",
        "Arsenal",
        sport_key="soccer_epl",
        sport_id=7,
        home_score=1,
        away_score=1,
    )
    cup = _Row(
        2,
        "Newcastle",
        "Arsenal",
        sport_key="soccer_england_efl_cup",
        sport_id=8,
        home_score=1,
        away_score=1,
    )

    assert _ids(fold_twin_events([epl, cup])) == [1, 2]


# ── the way it must NOT narrow ──────────────────────────────────────────────


@pytest.mark.parametrize("loaded_on", ["first", "second"])
def test_a_half_loaded_pair_still_folds(loaded_on):
    """A group master folds can never be SPLIT by this change.

    Two rows of one `sport_id` reach one fold from two queries — the league
    page hands it `[*upcoming, *results, *unreported]` — and only one of those
    queries needs to have eager-loaded `Event.sport` for a per-row league read
    to answer `football/nfl` for one row and `1` for the other. That would
    un-fold a pair production folds today, which is the same defect wearing the
    opposite sign. `_league_identities` is why it cannot: the map is keyed on
    `sport_id`, so both rows get the one answer the batch could find.
    """
    first = _Row(
        1,
        "Kansas City Chiefs",
        "Denver Broncos",
        sport_key="americanfootball_nfl" if loaded_on == "first" else None,
        home_score=21,
        away_score=17,
        espn_id="401773099",
    )
    second = _Row(
        2,
        "Kansas City Chiefs",
        "Denver Broncos",
        sport_key="americanfootball_nfl" if loaded_on == "second" else None,
        home_score=21,
        away_score=17,
        sources={"kalshi": {"probability": 0.61}},
    )

    result = fold_twin_events([first, second])

    assert _ids(result) == [1]
    assert result.dropped_ids == [2]


def test_a_wholly_unloaded_pair_of_one_sport_id_still_folds():
    """The other half of the same contract, and the reason it is not vacuous.

    With no row able to name the league, both fall back to `sport_id` — and
    because they share one, they still fold. This is the fold #4100 shipped and
    it must be byte-identical after #2866.
    """
    first = _Row(1, "Boston Red Sox", "New York Yankees", sport_key=None, espn_id="x")
    second = _Row(2, "Boston Red Sox", "New York Yankees", sport_key=None)

    assert _ids(fold_twin_events([first, second])) == [1]
