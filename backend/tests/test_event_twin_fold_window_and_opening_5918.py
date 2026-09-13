"""#5918 — the fold reaches a pair whose clocks disagree, and it costs no number.

## The two production facts this file was written from

**One.** `#5918`'s soccer name pass shipped with an exact-minute bucket and its
own specimen walked out of it in forty minutes. At 18:30Z on 2026-09-13
production held Getafe–Deportivo as two rows both stamped `16:30:00Z`; by
19:06Z the Odds API row read `16:32:00Z`, and
`https://bainluck.com/sports/soccer_spain_la_liga` served the finished match
twice under **Finished** — `Getafe 1–1 Coruña` with `54% / 46%`, and directly
beneath it `Getafe 1–1 Deportivo` with no percentage at all
(`artifacts-183/AFTER-5918-laliga-390-1908Z.png`, read at phone width). Two
providers' clocks, two cards.

**Two, and it is the worse of the pair.** Driving `fold_twin_events` — the real
function, not a re-implementation — over all 800 soccer rows a reader could
reach in `[now-12h, now+8d]` at 19:3xZ: of the eighteen rows it folded away,
`15297786` (Brest v Paris Saint-Germain) held
`opening_home_probability = 0.0953`, and the survivor it was folded into,
`15311919`, holds none. **The fold was already deleting a "Pre-match ·
sportsbooks" percentage from a live page** — one card instead of two, minus a
number — which is exactly the regression #5918 was filed to refuse, arriving by
way of its own fix. Widening the window without fixing that would have bought a
second one (Getafe's `0.5439`).

So the two halves land together, and the order matters: the carry is what makes
the widening safe.

## The measurement, both halves on, same 800 rows

    window   folded   openings carried
    0m         18       1   (Brest — the live defect, fixed)
    5m         19       1
    10m        20       2   (adds Getafe, and its 0.5439 travels)
    15m        20       2   (nothing new — the population plateaus)

No pair inside fifteen minutes was a different fixture, and no row the
exact-minute key already folded stopped being folded: every window is a strict
superset of the one before it.

## Why these tests are not a restatement of `test_event_twin_fold.py`

That file pins the strict key and the election. This one pins the two things
that can only go wrong once time is a WINDOW rather than an equality: a pair
that is near but not equal, and a chain of three that is near-by-neighbour and
far end to end. Plus the carry, on both of its arms.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    SOCCER_NAME_FOLD_WINDOW_MINUTES,
    fold_twin_events,
)

KICK_OFF = datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc)

LA_LIGA = 1317
MLB = 42


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `sport` loaded.

    Deliberately not a MagicMock, for the reason `test_event_twin_fold.py`
    states: an auto-attribute mock makes every `espn_id` truthy and every
    `sport.key` a soccer key, and this whole file would pass with the pass
    deleted. `sport` is set because the soccer gate reads it through
    `loaded_sport_key` and answers `None` for a row that has not loaded it —
    which is the "do nothing" branch, and would make every assertion below
    vacuous.
    """

    def __init__(
        self,
        id,
        *,
        sport_id=LA_LIGA,
        sport_key="soccer_spain_la_liga",
        home="Getafe",
        away="Deportivo",
        minutes_after=0,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        sources=None,
        opening=(None, None),
    ):
        self.id = id
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = KICK_OFF + timedelta(minutes=minutes_after)
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.win_probability_sources = sources
        self.opening_home_probability = opening[0]
        self.opening_away_probability = opening[1]


def _the_getafe_pair(*, minutes_apart=2):
    """The two rows production served twice, canonical-by-election first.

    `twin_identity_rank` elects on score-then-anchor, so the ESPN row wins and
    the Odds API row — the one holding every number a reader could see — is the
    one folded away. That asymmetry is the whole reason the carry exists and is
    reproduced here rather than tidied away.
    """
    espn = _Row(
        15311881,
        home="Getafe",
        away="Deportivo",
        home_score=1,
        away_score=1,
        espn_id="401882884",
    )
    odds_api = _Row(
        15298080,
        home="Getafe",
        away="Deportivo La Coruña",
        minutes_after=minutes_apart,
        home_score=1,
        away_score=1,
        external_id="15e3bf25540c88237a06c03df1cb334b",
        sources={"kalshi": {"value": 0.99}},
        opening=(0.5439, 0.4561),
    )
    return espn, odds_api


class TestTheWindow:
    def test_the_la_liga_pair_two_minutes_apart_is_one_card(self):
        """🔴 THE SHIP. The exact production specimen, at the drift that broke it."""
        espn, odds_api = _the_getafe_pair()

        result = fold_twin_events([espn, odds_api])

        assert [e.id for e in result.events] == [15311881], (
            "the two Getafe rows are still two cards — a two-minute disagreement "
            "between two providers' clocks is not two fixtures "
            f"(served: {[e.id for e in result.events]})"
        )
        assert result.dropped_ids == [15298080]

    def test_a_pair_at_the_window_edge_folds_and_one_minute_beyond_does_not(self):
        """The boundary is stated in both directions, because one side is a bug.

        Inclusive at the edge: a test that only asserted the inside would pass
        with the comparison written either way.

        🔴 THIS TEST CANNOT PIN THE CONSTANT'S VALUE and does not try to — it is
        written in terms of the constant, so setting the window to zero leaves
        it green. What pins the value is the specimen above: Getafe's two rows
        are two minutes apart on production, and
        `test_the_la_liga_pair_two_minutes_apart_is_one_card` goes red the
        moment the window can no longer reach them. Measured against a window
        of zero, that is exactly the pair of tests that fails.
        """
        at_edge = fold_twin_events(
            list(_the_getafe_pair(minutes_apart=SOCCER_NAME_FOLD_WINDOW_MINUTES))
        )
        beyond = fold_twin_events(
            list(_the_getafe_pair(minutes_apart=SOCCER_NAME_FOLD_WINDOW_MINUTES + 1))
        )

        assert at_edge.folded_count == 1, (
            "a pair exactly at the window was refused — the window is inclusive"
        )
        assert beyond.folded_count == 0, (
            "a pair past the window was folded — the window is not being applied"
        )

    def test_a_chain_of_three_that_is_far_end_to_end_is_refused_whole(self):
        """🔴 THE HAZARD THE WINDOW INTRODUCES, and the clique is the answer.

        Nearness is no more transitive than the name predicate is. Rows at 0, 8
        and 16 minutes pair up 0–8 and 8–16 and are sixteen minutes apart end to
        end. Following the chain would serve one card for a pair that nothing
        ever compared, so the cluster is refused whole and all three stand —
        the same treatment a non-clique of NAMES already gets.
        """
        rows = [
            _Row(1, minutes_after=0),
            _Row(2, minutes_after=8, home="Getafe CF"),
            _Row(3, minutes_after=16, home="Getafe"),
        ]

        result = fold_twin_events(rows)

        assert result.folded_count == 0, (
            "a three-row chain was folded through its middle row — the window "
            f"is not in the clique test (dropped: {result.dropped_ids})"
        )
        assert [e.id for e in result.events] == [1, 2, 3]

    def test_the_window_is_soccer_only(self):
        """Two MLB rows two minutes apart stay two cards.

        The subset name rule is measured on soccer boards and nowhere else
        (`Texas` ⊆ `Texas State` are different schools), so the window it is
        paired with may not leak either. Without the sport gate this pair folds.
        """
        rows = [
            _Row(
                1,
                sport_id=MLB,
                sport_key="baseball_mlb",
                home="San Francisco Giants",
                away="St. Louis Cardinals",
            ),
            _Row(
                2,
                sport_id=MLB,
                sport_key="baseball_mlb",
                home="San Francisco Giants",
                away="Cardinals",
                minutes_after=2,
            ),
        ]

        result = fold_twin_events(rows)

        assert result.folded_count == 0, (
            "a non-soccer pair was folded on a near-miss name inside the window"
        )

    def test_two_different_fixtures_inside_the_window_never_fold(self):
        """The window relaxes the clock, never the clubs.

        Real Sociedad v Atlético and Getafe v Deportivo kicked off four minutes
        apart in the same competition on the specimen day. Nothing about them
        matches, and the window must not invent a reason.
        """
        rows = [
            _Row(1, home="Getafe", away="Deportivo"),
            _Row(2, home="Real Sociedad", away="Atlético Madrid", minutes_after=4),
        ]

        result = fold_twin_events(rows)

        assert result.folded_count == 0
        assert [e.id for e in result.events] == [1, 2]


class TestTheCardKeepsItsPreMatchLine:
    def test_the_survivor_gains_the_opening_only_the_absorbed_row_held(self):
        """🔴 RED BEFORE THIS SHIP, on a live page. Brest v PSG's class.

        The elected survivor holds the id and the score; the row folded away
        holds every number. Before the carry the reader traded two cards for
        one card with no "Pre-match · sportsbooks" percentage on it.
        """
        espn, odds_api = _the_getafe_pair()

        result = fold_twin_events([espn, odds_api])
        survivor = result.events[0]

        assert survivor.opening_home_probability == 0.5439, (
            "the surviving card prints no pre-match line while the row it "
            "absorbed held one — the fold deleted a number "
            f"(got {survivor.opening_home_probability!r})"
        )
        assert survivor.opening_away_probability == 0.4561
        assert result.merged_opening == {15311881: (0.5439, 0.4561)}

    def test_a_survivor_with_its_own_line_is_never_overwritten(self):
        """Gap-fill, not preference — a correct pair on a page today cannot move."""
        espn, odds_api = _the_getafe_pair()
        espn.opening_home_probability = 0.61
        espn.opening_away_probability = 0.39

        result = fold_twin_events([espn, odds_api])
        survivor = result.events[0]

        assert (
            survivor.opening_home_probability,
            survivor.opening_away_probability,
        ) == (
            0.61,
            0.39,
        ), "the absorbed row's opening replaced the survivor's own"
        assert result.merged_opening == {}

    def test_a_half_line_on_the_survivor_still_blocks_the_carry(self):
        """Both halves must be absent. A pair is stated by ONE row or not at all.

        Two rows' openings are medians taken at different moments over
        different sportsbooks and need not sum to 1, so a home from here and an
        away from there is a line nobody quoted.
        """
        espn, odds_api = _the_getafe_pair()
        espn.opening_away_probability = 0.39

        result = fold_twin_events([espn, odds_api])
        survivor = result.events[0]

        assert survivor.opening_home_probability is None
        assert survivor.opening_away_probability == 0.39
        assert result.merged_opening == {}

    def test_the_carry_takes_the_lowest_id_of_two_holders_every_time(self):
        """A card may not flicker between two twins' readings across two polls.

        🔴 EACH ORDERING GETS ITS OWN ROWS, and the red that taught me so is
        worth the four lines: the carry WRITES to the survivor, so handing one
        set of objects to the fold twice asks the second call a different
        question — the survivor now holds a line and gap-fill correctly
        declines. That is the fold working, and it is not this assertion's
        subject.
        """

        def rows():
            espn, odds_api = _the_getafe_pair()
            third = _Row(
                15298081,
                home="Getafe",
                away="Deportivo La Coruña",
                minutes_after=1,
                opening=(0.10, 0.90),
            )
            return [espn, odds_api, third]

        first = fold_twin_events(rows())
        again = fold_twin_events(list(reversed(rows())))

        assert first.merged_opening == {15311881: (0.5439, 0.4561)}, (
            f"the carry did not take the lowest-id holder (got {first.merged_opening})"
        )
        assert again.merged_opening == first.merged_opening, (
            "the carry depends on the order the caller handed us the rows"
        )

    def test_a_second_fold_over_an_already_carried_row_is_a_no_op(self):
        """Idempotent, and `/api/leagues` is why that is load-bearing.

        That route hands the same row objects to this fold twice in one request
        (the same property `recover_kalshi_occurrence_starts` needed for the
        same reason). The second pass meets a survivor holding the line the
        first pass gave it, and gap-fill is what makes that a no-op rather than
        a second decision.
        """
        espn, odds_api = _the_getafe_pair()

        once = fold_twin_events([espn, odds_api])
        twice = fold_twin_events([*once.events, odds_api])

        assert twice.merged_opening == {}
        assert once.events[0].opening_home_probability == 0.5439

    def test_an_unfolded_row_is_left_exactly_alone(self):
        """The ordinary page: one row, no twin, nothing written to it."""
        espn, _ = _the_getafe_pair()

        result = fold_twin_events([espn])

        assert result.merged_opening == {}
        assert result.events[0].opening_home_probability is None
