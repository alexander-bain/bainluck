"""Guard: an unmapped `*_other` row and its real-league twin are ONE card (#2866).

THE PAGE THIS EXISTS FOR. `bainluck.com/search?q=Ajax`, 390px, 2026-09-14
03:44Z (authority/197). Ajax v Willem II on 2026-09-15 drew two cards — one
priced 91/9 and one saying "No price yet". The rows:

    15297733  soccer_netherlands_eredivisie  odds_api  18:00Z  external_id set
    15307699  soccer_other                   kalshi    21:00Z  no ids

Toluca v Santos Laguna (`15312342` × `15307702`) and América v Guadalajara
(`15311465` × `15307709`) are the same shape on Liga MX.

WHY EVERY OTHER GUARD IN THIS MODULE LET THEM THROUGH. #5905's recovery already
pulls the Kalshi row back three hours, so at serve time both rows sit at the
SAME MINUTE and their squashed club names are byte-identical — elements 1–3 of
`twin_fold_key` already match. Only element 0 differs, and rung one of #2866
cannot close it: `league_identity` promises an unmapped key falls back to
itself so it never SPLITS a group, and neither `soccer_other` nor
`soccer_netherlands_eredivisie` is in `SPORT_LEAGUE_MAP`. Both map to
themselves. Rung one is right and it is not sufficient.

WHAT EACH TEST HERE DEFENDS — the ways this repair could reach a reader as a
worse page than two cards:

* it never fires, because the catch-all licence was not actually consulted
  (`test_the_ajax_pair_folds_to_one_card`, with the strawman
  `test_with_no_sport_loaded_the_pair_still_serves_two_cards`);
* 🔴 it fires ACROSS SPORTS and merges the 65-pair cross-sport population the
  census found beside the 9 — `test_a_catch_all_never_folds_into_another_sport`
  and `test_the_baseball_other_esports_population_stays_two_cards`, which are
  the load-bearing pair in this file;
* it folds two REAL leagues into each other, which no catch-all licence may
  ever do (`test_two_real_leagues_are_never_folded`);
* it folds two CATCH-ALLS of different sports (`test_two_catch_alls_never_fold`);
* it guesses when a fixture is claimed by two different real leagues
  (`test_an_ambiguous_fixture_is_refused_whole`);
* it eats a second real game between the same clubs
  (`test_a_different_minute_keeps_its_own_card`);
* it quietly changes who survives, costing a reader a score or a price
  (`test_the_row_with_the_score_survives`,
  `test_a_priced_catch_all_still_beats_an_unpriced_league_row`);
* it stops the surviving card naming its competition where nothing else
  separates the rows (`test_the_row_that_names_its_league_wins_an_otherwise_tie`).

THE POPULATION, measured all-time on production 2026-09-14 over the whole
`events` table, on the clock the fold actually uses: 9 fixtures — 6 soccer and
3 esports — and ZERO for every other catch-all (baseball, tennis, basketball,
americanfootball, cricket, rugby, icehockey, mma, motorsport, aussierules,
golf). Driving `fold_twin_events` itself over the 1,554 soccer rows a reader can
reach in `[now-3d, now+8d]`: master folds 75, this folds 79, 0 lost. Both
false-fold controls clean over all 9 — no pair holds two scorelines, none holds
two `espn_id`s.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events, twin_identity_rank
from app.utils.kalshi_occurrence_start import KALSHI_EXPECTED_EXPIRATION_PAD

KICKOFF = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)

#: What a Kalshi-sourced soccer row stores INSTEAD of the kick-off — the
#: market's expected expiration. Imported rather than retyped so this file
#: cannot drift from the recovery it depends on (#5905).
KALSHI_EXPIRATION_PAD = KALSHI_EXPECTED_EXPIRATION_PAD

#: Production `sport_id`s are unequal for the two rows of every pair here —
#: that is the whole defect, so the doubles must not share one by accident.
EREDIVISIE_SPORT_ID = 4011
SOCCER_OTHER_SPORT_ID = 9901
LIGAMX_SPORT_ID = 4044


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Not a MagicMock, for the reason #5918's file gives: an auto-attribute mock
    makes every `espn_id` truthy and every `sport.key` a string by accident,
    and this file would then pass with the catch-all licence deleted.
    `sport_key=None` leaves `Event.sport` genuinely absent, which is what an
    unloaded relationship looks like to `loaded_sport_key`.
    """

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport_key,
        sport_id,
        commence_time=KICKOFF,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        commence_time_source="odds_api",
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


def _ajax_pair(*, sport_loaded=True):
    """The production specimen: `15297733` (Eredivisie) × `15307699` (catch-all).

    The catch-all row is stored THREE HOURS LATE, exactly as production holds
    it: `15307699` carries Kalshi's expected expiration (21:00Z) where the
    kick-off (18:00Z) belongs. #5905's recovery runs at the top of
    `fold_twin_events` and pulls it back, which is what puts the two rows in one
    minute for the league element to then be the only thing separating them.
    Handing both rows the same stored time would be a double that cannot fail
    the way production does. The Eredivisie row carries the Odds API's provider
    id and the catch-all row carries none, true of every soccer pair measured.
    """
    league = _Row(
        15297733,
        "Ajax",
        "Willem II",
        sport_key="soccer_netherlands_eredivisie" if sport_loaded else None,
        sport_id=EREDIVISIE_SPORT_ID,
        external_id="358980e06a390b57047eaf81a00169af",
    )
    catchall = _Row(
        15307699,
        "Ajax",
        "Willem II",
        sport_key="soccer_other" if sport_loaded else None,
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time=KICKOFF + KALSHI_EXPIRATION_PAD,
        commence_time_source="kalshi",
    )
    return league, catchall


def test_the_ajax_pair_folds_to_one_card():
    """The defect, exactly as photographed: two cards become one."""
    league, catchall = _ajax_pair()

    result = fold_twin_events([league, catchall])

    assert _ids(result) == [15297733]
    assert result.dropped_ids == [15307699]
    assert result.survivor_of == {15307699: 15297733}


def test_with_no_sport_loaded_the_pair_still_serves_two_cards():
    """The strawman. This is master's behaviour and it must stay the behaviour.

    A caller that did not `selectinload(Event.sport)` cannot be told which key
    is a catch-all, so the pass has nothing it is licensed to say. If this ever
    goes green the licence has stopped reading the sport key and is folding on
    names and a minute alone.
    """
    league, catchall = _ajax_pair(sport_loaded=False)

    result = fold_twin_events([league, catchall])

    assert _ids(result) == [15297733, 15307699]
    assert result.dropped_ids == []


def test_a_catch_all_never_folds_into_another_sport():
    """🔴 The guard the whole licence rests on.

    `basketball_other` × `baseball_npb` is a real production pair (`14986708` /
    `15180822`): same squashed names, same minute, two different sports. The
    prefix test is the only thing refusing it.
    """
    hoops = _Row(
        14986708,
        "Yomiuri Giants",
        "Hanshin Tigers",
        sport_key="basketball_other",
        sport_id=7701,
    )
    baseball = _Row(
        15180822,
        "Yomiuri Giants",
        "Hanshin Tigers",
        sport_key="baseball_npb",
        sport_id=5502,
    )

    result = fold_twin_events([hoops, baseball])

    assert _ids(result) == [14986708, 15180822]
    assert result.dropped_ids == []


def test_the_baseball_other_esports_population_stays_two_cards():
    """The 59-pair population, the largest this pass could have swallowed.

    `baseball_other` rows pair with `esports` rows on names and the minute 59
    times in a 90-day window. They are a classification defect somebody else
    owns; folding them would put a Counter-Strike match on a baseball card.
    """
    rows = []
    for index in range(6):
        minute = KICKOFF + timedelta(hours=index)
        rows.append(
            _Row(
                14971934 + index,
                f"Team Spirit {index}",
                f"Natus Vincere {index}",
                sport_key="baseball_other",
                sport_id=5599,
                commence_time=minute,
            )
        )
        rows.append(
            _Row(
                15167563 + index,
                f"Team Spirit {index}",
                f"Natus Vincere {index}",
                sport_key="esports",
                sport_id=8800,
                commence_time=minute,
            )
        )

    result = fold_twin_events(rows)

    assert result.dropped_ids == []
    assert len(_ids(result)) == 12


def test_two_real_leagues_are_never_folded():
    """No catch-all, no licence — even for one fixture at one minute.

    This is the men's/women's class in general form: `cricket_the_hundred` and
    `cricket_the_hundred_womens` field clubs of the same name and 19 such pairs
    exist. Requiring exactly one side to be `*_other` is what excludes them.
    """
    mens = _Row(
        1,
        "Oval Invincibles",
        "Southern Brave",
        sport_key="cricket_the_hundred",
        sport_id=3301,
    )
    womens = _Row(
        2,
        "Oval Invincibles",
        "Southern Brave",
        sport_key="cricket_the_hundred_womens",
        sport_id=3302,
    )

    result = fold_twin_events([mens, womens])

    assert _ids(result) == [1, 2]
    assert result.dropped_ids == []


def test_two_catch_alls_never_fold():
    """Two unmapped keys say nothing about each other, whatever the sport.

    `americanfootball_other` and `baseball_other` pair constantly on names and
    minutes and are different sports; neither names a league the other could be
    folded into.
    """
    gridiron = _Row(
        3, "Alpha", "Beta", sport_key="americanfootball_other", sport_id=6601
    )
    ball = _Row(4, "Alpha", "Beta", sport_key="baseball_other", sport_id=5599)

    result = fold_twin_events([gridiron, ball])

    assert _ids(result) == [3, 4]
    assert result.dropped_ids == []


def test_an_ambiguous_fixture_is_refused_whole():
    """Two real leagues claim one fixture — the catch-all cannot pick, so nothing moves.

    Refused WHOLE, the way `_name_clusters` discards a non-clique: three cards
    is today's behaviour and is honest, where folding into either league would
    be a guess presented as a fact.
    """
    catchall = _Row(
        5, "Ajax", "Willem II", sport_key="soccer_other", sport_id=SOCCER_OTHER_SPORT_ID
    )
    eredivisie = _Row(
        6,
        "Ajax",
        "Willem II",
        sport_key="soccer_netherlands_eredivisie",
        sport_id=EREDIVISIE_SPORT_ID,
    )
    cup = _Row(
        7,
        "Ajax",
        "Willem II",
        sport_key="soccer_netherlands_knvb_beker",
        sport_id=4012,
    )

    result = fold_twin_events([catchall, eredivisie, cup])

    assert _ids(result) == [5, 6, 7]
    assert result.dropped_ids == []


def test_a_different_minute_keeps_its_own_card():
    """The clock is untouched by this pass: exact-minute equality still decides.

    Two fixtures between one pair of clubs on one day are two games, and the
    catch-all licence must not become a way around that.
    """
    league, catchall = _ajax_pair()
    catchall.commence_time = KICKOFF + KALSHI_EXPIRATION_PAD + timedelta(minutes=1)

    result = fold_twin_events([league, catchall])

    assert _ids(result) == [15297733, 15307699]
    assert result.dropped_ids == []


def test_the_row_with_the_score_survives():
    """Daejeon v Pohang: the league row is Final 2–2, the catch-all is suspended.

    A fold that served the scoreless row would be a worse page than two cards,
    which is rule 1 of `twin_identity_rank` and must outrank everything here.
    """
    league = _Row(
        15305024,
        "Daejeon Citizen",
        "Pohang Steelers",
        sport_key="soccer_korea_kleague1",
        sport_id=4077,
        home_score=2,
        away_score=2,
        external_id="358980e06a390b57047eaf81a00169af",
    )
    catchall = _Row(
        15307887,
        "Daejeon Citizen",
        "Pohang Steelers",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time=KICKOFF + KALSHI_EXPIRATION_PAD,
        commence_time_source="kalshi",
    )

    result = fold_twin_events([league, catchall])

    assert _ids(result) == [15305024]
    assert result.survivor_of == {15307887: 15305024}


def test_a_priced_catch_all_still_beats_an_unpriced_league_row():
    """The World Cup pairs — the case where naming your league correctly LOSES.

    `14900527` (`soccer_other`) holds the only Polymarket price and `15168069`
    (`soccer_fifa_world_cup`) holds no venues at all, so source count decides one
    rung above the league criterion and the catch-all row survives. A reader
    keeps the number and loses a label, never the reverse — pinned here so
    nobody promotes the league criterion above the price later.
    """
    catchall = _Row(
        14900527,
        "Australia",
        "Turkiye",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time_source="kalshi",
        sources={"polymarket": 0.9995},
    )
    world_cup = _Row(
        15168069,
        "Australia",
        "Turkiye",
        sport_key="soccer_fifa_world_cup",
        sport_id=4099,
        commence_time_source="kalshi",
    )

    result = fold_twin_events([catchall, world_cup])

    assert _ids(result) == [14900527]
    assert result.survivor_of == {15168069: 14900527}


def test_the_row_that_names_its_league_wins_an_otherwise_tie():
    """The three `esports_other × esports` pairs, where everything above ties.

    No score, no `espn_id`, no provider id and no venues on either side, so
    before this criterion the lower row id won and the surviving card was filed
    under a catch-all. Measured on `14977192` / `15170329`.
    """
    catchall = _Row(
        14977192,
        "G2 Esports",
        "Twisted Minds",
        sport_key="esports_other",
        sport_id=8899,
        commence_time_source="kalshi",
    )
    named = _Row(
        15170329,
        "G2 Esports",
        "Twisted Minds",
        sport_key="esports",
        sport_id=8800,
        commence_time_source="kalshi",
    )

    result = fold_twin_events([catchall, named])

    assert _ids(result) == [15170329]
    assert result.survivor_of == {14977192: 15170329}


def test_the_league_criterion_cannot_outrank_a_venues_price():
    """The ordering itself, asserted directly rather than through a fold.

    `twin_identity_rank` is a tuple and the whole safety of the new element is
    where it sits: below source count, above the row id. A rank that put it
    higher would serve label over number.
    """
    priced_catchall = _Row(
        1,
        "Alpha",
        "Beta",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        sources={"polymarket": 0.5},
    )
    bare_league = _Row(
        2, "Alpha", "Beta", sport_key="soccer_mexico_ligamx", sport_id=LIGAMX_SPORT_ID
    )

    assert twin_identity_rank(priced_catchall) > twin_identity_rank(bare_league)


def test_the_league_criterion_outranks_the_row_id():
    """The other side of the same ordering, so the element is not inert."""
    low_id_catchall = _Row(
        1, "Alpha", "Beta", sport_key="soccer_other", sport_id=SOCCER_OTHER_SPORT_ID
    )
    high_id_league = _Row(
        99, "Alpha", "Beta", sport_key="soccer_mexico_ligamx", sport_id=LIGAMX_SPORT_ID
    )

    assert twin_identity_rank(high_id_league) > twin_identity_rank(low_id_catchall)


def test_a_lone_catch_all_row_is_left_exactly_as_it_is():
    """Most `*_other` rows have no twin at all — 21,797 of them in soccer alone.

    The pass must be inert on them: no drop, no reorder, no election.
    """
    rows = [
        _Row(
            10 + index,
            f"Club {index}",
            f"Rival {index}",
            sport_key="soccer_other",
            sport_id=SOCCER_OTHER_SPORT_ID,
            commence_time=KICKOFF + timedelta(hours=index),
        )
        for index in range(5)
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [10, 11, 12, 13, 14]
    assert result.dropped_ids == []


def test_the_catch_all_pass_unions_a_group_the_soccer_name_pass_already_made():
    """América v Guadalajara: the two relaxations compose, and that is by design.

    `América` and `America` are two SPELLINGS, so the strict key separates them
    and #5918's soccer pass is what brings them together; the league element is
    still `soccer_other` against `soccer_mexico_ligamx`, so this pass is what
    finishes the job. Neither closes it alone — the SQL census missed this pair
    entirely because it had no `unaccent`, and only the driven run found it.
    """
    league = _Row(
        15311465,
        "América",
        "Guadalajara",
        sport_key="soccer_mexico_ligamx",
        sport_id=LIGAMX_SPORT_ID,
        external_id="c8513bd1",
    )
    catchall = _Row(
        15307709,
        "America",
        "Guadalajara",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time=KICKOFF + KALSHI_EXPIRATION_PAD,
        commence_time_source="kalshi",
    )

    result = fold_twin_events([league, catchall])

    assert _ids(result) == [15311465]
    assert result.survivor_of == {15307709: 15311465}


def test_a_half_loaded_pair_says_nothing_and_does_not_crash(caplog):
    """One row's sport loaded, the other's not — the pass must abstain, quietly.

    Closes a mutant that survived the first pass of this file: deleting the
    `if not sport_key: continue` arm left an unloaded row classified as a
    LEAGUE row carrying a `None` key, which then meets `key.startswith(prefix)`
    and raises.

    🔴 THE ROW ASSERTION ALONE CANNOT SEE THAT, which is the whole reason the
    log assertion is here. The raise happens inside a stage wrapped in a bare
    `except` (gotcha #42), so the fold catches it, serves the groups it already
    had, and the page looks EXACTLY like a correct abstention — two cards,
    either way. The difference is that the broken version has silently switched
    the entire catch-all pass off for every other fixture in the same request.
    So this asserts the pass declined on purpose rather than by crashing.
    """
    league, catchall = _ajax_pair()
    del league.sport  # the caller loaded `Event.sport` for one row only

    with caplog.at_level(logging.ERROR, logger="app.utils.event_twin_fold"):
        result = fold_twin_events([league, catchall])

    assert _ids(result) == [15297733, 15307699]
    assert result.dropped_ids == []
    assert "catch-all league merge failed" not in caplog.text


def test_a_reversed_fixture_keeps_its_own_card():
    """Orientation is part of the identity, exactly as it is in the strict key.

    Closes a mutant that sorted the two club names before comparing them, which
    reads as harmless and is not: `twin_fold_key` is `(league, away, home,
    minute)` and #5918's name pass keeps orientation on purpose. A row pair that
    disagrees about who is at home is not proven to be one fixture, so it fails
    CLOSED to two cards.
    """
    league = _Row(
        15297733,
        "Ajax",
        "Willem II",
        sport_key="soccer_netherlands_eredivisie",
        sport_id=EREDIVISIE_SPORT_ID,
        external_id="358980e06a390b57047eaf81a00169af",
    )
    reversed_catchall = _Row(
        15307699,
        "Willem II",
        "Ajax",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time=KICKOFF + KALSHI_EXPIRATION_PAD,
        commence_time_source="kalshi",
    )

    result = fold_twin_events([league, reversed_catchall])

    assert _ids(result) == [15297733, 15307699]
    assert result.dropped_ids == []


def test_one_sport_answers_once_even_when_a_row_did_not_load_it():
    """Two rows of one `sport_id` can never disagree about being a catch-all.

    The pass resolves `{sport_id: sport key}` ONCE, the way `_league_identities`
    does and for the same reason. `15307699`'s sport is not loaded here, but
    another `soccer_other` row in the same batch answered for that `sport_id`,
    and a `sports` row has exactly one key — so the fixture still folds.

    Closes a mutant that swapped the map for a per-ROW `loaded_sport_key`. It
    reads as a pure tidy-up and is not: it also makes the pass abstain whenever
    the row it happens to ask is the one whose relationship a caller left cold,
    on top of costing a SQLAlchemy `inspect()` per row instead of per sport.

    The catch-all row here is deliberately NOT Kalshi-timed. #5905's recovery
    reads the sport key per row and has no batch map of its own, so a
    Kalshi-timed row with a cold relationship never gets its three hours back
    and could never reach the same minute as its twin whatever this pass does —
    it would test the recovery's limit rather than the map.
    """
    league, catchall = _ajax_pair()
    del catchall.sport  # this row did not load it...
    catchall.commence_time = KICKOFF
    catchall.commence_time_source = "odds_api"
    sibling = _Row(
        15307700,
        "Feyenoord",
        "PSV",
        sport_key="soccer_other",  # ...but this row of the same sport did
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time=KICKOFF + timedelta(days=1),
    )

    result = fold_twin_events([league, catchall, sibling])

    assert _ids(result) == [15297733, 15307700]
    assert result.survivor_of == {15307699: 15297733}


def test_a_catch_all_cluster_reaching_two_leagues_is_refused_whole():
    """The only path by which two REAL leagues could land on one card.

    #5918's soccer pass can build one cluster out of two spellings of a
    fixture. If each spelling then finds its own league twin in a DIFFERENT
    cluster, union-find would join all three and put two competitions on one
    card — the thing this pass promises never to do.

    Here `Ajax`/`AFC Ajax` are one catch-all cluster after the name pass, and
    they meet an Eredivisie row and a KNVB Cup row sitting in separate clusters.
    Refused whole: four cards, which is honest, rather than one that has
    silently merged two competitions.
    """
    eredivisie = _Row(
        20,
        "Ajax",
        "Willem II",
        sport_key="soccer_netherlands_eredivisie",
        sport_id=EREDIVISIE_SPORT_ID,
        external_id="a1",
    )
    cup = _Row(
        21,
        "AFC Ajax",
        "Willem II",
        sport_key="soccer_netherlands_knvb_beker",
        sport_id=4012,
        external_id="a2",
    )
    catchall_short = _Row(
        22,
        "Ajax",
        "Willem II",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
    )
    catchall_long = _Row(
        23,
        "AFC Ajax",
        "Willem II",
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
    )

    result = fold_twin_events([eredivisie, cup, catchall_short, catchall_long])

    # The two real leagues must BOTH still be served — whatever the pass does
    # with the catch-all rows, it may never put 20 and 21 on one card.
    assert 20 in _ids(result)
    assert 21 in _ids(result)
