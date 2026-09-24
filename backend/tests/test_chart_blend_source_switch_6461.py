"""#6461 — the chart's blend follows the price, not the polling schedule.

The defect, measured on `/api/events/15305465/history`: 29 of 261 points on the
served aggregate line moved 5+ percentage points from the one before, the worst
pair 42.6 points in 120 seconds, on a game where every individual source's own
series was smooth. The series aged each source against the BUCKET's clock (full
weight 2 min, gone at 5) while the sources poll at 185-282 s and betting's p90
gap is 1500 s, so the weights — and sometimes the membership — of the weighted
median changed every minute for no reason but cadence.

The repair puts the series on the recency rule #1829 already ruled for the hero:
a reading is aged against the FRESHEST OBSERVATION IN ITS OWN BUCKET, so uniform
slowness costs nothing and only falling behind a peer who is still observing
does. Terminal behaviour stays the series' own — decay to zero at 40 minutes
behind, not the hero's floor — because this axis is unbounded and a dark source
has to be able to leave.

What these tests are for, in one line each: the cadence tests prove the artifact
is gone, the movement tests prove nothing was smoothed away to achieve that, and
the lifecycle tests prove the fix did not buy stability with indefinite
carry-forward. A test that only showed "the line is calmer" would pass on a
moving average, which is exactly what ruling #4 forbids — so every calm-line
assertion here is paired with a real-move assertion on the same mechanism.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.aggregation import (
    HERO_MIN_STALENESS_MULTIPLIER,
    HERO_RELATIVE_DECAY_SECONDS,
    HERO_RELATIVE_GRACE_SECONDS,
    TimestampedProb,
    _relative_staleness_multiplier,
    compute_aggregated_probability,
)

BASE = datetime(2026, 9, 6, 17, 0, 0, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "chart_blend_15305465_6461.json"


def _tp(seconds: float, prob: float) -> TimestampedProb:
    return TimestampedProb(
        timestamp=BASE + timedelta(seconds=seconds), home_probability=prob
    )


def _series(line):
    return [p.home_probability for p in line]


def _biggest_step(line):
    probs = _series(line)
    if len(probs) < 2:
        return 0.0
    return max(abs(probs[i] - probs[i - 1]) for i in range(1, len(probs)))


class TestCadenceIsNotStaleness:
    """The ship: a slow poller no longer changes the answer by being slow."""

    def test_sources_at_different_cadences_produce_a_flat_line(self):
        """Three sources, none of them moving, all polling at different rates.

        This is the defect in miniature. Before the repair the 600 s source was
        deleted from the pool between its writes and rejoined on each one, so
        the weighted median walked back and forth between 0.60 and 0.10 for the
        length of the game. Nothing here has moved, so nothing on the chart may.
        """
        sources = {
            "espn": [_tp(s, 0.10) for s in range(0, 3600, 180)],
            "betting": [_tp(s, 0.60) for s in range(0, 3600, 600)],
            "stat_model": [_tp(s, 0.55) for s in range(0, 3600, 300)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)

        assert len(line) > 20, "the fixture should span many buckets"
        assert _biggest_step(line) == pytest.approx(0.0, abs=1e-9)
        assert (
            len(set(_series(line))) == 1
        ), f"a quiet market must draw one value, got {sorted(set(_series(line)))}"

    def test_a_source_slower_than_the_old_five_minute_cutoff_keeps_its_vote(self):
        """The specific mechanism: 600 s cadence used to mean zero weight.

        `betting` carries weight 3.0 against `espn`'s 1.5, so whether it is in
        the pool decides the answer outright. Asserted on the VALUE rather than
        on a weight, because a weight is an implementation detail and the reader
        sees the value.
        """
        sources = {
            "espn": [_tp(s, 0.20) for s in range(0, 1200, 60)],
            "betting": [_tp(0, 0.80), _tp(600, 0.80)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)

        # Every bucket, including the ones 9 minutes after betting last wrote.
        assert all(
            p == pytest.approx(0.80) for p in _series(line)
        ), "the heavier source stopped being counted between its own writes"

    def test_the_pinned_specimen_loses_its_source_switch_jumps(self):
        """The whole of event 15305465, real observations, before vs after.

        The BEFORE arm is not asserted from memory — `replay_chart_blend.py`
        reproduces the pre-repair rule and the fixture's provenance block
        records that the SERVED line had these same 29 jumps, so this test
        measures the shipped change rather than restating the issue.
        """
        from scripts.replay_chart_blend import (
            blend_after,
            blend_before,
            sources_from_payload,
        )

        payload = json.loads(FIXTURE.read_text())
        sources = sources_from_payload(payload)
        assert set(sources) == {"betting", "espn", "mlb", "stat_model"}

        def jumps(line):
            return [
                (line[i - 1], line[i])
                for i in range(1, len(line))
                if abs(line[i][1] - line[i - 1][1]) >= 0.05
            ]

        before = blend_before(sources, 60)
        after = blend_after(sources, 60)

        assert len(jumps(before)) == payload["_provenance"]["served_jumps_ge_5pp"] == 29
        assert len(jumps(after)) == 3, (
            "the three survivors are the 1-0 home run, the away two-run inning "
            "and a genuine betting drift — see the docstring on "
            "compute_aggregated_probability"
        )

        # Same number of points: this removed artifacts, it did not drop data.
        assert len(after) == len(before)
        # And the journey's ends are untouched — no re-basing, no clipping.
        assert after[0][1] == pytest.approx(before[0][1])

    def test_the_specimens_worst_pair_is_no_longer_a_cliff(self):
        """18:05 -> 18:07 read 0.572 -> 0.146, a 42.6-point fall in 120 seconds.

        The away side scored two runs at 18:07:41, so the pair SHOULD move — the
        defect was the size. The market's own answer was 0.264 (betting), and
        the old line overshot past it to 0.146 and bounced back to 0.264 in the
        next bucket. Asserting "it still moves, and it lands where the sources
        actually are" is the difference between this repair and a smoother.
        """
        from scripts.replay_chart_blend import blend_after, sources_from_payload

        payload = json.loads(FIXTURE.read_text())
        after = blend_after(sources_from_payload(payload), 60)
        at = {
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M"): value
            for ts, value, _ in after
        }

        assert at["18:05"] == pytest.approx(0.572, abs=0.001)
        assert at["18:07"] == pytest.approx(0.264, abs=0.001)
        # The real move survives in full and in one bucket — not damped, not
        # spread across three.
        assert at["18:05"] - at["18:07"] > 0.30
        # ...and it does not overshoot and come back, which is what it did.
        assert at["18:08"] == pytest.approx(at["18:07"], abs=0.001)


class TestRealMovementIsUntouched:
    """Ruling #4: movement IS the product. Every calm-line claim pays for itself
    here, or the repair is smoothing under another name."""

    def test_a_real_move_lands_in_full_in_one_bucket(self):
        sources = {
            "betting": [_tp(0, 0.50), _tp(60, 0.50), _tp(120, 0.80)],
            "espn": [_tp(0, 0.50), _tp(60, 0.50), _tp(120, 0.80)],
            "stat_model": [_tp(0, 0.50), _tp(60, 0.50), _tp(120, 0.80)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        assert _series(line)[-1] == pytest.approx(0.80)
        assert _biggest_step(line) == pytest.approx(
            0.30
        ), "the jump was damped — that is the EMA ruling #4 removed"

    def test_a_move_by_the_slow_source_alone_still_reaches_the_line(self):
        """The inverse risk of the repair: keeping a slow source in the pool is
        only honest if the line also FOLLOWS it when it moves."""
        sources = {
            "espn": [_tp(s, 0.20) for s in range(0, 1800, 180)],
            "betting": [_tp(0, 0.80), _tp(900, 0.30)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        probs = _series(line)
        assert probs[0] == pytest.approx(0.80)
        assert probs[-1] == pytest.approx(0.30)

    def test_the_settled_result_never_decays_and_never_sets_the_reference(self):
        """`final_result` is a graded outcome, not a forecast that can fall
        behind, so it is excluded from BOTH halves of the relative rule — the
        hero excludes the uncapped sources from its decay stamps and the series
        now has to do the same.

        Two claims in one fixture, because they fail in opposite directions.
        Decay it and the result fades out of a settled game (it writes once, an
        hour before the last market tick). Let it set the reference and every
        live source is aged against a result that will never be superseded.
        """
        sources = {
            "betting": [_tp(s, 0.45) for s in range(0, 3600, 120)],
            "espn": [_tp(s, 0.40) for s in range(0, 3600, 120)],
            "final_result": [_tp(0, 1.0)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)

        # Written once at t=0 and still deciding the line an hour later.
        assert _series(line)[-1] == pytest.approx(1.0)
        # "settled means settled" — and it never wobbles on the way.
        assert len(set(_series(line))) == 1


class TestObservationHygiene:
    """Late, duplicated, repeated and out-of-order receipts."""

    def test_out_of_order_input_gives_the_same_line_as_sorted_input(self):
        ordered = {
            "betting": [_tp(0, 0.50), _tp(60, 0.55), _tp(120, 0.60)],
            "espn": [_tp(0, 0.40), _tp(60, 0.45), _tp(120, 0.50)],
            "mlb": [_tp(0, 0.45), _tp(60, 0.50), _tp(120, 0.55)],
        }
        shuffled = {k: list(reversed(v)) for k, v in ordered.items()}
        assert _series(
            compute_aggregated_probability(ordered, bucket_seconds=60)
        ) == _series(compute_aggregated_probability(shuffled, bucket_seconds=60))

    def test_a_duplicate_receipt_does_not_move_the_line(self):
        """A second copy of an observation already held is not new evidence.

        It also must not refresh anything: the duplicate carries the SAME
        observation time, so the reference it could set is the one already set.
        """
        single = {
            "betting": [_tp(0, 0.50), _tp(300, 0.55)],
            "espn": [_tp(0, 0.30), _tp(300, 0.35)],
            "mlb": [_tp(0, 0.40), _tp(300, 0.45)],
        }
        doubled = {
            k: [p for point in v for p in (point, point)] for k, v in single.items()
        }
        assert _series(
            compute_aggregated_probability(single, bucket_seconds=60)
        ) == _series(compute_aggregated_probability(doubled, bucket_seconds=60))

    def test_a_confirmed_unchanged_value_is_a_flat_segment_not_a_gap(self):
        """T1's rule: a same-value observation is evidence, and it refreshes
        age. The line stays flat AND the source stays in the pool."""
        sources = {
            "betting": [_tp(s, 0.70) for s in range(0, 3600, 120)],
            "espn": [_tp(s, 0.20) for s in range(0, 3600, 120)],
            "mlb": [_tp(s, 0.25) for s in range(0, 3600, 120)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        assert len(line) > 25
        assert len(set(_series(line))) == 1
        # 0.25 rather than 0.70 because the #1829 share cap holds betting to 35%
        # and the crossing lands on `mlb` — the value is the cap's business, and
        # this test's business is that it does not MOVE while nothing does.
        assert _series(line)[0] == pytest.approx(0.25)

    def test_a_late_observation_is_read_at_its_own_time(self):
        """An observation that arrives out of band still belongs to the bucket
        its timestamp names — the repair reads observation time, never receipt
        order.

        Two sources, not three, so the heavier one's move is actually visible:
        with three the share cap would (correctly) refuse to let one source
        carry the median, and the test would pass without ever showing that the
        value landed where it landed BECAUSE of its timestamp.
        """
        sources = {
            "betting": [_tp(0, 0.50), _tp(600, 0.90)],
            "espn": [_tp(s, 0.50) for s in range(0, 900, 60)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        at = {
            int(p.timestamp.timestamp() - BASE.timestamp()): p.home_probability
            for p in line
        }
        assert at[480] == pytest.approx(0.50), "the late value leaked backwards in time"
        assert at[600] == pytest.approx(0.90)


class TestLifecycleIsBounded:
    """The repair must not have bought its stability with indefinite carry-forward."""

    def test_a_source_that_goes_dark_leaves_the_pool(self):
        """`betting` writes once and is never heard from again while its peers
        keep observing. It must decay OUT, not be carried at a floor forever."""
        sources = {
            "betting": [_tp(0, 0.90)],
            "espn": [_tp(s, 0.20) for s in range(0, 7200, 120)],
            "mlb": [_tp(s, 0.22) for s in range(0, 7200, 120)],
            "stat_model": [_tp(s, 0.21) for s in range(0, 7200, 120)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        assert _series(line)[-1] < 0.30, "a dark source was still carrying the median"

    def test_the_departure_is_at_the_ruled_boundary_not_a_new_constant(self):
        """The boundary is #1829's own grace + decay, read from the constants
        rather than written as a number here — a test that hardcodes 2400 is a
        test that silently stops matching the rule it guards."""
        boundary = HERO_RELATIVE_GRACE_SECONDS + HERO_RELATIVE_DECAY_SECONDS

        assert (
            _relative_staleness_multiplier(HERO_RELATIVE_GRACE_SECONDS, floor=0.0)
            == 1.0
        )
        assert _relative_staleness_multiplier(boundary - 1, floor=0.0) > 0.0
        assert _relative_staleness_multiplier(boundary, floor=0.0) == 0.0

        # The hero keeps its floor: this parameter must not have changed the
        # surface it was extracted from.
        assert _relative_staleness_multiplier(boundary) == HERO_MIN_STALENESS_MULTIPLIER
        assert (
            _relative_staleness_multiplier(boundary * 10)
            == HERO_MIN_STALENESS_MULTIPLIER
        )

    def test_a_returning_source_enters_on_its_first_observation(self):
        """T1 decision A: no cosmetic ramp. The bucket holding the returning
        observation is already weighted at full.

        Proved by identity against a control that never left, because that is
        the only form of the claim a ramp cannot satisfy: a ramp would make the
        two lines differ at exactly the returning bucket and agree everywhere
        after, which an assertion on one value would miss.

        Two sources on purpose — with three or more the share cap (correctly)
        stops any single returning source from carrying the median, and the test
        would pass whether or not the ramp existed.
        """
        espn = [_tp(s, 0.20) for s in range(0, 3660, 120)]
        gap = {"betting": [_tp(0, 0.90), _tp(3600, 0.90)], "espn": espn}
        never_left = {
            "betting": [_tp(s, 0.90) for s in range(0, 3660, 120)],
            "espn": espn,
        }

        def at(sources):
            line = compute_aggregated_probability(sources, bucket_seconds=60)
            return {
                int(p.timestamp.timestamp() - BASE.timestamp()): p.home_probability
                for p in line
            }

        gapped, control = at(gap), at(never_left)

        # Gone while dark: the line is espn's, alone.
        assert gapped[3480] == pytest.approx(0.20)
        assert control[3480] == pytest.approx(0.90)

        # Back at full weight the instant it observes again — identical to the
        # source that never went away.
        assert gapped[3600] == pytest.approx(0.90)
        assert gapped[3600] == control[3600]

    def test_a_fully_decayed_source_does_not_switch_the_share_cap_on(self):
        """A source decayed to zero must not count as a third contributor.

        The #1829 share cap only applies from three contributors up, so if a
        weightless arm counted, a genuinely two-source event would be capped,
        the heavy source held to 35%, and the median handed to the light one —
        0.80 becoming 0.20 here. That is #5542's "a dead arm decides by
        position" with the weight taken all the way to zero.

        WRITTEN AFTER A MUTATION THAT SURVIVED, and the honest reading is the
        opposite of the usual one. Replacing the producer's
        `if effective_weight > 0` with `if True` changed no output, so that gate
        is REDUNDANT — `cap_weight_shares` already counts only positive weights,
        and `_weighted_median` can never return a zero-weight entry. This test
        therefore pins the OUTCOME, which two mechanisms currently protect, and
        it cannot tell you which of them did the work; it exists so that
        removing BOTH is loud. Recording that honestly rather than claiming a
        kill, because a guard whose docstring overstates it is how the next
        person deletes the load-bearing half believing it is the spare one.
        """
        dark_plus_two = {
            "betting": [_tp(s, 0.80) for s in range(0, 7200, 120)],
            "espn": [_tp(s, 0.20) for s in range(0, 7200, 120)],
            "kalshi": [_tp(0, 0.95)],  # one reading, then dark for two hours
        }
        line = compute_aggregated_probability(dark_plus_two, bucket_seconds=60)

        assert _series(line)[-1] == pytest.approx(0.80), (
            "the dark source is still counted as a third contributor, so the "
            "share cap fired on a two-source event"
        )

    def test_sources_that_all_stop_together_are_not_penalised(self):
        """#1829's load-bearing consequence, restated for the series: uniform
        age is cadence. A game whose every source polls slowly is not a game
        whose every source is stale."""
        slow = {
            "betting": [_tp(s, 0.65) for s in range(0, 18000, 1800)],
            "espn": [_tp(s + 60, 0.20) for s in range(0, 18000, 1800)],
            "mlb": [_tp(s + 120, 0.25) for s in range(0, 18000, 1800)],
        }
        line = compute_aggregated_probability(slow, bucket_seconds=60)
        probs = _series(line)
        assert len(probs) == 30, "an all-slow event lost most of its line"

        # The opening step is not an artifact: the line genuinely begins on
        # betting alone (bucket 0), then betting + espn (bucket 1, where
        # betting's weight still carries the median), and only has three
        # contributors once mlb makes its first observation at 120s. Every
        # bucket after that is flat, which is the claim — five hours of
        # staggered half-hourly polling with nothing moving draws a straight
        # line.
        #
        # #8349: this used to pin the step at bucket 0 alone, because the
        # inclusive bucket edge pulled mlb's reading stamped exactly 120s into
        # bucket 60. Buckets are half-open now, so mlb joins in its own minute.
        assert probs[:2] == [pytest.approx(0.65), pytest.approx(0.65)]
        assert all(p == pytest.approx(0.25) for p in probs[2:])


class TestTheOldProtectionsStillHold:
    """Guards this change must not have quietly disarmed."""

    def test_a_single_source_is_reported_verbatim(self):
        """One source and no peers: the reference is that source's own reading,
        relative age is zero everywhere, and the line IS the series.

        Points are placed off the bucket boundary. Until #8349 the carry-forward
        window was `<= bucket_ts + bucket_seconds`, so a point sitting exactly on
        a boundary was also claimed by the bucket BEFORE it. Buckets are
        half-open now (`test_chart_bucket_edge_is_half_open_8349.py` holds
        that), so the offsets are no longer load-bearing here.
        """
        sources = {"betting": [_tp(10, 0.50), _tp(70, 0.55), _tp(130, 0.60)]}
        assert _series(compute_aggregated_probability(sources, bucket_seconds=60)) == [
            0.50,
            0.55,
            0.60,
        ]

    def test_the_1829_share_cap_still_stops_one_source_straddling_the_middle(self):
        """Event 15192596: betting frozen at 0.1347 while three fresh sources
        said ~0. The cap, not the decay, is what made the median honest there —
        and the cap must still fire now that the decay is relative.
        """
        sources = {
            "betting": [_tp(s, 0.1347) for s in range(0, 600, 60)],
            "mlb": [_tp(s, 0.001) for s in range(0, 600, 60)],
            "espn": [_tp(s, 0.008) for s in range(0, 600, 60)],
            "stat_model": [_tp(s, 0.001) for s in range(0, 600, 60)],
            "kalshi": [_tp(s, 0.565) for s in range(0, 600, 60)],
        }
        line = compute_aggregated_probability(sources, bucket_seconds=60)
        assert all(
            p < 0.05 for p in _series(line)
        ), "betting straddled the midpoint again — the share cap is not firing"

    def test_an_empty_input_is_still_an_empty_line(self):
        assert compute_aggregated_probability({}) == []
        assert compute_aggregated_probability({"betting": []}) == []
