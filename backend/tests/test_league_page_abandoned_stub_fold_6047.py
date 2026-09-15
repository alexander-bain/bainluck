"""#6047 — a La Liga fixture may not be a Final AND still awaiting its score.

THE PAGE THIS EXISTS FOR, MEASURED ON PRODUCTION 02:50Z 2026-09-13
══════════════════════════════════════════════════════════════════
`/sport/soccer/laliga` at 390px. Scrolling, a reader meets Real Racing Club de
Santander v Alavés **twice inside one screen** — `Sep 12 · FINAL · 2 SANTANDER –
1 ALAVÉS`, and ~800px below it, under **NO RESULT REPORTED**, the same fixture
again at `51% / 49%`. Athletic Bilbao v Elche and Osasuna v Espanyol the same.
Each pair is one ESPN row and one Odds API row::

    15298235  Racing Santander v Alavés  2026-09-12 12:00Z  espn      completed  2–1
    15298075  "                          2026-09-13 19:00Z  odds_api  suspended   —

The club names are **byte-identical on both sides**. What differs is the clock:
the Odds API row carries a fabricated `19:00:00Z` 31 hours after the real
kick-off and on the next UTC day, `suspended`, never scored — a card that prints
"No result reported" forever. This is ship 3's own sentence ("a marquee game
appears once") failing on a marquee league page in launch week.

WHY NO EXISTING TIER REACHES IT, AND WHY NONE OF THEM SHOULD BE WIDENED
═══════════════════════════════════════════════════════════════════════
`twin_fold_key` needs the same minute; `SOCCER_KICKOFF_DRIFT` allows five
minutes; `_soccer_bucket_key` will not even make two rows candidates across a UTC
day. Thirty-one hours clears all three. Widening the drift bound would swallow
the 30-minute re-mints #5918 excluded on purpose and the three-hour Kalshi rows
#5905 corrects upstream — so `TestItStaysOffOtherShipsPopulations` below pins
that those two classes are still refused, and `TestTheRefusals` pins the gates
that pay for dropping the clock.

🔴 THE FABRICATED STAMP IS NOT THE DISCRIMINATOR, AND THAT IS THE TRAP.
Four rows share the exact second `19:00:00Z`, which reads as a fabrication
fingerprint until you check the fifth: `15298074` Atlético Madrid v Real Sociedad
carries the same second and really kicked off then. Simultaneous kick-offs are
ordinary in soccer. `test_a_shared_exact_second_is_never_the_reason` is that
sentence as a test.

🔴 AND THE TIER IS SOCCER-ONLY BECAUSE OF A CONTRACT THAT ALREADY EXISTED.
Orientation excludes a reverse fixture and a two-legged tie's return leg, but not
a **baseball doubleheader** — two real games, one pair, one orientation, hours
apart, leg two stranded scoreless. `test_league_past_rails_twin_fold_5746.py`'s
`test_a_doubleheaders_second_leg_keeps_its_own_card` is that contract and this
tier folded it until the soccer gate went in. It is restated here, from this
tier's side, so that widening the gate reddens the file that widened it.

MEASURED BY DRIVING `fold_twin_events` OVER PRODUCTION, 2026-09-14 (artifact
`artifacts-lane1-310/measurement-6047.txt`, all 1,549 soccer rows a reader can
reach in `[now-3d, now+8d]`, folded league by league the way a reader meets
them):

    master                             73 rows folded
    with this tier                     88 rows folded   (+15, 5 leagues)
    master folds this tier loses        0
    survivors changed by this tier      0
    folded groups with two espn_ids     0   <- two real games merged
    folded groups with two scorelines   0   <- ditto
    losers not `odds_api` / `suspended` 0
    nearest new pair to the 30-min class   17.0h away
    nearest new pair to the 3-hour class   14.5h away
    the same rows relabelled baseball:  the tier adds 0
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, Sport
from app.routes.league_futures import _folded_past_rails
from app.utils.event_twin_fold import (
    fold_twin_events,
    is_abandoned_stub,
    is_finished_with_result,
    twin_fold_key,
)

#: The real kick-off of `15298235`, Racing Santander v Alavés.
KICKOFF = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)

#: The stamp all four Odds API rows carry, 31 hours later and on the next UTC
#: day. `15298074` Atlético Madrid v Real Sociedad carries it legitimately.
FABRICATED = datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)

LA_LIGA = "soccer_spain_la_liga"


def _row(
    id,
    *,
    home,
    away,
    commence,
    status,
    home_score=None,
    away_score=None,
    espn_id=None,
    sources=None,
    sport_key=LA_LIGA,
    sport_id=7,
):
    """A real, UNATTACHED `Event` — not a stand-in, for #5746's reason.

    The fold's venue union writes through `set_committed_value`, which reaches
    for `_sa_instance_state` and raises on anything that merely has the right
    attribute names; a plain fake falls into the caller's `except` and comes back
    unfolded, so the test would pass for a reason that is not the product.

    🔴 `sport` IS ASSIGNED, ALWAYS, AND THAT IS NOT BOILERPLATE. This tier is
    soccer-gated through `loaded_sport_key`, which answers `None` for a row whose
    `Event.sport` the caller never loaded — and `None` is the skip branch. A
    fixture that forgets it produces a whole file of green tests over a pass that
    never ran. `test_a_row_whose_sport_is_not_loaded_is_never_folded` pins the
    branch deliberately; every other fixture here loads it.
    """
    row = Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport_id,
        status=status,
        win_probability_sources=sources or {},
    )
    row.sport = Sport(id=sport_id, key=sport_key)
    row.home_score = home_score
    row.away_score = away_score
    row.espn_id = espn_id
    return row


def _final(id=15298235, *, when=KICKOFF, home="Real Racing Club de Santander"):
    """The ESPN row on the RESULTS rail: `completed`, 2–1, an ESPN id."""
    return _row(
        id,
        home=home,
        away="Alavés",
        commence=when,
        status="completed",
        home_score=2,
        away_score=1,
        espn_id="401882881",
        sources={"espn": 0.55},
    )


def _stub(id=15298075, *, when=FABRICATED, home="Real Racing Club de Santander"):
    """The Odds API row on the UNREPORTED rail: `suspended`, no score, no ids."""
    return _row(
        id,
        home=home,
        away="Alavés",
        commence=when,
        status="suspended",
        sources={"betting": 0.51},
    )


class TestTheProductionSpecimen:
    """The three fixtures Alex would have met scrolling one La Liga page."""

    def test_the_finished_game_is_not_also_awaiting_its_score(self):
        results, unreported, _ = _folded_past_rails([_final()], [_stub()], [])
        assert [e.id for e in results] == [15298235]
        assert unreported == []

    def test_the_survivor_is_the_row_that_says_what_happened(self):
        results, _, _ = _folded_past_rails([_final()], [_stub()], [])
        assert (results[0].home_score, results[0].away_score) == (2, 1)
        assert results[0].espn_id == "401882881"

    def test_all_three_la_liga_pairs_go_in_one_pass(self):
        """The page as the reader met it, not one pair in isolation."""
        finals = [
            _final(),
            _final(15298237, when=datetime(2026, 9, 12, 16, 30, tzinfo=timezone.utc),
                   home="Athletic Bilbao"),
            _final(15298236, when=datetime(2026, 9, 12, 14, 15, tzinfo=timezone.utc),
                   home="CA Osasuna"),
        ]
        stubs = [
            _stub(),
            _stub(15298076, home="Athletic Bilbao"),
            _stub(15298079, home="CA Osasuna"),
        ]
        results, unreported, _ = _folded_past_rails(finals, stubs, [])
        assert len(results) == 3 and unreported == []

    def test_the_31_hour_gap_is_why_no_existing_tier_reached_it(self):
        """The design claim. If this ever fails, read the tiers before deleting."""
        assert twin_fold_key(_final()) != twin_fold_key(_stub())
        assert _stub().commence_time - _final().commence_time == timedelta(hours=31)
        # Each row alone folds nothing; only together does one go.
        assert fold_twin_events([_final()]).dropped_ids == []
        assert fold_twin_events([_stub()]).dropped_ids == []
        assert fold_twin_events([_final(), _stub()]).dropped_ids == [15298075]

    def test_the_survivor_gains_the_venue_stranded_on_the_stub(self):
        """A fold that dropped the Odds API price would trade one bug for another."""
        results, _, _ = _folded_past_rails([_final()], [_stub()], [])
        assert results[0].win_probability_sources == {"espn": 0.55, "betting": 0.51}

    def test_the_caller_is_told_which_row_absorbed_the_stub(self):
        """#5532's `survivor_of`, which `_folded_past_rails` reads. Not
        reconstructible from key equality here — the keys deliberately differ."""
        fold = fold_twin_events([_final(), _stub()])
        assert fold.survivor_of == {15298075: 15298235}


class TestTheRefusals:
    """Each gate that pays for this tier having no clock bound at all."""

    def test_a_future_kickoff_is_a_real_fixture_and_stays(self):
        """The one gate that stops a season's next meeting being swallowed."""
        ahead = _stub(15298999, when=datetime.now(timezone.utc) + timedelta(days=6))
        results, unreported, _ = _folded_past_rails([_final()], [ahead], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_a_stub_that_has_a_score_is_not_a_stub(self):
        scored = _stub(15298998)
        scored.home_score, scored.away_score = 0, 0
        assert not is_abandoned_stub(scored)
        assert fold_twin_events([_final(), scored]).dropped_ids == []

    def test_a_result_less_survivor_is_refused_so_the_defect_cannot_move(self):
        """Folding one 'No result reported' card into another fixes nothing."""
        empty = _row(15298997, home="Real Racing Club de Santander", away="Alavés",
                     commence=KICKOFF, status="completed")
        assert not is_finished_with_result(empty)
        assert fold_twin_events([empty, _stub()]).dropped_ids == []

    def test_the_reverse_fixture_is_never_folded(self):
        """Home and away swapped is the other leg, or the other half of a season."""
        away_leg = _row(15298996, home="Alavés", away="Real Racing Club de Santander",
                        commence=FABRICATED, status="suspended")
        results, unreported, _ = _folded_past_rails([_final()], [away_leg], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_two_finals_for_one_fixture_refuse_the_fold_whole(self):
        """Nothing here can say which contest a stranded stub belonged to."""
        second = _final(15298995, when=KICKOFF + timedelta(days=1))
        fold = fold_twin_events([_final(), second, _stub()])
        assert fold.dropped_ids == []

    def test_a_different_fixture_is_untouched(self):
        other = _row(15298994, home="Sevilla", away="Valencia",
                     commence=FABRICATED, status="suspended")
        results, unreported, _ = _folded_past_rails([_final()], [other], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_a_shared_exact_second_is_never_the_reason(self):
        """`15298074` Atlético Madrid v Real Sociedad carries `19:00:00Z` and
        really kicked off then. Four rows sharing one second is not a
        fingerprint, and a tier that treated it as one would delete a real card."""
        real = _row(15298074, home="Atlético Madrid", away="Real Sociedad",
                    commence=FABRICATED, status="completed",
                    home_score=3, away_score=0, espn_id="401882884")
        fold = fold_twin_events([_final(), _stub(), real])
        assert fold.dropped_ids == [15298075]
        assert real.id not in fold.dropped_ids
        assert real in fold.events

    def test_a_row_whose_sport_is_not_loaded_is_never_folded(self):
        """`loaded_sport_key` answers `None` for an unloaded relationship and
        `None` is the skip branch — so a caller that does not `selectinload`
        gets today's page, never a fold this pass cannot justify."""
        blind = Event(
            id=15298993,
            home_team_name="Real Racing Club de Santander",
            away_team_name="Alavés",
            commence_time=FABRICATED,
            sport_id=7,
            status="suspended",
            win_probability_sources={},
        )
        blind.home_score = blind.away_score = blind.espn_id = None
        assert fold_twin_events([_final(), blind]).dropped_ids == []


class TestTheSoccerGateIsTheDoubleheaderContract:
    """#5746's `test_a_doubleheaders_second_leg_keeps_its_own_card`, from this
    tier's side. Orientation cannot exclude leg two of a baseball doubleheader —
    only the sport can — so the gate is restated where a widening would happen."""

    def _baseball(self, id, status, **kw):
        return _row(id, home="Chicago White Sox", away="St. Louis Cardinals",
                    sport_key="baseball_mlb", sport_id=1, status=status, **kw)

    def test_a_baseball_doubleheaders_second_leg_keeps_its_own_card(self):
        leg_one = self._baseball(15309733, "completed", commence=KICKOFF,
                                 home_score=7, away_score=3, espn_id="401816896")
        leg_two = self._baseball(15304909, "suspended",
                                 commence=KICKOFF + timedelta(hours=4))
        results, unreported, _ = _folded_past_rails([leg_one], [leg_two], [])
        assert (len(results), len(unreported)) == (1, 1)

    def test_the_identical_shape_in_soccer_does_fold(self):
        """The control. Without it the test above passes on a dead pass."""
        results, unreported, _ = _folded_past_rails(
            [_final()], [_stub(when=KICKOFF + timedelta(hours=4))], []
        )
        assert (len(results), len(unreported)) == (1, 0)


class TestItStaysOffOtherShipsPopulations:
    """The two classes this tier's docstring promises not to reach. Both are
    live ships; folding them here would make their own guards pass for the wrong
    reason and quietly retire work that is still doing something."""

    @pytest.mark.parametrize(
        "gap, owner",
        [(timedelta(minutes=30), "#5918 re-mints"), (timedelta(hours=3), "#5905 Kalshi")],
    )
    def test_a_scoreless_row_at_another_ships_offset_is_still_refused(self, gap, owner):
        """Both rows scoreless, so neither is a Final — this tier says nothing
        and the population stays with the ship that owns it."""
        near = _stub(15298992, when=KICKOFF + gap)
        sibling = _row(15298991, home="Real Racing Club de Santander", away="Alavés",
                       commence=KICKOFF, status="scheduled")
        assert fold_twin_events([sibling, near]).dropped_ids == [], owner

    def test_the_tier_adds_nothing_the_earlier_tiers_already_did(self):
        """A same-minute pair is #4100's; this tier must not claim it. Measured
        fleet-wide as 0 survivors changed — here as the mechanism."""
        same_minute = _stub(15298990, when=KICKOFF)
        fold = fold_twin_events([_final(), same_minute])
        assert fold.dropped_ids == [15298990]
        assert twin_fold_key(_final()) == twin_fold_key(same_minute)
