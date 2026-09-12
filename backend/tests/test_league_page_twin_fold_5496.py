"""#5496 — the league page serves ONE card per fixture (#4100's fourth surface).

THE DEFECT, seen on the live page (`/sport/baseball/mlb`) at 05:3xZ 2026-09-12:
THREE fixtures in the LIVE & UPCOMING rail were each drawn twice — Tigers–
Rockies, Yankees–Mets and Cubs–Pirates — **six of the eight slots**. Two of the
three printed a DIFFERENT number for the same game side by side (63%/62% and
53%/54%), which is the part that matters: not a wasted slot, but the site
disagreeing with itself where a reader sees both at once.

An API probe 25 minutes earlier found only two of them. The rail is
clock-ordered, so live games push its contents along and the visible count
moves; the stable population is the 114 MLB twin pairs on production. Do not
read any single count here as a rate.

WHY THE FILTER ALREADY ON THIS RAIL CANNOT HELP. `not_a_proven_duplicate`
(#2263) reads a `provenance:duplicate-of:` tag that only a prover writes, and
the prover needs a shared provider id. Of 114 MLB twin pairs on production,
**zero share an anchor key** — the StatPal-born row is anchored
`statpal:baseball_mlb:<id>`, the ESPN-born row `espn:`/`odds_api:`, and nothing
records that the two name one game. The id-keyed filter is structurally blind to
them; the id-free fold is not.

These tests are written so that REMOVING the fix turns them red for the reason
the fix exists, and so that the two orderings it depends on — fold before the
cap, fold before the count — are each pinned by a test that fails if only that
one ordering is reversed.
"""

from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes.league_futures import (
    UPCOMING_GAMES_LIMIT,
    UPCOMING_TWIN_FOLD_HEADROOM,
    _folded_upcoming,
    upcoming_games_query,
)


def _Row(id, home, away, commence, sources=None, sport_id=1):
    """A real, UNATTACHED `Event` ORM instance — not a stand-in.

    It has to be the real class: the route writes the unioned sources with
    `set_committed_value`, which reaches for `_sa_instance_state` and raises on
    anything that merely has the right attribute names. A plain fake passed the
    fold and then fell into the route's own `except` — so the rail came back
    UNFOLDED and the test failed for a reason that had nothing to do with the
    product. Using the real class is also the only way this file can notice if
    `set_committed_value` ever stops being the right call.
    """
    row = Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport_id,
        win_probability_sources=sources or {},
        status="scheduled",
    )
    return row


BASE = datetime(2026, 9, 12, 17, 5, tzinfo=timezone.utc)


def _pair(id_a, id_b, home, away, when=BASE, skew_seconds=0):
    """The production shape: an ESPN-born row and a StatPal-born row, one game.

    The provenance split is the point and it is not decoration. The ESPN row
    carries `espn_id` + `external_id`; the StatPal row carries neither. That is
    what `twin_identity_rank` elects on, and it is why the survivor here is the
    HIGHER id — a fixture where both rows are bare would tie all the way down to
    the id tie-break and quietly assert the opposite thing.
    """
    espn_row = _Row(id_a, home, away, when, sources={"betting": 0.63})
    espn_row.espn_id = "401816907"
    espn_row.external_id = "faaa421b"
    statpal_row = _Row(
        id_b,
        home,
        away,
        when + timedelta(seconds=skew_seconds),
        sources={"kalshi": 0.64},
    )
    statpal_row.statpal_fixture_id = "364963"
    return [espn_row, statpal_row]


class TestTheRailFolds:
    def test_the_production_specimen_serves_one_card(self):
        """Tigers–Rockies twice in, once out."""
        rows = _pair(15310663, 15305270, "Detroit Tigers", "Colorado Rockies")
        out = _folded_upcoming(rows)
        assert len(out) == 1, "two rows for one fixture must serve ONE card"
        # The ESPN-anchored row survives — the one the event page, the chart and
        # the settlement path can all reach. 148 measured this election over the
        # real 50 production rows for two slates: it won 15 of 15, 0 losses.
        assert out[0].id == 15310663

    def test_the_second_production_specimen_folds_too(self):
        rows = _pair(15310364, 15305271, "New York Yankees", "New York Mets")
        assert len(_folded_upcoming(rows)) == 1

    def test_the_survivor_gains_the_twins_venue(self):
        """The union is the point: folding must not cost a reader a source.

        If this asserted only the row count it would pass against a fold that
        threw the other row's price away, which the blend ruling forbids.
        """
        rows = _pair(1, 2, "Detroit Tigers", "Colorado Rockies")
        out = _folded_upcoming(rows)
        assert set(out[0].win_probability_sources) == {"betting", "kalshi"}

    def test_two_different_games_are_never_folded(self):
        """The negative control. Must hold in BOTH directions or the fix is a
        rail that serves one card whatever it is given."""
        rows = [
            _Row(1, "Detroit Tigers", "Colorado Rockies", BASE),
            _Row(2, "New York Yankees", "New York Mets", BASE),
        ]
        assert len(_folded_upcoming(rows)) == 2

    def test_a_doubleheaders_second_leg_keeps_its_own_card(self):
        """MLB's back-to-back is the doubleheader and it is a REAL second game.

        8h05m apart (Detroit @ Cleveland, 2026-09-04 — the one genuine
        doubleheader in the measured window). A fold that collapsed this would
        delete a game from the page.
        """
        rows = [
            _Row(1, "Cleveland Guardians", "Detroit Tigers", BASE),
            _Row(2, "Cleveland Guardians", "Detroit Tigers", BASE + timedelta(hours=8, minutes=5)),
        ]
        assert len(_folded_upcoming(rows)) == 2

    def test_an_empty_rail_is_not_a_crash(self):
        assert _folded_upcoming([]) == []


class TestTheOrderingsThatMakeItCorrect:
    """Each test here fails if exactly ONE of the two orderings is reversed."""

    def test_the_query_over_fetches_so_the_fold_cannot_cost_a_card(self):
        """FOLD BEFORE CAP. Without headroom in the LIMIT, a rail holding one
        twin pair serves seven cards where eight were available."""
        sql = str(
            upcoming_games_query(
                "baseball_mlb",
                BASE,
                fold_headroom=UPCOMING_TWIN_FOLD_HEADROOM,
            ).compile(compile_kwargs={"literal_binds": True})
        )
        assert f"LIMIT {UPCOMING_GAMES_LIMIT + 1 + UPCOMING_TWIN_FOLD_HEADROOM}" in sql

    def test_the_headroom_actually_reaches_the_statement(self):
        """Pins the wiring, not just the constant: a `fold_headroom` the query
        accepted and ignored would pass the test above by arithmetic alone."""
        without = str(
            upcoming_games_query("baseball_mlb", BASE).compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        with_room = str(
            upcoming_games_query("baseball_mlb", BASE, fold_headroom=5).compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert f"LIMIT {UPCOMING_GAMES_LIMIT + 1}" in without
        assert f"LIMIT {UPCOMING_GAMES_LIMIT + 1 + 5}" in with_room

    def test_a_full_rail_of_twins_still_fills_the_page(self):
        """The headroom's sizing argument, executed rather than asserted.

        `UPCOMING_GAMES_LIMIT + 1 + HEADROOM` rows that are ALL twin pairs must
        still fold to at least the cap. This is what fails if the headroom is
        cut below the cap.
        """
        rows = []
        for i in range(UPCOMING_GAMES_LIMIT + 1 + UPCOMING_TWIN_FOLD_HEADROOM):
            # Pairs: rows 2k and 2k+1 are the same fixture.
            fixture = i // 2
            rows.append(
                _Row(
                    1000 + i,
                    f"Home {fixture}",
                    f"Away {fixture}",
                    BASE + timedelta(days=fixture),
                )
            )
        out = _folded_upcoming(rows)
        assert len(out) >= UPCOMING_GAMES_LIMIT, (
            f"an all-twin rail folded to {len(out)}, below the {UPCOMING_GAMES_LIMIT}"
            " card cap — the headroom is too small"
        )

    def test_the_headroom_is_not_smaller_than_the_cap(self):
        """Pins the constant from the side a tuner would move it: down.

        The test above proves the behaviour, but only for pairs. This states the
        bound directly so a future edit has to argue with a sentence, not just
        get lucky on a fixture.
        """
        assert UPCOMING_TWIN_FOLD_HEADROOM >= UPCOMING_GAMES_LIMIT

    def test_the_headroom_is_bounded(self):
        """And from the other side: 'fetch everything' is not the fix.

        The feeder scan is 200 and is a measured exception for competition
        sharing; the fold's headroom has no such licence.
        """
        assert UPCOMING_TWIN_FOLD_HEADROOM <= 2 * UPCOMING_GAMES_LIMIT


class TestItNeverTakesThePageDown:
    def test_a_fold_that_raises_serves_the_unfolded_rail(self, monkeypatch):
        """Gotcha #42 as a whole stage: today's bug beats no page at all."""

        def _boom(_events):
            raise RuntimeError("fold exploded")

        monkeypatch.setattr(
            "app.routes.league_futures.fold_twin_events", _boom
        )
        rows = _pair(1, 2, "Detroit Tigers", "Colorado Rockies")
        out = _folded_upcoming(rows)
        assert len(out) == 2, "a raising fold must return the rail it was given"

    def test_the_helper_cannot_see_the_path_parameter_at_all(self):
        """The guard for the class, written because the first push failed it.

        `sport_key` is a path parameter, so interpolating it into a log is
        `py/log-injection` — CodeQL graded it MEDIUM security severity on this
        very function and notice 32 refuses that. The first version of this file
        asserted only that the EXCEPT branch stayed clean, and the success
        branch four lines above it leaked the value anyway.

        So the assertion is no longer "does this branch avoid it". A helper that
        never receives the tainted value cannot leak it from any branch, and
        that is what is pinned here — signature first, then the whole source.
        """
        import inspect

        from app.routes import league_futures

        params = inspect.signature(league_futures._folded_upcoming).parameters
        assert "sport_key" not in params, (
            "the fold helper must not take the path parameter — a value it "
            "cannot see is a value it cannot log"
        )

        # Read as CODE, not as text. The docstring and the comments name
        # `sport_key` on purpose — they are the explanation — so a substring
        # scan would fail on its own warning label. Only a real identifier
        # reference counts.
        import ast
        import textwrap

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(league_futures._folded_upcoming))
        )
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        assert "sport_key" not in names, (
            "the tainted path parameter is referenced as code inside the fold "
            "helper — that is the py/log-injection shape CodeQL refuses"
        )


class TestTheRailIsStillWiredUp:
    def test_the_route_calls_the_fold_before_it_counts_or_caps(self):
        """A source scan, and it is the only thing here that can catch the fold
        being moved BELOW `_more_games` or the cap — a reordering every
        behavioural test above would survive, because each drives the helper
        directly."""
        import inspect

        from app.routes import league_futures

        source = inspect.getsource(league_futures.build_league)
        fold_at = source.index("_folded_upcoming(")
        count_at = source.index("_more_games = ")
        cap_at = source.index("[:UPCOMING_GAMES_LIMIT]")
        assert fold_at < count_at, "the fold must run before `_more_games` counts"
        assert fold_at < cap_at, "the fold must run before the cap"

    def test_the_route_actually_asks_for_the_headroom(self):
        """The gap the first red control exposed.

        Every LIMIT test above calls `upcoming_games_query` itself and passes
        the headroom by hand, so all of them stay green against a route that
        stopped asking for it — and the rail would quietly serve seven cards.
        This is the only assertion that fails when the call site drops it.
        """
        import inspect

        from app.routes import league_futures

        source = inspect.getsource(league_futures.build_league)
        assert "fold_headroom=UPCOMING_TWIN_FOLD_HEADROOM" in source

    def test_the_rail_still_carries_its_proven_duplicate_filter(self):
        """Belt AND braces. The fold does not replace #2263's filter, and a
        sweep that removed it while adding this would be a regression the
        row-count tests could not see."""
        sql = str(
            upcoming_games_query("baseball_mlb", BASE).compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        # The filter's own literal, read off the compiled statement rather than
        # guessed at: it is a tag LIKE, not an EXISTS.
        assert "provenance:duplicate-of:" in sql
