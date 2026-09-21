"""#2727 — the accuracy page stops apologising in the beat it publishes.

The defect, as a reader saw it on the first q269 publish (2026-09-02 16:59 PT),
under a curve that had been rebuilt three minutes earlier with zero measured
drift:

    The curve is current. The data behind it is older. … the market data behind
    it was last staged Sep 2, 4:59 PM (3 min ago), and 0 of 128 units have
    drifted since (3 more couldn't be checked). So it describes the market as of
    then, not now.

The one reading where the page had the best possible story to tell is the
reading where it apologised. The three units that "couldn't be checked" were
exactly the three the rolling re-stage was rebuilding that beat, which by
construction cannot carry a digest yet — they belonged to the bank being BUILT,
and they were being counted against the bank being SERVED.

## Why this file is a guard and not a fix

CAL-P078 (``1ed086a00``, 2026-09-05) split the two banks and repaired this three
days after #2727 was filed, as a consequence of a larger change rather than as
an answer to it — nobody closed the issue and nobody pinned the behaviour.
Driven against master on 2026-09-21 the publishing beat now renders ``fresh``
(arm 1 below). So this file exists because **the serving branch that decides
what a reader is told about the bank they are looking at had no test at all**:
all 25 cases in ``test_calibration_staged_disclosure_p076.py`` pre-date
CAL-P078 and describe the building bank, so every one of them passes with the
serving branch deleted.

## What each arm is for

The two arms that matter pull in opposite directions, and a repair that only
gets one of them is the original defect with its sign flipped:

* **Arm 1** — in-flight units of the BUILDING bank must not condemn the SERVED
  one. This is #2727 itself.
* **Arm 2** — a genuinely uncheckable unit of the SERVED bank must still refuse
  ``fresh``. This is CAL-P069, where 6 unmeasurable units published as
  ``units_drifted: 0``, and it is the reason the naive repair (drop the unknown
  term) is wrong.

Arms 3-6 pin the reads the serving branch performs to get there: the served
gauges take precedence over the builder's same-named ones, an absent gauge is
not a reassuring zero, and the date on the block is the served census's own.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils.availability_envelope import AVAILABILITY_STALE
from app.utils.calibration_staged_disclosure import (
    GAUGE_SERVED_AT,
    GAUGE_SERVED_DRIFT_UNCHECKABLE,
    GAUGE_SERVED_DRIFTED,
    GAUGE_SERVED_UNITS,
    GAUGE_UNITS_BANKED,
    GAUGE_UNITS_DRIFT_CHECKABLE,
    GAUGE_UNITS_DRIFT_UNCHECKABLE,
    GAUGE_UNITS_DRIFTED,
    GAUGE_UNITS_THIS_BEAT,
    availability_floor,
    build_disclosure,
)

#: The instant the publishing beat is observed.
NOW = datetime(2026, 9, 2, 23, 59, 0, tzinfo=timezone.utc)
#: The served census completed three minutes earlier — #2727's own figure.
SERVED_AT = NOW - timedelta(minutes=3)
#: The builder's durable row. Under CAL-P078 this is the publish clock, and the
#: block must NOT date the served census from it (that substitution is #2007).
BUILDER_ROW_AT = datetime(2026, 9, 2, 20, 0, 0, tzinfo=timezone.utc)


def publishing_beat(**overrides) -> dict:
    """#2727's gauge reading: a complete, clean served bank of 128 beside a
    builder three units into a rolling re-stage.

    The builder's ``units_drift_checkable`` is 125 against the served bank's
    128. That three-unit gap IS the defect — it describes the other bank.
    """
    stages = {
        # the bank being SERVED
        GAUGE_SERVED_UNITS: 128,
        GAUGE_SERVED_AT: int(SERVED_AT.timestamp()),
        GAUGE_SERVED_DRIFTED: 0,
        GAUGE_SERVED_DRIFT_UNCHECKABLE: 0,
        # the bank being BUILT, mid rolling re-stage
        GAUGE_UNITS_BANKED: 3,
        GAUGE_UNITS_THIS_BEAT: 3,
        GAUGE_UNITS_DRIFTED: 0,
        GAUGE_UNITS_DRIFT_CHECKABLE: 125,
        GAUGE_UNITS_DRIFT_UNCHECKABLE: 3,
    }
    stages.update(overrides)
    return stages


def disclose(stages: dict) -> dict:
    return build_disclosure(
        ledger_stages=stages,
        staged_generated_at=BUILDER_ROW_AT,
        now=NOW,
    )


class TestThePublishingBeat:
    def test_in_flight_units_of_the_building_bank_do_not_condemn_the_served_one(
        self,
    ):
        """#2727. A curve staged three minutes ago with zero drift is fresh."""
        d = disclose(publishing_beat())

        assert d["measured"] is True
        # The served bank is whole: nothing about it is unknown, even though the
        # builder is three units into a re-stage with no digests yet.
        assert d["units_banked"] == 128
        assert d["units_drifted"] == 0
        assert d["units_drift_unknown"] == 0
        assert d["frozen_over_drift"] is False
        # …so nothing forces the word down, and the banner does not render.
        assert availability_floor(d) is None

    def test_a_reader_can_still_tell_the_build_is_alive_from_the_curve_being_current(
        self,
    ):
        """The builder's progress is published BESIDE the served figures.

        Collapsing the two is how "the build is fine" came to stand in for "the
        curve is current" (#2007). ``units_banked`` is the served census; the
        rebuild's own counters carry the ``rebuild_`` prefix.
        """
        d = disclose(publishing_beat())

        assert d["units_banked"] == 128, "the served census, not the builder's 3"
        assert d["rebuild_units_banked"] == 3
        assert d["rebuild_units_this_beat"] == 3
        assert d["rolling_restage"] is True

    def test_the_block_is_dated_from_the_served_census_not_the_publish_clock(self):
        """#2007: dating the served census from the builder's durable row is the
        publish clock wearing the census's name."""
        d = disclose(publishing_beat())

        assert d["staged_at"].startswith("2026-09-02T23:56")
        assert d["staged_age_s"] == 180
        # And the drift figure is dated to the same instant, not to the beat.
        assert d["units_drifted_as_of"] == d["staged_at"]


class TestWhatMustStillRefuseFresh:
    def test_an_uncheckable_unit_of_the_served_bank_still_refuses(self):
        """CAL-P069, and the reason the naive repair is wrong.

        Same beat, same in-flight builder — the only change is that three units
        of the SERVED bank carry no digest. A zero drift reading over them is
        the unmeasurable zero the rule exists to catch.
        """
        d = disclose(publishing_beat(**{GAUGE_SERVED_DRIFT_UNCHECKABLE: 3}))

        assert d["units_drifted"] == 0
        assert d["units_drift_unknown"] == 3
        assert d["frozen_over_drift"] is True
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_measured_drift_in_the_served_bank_refuses(self):
        d = disclose(publishing_beat(**{GAUGE_SERVED_DRIFTED: 4}))

        assert d["units_drifted"] == 4
        assert d["frozen_over_drift"] is True
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_an_absent_served_uncheckable_gauge_is_not_a_reassuring_zero(self):
        """The gauge is written only when the cursor carries a digest map at
        all, so its absence means "we cannot say" — which may not resolve to the
        reassuring reading (gotcha #53)."""
        stages = publishing_beat()
        del stages[GAUGE_SERVED_DRIFT_UNCHECKABLE]
        d = disclose(stages)

        assert d["units_drift_unknown"] is None
        assert d["units_drift_checkable"] is None
        assert d["frozen_over_drift"] is True
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_the_served_figures_win_where_both_banks_report(self):
        """The two banks publish same-named gauges and they disagree.

        Set them in the direction where reading the wrong one is REASSURING —
        a clean builder over a drifted served bank — so a regression that drops
        the served override renders ``fresh`` over a stale curve rather than
        merely producing a different number.
        """
        d = disclose(
            publishing_beat(
                **{
                    GAUGE_SERVED_DRIFTED: 9,
                    GAUGE_SERVED_DRIFT_UNCHECKABLE: 0,
                    GAUGE_UNITS_DRIFTED: 0,
                    GAUGE_UNITS_DRIFT_CHECKABLE: 3,
                    GAUGE_UNITS_DRIFT_UNCHECKABLE: 0,
                }
            )
        )

        assert d["units_drifted"] == 9, "read the served bank, not the builder's 0"
        assert availability_floor(d) == AVAILABILITY_STALE
