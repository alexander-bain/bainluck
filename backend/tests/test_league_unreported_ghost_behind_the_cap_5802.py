"""#5802 — the rail says "No result reported" over a game we have the score for.

THE SPECIMEN, MEASURED ON PRODUCTION 17:5xZ 2026-09-14
══════════════════════════════════════════════════════
`GET /api/leagues/baseball_mlb`. SIX of six cards on the NO RESULT REPORTED rail
are `suspended` StatPal rows from 2026-09-06, and every one of them has a
completed, ESPN-anchored twin at the same kickoff minute holding the final
score::

    15298230 Astros/DBacks    -> 15305469 completed 2-3   espn 401816834
    15298231 Royals/Jays      -> 15305470 completed 6-1   espn 401816837
    15298232 Rangers/Rays     -> 15305471 completed 8-6   espn 401816836
    15298408 Padres/Yankees   -> 15305474 completed 4-3   espn 401816840
    15298409 Mariners/A's     -> 15305473 completed 2-0   espn 401816839
    15298326 Rockies/Cardinals-> 15305472 completed 8-10  espn 401816838

Five of them print `No result reported · last score 2-0` — a final score and a
denial that the result is known, on one line. The sixth prints no score at all.

🔴 THE SIXTH IS THE ONE THAT MATTERS TO THIS FILE, because #5802 was filed
saying it was honestly unreported — "no twin and no score". It has both. The
pairing that found the other five was name-equality, and the ghost spells its
home side `St.Louis Cardinals` against the Final's `St. Louis Cardinals`. That
missing space hid the pair from the analysis exactly as native/098 measured it
hiding seven Cardinals rows from a join, which is why every key in this area
normalises rather than compares. `test_the_sixth_card_is_a_ghost_too` is that
correction as a test.

WHY `_folded_past_rails` — WRITTEN FOR PRECISELY THIS — FOLDED NOTHING
══════════════════════════════════════════════════════════════════════
Its #5746 argument is that `twin_fold_key` requires the same `commence_time` to
the minute, so twins always share a kickoff and "can never be separated by a
rail's TIME bound". That is TRUE, and it is not the bound that separates these.
THE ROW CAP IS. Both past rails carry the same 14-day `RESULTS_LOOKBACK_DAYS`
and each is `ORDER BY commence_time DESC LIMIT n` over populations of utterly
different density: MLB plays fifteen games a day, so the results rail's eight
slots span about ONE day, while six unreported rows reach back EIGHT. Not one of
the six Finals above was inside the results rail's eight.

So the fold was handed one member of every pair and, correctly, folded nothing —
`fold.dropped_ids` is empty on this specimen, which took the function down its
early-return branch before it could do anything else.
`test_the_fold_alone_drops_nothing_on_this_specimen` is that sentence as a test:
like its #5746 sibling it fails on the design, not the implementation, and it is
the one to read first.

The repair is to ask the settled rail directly, at the unreported rail's own
kickoff instants, unbounded by the results rail's cap
(`finals_behind_the_results_cap_query`) and hand the answer to the fold as
context. The Finals so found are never served — they answer a question about a
row that IS served.

WHAT THIS FILE REFUSES TO LET THE FIX BECOME
════════════════════════════════════════════
A rail called NO RESULT REPORTED must keep reporting the rows that genuinely
have no result — that rail exists because #3211 found 171 US Open matches on no
rail whatsoever. `test_a_genuinely_unreported_game_keeps_its_card` and
`test_a_final_at_another_minute_suppresses_nothing` are the over-suppression
guards, and they are the reason the query is keyed on the kickoff instant rather
than on "this league had a Final that day".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes.league_futures import _folded_past_rails
from app.utils.event_twin_fold import fold_twin_events

# 2026-09-06 19:10Z — the Rockies/Cardinals kickoff, the sixth card's own minute.
BASE = datetime(2026, 9, 6, 19, 10, tzinfo=timezone.utc)


def _Row(id, home, away, commence, sport_id=1, status="scheduled"):
    """A real, UNATTACHED `Event` ORM instance — not a stand-in.

    Same reason as `test_league_past_rails_twin_fold_5746._Row`: the fold writes
    unioned sources through `set_committed_value`, which reaches for
    `_sa_instance_state` and raises on anything that merely has the right
    attribute names. A plain fake would fall into the helper's own `except` and
    come back unfolded — passing, or failing, for a reason that is not the
    product.
    """
    return Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport_id,
        win_probability_sources={},
        status=status,
    )


def _off_page_final(
    id=15305472, when=BASE, home="St. Louis Cardinals", away="Colorado Rockies"
):
    """The completed ESPN row — real, scored, and NOT on the page.

    It is off the page because the results rail's eight slots went to games from
    the last day. Nothing about the row itself is unusual; that is the point.
    """
    row = _Row(id, home, away, when, status="completed")
    row.home_score = 8
    row.away_score = 10
    row.espn_id = "401816838"
    return row


def _ghost(id=15298326, when=BASE, home="St.Louis Cardinals", away="Colorado Rockies"):
    """The StatPal row on the unreported rail: `suspended`, no score, no ids.

    `St.Louis` is spelled exactly as production spells it — the missing space
    that hid this pair from #5802's own analysis.
    """
    return _Row(id, home, away, when, status="suspended")


class TestTheProductionSpecimen:
    def test_the_ghost_does_not_claim_a_result_is_missing(self):
        results, unreported, _g = _folded_past_rails(
            [], [_ghost()], [], [_off_page_final()]
        )
        assert [e.id for e in unreported] == []
        assert results == []

    def test_the_sixth_card_is_a_ghost_too(self):
        """#5802 called this one honestly unreported. It has a Final: 8-10.

        The correction the issue needs, pinned so it cannot be re-lost: the two
        rows differ ONLY by the space in `St.Louis`, and the key sees through it.
        """
        ghost, final = _ghost(), _off_page_final()
        assert ghost.home_team_name != final.home_team_name
        _r, unreported, _g = _folded_past_rails([], [ghost], [], [final])
        assert unreported == []

    def test_the_fold_alone_drops_nothing_on_this_specimen(self):
        """The design failure, not the implementation — read this one first.

        Each ghost is the only member of its pair on the page, so the union the
        fold is handed has no twin in it and `dropped_ids` is empty. That empty
        set took `_folded_past_rails` down its early return, which is how six
        false cards survived a function written to remove them.
        """
        fold = fold_twin_events([_ghost()])
        assert fold.dropped_ids == []

    def test_the_off_page_final_is_never_served(self):
        """It is CONTEXT. It answers a question; it does not become a card."""
        final = _off_page_final()
        results, unreported, upcoming = _folded_past_rails([], [_ghost()], [], [final])
        assert final.id not in [e.id for e in (*results, *unreported, *upcoming)]

    def test_all_six_production_ghosts_go(self):
        """The whole rail as measured, not one specimen generalised."""
        pairs = [
            (15298230, 15305469, "Houston Astros", "Arizona Diamondbacks"),
            (15298231, 15305470, "Kansas City Royals", "Toronto Blue Jays"),
            (15298232, 15305471, "Texas Rangers", "Tampa Bay Rays"),
            (15298408, 15305474, "San Diego Padres", "New York Yankees"),
            (15298409, 15305473, "Seattle Mariners", "Athletics"),
            (15298326, 15305472, "Colorado Rockies", "St.Louis Cardinals"),
        ]
        ghosts, finals = [], []
        for i, (gid, fid, home, away) in enumerate(pairs):
            when = BASE + timedelta(minutes=i)
            ghosts.append(_Row(gid, home, away, when, status="suspended"))
            f = _Row(fid, home, away.replace("St.L", "St. L"), when, status="completed")
            f.home_score, f.away_score = 2, 3
            f.espn_id = str(401816834 + i)
            finals.append(f)
        _r, unreported, _g = _folded_past_rails([], ghosts, [], finals)
        assert unreported == []


class TestItDoesNotEmptyTheRailItIsFixing:
    def test_a_genuinely_unreported_game_keeps_its_card(self):
        """No Final anywhere ⇒ the rail still reports it. #3211's whole point."""
        ghost = _ghost()
        _r, unreported, _g = _folded_past_rails([], [ghost], [], [])
        assert [e.id for e in unreported] == [ghost.id]

    def test_a_final_at_another_minute_suppresses_nothing(self):
        """Keyed on the fixture, never on "this league had a Final that day"."""
        other = _off_page_final(id=15305999, when=BASE + timedelta(minutes=35))
        _r, unreported, _g = _folded_past_rails([], [_ghost()], [], [other])
        assert [e.id for e in unreported] == [15298326]

    def test_a_final_for_another_fixture_suppresses_nothing(self):
        """Same minute, different teams — MLB starts many games at :10."""
        other = _off_page_final(
            id=15305469, home="Houston Astros", away="Arizona Diamondbacks"
        )
        _r, unreported, _g = _folded_past_rails([], [_ghost()], [], [other])
        assert [e.id for e in unreported] == [15298326]

    def test_the_old_behaviour_is_what_you_get_with_no_finals_to_hand(self):
        """The control: the suppression is never unconditional.

        If a later edit makes the unreported rail drop rows without a Final to
        justify it, this is the test that reddens.
        """
        _r, unreported, _g = _folded_past_rails([], [_ghost()], [], ())
        assert len(unreported) == 1


class TestTheOtherRailsAreUntouched:
    def test_the_results_rail_is_not_shortened_by_an_off_page_final(self):
        served_final = _off_page_final(id=15311666, when=BASE + timedelta(minutes=90))
        results, _u, _g = _folded_past_rails(
            [served_final], [], [], [_off_page_final()]
        )
        assert [e.id for e in results] == [15311666]

    def test_the_upcoming_rail_is_not_shortened_by_an_off_page_final(self):
        """#5532's trade is keyed on Finals the page PRINTS, and stays that way.

        An off-page Final shortens the unreported rail only: that card asserts
        something false, while dropping an upcoming card here would spend a slot
        the headroom argument says we cannot pay for.
        """
        soon = _Row(15312256, "St. Louis Cardinals", "San Francisco Giants",
                    BASE + timedelta(days=8))
        _r, _u, upcoming = _folded_past_rails([], [], [soon], [_off_page_final()])
        assert [e.id for e in upcoming] == [15312256]


class TestItNeverCostsThePageItsRails:
    def test_a_final_that_cannot_be_keyed_is_ignored_not_fatal(self):
        """Gotcha #42 — an unkeyable context row suppresses nothing, quietly.

        `_twin_key_or_none` swallows and returns None; a None key must not
        collide with a ghost's real key and must not raise out of the rail.
        """
        broken = _off_page_final()
        broken.commence_time = "not a datetime"
        _r, unreported, _g = _folded_past_rails([], [_ghost()], [], [broken])
        assert [e.id for e in unreported] == [15298326]

    def test_a_ghost_that_cannot_be_keyed_keeps_its_card(self):
        ghost = _ghost()
        ghost.commence_time = "not a datetime"
        _r, unreported, _g = _folded_past_rails([], [ghost], [], [_off_page_final()])
        assert len(unreported) == 1
