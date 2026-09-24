"""#8349 — a live chart stops rewriting the minute that just ended.

THE SHIP, IN A READER'S WORDS: on a live game page, the probability line for a
minute that is already over stays put when the next minute's data arrives, and
each source is drawn in the minute it was captured, not the one before.

WHAT WAS WRONG. `compute_aggregated_probability` carries each source's latest
reading into every time bucket. Its scan admitted points with
`epoch <= bucket_ts + bucket_seconds`, so the top of each bucket was CLOSED: a
point stamped exactly on the next bucket's start was claimed by the bucket
before it too. Sportsbook history is keyed on the minute rounded down, so every
point of the heaviest source (`betting`, weight 3.0) sits exactly on a boundary.
The result was that source drawn one bucket early, and each finished bucket
rewritten once, when the next minute's sportsbook point landed.

Specimen (native/316's two saved payloads, Astros–Mariners 15317698): bucket
04:20 served .5766 at 04:21:19Z and .5697 at 04:22:39Z. .5697 is exactly the
sportsbook point stamped 04:21:00, which first appeared in the second read.

WHAT THIS ASSERTS.

* THE RULE: a bucket is half-open, [bucket_ts, bucket_ts + bucket_seconds).
  Just before the edge counts, exactly on the edge counts for the next bucket
  only, and just after counts for the next bucket.
* THE READER'S CLAIM: appending later observations, including ones stamped
  exactly on a boundary, never changes a bucket that has already ended.
* THE CONTRACTS THAT MUST NOT MOVE: source weights still decide the median;
  a pre-game bucket is still judged on `limit <= pregame_epoch` (#4976); a
  `final_result` point is still exempt from ageing and claimed by its own
  bucket (#6461).
* THE LITERAL REPLAY: the saved pair, trimmed to 03:40Z onward with one
  carry-in point per source (`fixtures/chart_bucket_edge_15317698_8349.json`).
  The served `aggregate_line` values are production output of the OLD rule and
  are never refreshed (notice 50). Every bucket where the fixed rule differs
  from what was served has a source point on its upper edge, and every bucket
  without one matches exactly. So each changed value comes from the boundary
  rule and nothing else.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.aggregation import (
    TimestampedProb,
    compute_aggregated_probability,
    pregame_boundary,
)

BASE = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "chart_bucket_edge_15317698_8349.json"


def _tp(seconds: float, prob: float) -> TimestampedProb:
    return TimestampedProb(
        timestamp=BASE + timedelta(seconds=seconds), home_probability=prob
    )


def _by_bucket(line) -> dict[datetime, float]:
    return {p.timestamp: p.home_probability for p in line}


def _bucket(minute: int) -> datetime:
    return BASE + timedelta(minutes=minute)


# ── THE RULE ─────────────────────────────────────────────────────────────────


class TestTheBucketIsHalfOpen:
    """One source, so the line IS the series and weighting cannot hide an
    off-by-one."""

    def test_a_point_just_before_the_edge_belongs_to_its_bucket(self):
        line = _by_bucket(
            compute_aggregated_probability(
                {"betting": [_tp(0, 0.40), _tp(59.999, 0.70)]}, bucket_seconds=60
            )
        )
        assert line == {_bucket(0): pytest.approx(0.70)}

    def test_a_point_exactly_on_the_edge_belongs_to_the_next_bucket_only(self):
        line = _by_bucket(
            compute_aggregated_probability(
                {"betting": [_tp(0, 0.40), _tp(60, 0.70)]}, bucket_seconds=60
            )
        )
        assert line[_bucket(0)] == pytest.approx(0.40), (
            "the point stamped exactly 04:01:00 was claimed by the 04:00 bucket "
            "— the inclusive edge #8349 removed"
        )
        assert line[_bucket(1)] == pytest.approx(0.70)

    def test_a_point_just_after_the_edge_belongs_to_the_next_bucket(self):
        line = _by_bucket(
            compute_aggregated_probability(
                {"betting": [_tp(0, 0.40), _tp(60.001, 0.70)]}, bucket_seconds=60
            )
        )
        assert line[_bucket(0)] == pytest.approx(0.40)
        assert line[_bucket(1)] == pytest.approx(0.70)

    @pytest.mark.parametrize("bucket_seconds", [1, 30, 60, 300])
    def test_every_bucket_size_is_half_open(self, bucket_seconds):
        sources = {"betting": [_tp(0, 0.40), _tp(bucket_seconds, 0.70)]}
        line = _by_bucket(
            compute_aggregated_probability(sources, bucket_seconds=bucket_seconds)
        )
        assert line[BASE] == pytest.approx(0.40)
        assert line[BASE + timedelta(seconds=bucket_seconds)] == pytest.approx(0.70)

    def test_a_minute_floored_sportsbook_series_is_drawn_in_its_own_minutes(self):
        """The production shape: sportsbook points on every round minute."""
        prices = [0.50, 0.55, 0.61, 0.58, 0.64]
        sources = {"betting": [_tp(60 * i, p) for i, p in enumerate(prices)]}
        line = _by_bucket(compute_aggregated_probability(sources, bucket_seconds=60))
        assert [line[_bucket(i)] for i in range(len(prices))] == [
            pytest.approx(p) for p in prices
        ]


# ── THE READER'S CLAIM ───────────────────────────────────────────────────────


def _live_game(minutes: int, seed: int) -> dict[str, list[TimestampedProb]]:
    """Production shape: sportsbook on round minutes, kalshi at arbitrary
    seconds, a slower stat model, and an espn feed that lands on round minutes
    now and then."""
    rng = random.Random(seed)
    sources: dict[str, list[TimestampedProb]] = {
        "betting": [],
        "kalshi": [],
        "stat_model": [],
        "espn": [],
    }
    for m in range(minutes):
        sources["betting"].append(_tp(60 * m, rng.uniform(0.3, 0.7)))
        for _ in range(rng.randint(0, 3)):
            sources["kalshi"].append(_tp(60 * m + rng.uniform(0, 59.9), rng.uniform(0.3, 0.7)))
        if m % 3 == 0:
            sources["stat_model"].append(_tp(60 * m + rng.uniform(0, 59.9), rng.uniform(0.3, 0.7)))
        if rng.random() < 0.3:
            sources["espn"].append(_tp(60 * m, rng.uniform(0.3, 0.7)))
    return sources


class TestAFinishedBucketNeverChanges:
    @pytest.mark.parametrize("seed", range(8))
    def test_the_next_minutes_arrival_cannot_alter_an_earlier_bucket(self, seed):
        """Read the chart at the end of minute N, then again after every
        source's minute-N+1 points (sportsbook exactly on the boundary) have
        arrived. Every bucket before N+1 must be identical."""
        full = _live_game(40, seed)
        for cut_minute in (10, 25, 39):
            cut = BASE + timedelta(minutes=cut_minute)
            early = {k: [p for p in v if p.timestamp < cut] for k, v in full.items()}
            later = {
                k: [p for p in v if p.timestamp < cut + timedelta(minutes=1)]
                for k, v in full.items()
            }
            first = _by_bucket(compute_aggregated_probability(early, bucket_seconds=60))
            second = _by_bucket(compute_aggregated_probability(later, bucket_seconds=60))
            assert first, "vacuous: the early read drew nothing"
            changed = [t for t, v in first.items() if second[t] != v]
            assert changed == [], (
                f"buckets {changed} were rewritten by data stamped at or after "
                f"{cut:%H:%M}"
            )

    def test_the_arrival_is_actually_on_the_boundary(self):
        """The property above is only a test of #8349 if the appended minute
        really carries a point exactly on the boundary. Proves it, rather than
        trusting the generator."""
        full = _live_game(40, 0)
        cut = BASE + timedelta(minutes=10)
        assert any(p.timestamp == cut for p in full["betting"])


# ── THE CONTRACTS THAT MUST NOT MOVE ─────────────────────────────────────────


class TestTheContractsAroundTheEdgeHold:
    def test_source_weights_still_decide_the_median_inside_a_bucket(self):
        """betting (3.0) vs espn (1.5), both inside bucket 0: betting leads.
        A betting point stamped on the edge now joins bucket 1, where espn's
        carry-forward is still present, and betting still leads there."""
        sources = {
            "betting": [_tp(10, 0.70), _tp(60, 0.72)],
            "espn": [_tp(20, 0.30)],
        }
        line = _by_bucket(compute_aggregated_probability(sources, bucket_seconds=60))
        assert line[_bucket(0)] == pytest.approx(0.70)
        assert line[_bucket(1)] == pytest.approx(0.72)

    def test_the_pregame_edge_is_unchanged(self):
        """#4976 judges pre-game on the bucket's LIMIT (`limit <= pregame_epoch`).
        #8349 changed which points a bucket sees, not which bucket is pre-game.

        Kickoff 04:02:00. betting is an hour stale at 0.70; kalshi quotes 0.30
        before the bell and 0.90 exactly AT it. Bucket 04:01 is the last
        pre-game bucket: nothing is aged, betting's weight leads, and kalshi's
        kickoff reading is not in it. Bucket 04:02 is in play: betting is aged
        to the floor and the kickoff reading, in its own bucket, leads."""
        kick = BASE + timedelta(minutes=2)
        sources = {
            "betting": [_tp(-3600, 0.70)],
            "kalshi": [_tp(90, 0.30), _tp(120, 0.90)],
        }
        pre = _by_bucket(
            compute_aggregated_probability(sources, bucket_seconds=60, pregame_until=kick)
        )
        no_gate = _by_bucket(compute_aggregated_probability(sources, bucket_seconds=60))
        assert pre[_bucket(1)] == pytest.approx(0.70)
        assert pre[_bucket(2)] == pytest.approx(0.90)
        # The gate is doing the work at 04:01: without it betting is aged there.
        assert no_gate[_bucket(1)] == pytest.approx(0.30)

    def test_a_final_result_on_the_edge_is_claimed_by_its_own_bucket(self):
        sources = {
            "betting": [_tp(0, 0.60)],
            "final_result": [_tp(60, 1.0)],
        }
        line = _by_bucket(compute_aggregated_probability(sources, bucket_seconds=60))
        assert line[_bucket(0)] == pytest.approx(0.60), (
            "a result stamped 04:01:00 was drawn in the 04:00 bucket"
        )
        assert line[_bucket(1)] == pytest.approx(1.0)


# ── THE LITERAL REPLAY ───────────────────────────────────────────────────────


def _load_reads():
    data = json.loads(FIXTURE.read_text())
    reads = []
    for read in data["reads"]:
        sources = {
            key: [
                TimestampedProb(timestamp=datetime.fromisoformat(t), home_probability=p)
                for t, p in points
            ]
            for key, points in read["inputs"].items()
        }
        now = datetime.fromisoformat(read["time_domain_end"])
        pregame = pregame_boundary(
            read["status"], datetime.fromisoformat(read["commence_time"]), now
        )
        served = {datetime.fromisoformat(t): p for t, p in read["aggregate_line"]}
        replay = {
            p.timestamp: round(p.home_probability, 4)
            for p in compute_aggregated_probability(
                sources, bucket_seconds=60, pregame_until=pregame
            )
        }
        # The last served bucket is pinned to the live edge by the route
        # (`blend_edge_pinned`), not produced by the scan.
        last = max(served)
        reads.append((sources, served, replay, last))
    return reads


EDGE_0420 = datetime(2026, 9, 24, 4, 20, tzinfo=timezone.utc)


class TestTheSavedPairReplays:
    def test_the_control_shows_the_revision_the_reader_saw(self):
        """The served values are the old rule's production output. Before any
        claim about the fix, prove the literal control really holds the defect."""
        (_, served_a, _, _), (_, served_b, _, _) = _load_reads()
        assert served_a[EDGE_0420] == pytest.approx(0.5766)
        assert served_b[EDGE_0420] == pytest.approx(0.5697)

    def test_the_0420_bucket_is_stable_across_both_reads(self):
        (_, _, replay_a, _), (_, _, replay_b, _) = _load_reads()
        assert replay_a[EDGE_0420] == pytest.approx(0.5766)
        assert replay_b[EDGE_0420] == pytest.approx(0.5766)

    def test_only_the_minute_in_progress_changes_between_reads(self):
        (_, _, replay_a, last_a), (_, _, replay_b, _) = _load_reads()
        finished = [t for t in replay_a if t < last_a]
        assert len(finished) >= 40, "vacuous: the window lost its buckets"
        assert [t for t in finished if replay_b[t] != replay_a[t]] == []

    def test_every_changed_value_is_attributable_to_the_boundary(self):
        """Where the fix differs from what production served, some source has a
        point on that bucket's upper edge. Where no source does, the fix
        reproduces production exactly. Both directions, both reads."""
        for sources, served, replay, last in _load_reads():
            edges = {
                p.timestamp - timedelta(seconds=60)
                for points in sources.values()
                for p in points
            }
            compared = [t for t in served if t != last]
            changed = [t for t in compared if abs(replay[t] - served[t]) > 1e-4]
            unchanged_on_edge = [t for t in compared if t in edges and t not in changed]
            assert changed, "vacuous: the fix moved nothing on the specimen"
            assert [t for t in changed if t not in edges] == [], (
                "a served value moved at a bucket with no point on its edge — "
                "that change is not the boundary rule's"
            )
            assert all(
                abs(replay[t] - served[t]) <= 1e-4
                for t in compared
                if t not in edges
            )
            # Some on-edge buckets legitimately keep their value (the edge point
            # happens to leave the median where it was); recorded, not asserted.
            del unchanged_on_edge
