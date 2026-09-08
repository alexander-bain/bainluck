"""A ladder that never crosses 50% implies nothing, and says so (#3965).

`binary_to_implied_spread` used to extrapolate past the end of a one-sided
ladder — `-first * 0.5` below the crossover, `-last * 1.5` above it. Both
multipliers are invented, and the second one put a **-14.25 run** implied
spread on `/events/15307194` off a Polymarket ladder priced 1.000 at every
rung. `ScoreDifferentialChart` draws every non-sportsbook arm on presence
alone (#3948), so that fabricated number was a chart line at +14.25 home
margin next to a Kalshi line at +0.2.

Every fixture below is the production payload of 2026-09-08, read from
`/api/events/{id}/history` while the defect was live, so a regression is
measured against what the venue actually served rather than against a
hand-written ladder that happens to trip the branch.
"""

from app.utils.binary_spread import (
    binary_to_implied_spread,
    home_margin_from_spread,
    select_projection_source,
)


def _contracts(rungs):
    return [{"threshold": t, "probability": p} for t, p in rungs]


# `/api/events/15307194/history`, Minnesota Twins @ Detroit Tigers, 2026-09-08.
# Twenty rungs, all but one priced 1.000 — a dead surface, not a price.
PM_DEGENERATE_15307194 = [
    (1.5, 1.0),
    (1.5, 1.0),
    (1.5, 1.0),
    (2.5, 1.0),
    (2.5, 1.0),
    (2.5, 1.0),
    (3.5, 0.84),
    (3.5, 1.0),
    (3.5, 1.0),
    (4.5, 1.0),
    (4.5, 1.0),
    (5.5, 1.0),
    (5.5, 1.0),
    (6.5, 1.0),
    (6.5, 1.0),
    (7.5, 1.0),
    (7.5, 1.0),
    (8.5, 1.0),
    (8.5, 1.0),
    (9.5, 1.0),
]

# The Kalshi arm on that same event, which crosses cleanly and must survive.
KALSHI_CROSSES_15307194 = [
    (-3.5, 0.84),
    (-2.5, 0.77),
    (-1.5, 0.66),
    (1.5, 0.38),
    (2.5, 0.28),
    (3.5, 0.19),
]

# `/api/events/15307719/history`, Nippon-Ham at SoftBank. Two rungs on the
# signed home-margin axis, both above 50%.
KALSHI_WRONG_SIDE_15307719 = [(-2.5, 0.770), (-1.5, 0.685)]


class TestOneSidedLadderDerivesNothing:
    def test_degenerate_polymarket_ladder_derives_no_spread(self):
        """The -14.25 specimen. No rung crosses 50%, so there is no spread."""
        assert binary_to_implied_spread(_contracts(PM_DEGENERATE_15307194)) is None

    def test_never_returns_a_value_past_its_own_last_rung(self):
        """The failure was a number OUTSIDE the ladder, not merely a wrong one.

        Pinned as a property rather than as `!= -14.25` so that restoring the
        branch with a different multiplier still fails.
        """
        result = binary_to_implied_spread(_contracts(PM_DEGENERATE_15307194))
        if result is not None:  # pragma: no cover - the assertion below fails first
            last = max(t for t, _ in PM_DEGENERATE_15307194)
            assert abs(home_margin_from_spread(result.spread)) <= last
        assert result is None

    def test_all_below_crossover_derives_nothing(self):
        """The mirror branch, which extrapolated to `-first * 0.5`."""
        rungs = [(1.0, 0.40), (3.5, 0.25), (5.5, 0.15)]
        assert binary_to_implied_spread(_contracts(rungs)) is None

    def test_signed_axis_ladder_is_not_pushed_away_from_its_crossover(self):
        """🔴 The extrapolation could land on the WRONG SIDE of its own data.

        `P(home_margin >= -1.5) = 0.685`, and probability falls as the
        threshold rises, so the 50% crossover sits ABOVE -1.5. The old branch
        computed `-(-1.5) * 1.5 = 2.25`, i.e. `home_margin = -2.25` — below
        every rung the ladder priced. Treating a signed home-margin threshold
        as a positive magnitude is the #3948 sign collision; see
        `home_margin_from_spread`.
        """
        result = binary_to_implied_spread(_contracts(KALSHI_WRONG_SIDE_15307719))
        assert result is None
        # And the specific inversion never comes back.
        if result is not None:  # pragma: no cover
            assert home_margin_from_spread(result.spread) > -1.5


class TestRefusalIsNarrow:
    """The fix must not cost a projection that was correct."""

    def test_crossing_ladder_still_derives(self):
        result = binary_to_implied_spread(_contracts(KALSHI_CROSSES_15307194))
        assert result is not None
        assert -1.5 < home_margin_from_spread(result.spread) < 1.5
        assert result.confidence > 0.5

    def test_the_event_that_lost_its_bad_arm_keeps_its_good_one(self):
        """15307194 end to end: Polymarket drops out, Kalshi still projects.

        This is the "0 correct projections lost" criterion at the unit the
        route builds: a dict of arms per source. Before the fix both keys were
        present and the chart drew both lines; after it, only Kalshi is there,
        and it is still the source `select_projection_source` picks.
        """
        implied = {}
        for source, rungs in (
            ("polymarket", PM_DEGENERATE_15307194),
            ("kalshi", KALSHI_CROSSES_15307194),
        ):
            arm = binary_to_implied_spread(_contracts(rungs))
            if arm:
                implied[source] = {
                    "spread": arm.spread,
                    "home_margin": home_margin_from_spread(arm.spread),
                    "confidence": arm.confidence,
                }

        assert "polymarket" not in implied, "the fabricated arm still renders"
        assert "kalshi" in implied, "a correct projection was lost"
        assert select_projection_source(implied) == "kalshi"

    def test_a_rung_sitting_exactly_on_the_crossover_still_derives(self):
        """0.50 is a crossing, not a one-sided ladder — the branch uses >=/<=."""
        rungs = [(3.5, 0.62), (7.5, 0.50), (10.5, 0.38)]
        assert binary_to_implied_spread(_contracts(rungs)) is not None

    def test_two_rung_ladder_that_crosses_is_untouched(self):
        """Polymarket often carries only two rungs; crossing ones still count."""
        rungs = [(9.5, 0.55), (10.5, 0.45)]
        result = binary_to_implied_spread(_contracts(rungs))
        assert result is not None
        assert -11 < result.spread < -9
