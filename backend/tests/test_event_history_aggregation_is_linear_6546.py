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
# still verbatim and is still the control. The weighting block carries the
# #6461 rule, mirrored inline rather than imported, so that the two
# implementations remain independent and this file keeps failing if the scan
# ever disagrees. #6461's own behaviour is proved next door, in
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


#: The shipped implementation must build the specimen's line in well under this.
#: It measures ~0.015 s; the budget leaves ~30x of headroom for a slow CI box,
#: and the control below proves the budget is still tight enough to catch the
#: defect it was written for.
_BUDGET_S = 0.5


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

    def test_the_implementation_it_replaced_blows_that_budget(self):
        """THE CONTROL. Without this the arm above measures the laptop.

        The oracle is the code that ran in production on 2026-09-16; it must be
        comfortably over the budget on the same machine, in the same run, on the
        same data.
        """
        oracle_s, _ = _time_it(_oracle_aggregated_probability, _specimen_shape())
        shipped_s, _ = _time_it(compute_aggregated_probability, _specimen_shape())
        assert oracle_s > _BUDGET_S, (
            f"the pre-#6546 implementation built the specimen in {oracle_s:.2f}s, "
            "inside the budget — the budget no longer catches the defect it was "
            "written for and needs re-sizing against a current measurement"
        )
        assert shipped_s * 10 < oracle_s, (
            f"shipped {shipped_s:.3f}s vs oracle {oracle_s:.3f}s — less than the "
            "order of magnitude the one-pass scan is supposed to buy"
        )

    def test_quadrupling_the_input_does_not_sixteen_times_the_work(self):
        """Machine-independent, which the budget above is not.

        Linear work grows ~4x when the series and its buckets grow 4x; the scan
        this replaced grew ~16x. The bar sits between them rather than at either
        end, so ordinary noise cannot decide it.
        """
        small = {
            "kalshi": _series(500, step_min=1, seed=31),
            "polymarket": _series(400, step_min=1.25, seed=32),
        }
        large = {
            "kalshi": _series(2000, step_min=1, seed=31),
            "polymarket": _series(1600, step_min=1.25, seed=32),
        }
        small_s, _ = _time_it(compute_aggregated_probability, small)
        large_s, _ = _time_it(compute_aggregated_probability, large)
        growth = large_s / max(small_s, 1e-6)
        assert growth < 8, (
            f"4x the points cost {growth:.1f}x the time — the carry-forward is "
            "scanning from the start of each source again"
        )
