"""Guard: two providers naming one club two ways get one card (#5918).

THE PAGE THIS EXISTS FOR. `/sports/soccer_spain_la_liga`, phone width,
2026-09-13 14:11Z. La Liga carried Celta–Málaga twice: once in Finished at
1–1, and once in **Live & Paused with a green LIVE badge and "No price yet"**
for a match that had already ended. Two `events` rows, one fixture:

    15298077  espn      "Celta Vigo"        v "Málaga"     espn_id, kalshi 0.99
    15310518  espn      "RC Celta de Vigo"  v "Malaga CF"  no ids, no price

#4100's fold did not fire, and could not: its key is a character squash, and
`celtavigo` is not `rcceltadevigo`. Nothing was spelled wrong. The two rows were
NAMED by two vocabularies, which is the ordinary condition of soccer and not a
defect in either provider.

WHY THE OBVIOUS FIX WAS REFUSED, AND IT IS THE REASON #5918 IS A p1 RATHER THAN
A ONE-LINER. `15310518` already carried `provenance:duplicate-of:` — the id rail
had tagged it correctly — so filtering tagged rows out of `/api/events` looks
like the fix. On the Mainz pair measured the same morning, the TAGGED row is the
one holding the Kalshi price and its elected canonical holds only
`statpal_injuries`. Hiding it would have deleted the only priced card. The fold
merges and elects; it never hides.

WHAT EACH TEST HERE DEFENDS — the five ways a relaxed name rule reaches a reader
as a WORSE page than two cards:

* it never fires, because the relaxation stopped at spelling
  (`test_celta_pair_folds_although_neither_name_is_misspelled`);
* it fires and the price is gone, because the id-bearing row and the priced row
  are different rows (`test_getafes_only_price_survives_on_the_espn_row`);
* it chains two different clubs through a third row that matched both
  (`test_the_two_madrid_clubs_never_chain_through_a_shared_token`);
* it escapes soccer, where `Texas` ⊆ `Texas State` is two different schools
  (`test_a_college_bucket_is_never_touched`, `test_an_unloaded_sport_never_folds`);
* it eats a reserve side, a reverse fixture or a different kick-off
  (`test_a_b_team_is_not_its_first_team`, `test_the_reverse_fixture_never_folds`,
  `test_a_different_minute_is_a_different_fixture`).
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events

KICKOFF = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock: an auto-attribute mock makes every `espn_id`
    truthy and every `sport.key` a soccer key by accident, which would let this
    whole file pass with the soccer pass deleted.
    """

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport_key="soccer_spain_la_liga",
        sport_id=7,
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


# ── the two production pairs, as measured 2026-09-13 ────────────────────────


def _celta_pair():
    """`/api/events?sport=soccer_spain_la_liga`, read 14:11Z."""
    finished = _Row(
        15298077,
        "Celta Vigo",
        "Málaga",
        home_score=1,
        away_score=1,
        espn_id="401882885",
        external_id="0eba3c2d3bcf1d1fe4ab3180a3d03152",
        sources={"kalshi": {"value": 0.99}},
    )
    ghost = _Row(
        15310518,
        "RC Celta de Vigo",
        "Malaga CF",
        sources={"statpal_injuries": [{"team": "Celta Vigo"}]},
    )
    return finished, ghost


def test_celta_pair_folds_although_neither_name_is_misspelled():
    finished, ghost = _celta_pair()

    result = fold_twin_events([finished, ghost])

    assert _ids(result) == [15298077]
    assert result.dropped_ids == [15310518]


def test_the_ghost_that_goes_is_the_one_with_the_live_badge_and_no_price():
    """Election is unchanged by #5918 and this pins which row a reader keeps.

    The row that survives must be the one carrying the score and the ESPN id —
    serving the scoreless "LIVE" row instead would be a worse page than the two
    cards this fold replaced.
    """
    finished, ghost = _celta_pair()

    survivor = fold_twin_events([ghost, finished]).events[0]

    assert (survivor.id, survivor.home_score, survivor.espn_id) == (
        15298077,
        1,
        "401882885",
    )


def test_getafes_only_price_survives_on_the_espn_row():
    """The id-bearing row and the priced row are DIFFERENT rows here.

    `15311881` wins the election on its ESPN id and carries no sources at all;
    the Kalshi price lives on the twin. A fold that dropped the loser's venues —
    or a filter that dropped the loser — would serve Getafe with no number.
    """
    espn_row = _Row(
        15311881,
        "Getafe",
        "Deportivo",
        commence_time=datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc),
        espn_id="401882884",
    )
    priced = _Row(
        15298080,
        "Getafe",
        "Deportivo La Coruña",
        commence_time=datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc),
        external_id="15e3bf25540c88237a06c03df1cb334b",
        commence_time_source="odds_api",
        sources={"kalshi": {"value": 0.37}},
    )

    result = fold_twin_events([priced, espn_row])

    assert _ids(result) == [15311881]
    assert result.merged_sources[15311881] == {"kalshi": {"value": 0.37}}


# ── the non-transitivity trap, which is why this is a predicate ─────────────


def test_the_two_madrid_clubs_never_chain_through_a_shared_token():
    """`Madrid` ⊆ `Real Madrid` and `Madrid` ⊆ `Atlético Madrid`; the two clubs
    are not each other. A dict keyed on the relaxed name, or a union-find with
    no clique test, folds all three into one card. All three must stand.
    """
    rows = [
        _Row(1, "Madrid", "Getafe"),
        _Row(2, "Real Madrid", "Getafe"),
        _Row(3, "Atlético Madrid", "Getafe"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_a_clique_of_three_still_folds():
    """The clique test must refuse chains, not every cluster above two.

    All three of these name one club in three vocabularies, so every pair
    matches and the reader gets one card.
    """
    rows = [
        _Row(1, "PSG", "Brest"),
        _Row(2, "Paris Saint Germain", "Brest"),
        _Row(3, "Paris Saint-Germain", "Brest", espn_id="401882900"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [3]
    assert sorted(result.dropped_ids) == [1, 2]


# ── the sport gate ──────────────────────────────────────────────────────────


def test_a_college_bucket_is_never_touched():
    """`Texas` ⊆ `Texas State` and `Miami` ⊆ `Miami (OH)` are different schools.

    The subset rule was measured on soccer boards, where the short name is the
    same club. College sport is the population that breaks it, and soccer's
    squad-qualifier guard has nothing to say about a `State` suffix.
    """
    rows = [
        _Row(1, "Texas", "Oklahoma", sport_key="basketball_ncaab", sport_id=12),
        _Row(2, "Texas State", "Oklahoma", sport_key="basketball_ncaab", sport_id=12),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2]


def test_an_unloaded_sport_never_folds():
    """`/api/teams/{identifier}` and `/api/leagues/{sport_key}` do not
    `selectinload(Event.sport)`. A lazy load from inside a stage wrapped in a
    bare `except` would silently disable the whole fold, so "cannot tell" means
    "leave the rows alone" — the same answer #5905's recovery gives.
    """
    rows = [_Row(1, "Celta Vigo", "Málaga"), _Row(2, "RC Celta de Vigo", "Malaga CF")]
    for row in rows:
        del row.sport

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2]


# ── the refusals soccer's own rule already makes, pinned at this seam ───────


def test_a_b_team_is_not_its_first_team():
    rows = [_Row(1, "Barcelona", "Getafe"), _Row(2, "Barcelona B", "Getafe")]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_the_reverse_fixture_never_folds():
    """Orientation is kept. Every league in the corpus plays home and away."""
    rows = [_Row(1, "Celta Vigo", "Málaga"), _Row(2, "Malaga CF", "RC Celta de Vigo")]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_a_different_minute_is_a_different_fixture():
    """Relaxing the names does not relax the clock: the 30-minute Polymarket
    re-mints measured on the same boards are a different mechanism and are not
    this pass's to fold.

    #5964 moved the clock rule out of the bucket and into a bound on the pair
    (`SOCCER_KICKOFF_DRIFT`, 5 minutes), so the sentence that used to be here —
    "the bucket is `(sport_id, minute)`" — is no longer how it is enforced. The
    assertion is untouched and still says what it always said: thirty minutes is
    not one fixture. That is now a statement about the bound rather than about
    exact equality, and it is exactly the boundary #5964 undertook not to cross.
    """
    rows = [
        _Row(1, "Celta Vigo", "Málaga"),
        _Row(
            2,
            "RC Celta de Vigo",
            "Malaga CF",
            commence_time=KICKOFF + timedelta(minutes=30),
        ),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


def test_a_different_sport_id_is_a_different_bucket():
    rows = [
        _Row(1, "Celta Vigo", "Málaga", sport_id=7),
        _Row(2, "RC Celta de Vigo", "Malaga CF", sport_id=8),
    ]

    assert _ids(fold_twin_events(rows)) == [1, 2]


# ── composition, order and blast radius ─────────────────────────────────────


def test_the_strict_key_still_folds_what_it_always_folded():
    """#4100's own pair carries no `sport`, so the soccer pass cannot see it.

    If this breaks, the relaxation has cost the MLB card Alex reported rather
    than added to it.
    """
    rows = [
        _Row(
            15307210,
            "San Francisco Giants",
            "St. Louis Cardinals",
            home_score=2,
            away_score=0,
        ),
        _Row(15300848, "San Francisco Giants", "St.Louis Cardinals"),
    ]
    for row in rows:
        del row.sport

    result = fold_twin_events(rows)

    assert _ids(result) == [15307210]


def test_the_pass_removes_a_row_and_never_reorders_one():
    """A fold that reshuffles a page is a ranking change wearing a bug fix's
    clothes, and this pass cannot be one: `fold_twin_events` emits survivors by
    filtering the ARRIVAL order, so the groups the pass merges decide membership
    and never sequence. The ghost leaves; every other row keeps its slot, and
    the survivor keeps the slot it arrived in rather than its twin's.
    """
    finished, ghost = _celta_pair()
    before = _Row(10, "Sevilla", "Elche", commence_time=KICKOFF - timedelta(hours=2))
    after = _Row(11, "Osasuna", "Alaves", commence_time=KICKOFF + timedelta(hours=2))

    arrived = [before, ghost, after, finished]
    result = fold_twin_events(arrived)

    assert _ids(result) == [10, 11, 15298077]
    assert _ids(result) == [row.id for row in arrived if row.id != 15310518]


def test_one_unreadable_row_costs_that_row_its_fold_and_not_the_page():
    """Gotcha #42 at this seam: the pass runs on `/api/feed` above every other
    stage, so a surprising row must never empty a page.
    """

    class _Exploding(_Row):
        @property
        def home_team_name(self):  # noqa: D102 — the whole point is that it raises
            raise RuntimeError("surprising row")

        @home_team_name.setter
        def home_team_name(self, value):
            pass

    finished, ghost = _celta_pair()
    result = fold_twin_events([_Exploding(9, "x", "y"), finished, ghost])

    assert 15298077 in _ids(result)
    assert 15310518 not in _ids(result)


def test_no_soccer_means_no_extra_work_and_no_change():
    """The pass must be inert for a caller serving a sport it does not cover."""
    rows = [
        _Row(
            1,
            "Boston Red Sox",
            "New York Yankees",
            sport_key="baseball_mlb",
            sport_id=3,
        ),
        _Row(
            2,
            "Houston Astros",
            "Seattle Mariners",
            sport_key="baseball_mlb",
            sport_id=3,
        ),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2]
    assert result.dropped_ids == []
