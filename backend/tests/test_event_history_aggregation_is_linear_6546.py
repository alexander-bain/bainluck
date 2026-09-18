"""#6546 — the blend line is built in one pass, not one pass per bucket.

THE SHIP, IN A READER'S WORDS: the chart on a finished game draws instead of
spinning.

WHAT WAS WRONG. `compute_aggregated_probability` carries each source's last
reading forward into every time bucket, and it found that reading by scanning
the source's points from the BEGINNING for every bucket — recomputing
`point.timestamp.timestamp()` on each visit. On the specimen in #6546 (Broncos
at Chiefs, FINAL, with four months of pre-match market history: 3,009 Kalshi +
2,405 Polymarket points over 4,607 one-minute buckets) that is ~14 million
datetime conversions for one request. Measured on production:
`x-response-time: 4261ms`, split `db=110.5 app=4147.0` — the database is a
tenth of a second and the Python is four seconds, in a route the phone waits on
with a spinner in the middle of a blank half-screen.

It is also four seconds of CPU inside an async handler, on the uvicorn loop that
serves `/api/feed`.

WHAT THIS ASSERTS. Two things, because either alone would be weak:

* **EQUIVALENCE.** The previous implementation is kept below, verbatim, as an
  oracle, and the shipped one must agree with it EXACTLY — same points, same
  timestamps, same probabilities — on randomised multi-source series and on
  every edge the carry-forward has (duplicate timestamps, unsorted input, a
  source that starts after the last bucket, one-point sources, empty sources).
  A speed change to the number a reader sees is a data change; this is the
  clause that says it is not one.
* **COMPLEXITY, WITH A CONTROL.** A timing budget alone measures the machine.
  So the oracle runs through the SAME harness on the SAME data: it must blow the
  budget the shipped one meets. A green row here is therefore never "this laptop
  is fast".
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    SourceReading,
    TimestampedProb,
    _relative_staleness_multiplier,
    _weighted_median,
    cap_weight_shares,
    compute_aggregated_probability,
)
from app.utils.aggregation import _UNCAPPED_SOURCES


# ---------------------------------------------------------------------------
# The oracle: the implementation as it stood before #6546, character for
# character inside the loop. DO NOT "fix" this file's copy — it is the BEFORE,
# and a BEFORE that is quietly improved proves nothing (ruling on verbatim
# controls, 2026-09-12).
#
# ── #6461 AMENDMENT: THE CONTROL IS THE SCAN, NOT THE WEIGHTING ─────────────
#
# One thing in this oracle was never the BEFORE it is guarding. #6546 changed
# HOW the carry-forward finds each source's reading (restart-per-bucket ->
# per-source cursor) and nothing else; the weighting that turns those readings
# into a number was incidental to it, and is copied here only because it sat in
# the same loop.
#
# #6461 changed exactly that weighting — a reading is now aged against the
# freshest observation in its own bucket rather than against the bucket clock —
# so a byte-for-byte oracle reddens on eight cases while saying nothing about
# the scan it exists to protect. Refreshing the whole copy would destroy the
# control (the 2026-09-12 ruling); leaving it red would strike a guard for
# being correct.
#
# So the assertion is SPLIT, which is what that ruling asks for. The scan below
# — the `for point in points: if ... else: break` restart, the bucket
# enumeration, the timezone derivation, the duplicate/unsorted handling — is
# still verbatim and is still the control, and it is the only thing this file
# has ever been able to prove.
#
# Be precise about how independent the rest of it is, because "mirrored" would
# be a bigger claim than this file can pay. The DERIVATION is mirrored: which
# candidates set the reference, that `final_result` is excluded from it and
# exempt from decay, and that the age is a difference against that reference —
# all written out here rather than called, so a change to any of it in
# `aggregation.py` reddens this test. The CURVE is imported
# (`_relative_staleness_multiplier`), exactly as `_staleness_weight` was
# imported before #6461: that helper was never part of the control either, and
# copying its constants now would fabricate an independence this file did not
# have yesterday and does not need.
#
# One deliberate asymmetry, and it earns its place: the shipped code dropped its
# negative-age clamp as unreachable, and this copy keeps `max(0.0, ...)`. So if
# the reference epoch ever stops being the max of the values it is compared
# against, the two disagree and this test says so — the clamp is retained here
# precisely BECAUSE it is dead in the shipped path.
#
# #6461's own behaviour is proved next door, in
# `test_chart_blend_source_switch_6461.py`; it is not this file's job and never
# was.
# ---------------------------------------------------------------------------


def _oracle_aggregated_probability(
    sources: dict[str, list[TimestampedProb]],
    bucket_seconds: int = 30,
    custom_weights: Optional[dict[str, float]] = None,
) -> list[TimestampedProb]:
    weights = custom_weights or SOURCE_WEIGHTS

    if not sources:
        return []

    all_timestamps: set[float] = set()
    for source_points in sources.values():
        for point in source_points:
            ts = point.timestamp.timestamp()
            bucket_key = int(ts // bucket_seconds) * bucket_seconds
            all_timestamps.add(bucket_key)

    if not all_timestamps:
        return []

    sorted_buckets = sorted(all_timestamps)

    source_sorted: dict[str, list[TimestampedProb]] = {}
    for source_key, points in sources.items():
        source_sorted[source_key] = sorted(points, key=lambda p: p.timestamp)

    aggregated: list[TimestampedProb] = []

    for bucket_ts in sorted_buckets:
        bucket_time = datetime.fromtimestamp(bucket_ts, tz=None)
        for pts in sources.values():
            if pts:
                bucket_time = datetime.fromtimestamp(
                    bucket_ts, tz=pts[0].timestamp.tzinfo
                )
                break

        readings: list[SourceReading] = []

        # ── THE CONTROL: the pre-#6546 restart-per-bucket scan, verbatim ────
        candidates: list[tuple[str, TimestampedProb]] = []
        for source_key, points in source_sorted.items():
            latest: Optional[TimestampedProb] = None
            for point in points:
                if point.timestamp.timestamp() <= bucket_ts + bucket_seconds:
                    latest = point
                else:
                    break

            if latest is None:
                continue

            candidates.append((source_key, latest))

        if not candidates:
            continue

        # ── NOT the control: #6461's weighting, mirrored (see the note above)
        decay_epochs = [
            point.timestamp.timestamp()
            for source_key, point in candidates
            if source_key not in _UNCAPPED_SOURCES
        ]
        reference_epoch = max(decay_epochs) if decay_epochs else None

        for source_key, latest in candidates:
            base_weight = weights.get(source_key, 0.5)

            if reference_epoch is None or source_key in _UNCAPPED_SOURCES:
                relative_age = 0.0
            else:
                relative_age = max(0.0, reference_epoch - latest.timestamp.timestamp())

            stale_mult = _relative_staleness_multiplier(relative_age, floor=0.0)
            effective_weight = base_weight * stale_mult

            if effective_weight > 0:
                readings.append(
                    SourceReading(
                        source=source_key,
                        probability=latest.home_probability,
                        weight=effective_weight,
                        stale_seconds=relative_age,
                    )
                )

        if not readings:
            continue

        values = [r.probability for r in readings]
        wts = cap_weight_shares(
            [r.weight for r in readings],
            exempt=[r.source in _UNCAPPED_SOURCES for r in readings],
        )
        raw_aggregate = _weighted_median(values, wts)

        aggregated.append(
            TimestampedProb(
                timestamp=bucket_time,
                home_probability=round(raw_aggregate, 6),
            )
        )

    return aggregated


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 9, 15, 0, 15, tzinfo=timezone.utc)


def _series(n: int, *, start_min: float = 0.0, step_min: float = 1.0, seed: int = 1):
    rng = random.Random(seed)
    prob = rng.uniform(0.2, 0.8)
    out = []
    for i in range(n):
        prob = min(0.99, max(0.01, prob + rng.uniform(-0.03, 0.03)))
        out.append(
            TimestampedProb(
                timestamp=_T0 + timedelta(minutes=start_min + i * step_min),
                home_probability=round(prob, 4),
            )
        )
    return out


def _as_tuples(points):
    return [(p.timestamp.isoformat(), p.home_probability) for p in points]


def _specimen_shape():
    """The #6546 specimen's shape: months of market history, minutes of game.

    Point counts and spans are the measured ones, so the timing arm below is
    sized to the request a reader actually waited on rather than to a number
    someone liked.
    """
    return {
        "betting": _series(346, start_min=-120 * 24 * 60, step_min=300, seed=4),
        "kalshi": _series(3009, start_min=-123 * 24 * 60, step_min=58, seed=5),
        "polymarket": _series(2405, start_min=-36 * 24 * 60, step_min=21, seed=6),
        "stat_model": _series(98, step_min=2, seed=7),
        "espn": _series(120, step_min=1.75, seed=8),
    }


def _time_it(fn, sources, bucket_seconds=60):
    started = time.perf_counter()
    out = fn(sources, bucket_seconds=bucket_seconds)
    return time.perf_counter() - started, out


#: A CRASH GUARD, AND NO LONGER THE PROOF OF ANYTHING. Re-sized 2026-09-17 after
#: this file's clock control went red on master sha `2d2374a57` (shard 3) at
#: `shipped 0.421s vs oracle 3.390s` — 8.05x against a 10x bar.
#:
#: THE CLOCK CANNOT CARRY THIS PROOF, and that is a measurement rather than a
#: preference. Same specimen, same run, two machines:
#:
#:            shipped    oracle    oracle/shipped
#:   laptop    0.022s    1.80s        ~82x
#:   CI        0.421s    3.39s         ~8x
#:
#: The MACHINE spread on the shipped arm (0.022 -> 0.421, ~19x) is larger than
#: the gap between the two implementations on the slow machine (~8x). So no
#: single wall-clock threshold can separate "linear" from "quadratic" on both
#: boxes: any bar tight enough to fail the oracle on the laptop fails the fix on
#: CI. The old budget was inside that squeeze — 0.421s of an 0.5s budget is 84%
#: spent, so the FIRST arm was one noisy run from red too, not just the ratio.
#:
#: The real invariant is counted, not timed: see `_point_reads` and
#: `test_the_implementation_it_replaced_reads_every_point_again_per_bucket`,
#: which measures 972x on any machine because it counts work instead of seconds.
#: This budget stays only to catch a catastrophic blow-up (an accidental O(n^2)
#: that takes minutes), and 2.0 s is chosen as ~5x the slowest shipped run ever
#: observed. It is deliberately LOOSE ENOUGH THAT THE ORACLE WOULD PASS IT on the
#: laptop, which is exactly why the anti-vacuity control had to stop being a
#: clock comparison.
_BUDGET_S = 2.0


def _point_reads(fn, sources=None, bucket_seconds=60):
    """Count how many times `fn` reads a source point's timestamp. No clock.

    THIS IS THE FILE'S REAL CONTROL. The pre-#6546 implementation restarts its
    scan from the front of every source for every bucket, so it reads each
    point's timestamp once per bucket it precedes; the one-pass scan reads each
    point a constant number of times. That difference is arithmetic — it is the
    same on a laptop, on a loaded CI runner, and under a debugger — where the
    ratio of their run times is a property of the box.

    Returns `(reads, output)`. The output is returned so the caller can prove
    the probe did not perturb the computation: a probe that quietly broke the
    implementation would report a small, meaningless count.
    """

    class _Probe:
        """Forwards to a real point, counting reads of `.timestamp` only."""

        __slots__ = ("_p", "_box")

        def __init__(self, p, box):
            object.__setattr__(self, "_p", p)
            object.__setattr__(self, "_box", box)

        @property
        def timestamp(self):
            self._box[0] += 1
            return self._p.timestamp

        @property
        def home_probability(self):
            return self._p.home_probability

    box = [0]
    src = {
        key: [_Probe(p, box) for p in points]
        for key, points in (sources or _specimen_shape()).items()
    }
    out = fn(src, bucket_seconds=bucket_seconds)
    return box[0], out


#: Measured 2026-09-17 on the specimen: shipped 17,935 reads for 5,978 points
#: (3.0 per point — one pass), oracle 17,436,154 (972x). A bar of 50x sits an
#: order of magnitude below the observed ratio and cannot be reached by any
#: amount of machine noise, because no machine noise enters a count.
_MIN_READ_RATIO = 50

#: One pass means reads grow with the POINT COUNT, not with points x buckets.
#: Measured 3.0 reads per point; 10 leaves room for an honest refactor and still
#: fails instantly if a per-bucket rescan comes back (the oracle reads 2,917).
_MAX_READS_PER_POINT = 10


class TestItAgreesWithWhatItReplaced:
    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_randomised_multi_source_series_agree_exactly(self, seed):
        rng = random.Random(seed)
        sources = {
            name: _series(
                rng.randint(1, 400),
                start_min=rng.uniform(-5000, 0),
                step_min=rng.uniform(0.25, 30),
                seed=seed * 100 + i,
            )
            for i, name in enumerate(
                ["betting", "kalshi", "polymarket", "espn", "stat_model"]
            )
        }
        assert _as_tuples(
            compute_aggregated_probability(sources, bucket_seconds=60)
        ) == _as_tuples(_oracle_aggregated_probability(sources, bucket_seconds=60))

    def test_the_specimen_shape_agrees_exactly(self):
        """The real one. 4,600-odd buckets is where an off-by-one would hide."""
        sources = _specimen_shape()
        shipped = compute_aggregated_probability(sources, bucket_seconds=60)
        oracle = _oracle_aggregated_probability(sources, bucket_seconds=60)
        assert len(shipped) > 4000, "the shape under test collapsed — nothing proved"
        assert _as_tuples(shipped) == _as_tuples(oracle)

    @pytest.mark.parametrize("bucket_seconds", [1, 30, 60, 300])
    def test_every_bucket_size_agrees(self, bucket_seconds):
        """The cursor advances on `bucket_ts + bucket_seconds`; a bucket size
        the carry-forward window straddles is exactly where that would drift."""
        sources = {
            "kalshi": _series(120, step_min=0.5, seed=11),
            "espn": _series(90, start_min=7, step_min=1.5, seed=12),
        }
        assert _as_tuples(
            compute_aggregated_probability(sources, bucket_seconds=bucket_seconds)
        ) == _as_tuples(
            _oracle_aggregated_probability(sources, bucket_seconds=bucket_seconds)
        )

    def test_duplicate_timestamps_pick_the_same_reading(self):
        """Two points in one bucket: both implementations take the LAST."""
        dup = _series(40, step_min=1, seed=13)
        dup = dup + [
            TimestampedProb(timestamp=p.timestamp, home_probability=0.123)
            for p in dup[10:20]
        ]
        sources = {"kalshi": dup, "espn": _series(30, step_min=1, seed=14)}
        assert _as_tuples(
            compute_aggregated_probability(sources, bucket_seconds=60)
        ) == _as_tuples(_oracle_aggregated_probability(sources, bucket_seconds=60))

    def test_unsorted_input_agrees(self):
        """Both sort first. A cursor over an unsorted list would be nonsense,
        so this is the arm that says the sort still happens."""
        rng = random.Random(15)
        pts = _series(200, step_min=0.75, seed=15)
        rng.shuffle(pts)
        sources = {"kalshi": pts, "polymarket": _series(150, step_min=1.1, seed=16)}
        assert _as_tuples(
            compute_aggregated_probability(sources, bucket_seconds=60)
        ) == _as_tuples(_oracle_aggregated_probability(sources, bucket_seconds=60))

    def test_a_source_that_starts_after_every_bucket_is_carried_the_same(self):
        """`index == 0` is the new spelling of `latest is None`. A source whose
        first point is later than every bucket it is asked about must be absent
        from those buckets, not clamped to its first reading."""
        sources = {
            "kalshi": _series(50, step_min=1, seed=17),
            "polymarket": _series(3, start_min=10_000, step_min=1, seed=18),
        }
        shipped = compute_aggregated_probability(sources, bucket_seconds=60)
        assert _as_tuples(shipped) == _as_tuples(
            _oracle_aggregated_probability(sources, bucket_seconds=60)
        )
        assert len(shipped) > 40, "the late source swallowed the series"

    def test_single_point_and_empty_sources_agree(self):
        sources = {
            "kalshi": _series(1, seed=19),
            "polymarket": [],
            "espn": _series(5, start_min=3, seed=20),
        }
        assert _as_tuples(
            compute_aggregated_probability(sources, bucket_seconds=60)
        ) == _as_tuples(_oracle_aggregated_probability(sources, bucket_seconds=60))

    def test_no_sources_and_all_empty_return_nothing(self):
        assert compute_aggregated_probability({}, bucket_seconds=60) == []
        assert compute_aggregated_probability(
            {"kalshi": [], "espn": []}, bucket_seconds=60
        ) == []

    def test_the_bucket_timezone_is_still_the_first_sources(self):
        """Hoisted out of the bucket loop, so the arm that proves it stayed."""
        eastern = timezone(timedelta(hours=-4))
        sources = {
            "kalshi": [
                TimestampedProb(
                    timestamp=_T0.astimezone(eastern) + timedelta(minutes=i),
                    home_probability=0.5,
                )
                for i in range(10)
            ]
        }
        shipped = compute_aggregated_probability(sources, bucket_seconds=60)
        oracle = _oracle_aggregated_probability(sources, bucket_seconds=60)
        assert [p.timestamp.utcoffset() for p in shipped] == [
            p.timestamp.utcoffset() for p in oracle
        ]
        assert shipped[0].timestamp.utcoffset() == timedelta(hours=-4)


class TestItIsLinearAndTheBudgetIsNotVacuous:
    def test_the_specimen_is_built_inside_the_budget(self):
        elapsed, out = _time_it(compute_aggregated_probability, _specimen_shape())
        assert len(out) > 4000, "the shape under test collapsed — nothing timed"
        assert elapsed < _BUDGET_S, (
            f"the blend line took {elapsed:.2f}s to build for one finished game "
            f"— this is the four seconds of app time #6546 measured"
        )

    def test_the_implementation_it_replaced_reads_every_point_again_per_bucket(self):
        """THE CONTROL. Counted, not timed — see `_BUDGET_S` for why.

        This replaces a `shipped_s * 10 < oracle_s` wall-clock ratio that went
        red on master at 8.05x against its 10x bar. It was not a regression: the
        two implementations are only ~8x apart on a loaded CI runner, while the
        same shipped code varies ~19x between machines, so the bar was measuring
        the box. Counting the work removes the box from the measurement entirely.

        The oracle restarts each source scan per bucket; the shipped one-pass
        scan does not. Measured: 972x, on identical output.
        """
        oracle_reads, oracle_out = _point_reads(_oracle_aggregated_probability)
        shipped_reads, shipped_out = _point_reads(compute_aggregated_probability)

        # ANTI-VACUITY, FIRST. A probe that broke either implementation would
        # report a small count and this test would "pass" by measuring nothing.
        # Both must still produce the real answer, and the same one.
        assert shipped_out, "the probed run produced no line — the probe is broken"
        assert _as_tuples(shipped_out) == _as_tuples(
            compute_aggregated_probability(_specimen_shape(), bucket_seconds=60)
        ), "the counting probe changed the shipped result — the counts are meaningless"
        assert _as_tuples(oracle_out) == _as_tuples(shipped_out), (
            "the two implementations disagree under the probe — this file's "
            "equivalence arms are the place to look, not the budget"
        )

        points = sum(len(v) for v in _specimen_shape().values())
        assert shipped_reads <= points * _MAX_READS_PER_POINT, (
            f"the shipped scan read {shipped_reads:,} timestamps for {points:,} "
            f"points ({shipped_reads / points:.1f} each) — more than a constant "
            "number of passes, so the carry-forward is rescanning"
        )
        assert oracle_reads > shipped_reads * _MIN_READ_RATIO, (
            f"the pre-#6546 implementation read {oracle_reads:,} timestamps vs "
            f"the shipped {shipped_reads:,} ({oracle_reads / max(shipped_reads, 1):.0f}x). "
            "Under 50x means the control no longer reproduces the per-bucket "
            "rescan it exists to represent, so this file has stopped guarding "
            "the defect it was written for."
        )

    def test_quadrupling_the_input_does_not_sixteen_times_the_work(self):
        """Machine-independent — counted, not timed. Converted 2026-09-17.

        Linear work grows ~4x when the series and its buckets grow 4x; the scan
        this replaced grew ~16x. The bar sits between them rather than at either
        end, so ordinary noise cannot decide it.

        IT USED TO DIVIDE TWO WALL-CLOCK READINGS, and the docstring's first
        line claimed that was machine-independent. It was not, and the arm
        directly above it had already been converted for the same reason
        (`26927ff18`, #6546) while this one was left on the clock. On CI it went
        red at **134.2x / 86.3x / 142.8x** (calibration/1352, sha `9cd1ef1b3`,
        run 35286098562) and **90.2x / 93.6x** (live/362, sha `147f036c0`, run
        35288974082) against this same bar of 8 — two lanes, two diffs disjoint
        from each other AND from `aggregation.py`, both green on master in the
        same minutes, both green 19/19 locally.

        The arithmetic of why: the SMALL arm runs ~2 ms on a laptop and ~3.5 ms
        on CI, and `large / small` puts that on the bottom of a fraction. A few
        milliseconds of noise from whatever else shares the process — and both
        red branches added a test file, which reshuffles who a shard's
        neighbours are — moves the ratio by an order of magnitude without any
        code changing. A denominator that small cannot carry a proof.

        Measured on the counts, same two arms, 2026-09-17: points 900 -> 3,600
        (4.00x); shipped reads 2,701 -> 10,801, growth **4.00x**, a flat 3.0
        reads per point on BOTH arms; oracle reads 231,544 -> 3,626,194, growth
        **15.66x**. Linear and quadratic land where the names say, the bar of 8
        sits halfway between them, and no machine enters the number.
        """
        small = {
            "kalshi": _series(500, step_min=1, seed=31),
            "polymarket": _series(400, step_min=1.25, seed=32),
        }
        large = {
            "kalshi": _series(2000, step_min=1, seed=31),
            "polymarket": _series(1600, step_min=1.25, seed=32),
        }

        small_reads, small_out = _point_reads(compute_aggregated_probability, small)
        large_reads, large_out = _point_reads(compute_aggregated_probability, large)

        # ANTI-VACUITY, FIRST — the same clause the arm above carries. A probe
        # that broke the implementation would report small counts and this test
        # would "pass" by measuring nothing.
        assert (
            small_out and large_out
        ), "a probed run produced no line — the probe is broken"
        assert _as_tuples(large_out) == _as_tuples(
            compute_aggregated_probability(large, bucket_seconds=60)
        ), "the counting probe changed the shipped result — the counts are meaningless"
        assert len(large_out) == 4 * len(small_out), (
            f"the two arms built {len(small_out)} and {len(large_out)} buckets — "
            "quadrupling the input did not quadruple the work being measured, so "
            "this arm is no longer comparing what it says it compares"
        )

        growth = large_reads / max(small_reads, 1)
        assert growth < 8, (
            f"4x the points cost {growth:.1f}x the reads ({small_reads:,} -> "
            f"{large_reads:,}) — the carry-forward is scanning from the start of "
            "each source again"
        )

        # THE CONTROL, which the wall-clock version never had: the scan this
        # replaced must FAIL the bar this one passes, on the same two arms in
        # the same run. Without it a green row here is consistent with the
        # measurement having quietly stopped measuring.
        oracle_small, _ = _point_reads(_oracle_aggregated_probability, small)
        oracle_large, _ = _point_reads(_oracle_aggregated_probability, large)
        oracle_growth = oracle_large / max(oracle_small, 1)
        assert oracle_growth >= 8, (
            f"the pre-#6546 scan grew only {oracle_growth:.1f}x ({oracle_small:,} "
            f"-> {oracle_large:,}) across the same 4x — it would pass the bar it "
            "exists to fail, so this arm is vacuous and the shapes above need "
            "resizing, not the bar"
        )
