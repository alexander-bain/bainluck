"""Pure scorer and payload builder for Blend vs Contributing Sources calibration (#356a).

Scores the recorded Bain Luck blend beside each contributing source on the
**exact same games** at pre-game horizons (Start, T-1h, T-6h, T-24h), with raw
un-smoothed 10-band calibration buckets and exact game counts.

Leaf contract: imports only stdlib plus ``aggregation``,
``calibration_scoring`` and ``publication_reader``. No database or Redis I/O.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from app.utils.aggregation import SOURCE_WEIGHTS, parse_source_entry
from app.utils.calibration_scoring import _stats
from app.utils.publication_reader import HORIZONS

SCHEMA = "blend-vs-sources/1"
REDIS_KEY = "bainluck:calibration:blend_vs_sources"
LAST_GOOD_KEY = "bainluck:calibration:blend_vs_sources:last_good"
TTL_S = 50 * 3600
LAST_GOOD_TTL_S = 30 * 86400
RECORDING_START_ISO = "2026-11-06T05:52:44+00:00"

FORECAST_SOURCES: tuple[str, ...] = tuple(
    sorted(k for k in SOURCE_WEIGHTS if k != "final_result")
)
HORIZON_ORDER: tuple[str, ...] = ("start", "t_minus_1h", "t_minus_6h", "t_minus_24h")
_LOG_LOSS_CLIP = 1e-15
_MAX_COMMON_SETS = 20
_MIN_COMMON_SET_GAMES_FOR_LARGEST = 10


def _valid_probability(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p) or not (0.0 <= p <= 1.0):
        return None
    return p


def extract_forecast_sources(raw_sources: Any) -> dict[str, float]:
    """Extract finite ``[0, 1]`` forecast probabilities keyed by canonical source."""
    if not isinstance(raw_sources, Mapping):
        return {}
    out: dict[str, float] = {}
    for source in FORECAST_SOURCES:
        if source not in raw_sources:
            continue
        value, _ = parse_source_entry(raw_sources[source])
        prob = _valid_probability(value)
        if prob is not None:
            out[source] = prob
    return out


def _wilson_ci(winners: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson 95% CI in percentage points ``[0.0, 100.0]``."""
    if n <= 0:
        return None, None
    p = winners / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    return round(max(0.0, center - half) * 100.0, 2), round(
        min(1.0, center + half) * 100.0, 2
    )


def raw_reliability_buckets(pairs: Sequence[tuple[float, int]]) -> list[dict[str, Any]]:
    """Build raw un-smoothed 10-band calibration buckets with exact bin counts."""
    bins: dict[int, dict[str, float | int]] = {}
    for p, y in pairs:
        idx = min(9, max(0, math.floor(p * 10.0)))
        cell = bins.setdefault(idx, {"n": 0, "winners": 0, "sum_prob": 0.0})
        cell["n"] = int(cell["n"]) + 1
        cell["winners"] = int(cell["winners"]) + y
        cell["sum_prob"] = float(cell["sum_prob"]) + p

    out: list[dict[str, Any]] = []
    for idx in sorted(bins):
        cell = bins[idx]
        n = int(cell["n"])
        winners = int(cell["winners"])
        sum_prob = float(cell["sum_prob"])
        avg_prob = sum_prob / n
        actual = winners / n
        ci_lower, ci_upper = _wilson_ci(winners, n)
        out.append(
            {
                "bucket_idx": idx,
                "bucket": f"{idx * 10}-{(idx + 1) * 10}%",
                "midpoint": idx * 10 + 5,
                "n": n,
                "winners": winners,
                "avg_prob": round(avg_prob, 4),
                "actual": round(actual, 4),
                "error": round((actual - avg_prob) * 100.0, 2),
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            }
        )
    return out


def score_pairs(pairs: Sequence[tuple[float, int]]) -> dict[str, Any]:
    """Score ``(probability, outcome)`` pairs with raw 10-band buckets and proper rules."""
    if not pairs:
        return {
            "n_games": 0,
            "ece": None,
            "gap": None,
            "brier": None,
            "log_loss": None,
            "buckets": [],
        }

    bins: dict[int, dict[str, float | int]] = {}
    brier_sum = 0.0
    log_loss_sum = 0.0
    for p, y in pairs:
        idx = min(9, max(0, math.floor(p * 10.0)))
        cell = bins.setdefault(idx, {"n": 0, "winners": 0, "sum_prob": 0.0})
        cell["n"] = int(cell["n"]) + 1
        cell["winners"] = int(cell["winners"]) + y
        cell["sum_prob"] = float(cell["sum_prob"]) + p
        brier_sum += (p - y) ** 2
        clipped = min(1.0 - _LOG_LOSS_CLIP, max(_LOG_LOSS_CLIP, p))
        log_loss_sum -= y * math.log(clipped) + (1 - y) * math.log1p(-clipped)

    stats = _stats(bins)
    n_games = len(pairs)
    return {
        "n_games": stats["n"],
        "ece": stats["ece"],
        "gap": stats["gap"],
        "brier": round(brier_sum / n_games, 4),
        "log_loss": round(log_loss_sum / n_games, 4),
        "buckets": raw_reliability_buckets(pairs),
    }


def _select_common_sets(
    common_groups: dict[tuple[str, ...], list[tuple[int, float, dict[str, float], int]]],
) -> list[dict[str, Any]]:
    ranked = sorted(
        common_groups.items(),
        key=lambda item: (-len(item[1]), -len(item[0]), item[0]),
    )
    selected_keys = [combo for combo, _ in ranked[:_MAX_COMMON_SETS]]

    material_combos = [
        (combo, rows)
        for combo, rows in common_groups.items()
        if len(rows) >= _MIN_COMMON_SET_GAMES_FOR_LARGEST
    ]
    if material_combos:
        largest_combo, _ = max(
            material_combos,
            key=lambda item: (len(item[0]), len(item[1]), tuple(item[0])),
        )
        if largest_combo not in selected_keys:
            if len(selected_keys) >= _MAX_COMMON_SETS:
                selected_keys[-1] = largest_combo
            else:
                selected_keys.append(largest_combo)

    selected_keys = sorted(
        set(selected_keys),
        key=lambda combo: (-len(common_groups[combo]), -len(combo), combo),
    )

    out: list[dict[str, Any]] = []
    for combo in selected_keys:
        rows = common_groups[combo]
        out.append(
            {
                "sources": list(combo),
                "n_games": len(rows),
                "distinct_events": len({r[0] for r in rows}),
                "blend": score_pairs([(r[1], r[3]) for r in rows]),
                "by_source": {
                    s: score_pairs([(r[2][s], r[3]) for r in rows]) for s in combo
                },
            }
        )
    return out


def build_blend_vs_sources_payload(
    observations: Iterable[Mapping[str, Any]],
    *,
    generated_at: str,
    recording_start: str = RECORDING_START_ISO,
    events_scanned: int = 0,
) -> dict[str, Any]:
    """Aggregate matched-game Blend vs Source scores across all grading horizons."""
    known_horizons = {h for h, _ in HORIZONS}
    assert set(HORIZON_ORDER) == known_horizons

    by_horizon_dedup: dict[str, dict[int, tuple[float, dict[str, float], int]]] = {
        h: {} for h in HORIZON_ORDER
    }
    for obs in observations:
        horizon = obs.get("horizon")
        if horizon not in by_horizon_dedup:
            continue
        raw_eid = obs.get("event_id")
        if isinstance(raw_eid, bool) or raw_eid is None:
            continue
        try:
            event_id = int(raw_eid)
        except (TypeError, ValueError):
            continue
        outcome = obs.get("outcome")
        if isinstance(outcome, bool) or outcome not in (0, 1):
            continue
        blend_p = _valid_probability(obs.get("blend_probability"))
        if blend_p is None:
            continue
        src_probs = extract_forecast_sources(obs.get("sources"))
        if not src_probs:
            continue
        by_horizon_dedup[horizon][event_id] = (blend_p, src_probs, int(outcome))

    horizons_payload: dict[str, dict[str, Any]] = {}
    for horizon in HORIZON_ORDER:
        dedup = by_horizon_dedup[horizon]
        per_source_groups: dict[str, list[tuple[int, float, float, int]]] = defaultdict(
            list
        )
        common_groups: dict[
            tuple[str, ...], list[tuple[int, float, dict[str, float], int]]
        ] = defaultdict(list)

        for event_id, (blend_p, src_probs, outcome) in sorted(dedup.items()):
            for source, src_p in src_probs.items():
                per_source_groups[source].append((event_id, blend_p, src_p, outcome))
            present = sorted(src_probs)
            for size in range(2, len(present) + 1):
                for combo in itertools.combinations(present, size):
                    common_groups[combo].append(
                        (
                            event_id,
                            blend_p,
                            {s: src_probs[s] for s in combo},
                            outcome,
                        )
                    )

        per_source_matched: list[dict[str, Any]] = []
        for source, rows in sorted(
            per_source_groups.items(), key=lambda item: (-len(item[1]), item[0])
        ):
            blend_scored = score_pairs([(r[1], r[3]) for r in rows])
            src_scored = score_pairs([(r[2], r[3]) for r in rows])
            per_source_matched.append(
                {
                    "source": source,
                    "n_games": len(rows),
                    "distinct_events": len({r[0] for r in rows}),
                    "blend": blend_scored,
                    "source_metrics": src_scored,
                    "delta_ece_pp": (
                        round(blend_scored["ece"] - src_scored["ece"], 2)
                        if blend_scored["ece"] is not None
                        and src_scored["ece"] is not None
                        else None
                    ),
                    "delta_brier": (
                        round(blend_scored["brier"] - src_scored["brier"], 4)
                        if blend_scored["brier"] is not None
                        and src_scored["brier"] is not None
                        else None
                    ),
                    "delta_log_loss": (
                        round(blend_scored["log_loss"] - src_scored["log_loss"], 4)
                        if blend_scored["log_loss"] is not None
                        and src_scored["log_loss"] is not None
                        else None
                    ),
                }
            )

        horizons_payload[horizon] = {
            "n_events": len(dedup),
            "per_source_matched": per_source_matched,
            "common_source_sets": _select_common_sets(common_groups),
        }

    return {
        "schema": SCHEMA,
        "status": "ready",
        "smoothing": "none",
        "generated_at": generated_at,
        "recording_start": recording_start,
        "events_scanned": int(events_scanned),
        "horizons": horizons_payload,
    }
