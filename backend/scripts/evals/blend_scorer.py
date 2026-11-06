"""#12108: score a SHA-256-pinned replay without reading a database or fitting.

python -m scripts.evals.blend_scorer --input replay.json --sha256 <digest>

Reports league x horizon x time split x record kind, not a pooled headline.
Held-out metrics use recorded publications only. No weights or licences change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from app.utils.aggregation import SOURCE_WEIGHTS, compute_aggregate_probability_tiered
from app.utils.calibration_scoring import _stats
from app.utils.probability_publication import BLEND_METHOD
from scripts.evals.blend_replay_export import SCHEMA, probability


def replay(row: dict) -> tuple[float | None, str | None]:
    if row["kind"] == "served" and row["blend_method"] != BLEND_METHOD:
        raise ValueError("recorded method does not match the current replay method")
    inputs = row["blend_inputs"]
    if set(inputs) != {"espn_win_prob_home", "opening_home_probability"}:
        raise ValueError("incomplete or unexpected blend inputs")
    for value in inputs.values():
        if value is not None:
            probability(value)
    if not isinstance(row["sources"], dict):
        raise ValueError("source bag must be an object")
    for source, entry in row["sources"].items():
        if source in SOURCE_WEIGHTS:
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value is not None:
                probability(value)
    value, tier = compute_aggregate_probability_tiered(
        SimpleNamespace(
            win_probability_sources=row["sources"],
            status=row["event_status"],
            **inputs,
        ),
        row["event_status"],
    )
    if value is not None:
        probability(value)
    return value, tier


def metrics(rows: list[dict]) -> dict:
    bins: dict[int, dict] = {}
    log_loss, brier = 0.0, 0.0
    for row in rows:
        p, y = row["probability"], row["outcome"]
        bucket = min(9, math.floor(p * 10))
        cell = bins.setdefault(bucket, {"n": 0, "winners": 0, "sum_prob": 0.0})
        cell["n"] += 1
        cell["winners"] += y
        cell["sum_prob"] += p
        # Fixed before scoring; endpoint forecasts still count as large errors.
        clipped = min(1 - 1e-15, max(1e-15, p))
        log_loss -= y * math.log(clipped) + (1 - y) * math.log1p(-clipped)
        brier += (p - y) ** 2
    stats = _stats(bins)
    return {
        **stats,
        "log_loss": log_loss / len(rows) if rows else None,
        "brier": brier / len(rows) if rows else None,
    }


def intervals(rows: list[dict], *, replicates: int, seed: int) -> dict:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        clusters[row["cluster_id"]].append(row)
    names = sorted(clusters)
    if len(names) < 2:
        return {"result": "UNKNOWN", "clusters": len(names), "bounds": None}
    rng = random.Random(seed)
    samples = {key: [] for key in ("ece", "gap", "log_loss", "brier")}
    for _ in range(replicates):
        draw = [r for _ in names for r in clusters[rng.choice(names)]]
        score = metrics(draw)
        for key in samples:
            samples[key].append(score[key])
    bounds = {}
    for key, values in samples.items():
        values.sort()
        bounds[key] = [
            values[math.floor((replicates - 1) * 0.025)],
            values[math.ceil((replicates - 1) * 0.975)],
        ]
    return {"clusters": len(names), "replicates": replicates, "bounds": bounds}


def score_export(export: dict, *, replicates: int = 1000, seed: int = 12108) -> dict:
    if export["schema"] != SCHEMA:
        raise ValueError("unsupported replay schema")
    if replicates < 100:
        raise ValueError("at least 100 bootstrap replicates required")
    groups: dict[tuple, list] = defaultdict(list)
    failures = Counter({"export_packet": len(export["failures"])})
    mismatches = compared = null_rows = 0
    seen: set[tuple] = set()
    cluster_splits: dict[str, str] = {}
    for row in export["rows"]:
        try:
            identity = (int(row["event_id"]), row["horizon"], row["kind"])
            if identity in seen:
                raise ValueError("duplicate_event_horizon_kind")
            seen.add(identity)
            cluster = row["cluster_id"]
            split = row["split"]
            if not isinstance(cluster, str) or not cluster:
                raise ValueError("missing_cluster")
            if cluster in cluster_splits and cluster_splits[cluster] != split:
                raise ValueError("cluster_crosses_splits")
            cluster_splits[cluster] = split
            if split not in {"train", "tune", "held_out"}:
                continue
            if row["kind"] not in {"served", "reconstruction"}:
                raise ValueError("unknown_record_kind")
            if split == "held_out" and row["kind"] != "served":
                raise ValueError("held_out_must_be_recorded")
            y = row["outcome"]
            if y not in (0, 1) or isinstance(y, bool):
                raise ValueError("unknown_outcome")
            p, tier = replay(row)
            if row["kind"] == "served":
                compared += 1
                mismatches += (p, tier) != (row["blend_probability"], row["blend_tier"])
            if p is None:
                null_rows += 1
                continue
            groups[(row["league"], row["horizon"], split, row["kind"])].append(
                {
                    "cluster_id": cluster,
                    "probability": p,
                    "outcome": y,
                }
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            # An unreadable input is a failed row, never a silently dropped pass.
            failures["unreadable_row"] += 1
    cohorts = []
    for (league, horizon, split, kind), rows in sorted(groups.items()):
        cohorts.append(
            {
                "league": league,
                "horizon": horizon,
                "split": split,
                "kind": kind,
                **metrics(rows),
                "interval95": intervals(rows, replicates=replicates, seed=seed),
            }
        )
    failed = sum(failures.values()) or mismatches or not compared or not cohorts
    return {
        "result": "FAIL" if failed else "BASELINE_REPLAY_ONLY",
        "activation": "NONE",
        "method": BLEND_METHOD,
        "failures": dict(failures),
        "input_rows": len(export["rows"]),
        "null_probability_rows": null_rows,
        "recorded_reproduction": {"n": compared, "mismatches": mismatches},
        "cohorts": cohorts,
        "interval_basis": "series_doubleheader_cluster_percentile_bootstrap",
        "seed": seed,
        "log_loss_clip": 1e-15,
        "candidate_verdict": "UNKNOWN_NO_FROZEN_CANDIDATE",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != args.sha256:
        parser.error("input SHA-256 does not match the frozen export")
    report = score_export(json.loads(raw))
    print(json.dumps({"input_sha256": actual, **report}, allow_nan=False))
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
