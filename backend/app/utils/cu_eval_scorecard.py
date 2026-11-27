"""Content Understanding (CU) evaluation scorecard (#13901).

Pure scoring, normalization, slice breakdown, and formatting helpers for comparing
a writer run against a human-labeled answer key with zero model calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.utils.cu_frame import NO_SUBJECT_MARKER, UNRESOLVED_PREFIX
from app.utils.cu_junk_flags import cu_junk_flags

SAID_NOT_KNOWN_TOKENS = frozenset({"unknown", "not_sure", "not sure", "idk", "unsure", "abstain"})
_CANONICAL_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class FieldSpec:
    """Definition of one scored Content Understanding field."""

    key: str
    label: str
    default_decider: str  # "code" | "model"
    kind: str  # "str" | "date" | "int" | "flags" | "frame" | "subject" | "entities"
    in_pilot_core: bool = False


CU_SCORECARD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("topic", "Topic", "model", "str", in_pilot_core=True),
    FieldSpec("subtopic", "Specific area", "model", "str"),
    FieldSpec("geography", "Region", "model", "str", in_pilot_core=True),
    FieldSpec("temporal_class", "How time works", "model", "str", in_pilot_core=True),
    FieldSpec("event_date", "Day of the event", "model", "date"),
    FieldSpec("recurrence", "How often it repeats", "model", "str"),
    FieldSpec("stakes", "Real-world stakes", "model", "int", in_pilot_core=True),
    FieldSpec("breadth", "How wide the audience is", "model", "int", in_pilot_core=True),
    FieldSpec("oddity", "How unusual it is", "model", "int", in_pilot_core=True),
    FieldSpec("arc", "Kind of story", "model", "str"),
    FieldSpec("junk_flags", "Format warnings", "model", "flags"),
    FieldSpec("liveness", "Trading activity", "code", "str"),
    FieldSpec("subject_ref", "Main subject link", "code", "subject"),
    FieldSpec("frame", "Number and comparison", "model", "frame"),
    FieldSpec("series_key", "Recurring series", "model", "str"),
    FieldSpec("story_key", "Story group", "model", "str"),
    FieldSpec("entities", "Named subjects", "model", "entities"),
)

FIELD_SPEC_BY_KEY: dict[str, FieldSpec] = {spec.key: spec for spec in CU_SCORECARD_FIELDS}
SUPPORTED_SLICES: tuple[str, ...] = ("by_venue", "by_category", "by_market_shape", "by_exposure")


def _empty_counts() -> dict[str, int]:
    return {
        "right": 0,
        "wrong": 0,
        "blank": 0,
        "said_not_known": 0,
        "total": 0,
    }


def _record_outcome(counts: dict[str, int], outcome: str) -> None:
    counts[outcome] += 1
    counts["total"] += 1


def _is_blank_value(value: Any, kind: str) -> bool:
    if value is None:
        return True
    if kind in {"flags", "entities"}:
        return not isinstance(value, list) or len(value) == 0
    if kind == "frame":
        return not isinstance(value, dict) or len(value) == 0
    if isinstance(value, str):
        token = value.strip()
        if kind == "subject" and token.lower() == NO_SUBJECT_MARKER.lower():
            return True
        return token == ""
    return False


def _is_said_not_known(value: Any, kind: str) -> bool:
    if isinstance(value, str):
        token = value.strip().lower()
        if token in SAID_NOT_KNOWN_TOKENS:
            return True
        if kind == "subject" and token != NO_SUBJECT_MARKER.lower() and (
            token.startswith(UNRESOLVED_PREFIX) or token == "unresolved"
        ):
            return True
    if kind == "frame" and isinstance(value, dict):
        measure = value.get("measure")
        if isinstance(measure, str) and measure.strip().lower() in SAID_NOT_KNOWN_TOKENS:
            return True
    return False


def normalize_field_value(value: Any, kind: str) -> Any:
    """Normalize a predicted or ground-truth field value for exact comparison."""
    if _is_blank_value(value, kind):
        return None
    if kind == "str":
        return str(value).strip().lower()
    if kind == "date":
        text = str(value).strip()
        return text[:10] if _CANONICAL_ISO_DATE.match(text[:10]) else text.lower()
    if kind == "int":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(round(value))
        try:
            return int(str(value).strip())
        except ValueError:
            return str(value).strip().lower()
    if kind == "subject":
        return str(value).strip().lower()
    if kind == "flags":
        return tuple(sorted({str(v).strip().lower() for v in value if str(v).strip()}))
    if kind == "frame":
        if not isinstance(value, dict):
            return None
        canonical = {}
        for slot in ("measure", "comparator", "value", "unit", "horizon_kind", "window_date"):
            raw_slot = value.get(slot)
            if raw_slot is None or (isinstance(raw_slot, str) and raw_slot.strip() == ""):
                canonical[slot] = None
            elif slot == "value":
                canonical[slot] = str(raw_slot).strip().lower()
            else:
                canonical[slot] = str(raw_slot).strip().lower()
        return tuple(sorted(canonical.items()))
    if kind == "entities":
        items = []
        for entry in value:
            if isinstance(entry, dict):
                name = str(entry.get("name") or "").strip().lower()
                etype = str(entry.get("type") or "").strip().lower()
            else:
                name = str(entry or "").strip().lower()
                etype = ""
            if name:
                items.append((name, etype))
        return tuple(sorted(set(items)))
    return value


def classify_field_prediction(expected: Any, predicted: Any, spec: FieldSpec) -> str:
    """Return 'right', 'wrong', 'blank', or 'said_not_known' for one field cell."""
    if _is_said_not_known(predicted, spec.kind):
        # If truth explicitly expects unknown/not_sure (e.g. unpriced liveness),
        # returning that value is right rather than an evasion.
        norm_expected = normalize_field_value(expected, spec.kind)
        norm_pred = normalize_field_value(predicted, spec.kind)
        if norm_expected is not None and norm_expected == norm_pred:
            return "right"
        return "said_not_known"

    norm_expected = normalize_field_value(expected, spec.kind)
    norm_pred = normalize_field_value(predicted, spec.kind)
    if norm_expected == norm_pred:
        return "right"
    if _is_blank_value(predicted, spec.kind):
        return "blank"
    return "wrong"


def infer_field_decider(
    field_key: str,
    prediction_row: dict[str, Any],
    market_meta: dict[str, Any] | None = None,
) -> str:
    """Resolve whether code or the model decided `field_key` on one market."""
    explicit = prediction_row.get("field_deciders") or {}
    if isinstance(explicit, dict):
        raw_decider = explicit.get(field_key)
        if raw_decider in {"code", "model"}:
            return raw_decider

    spec = FIELD_SPEC_BY_KEY[field_key]
    if spec.default_decider == "code":
        return "code"

    if market_meta:
        event_facts = market_meta.get("event_facts")
        if isinstance(event_facts, dict) and field_key in event_facts:
            return "code"
        if field_key == "junk_flags" and market_meta.get("outcome_names"):
            if cu_junk_flags(market_meta["outcome_names"], []):
                return "code"

    return spec.default_decider


def _infer_market_shape(row: dict[str, Any]) -> str:
    explicit = row.get("market_shape") or row.get("shape")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    outcome_names = row.get("outcome_names") or []
    if outcome_names:
        flags = set(cu_junk_flags(outcome_names, row.get("junk_flags")))
        if "ladder" in flags:
            return "ladder"
        if "dated_bucket" in flags:
            return "dated_bucket"
        if len(outcome_names) == 2:
            return "binary"
        return "multi_outcome"
    return "unknown"


def _infer_exposure(row: dict[str, Any]) -> str:
    explicit = row.get("exposure")
    if isinstance(explicit, str) and explicit.strip().lower() in {"readers_see", "rest"}:
        return explicit.strip().lower()
    if row.get("readers_see") or row.get("is_reader_visible"):
        return "readers_see"
    if row.get("sampling_bucket") == "readers_see":
        return "readers_see"
    return "rest"


def _index_rows_by_market_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        mid = row.get("market_id") if row.get("market_id") is not None else row.get("id")
        if mid is None:
            continue
        indexed[str(mid)] = row
    return indexed


def _extract_profile(prediction_row: dict[str, Any]) -> dict[str, Any]:
    profile = prediction_row.get("profile")
    if isinstance(profile, dict):
        return profile
    discover_llm = prediction_row.get("discover_llm")
    if isinstance(discover_llm, dict):
        return discover_llm
    return prediction_row


def _extract_answer_fields(answer_row: dict[str, Any]) -> dict[str, Any]:
    for key in ("answers", "labels", "expected", "fields"):
        candidate = answer_row.get(key)
        if isinstance(candidate, dict):
            return candidate
    return answer_row


def _init_field_accumulator(spec: FieldSpec) -> dict[str, Any]:
    return {
        "field": spec.key,
        "label": spec.label,
        "default_decider": spec.default_decider,
        "code": _empty_counts(),
        "model": _empty_counts(),
        "total": _empty_counts(),
    }


def _finalize_field_rows(accumulators: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for spec in CU_SCORECARD_FIELDS:
        entry = accumulators[spec.key]
        code_total = entry["code"]["total"]
        model_total = entry["model"]["total"]
        if code_total and model_total:
            primary = "code_and_model"
        elif code_total:
            primary = "code"
        elif model_total:
            primary = "model"
        else:
            primary = spec.default_decider
        rows.append(
            {
                "field": entry["field"],
                "label": entry["label"],
                "decided_by": primary,
                "code": entry["code"],
                "model": entry["model"],
                "total": entry["total"],
            }
        )
    return rows


def _score_subset(
    market_ids: list[str],
    answers_by_id: dict[str, dict[str, Any]],
    preds_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    field_accs = {spec.key: _init_field_accumulator(spec) for spec in CU_SCORECARD_FIELDS}
    decider_totals = {"code": _empty_counts(), "model": _empty_counts()}
    missing_predictions = 0

    for mid in market_ids:
        ans_row = answers_by_id[mid]
        pred_row = preds_by_id.get(mid)
        if pred_row is None:
            missing_predictions += 1
            pred_row = {}
        pred_profile = _extract_profile(pred_row)
        ans_fields = _extract_answer_fields(ans_row)
        market_meta = ans_row.get("market_meta") if isinstance(ans_row.get("market_meta"), dict) else ans_row

        for spec in CU_SCORECARD_FIELDS:
            if spec.key not in ans_fields:
                continue
            expected_val = ans_fields[spec.key]
            # Handle the common `temporal` vs `temporal_class` alias seamlessly.
            if spec.key == "temporal_class" and "temporal_class" not in pred_profile and "temporal" in pred_profile:
                predicted_val = pred_profile.get("temporal")
            else:
                predicted_val = pred_profile.get(spec.key)
            outcome = classify_field_prediction(expected_val, predicted_val, spec)
            decider = infer_field_decider(spec.key, pred_row, market_meta)

            _record_outcome(field_accs[spec.key][decider], outcome)
            _record_outcome(field_accs[spec.key]["total"], outcome)
            _record_outcome(decider_totals[decider], outcome)

    return {
        "market_count": len(market_ids),
        "missing_predictions": missing_predictions,
        "decider_totals": decider_totals,
        "fields": _finalize_field_rows(field_accs),
    }


def _normalize_cost(cost: dict[str, Any] | None, market_count: int) -> dict[str, Any]:
    if not cost:
        return {
            "total_usd": None,
            "per_market_usd": None,
            "api_calls": None,
            "input_tokens": None,
            "output_tokens": None,
        }
    total_usd = cost.get("total_usd") if cost.get("total_usd") is not None else cost.get("actual_usd")
    per_market = cost.get("per_market_usd")
    if per_market is None and isinstance(total_usd, (int, float)) and market_count > 0:
        per_market = round(float(total_usd) / market_count, 8)
    return {
        "total_usd": round(float(total_usd), 6) if isinstance(total_usd, (int, float)) else None,
        "per_market_usd": per_market,
        "api_calls": cost.get("api_calls"),
        "input_tokens": cost.get("input_tokens"),
        "output_tokens": cost.get("output_tokens"),
    }


def build_unlabeled_scorecard(
    *,
    as_of: str,
    writer_rev: int | None = None,
    model: str | None = None,
    cost: dict[str, Any] | None = None,
    dataset: str = "sealed",
    sealed_set_size: int | None = None,
) -> dict[str, Any]:
    """Build the initial checked-in payload before two-person labels exist."""
    return {
        "status": "not_measured_yet",
        "as_of": as_of,
        "dataset": dataset,
        "writer_rev": writer_rev,
        "model": model,
        "sealed_set_size": sealed_set_size,
        "cost": _normalize_cost(cost, 0),
        "market_count": 0,
        "decider_totals": {"code": _empty_counts(), "model": _empty_counts()},
        "fields": [
            {
                "field": spec.key,
                "label": spec.label,
                "decided_by": spec.default_decider,
                "code": _empty_counts(),
                "model": _empty_counts(),
                "total": _empty_counts(),
            }
            for spec in CU_SCORECARD_FIELDS
        ],
        "slices": {slice_name: {} for slice_name in SUPPORTED_SLICES},
    }


def score_cu_eval_run(
    answer_key_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    *,
    as_of: str,
    writer_rev: int | str | None = None,
    model: str | None = None,
    dataset: str = "sealed",
    cost: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Score a CU writer run against an answer key across fields and slices."""
    answers_by_id = _index_rows_by_market_id(answer_key_rows)
    preds_by_id = _index_rows_by_market_id(prediction_rows)
    market_ids = list(answers_by_id.keys())

    overall = _score_subset(market_ids, answers_by_id, preds_by_id)

    slice_buckets: dict[str, dict[str, list[str]]] = {
        "by_venue": {},
        "by_category": {},
        "by_market_shape": {},
        "by_exposure": {},
    }
    for mid in market_ids:
        ans_row = answers_by_id[mid]
        pred_row = preds_by_id.get(mid, {})
        venue = str(ans_row.get("source") or ans_row.get("venue") or "unknown").strip().lower() or "unknown"
        category = str(
            ans_row.get("category")
            or ans_row.get("llm_sport_category")
            or _extract_answer_fields(ans_row).get("topic")
            or "unknown"
        ).strip().lower() or "unknown"
        shape = _infer_market_shape({**ans_row, "junk_flags": _extract_profile(pred_row).get("junk_flags")})
        exposure = _infer_exposure(ans_row)

        slice_buckets["by_venue"].setdefault(venue, []).append(mid)
        slice_buckets["by_category"].setdefault(category, []).append(mid)
        slice_buckets["by_market_shape"].setdefault(shape, []).append(mid)
        slice_buckets["by_exposure"].setdefault(exposure, []).append(mid)

    slices_out: dict[str, dict[str, Any]] = {}
    for slice_name, groups in slice_buckets.items():
        slices_out[slice_name] = {
            group_key: _score_subset(group_ids, answers_by_id, preds_by_id)
            for group_key, group_ids in sorted(groups.items())
        }

    return {
        "status": "measured",
        "as_of": as_of,
        "run_id": run_id,
        "dataset": dataset,
        "writer_rev": writer_rev,
        "model": model,
        "cost": _normalize_cost(cost, len(market_ids)),
        **overall,
        "slices": slices_out,
    }


def _fmt_counts(counts: dict[str, int]) -> str:
    if counts["total"] == 0:
        return "-"
    return f"{counts['right']}/{counts['wrong']}/{counts['blank']}/{counts['said_not_known']}"


def format_scorecard_table(scorecard: dict[str, Any]) -> str:
    """Format a human-readable scorecard table with separate code/model columns."""
    if scorecard.get("status") == "not_measured_yet":
        return (
            f"CU Eval Scorecard: NOT MEASURED YET (as of {scorecard.get('as_of')})\n"
            f"Dataset: {scorecard.get('dataset')} | Writer rev: {scorecard.get('writer_rev') or '-'}"
        )

    lines = [
        f"CU Eval Scorecard ({scorecard.get('as_of')}) — {scorecard.get('dataset')} set "
        f"| rev={scorecard.get('writer_rev')} | model={scorecard.get('model')} "
        f"| markets={scorecard.get('market_count')}",
    ]
    cost = scorecard.get("cost") or {}
    if cost.get("total_usd") is not None:
        lines.append(
            f"Cost: ${cost['total_usd']:.4f} total "
            f"(${cost['per_market_usd']:.6f}/market)" if cost.get("per_market_usd") is not None else
            f"Cost: ${cost['total_usd']:.4f} total"
        )
    lines.append("")
    lines.append(
        f"{'Field':<24} {'By':<14} {'Code R/W/B/IDK':<18} {'Model R/W/B/IDK':<18} {'Total R/W/B/IDK'}"
    )
    lines.append("-" * 92)
    for row in scorecard.get("fields", []):
        lines.append(
            f"{row['field']:<24} {row['decided_by']:<14} "
            f"{_fmt_counts(row['code']):<18} {_fmt_counts(row['model']):<18} "
            f"{_fmt_counts(row['total'])}"
        )

    dt = scorecard.get("decider_totals") or {}
    lines.append("-" * 92)
    lines.append(
        f"{'ALL CODE DECISIONS':<39} {_fmt_counts(dt.get('code', _empty_counts()))}"
    )
    lines.append(
        f"{'ALL MODEL DECISIONS':<39} {'':<18} {_fmt_counts(dt.get('model', _empty_counts()))}"
    )
    return "\n".join(lines)


def write_scorecard_json(scorecard: dict[str, Any], path: str) -> None:
    """Serialize a scorecard payload with stable formatting for git commits."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(scorecard, handle, indent=2, sort_keys=False)
        handle.write("\n")
