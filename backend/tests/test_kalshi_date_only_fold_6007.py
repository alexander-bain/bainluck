"""Guard: a Kalshi ticker's DATE stops posing as a kick-off (#6007).

THE PAGE THIS EXISTS FOR. `/sports/soccer_epl` at phone width, 2026-09-13
22:09Z. The Premier League page opened — above everything, in a section headed
"Live & Paused 3" — with three grey cards reading **"No result reported"**:

    Sunderland AFC v Arsenal FC          Liverpool FC v Fulham FC
    Coventry City v Brighton & Hove Albion

All three had been played. Their real cards were on the same page, eight rows
further down under "Finished 9", with scores: Sunderland 0–2 Arsenal, Liverpool
0–0 Fulham, Coventry 0–5 Brighton. The first two were the FIRST TWO ROWS the
payload served.

WHY THE EXISTING FOLD COULD NOT SEE THEM, AND WHY THAT IS NOT A BUG IN IT.
Those rows came from a Kalshi TICKER, which encodes a date and no hour
(gotcha #14), so each was stored at exactly midnight UTC:

    15310635  "Sunderland AFC" v "Arsenal FC"  2026-09-12 00:00:00Z  kalshi_ticker
    15297679  "Sunderland"     v "Arsenal"     2026-09-12 19:00:00Z  espn, 0–2

#5918 taught the fold these two spellings are one club pair, and it says so —
`soccer_pair_matches` already answers True for nine of the ten production pairs.
#5964 then made the clock a five-minute BOUND on provider disagreement. But
19 hours is not provider disagreement, so the bound refused every one of them.
The bound was right and the names were right; the mistake was asking a row that
never claimed an hour to agree about one.

So #6007 adds one exception, and only for rows that can be shown to have no
clock at all (:func:`is_kalshi_date_only`): the source names the ticker, and
midnight-UTC proves no hour was ever recovered on top of it. For those the
bucket's own `(sport_id, UTC date)` is the clock half and the club names carry
the decision — both clubs, orientation kept, squad-marker refusal, clique
refusal, soccer only. Nothing about any other row changes.

MEASURED by replaying this module over the 916 soccer rows a reader could reach
on 2026-09-13 (`tools/replay_6007_date_only_fold.py`, master vs this change):

    folded 57 -> 66     +9, and 0 rows master folded that this one does not
    all 9 new folds are kalshi_ticker midnight rows; nothing else moved
    every survivor is the completed, ESPN-anchored card with the real score
    false-fold audits over all 50 elected groups: 0 groups with two espn_ids,
        0 groups with two scorelines, 0 groups where the placeholder won

The four date-only rows it does NOT fold are honest misses, recorded so a later
reader does not mistake them for regressions: `Racing Club De Lens` v `RC Lens`
is a name the shared matcher does not yet join, and three rows (a Denver–Kansas
City MLS fixture and two Brazilian ones) have no counterpart row to fold into.

**Update, #6022:** the first of those four is closed. `Racing Club De Lens` is a
whole-name entry in `soccer_team_matching.CLUB_NAME_ALIASES` now, so the Ligue 1
pair below folds on the same exception this file tests. The other three stand —
they have no counterpart row, which no name rule can invent.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    SOCCER_KICKOFF_DRIFT,
    fold_twin_events,
    is_kalshi_date_only,
)

MIDNIGHT = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 12, 19, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock, for the reason #5918's file gives: an
    auto-attribute mock makes every `espn_id` truthy, every `sport.key` a soccer
    key and every `commence_time_source` a ticker by accident, so this whole
    file would pass with the exception deleted.
    """

    def __init__(
        self,
        row_id,
        home,
        away,
        commence_time=None,
        commence_time_source=None,
        sport_id=1316,
        sport_key="soccer_epl",
        espn_id=None,
        external_id=None,
        home_score=None,
        away_score=None,
        sources=None,
    ):
        self.id = row_id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time or KICKOFF
        self.commence_time_source = commence_time_source
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.espn_id = espn_id
        self.external_id = external_id
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = sources


def _ids(result):
    return sorted(event.id for event in result.events)


def _placeholder(row_id=15310635, home="Sunderland AFC", away="Arsenal FC", **kw):
    """Production's phantom row: a ticker date with midnight stapled on."""
    kw.setdefault("commence_time", MIDNIGHT)
    kw.setdefault("commence_time_source", "kalshi_ticker")
    return _Row(row_id, home, away, **kw)


def _played(row_id=15297679, home="Sunderland", away="Arsenal", **kw):
    """The real card: ESPN's row, kicked off, finished, with a score."""
    kw.setdefault("commence_time", KICKOFF)
    kw.setdefault("commence_time_source", "espn")
    kw.setdefault("espn_id", "401881962")
    kw.setdefault("home_score", 0)
    kw.setdefault("away_score", 2)
    return _Row(row_id, home, away, **kw)


# ── the ship ────────────────────────────────────────────────────────────────


def test_the_phantom_epl_card_folds_into_the_finished_one():
    """The defect itself, with production's exact two rows."""
    result = fold_twin_events([_placeholder(), _played()])

    assert _ids(result) == [15297679]
    assert result.folded_count == 1


def test_the_card_the_reader_keeps_is_the_one_with_the_score():
    """A page showing "No result reported" instead of 0–2 is the whole defect.

    Order-independent, because the election and not the caller's list order is
    what decides: the placeholder is listed second here and first above.
    """
    result = fold_twin_events([_played(), _placeholder()])

    (survivor,) = result.events
    assert survivor.id == 15297679
    assert (survivor.home_score, survivor.away_score) == (0, 2)


def test_the_placeholder_never_wins_even_carrying_more_venues():
    """Richness must not buy the election — gotcha, and lane1/197's measurement.

    Production's placeholders really did carry sources of their own
    (`statpal_injuries`), so this is the shape on the page, not a hypothetical.
    """
    result = fold_twin_events(
        [
            _placeholder(sources={"statpal_injuries": {}, "kalshi": {"p": 0.4}}),
            _played(sources=None),
        ]
    )

    (survivor,) = result.events
    assert survivor.id == 15297679


def test_the_absorbed_venues_reach_the_surviving_card():
    """Folding must merge, never filter: the union is the reason this is safe.

    Dropping the phantom row instead — the obvious fix, and the one #5918 was
    filed to refuse — would delete whatever price only it carried.
    """
    result = fold_twin_events(
        [
            _placeholder(sources={"kalshi": {"probability": 0.22}}),
            _played(sources={"betting": {"probability": 0.31}}),
        ]
    )

    assert sorted(result.merged_sources[15297679]) == ["betting", "kalshi"]


def test_all_three_premier_league_phantoms_fold_in_one_pass():
    """The page had three, not one, and they must not interfere with each other."""
    population = [
        _placeholder(15310635, "Sunderland AFC", "Arsenal FC"),
        _placeholder(15310639, "Liverpool FC", "Fulham FC"),
        _placeholder(
            15310517,
            "Coventry City",
            "Brighton & Hove Albion",
            commence_time=datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc),
        ),
        _played(15297679, "Sunderland", "Arsenal"),
        _played(
            15297677,
            "Liverpool",
            "Fulham",
            commence_time=datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc),
            espn_id="401881961",
            home_score=0,
            away_score=0,
        ),
        _played(
            15297680,
            "Coventry City",
            "Brighton and Hove Albion",
            commence_time=datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc),
            espn_id="401881960",
            home_score=0,
            away_score=5,
        ),
    ]

    result = fold_twin_events(population)

    assert _ids(result) == [15297677, 15297679, 15297680]
    assert result.folded_count == 3


def test_the_ligue_one_phantom_folds_now_that_its_club_has_a_name():
    """The fourth date-only row, and the only one this file listed as a miss (#6022).

    Production 2026-09-13 served both of these on `/sports/soccer_france_ligue_one`:
    a midnight Kalshi-ticker placeholder and the finished 2-2 eight rows below
    it. Every part of the #6007 exception already reached them — same sport,
    same UTC date, `Le Mans FC` matching on the home side — and the away side
    did not, because `Racing Club De Lens` and `RC Lens` share no token. The
    whole-name entry in `soccer_team_matching.CLUB_NAME_ALIASES` is what closes
    it, so this test fails if either half is reverted.
    """
    population = [
        _placeholder(
            15310514,
            "Le Mans FC",
            "Racing Club De Lens",
            commence_time=datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc),
            sport_id=1319,
            sport_key="soccer_france_ligue_one",
        ),
        _played(
            15297788,
            "Le Mans FC",
            "RC Lens",
            commence_time=datetime(2026, 9, 13, 15, 15, tzinfo=timezone.utc),
            sport_id=1319,
            sport_key="soccer_france_ligue_one",
            espn_id="740283",
            home_score=2,
            away_score=2,
        ),
    ]

    result = fold_twin_events(population)

    (survivor,) = result.events
    assert survivor.id == 15297788
    assert (survivor.home_score, survivor.away_score) == (2, 2)
    assert result.folded_count == 1


# ── the regression this change is most likely to ship inert ────────────────


def test_a_busy_league_day_does_not_hide_the_phantom_behind_the_time_window():
    """THE INERT-FIX GUARD, and it is the reason this file is not three tests.

    `_name_clusters` walks its day-bucket in kick-off order and BREAKS out of
    the inner loop at the first row past `SOCCER_KICKOFF_DRIFT` — that window is
    what keeps a day-wide bucket from being a cross product (#5964). A
    placeholder sits at 00:00Z and so sorts first in its day, which puts every
    real kick-off hours beyond the break. Relax the predicate and forget the
    window and the fold never gets asked: the change reads as a no-op, and every
    other test in this file still passes because a two-row population has
    nothing to break on.

    So this one is a real Saturday: nine other fixtures between the phantom and
    its twin, each a genuine separate match that must survive untouched.
    """
    population = [_placeholder(), _played()]
    for i in range(9):
        population.append(
            _Row(
                16000000 + i,
                f"Filler Town {i}",
                f"Filler City {i}",
                commence_time=MIDNIGHT + timedelta(hours=2 + i),
                commence_time_source="espn",
                espn_id=f"9000{i}",
            )
        )

    result = fold_twin_events(population)

    assert result.folded_count == 1
    assert 15310635 not in _ids(result)
    assert 15297679 in _ids(result)
    for i in range(9):
        assert 16000000 + i in _ids(result)


# ── the exception is narrow, and each gate is asked on its own ─────────────


def test_a_ticker_row_that_has_a_real_hour_is_still_held_to_the_drift_bound():
    """Midnight is the evidence of NO hour; it is not decoration on the source.

    A `kalshi_ticker` row later given a real kick-off has a clock, so it can
    disagree about one, so the bound is the right rule for it again.
    """
    result = fold_twin_events(
        [
            _placeholder(commence_time=KICKOFF - timedelta(hours=8)),
            _played(),
        ]
    )

    assert _ids(result) == [15297679, 15310635]
    assert result.folded_count == 0


def test_a_midnight_row_from_another_source_is_not_a_placeholder():
    """`kalshi` is the market's own close time — a real instant, even when wrong.

    Three `soccer_other` rows carried it at midnight on the measured day with no
    evidence either way, and a midnight-UTC kick-off is an ordinary evening in
    South America. Only the source that names the TICKER is admitted.
    """
    result = fold_twin_events(
        [
            _placeholder(commence_time_source="kalshi"),
            _played(),
        ]
    )

    assert result.folded_count == 0


def test_a_row_with_no_source_recorded_is_not_a_placeholder():
    """The default must be the strict rule, so an unstamped row cannot slip in."""
    result = fold_twin_events([_placeholder(commence_time_source=None), _played()])

    assert result.folded_count == 0


def test_the_exception_does_not_reach_across_the_day_boundary():
    """The bucket is `(sport_id, UTC date)` and stays the outer limit.

    A ticker date is the one thing these rows DO assert. Letting a midnight row
    fold into the next day's fixture would throw away the only fact it has.
    """
    result = fold_twin_events(
        [
            _placeholder(),
            _played(commence_time=KICKOFF + timedelta(days=1)),
        ]
    )

    assert result.folded_count == 0


def test_both_clubs_still_have_to_match():
    """The names carry the whole decision now, so they are asked in full."""
    result = fold_twin_events(
        [
            _placeholder(home="Liverpool FC", away="Fulham FC"),
            _played(home="Manchester City", away="Fulham"),
        ]
    )

    assert result.folded_count == 0


def test_orientation_still_decides():
    """Home and away are not interchangeable; a reversed fixture is not a twin."""
    result = fold_twin_events(
        [
            _placeholder(home="Liverpool FC", away="Fulham FC"),
            _played(home="Fulham", away="Liverpool"),
        ]
    )

    assert result.folded_count == 0


def test_a_placeholder_outside_soccer_is_left_alone():
    """The subset name rule is measured on soccer boards and used nowhere else.

    `Texas` ⊆ `Texas State` are different schools; the soccer gate is what keeps
    that out, and a date-only row must not be a way around it.
    """
    result = fold_twin_events(
        [
            _placeholder(
                home="Texas",
                away="Baylor",
                sport_id=99,
                sport_key="americanfootball_ncaaf",
            ),
            _played(
                home="Texas State",
                away="Baylor",
                sport_id=99,
                sport_key="americanfootball_ncaaf",
            ),
        ]
    )

    assert result.folded_count == 0


def test_the_clique_refusal_still_holds_when_one_member_is_a_placeholder():
    """`Madrid` ⊆ `Real Madrid` and `Madrid` ⊆ `Atlético Madrid` chain two clubs.

    Union-find over a non-transitive predicate is the bug #5918 was handed over
    to refuse, and a dateless row reaches MORE candidates than any other row in
    its bucket — so it is the likeliest thing ever to build such a chain.
    """
    population = [
        _placeholder(
            1, "Madrid", "Barcelona", sport_id=1317, sport_key="soccer_spain_la_liga"
        ),
        _played(
            2,
            "Real Madrid",
            "Barcelona",
            sport_id=1317,
            sport_key="soccer_spain_la_liga",
            espn_id="a",
        ),
        _played(
            3,
            "Atlético Madrid",
            "Barcelona",
            sport_id=1317,
            sport_key="soccer_spain_la_liga",
            espn_id="b",
            commence_time=KICKOFF + timedelta(hours=2),
        ),
    ]

    result = fold_twin_events(population)

    assert _ids(result) == [1, 2, 3]
    assert result.folded_count == 0


def test_two_different_fixtures_a_club_could_not_play_both_of_stay_apart():
    """Same day, same competition, names that do not name the same two clubs."""
    result = fold_twin_events(
        [
            _placeholder(home="Liverpool FC", away="Fulham FC"),
            _played(
                home="Arsenal",
                away="Tottenham Hotspur",
                espn_id="x",
                commence_time=KICKOFF + timedelta(hours=3),
            ),
        ]
    )

    assert result.folded_count == 0


# ── the predicate itself ───────────────────────────────────────────────────


def test_is_kalshi_date_only_reads_both_halves():
    assert is_kalshi_date_only(_placeholder()) is True
    assert is_kalshi_date_only(_placeholder(commence_time_source="kalshi")) is False
    assert is_kalshi_date_only(_placeholder(commence_time_source="espn")) is False
    assert is_kalshi_date_only(_played()) is False


def test_is_kalshi_date_only_needs_midnight_exactly():
    """Not "near midnight": the caller's window exemption relies on 00:00 sorting
    first in its day, and a row a second past midnight is a row with an hour."""
    for delta in (
        timedelta(seconds=1),
        timedelta(minutes=1),
        timedelta(microseconds=1),
        timedelta(hours=1),
        timedelta(seconds=-1),
    ):
        row = _placeholder(commence_time=MIDNIGHT + delta)
        assert is_kalshi_date_only(row) is False, delta


def test_is_kalshi_date_only_survives_a_row_it_cannot_read():
    """Gotcha #42 — one surprising row must cost that row, never the page."""

    class _Surprising:
        commence_time_source = "kalshi_ticker"
        commence_time = "2026-09-12"  # a string, not a datetime

    assert is_kalshi_date_only(_Surprising()) is False


def test_the_drift_bound_itself_is_untouched():
    """#6007 adds an exception for rows with no clock; it does not widen the bound.

    A guard here rather than in #5964's file because this is the change that
    could have been written by moving the constant instead.
    """
    assert SOCCER_KICKOFF_DRIFT == timedelta(minutes=5)
