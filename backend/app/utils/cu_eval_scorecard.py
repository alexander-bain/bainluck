"""Content Understanding (CU) evaluation scorecard (#13901).

Pure scoring, normalization, slice breakdown, and formatting helpers for comparing
a writer run against a human-labeled answer key with zero model calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from app.utils.cu_event_facts import cu_event_facts
from app.utils.cu_frame import NO_SUBJECT_MARKER, UNRESOLVED_PREFIX
from app.utils.cu_junk_flags import cu_junk_flags

SAID_NOT_KNOWN_TOKENS = frozenset({"unknown", "not_sure", "not sure", "idk", "unsure", "abstain"})
ASKED_STRUCTURE_FLAGS = frozenset({"ladder", "dated_bucket"})
_CANONICAL_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")


@dataclass(frozen=True)
class FieldSpec:
    """Definition of one scored Content Understanding field."""

    key: str
    label: str
    default_decider: str  # "code" | "model" | "code_and_model"
    kind: str  # "str" | "date" | "int" | "flags" | "frame" | "subject" | "entities"
    in_pilot_core: bool = False
    tolerance: int = 0


CU_SCORECARD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("topic", "Topic", "model", "str", in_pilot_core=True),
    FieldSpec("subtopic", "Specific area", "model", "str"),
    FieldSpec("geography", "Region", "code_and_model", "str", in_pilot_core=True),
    FieldSpec("temporal_class", "How time works", "model", "str", in_pilot_core=True),
    FieldSpec("event_date", "Day of the event", "code_and_model", "date"),
    FieldSpec("recurrence", "How often it repeats", "model", "str"),
    FieldSpec("stakes", "Real-world stakes", "code_and_model", "int", in_pilot_core=True, tolerance=1),
    FieldSpec("breadth", "How wide the audience is", "code_and_model", "int", in_pilot_core=True, tolerance=1),
    FieldSpec("oddity", "How unusual it is", "model", "int", in_pilot_core=True),
    FieldSpec("arc", "Kind of story", "model", "str"),
    FieldSpec("junk_flags", "Format warnings", "code_and_model", "flags"),
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


def _subject_tokens(name: str) -> tuple[str, ...]:
    cleaned = re.sub(r"['’]", "", name.strip().lower())
    cleaned = re.sub(r"[^\w]+", " ", cleaned).replace("_", " ")
    return tuple(tok for tok in cleaned.split() if tok)


def _contains_token_subsequence(seq: tuple[str, ...], sub: tuple[str, ...]) -> bool:
    if not sub or len(sub) > len(seq):
        return False
    return any(seq[idx : idx + len(sub)] == sub for idx in range(len(seq) - len(sub) + 1))


def _subjects_match(labeled: str, predicted: str) -> bool:
    """True when either normalized subject is a contiguous whole-word match of the other."""
    ltok = _subject_tokens(labeled)
    ptok = _subject_tokens(predicted)
    if not ltok or not ptok:
        return False
    return _contains_token_subsequence(ptok, ltok) or _contains_token_subsequence(ltok, ptok)


def _extract_entity_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for entry in value:
        raw = entry.get("name") if isinstance(entry, dict) else entry
        text = str(raw or "").strip()
        if text:
            names.append(text)
    return names


def _evaluate_entities(expected: Any, predicted: Any) -> tuple[str, int]:
    """Compare named subjects ignoring type, using whole-word containment.

    Every labeled subject must be matched by at least one writer name for the
    row to score right. Extra writer names are counted separately, not as wrong.
    """
    if _is_said_not_known(predicted, "entities"):
        return ("said_not_known", 0)
    labeled = _extract_entity_names(expected)
    if predicted is None:
        return ("blank", 0)
    pred_names = _extract_entity_names(predicted)
    if not labeled:
        return ("right", 0) if not pred_names else ("wrong", len(pred_names))
    if not pred_names:
        return ("blank", 0)
    all_found = all(any(_subjects_match(lbl, pred) for pred in pred_names) for lbl in labeled)
    extra = sum(1 for pred in pred_names if not any(_subjects_match(lbl, pred) for lbl in labeled))
    return ("right" if all_found else "wrong", extra)


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
                text_val = str(raw_slot).strip().lower()
                canonical[slot] = _THOUSANDS_COMMA_RE.sub("", text_val)
            else:
                canonical[slot] = str(raw_slot).strip().lower()
        return tuple(sorted(canonical.items()))
    if kind == "entities":
        return tuple(sorted({_subject_tokens(name) for name in _extract_entity_names(value)}))
    return value


def _extract_expected_ints(expected: Any) -> list[int]:
    if isinstance(expected, (list, tuple)):
        out: list[int] = []
        for item in expected:
            norm = normalize_field_value(item, "int")
            if isinstance(norm, int):
                out.append(norm)
        return out
    norm = normalize_field_value(expected, "int")
    return [norm] if isinstance(norm, int) else []


def classify_field_prediction(expected: Any, predicted: Any, spec: FieldSpec) -> str:
    """Return 'right', 'wrong', 'blank', or 'said_not_known' for one field cell."""
    if spec.kind == "entities":
        return _evaluate_entities(expected, predicted)[0]

    if _is_said_not_known(predicted, spec.kind):
        # If truth explicitly expects unknown/not_sure (e.g. unpriced liveness),
        # returning that value is right rather than an evasion.
        norm_expected = normalize_field_value(expected, spec.kind)
        norm_pred = normalize_field_value(predicted, spec.kind)
        if norm_expected is not None and norm_expected == norm_pred:
            return "right"
        return "said_not_known"

    if spec.key == "junk_flags":
        norm_expected = normalize_field_value(expected, "flags")
        if predicted is None:
            return "blank"
        norm_pred = normalize_field_value(predicted, "flags")
        expected_set = set(norm_expected or ())
        scope = ASKED_STRUCTURE_FLAGS | expected_set
        filtered_pred = {flag for flag in (norm_pred or ()) if flag in scope}
        return "right" if filtered_pred == expected_set else "wrong"

    if spec.kind == "int":
        expected_ints = _extract_expected_ints(expected)
        if _is_blank_value(predicted, "int"):
            return "right" if expected is None else "blank"
        norm_pred = normalize_field_value(predicted, "int")
        if isinstance(norm_pred, int) and expected_ints:
            if any(abs(norm_pred - target) <= spec.tolerance for target in expected_ints):
                return "right"
            return "wrong"
        return "wrong"

    norm_expected = normalize_field_value(expected, spec.kind)
    norm_pred = normalize_field_value(predicted, spec.kind)
    if norm_expected == norm_pred:
        return "right"
    if _is_blank_value(predicted, spec.kind):
        return "blank"
    return "wrong"


def _parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _derived_event_facts(market_meta: dict[str, Any]) -> dict[str, Any]:
    event_facts = market_meta.get("event_facts")
    if isinstance(event_facts, dict):
        return event_facts
    title = market_meta.get("title") or market_meta.get("name") or ""
    if not isinstance(title, str) or not title.strip():
        return {}
    return cu_event_facts(
        title,
        linked_game_id=market_meta.get("linked_game_id")
        if market_meta.get("linked_game_id") is not None
        else market_meta.get("event_id"),
        linked_start=_parse_iso_dt(market_meta.get("linked_start")),
        start_source=market_meta.get("start_source"),
        linked_league=market_meta.get("linked_league"),
        home_team_league=market_meta.get("home_team_league"),
        away_team_league=market_meta.get("away_team_league"),
    )


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
        event_facts = _derived_event_facts(market_meta)
        if field_key in event_facts:
            return "code"
        if field_key == "junk_flags" and market_meta.get("outcome_names"):
            if cu_junk_flags(market_meta["outcome_names"], []):
                return "code"

    return "model" if spec.default_decider == "code_and_model" else spec.default_decider


def _infer_market_shape(row: dict[str, Any]) -> str:
    explicit = row.get("market_shape") or row.get("shape")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    outcome_names = row.get("outcome_names") or [
        o.get("name")
        for o in (row.get("outcomes") or [])
        if isinstance(o, dict) and o.get("name")
    ]
    if outcome_names:
        # Slicing comes strictly from market inputs; never use model-predicted flags.
        flags = set(cu_junk_flags(outcome_names, []))
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
    if row.get("sampling_bucket") == "readers_see" or row.get("draw_bucket") == "reader_weighted":
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
    acc: dict[str, Any] = {
        "field": spec.key,
        "label": spec.label,
        "default_decider": spec.default_decider,
        "code": _empty_counts(),
        "model": _empty_counts(),
        "total": _empty_counts(),
    }
    if spec.key == "entities":
        acc["extra_names"] = 0
    return acc


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
        row: dict[str, Any] = {
            "field": entry["field"],
            "label": entry["label"],
            "decided_by": primary,
            "code": entry["code"],
            "model": entry["model"],
            "total": entry["total"],
        }
        if "extra_names" in entry:
            row["extra_names"] = entry["extra_names"]
        rows.append(row)
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
            if spec.key == "entities":
                outcome, extra_names = _evaluate_entities(expected_val, predicted_val)
                field_accs["entities"]["extra_names"] += extra_names
            else:
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
    withheld_fields: list[str] | None = None,
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
        slice_inputs = (
            {**ans_row, **ans_row["market_meta"]}
            if isinstance(ans_row.get("market_meta"), dict)
            else ans_row
        )
        venue = str(slice_inputs.get("source") or slice_inputs.get("venue") or "unknown").strip().lower() or "unknown"
        category = str(
            slice_inputs.get("category")
            or slice_inputs.get("llm_sport_category")
            or _extract_answer_fields(ans_row).get("topic")
            or "unknown"
        ).strip().lower() or "unknown"
        shape = _infer_market_shape(slice_inputs)
        exposure = _infer_exposure(slice_inputs)

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

    payload: dict[str, Any] = {
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
    if withheld_fields:
        payload["withheld_fields"] = list(withheld_fields)
    return payload


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
        f"| markets={scorecard.get('market_count')} | missing_predictions={scorecard.get('missing_predictions', 0)}",
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
    entities_row = next((r for r in scorecard.get("fields", []) if r.get("field") == "entities"), None)
    if entities_row and entities_row.get("extra_names"):
        lines.append(f"Extra writer-only entity names (not counted wrong): {entities_row['extra_names']}")
    if scorecard.get("withheld_fields"):
        lines.append(f"Withheld taste fields (<80% agreement): {', '.join(scorecard['withheld_fields'])}")
    return "\n".join(lines)


def write_scorecard_json(scorecard: dict[str, Any], path: str) -> None:
    """Serialize a scorecard payload with stable formatting for git commits."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(scorecard, handle, indent=2, sort_keys=False)
        handle.write("\n")
