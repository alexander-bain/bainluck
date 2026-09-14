"""Guard: a `*_other` row that SHORTENS its club names is still one card (#2866 rung 3).

THE PAGE THIS EXISTS FOR. `bainluck.com/search?q=Ajax`, 390px, 2026-09-14
06:07Z (lane1/312, `artifacts-lane1-312/search-ajax-rung2-live-0607Z.png`).
Rung two had just gone live and closed Ajax v Willem II, so that fixture drew
one priced card. Directly beneath it the same page drew:

    DUTCH EREDIVISIE   Sep 12  FINAL   1 – 5   Fortuna Sittard v Ajax
    OTHER SOCCER               No result reported  Sittard v Ajax

One game. Two cards. The second is `15307863`, `soccer_other`, `suspended`, no
score and no `espn_id`; the first is `15297730`, Eredivisie, `completed` 1–5.

WHY RUNG TWO CANNOT REACH IT, WHICH IS THE WHOLE REASON THIS FILE EXISTS. Rung
two pairs a catch-all with a league row on the exact fixture IDENTITY —
`twin_fold_key` elements 1–3, the SQUASHED club names and the minute. `Sittard`
and `Fortuna Sittard` do not squash alike, so no identity matches and rung two
never looks at the pair. `_merge_soccer_name_variants` is the pass that owns
"same fixture, different spelling" and it cannot see them either: its bucket is
`(league, date)`, and since rung one made element 0 the LEAGUE the two rows sit
in different buckets and are never asked the name question at all.

🔴 WHY THE OBVIOUS FIX — DROP THE LEAGUE FROM THAT BUCKET — IS THE DANGEROUS
ONE, and the reason `test_a_named_reserve_side_never_folds_onto_the_senior_card`
is the load-bearing test in this file. `soccer_pair_matches` states its own
residual: a reserve side with its own NAME is not caught, so `Ajax` matches
`Jong Ajax Amsterdam` (measured True). Within a league that is harmless, since
a club's senior and reserve sides are not in one competition. An unmapped key
is precisely where reserve and amateur sides land, and the very page above
carries FOUR `Jong Ajax Amsterdam` rows and one `Ajax Amateurs` row in
`soccer_other`. Widening the name pass's bucket would fold those onto the
senior Ajax card. This pass keeps the league separation everywhere except where
one side is a catch-all making no competition claim, and refuses the named-squad
shape outright.

THE POPULATION, measured 2026-09-14 06:3xZ by DRIVING `fold_twin_events` itself
over the 1,559 reader-reachable soccer rows in `[now-3d, now+8d]`: master folds
80, this folds 98 — **18 newly folded, 0 lost**. All 18 are listed by name in
`test_the_measured_population_folds_and_the_catch_all_is_what_goes` and every
one was read by hand against its survivor: two rows of one fixture, across
Eredivisie, K League, Liga MX, Ligue 2, Brazilian Série B and German Liga 3.
The catch-all is the row dropped in all 18, so no reader loses a score or a
competition name.

A SQL census over a wider 150d/60d window is deliberately NOT the number quoted
here, and the gap is the lesson rung two's own docstring records. That census
narrowed candidates with a substring containment test and found 19 name-variant
pairs; the predicate this pass actually uses is a TOKEN SUBSET, which is
strictly more permissive, so the census missed five real pairs that the driven
run caught — `GA Eagles` × `Go Ahead Eagles`, `Bucheon` × `Bucheon FC 1995`,
`America FC` × `América Mineiro` twice, and `Hoffenheim II` × `TSG Hoffenheim
II`. A census instrument that is not the code is a lower bound, never the
population; the driven run is the measurement of record.

Both objective false-fold controls are clean over the whole population: no pair
holds two scorelines, no pair holds two `espn_id`s, and not one catch-all row
carries either — the ghost beside the FINAL is the whole shape.

`Hoffenheim II` × `TSG Hoffenheim II` is worth its own sentence because it reads
at a glance like the thing this file refuses: it is the RESERVE side on BOTH
sides of the fold, in Liga 3, which is where Hoffenheim's reserves play. A squad
marker shared by both rows is agreement, not a conflict — what
`test_a_named_reserve_side_never_folds_onto_the_senior_card` forbids is a marker
on ONE side only.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events
from app.utils.kalshi_occurrence_start import KALSHI_EXPECTED_EXPIRATION_PAD

KICKOFF = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)

#: Imported rather than retyped so this file cannot drift from the recovery it
#: depends on (#5905): a Kalshi-sourced soccer row STORES the market's expected
#: expiration, and the fold pulls it back to the kick-off before keying.
KALSHI_EXPIRATION_PAD = KALSHI_EXPECTED_EXPIRATION_PAD

EREDIVISIE_SPORT_ID = 4011
SOCCER_OTHER_SPORT_ID = 9901
LA_LIGA_SPORT_ID = 4022
ESPORTS_SPORT_ID = 7001


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Not a MagicMock, for the reason #5918's file gives and rung two's repeats:
    an auto-attribute mock makes every `espn_id` truthy and every `sport.key` a
    string by accident, and this file would then pass with the whole pass
    deleted. `sport_key=None` leaves `Event.sport` genuinely absent, which is
    what an unloaded relationship looks like to `loaded_sport_key`.
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
        status="scheduled",
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
        self.status = status
        self.win_probability_sources = sources


def _ids(result):
    return [row.id for row in result.events]


def _catchall(id, home, away, *, sport_key="soccer_other", sport_id=None, **kwargs):
    """A Kalshi-minted catch-all row, stored three hours late as production holds it."""
    return _Row(
        id,
        home,
        away,
        sport_key=sport_key,
        sport_id=SOCCER_OTHER_SPORT_ID if sport_id is None else sport_id,
        commence_time=kwargs.pop("commence_time", KICKOFF) + KALSHI_EXPIRATION_PAD,
        commence_time_source="kalshi",
        external_id=None,
        **kwargs,
    )


def _league(id, home, away, *, sport_key="soccer_netherlands_eredivisie", sport_id=None, **kwargs):
    return _Row(
        id,
        home,
        away,
        sport_key=sport_key,
        sport_id=EREDIVISIE_SPORT_ID if sport_id is None else sport_id,
        external_id=f"odds-{id}",
        **kwargs,
    )


def _sittard_pair():
    """The production specimen: `15297730` (Eredivisie, 1–5 FINAL) × `15307863`."""
    return [
        _league(
            15297730,
            "Fortuna Sittard",
            "Ajax",
            home_score=1,
            away_score=5,
            status="completed",
        ),
        _catchall(15307863, "Sittard", "Ajax", status="suspended"),
    ]


def test_the_sittard_pair_folds_to_one_card():
    """The photographed defect: a FINAL and a 'No result reported' ghost become one."""
    result = fold_twin_events(_sittard_pair())

    assert _ids(result) == [15297730]
    assert result.dropped_ids == [15307863]


def test_the_row_holding_the_score_and_the_competition_survives():
    """A reader must not lose the 1–5 or the league name to the fold."""
    survivor = fold_twin_events(_sittard_pair()).events[0]

    assert (survivor.home_score, survivor.away_score) == (1, 5)
    assert survivor.sport.key == "soccer_netherlands_eredivisie"


def test_with_no_sport_loaded_the_pair_still_serves_two_cards():
    """The strawman: with `Event.sport` absent the pass must decline, not guess.

    Without this a caller that forgets `selectinload(Event.sport)` would get a
    silently different page, and every other test here would pass on a pass
    that had been deleted.
    """
    rows = _sittard_pair()
    for row in rows:
        del row.sport

    assert len(fold_twin_events(rows).events) == 2


def test_a_named_reserve_side_never_folds_onto_the_senior_card():
    """🔴 THE LOAD-BEARING REFUSAL. `Ajax` matches `Jong Ajax Amsterdam`.

    `soccer_pair_matches` returns True for this pair — its documented residual —
    and `soccer_other` is exactly where a reserve fixture lands. Folding here
    would put a reserve game and a senior game on one card.
    """
    rows = [
        _league(1, "Ajax", "Utrecht"),
        _catchall(2, "Jong Ajax Amsterdam", "Utrecht"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_an_amateur_side_never_folds_onto_the_senior_card():
    """`Ajax Amateurs` sits in `soccer_other` on the same production page."""
    rows = [
        _league(1, "Ajax", "Feyenoord"),
        _catchall(2, "Ajax Amateurs", "Feyenoord"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_a_fixture_claimed_by_two_real_leagues_is_refused_whole():
    """`Madrid` is a subset of both Madrid clubs; the pass may never pick one."""
    rows = [
        _league(1, "Real Madrid", "Getafe", sport_key="soccer_spain_la_liga", sport_id=LA_LIGA_SPORT_ID),
        _league(3, "Atletico Madrid", "Getafe", sport_key="soccer_spain_la_liga", sport_id=LA_LIGA_SPORT_ID),
        _catchall(2, "Madrid", "Getafe"),
    ]

    assert len(fold_twin_events(rows).events) == 3


def test_one_league_row_claimed_by_two_catch_alls_is_refused_whole():
    """The ambiguity read from the other end — union-find would join all three."""
    rows = [
        _league(1, "Fortuna Sittard", "Ajax"),
        _catchall(2, "Sittard", "Ajax"),
        _catchall(3, "Fortuna", "Ajax"),
    ]

    assert len(fold_twin_events(rows).events) == 3


def test_two_different_authority_ids_are_two_games():
    """One game, one `espn_id` (#2693) — so two of them can never be one card."""
    rows = [
        _league(1, "Fortuna Sittard", "Ajax", espn_id="4011"),
        _catchall(2, "Sittard", "Ajax", espn_id="4012"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_two_different_scorelines_are_two_games():
    """Folding these would have to throw one result away; neither is ours to discard."""
    rows = [
        _league(1, "Fortuna Sittard", "Ajax", home_score=1, away_score=5, status="completed"),
        _catchall(2, "Sittard", "Ajax", home_score=2, away_score=2, status="completed"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_a_catch_all_never_folds_into_another_sport():
    """The 65 cross-sport pairs rung two measured stay two cards.

    The name predicate measured itself on soccer boards; this pass is gated on
    the soccer prefix so those pairs are refused before it is ever consulted.
    """
    rows = [
        _Row(1, "Team Liquid", "G2", sport_key="esports", sport_id=ESPORTS_SPORT_ID),
        _catchall(2, "Team Liquid", "G2", sport_key="baseball_other"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_a_different_minute_keeps_its_own_card():
    """Two real fixtures between the same clubs are not one game."""
    rows = [
        _league(1, "Fortuna Sittard", "Ajax"),
        _catchall(2, "Sittard", "Ajax", commence_time=KICKOFF + timedelta(days=7)),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_clubs_that_merely_share_a_word_are_not_folded():
    """`Fortuna Sittard` and `Fortuna Dusseldorf` are different clubs."""
    rows = [
        _league(1, "Fortuna Sittard", "Ajax"),
        _catchall(2, "Fortuna Dusseldorf", "Ajax"),
    ]

    assert len(fold_twin_events(rows).events) == 2


def test_the_measured_population_folds_and_the_catch_all_is_what_goes():
    """The 19 production pairs, by name, driven through the real fold.

    Named rather than counted so a future reader can see WHICH fixtures this
    pass acts on, and so a regression names the league it broke. Every row here
    was read by hand against its survivor on 2026-09-14.

    Three shapes in this list are the reason simpler rules were rejected. The
    club-type prefixes (`SC`, `FC`, `AZ`, `NEC`, `ADO`, `TSG`) killed "the
    catch-all may not add tokens", which would refuse the real pairs that carry
    them. `GA Eagles` × `Go Ahead Eagles` and `Bucheon` × `Bucheon FC 1995`
    killed a substring-containment rule, which is what the first census used and
    what made it miss them. And `Hoffenheim II` × `TSG Hoffenheim II` is a
    reserve side folding onto the RIGHT reserve row — a squad marker on both
    sides is agreement, which is exactly what the named-squad refusal must not
    mistake for a conflict.
    """
    population = [
        ("soccer_korea_kleague1", "Gwangju", "FC Anyang", "Gwangju FC", "FC Anyang"),
        ("soccer_netherlands_eredivisie", "Heerenveen", "Telstar", "Heerenveen", "SC Telstar"),
        ("soccer_netherlands_eredivisie", "Excelsior", "Utrecht", "Excelsior", "FC Utrecht"),
        ("soccer_netherlands_eredivisie", "Zwolle", "Feyenoord", "FC Zwolle", "Feyenoord"),
        ("soccer_netherlands_eredivisie", "Eindhoven", "Sparta", "PSV Eindhoven", "Sparta Rotterdam"),
        ("soccer_brazil_serie_b", "America FC", "Sao Bernardo", "América Mineiro", "São Bernardo"),
        ("soccer_mexico_ligamx", "Juarez", "Tigres", "FC Juárez", "Tigres"),
        ("soccer_netherlands_eredivisie", "Cambuur", "Nijmegen", "SC Cambuur", "NEC Nijmegen"),
        ("soccer_netherlands_eredivisie", "Sittard", "Ajax", "Fortuna Sittard", "Ajax"),
        ("soccer_netherlands_eredivisie", "GA Eagles", "Groningen", "Go Ahead Eagles", "Groningen"),
        ("soccer_netherlands_eredivisie", "Enschede", "Den Haag", "FC Twente Enschede", "ADO Den Haag"),
        ("soccer_korea_kleague1", "Jeonbuk", "Seoul", "Jeonbuk Hyundai Motors", "FC Seoul"),
        ("soccer_korea_kleague1", "Bucheon", "Jeju SK", "Bucheon FC 1995", "Jeju United FC"),
        ("soccer_france_ligue_two", "Montpellier", "Pau", "Montpellier", "Pau FC"),
        ("soccer_netherlands_eredivisie", "Alkmaar", "Willem II", "AZ Alkmaar", "Willem II"),
        ("soccer_germany_liga3", "Hoffenheim II", "Fortuna Cologne", "TSG Hoffenheim II", "SC Fortuna Köln"),
        ("soccer_brazil_serie_b", "Vila Nova", "America FC", "Vila Nova", "América Mineiro"),
        ("soccer_netherlands_eredivisie", "Groningen", "Zwolle", "Groningen", "FC Zwolle"),
    ]

    assert len(population) == 18

    for index, (league_key, cat_home, cat_away, lg_home, lg_away) in enumerate(population):
        rows = [
            _league(
                1000 + index,
                lg_home,
                lg_away,
                sport_key=league_key,
                sport_id=5000 + index,
                home_score=1,
                away_score=0,
                status="completed",
            ),
            _catchall(2000 + index, cat_home, cat_away, status="suspended"),
        ]

        result = fold_twin_events(rows)

        assert _ids(result) == [1000 + index], f"{cat_home} v {cat_away} did not fold"
        assert result.dropped_ids == [2000 + index], (
            f"{cat_home} v {cat_away} dropped the league row, not the catch-all"
        )
