"""#12108: score a SHA-256-pinned replay without reading a database or fitting.

Extends calibration_population_integrity (ruling 002).

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
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.utils.aggregation import SOURCE_WEIGHTS, compute_aggregate_probability_tiered
from app.utils.calibration_scoring import _stats
from app.utils.probability_publication import BLEND_METHOD
from scripts.evals.blend_replay_export import SCHEMA, instant, probability, time_split


def committed_protocol(
    path: Path, expected_sha256: str, *, repository: Path | None = None
) -> dict:
    """A changed working copy or untracked protocol cannot score real data."""
    repository = repository or Path(__file__).resolve().parents[3]
    relative = path.resolve().relative_to(repository.resolve())
    stored = subprocess.run(
        ["git", "-C", str(repository), "show", "HEAD:" + relative.as_posix()],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    ).stdout
    raw = path.read_bytes()
    if stored != raw or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("protocol must match its committed SHA-256")
    protocol = json.loads(raw)
    if protocol["schema"] != "blend-replay-protocol/1":
        raise ValueError("unsupported scoring protocol")
    expected = {
        "pillar": "TRUTH",
        "target": "home_win",
        "cohorts": ["league", "horizon"],
        "train_start": "2026-09-01T00:00:00+00:00",
        "soccer_train_start": "2026-09-16T00:00:00+00:00",
        "train_end_exclusive": "2026-10-16T00:00:00+00:00",
        "held_out_weeks": 4,
        "primary_metric": "log_loss",
        "secondary_metrics": ["brier", "ece", "gap"],
        "ece_basis": "calibration_scoring._stats",
        "log_loss_clip": 1e-15,
        "bootstrap_replicates": 1000,
        "bootstrap_seed": 12108,
        "cluster": "series_doubleheader",
        "minimum_heldout_forecasts": 400,
        "maximum_cohort_ece_increase_pp": 0.5,
        "pooled_horizon_ece_must_not_rise": True,
        "improvement_interval_must_exclude_zero": True,
        "speed_gate_required": True,
        "reconstruction_agreement_minimum": 0.95,
        "database_statement_timeout_seconds": 10,
        "nightly_database_statement_seconds": 1800,
        "paid_model_budget_usd": 0,
        "activation": "NONE",
        "tuner_heldout_access": "cohort_counts_only",
        "score_policy": "first_run_counts_each_score_receipted",
    }
    if any(protocol.get(key) != value for key, value in expected.items()):
        raise ValueError("protocol differs from the adopted gates")
    if set(protocol) != set(expected) | {
        "schema",
        "recording_start",
        "candidate_sha256",
    }:
        raise ValueError("protocol has missing or undeclared fields")
    return protocol


def implementation_hashes() -> dict:
    from app.utils import aggregation, book_consensus, calibration_scoring
    from app.utils import probability_eligibility, publication_reader
    from scripts.evals import blend_replay_export

    modules = [
        aggregation,
        book_consensus,
        calibration_scoring,
        probability_eligibility,
        publication_reader,
        blend_replay_export,
    ]
    result = {
        m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
        for m in modules
    }
    result[__name__] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


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


def candidate_prediction(row: dict, weights: dict) -> tuple[float | None, str | None]:
    """Run the actual cascade with frozen candidate weights in this offline process."""
    from app.utils import aggregation

    if set(weights) != set(SOURCE_WEIGHTS):
        raise ValueError("candidate must retain the exact source feature set")
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v < 0
        for v in weights.values()
    ):
        raise ValueError("candidate weights must be finite nonnegative numbers")
    if not any(weights.values()):
        raise ValueError("candidate needs at least one positive weight")
    # The context restores the module even when a malformed row raises. There
    # are no writers, tasks, clients or background threads in this scorer.
    with patch.object(aggregation, "SOURCE_WEIGHTS", dict(weights)):
        return replay(row)


def paired_metrics(rows: list[dict]) -> dict:
    before = metrics([{**r, "probability": r["baseline"]} for r in rows])
    after = metrics([{**r, "probability": r["candidate"]} for r in rows])
    return {
        key: (
            round(after[key] - before[key], 2)
            if key in {"ece", "gap"}
            else after[key] - before[key]
        )
        for key in ("ece", "gap", "brier", "log_loss")
    }


def paired_interval(rows: list[dict], *, replicates: int, seed: int) -> dict:
    clusters = defaultdict(list)
    for row in rows:
        clusters[row["cluster_id"]].append(row)
    names = sorted(clusters)
    if len(names) < 2:
        return {"clusters": len(names), "bounds": None}
    samples = {key: [] for key in ("ece", "gap", "brier", "log_loss")}
    rng = random.Random(seed)
    for _ in range(replicates):
        draw = [r for _ in names for r in clusters[rng.choice(names)]]
        delta = paired_metrics(draw)
        for key in samples:
            samples[key].append(delta[key])
    return {
        "clusters": len(names),
        "replicates": replicates,
        "bounds": {
            key: [
                sorted(values)[math.floor((replicates - 1) * 0.025)],
                sorted(values)[math.ceil((replicates - 1) * 0.975)],
            ]
            for key, values in samples.items()
        },
    }


def score_candidate(
    export: dict, candidate: dict, *, replicates: int, seed: int
) -> dict:
    """Paired comparisons only; this function cannot train or activate weights."""
    weights = candidate["weights"]
    method = candidate["method_id"]
    if not isinstance(method, str) or not method:
        raise ValueError("candidate method id required")
    groups, horizon_rows = defaultdict(list), defaultdict(list)
    failures, withheld = 0, 0
    seen, cluster_splits = set(), {}
    for row in export["rows"]:
        try:
            identity = (int(row["event_id"]), row["horizon"], row["kind"])
            if identity in seen or row["kind"] not in {"served", "reconstruction"}:
                raise ValueError("duplicate or unknown candidate row")
            seen.add(identity)
            if row["outcome"] not in (0, 1) or isinstance(row["outcome"], bool):
                raise ValueError("unknown outcome")
            if not isinstance(row["cluster_id"], str) or not row["cluster_id"]:
                raise ValueError("missing cluster")
            previous = cluster_splits.setdefault(row["cluster_id"], row["split"])
            if previous != row["split"]:
                raise ValueError("cluster crosses splits")
            if row["split"] not in {"train", "tune", "held_out"}:
                continue
            if row["split"] == "held_out" and row["kind"] != "served":
                continue
            baseline, _ = replay(row)
            prediction, _ = candidate_prediction(row, weights)
            if baseline is None or prediction is None:
                withheld += 1
                continue
            observation = {
                "baseline": baseline,
                "candidate": prediction,
                "outcome": row["outcome"],
                "cluster_id": row["cluster_id"],
            }
            groups[(row["league"], row["horizon"], row["split"], row["kind"])].append(
                observation
            )
            if row["split"] == "held_out":
                horizon_rows[row["horizon"]].append(observation)
        except (KeyError, TypeError, ValueError, OverflowError):
            failures += 1
    cohorts, tripped = [], False
    for (league, horizon, split, kind), rows in sorted(groups.items()):
        delta = paired_metrics(rows)
        interval = paired_interval(rows, replicates=replicates, seed=seed)
        bounds = interval["bounds"]
        material = split == "held_out" and len(rows) >= 400
        breach = material and (
            delta["ece"] > 0.5 or (bounds is not None and bounds["log_loss"][0] > 0)
        )
        tripped |= breach
        cohorts.append(
            {
                "league": league,
                "horizon": horizon,
                "split": split,
                "kind": kind,
                "n": len(rows),
                "delta_candidate_minus_baseline": delta,
                "interval95": interval,
                "guardrail_breach": breach,
                "statistical_bar_met": material
                and not breach
                and bounds is not None
                and bounds["log_loss"][1] < 0,
            }
        )
    pooled = []
    for horizon, rows in sorted(horizon_rows.items()):
        delta = paired_metrics(rows)
        tripped |= delta["ece"] > 0
        pooled.append(
            {"horizon": horizon, "n": len(rows), "ece_delta_pp": delta["ece"]}
        )
    return {
        "method_id": method,
        "failures": failures,
        "withheld_pairs": withheld,
        "cohorts": cohorts,
        "heldout_pooled_horizons": pooled,
        "shared_guardrail": (
            "FAIL"
            if tripped or failures
            else (
                "UNKNOWN_WITHHELD_PAIRS"
                if withheld
                else "UNKNOWN_NO_HELDOUT" if not pooled else "NO_OBSERVED_BREACH"
            )
        ),
        "licence": "HELD",
        "activation": "NONE",
        "speed_gate": "UNKNOWN",
    }


def score_export(export: dict, *, replicates: int = 1000, seed: int = 12108) -> dict:
    if export["schema"] != SCHEMA:
        raise ValueError("unsupported replay schema")
    if replicates < 100:
        raise ValueError("at least 100 bootstrap replicates required")
    groups: dict[tuple, list] = defaultdict(list)
    overlapping: dict[tuple, dict] = defaultdict(dict)
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
            if (
                time_split(
                    instant(row["start"]),
                    instant(export["recording_start"]),
                    row["league"],
                )
                != split
            ):
                raise ValueError("row does not match the frozen time split")
            if split not in {"train", "tune", "held_out"}:
                continue
            if row["kind"] not in {"served", "reconstruction"}:
                raise ValueError("unknown_record_kind")
            y = row["outcome"]
            if y not in (0, 1) or isinstance(y, bool):
                raise ValueError("unknown_outcome")
            p, tier = replay(row)
            pair = overlapping[(row["event_id"], row["horizon"])]
            if row["kind"] == "served":
                compared += 1
                mismatches += (p, tier) != (row["blend_probability"], row["blend_tier"])
                pair["served"] = (
                    row["blend_probability"],
                    row["blend_tier"],
                    instant(row["recorded_at"]),
                )
            else:
                pair["reconstruction"] = (p, tier, instant(row["reconstructed_at"]))
                if split == "held_out":
                    # Fidelity comparison only: never substitute this for a
                    # prospective recorded forecast in a held-out grade.
                    continue
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
    agreements = pairs = nullable = unpaired = 0
    for pair in overlapping.values():
        if set(pair) != {"served", "reconstruction"}:
            unpaired += 1
            continue
        served, reconstructed = pair["served"], pair["reconstruction"]
        if served[2] != reconstructed[2]:
            unpaired += 1
            continue
        if served[0] is None:
            nullable += 1
            continue
        pairs += 1
        agreements += served[:2] == reconstructed[:2]
    agreement = {
        "k": agreements,
        "n": pairs,
        "nullable_pairs": nullable,
        "unpaired": unpaired,
        "required_share": 0.95,
        "result": (
            "UNKNOWN" if not pairs else "PASS" if agreements / pairs >= 0.95 else "FAIL"
        ),
    }
    coverage = defaultdict(
        lambda: {"expected": 0, "recorded": 0, "recorded_probability": 0}
    )
    for row in export.get("coverage", []):
        try:
            key = (row["league"], row["horizon"], row["split"])
            coverage[key]["expected"] += 1
            coverage[key]["recorded"] += int(row["recorded"])
            coverage[key]["recorded_probability"] += int(row["recorded_probability"])
        except (KeyError, TypeError, ValueError):
            failures["unreadable_coverage"] += 1
    failed = sum(failures.values()) or mismatches or agreement["result"] == "FAIL"
    return {
        "result": (
            "FAIL"
            if failed
            else (
                "UNKNOWN"
                if not pairs or not compared or not cohorts
                else "BASELINE_REPLAY_ONLY"
            )
        ),
        "activation": "NONE",
        "method": BLEND_METHOD,
        "failures": dict(failures),
        "input_rows": len(export["rows"]),
        "null_probability_rows": null_rows,
        "recorded_reproduction": {"n": compared, "mismatches": mismatches},
        "reconstruction_agreement": agreement,
        "coverage": [
            {"league": league, "horizon": horizon, "split": split, **counts}
            for (league, horizon, split), counts in sorted(coverage.items())
        ],
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
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != args.sha256:
        parser.error("input SHA-256 does not match the frozen export")
    protocol = committed_protocol(args.protocol, args.protocol_sha256)
    export = json.loads(raw)
    if protocol["recording_start"] is None or instant(
        protocol["recording_start"]
    ) != instant(export["recording_start"]):
        parser.error("commit the actual recording switch time before scoring")
    candidate, candidate_sha = None, None
    if args.candidate:
        candidate_raw = args.candidate.read_bytes()
        candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
        if candidate_sha != protocol["candidate_sha256"]:
            parser.error("candidate does not match the preregistered SHA-256")
        candidate = json.loads(candidate_raw)
    elif protocol["candidate_sha256"] is not None:
        parser.error("registered candidate must accompany this score")
    # Reserve the immutable receipt before scoring. A failed guard leaves its
    # own failed report; no subsequent command can overwrite that attempt.
    with args.output.open("x") as output:
        report = score_export(export)
        report["baseline_result"] = report["result"]
        if candidate is not None and report["result"] == "BASELINE_REPLAY_ONLY":
            try:
                report["candidate"] = score_candidate(
                    export, candidate, replicates=1000, seed=12108
                )
                report["candidate_verdict"] = "HELD"
                report["result"] = (
                    "FAIL"
                    if report["candidate"]["shared_guardrail"] == "FAIL"
                    else "CANDIDATE_EVALUATED_LICENCE_HELD"
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                report["candidate_verdict"] = "INVALID_CONFIGURATION"
                report["result"] = "FAIL"
        report = {
            "input_sha256": actual,
            "protocol_sha256": args.protocol_sha256,
            "candidate_sha256": candidate_sha,
            "implementation_sha256": implementation_hashes(),
            **report,
        }
        output.write(json.dumps(report, allow_nan=False, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "receipt": str(args.output),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "result": report["result"],
                "activation": "NONE",
            }
        )
    )
    return (
        1 if report["result"] == "FAIL" else 2 if report["result"] == "UNKNOWN" else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
