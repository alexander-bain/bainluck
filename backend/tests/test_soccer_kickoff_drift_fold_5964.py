"""Guard: two providers two minutes apart on one kick-off get one card (#5964).

THE PAGE THIS EXISTS FOR. `/sports/soccer_spain_la_liga`, 2026-09-13 18:xxZ.
La Liga carried Getafe–Deportivo THREE times — a 00:00Z ghost fixture (#5896's,
already certed) and, the part this file is about, the same finished match twice:

    15311881  "Getafe" v "Deportivo"            16:30:00Z  completed 1-1  espn_id
    15298080  "Getafe" v "Deportivo La Coruña"  16:32:00Z  completed 1-1  no espn_id

#5918's name pass was built for exactly this exonym family and could not see it.
Not because it refused the names — it matches them — but because it was never
asked: the pass bucketed candidates by `(sport_id, commence MINUTE)`, and ESPN
had stored the kick-off at 16:30Z while the Odds API had 16:32Z. One fixture,
two minute-buckets, no question asked. Nobody's name rule was wrong and no
provider was wrong; two minutes of rounding hid the pair.

So the clock moved out of the bucket and became a BOUND on the pair
(`SOCCER_KICKOFF_DRIFT`). What that bound must never become is the subject of
most of this file, because the populations immediately either side of it belong
to other people's ships:

* 30-minute re-mints — #5918 excluded them ON PURPOSE;
* three-hour Kalshi expected-expirations — #5905 corrects those upstream, and
  folding them here would make that recovery's own guards pass for the wrong
  reason and quietly retire a ship still doing work on rows with no twin.

Measured on production the day this shipped: over all 1,503 soccer rows a reader
could reach, the bound folds 6 rows master served twice (the Getafe pair and
five identical-name `soccer_other` pairs 3–4 minutes apart) and unfolds nothing.
The naive version — bucket by day, let the names decide — folded 226.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_twin_fold import SOCCER_KICKOFF_DRIFT, fold_twin_events

KICKOFF = datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock, for the reason #5918's file gives: an
    auto-attribute mock makes every `espn_id` truthy and every `sport.key` a
    soccer key by accident, so the whole file would pass with the pass deleted.
    """

    def __init__(
        self,
        row_id,
        home,
        away,
        commence_time=None,
        sport_id=1317,
        sport_key="soccer_spain_la_liga",
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
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.espn_id = espn_id
        self.external_id = external_id
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = sources


def _ids(result):
    return sorted(event.id for event in result.events)


def _getafe_pair(drift_minutes):
    """Production's two rows, with the Odds API row's kick-off pushed by N."""
    espn = _Row(
        15311881,
        "Getafe",
        "Deportivo",
        espn_id="401882884",
        home_score=1,
        away_score=1,
    )
    odds_api = _Row(
        15298080,
        "Getafe",
        "Deportivo La Coruña",
        commence_time=KICKOFF + timedelta(minutes=drift_minutes),
        external_id="15e3bf25540c88237a06c03df1cb334b",
        home_score=1,
        away_score=1,
        sources={"kalshi": {"probability": 0.61}},
    )
    return [espn, odds_api]


# ── the ship ────────────────────────────────────────────────────────────────


def test_the_two_minute_getafe_pair_folds_to_one_card():
    """The defect itself: production's exact rows, production's exact drift."""
    result = fold_twin_events(_getafe_pair(2))

    assert _ids(result) == [15311881]
    assert result.folded_count == 1


def test_the_surviving_getafe_card_is_the_one_with_the_score_and_the_id():
    """Serving the scoreless row would be a worse page than serving two.

    `twin_identity_rank` already decides this; the point here is that a drift
    fold hands its group to the SAME election rather than keeping whichever row
    the caller happened to list first.
    """
    result = fold_twin_events(list(reversed(_getafe_pair(2))))

    (survivor,) = result.events
    assert survivor.id == 15311881
    assert survivor.espn_id == "401882884"
    assert (survivor.home_score, survivor.away_score) == (1, 1)


def test_the_folded_twins_price_is_carried_onto_the_survivor():
    """The blend is the product: the fold merges venues, it never deletes one.

    Production's survivor is the ESPN row, which holds no price at all — so a
    fold that dropped the Odds API row without unioning its sources would have
    deleted the only price on the card.
    """
    result = fold_twin_events(_getafe_pair(2))

    assert result.merged_sources[15311881] == {"kalshi": {"probability": 0.61}}


# ── the bound, pinned from BOTH sides ───────────────────────────────────────


def test_the_bound_is_five_minutes():
    """Pinned so that moving the constant is a decision, not a silent widening."""
    assert SOCCER_KICKOFF_DRIFT == timedelta(minutes=5)


@pytest.mark.parametrize("drift", [0, 1, 2, 3, 4, 5])
def test_a_pair_inside_the_bound_folds(drift):
    assert _ids(fold_twin_events(_getafe_pair(drift))) == [15311881]


@pytest.mark.parametrize("drift", [6, 7, 15, 30, 31, 180])
def test_a_pair_outside_the_bound_is_left_alone(drift):
    """Six minutes is refused for the same reason three hours is.

    30/31 are #5918's re-mint class and 180 is #5905's Kalshi class; both are
    listed here so that widening this bound trips a test naming its owner.
    """
    assert _ids(fold_twin_events(_getafe_pair(drift))) == [15298080, 15311881]


def test_the_bound_cannot_be_walked_around_in_steps():
    """Rows at 0, 4 and 8 minutes are not one fixture.

    Union-find would chain them — 0–4 and 4–8 both pass — which is why the
    clique refusal asks EVERY pair, and 0–8 is outside the bound. Refusing the
    cluster whole leaves all three rows standing rather than folding some
    arbitrary two of them.
    """
    rows = [
        _Row(1, "Getafe", "Deportivo"),
        _Row(2, "Getafe CF", "Deportivo", commence_time=KICKOFF + timedelta(minutes=4)),
        _Row(
            3,
            "Getafe",
            "Deportivo La Coruña",
            commence_time=KICKOFF + timedelta(minutes=8),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2, 3]


def test_a_chain_whose_ends_are_just_outside_the_bound_is_refused():
    """0, 3 and 6 minutes: every neighbour is inside the bound, the ends are not.

    This is the one shape that can see the bound the CLIQUE test applies, as
    distinct from the one the candidate search applies. The sliding window stops
    the union-find from ever asking about the 6-minute pair, so if the clique
    test's own bound were widened by a minute nothing else in this file would
    notice and these three rows would silently become one card.
    """
    rows = [
        _Row(1, "Getafe", "Deportivo"),
        _Row(2, "Getafe CF", "Deportivo", commence_time=KICKOFF + timedelta(minutes=3)),
        _Row(
            3,
            "Getafe",
            "Deportivo La Coruña",
            commence_time=KICKOFF + timedelta(minutes=6),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2, 3]


def test_a_pair_either_side_of_midnight_utc_fails_closed():
    """A known, deliberate gap: the candidate bucket is a UTC day.

    Two cards is today's behaviour and the wrong answer here is invisible, so
    this is pinned as a decision rather than left to be rediscovered as a bug.
    """
    rows = [
        _Row(
            1,
            "Getafe",
            "Deportivo",
            commence_time=datetime(2026, 9, 13, 23, 59, tzinfo=timezone.utc),
        ),
        _Row(
            2,
            "Getafe",
            "Deportivo La Coruña",
            commence_time=datetime(2026, 9, 14, 0, 1, tzinfo=timezone.utc),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


# ── the drift relaxes the CLOCK and nothing else ────────────────────────────


def test_a_reserve_side_is_not_folded_by_being_two_minutes_away():
    rows = [
        _Row(1, "Barcelona", "Getafe"),
        _Row(2, "Barcelona B", "Getafe", commence_time=KICKOFF + timedelta(minutes=2)),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_the_reverse_fixture_is_not_folded_by_being_two_minutes_away():
    rows = [
        _Row(1, "Celta Vigo", "Málaga"),
        _Row(
            2,
            "Malaga CF",
            "RC Celta de Vigo",
            commence_time=KICKOFF + timedelta(minutes=2),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_the_two_madrid_clubs_still_never_chain():
    """The drift must not give the non-transitive token rule a second chance."""
    rows = [
        _Row(1, "Real Madrid", "Getafe"),
        _Row(2, "Madrid", "Getafe", commence_time=KICKOFF + timedelta(minutes=2)),
        _Row(
            3, "Atlético Madrid", "Getafe", commence_time=KICKOFF + timedelta(minutes=4)
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2, 3]


def test_a_different_competition_is_still_a_different_bucket():
    """Widening the bucket to a DAY did not let it cross a competition, and
    #2866's league element did not either.

    Re-stated for the same reason as its twin in
    `test_soccer_name_pair_fold_5918.py`: this used to hold one `sport_key`
    against two `sport_id`s, a pair `sports.key`'s UNIQUE constraint makes
    impossible, and element 0 of the key is now the LEAGUE. Two keys naming two
    competitions is what the assertion was always about.
    """
    rows = [
        _Row(1, "Celta Vigo", "Málaga", sport_key="soccer_spain_la_liga", sport_id=7),
        _Row(
            2,
            "RC Celta de Vigo",
            "Malaga CF",
            sport_key="soccer_portugal_primeira_liga",
            sport_id=8,
            commence_time=KICKOFF + timedelta(minutes=2),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


# ── the soccer gate is what keeps the drift off everybody else ──────────────


def test_a_college_bucket_is_never_reached_by_the_drift():
    """`Texas` ⊆ `Texas State` is two different schools, at any drift."""
    rows = [
        _Row(1, "Texas", "Baylor", sport_key="americanfootball_ncaaf", sport_id=99),
        _Row(
            2,
            "Texas State",
            "Baylor",
            sport_key="americanfootball_ncaaf",
            sport_id=99,
            commence_time=KICKOFF + timedelta(minutes=2),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_a_baseball_doubleheader_is_never_reached_by_the_drift():
    """The minute in the STRICT key guards this, and it is unchanged.

    The strict key is every sport's; only the soccer pass got a drift bound. A
    doubleheader is the same teams on the same day, so if the bound ever escaped
    soccer this is the row that would vanish.
    """
    rows = [
        _Row(
            1,
            "St. Louis Cardinals",
            "San Francisco Giants",
            sport_key="baseball_mlb",
            sport_id=3,
        ),
        _Row(
            2,
            "St. Louis Cardinals",
            "San Francisco Giants",
            sport_key="baseball_mlb",
            sport_id=3,
            commence_time=KICKOFF + timedelta(minutes=2),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_an_unloaded_sport_still_refuses_to_fold():
    """ "Cannot tell" means "leave the rows alone" — gotcha #42's answer."""
    rows = _getafe_pair(2)
    for row in rows:
        del row.sport

    assert _ids(fold_twin_events(rows)) == [15298080, 15311881]


# ── nothing the strict key already did changes ──────────────────────────────


def test_an_exact_minute_identical_name_pair_folds_as_it_always_did():
    rows = [
        _Row(1, "Getafe", "Deportivo", espn_id="401882884"),
        _Row(2, "Getafe", "Deportivo"),
    ]

    assert _ids(fold_twin_events(rows)) == [1]


def test_two_unrelated_fixtures_in_one_competition_minutes_apart_are_untouched():
    """The ordinary case: a league stagger, which must never become one card."""
    rows = [
        _Row(1, "Sevilla", "Valencia"),
        _Row(2, "Real Betis", "Osasuna", commence_time=KICKOFF + timedelta(minutes=2)),
        _Row(3, "Villarreal", "Levante", commence_time=KICKOFF + timedelta(minutes=4)),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2, 3]
