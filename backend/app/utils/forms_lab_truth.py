"""Pre-draw truth checks for Forms Lab Batch 1 (#13551).

Every form runs these pure checks before drawing. Any failed check blocks the specialized
rendering and returns ``refused`` with an exact machine-readable reason so the UI falls back
to plain probability rows cleanly (never drawing a misleading chart or grid).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class TruthCheckResult:
    check_id: str
    passed: bool
    reason: str
    observed: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_date_token(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%b %d", "%B %d"):
        try:
            dt_obj = datetime.strptime(s, fmt)
            if dt_obj.year == 1900:
                return f"MM-{dt_obj.month:02d}-{dt_obj.day:02d}"
            return dt_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(20\d\d-\d\d-\d\d)", s)
    if m:
        return m.group(1)
    return re.sub(r"\s+", " ", s.lower())


def check_one_winner_adds_to_100(
    probs_pct: Sequence[float],
    *,
    field_label: str = "field",
    min_sum: float = 85.0,
    max_sum: float = 115.0,
) -> TruthCheckResult:
    """Reject a one-winner field whose percentages deviate outside [85%, 115%] (#11995)."""
    vals = [float(p) for p in probs_pct]
    total = round(sum(vals), 1)
    if not vals:
        return TruthCheckResult(
            check_id="one_winner_adds_to_100",
            passed=False,
            reason=f"{field_label} has no priced outcomes",
            observed={"field": field_label, "sum_pct": 0.0, "bounds": [min_sum, max_sum]},
        )
    passed = min_sum <= total <= max_sum
    reason = (
        "ok"
        if passed
        else f"{field_label} adds to {total:g}%, outside single-winner band ({min_sum:g}%–{max_sum:g}%)"
    )
    return TruthCheckResult(
        check_id="one_winner_adds_to_100",
        passed=passed,
        reason=reason,
        observed={"field": field_label, "sum_pct": total, "bounds": [min_sum, max_sum]},
    )


def check_ladder_monotonic(
    steps: Sequence[tuple[str, float] | Mapping[str, Any]],
    *,
    ladder_label: str = "ladder",
    tolerance_pp: float = 3.0,
) -> TruthCheckResult:
    """Verify cumulative 'by date X' ladder values do not drop by more than tolerance_pp."""
    ordered: list[tuple[str, float]] = []
    for item in steps:
        if isinstance(item, Mapping):
            ordered.append((str(item.get("label") or item.get("date") or ""), float(item.get("pct") or item.get("p") or 0.0)))
        else:
            ordered.append((str(item[0]), float(item[1])))

    violations: list[dict[str, Any]] = []
    high_label, high_pct = ("", -1.0)
    for label, pct in ordered:
        if high_pct >= 0.0 and pct + tolerance_pp < high_pct:
            violations.append(
                {"prev_label": high_label, "prev_pct": round(high_pct, 1), "label": label, "pct": round(pct, 1)}
            )
        if pct > high_pct:
            high_label, high_pct = label, pct

    passed = not violations
    reason = (
        "ok"
        if passed
        else f"{ladder_label} dips >{tolerance_pp:g}% at {violations[0]['label']} ({violations[0]['pct']}% after {violations[0]['prev_pct']}%)"
    )
    return TruthCheckResult(
        check_id="ladder_monotonic",
        passed=passed,
        reason=reason,
        observed={"ladder": ladder_label, "violations": violations},
    )


def check_one_date_per_family(
    target_dates: Sequence[str],
    *,
    family_label: str = "family",
) -> TruthCheckResult:
    """Ensure every race/column in a single family targets the same resolution date."""
    raw_clean = [str(d).strip() for d in target_dates if str(d).strip()]
    normalized = sorted({_normalize_date_token(d) for d in raw_clean})
    passed = len(normalized) == 1
    reason = (
        "ok"
        if passed
        else f"{family_label} mixes target dates ({', '.join(raw_clean)}) instead of sharing one deadline"
    )
    return TruthCheckResult(
        check_id="one_date_per_family",
        passed=passed,
        reason=reason,
        observed={"family": family_label, "dates": raw_clean, "distinct": normalized},
    )


def check_one_unit_per_axis(
    units: Sequence[str],
    *,
    axis_label: str = "axis",
) -> TruthCheckResult:
    """Ensure every series plotted on one axis uses the exact same physical/scale unit."""
    clean = [str(u).strip() for u in units if str(u).strip()]
    distinct = sorted({u.lower() for u in clean})
    passed = len(distinct) == 1
    reason = (
        "ok"
        if passed
        else f"{axis_label} mixes incompatible units ({', '.join(sorted(set(clean)))})"
    )
    return TruthCheckResult(
        check_id="one_unit_per_axis",
        passed=passed,
        reason=reason,
        observed={"axis": axis_label, "units": clean},
    )


def check_ties_handled(
    ranked_items: Sequence[tuple[str, float] | Mapping[str, Any]],
    *,
    context_label: str = "field",
    tie_rule: Optional[str] = None,
    cut_index: Optional[int] = None,
    cut_tie_rule: Optional[str] = None,
) -> TruthCheckResult:
    """Require an explicit tie disclosure whenever rank 1 ties or cut boundary teams tie."""
    items: list[tuple[str, float]] = []
    for it in ranked_items:
        if isinstance(it, Mapping):
            items.append((str(it.get("name") or it.get("label") or ""), float(it.get("pct") or it.get("p") or 0.0)))
        else:
            items.append((str(it[0]), float(it[1])))

    sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
    rank1_tie = False
    if len(sorted_items) >= 2 and abs(sorted_items[0][1] - sorted_items[1][1]) <= 0.15:
        rank1_tie = True

    cut_tie = False
    if cut_index and 1 <= cut_index < len(sorted_items):
        if abs(sorted_items[cut_index - 1][1] - sorted_items[cut_index][1]) <= 0.15:
            cut_tie = True

    if rank1_tie and not (tie_rule and tie_rule.strip()):
        return TruthCheckResult(
            check_id="ties_handled",
            passed=False,
            reason=f"{context_label} has a rank-1 tie ({sorted_items[0][0]} / {sorted_items[1][0]} at {sorted_items[0][1]:g}%) with no tie rule",
            observed={"context": context_label, "rank1_tie": True, "cut_tie": cut_tie},
        )
    if cut_tie and not (cut_tie_rule and cut_tie_rule.strip()):
        return TruthCheckResult(
            check_id="ties_handled",
            passed=False,
            reason=f"{context_label} ties across cut line #{cut_index} ({sorted_items[cut_index - 1][0]} / {sorted_items[cut_index][0]}) with no boundary tie rule",
            observed={"context": context_label, "rank1_tie": rank1_tie, "cut_tie": True},
        )
    return TruthCheckResult(
        check_id="ties_handled",
        passed=True,
        reason="ok",
        observed={
            "context": context_label,
            "rank1_tie": rank1_tie,
            "tie_rule": tie_rule,
            "cut_tie": cut_tie,
            "cut_tie_rule": cut_tie_rule,
        },
    )


def check_no_price_floor(
    probs_pct: Sequence[float],
    *,
    field_label: str = "field",
    floor_pct: float = 5.0,
    max_floor_fraction: float = 0.65,
) -> TruthCheckResult:
    """Reject a set whose entries are stacked on an uninformative <=5% price floor."""
    vals = [float(p) for p in probs_pct]
    if not vals:
        return TruthCheckResult(
            check_id="no_price_floor",
            passed=False,
            reason=f"{field_label} has no values",
            observed={"field": field_label, "floor_fraction": 1.0},
        )
    at_floor = sum(1 for v in vals if v <= floor_pct)
    frac = at_floor / len(vals)
    spread = max(vals) - min(vals)
    passed = not (max(vals) <= floor_pct or (frac >= max_floor_fraction and spread <= 3.0 and len(vals) >= 3))
    reason = (
        "ok"
        if passed
        else f"{field_label} is pinned to the <={floor_pct:g}% price floor ({at_floor}/{len(vals)} entries, spread {spread:g}%)"
    )
    return TruthCheckResult(
        check_id="no_price_floor",
        passed=passed,
        reason=reason,
        observed={"field": field_label, "at_floor": at_floor, "total": len(vals), "max_pct": max(vals)},
    )


def check_no_computed_number(
    *,
    has_computed_numbers: bool,
    allowed: bool = False,
    decision_ref: str = "decision 367",
) -> TruthCheckResult:
    """Enforce Decision 367: block computed per-day numbers on Calendar strip until Alex allows them."""
    passed = not has_computed_numbers or allowed
    reason = (
        "ok"
        if passed
        else f"computed per-day numbers refused until {decision_ref} is ruled"
    )
    return TruthCheckResult(
        check_id="no_computed_number",
        passed=passed,
        reason=reason,
        observed={
            "has_computed_numbers": has_computed_numbers,
            "allowed": allowed,
            "decision_ref": decision_ref,
        },
    )


def evaluate_truth_checks(
    checks: Sequence[TruthCheckResult],
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Aggregate TruthCheckResult objects into overall status, refusal reasons, and wire dicts."""
    reasons = [c.reason for c in checks if not c.passed]
    return (len(reasons) == 0, reasons, [c.to_dict() for c in checks])
