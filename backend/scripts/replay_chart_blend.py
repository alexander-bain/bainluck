#!/usr/bin/env python3
"""Replay a saved ``/api/events/{id}/history`` payload through the chart blend.

#6461. The acceptance test for the source-switch-jump repair is "replay the
existing observations against before and after, and explain every jump that
went away" — this is the harness that does it, so the numbers in the issue and
the cert can be re-derived by anyone instead of quoted.

The payload is the right input and not a convenience: ``history`` (sportsbook
consensus) and ``win_prob_history`` (every model/venue series) are the exact
two things ``routes/events.py`` hands ``compute_aggregated_probability``, so a
replay off the saved payload reconstructs the served line rather than
approximating it. Verified on the specimen: 258 of 261 interior points come
back bit-identical, the three that differ being the live-edge extension and the
right-edge pin, both of which run outside the aggregation and are deliberately
not modelled here.

Usage::

    python3 backend/scripts/replay_chart_blend.py PAYLOAD.json
    python3 backend/scripts/replay_chart_blend.py PAYLOAD.json --json
    python3 backend/scripts/replay_chart_blend.py --dry-run

``--dry-run`` runs the whole comparison on a small built-in series and touches
no file, so the script can prove itself on an exact sha with nothing fetched.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.aggregation import (  # noqa: E402
    SOURCE_WEIGHTS,
    STALENESS_GRACE_PERIOD,
    MAX_STALENESS,
    TimestampedProb,
    _UNCAPPED_SOURCES,
    _weighted_median,
    cap_weight_shares,
    compute_aggregated_probability,
)

JUMP_THRESHOLD = 0.05


def _absolute_staleness_weight(stale_seconds: float) -> float:
    """The pre-#6461 rule, kept verbatim as the BEFORE arm.

    A copy rather than an import on purpose: the point of the comparison is to
    survive the day the shipped function changes again, and an oracle that
    tracks the code it is measuring measures nothing. (Same reason
    ``test_event_history_aggregation_is_linear_6546.py`` keeps its own copy.)
    """
    if stale_seconds <= STALENESS_GRACE_PERIOD:
        return 1.0
    if stale_seconds >= MAX_STALENESS:
        return 0.0
    return max(
        0.0,
        1.0
        - (stale_seconds - STALENESS_GRACE_PERIOD)
        / (MAX_STALENESS - STALENESS_GRACE_PERIOD),
    )


def blend_before(
    sources: dict[str, list[TimestampedProb]], bucket_seconds: int = 60
) -> list[tuple[float, float, tuple[str, ...]]]:
    """Pre-#6461 series: absolute age, full weight 2 min, gone at 5.

    Returns ``(bucket_epoch, probability, contributing sources)`` so the caller
    can say WHICH sources fed each point, which is the whole question.
    """
    if not sources:
        return []

    ordered = {k: sorted(v, key=lambda p: p.timestamp) for k, v in sources.items()}
    buckets = sorted(
        {
            int(p.timestamp.timestamp() // bucket_seconds) * bucket_seconds
            for pts in ordered.values()
            for p in pts
        }
    )

    out: list[tuple[float, float, tuple[str, ...]]] = []
    for bucket_ts in buckets:
        limit = bucket_ts + bucket_seconds
        readings: list[tuple[str, float, float]] = []
        for key, pts in ordered.items():
            latest: Optional[TimestampedProb] = None
            for point in pts:
                if point.timestamp.timestamp() <= limit:
                    latest = point
                else:
                    break
            if latest is None:
                continue
            stale = max(0.0, bucket_ts - latest.timestamp.timestamp())
            weight = SOURCE_WEIGHTS.get(key, 0.5) * _absolute_staleness_weight(stale)
            if weight > 0:
                readings.append((key, latest.home_probability, weight))
        if not readings:
            continue
        weights = cap_weight_shares(
            [w for _, _, w in readings],
            exempt=[k in _UNCAPPED_SOURCES for k, _, _ in readings],
        )
        value = _weighted_median([p for _, p, _ in readings], weights)
        out.append(
            (bucket_ts, round(value, 6), tuple(sorted(k for k, _, _ in readings)))
        )
    return out


def blend_after(
    sources: dict[str, list[TimestampedProb]], bucket_seconds: int = 60
) -> list[tuple[float, float, tuple[str, ...]]]:
    """The shipped series, called for real — never re-implemented here.

    Contributor sets come from a second pass rather than from the function,
    which returns values only; they are reported for explanation and are not
    what the repair is judged on.
    """
    line = compute_aggregated_probability(sources, bucket_seconds=bucket_seconds)
    contributors = _contributors_after(sources, bucket_seconds)
    return [
        (
            p.timestamp.timestamp(),
            p.home_probability,
            contributors.get(
                int(p.timestamp.timestamp() // bucket_seconds) * bucket_seconds, ()
            ),
        )
        for p in line
    ]


def _contributors_after(
    sources: dict[str, list[TimestampedProb]], bucket_seconds: int
) -> dict[int, tuple[str, ...]]:
    from app.utils.aggregation import _relative_staleness_multiplier

    ordered = {k: sorted(v, key=lambda p: p.timestamp) for k, v in sources.items()}
    buckets = sorted(
        {
            int(p.timestamp.timestamp() // bucket_seconds) * bucket_seconds
            for pts in ordered.values()
            for p in pts
        }
    )
    out: dict[int, tuple[str, ...]] = {}
    for bucket_ts in buckets:
        limit = bucket_ts + bucket_seconds
        cands: list[tuple[str, float]] = []
        for key, pts in ordered.items():
            latest_epoch = None
            for point in pts:
                epoch = point.timestamp.timestamp()
                if epoch <= limit:
                    latest_epoch = epoch
                else:
                    break
            if latest_epoch is not None:
                cands.append((key, latest_epoch))
        if not cands:
            continue
        decay = [e for k, e in cands if k not in _UNCAPPED_SOURCES]
        reference = max(decay) if decay else None
        live = []
        for key, epoch in cands:
            age = (
                0.0
                if (reference is None or key in _UNCAPPED_SOURCES)
                else max(0.0, reference - epoch)
            )
            if (
                SOURCE_WEIGHTS.get(key, 0.5)
                * _relative_staleness_multiplier(age, floor=0.0)
                > 0
            ):
                live.append(key)
        if live:
            out[bucket_ts] = tuple(sorted(live))
    return out


def sources_from_payload(payload: dict[str, Any]) -> dict[str, list[TimestampedProb]]:
    """Rebuild the route's ``agg_sources`` from a saved history payload.

    Mirrors ``routes/events.py``: sportsbook consensus enters as ``betting``,
    every ``win_prob_history`` key enters under its own name, and a null
    probability is skipped rather than coerced.
    """
    out: dict[str, list[TimestampedProb]] = {}

    betting = [
        TimestampedProb(datetime.fromisoformat(h["timestamp"]), h["home_probability"])
        for h in (payload.get("history") or [])
        if h.get("home_probability") is not None
    ]
    if betting:
        out["betting"] = betting

    for key, points in (payload.get("win_prob_history") or {}).items():
        series = [
            TimestampedProb(
                datetime.fromisoformat(p["timestamp"]), p["home_probability"]
            )
            for p in points
            if p.get("home_probability") is not None
        ]
        if series:
            out[key] = series
    return out


def _jumps(line: list[tuple[float, float, tuple[str, ...]]]) -> list[dict[str, Any]]:
    out = []
    for i in range(1, len(line)):
        delta = line[i][1] - line[i - 1][1]
        if abs(delta) >= JUMP_THRESHOLD:
            out.append(
                {
                    "from": datetime.fromtimestamp(
                        line[i - 1][0], tz=timezone.utc
                    ).isoformat(),
                    "to": datetime.fromtimestamp(
                        line[i][0], tz=timezone.utc
                    ).isoformat(),
                    "from_prob": round(line[i - 1][1], 4),
                    "to_prob": round(line[i][1], 4),
                    "delta_pp": round(delta * 100, 1),
                    "sources_before": list(line[i - 1][2]),
                    "sources_after": list(line[i][2]),
                    "source_set_changed": line[i - 1][2] != line[i][2],
                }
            )
    return out


def _summary(
    label: str, line: list[tuple[float, float, tuple[str, ...]]]
) -> dict[str, Any]:
    jumps = _jumps(line)
    variation = sum(abs(line[i][1] - line[i - 1][1]) for i in range(1, len(line)))
    set_changes = sum(1 for i in range(1, len(line)) if line[i][2] != line[i - 1][2])
    return {
        "arm": label,
        "points": len(line),
        "jumps_ge_5pp": len(jumps),
        "jumps_with_source_set_change": sum(
            1 for j in jumps if j["source_set_changed"]
        ),
        "source_set_changes": set_changes,
        "total_variation": round(variation, 4),
        "first": round(line[0][1], 4) if line else None,
        "last": round(line[-1][1], 4) if line else None,
        "jumps": jumps,
    }


def _dry_run_sources() -> dict[str, list[TimestampedProb]]:
    """A three-source series whose only movement is cadence, plus one real move.

    Deliberately not the specimen: ``--dry-run`` exists to prove the script
    executes, and a fixture it can carry in-process keeps that proof independent
    of any saved file.
    """
    base = datetime(2026, 9, 6, 17, 0, 0, tzinfo=timezone.utc)
    return {
        # Fast poller, flat, far from the others.
        "espn": [
            TimestampedProb(base + timedelta(seconds=s), 0.10)
            for s in range(0, 1800, 180)
        ],
        # Slow poller — the one absolute age used to delete between writes.
        "betting": [
            TimestampedProb(base + timedelta(seconds=s), 0.60 if s < 900 else 0.35)
            for s in range(0, 1800, 600)
        ],
        "stat_model": [
            TimestampedProb(base + timedelta(seconds=s), 0.55 if s < 900 else 0.33)
            for s in range(0, 1800, 300)
        ],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", help="saved /history JSON")
    parser.add_argument("--bucket-seconds", type=int, default=60)
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run on a built-in fixture and read no file",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        sources = _dry_run_sources()
        label = "built-in fixture"
    else:
        if not args.payload:
            parser.error("a payload path is required unless --dry-run is given")
        payload = json.loads(Path(args.payload).read_text())
        sources = sources_from_payload(payload)
        label = f"{args.payload} (event {payload.get('event_id')})"

    if not sources:
        print("no source series in payload — nothing to replay", file=sys.stderr)
        return 1

    before = _summary("before", blend_before(sources, args.bucket_seconds))
    after = _summary("after", blend_after(sources, args.bucket_seconds))

    if args.json:
        print(json.dumps({"input": label, "before": before, "after": after}, indent=2))
        return 0

    print(f"replay: {label}")
    print(f"sources: { {k: len(v) for k, v in sorted(sources.items())} }")
    print()
    print(f"{'':<28}{'before':>10}{'after':>10}")
    for field in (
        "points",
        "jumps_ge_5pp",
        "jumps_with_source_set_change",
        "source_set_changes",
        "total_variation",
        "first",
        "last",
    ):
        print(f"{field:<28}{str(before[field]):>10}{str(after[field]):>10}")
    print()
    print(f"surviving jumps ({len(after['jumps'])}) — each must be a real move:")
    for j in after["jumps"]:
        print(
            f"  {j['from'][11:16]} -> {j['to'][11:16]}  "
            f"{j['from_prob']:.3f} -> {j['to_prob']:.3f}  ({j['delta_pp']:+.1f}pp)  "
            f"sources {'CHANGED' if j['source_set_changed'] else 'unchanged'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
