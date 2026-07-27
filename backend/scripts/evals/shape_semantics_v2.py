"""Offline market-semantics v2 classifier and stamped-row delta census.

This evaluator is deliberately independent from ``app.utils.market_shape``. It
does not mutate production data. JSON/JSONL inputs are safe for local use; the
session loader is a read-only seam for a later authorized ops run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

CLASSIFIER_VERSION = 2
YES_NO = {"yes", "no"}
DRAW_NAMES = {"draw", "tie"}
TOP_N_RE = re.compile(r"(?:top[_\s-]?(\d+)|make[_\s-]?cut|qualif|advance)", re.I)
WIN_RE = re.compile(r"(?:^|[_\s-])(win|winner|champion)(?:$|[_\s-])", re.I)
NUMBER_RE = re.compile(r"[-+]?\d+(?:[,.]\d+)?")
RANGE_RE = re.compile(r"\d[^\n]*(?:-|–|—|\bto\b)[^\n]*\d", re.I)
CUMULATIVE_RE = re.compile(
    r"(?:>=|<=|≥|≤|\bat least\b|\bat most\b|\bover\b|\bunder\b|"
    r"\babove\b|\bbelow\b|\bby\b|\bbefore\b|\bor more\b|\bor fewer\b)",
    re.I,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value).lower())


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def load_file(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    for key in ("markets", "rows", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError(f"No market array found in {source}")


async def load_from_session(session: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read stamped market inputs without updating any row (Postgres only)."""
    from sqlalchemy import text

    limit_sql = "LIMIT :limit" if limit else ""
    query = text(
        f"""
        WITH group_sizes AS (
            SELECT group_id, COUNT(*) AS group_size
            FROM futures_markets WHERE group_id IS NOT NULL GROUP BY group_id
        )
        SELECT fm.id, fm.source, fm.external_id, fm.name,
               fm.market_type AS old_shape, fm.category,
               fm.llm_sport_category, fm.llm_league,
               fm.event_id, fm.group_id, fm.group_type,
               COALESCE(gs.group_size, 1) AS group_size,
               fm.mutually_exclusive, fm.status, fm.market_metadata,
               COALESCE(jsonb_agg(jsonb_build_object(
                   'id', fo.id, 'name', fo.name, 'is_winner', fo.is_winner,
                   'resolution_source', fo.resolution_source,
                   'calibration_probability', fo.calibration_probability
               ) ORDER BY fo.id) FILTER (WHERE fo.id IS NOT NULL), '[]'::jsonb) AS outcomes
        FROM futures_markets fm
        LEFT JOIN group_sizes gs ON gs.group_id = fm.group_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY fm.id, gs.group_size
        ORDER BY fm.id
        {limit_sql}
        """
    )
    result = await session.execute(query, {"limit": limit} if limit else {})
    return [dict(row._mapping) for row in result.all()]


async def load_rows(source: str | Path | Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    if isinstance(source, (str, Path)):
        return load_file(source)
    if hasattr(source, "execute"):
        return await load_from_session(source, limit=limit)
    raise TypeError("source must be a JSON/JSONL path or SQLAlchemy session")


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("market_metadata") or row.get("metadata") or {}
    return value if isinstance(value, dict) else {}


def _outcomes(row: dict[str, Any]) -> list[dict[str, Any]]:
    values = row.get("outcomes") or []
    return [value for value in values if isinstance(value, dict)]


def _source_kind(row: dict[str, Any]) -> str:
    metadata = _metadata(row)
    return _norm(
        row.get("source_market_kind")
        or metadata.get("source_market_kind")
        or metadata.get("market_kind")
        or metadata.get("datagolf_market_type")
        or (_text(row.get("external_id")).rsplit(":", 1)[-1] if row.get("source") == "datagolf" else "")
    )


def _structured_expected_winners(row: dict[str, Any], source_kind: str) -> int | None:
    metadata = _metadata(row)
    explicit = _int(row.get("expected_winners"))
    if explicit is None:
        explicit = _int(metadata.get("expected_winners"))
    if explicit is not None:
        return explicit
    match = TOP_N_RE.search(source_kind)
    if match and match.group(1):
        return int(match.group(1))
    if WIN_RE.search(source_kind):
        return 1
    if row.get("mutually_exclusive") is True:
        return 1
    return None


def _input_payload(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(row)
    outcomes = _outcomes(row)
    return {
        "source": _norm(row.get("source")),
        "source_kind": _source_kind(row),
        "outcomes": sorted(_norm(outcome.get("name")) for outcome in outcomes),
        "mutually_exclusive": row.get("mutually_exclusive"),
        "expected_winners": row.get("expected_winners", metadata.get("expected_winners")),
        "event_id": row.get("event_id"),
        "group_id": _text(row.get("group_id")),
        "group_type": _norm(row.get("group_type")),
        "group_size": _int(row.get("group_size")) or 1,
        "conditional": bool(row.get("conditional", metadata.get("conditional", False))),
        "parent_condition_id": row.get("parent_condition_id", metadata.get("parent_condition_id")),
        "push_possible": row.get("push_possible", metadata.get("push_possible")),
        "container_semantics": row.get("container_semantics", metadata.get("container_semantics")),
    }


def input_fingerprint(row: dict[str, Any]) -> str:
    payload = json.dumps(_input_payload(row), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def classify(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(row)
    outcomes = _outcomes(row)
    names = [_norm(outcome.get("name")) for outcome in outcomes if _norm(outcome.get("name"))]
    name_set = set(names)
    source_kind = _source_kind(row)
    expected_winners = _structured_expected_winners(row, source_kind)
    mutually_exclusive = row.get("mutually_exclusive")
    conditional = bool(row.get("conditional", metadata.get("conditional", False)))
    parent_condition = row.get("parent_condition_id", metadata.get("parent_condition_id"))
    push_possible = row.get("push_possible", metadata.get("push_possible"))
    evidence: list[str] = []
    confidence = "low"

    if source_kind:
        evidence.append(f"source_kind:{source_kind}")
    if mutually_exclusive is not None:
        evidence.append(f"mutually_exclusive:{str(bool(mutually_exclusive)).lower()}")
    if expected_winners is not None:
        evidence.append(f"expected_winners:{expected_winners}")
    if conditional or parent_condition:
        evidence.append("conditional_parent")

    relation = "unknown"
    exhaustiveness: bool | None = None
    display_shape = "unshaped"

    if conditional or parent_condition:
        relation = "conditional"
        display_shape = "claim" if name_set <= YES_NO else "field"
        confidence = "high" if parent_condition else "medium"
    elif len(names) < 2:
        relation = "unknown"
        display_shape = "unshaped"
    elif name_set <= YES_NO:
        relation = "complements"
        exhaustiveness = True
        expected_winners = 1
        display_shape = "claim"
        confidence = "high"
        evidence.append("yes_no_pair")
    elif name_set == {"over", "under"} or name_set == {"above", "below"}:
        relation = "complements"
        exhaustiveness = True
        expected_winners = 1
        display_shape = "quantity"
        confidence = "high"
        push_possible = True if push_possible is None else push_possible
        evidence.append("two_sided_threshold")
    else:
        range_count = sum(bool(RANGE_RE.search(name)) for name in names)
        cumulative_count = sum(bool(CUMULATIVE_RE.search(name) and NUMBER_RE.search(name)) for name in names)
        numeric_count = sum(bool(NUMBER_RE.search(name)) for name in names)
        has_draw = bool(name_set & DRAW_NAMES)
        top_n = TOP_N_RE.search(source_kind)

        if top_n or (expected_winners is not None and expected_winners > 1):
            relation = "independent_participation"
            exhaustiveness = False
            display_shape = "field"
            confidence = "high" if source_kind or row.get("expected_winners") is not None else "medium"
            evidence.append("multi_winner_contract")
        elif range_count >= 2 and range_count * 2 >= len(names):
            relation = "exclusive_ranges"
            exhaustiveness = bool(mutually_exclusive) if mutually_exclusive is not None else None
            display_shape = "quantity"
            confidence = "medium" if mutually_exclusive is None else "high"
            evidence.append("range_outcomes")
        elif cumulative_count >= 2 and cumulative_count * 2 >= len(names):
            relation = "cumulative_thresholds"
            exhaustiveness = False
            display_shape = "quantity"
            confidence = "medium"
            evidence.append("cumulative_threshold_outcomes")
        elif len(names) == 2 or has_draw:
            relation = "competitors"
            exhaustiveness = bool(mutually_exclusive) if mutually_exclusive is not None else None
            expected_winners = expected_winners or (1 if mutually_exclusive else None)
            display_shape = "duel" if len(names) == 2 else "field"
            confidence = "high" if mutually_exclusive is not None else "medium"
            evidence.append("named_competitors")
            if has_draw:
                evidence.append("draw_capable")
        elif expected_winners == 1 and mutually_exclusive is True:
            relation = "competitors"
            exhaustiveness = True
            display_shape = "field"
            confidence = "high"
            evidence.append("exactly_one_structured")
        elif numeric_count >= 2 and numeric_count * 2 >= len(names):
            relation = "unknown"
            display_shape = "quantity"
            confidence = "low"
            evidence.append("numeric_but_relation_unknown")
        else:
            relation = "unknown"
            display_shape = "field"
            confidence = "low"
            evidence.append("multi_named_relation_unknown")

    if relation == "competitors" and expected_winners == 1 and mutually_exclusive is True:
        exhaustiveness = True

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "input_fingerprint": input_fingerprint(row),
        "display_shape": display_shape,
        "outcome_relation": relation,
        "exhaustive": exhaustiveness,
        "expected_winners": expected_winners,
        "push_void_capable": bool(push_possible),
        "confidence": confidence,
        "evidence": sorted(set(evidence)),
    }


def risk_flags(row: dict[str, Any], result: dict[str, Any]) -> list[str]:
    outcomes = _outcomes(row)
    names = {_norm(outcome.get("name")) for outcome in outcomes if _norm(outcome.get("name"))}
    winners = sum(outcome.get("is_winner") is True for outcome in outcomes)
    status = _norm(row.get("status"))
    flags: list[str] = []
    if row.get("event_id") is not None and names <= YES_NO and names:
        flags.append("linked_yes_no")
    if result["outcome_relation"] == "independent_participation" and row.get("old_shape", row.get("market_type")) == "field":
        flags.append("top_n_as_field")
    expected = result.get("expected_winners")
    if status == "resolved" and expected and expected > 1 and winners < expected:
        flags.append("incomplete_multi_winner_grading")
    if result["outcome_relation"] == "conditional":
        flags.append("conditional")
    if "draw_capable" in result["evidence"]:
        flags.append("draw_capable")
    if result["outcome_relation"] == "cumulative_thresholds":
        flags.append("cumulative_ladder")
    if result["outcome_relation"] == "exclusive_ranges":
        flags.append("exclusive_range")
    stored_fingerprint = row.get("stored_input_fingerprint") or _metadata(row).get("shape_input_fingerprint")
    if stored_fingerprint and stored_fingerprint != result["input_fingerprint"]:
        flags.append("input_fingerprint_changed")
    if result["outcome_relation"] == "unknown":
        flags.append("unknown_semantics")
    return sorted(flags)


def _bucket(counter: Counter, key: str) -> dict[str, int]:
    return dict(sorted((str(name), count) for name, count in counter.items() if name.startswith(key)))


def canonical_population_crosswalk(
    classified: list[dict[str, Any]], canonical_outcome_ids: set[str] | None = None
) -> dict[str, Any]:
    """Optional Queue #259 seam; no population inference occurs when IDs are absent."""
    if canonical_outcome_ids is None:
        return {"status": "not_provided", "markets": 0, "outcomes": 0, "by_risk": {}}
    market_ids: set[str] = set()
    outcome_count = 0
    risks: Counter = Counter()
    for item in classified:
        included = {
            str(outcome.get("id"))
            for outcome in item["input"].get("outcomes", [])
            if str(outcome.get("id")) in canonical_outcome_ids
        }
        if not included:
            continue
        market_ids.add(str(item["input"].get("id")))
        outcome_count += len(included)
        for flag in item["risk_flags"]:
            risks[flag] += 1
    return {
        "status": "provided",
        "markets": len(market_ids),
        "outcomes": outcome_count,
        "by_risk": dict(sorted(risks.items())),
    }


def census(rows: Iterable[dict[str, Any]], canonical_outcome_ids: set[str] | None = None) -> dict[str, Any]:
    classified: list[dict[str, Any]] = []
    transitions: Counter = Counter()
    semantics: Counter = Counter()
    dimensions: Counter = Counter()
    risks: Counter = Counter()
    calibration_risks: Counter = Counter()

    for row in rows:
        result = classify(row)
        flags = risk_flags(row, result)
        old_shape = _text(row.get("old_shape", row.get("market_type"))) or "null"
        transitions[f"{old_shape}->{result['display_shape']}"] += 1
        semantics[result["outcome_relation"]] += 1
        source = _text(row.get("source")) or "unknown"
        category = _text(row.get("llm_league") or row.get("llm_sport_category") or row.get("category")) or "unknown"
        group_type = _text(row.get("group_type")) or "none"
        dimensions[f"source:{source}"] += 1
        dimensions[f"old_shape:{old_shape}"] += 1
        dimensions[f"category:{category}"] += 1
        dimensions[f"group_type:{group_type}"] += 1
        eligible = bool(row.get("calibration_eligible", False))
        dimensions[f"calibration_eligible:{str(eligible).lower()}"] += 1
        for flag in flags:
            risks[flag] += 1
            if eligible:
                calibration_risks[flag] += 1
        classified.append({"input": row, "semantics_v2": result, "risk_flags": flags})

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "markets": len(classified),
        "transitions": dict(sorted(transitions.items())),
        "semantics": dict(sorted(semantics.items())),
        "dimensions": dict(sorted(dimensions.items())),
        "risk_flags": dict(sorted(risks.items())),
        "calibration_eligible_risk_flags": dict(sorted(calibration_risks.items())),
        "canonical_population_crosswalk": canonical_population_crosswalk(classified, canonical_outcome_ids),
        "rows": classified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON or JSONL market export")
    parser.add_argument("--canonical-outcome-ids", help="Optional newline/JSON array of Queue #259 final outcome IDs")
    parser.add_argument("--output", help="Write JSON report instead of stdout-only")
    args = parser.parse_args()
    canonical_ids = None
    if args.canonical_outcome_ids:
        raw = Path(args.canonical_outcome_ids).read_text(encoding="utf-8")
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            values = [line for line in raw.splitlines() if line.strip()]
        canonical_ids = {str(value) for value in values}
    report = census(load_file(args.input), canonical_ids)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
