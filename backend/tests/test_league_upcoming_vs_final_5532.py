"""#5532 — a finished game may not also be in the Top 9th on the same page.

THE SPECIMEN, MEASURED ON PRODUCTION 22:2xZ 2026-09-13
══════════════════════════════════════════════════════
`GET /api/leagues/baseball_mlb`, two rails of one payload::

    upcoming_games   15311614  St. Louis Cardinals 3-1 Chicago White Sox  live       no ids
    recent_results   15311666  St. Louis Cardinals 3-1 Chicago White Sox  completed  espn 401816926

One contest, one kickoff `2026-09-13T18:15:00+00:00`, the SAME SCORE on both
rows. At 390px a reader saw "● Top 9th" and, further down, "Sep 13 FINAL" —
the same game, twice, in two different states. Row values in this file are the
ones the production rows actually held (`win_probability_sources` included);
the id-less row is #5532's own title row, the one no poller can reach.

WHY THE THREE DEFENCES ALREADY ON THIS PAGE ALL MISSED IT
═════════════════════════════════════════════════════════
* `not_a_proven_duplicate()` (#2263) is id-keyed and needs a
  `provenance:duplicate-of:` tag. 15311614 carries no provider id at all, so
  nothing could ever have proven it a duplicate of anything.
* `_folded_upcoming` (#5496) folds the upcoming rail against ITSELF. Its twin
  is not on that rail.
* `_folded_past_rails` (#5746) already folded over the union and already
  ELECTED CORRECTLY — it dropped 15311614. It then returned the upcoming rail
  whole, by a documented design choice, and the dropped row went back on the
  page. The bug was one list, not one key.

THE ELECTION IS THE REASON THIS IS SAFE, AND IT IS NOT THE OBVIOUS ONE
══════════════════════════════════════════════════════════════════════
`twin_identity_rank` breaks a tie on the lower row id LAST, and 15311614 is the
LOWER id — so a fold that elected on id would have kept the live row and
dropped the Final, which is the worse page, not the better one. What actually
decides it is the ESPN id, two positions earlier. Both rows carry a score
(3-1), so the first position is a tie and cannot help.
`test_the_election_does_not_come_down_to_the_row_id` is that sentence as a test:
it is the one to read before widening anything here.

WHAT THIS RULE DELIBERATELY DOES NOT DO
═══════════════════════════════════════
It drops an upcoming row only when the survivor is on the RESULTS rail — a card
this page is already printing with a score on it. A survivor on the unreported
rail is not a Final, and dropping there would leave a reader with nothing that
says what happened; that half of the old rule is still asserted, in
`test_league_past_rails_twin_fold_5746.py`.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes import league_futures
from app.routes.league_futures import _folded_past_rails
from app.utils.event_twin_fold import twin_fold_key, twin_identity_rank

KICKOFF = datetime(2026, 9, 13, 18, 15, tzinfo=timezone.utc)


def _Row(id, home, away, commence, sources=None, sport_id=53232, status="scheduled"):
    """A real, UNATTACHED `Event` ORM instance — not a stand-in.

    The sibling file's reason, which holds here too: the fold writes unioned
    sources with `set_committed_value`, which reaches for `_sa_instance_state`
    and raises on anything that merely has the right attribute names. A plain
    fake would fall into the helper's own `except` and come back unfolded — the
    test would fail for a reason that is not the product, or pass for one.
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


def _the_live_row(id=15311614, when=KICKOFF):
    """15311614 — on `upcoming_games`, `live`, no provider id of any kind."""
    row = _Row(
        id,
        "St. Louis Cardinals",
        "Chicago White Sox",
        when,
        sources={"mlb": {"value": 0.852}},
        status="live",
    )
    row.home_score = 3
    row.away_score = 1
    return row


def _the_final(id=15311666, when=KICKOFF):
    """15311666 — on `recent_results`, `completed`, ESPN-anchored."""
    row = _Row(
        id,
        "St. Louis Cardinals",
        "Chicago White Sox",
        when,
        sources={"mlb": {"value": 0.826}, "espn": {"value": 0.752}},
        status="completed",
    )
    row.home_score = 3
    row.away_score = 1
    row.espn_id = "401816926"
    row.external_id = "c57fd4622cf0e5105ce22874c061913c"
    return row


class TestTheProductionSpecimen:
    def test_the_finished_game_is_not_also_live_on_the_same_page(self):
        results, _u, upcoming = _folded_past_rails(
            [_the_final()], [], [_the_live_row()]
        )
        assert [e.id for e in results] == [15311666]
        assert [e.id for e in upcoming] == [], (
            "the live twin of a printed Final is still on the upcoming rail"
        )

    def test_the_card_the_reader_keeps_is_the_one_with_the_result(self):
        results, _u, _g = _folded_past_rails([_the_final()], [], [_the_live_row()])
        kept = results[0]
        assert kept.status == "completed"
        assert (kept.home_score, kept.away_score) == (3, 1)
        assert kept.espn_id == "401816926"

    def test_both_rows_really_are_one_fixture_to_the_key(self):
        """Not a key-strictness problem: exact minute, exact squashed names."""
        assert twin_fold_key(_the_final()) == twin_fold_key(_the_live_row())

    def test_the_election_does_not_come_down_to_the_row_id(self):
        """The lower id is the LIVE row, so id-order would serve the lie.

        Read this before touching `twin_identity_rank`. The score position is a
        tie here — both rows carry 3-1 — so the ESPN id is the whole margin.
        """
        live, final = _the_live_row(), _the_final()
        assert live.id < final.id
        assert twin_identity_rank(final) > twin_identity_rank(live)

        # The margin is real and doubled: the ESPN id at position 2, and — on
        # these two rows, though not by design — source count at position 4.
        # Strip BOTH and the election falls through to the id tiebreak, which
        # points at the live row. That is the page #5532 would have served if
        # the fold had elected on row order, and it is worse than serving two
        # cards: the Final would have been the row that disappeared.
        blinded = _the_final()
        blinded.espn_id = None
        blinded.external_id = None
        blinded.win_probability_sources = {"mlb": {"value": 0.826}}
        assert twin_identity_rank(blinded) < twin_identity_rank(live)


class TestWhatItMustNeverDrop:
    def test_an_upcoming_row_with_no_final_anywhere_is_untouched(self):
        """The rule is not 'drop live rows' — it is 'drop a printed duplicate'."""
        _r, _u, upcoming = _folded_past_rails([], [], [_the_live_row()])
        assert [e.id for e in upcoming] == [15311614]

    def test_a_different_fixture_at_the_same_instant_is_untouched(self):
        other = _Row(15311700, "Boston Red Sox", "Kansas City Royals", KICKOFF)
        _r, _u, upcoming = _folded_past_rails([_the_final()], [], [other])
        assert [e.id for e in upcoming] == [15311700]

    def test_a_doubleheaders_second_leg_keeps_its_card(self):
        leg_two = _the_live_row(id=15311615, when=KICKOFF + timedelta(hours=4))
        _r, _u, upcoming = _folded_past_rails([_the_final()], [], [leg_two])
        assert [e.id for e in upcoming] == [15311615]

    def test_a_row_that_cannot_be_keyed_is_kept(self):
        """No team name ⇒ unprovable as anybody's twin ⇒ leave it alone."""
        nameless = _Row(15311701, None, "Chicago White Sox", KICKOFF)
        _r, _u, upcoming = _folded_past_rails([_the_final()], [], [nameless])
        assert [e.id for e in upcoming] == [15311701]

    def test_a_survivor_on_the_upcoming_rail_never_drops_itself(self):
        """The Final loses the election (no ids, no score) — the live row is the
        survivor and must stay, even though it is the one on this rail."""
        weak_final = _Row(
            15311888, "St. Louis Cardinals", "Chicago White Sox", KICKOFF,
            status="completed",
        )
        results, _u, upcoming = _folded_past_rails([weak_final], [], [_the_live_row()])
        assert [e.id for e in upcoming] == [15311614]
        assert results == []


class TestItNeverTakesThePageDown:
    def test_a_fold_that_raises_serves_all_three_rails_unfolded(self, monkeypatch):
        """Gotcha #42: the fold improves the page, it never gates having one."""

        def boom(_events):
            raise RuntimeError("fold exploded")

        monkeypatch.setattr(league_futures, "fold_twin_events", boom)
        results, _u, upcoming = _folded_past_rails(
            [_the_final()], [], [_the_live_row()]
        )
        assert [e.id for e in results] == [15311666]
        assert [e.id for e in upcoming] == [15311614]

    def test_a_row_that_raises_while_keying_costs_only_its_own_drop(
        self, monkeypatch
    ):
        """One bad item must never wipe the pass (gotcha #42).

        The key call this rule adds runs over rails that are already built, so a
        single row with a surprising `commence_time` must cost that row its
        comparison and nothing else — the Final still serves, the page still
        renders.
        """
        real = league_futures.twin_fold_key

        def selective(event):
            if getattr(event, "id", None) == 15311614:
                raise TypeError("surprising commence_time")
            return real(event)

        monkeypatch.setattr(league_futures, "twin_fold_key", selective)
        results, _u, upcoming = _folded_past_rails(
            [_the_final()], [], [_the_live_row()]
        )
        assert [e.id for e in results] == [15311666]
        assert [e.id for e in upcoming] == [15311614]


class TestTheSlotItSpends:
    def test_the_rail_is_capped_downstream_so_the_drop_is_backfilled(self):
        """The half of this trade that was never measured before #5532.

        The old rule feared "a card slot with nothing left to backfill it". But
        `upcoming_games_query` fetches `UPCOMING_GAMES_LIMIT + 1 + scan_depth +
        fold_headroom` rows and the cap is not applied until
        `_grows[:UPCOMING_GAMES_LIMIT]`, which is BELOW this call — so on any
        league with more fixtures than the cap the next real game slides up and
        the rail still serves eight. The MLB payload that produced the specimen
        carried `upcoming_games_has_more: True`, so this fix cost that page zero
        cards.

        If the slice ever moves above the fold, that reasoning is void and the
        trade has to be argued again on its own merits.
        """
        source = inspect.getsource(league_futures)
        fold_at = source.index(
            "_r_events, _u_events, _g_events = _folded_past_rails("
        )
        # The needle is the STATEMENT, not the slice: the bare slice text also
        # appears in the docstring above explaining this very ordering, and
        # `str.index` would have graded that warning label instead of the code.
        assert fold_at < source.index("upcoming_games = _grows[:UPCOMING_GAMES_LIMIT]")
        assert "fold_headroom=UPCOMING_TWIN_FOLD_HEADROOM" in source
