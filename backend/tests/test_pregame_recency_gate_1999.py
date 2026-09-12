"""#1999 — relative recency decay is an IN-PLAY rule; before kickoff it is off.

THE SPECIMEN, read off production 2026-09-11 23:30Z, is a marquee fixture:

    15297691  Aston Villa v Nottingham Forest (EPL, kickoff +14h)
        win_probability_sources.betting     0.6339  stamped 2026-09-06T17:27:22Z
        win_probability_sources.kalshi      0.4250  stamped 2026-09-11T23:21:04Z
        GET /api/events/15297691 -> hero_probability 0.425, source "blend"

`betting` is five days older than `kalshi`, so `_relative_staleness_multiplier`
took it to its 0.1 floor (3.0 -> 0.3), the single Kalshi price outweighed the
sportsbook consensus, and the page printed **42%** under the caption
**"11 sportsbooks"** while its own chart line sat at ~59% for three days. That
is #240's hero-disagrees-with-its-own-chart contradiction rebuilt out of the
decay instead of out of the mean.

AND THE CHART WAS THE ONE TELLING THE TRUTH. Nine books quoted this match
within 30 hours of that read (`odds_snapshots`, devigged): 0.5741 - 0.5872,
mean **0.5809**. So the error bar on each candidate hero is

    served today   0.425   -> 15.6 points from the book consensus
    with this gate 0.6339  ->  5.3 points from the book consensus

This ship closes the first gap. The residual 5.3 is NOT this gap and is not
fixed here: the `betting` entry itself was last written on 2026-09-06 while the
books were being polled all day, which is a writer-reach defect filed on its own
terms. A stale stored value is repaired by refreshing it, never by routing the
hero around it onto a single venue that is three times further off.

WHY PRE-GAME AND NOT `status == 'live'`, which is what #1999 proposed. Measured
over the whole -6h/+48h board with the shipped aggregator:

    status       multi-source   decay moves the number   median    max
    scheduled            362                      128    12.0pt   30.0pt
    suspended             25                       14     7.8pt   43.0pt
    completed             32                        3     1.0pt    3.8pt
    live                  16                        1     0.5pt    0.5pt

Decaying only when live would ALSO stop decaying `suspended`, and there the
decay is currently right: those 14 rows are finished games whose Kalshi leg has
settled to 0.01/0.99, and undecaying them republishes the last in-play
sportsbook line over a settled market. Refusing the decay only where the game
has not started leaves live, suspended, completed and voided bit-for-bit
unchanged — the blast radius is exactly the population whose premise fails.

NO WALL CLOCK, by construction, exactly as #1829's own suite: every stamp below
is a literal and the decay compares stamps to each other. `clock_sweep.py` has
nothing to find here.
"""

from types import SimpleNamespace

import pytest

from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    _relative_decay_applies,
    compute_aggregate_probability,
    effective_source_weights,
)

# ── The specimen, verbatim from production ───────────────────────────────────

BETTING_VALUE = 0.6339
KALSHI_VALUE = 0.425
BOOK_CONSENSUS_TODAY = 0.5809  # 9 books, devigged, within 30h of the read

SPECIMEN = {
    "betting": {"value": BETTING_VALUE, "updated_at": "2026-09-06T17:27:22.934725+00:00"},
    "kalshi": {"value": KALSHI_VALUE, "updated_at": "2026-09-11T23:21:04.214200+00:00"},
}


def _event(sources, status):
    return SimpleNamespace(
        win_probability_sources=sources,
        status=status,
        espn_win_prob_home=None,
        opening_home_probability=None,
    )


def _hero(sources, status):
    return compute_aggregate_probability(_event(sources, status), status)


class TestTheSpecimen:
    """One JSONB, two statuses, two different right answers."""

    def test_a_pregame_hero_is_the_sportsbook_consensus(self):
        """THE SHIP. Villa's card stops printing one venue's 42%."""
        assert _hero(SPECIMEN, "scheduled") == pytest.approx(BETTING_VALUE)

    def test_and_that_is_the_closer_of_the_two_to_what_the_books_actually_say(self):
        """The ship is a MEASURED improvement, not merely a different number.

        Without this assertion the test above is satisfied by any change that
        happens to prefer `betting`, including one that prefers it for a wrong
        reason. Pinning the direction against the independently-measured book
        consensus is what makes it a claim about the reader's screen.
        """
        served_today = KALSHI_VALUE
        with_this_gate = BETTING_VALUE
        assert abs(with_this_gate - BOOK_CONSENSUS_TODAY) < abs(
            served_today - BOOK_CONSENSUS_TODAY
        )

    def test_the_same_readings_in_play_still_decay(self):
        """THE OTHER ARM, and the one that makes the first arm a boundary.

        Identical JSONB, `status='live'`: #1829's rule still runs, `betting`
        still falls to its floor, and the hero is still the market. A change
        that switched the decay off everywhere passes the first test and fails
        this one.
        """
        assert _hero(SPECIMEN, "live") == pytest.approx(KALSHI_VALUE)

    def test_the_pregame_weights_are_the_base_weights(self):
        """Not just the value — the weights the divergence gate also reads."""
        keys, _values, weights = effective_source_weights(
            _event(SPECIMEN, "scheduled"), "scheduled"
        )
        by_source = dict(zip(keys, weights))
        assert by_source["betting"] == pytest.approx(SOURCE_WEIGHTS["betting"])
        assert by_source["kalshi"] == pytest.approx(SOURCE_WEIGHTS["kalshi"])

    def test_in_play_the_heavier_source_really_is_demoted_to_its_floor(self):
        """The control for the assertion above: 3.0 -> 0.3 while live."""
        keys, _values, weights = effective_source_weights(
            _event(SPECIMEN, "live"), "live"
        )
        by_source = dict(zip(keys, weights))
        assert by_source["betting"] == pytest.approx(SOURCE_WEIGHTS["betting"] * 0.1)


class TestTheBoundaryIsExactlyOneStatus:
    """Every status the gate does NOT move, pinned so a widening is visible.

    `suspended` is the one that matters and it is the reason this gate is not
    `status == 'live'`; the others are here so that "not scheduled" cannot be
    quietly re-read as "live only" later.
    """

    @pytest.mark.parametrize("status", ["live", "suspended", "completed", "closed", "voided"])
    def test_decay_still_applies(self, status):
        assert _relative_decay_applies(status) is True

    @pytest.mark.parametrize("status", ["scheduled", "SCHEDULED", "Scheduled"])
    def test_decay_is_off_before_the_game_starts(self, status):
        assert _relative_decay_applies(status) is False

    @pytest.mark.parametrize("status", [None, "", "some_status_nobody_has_written_yet"])
    def test_an_unknown_status_keeps_decaying(self, status):
        """The monotone default, matching the one an unstamped entry gets: a
        status this module has never seen must not silently change a hero."""
        assert _relative_decay_applies(status) is True

    def test_suspended_keeps_its_settled_kalshi_leg(self):
        """15308773 (KBO, suspended): Kalshi settled to 0.01, betting holds the
        last in-play line at 0.4401. Decay demotes betting and the hero is the
        settled 0.01 — a 43-point difference this gate deliberately does not
        touch, because the game is over and the settled leg is right."""
        settled = {
            "kalshi": {"value": 0.01, "updated_at": "2026-09-11T14:02:11+00:00"},
            "betting": {"value": 0.4401, "updated_at": "2026-09-11T09:31:44+00:00"},
        }
        assert _hero(settled, "suspended") == pytest.approx(0.01)


class TestCadenceInvariance:
    """The jag property, in the one population where it can hold exactly.

    A published number must not depend on HOW OFTEN a source is written, only on
    WHAT it says. Before kickoff that is now true by construction, so it can be
    asserted rather than bounded: sweep the sportsbook's stamp across five days
    of relative age and the hero must not move a millipoint.
    """

    STAMPS = [
        "2026-09-11T23:21:04.214200+00:00",  # same instant as kalshi
        "2026-09-11T23:11:04.214200+00:00",  # 10 min behind — the old grace edge
        "2026-09-11T22:41:04.214200+00:00",  # 40 min — old floor edge
        "2026-09-11T17:27:22.934725+00:00",  # 6 h
        "2026-09-06T17:27:22.934725+00:00",  # 5 d — the production stamp
    ]

    def test_a_pregame_hero_is_invariant_to_its_sources_cadence(self):
        heroes = {
            stamp: _hero(
                {**SPECIMEN, "betting": {"value": BETTING_VALUE, "updated_at": stamp}},
                "scheduled",
            )
            for stamp in self.STAMPS
        }
        assert list(heroes.values()) == [pytest.approx(BETTING_VALUE)] * len(
            self.STAMPS
        ), heroes

    def test_and_in_play_it_is_NOT_invariant_which_is_why_the_test_above_means_something(self):
        """RED CONTROL. The same sweep on a live event moves the hero across the
        whole inter-source spread — so the assertion above is measuring the gate
        and not measuring nothing."""
        heroes = {
            stamp: _hero(
                {**SPECIMEN, "betting": {"value": BETTING_VALUE, "updated_at": stamp}},
                "live",
            )
            for stamp in self.STAMPS
        }
        assert len(set(heroes.values())) > 1, heroes
        assert max(heroes.values()) - min(heroes.values()) == pytest.approx(
            BETTING_VALUE - KALSHI_VALUE
        )


class TestTheGhostCannotArbitrateAnUnstartedGameEither:
    """#4028 held from the WRITER side; this gate closes the same door from the
    reader side, and closes it harder.

    #4028's specimen was a scheduled game where a settled Polymarket container
    was re-stamped `now`, decayed the real sportsbook line out of the blend, and
    printed "Marlins 1% - 99% Mets" over "18 sportsbooks". That was fixed by
    making the writer stamp an OBSERVATION rather than a re-read. Before
    kickoff the reader now refuses the same outcome independently: a ghost may
    hold the freshest stamp on the event and still cannot outvote the books,
    because pre-game weights are the base weights and `betting` is 3.75x a
    market source.
    """

    def test_a_ghost_with_the_freshest_possible_stamp_still_loses_pregame(self):
        ghost = {
            "betting": {"value": 0.589, "updated_at": "2026-09-06T17:27:22+00:00"},
            "polymarket": {"value": 0.07, "updated_at": "2026-09-11T23:59:59+00:00"},
        }
        assert _hero(ghost, "scheduled") == pytest.approx(0.589)

    def test_in_play_that_same_ghost_still_wins_and_still_needs_the_writer_fix(self):
        """Stated so nobody reads this gate as having retired #4028."""
        ghost = {
            "betting": {"value": 0.589, "updated_at": "2026-09-06T17:27:22+00:00"},
            "polymarket": {"value": 0.07, "updated_at": "2026-09-11T23:59:59+00:00"},
        }
        assert _hero(ghost, "live") == pytest.approx(0.07)
