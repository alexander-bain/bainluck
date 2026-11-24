"""#5746 — a finished game may not also sit on the page waiting for its score.

THE SPECIMEN, MEASURED ON PRODUCTION 20:5xZ 2026-09-12
══════════════════════════════════════════════════════
`GET /api/leagues/baseball_mlb`, two rails of one payload::

    recent_results     15309733  St. Louis Cardinals 7-3 Chicago White Sox  completed  espn
    unreported_games   15304908  St.Louis Cardinals      Chicago White Sox  suspended  statpal

One contest. Both rows carry StatPal fixture `364953`; both carry
`2026-09-12 00:15:00+00:00`. The reader saw the game Final and, further down the
same page, waiting for a result.

WHY THE EXISTING DEFENCES BOTH MISSED IT — and why folding each rail separately
would have shipped a green test over a live bug
═══════════════════════════════════════════════════════════════════════════════
`not_a_proven_duplicate()` (#2263) IS on both past rails, and is id-keyed: it
needs the ghost tagged `provenance:duplicate-of:`. Nothing tagged this one —
`_proven_duplicates` fires at ingest and needs a shared PROVIDER id, and at the
moment the ESPN row was created it had no StatPal fixture id (the stamping rail
writes that afterwards). So the belt was structurally blind.

The braces — `fold_twin_events`, id-free — reached only the UPCOMING rail
(`_folded_upcoming`, #5496).

And the shape of the miss is what this file is really about:
:func:`app.utils.event_twin_fold.twin_fold_key` requires the same
`commence_time` to the minute, so twins ALWAYS share a kickoff and can never be
split by a rail's time bound. What splits these two rails is
`settled_rail_condition` vs `unreported_rail_condition` — whether the row has a
result — and having no result is the ghost's defining property. So a past twin
does not merely tend to straddle the two rails; it is guaranteed to. A fold
applied to each rail on its own sees exactly one member of every such pair and
folds nothing, while reporting success.

`test_folding_each_rail_alone_would_have_changed_nothing` is that sentence as a
test, and it is the one to read first: it fails on the design, not on the
implementation.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event
from app.routes import league_futures
from app.routes.league_futures import _folded_past_rails
from app.utils.event_twin_fold import fold_twin_events

BASE = datetime(2026, 9, 12, 0, 15, tzinfo=timezone.utc)


def _Row(id, home, away, commence, sources=None, sport_id=1, status="scheduled"):
    """A real, UNATTACHED `Event` ORM instance — not a stand-in.

    The same reason as `test_league_page_twin_fold_5496._Row`: the helper writes
    unioned sources with `set_committed_value`, which reaches for
    `_sa_instance_state` and raises on anything that merely has the right
    attribute names. A plain fake would fall into the helper's own `except` and
    come back unfolded — the test would fail for a reason that is not the
    product, or worse, pass for one.
    """
    return Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport_id,
        win_probability_sources=sources or {},
        status=status,
    )


def _final(id=15309733, when=BASE, home="St. Louis Cardinals"):
    """The ESPN row that rides the RESULTS rail: a score and two provider ids."""
    row = _Row(id, home, "Chicago White Sox", when, sources={"betting": 0.63},
               status="completed")
    row.home_score = 7
    row.away_score = 3
    row.espn_id = "401816896"
    row.external_id = "c4e5d894df1c758237b65a07b20a62b2"
    row.statpal_fixture_id = "364953"
    return row


def _ghost(id=15304908, when=BASE, home="St.Louis Cardinals"):
    """The StatPal pre-load that rides the UNREPORTED rail: no score, no ids.

    The home name is spelled `St.Louis` exactly as production spells it. That
    one missing space is not decoration — it is the difference native/098
    measured as making seven Cardinals rows invisible to any name-equality join,
    and it is why the key normalises rather than compares.
    """
    row = _Row(id, home, "Chicago White Sox", when, sources={"kalshi": 0.64},
               status="suspended")
    row.statpal_fixture_id = "364953"
    return row


class TestTheProductionSpecimen:
    def test_the_finished_game_is_not_also_awaiting_its_score(self):
        results, unreported, _g = _folded_past_rails([_final()], [_ghost()], [])
        assert [e.id for e in results] == [15309733]
        assert unreported == []

    def test_the_survivor_is_the_row_with_the_result(self):
        """Not the lower id, and not the richer row — the one a reader wants."""
        results, unreported, _g = _folded_past_rails([_final()], [_ghost()], [])
        survivor = results[0]
        assert survivor.home_score == 7
        assert survivor.espn_id == "401816896"

    def test_the_spelling_difference_does_not_save_the_ghost(self):
        assert _final().home_team_name != _ghost().home_team_name
        results, unreported, _g = _folded_past_rails([_final()], [_ghost()], [])
        assert (len(results), len(unreported)) == (1, 0)

    def test_the_survivor_gains_the_venue_stranded_on_the_ghost(self):
        results, _, _g = _folded_past_rails([_final()], [_ghost()], [])
        assert results[0].win_probability_sources == {
            "betting": 0.63,
            "kalshi": 0.64,
        }


class TestTheDesignClaimItself:
    """The union is not a convenience — a per-rail fold is provably inert."""

    def test_folding_each_rail_alone_would_have_changed_nothing(self):
        """The strawman, run for real. This is the whole argument for #5746.

        If this ever passes with counts of 0, the split stopped being structural
        and the union fold is no longer load-bearing — read the rail conditions
        before deleting anything.
        """
        assert len(fold_twin_events([_final()]).dropped_ids) == 0
        assert len(fold_twin_events([_ghost()]).dropped_ids) == 0
        # ...and together, one goes.
        assert len(fold_twin_events([_final(), _ghost()]).dropped_ids) == 1

    def test_a_twin_can_never_be_separated_by_a_rails_time_bound(self):
        """Same key ⇒ same minute, so only the RESULT predicate can split a pair."""
        from app.utils.event_twin_fold import twin_fold_key

        assert twin_fold_key(_final()) == twin_fold_key(_ghost())
        skewed = _ghost(when=BASE + timedelta(minutes=1))
        assert twin_fold_key(_final()) != twin_fold_key(skewed)


class TestWhatItMustNeverFold:
    def test_a_doubleheaders_second_leg_keeps_its_own_card(self):
        leg_two = _ghost(id=15304909, when=BASE + timedelta(hours=4))
        results, unreported, _g = _folded_past_rails([_final()], [leg_two], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_two_different_games_at_one_instant_are_untouched(self):
        other = _Row(15304910, "Boston Red Sox", "Kansas City Royals", BASE)
        results, unreported, _g = _folded_past_rails([_final()], [other], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_a_row_missing_a_team_name_is_never_folded(self):
        nameless = _Row(15304911, None, "Chicago White Sox", BASE)
        results, unreported, _g = _folded_past_rails([_final()], [nameless], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_two_lone_rails_are_returned_unchanged(self):
        results, unreported, _g = _folded_past_rails([], [], [])
        assert (results, unreported) == ([], [])


class TestTheUpcomingRailIsContextExceptAgainstAFinal:
    """#5532 narrowed this class; it did not delete it.

    `test_the_upcoming_rail_is_never_shortened_by_this_call` used to live here
    and asserted the rule in full. It was retired deliberately, not lost: its
    own specimen — an upcoming ghost whose survivor is the Final on the results
    rail — is the exact shape #5532 measured on production as a reader being
    told one game was both in the Top 9th and over. The two tests below are that
    old test split on the line the new rule draws, so the half that still holds
    is still asserted.

    It also could not have caught the change if it had been left alone: it
    asserted `upcoming == before`, and the implementation builds a new list
    rather than mutating the caller's, so it would have passed green over the
    new behaviour without ever reading the returned rail. The mutation
    guarantee is worth keeping and is now its own test, below, stated as what
    it is.
    """

    def test_a_ghost_here_goes_when_its_survivor_is_on_the_upcoming_rail(self):
        live = _final(id=15309999)
        live.status = "live"
        _r, unreported, _g = _folded_past_rails([], [_ghost()], [live])
        assert unreported == []

    def test_the_returned_rail_drops_a_row_whose_fixture_is_already_a_final(self):
        """#5532. The fixture keeps a card — the one with the score on it."""
        upcoming = [_ghost(id=15304912)]
        results, _u, kept_g = _folded_past_rails([_final()], [], upcoming)
        assert [e.id for e in kept_g] == []
        assert [e.id for e in results] == [15309733]

    def test_it_is_not_shortened_when_the_survivor_has_no_result(self):
        """The old rule, kept where it still holds.

        The survivor is on the UNREPORTED rail, so the page has no finished
        card for this fixture. Dropping the upcoming row would leave a reader
        with nothing that says what happened — the card-slot argument the
        docstring makes, on the pairing it is still true for.
        """
        bare = _Row(15304950, "St.Louis Cardinals", "Chicago White Sox", BASE)
        ghost = _ghost()  # one source to the bare row's none, so the ghost wins
        _r, unreported, kept_g = _folded_past_rails([], [ghost], [bare])
        assert [e.id for e in unreported] == [15304908]
        assert [e.id for e in kept_g] == [15304950], (
            "an upcoming row was dropped for a survivor that is not a Final"
        )

    def test_the_callers_own_list_is_never_mutated(self):
        """The rail is rebuilt, never edited in place — the route reassigns."""
        upcoming = [_ghost(id=15304912)]
        before = list(upcoming)
        _r, _u, kept_g = _folded_past_rails([_final()], [], upcoming)
        assert upcoming == before
        assert kept_g is not upcoming


class TestItNeverTakesThePageDown:
    def test_a_fold_that_raises_serves_both_rails_unfolded(self, monkeypatch):
        """Gotcha #42: the fold improves the page, it never gates having one."""

        def boom(_events):
            raise RuntimeError("fold exploded")

        monkeypatch.setattr(league_futures, "fold_twin_events", boom)
        results, unreported, _g = _folded_past_rails([_final()], [_ghost()], [])
        assert [e.id for e in results] == [15309733]
        assert [e.id for e in unreported] == [15304908]

    def test_the_helper_cannot_see_the_path_parameter_at_all(self):
        """`sport_key` is a path parameter; interpolating it into a log line is
        `py/log-injection` at medium severity, which notice 32 refuses. A helper
        that cannot see the tainted value cannot leak it."""
        assert "sport_key" not in inspect.signature(_folded_past_rails).parameters

        # Read as CODE, not as text — the sibling file's lesson (#5496). The
        # docstring and comments name `sport_key` deliberately, because they are
        # the explanation, so a substring scan fails on its own warning label.
        # Only a real identifier reference counts.
        tree = ast.parse(textwrap.dedent(inspect.getsource(_folded_past_rails)))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "sport_key" not in names, (
            "the tainted path parameter is referenced as code inside the fold "
            "helper — that is the py/log-injection shape CodeQL refuses"
        )


class TestTheRailsAreStillWiredUp:
    def test_the_route_folds_before_it_counts_or_caps_either_rail(self):
        source = inspect.getsource(league_futures)
        fold_at = source.index(
            "_r_events, _u_events, _g_events = _folded_past_rails("
        )
        assert fold_at < source.index("more_results = len(_rrows)")
        assert fold_at < source.index("more_unreported = len(_urows)")
        assert fold_at > source.index("_u_events = list(_u.scalars().all())")

    def test_the_route_takes_back_the_upcoming_rail_before_anything_reads_it(self):
        """#5532. The drop is only real if the reassignment lands upstream of
        every reader — a returned list nobody binds changes no page."""
        source = inspect.getsource(league_futures)
        fold_at = source.index(
            "_r_events, _u_events, _g_events = _folded_past_rails("
        )
        for reader in (
            "for _e in (*_g_events, *_r_events, *_u_events):",
            "_tag_folded = await _tag_folded_rows(",
            "_grows = _format_all(_g_events)",
        ):
            assert fold_at < source.index(reader), reader

    @pytest.mark.parametrize("query", ["recent_results_query", "unreported_games_query"])
    def test_both_past_rails_keep_their_id_keyed_belt(self, query):
        """The braces are added to the belt, never instead of it."""
        source = inspect.getsource(getattr(league_futures, query))
        assert "not_a_proven_duplicate()" in source
