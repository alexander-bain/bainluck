"""Calibration metric robustness battery, dependency free."""

from __future__ import annotations

from typing import Any


def _gap(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return abs(sum(r["p"] for r in rows) / len(rows) - sum(r["y"] for r in rows) / len(rows))


def fixed_width_ece(rows: list[dict[str, Any]], bins: int) -> tuple[float, list[int]]:
    groups = [[] for _ in range(bins)]
    for row in rows:
        index = min(bins - 1, max(0, int(row["p"] * bins)))
        groups[index].append(row)
    n = len(rows) or 1
    return sum(len(group) / n * _gap(group) for group in groups), [len(group) for group in groups]


def equal_mass_ece(rows: list[dict[str, Any]], bins: int) -> tuple[float, list[int]]:
    ordered = sorted(rows, key=lambda row: (row["p"], str(row.get("id", ""))))
    groups = [[] for _ in range(min(bins, len(ordered)))]
    if not groups:
        return 0.0, []
    for index, row in enumerate(ordered):
        groups[min(len(groups) - 1, index * len(groups) // len(ordered))].append(row)
    n = len(rows) or 1
    return sum(len(group) / n * _gap(group) for group in groups), [len(group) for group in groups]


def brier(rows: list[dict[str, Any]]) -> float:
    return sum((row["p"] - row["y"]) ** 2 for row in rows) / len(rows) if rows else 0.0


def report(rows: list[dict[str, Any]], *, bin_counts: tuple[int, ...] = (5, 10, 20), sparse_floor: int = 30) -> dict[str, Any]:
    fixed: dict[str, float] = {}
    mass: dict[str, float] = {}
    sparse: dict[str, int] = {}
    for bins in bin_counts:
        fixed_value, fixed_n = fixed_width_ece(rows, bins)
        mass_value, mass_n = equal_mass_ece(rows, bins)
        fixed[str(bins)] = fixed_value
        mass[str(bins)] = mass_value
        sparse[str(bins)] = sum(0 < n < sparse_floor for n in fixed_n) + sum(0 < n < sparse_floor for n in mass_n)
    all_ece = list(fixed.values()) + list(mass.values())
    clusters = {str(row.get("question_id")) for row in rows if row.get("question_id") is not None}
    return {
        "rows": len(rows),
        "question_clusters": len(clusters),
        "rows_per_cluster": len(rows) / len(clusters) if clusters else None,
        "fixed_width_ece": fixed,
        "equal_mass_ece": mass,
        "brier": brier(rows),
        "ece_min": min(all_ece) if all_ece else None,
        "ece_max": max(all_ece) if all_ece else None,
        "sparse_bins": sparse,
    }


def compare(before: list[dict[str, Any]], after: list[dict[str, Any]], *, practical_floor: float = 0.005) -> dict[str, Any]:
    b = report(before)
    a = report(after)
    deltas = []
    for family in ("fixed_width_ece", "equal_mass_ece"):
        for bins in b[family]:
            deltas.append(a[family][bins] - b[family][bins])
    reasons: list[str] = []
    if b["question_clusters"] < 30 or a["question_clusters"] < 30:
        reasons.append("TOO_FEW_QUESTION_CLUSTERS")
    if any(delta < -practical_floor for delta in deltas) and any(delta >= 0 for delta in deltas):
        reasons.append("CONCLUSION_BIN_SENSITIVE")
    if not deltas or max((-delta for delta in deltas), default=0) < practical_floor:
        reasons.append("PRACTICAL_IMPROVEMENT_NOT_ESTABLISHED")
    if a["brier"] >= b["brier"]:
        reasons.append("BRIER_DID_NOT_IMPROVE")
    return {"verdict": "ROBUST_IMPROVEMENT" if not reasons else "REFUSE_CLAIM", "reasons": reasons, "before": b, "after": a, "ece_deltas": deltas}
