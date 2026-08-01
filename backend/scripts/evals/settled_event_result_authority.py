"""Dependency-free settled-event result authority contract evaluator."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/settled_event_result_authority.json"
TERMINAL = {"completed", "closed"}
NON_DECISIVE = {"abandoned", "cancelled", "postponed", "void", "no_contest"}
NONTERMINAL = {"scheduled", "live"}


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def _score(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
        and math.isfinite(float(value))
    )


def _score_evidence(rows: Any) -> tuple[list[tuple[int, int]], list[str]]:
    if not isinstance(rows, list):
        return [], ["SCORE_EVIDENCE_WRONG_SHAPE"]
    scores: list[tuple[int, int]] = []
    findings: list[str] = []
    sources: dict[str, tuple[int, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            findings.append("POISON_SCORE_EVIDENCE")
            continue
        if set(("source", "home", "away")) - row.keys():
            findings.append("SCORE_EVIDENCE_MISSING_FIELDS")
            continue
        if not isinstance(row["source"], str) or not row["source"]:
            findings.append("INVALID_SCORE_SOURCE")
            continue
        if not _score(row["home"]) or not _score(row["away"]):
            findings.append("INVALID_SCORE")
            continue
        pair = (row["home"], row["away"])
        if row["source"] in sources and sources[row["source"]] != pair:
            findings.append("DUPLICATE_SOURCE_CONFLICT")
        sources[row["source"]] = pair
        scores.append(pair)
    if len(set(scores)) > 1:
        findings.append("SCORE_AUTHORITY_CONFLICT")
    return scores, sorted(set(findings))


def evaluate(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    if case.get("schema_version") != policy["case_schema_version"]:
        findings.append("CASE_SCHEMA_MISMATCH")
    status = case.get("status")
    if not isinstance(status, str) or status not in TERMINAL | NON_DECISIVE | NONTERMINAL:
        findings.append("INVALID_STATUS")
    scores, score_findings = _score_evidence(case.get("score_evidence"))
    findings.extend(score_findings)
    if case.get("authority_conflict") is True:
        findings.append("DECLARED_AUTHORITY_CONFLICT")
    if not isinstance(case.get("correction_reopen"), bool):
        findings.append("INVALID_CORRECTION_FLAG")

    authority_state = "unknown"
    winner_side: str | None = None
    final_score: dict[str, int] | None = None
    reasons = sorted(set(findings))
    trustworthy_score = scores[0] if scores and not score_findings else None
    if not findings:
        if case["correction_reopen"]:
            reasons = ["RESULT_REOPENED"]
        elif status in TERMINAL:
            if trustworthy_score is None:
                reasons = ["FINAL_SCORE_MISSING"]
            else:
                home, away = trustworthy_score
                final_score = {"home": home, "away": away}
                if home == away:
                    authority_state, winner_side = "tie", None
                else:
                    authority_state = "decisive"
                    winner_side = "home" if home > away else "away"
        elif status in NON_DECISIVE:
            authority_state = "non_decisive"
            reasons = [f"DISPOSITION_{status.upper()}"]
        else:
            authority_state = "live"

    if authority_state == "decisive":
        terminal_home = 1.0 if winner_side == "home" else 0.0
        api = {
            "mode": "settled_result", "winner_side": winner_side,
            "final_score": final_score, "allowed_terminal_home_probability": terminal_home,
            "stale_live_probability_may_headline": False,
        }
        metadata_mode = web_mode = native_mode = card_mode = "result"
        chart_terminal = winner_side
        sentinel = {"verdict": "pass", "reason": "HERO_MATCHES_FINAL_RESULT"}
    elif authority_state == "tie":
        api = {"mode": "settled_result", "winner_side": None, "final_score": final_score,
               "allowed_terminal_home_probability": None, "stale_live_probability_may_headline": False}
        metadata_mode = web_mode = native_mode = card_mode = "tie"
        chart_terminal = "tie"
        sentinel = {"verdict": "pass", "reason": "TIE_EXPLICIT"}
    elif authority_state == "non_decisive":
        api = {"mode": "typed_disposition", "winner_side": None, "final_score": None,
               "allowed_terminal_home_probability": None, "stale_live_probability_may_headline": False}
        metadata_mode = web_mode = native_mode = card_mode = "disposition"
        chart_terminal = None
        sentinel = {"verdict": "pass", "reason": reasons[0]}
    elif authority_state == "live":
        api = {"mode": "live_probability", "winner_side": None, "final_score": None,
               "allowed_terminal_home_probability": None, "stale_live_probability_may_headline": True}
        metadata_mode = web_mode = native_mode = card_mode = "live_probability"
        chart_terminal = None
        sentinel = {"verdict": "not_applicable", "reason": "EVENT_NOT_TERMINAL"}
    else:
        api = {"mode": "typed_unknown", "winner_side": None, "final_score": None,
               "allowed_terminal_home_probability": None, "stale_live_probability_may_headline": False}
        metadata_mode = web_mode = native_mode = card_mode = "unknown"
        chart_terminal = None
        sentinel = {"verdict": "unknown", "reason": reasons[0] if reasons else "AUTHORITY_UNKNOWN"}

    return {
        "authority_state": authority_state,
        "winner_side": winner_side,
        "final_score": final_score,
        "reasons": reasons,
        "api": api,
        "surfaces": {
            "metadata_mode": metadata_mode,
            "web_hero_mode": web_mode,
            "native_hero_mode": native_mode,
            "card_mode": card_mode,
            "probability_copy_allowed": authority_state == "live",
            "title_suffix_count": 1,
        },
        "chart": {
            "history_mutated": False,
            "terminal_result_marker": chart_terminal,
        },
        "sentinel": sentinel,
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack.get("cases", []):
        result = evaluate(case, pack["policy"])
        expected = case.get("expected", {})
        mismatches = [key for key, value in expected.items() if result.get(key) != value]
        rows.append({"id": case.get("id"), **result, "expected_mismatches": mismatches})
    return {
        "contract_version": pack["policy"]["contract_version"],
        "cases": len(rows),
        "passed": sum(not row["expected_mismatches"] for row in rows),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['passed']}/{result['cases']} settled-result cases passed")
        for row in result["results"]:
            if row["expected_mismatches"]:
                print(f"FAIL {row['id']}: {row['expected_mismatches']}")
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
