"""Cross-program gate for claims that a user-visible metric improved.

This does not calculate domain metrics. It decides whether evidence produced by
domain-specific evaluators is comparable and complete enough to support words
like "faster", "fresher", "better calibrated", or "more interesting".
"""

from __future__ import annotations

from typing import Any


COMMON_REQUIRED = {
    "claim_id",
    "domain",
    "surface",
    "generated_at",
    "deployed_sha",
    "method_version",
    "baseline",
    "candidate",
}


def _common(evidence: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = sorted(COMMON_REQUIRED - set(evidence))
    if missing:
        return ["COMMON_FIELDS_MISSING"]
    for key in ("claim_id", "surface", "generated_at", "deployed_sha", "method_version"):
        if not isinstance(evidence.get(key), str) or not evidence[key].strip():
            reasons.append(f"INVALID_{key.upper()}")
    sha = evidence.get("deployed_sha", "")
    if isinstance(sha, str) and len(sha) not in (8, 40):
        reasons.append("INVALID_DEPLOYED_SHA")
    if not isinstance(evidence.get("baseline"), dict) or not isinstance(evidence.get("candidate"), dict):
        reasons.append("COMPARISON_WRONG_SHAPE")
    if evidence.get("baseline_method_version", evidence.get("method_version")) != evidence.get("method_version"):
        reasons.append("METHOD_VERSION_CHANGED")
    if evidence.get("baseline_surface", evidence.get("surface")) != evidence.get("surface"):
        reasons.append("SURFACE_CHANGED")
    return reasons


def _calibration(e: dict[str, Any]) -> list[str]:
    b, c = e["baseline"], e["candidate"]
    reasons: list[str] = []
    if not b.get("build_complete") or not c.get("build_complete"):
        reasons.append("CALIBRATION_BUILD_INCOMPLETE")
    version_changed = b.get("population_version") != c.get("population_version")
    if version_changed and not c.get("population_bridge_valid"):
        reasons.append("CALIBRATION_POPULATION_UNBRIDGED")
    if not version_changed and b.get("population_count") != c.get("population_count"):
        delta = abs(c.get("population_count", 0) - b.get("population_count", 0))
        denom = max(1, b.get("population_count", 0))
        if delta / denom > 0.05:
            reasons.append("CALIBRATION_POPULATION_DRIFT")
    if set(b.get("categories", [])) != set(c.get("categories", [])):
        reasons.append("CALIBRATION_CATEGORY_SET_CHANGED")
    if not c.get("unknown_reported_separately", False):
        reasons.append("CALIBRATION_UNKNOWN_COLLAPSED")
    if c.get("metric") not in {"ece", "weighted_ece", "brier"}:
        reasons.append("CALIBRATION_METRIC_UNDECLARED")
    return reasons


def _latency(e: dict[str, Any]) -> list[str]:
    b, c = e["baseline"], e["candidate"]
    reasons: list[str] = []
    for side, sample in (("BASELINE", b), ("CANDIDATE", c)):
        n = sample.get("attempts", 0)
        if not isinstance(n, int) or n < 20:
            reasons.append(f"LATENCY_{side}_SAMPLE_TOO_SMALL")
        if sample.get("successes", 0) + sample.get("failures", 0) != n:
            reasons.append(f"LATENCY_{side}_ACCOUNTING_INCOMPLETE")
        if sample.get("failures", 0) and not sample.get("failures_in_percentile", False):
            reasons.append(f"LATENCY_{side}_FAILURES_CENSORED")
        if sample.get("cache_state") not in {"cold", "warm", "mixed_stratified"}:
            reasons.append(f"LATENCY_{side}_CACHE_STATE_UNKNOWN")
    if b.get("cache_state") != c.get("cache_state"):
        reasons.append("LATENCY_CACHE_STATE_CHANGED")
    if b.get("request_shape") != c.get("request_shape"):
        reasons.append("LATENCY_REQUEST_SHAPE_CHANGED")
    if not e.get("paired_control"):
        reasons.append("LATENCY_PAIRED_CONTROL_MISSING")
    return reasons


def _staleness(e: dict[str, Any]) -> list[str]:
    b, c = e["baseline"], e["candidate"]
    reasons: list[str] = []
    for side, sample in (("BASELINE", b), ("CANDIDATE", c)):
        rendered = sample.get("rendered_items")
        audited = sample.get("audited_items")
        if not isinstance(rendered, int) or rendered <= 0:
            reasons.append(f"STALENESS_{side}_NO_RENDERED_DENOMINATOR")
        if audited != rendered:
            reasons.append(f"STALENESS_{side}_INVENTORY_NOT_RENDERED")
        if not sample.get("lifecycle_authority"):
            reasons.append(f"STALENESS_{side}_NO_LIFECYCLE_AUTHORITY")
        if not sample.get("viewport"):
            reasons.append(f"STALENESS_{side}_VIEWPORT_MISSING")
    if b.get("feed_mode") != c.get("feed_mode"):
        reasons.append("STALENESS_FEED_MODE_CHANGED")
    if b.get("limit") != c.get("limit"):
        reasons.append("STALENESS_LIMIT_CHANGED")
    return reasons


def _interestingness(e: dict[str, Any]) -> list[str]:
    b, c = e["baseline"], e["candidate"]
    reasons: list[str] = []
    if c.get("evaluation_split") != "holdout":
        reasons.append("INTERESTINGNESS_NO_HOLDOUT")
    if c.get("trained_row_ids_hash") == c.get("evaluated_row_ids_hash"):
        reasons.append("INTERESTINGNESS_TRAIN_EVAL_OVERLAP")
    if c.get("temporal_cutoff") is None:
        reasons.append("INTERESTINGNESS_TEMPORAL_CUTOFF_MISSING")
    for side, sample in (("BASELINE", b), ("CANDIDATE", c)):
        if sample.get("rows", 0) < 50:
            reasons.append(f"INTERESTINGNESS_{side}_SAMPLE_TOO_SMALL")
        positives = sample.get("positives", 0)
        rows = sample.get("rows", 0)
        if rows <= 0 or positives <= 0 or positives >= rows:
            reasons.append(f"INTERESTINGNESS_{side}_ONE_CLASS")
        if sample.get("label_policy_version") != c.get("label_policy_version"):
            reasons.append(f"INTERESTINGNESS_{side}_LABEL_POLICY_MISMATCH")
    if b.get("row_ids_hash") != c.get("row_ids_hash"):
        reasons.append("INTERESTINGNESS_EVALUATION_POPULATION_CHANGED")
    for metric in ("auc", "precision_at_20"):
        if metric not in b or metric not in c:
            reasons.append("INTERESTINGNESS_METRIC_MISSING")
            break
    return reasons


DOMAIN_GATES = {
    "calibration": _calibration,
    "latency": _latency,
    "staleness": _staleness,
    "interestingness": _interestingness,
}


def evaluate_claim(evidence: dict[str, Any]) -> dict[str, Any]:
    reasons = _common(evidence)
    domain = evidence.get("domain")
    if domain not in DOMAIN_GATES:
        reasons.append("DOMAIN_UNSUPPORTED")
    elif not {"COMMON_FIELDS_MISSING", "COMPARISON_WRONG_SHAPE"} & set(reasons):
        reasons.extend(DOMAIN_GATES[domain](evidence))
    reasons = sorted(set(reasons))
    return {
        "verdict": "ACCEPT_CLAIM" if not reasons else "REFUSE_CLAIM",
        "reasons": reasons,
        "claim_id": evidence.get("claim_id"),
        "domain": domain,
    }
