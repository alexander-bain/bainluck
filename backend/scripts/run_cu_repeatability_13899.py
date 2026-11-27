#!/usr/bin/env python3
"""Run the CU v2 writer twice over the frozen development set (#13899).

Reads only the frozen JSON development set, calls ``complete_chat_detailed("cu_v2", ...)``
twice per market under a hard ``JobBudget(<= $1.00)`` on the existing Redis spend ledger,
writes nothing to Postgres, and computes field-by-field run-to-run changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.enrich_markets import (  # noqa: E402
    _CU_V2_PROMPT,
    CU_V2_SCHEMA_VERSION,
    CU_WRITER_REV,
    _compute_liveness,
    _cu_prompt_outcome,
    _cu_series_key,
    _json_from_llm_response,
)
from app.utils.cu_event_facts import (  # noqa: E402
    cu_event_facts,
    cu_model_geography,
    cu_unlinked_event_date,
)
from app.utils.cu_frame import (  # noqa: E402
    MEASURES as CU_FRAME_MEASURES,
    clean_entity_mentions,
    sanitize_cu_frame,
)
from app.utils.cu_junk_flags import cu_junk_flags  # noqa: E402

DEFAULT_DEV_PATH = REPO_ROOT / "backend" / "data" / "evals" / "cu_dev_200_v1.json"
DEFAULT_OUT_PATH = REPO_ROOT / "handoffs" / "cu-repeatability-13899-2026-11-27.json"
MAX_TOTAL_USD = 1.00

COMPARED_FIELDS: tuple[str, ...] = (
    "topic",
    "subtopic",
    "entities",
    "geography",
    "story_key",
    "series_key",
    "temporal_class",
    "event_date",
    "recurrence",
    "stakes",
    "breadth",
    "oddity",
    "arc",
    "hook_facts",
    "junk_flags",
    "liveness",
    "frame",
    "frame_drop_reason",
    "confidence",
)

MODEL_DECIDED_FIELDS = frozenset({
    "topic",
    "subtopic",
    "entities",
    "story_key",
    "series_key",
    "temporal_class",
    "recurrence",
    "oddity",
    "arc",
    "hook_facts",
    "confidence",
})


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _item_event_facts(item: dict[str, Any]) -> dict[str, Any]:
    linked_game_id = (
        item.get("linked_game_id")
        if item.get("linked_game_id") is not None
        else item.get("event_id")
    )
    return cu_event_facts(
        item.get("title") or item.get("name") or "",
        linked_game_id=linked_game_id,
        linked_start=_parse_dt(item.get("linked_start")),
        start_source=item.get("start_source"),
        linked_league=item.get("linked_league"),
        home_team_league=item.get("home_team_league"),
        away_team_league=item.get("away_team_league"),
    )


def _ordered_outcomes(item: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes_raw = [o for o in (item.get("outcomes") or []) if isinstance(o, dict)]
    if any(o.get("rank") is not None for o in outcomes_raw):
        return sorted(
            outcomes_raw,
            key=lambda o: (
                o.get("rank") is None,
                int(o["rank"]) if o.get("rank") is not None else 0,
                int(o["id"]) if o.get("id") is not None else 0,
            ),
        )
    return outcomes_raw


def build_prompt_for_market(item: dict[str, Any]) -> str:
    """Render the exact CU v2 prompt for one frozen development-set market."""
    outcomes_ordered = _ordered_outcomes(item)
    outcome_lines = [_cu_prompt_outcome(o) for o in outcomes_ordered[:8]]
    settlement_at = _parse_dt(item.get("resolution_date"))
    category = item.get("llm_sport_category") or item.get("category") or "other"
    event_facts = _item_event_facts(item)

    prompt = _CU_V2_PROMPT.format(
        name=item.get("title") or item.get("name") or "",
        category=category,
        source=item.get("source") or "",
        resolution_date=settlement_at.isoformat() if settlement_at else "unknown",
        outcomes="\n".join(outcome_lines) if outcome_lines else "- unknown",
        measure_vocabulary=", ".join(sorted(CU_FRAME_MEASURES)),
    )
    if event_facts:
        supplied = ", ".join(event_facts)
        prompt += f"\n\nOmit these fields. Bain Luck supplies them: {supplied}."
    return prompt


def apply_writer_postprocess(
    item: dict[str, Any],
    raw: dict[str, Any],
    *,
    model_name: str,
) -> dict[str, Any]:
    """Apply CU v2 deterministic rules and sanitizers without any DB write."""
    title = item.get("title") or item.get("name") or ""
    outcomes_raw = _ordered_outcomes(item)
    outcome_names = item.get("outcome_names") or [o.get("name") for o in outcomes_raw]
    all_probs = [float(o["prob"]) for o in outcomes_raw if o.get("prob") is not None]
    settlement_at = _parse_dt(item.get("resolution_date"))
    event_facts = _item_event_facts(item)

    frame_slot_drops: dict[str, str] = {}
    frame, frame_drop = sanitize_cu_frame(raw.get("frame"), title=title, slot_drops=frame_slot_drops)
    liveness = _compute_liveness(all_probs, item.get("status"))
    clean_entity_mentions(raw.get("entities"))

    profile: dict[str, Any] = {
        "schema_version": CU_V2_SCHEMA_VERSION,
        "writer_rev": CU_WRITER_REV,
        "model": model_name,
        "topic": raw.get("topic"),
        "subtopic": raw.get("subtopic"),
        "entities": raw.get("entities", []),
        "geography": cu_model_geography(
            raw.get("geography"),
            linked_league=item.get("linked_league"),
            home_team_league=item.get("home_team_league"),
            away_team_league=item.get("away_team_league"),
        ),
        "story_key": raw.get("story_key"),
        "series_key": _cu_series_key(raw.get("series_key")),
        "temporal_class": raw.get("temporal"),
        "event_date": cu_unlinked_event_date(raw.get("event_date"), settlement_at),
        "recurrence": raw.get("recurrence"),
        "stakes": raw.get("stakes"),
        "breadth": raw.get("breadth"),
        "oddity": raw.get("oddity"),
        "arc": raw.get("arc"),
        "hook_facts": raw.get("hook_facts", []),
        "junk_flags": cu_junk_flags(outcome_names, raw.get("junk_flags")),
        "confidence": raw.get("confidence"),
        "liveness": liveness,
        "frame": frame,
        "frame_drop_reason": frame_drop,
        "frame_slot_drops": frame_slot_drops,
    }
    profile.update(event_facts)
    return profile


def _normalize_for_diff(field: str, value: Any) -> Any:
    if field == "entities" and isinstance(value, list):
        return sorted(
            (str(e.get("name") or "").strip().lower(), str(e.get("type") or "").strip().lower())
            if isinstance(e, dict)
            else (str(e or "").strip().lower(), "")
            for e in value
        )
    if field == "junk_flags" and isinstance(value, list):
        return sorted(str(v).strip().lower() for v in value)
    if field == "hook_facts" and isinstance(value, list):
        return [
            (str(h.get("type") or "").strip().lower(), str(h.get("text") or "").strip())
            if isinstance(h, dict)
            else str(h)
            for h in value
        ]
    return value


def compare_cu_runs(
    markets: list[dict[str, Any]],
    run1: dict[int, dict[str, Any]],
    run2: dict[int, dict[str, Any]],
    *,
    fields: tuple[str, ...] = COMPARED_FIELDS,
) -> dict[str, Any]:
    """Compute per-field change rates and ordered changed-market list."""
    field_changes: dict[str, int] = {f: 0 for f in fields}
    changed_markets: list[dict[str, Any]] = []

    for item in markets:
        mid = int(item["market_id"])
        p1 = run1.get(mid) or {}
        p2 = run2.get(mid) or {}
        diffs: list[str] = []
        detail: dict[str, list[Any]] = {}
        for f in fields:
            v1 = _normalize_for_diff(f, p1.get(f))
            v2 = _normalize_for_diff(f, p2.get(f))
            if v1 != v2:
                field_changes[f] += 1
                diffs.append(f)
                detail[f] = [p1.get(f), p2.get(f)]
        if diffs:
            changed_markets.append(
                {
                    "market_id": mid,
                    "title": item.get("title"),
                    "draw_bucket": item.get("draw_bucket"),
                    "source": item.get("source"),
                    "changed_fields": diffs,
                    "field_count": len(diffs),
                    "diffs": detail,
                }
            )

    changed_markets.sort(key=lambda r: (-r["field_count"], r["market_id"]))
    n = len(markets)
    over_ten_pct = [
        {"field": f, "changed": cnt, "total": n, "rate": round(cnt / n, 4) if n else 0.0}
        for f, cnt in sorted(field_changes.items(), key=lambda kv: (-kv[1], kv[0]))
        if n > 0 and cnt > 0.10 * n
    ]
    return {
        "market_count": n,
        "any_field_changed_markets": len(changed_markets),
        "any_model_field_changed_markets": sum(
            1 for m in changed_markets if any(f in MODEL_DECIDED_FIELDS for f in m["changed_fields"])
        ),
        "per_field_changes": [
            {
                "field": f,
                "changed": field_changes[f],
                "total": n,
                "rate": round(field_changes[f] / n, 4) if n else 0.0,
            }
            for f in sorted(fields, key=lambda k: (-field_changes[k], k))
        ],
        "fields_over_10_pct": over_ten_pct,
        "changed_markets": changed_markets,
    }


def execute_repeatability_runs(
    dev_path: Path,
    *,
    max_budget_usd: float = MAX_TOTAL_USD,
    limit: int | None = None,
) -> dict[str, Any]:
    if max_budget_usd <= 0 or max_budget_usd > MAX_TOTAL_USD:
        raise ValueError(f"max_budget_usd must be in (0, {MAX_TOTAL_USD}], got {max_budget_usd}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY must be set in the environment (this script never reads .env files)"
        )

    from openai import OpenAI

    from app.services.llm_request import JobBudget, complete_chat_detailed

    raw_bytes = dev_path.read_bytes()
    dev_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    payload = json.loads(raw_bytes.decode("utf-8"))
    markets = payload["markets"][:limit] if limit else payload["markets"]
    budget = JobBudget(limit_usd=max_budget_usd)
    client = OpenAI(api_key=api_key, timeout=30.0)

    runs_profiles: list[dict[int, dict[str, Any]]] = []
    run_stats: list[dict[str, Any]] = []
    model_used: str | None = None

    for run_idx in (1, 2):
        profiles: dict[int, dict[str, Any]] = {}
        cost_usd = 0.0
        in_tok = 0
        out_tok = 0
        calls = 0
        errors = 0
        for idx, item in enumerate(markets, start=1):
            mid = int(item["market_id"])
            prompt = build_prompt_for_market(item)
            result = complete_chat_detailed(
                "cu_v2",
                client,
                max_output_tokens=500,
                temperature=0.1,
                job_budget=budget,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            calls += 1
            model_used = model_used or result.model
            if result.cost_usd is None:
                raise RuntimeError(f"Missing computed cost on market {mid} in run {run_idx}")
            cost_usd += result.cost_usd
            usage = getattr(result.response, "usage", None)
            if usage:
                in_tok += int(getattr(usage, "prompt_tokens", 0) or 0)
                out_tok += int(getattr(usage, "completion_tokens", 0) or 0)
            content = result.response.choices[0].message.content or "{}"
            try:
                raw = _json_from_llm_response(content)
            except Exception:
                raw = {}
                errors += 1
            profiles[mid] = apply_writer_postprocess(item, raw, model_name=result.model)
            if idx % 25 == 0 or idx == len(markets):
                print(
                    f"[run {run_idx}] {idx}/{len(markets)} spent=${budget.spent_usd:.6f}",
                    flush=True,
                )
            time.sleep(0.05)

        runs_profiles.append(profiles)
        run_stats.append(
            {
                "run": run_idx,
                "calls": calls,
                "parse_errors": errors,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(cost_usd, 6),
            }
        )

    diff = compare_cu_runs(markets, runs_profiles[0], runs_profiles[1])
    total_actual_usd = round(sum(s["cost_usd"] for s in run_stats), 6)
    return {
        "issue": 13899,
        "dataset": payload.get("dataset"),
        "dev_set_sha256": dev_sha256,
        "seed": payload.get("seed"),
        "writer_rev": CU_WRITER_REV,
        "model": model_used,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "budget_cap_usd": max_budget_usd,
        "ledger_spent_usd": round(budget.spent_usd, 6),
        "actual_cost_usd": total_actual_usd,
        "runs": run_stats,
        "comparison": diff,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run CU v2 writer twice on frozen dev set (#13899).")
    parser.add_argument("--dev", type=Path, default=DEFAULT_DEV_PATH, help="Frozen cu_dev_200_v1.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help="Output JSON report path")
    parser.add_argument("--max-usd", type=float, default=MAX_TOTAL_USD, help="Hard USD cap <= $1.00")
    parser.add_argument("--limit", type=int, default=None, help="Optional market limit for dry check")
    args = parser.parse_args(argv)

    report = execute_repeatability_runs(args.dev, max_budget_usd=args.max_usd, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    comp = report["comparison"]
    print(
        f"Completed 2 runs over {comp['market_count']} markets | total=${report['actual_cost_usd']:.6f} "
        f"(ledger=${report['ledger_spent_usd']:.6f}) | any_changed={comp['any_field_changed_markets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
