"""Sibling-family exam scorer and frozen set-aside card suite (#12374, #12221 §3).

PILLAR: DISCOVER / TRUTH · SHIP: Before model-proposed ``sibling_family`` cards
reach Discover, the model must pass a scored exam on set-aside cards never used
for tuning.

Gates (#12221 §3, Decide 63 / 61-A):
1. ``card_vs_single_member`` (on ``test``, n >= 20):
   Rated *Better* on at least 85% of held-out ``test`` cards (95% Wilson CI
   reported) and *Worse* on at most 10%, with all held-out ``test`` cards
   graded on ``/grade/groupings`` (#12373).
2. ``relation_truth`` (on ``test``, per pass):
   100% of member rows share the stated ``sibling_of`` parent and vary on the
   stated axis, and 0 cards have duplicate members.
3. ``freshness_and_count`` (on ``test``, per pass):
   100% of ``test`` cards have 3-6 live, unsettled members.
4. ``run_to_run_stability`` (across 3 passes):
   Across 3 runs, >= 90% of proposed cards agree on their exact member set.

Spend guard (Decide 61-A):
- Prints estimated cost before running.
- Hard cap: $5.00 per run, $30.00 per month (Nov 2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.utils.roundup_containers import RoundupMembers
from app.utils.sibling_family import (
    _extract_stated_deadline,
    _match_declared_template,
    _tokenize_title,
    select_sibling_family,
)
from app.utils.sibling_family_proposer import (
    DEFAULT_PROPOSER_MODEL,
    HARD_RUN_COST_CAP_USD as PER_RUN_CAP_USD,
    NOVEMBER_MONTHLY_CAP_USD as MONTHLY_BUDGET_CAP_USD,
    verify_word_for_word_quote,
)

# OpenAI published usage rate for gpt-4o-mini (LEGACY_MODEL): $0.15 / 1M input, $0.60 / 1M output.
PRICE_INPUT_PER_1M_USD: float = 0.15
PRICE_OUTPUT_PER_1M_USD: float = 0.60

DEFAULT_EXAM_DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "sibling-family-exam-dataset-2026-11.json"
)
EXAM_EVAL_NOW_UTC = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

EXAM_SCHEMA_VERSION = "sibling-family-exam/1"
EXAM_PASSES: tuple[str, ...] = ("1", "2", "3")
EXAM_SPLITS: tuple[str, ...] = ("test", "dev", "all")

MIN_TEST_CARDS = 20
GATE_BETTER_MIN_RATE = 0.85
GATE_WORSE_MAX_RATE = 0.10
GATE_STABILITY_MIN_RATE = 0.90
MIN_LIVE_MEMBERS = 3
MAX_LIVE_MEMBERS = 6

# Wilson 95% z-value (matches #11951 / #12118 exam machinery)
WILSON_Z_95 = 1.959963984540054

# Decide 109-A (Alex, 2026-11-09): on /grade/groupings, "amazing" (DB "shareable")
# and "fine" (DB "interesting") count as "better", and "no" (DB "neither") counts
# as "worse". The strict "amazing"-only reading is recorded alongside.
GROUPING_GRADE_TO_EXAM_BUCKET: dict[str, str] = {
    "amazing": "better",
    "fine": "better",
    "no": "worse",
    "shareable": "better",
    "interesting": "better",
    "neither": "worse",
    "better": "better",
    "same": "same",
    "worse": "worse",
}
STRICT_AMAZING_GRADES: frozenset[str] = frozenset({"amazing", "shareable"})
GROUPING_PAGE_GRADES: frozenset[str] = frozenset(
    {"amazing", "fine", "no", "shareable", "interesting", "neither"}
)


def normalize_exam_human_grade(grade: Any) -> str | None:
    """Map `/grade/groupings` grades (`amazing`/`fine`/`no` or DB `shareable`/`interesting`/`neither`) to exam buckets (`better`/`same`/`worse`) per Decide 109-A."""
    raw = str(grade or "").strip().lower()
    return GROUPING_GRADE_TO_EXAM_BUCKET.get(raw)


@dataclass(frozen=True)
class SiblingExamCostEstimate:
    """Pre-run cost estimate under Decide 61-A."""

    model: str
    card_count: int
    passes: int
    total_calls: int
    est_input_tokens: int
    est_output_tokens: int
    estimated_usd: float
    per_run_cap_usd: float = PER_RUN_CAP_USD
    monthly_cap_usd: float = MONTHLY_BUDGET_CAP_USD
    month_spent_before_usd: float = 0.0

    @property
    def within_caps(self) -> bool:
        if self.estimated_usd > self.per_run_cap_usd:
            return False
        if (self.month_spent_before_usd + self.estimated_usd) > self.monthly_cap_usd:
            return False
        return True

    def format_banner(self) -> str:
        status = "OK" if self.within_caps else "CAP_EXCEEDED"
        return (
            f"[sibling_family_exam 61-A] model={self.model} "
            f"cards={self.card_count} passes={self.passes} calls={self.total_calls} "
            f"est_tokens={self.est_input_tokens}in/{self.est_output_tokens}out "
            f"estimated_cost=${self.estimated_usd:.4f} "
            f"(run_cap=${self.per_run_cap_usd:.2f}, "
            f"month_spent=${self.month_spent_before_usd:.4f}/${self.monthly_cap_usd:.2f}) "
            f"status={status}"
        )


def wilson95_interval(k: int, n: int) -> tuple[float, float]:
    """Return 95% Wilson confidence interval ``(low_pct, high_pct)`` in percentage points."""
    if n <= 0:
        return (0.0, 0.0)
    k_clamped = max(0, min(int(k), int(n)))
    p = k_clamped / n
    z = WILSON_Z_95
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (
        z
        * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
        / denom
    )
    low = max(0.0, (center - half) * 100.0)
    high = min(100.0, (center + half) * 100.0)
    return (round(low, 1), round(high, 1))


def estimate_sibling_family_exam_cost(
    card_count: int,
    *,
    passes: int = 3,
    model: str = DEFAULT_PROPOSER_MODEL,
    est_input_tokens_per_call: int = 900,
    est_output_tokens_per_call: int = 440,
    month_spent_before_usd: float = 0.0,
) -> SiblingExamCostEstimate:
    """Compute pre-run token and USD cost estimate under Decide 61-A."""
    safe_cards = max(0, int(card_count))
    safe_passes = max(1, int(passes))
    total_calls = safe_cards * safe_passes
    in_tokens = total_calls * max(0, int(est_input_tokens_per_call))
    out_tokens = total_calls * max(0, int(est_output_tokens_per_call))
    est_usd = (
        (in_tokens / 1_000_000.0) * PRICE_INPUT_PER_1M_USD
        + (out_tokens / 1_000_000.0) * PRICE_OUTPUT_PER_1M_USD
    )
    return SiblingExamCostEstimate(
        model=model,
        card_count=safe_cards,
        passes=safe_passes,
        total_calls=total_calls,
        est_input_tokens=in_tokens,
        est_output_tokens=out_tokens,
        estimated_usd=round(est_usd, 4),
        month_spent_before_usd=round(float(month_spent_before_usd), 4),
    )


def _make_card_case(
    card_id: str,
    split: str,
    parent_subject: str,
    axis: str,
    category: str,
    member_labels: Sequence[tuple[int, str, float]],
    *,
    pass3_alt_member_id: int | None = None,
    pass3_Alt_member_id: int | None = None,
) -> dict[str, Any]:
    """Construct a synthetic unit-test card case with 3 pass outputs and ground-truth parent/axis."""
    alt_id = pass3_alt_member_id if pass3_alt_member_id is not None else pass3_Alt_member_id
    base_members = [
        {
            "market_id": mid,
            "label": label,
            "probability": prob,
            "parent_subject": parent_subject,
            "axis_value": label,
            "status": "active",
            "settled": False,
        }
        for mid, label, prob in member_labels
    ]
    pass1_members = [dict(m) for m in base_members]
    pass2_members = [dict(m) for m in base_members]
    pass3_members = [dict(m) for m in base_members]
    if alt_id is not None and pass3_members:
        pass3_members[-1] = {
            **pass3_members[-1],
            "market_id": alt_id,
            "label": f"{pass3_members[-1]['label']} (alt)",
            "axis_value": f"{pass3_members[-1]['label']} (alt)",
        }

    return {
        "card_id": card_id,
        "split": split,
        "parent_subject": parent_subject,
        "axis": axis,
        "category": category,
        "human_grade": None,
        "passes": {
            "1": {
                "members": pass1_members,
                "input_tokens": 610,
                "output_tokens": 135,
            },
            "2": {
                "members": pass2_members,
                "input_tokens": 610,
                "output_tokens": 135,
            },
            "3": {
                "members": pass3_members,
                "input_tokens": 610,
                "output_tokens": 135,
            },
        },
    }


def build_default_sibling_family_exam_dataset(
    dataset_path: Path = DEFAULT_EXAM_DATASET_PATH,
    *,
    raw_payload: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Load the 32-card sibling-family exam dataset (12 ``dev`` + 20 set-aside ``test``) and evaluate each pass via ``verify_word_for_word_quote`` + ``select_sibling_family``.

    - Built from 32 real nominated sibling families on ``https://api.bainluck.com``
      (real 8-digit market IDs, real rule descriptions, real ``yes_probability``)
      evaluated across 3 independent ``sibling_family_proposer`` (``gpt-4o-mini``)
      passes (`96` real API calls with usage-rated ``prompt_tokens`` and
      ``completion_tokens``).
    - ``dev`` (12 cards): used for prompt and clustering tuning.
    - ``test`` (20 set-aside cards): never used for tuning.
    - Human grades on ``test`` start unrated (``None``) until graded on
      ``/grade/groupings`` (#12373), so Gate 1 (``card_vs_single_member``)
      and the overall exam verdict report ``HELD`` (``0 of 20 graded (20 ungraded)``).
    """
    raw = (
        dict(raw_payload)
        if raw_payload is not None
        else json.loads(dataset_path.read_text(encoding="utf-8"))
    )
    cards: list[dict[str, Any]] = []
    for raw_card in raw.get("cards") or []:
        c = dict(raw_card)
        passes_out: dict[str, dict[str, Any]] = {}
        for pass_id, pp in (c.get("passes") or {}).items():
            pp_copy = dict(pp)
            pp_copy["members"] = _derive_members_from_proposer_pass(c, pp_copy)
            passes_out[str(pass_id)] = pp_copy
        c["passes"] = passes_out
        cards.append(c)
    return cards


def _derive_member_parent_from_market_title(title: str, subject: str) -> str:
    """Derive a member market's parent template directly from its own title and extracted subject."""
    stem = _extract_stated_deadline(title).stem_text
    stem_toks = [f for _, f in _tokenize_title(stem)]
    subj_toks = [f for _, f in _tokenize_title(subject)]
    if not stem_toks or not subj_toks:
        return ""
    n = len(subj_toks)
    for idx in range(len(stem_toks) - n + 1):
        if stem_toks[idx : idx + n] == subj_toks:
            return " ".join(stem_toks[:idx] + ["*"] + stem_toks[idx + n :])
    return " ".join(stem_toks)


def _derive_members_from_proposer_pass(
    card: Mapping[str, Any],
    pass_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Run ``verify_word_for_word_quote`` and ``select_sibling_family`` on a recorded proposer pass."""
    candidate_markets = list(card.get("candidate_markets") or [])
    rule = card.get("rule")
    if not candidate_markets or not isinstance(rule, Mapping):
        return [dict(m) for m in (pass_payload.get("members") or [])]

    osd = bool(pass_payload.get("only_subject_differs", True))
    qa = str(pass_payload.get("market_a_quote") or "").strip()
    qb = str(pass_payload.get("market_b_quote") or "").strip()
    va = verify_word_for_word_quote(qa, candidate_markets[0]) if len(candidate_markets) >= 1 else False
    vb = verify_word_for_word_quote(qb, candidate_markets[1]) if len(candidate_markets) >= 2 else False
    quotes_ok = va and vb

    ah_ids = {
        int(x)
        for x in (pass_payload.get("already_happened_market_ids") or [])
        if isinstance(x, int) and not isinstance(x, bool)
    }
    filtered = [m for m in candidate_markets if int(m.get("id") or 0) not in ah_ids]
    declared_template = str(rule["template"])

    verdict = select_sibling_family(
        filtered,
        expected_source=str(rule["source"]),
        template=declared_template,
        title_template=str(rule["title_template"]),
        kicker_prefix=str(rule["kicker_prefix"]),
        kicker_include_date=bool(rule["kicker_include_date"]),
        subject_unit=str(rule["subject_unit"]),
        outcome_name=str(rule["outcome_name"]),
        lead_rule=str(rule["lead_rule"]),
        min_numbered_members=int(rule["min_numbered_members"]),
        card_rows=int(rule["card_rows"]),
        footer=str(card.get("footer") or ""),
        now=EXAM_EVAL_NOW_UTC,
    )
    if not isinstance(verdict, RoundupMembers):
        return []

    by_id = {int(m["id"]): m for m in filtered if isinstance(m.get("id"), int)}
    out_members: list[dict[str, Any]] = []
    for row in verdict.rows:
        mid = int(row.get("market_id") or 0)
        src_m = by_id.get(mid, {})
        subj = str(row.get("subject") or row.get("label") or "").strip()
        status_raw = str(src_m.get("status") or "open").strip().lower()
        derived_parent = (
            _derive_member_parent_from_market_title(str(src_m.get("name") or ""), subj)
            if (osd and quotes_ok)
            else ""
        )
        out_members.append(
            {
                "market_id": mid,
                "label": subj,
                "probability": row.get("probability"),
                "parent_subject": derived_parent,
                "axis_value": subj,
                "status": "active" if status_raw in ("open", "active") else status_raw,
                "settled": status_raw in ("settled", "closed", "resolved"),
            }
        )

    # If any non-excluded candidate market in filtered did not match the declared
    # template, retain it as an unmatched member with its own tokenized stem so
    # relation_truth fails whenever a contaminated market enters the pass.
    for src_m in filtered:
        mid = int(src_m.get("id") or 0)
        title = str(src_m.get("name") or "")
        stem = _extract_stated_deadline(title).stem_text
        if not _match_declared_template(stem, declared_template):
            status_raw = str(src_m.get("status") or "open").strip().lower()
            unmatched_parent = " ".join(f for _, f in _tokenize_title(stem))
            out_members.append(
                {
                    "market_id": mid,
                    "label": title,
                    "probability": src_m.get("yes_probability"),
                    "parent_subject": unmatched_parent,
                    "axis_value": title,
                    "status": "active" if status_raw in ("open", "active") else status_raw,
                    "settled": status_raw in ("settled", "closed", "resolved"),
                }
            )
    return out_members


def _evaluate_card_pass(card: Mapping[str, Any], pass_id: str) -> dict[str, Any]:
    """Evaluate a single card's pass output on relation truth and freshness/count."""
    expected_parent = str(card.get("parent_subject") or "").strip()
    pass_payload = (card.get("passes") or {}).get(pass_id) or {}
    if "members" in pass_payload:
        members = list(pass_payload.get("members") or [])
    else:
        members = _derive_members_from_proposer_pass(card, pass_payload)

    member_ids: list[int] = []
    axis_values: list[str] = []
    parent_matches_all = len(members) > 0
    all_live_unsettled = len(members) > 0

    for m in members:
        mid = int(m.get("market_id") or 0)
        member_ids.append(mid)
        m_parent = str(m.get("parent_subject") or "").strip()
        m_axis = str(m.get("axis_value") or m.get("label") or "").strip()
        axis_values.append(m_axis.lower())
        if not m_parent or m_parent != expected_parent:
            parent_matches_all = False
        status = str(m.get("status") or "active").lower()
        settled = bool(m.get("settled", False))
        if status != "active" or settled:
            all_live_unsettled = False

    has_duplicate_members = len(set(member_ids)) != len(member_ids)
    varies_on_axis = len(set(axis_values)) == len(axis_values) and len(axis_values) > 1
    relation_truth_ok = (
        parent_matches_all and varies_on_axis and not has_duplicate_members
    )
    count_in_range = MIN_LIVE_MEMBERS <= len(members) <= MAX_LIVE_MEMBERS
    freshness_and_count_ok = count_in_range and all_live_unsettled

    return {
        "member_set": tuple(sorted(member_ids)),
        "member_count": len(members),
        "parent_matches_all": parent_matches_all,
        "varies_on_axis": varies_on_axis,
        "has_duplicate_members": has_duplicate_members,
        "relation_truth_ok": relation_truth_ok,
        "freshness_and_count_ok": freshness_and_count_ok,
        "input_tokens": int(pass_payload.get("input_tokens") or 0),
        "output_tokens": int(pass_payload.get("output_tokens") or 0),
    }


def _score_split_for_pass(
    cards: Sequence[Mapping[str, Any]],
    pass_id: str,
) -> dict[str, Any]:
    n = len(cards)
    better = 0
    same = 0
    worse = 0
    ungraded = 0
    strict_amazing = 0
    has_grouping_page_grade = False
    relation_valid = 0
    duplicate_free = 0
    freshness_valid = 0

    for card in cards:
        raw_grade = str(card.get("human_grade") or "").strip().lower()
        if raw_grade in GROUPING_PAGE_GRADES:
            has_grouping_page_grade = True
        if raw_grade in STRICT_AMAZING_GRADES:
            strict_amazing += 1
        bucket = normalize_exam_human_grade(raw_grade)
        if bucket == "better":
            better += 1
        elif bucket == "same":
            same += 1
        elif bucket == "worse":
            worse += 1
        else:
            ungraded += 1

        ev = _evaluate_card_pass(card, pass_id)
        if ev["relation_truth_ok"]:
            relation_valid += 1
        if not ev["has_duplicate_members"]:
            duplicate_free += 1
        if ev["freshness_and_count_ok"]:
            freshness_valid += 1

    graded = better + same + worse
    out: dict[str, Any] = {
        "expected": n,
        "graded": graded,
        "ungraded": ungraded,
        "better": {
            "k": better,
            "n": graded,
            "ungraded": ungraded,
            "pct": round((better / graded) * 100.0, 1) if graded else None,
            "wilson95": list(wilson95_interval(better, graded)) if graded else None,
        },
        "same": {
            "k": same,
            "n": graded,
            "ungraded": ungraded,
            "pct": round((same / graded) * 100.0, 1) if graded else None,
            "wilson95": list(wilson95_interval(same, graded)) if graded else None,
        },
        "worse": {
            "k": worse,
            "n": graded,
            "ungraded": ungraded,
            "pct": round((worse / graded) * 100.0, 1) if graded else None,
            "wilson95": list(wilson95_interval(worse, graded)) if graded else None,
        },
        "relation_truth": {
            "k": relation_valid,
            "n": n,
            "pct": round((relation_valid / n) * 100.0, 1) if n else 0.0,
            "wilson95": list(wilson95_interval(relation_valid, n)),
        },
        "duplicate_free": {
            "k": duplicate_free,
            "n": n,
            "pct": round((duplicate_free / n) * 100.0, 1) if n else 0.0,
            "wilson95": list(wilson95_interval(duplicate_free, n)),
        },
        "freshness_and_count": {
            "k": freshness_valid,
            "n": n,
            "pct": round((freshness_valid / n) * 100.0, 1) if n else 0.0,
            "wilson95": list(wilson95_interval(freshness_valid, n)),
        },
    }
    if has_grouping_page_grade:
        out["strict_amazing"] = {
            "k": strict_amazing,
            "n": graded,
            "ungraded": ungraded,
            "pct": round((strict_amazing / graded) * 100.0, 1) if graded else None,
            "wilson95": list(wilson95_interval(strict_amazing, graded)) if graded else None,
        }
    return out


def score_sibling_family_exam(
    cards: Sequence[Mapping[str, Any]],
    *,
    model: str = DEFAULT_PROPOSER_MODEL,
    as_of: str = "2026-11-08",
    ruling_ref: str = "https://github.com/alexander-bain/bainluck/issues/12221",
    receipt_ref: str = "https://github.com/alexander-bain/bainluck/issues/12374",
    auto_publish_licensed: bool = False,
) -> dict[str, Any]:
    """Score the sibling-family exam across 3 passes and return the full exam record.

    Measured gates return ``PASS`` or ``FAIL``; ``card_vs_single_member`` returns
    ``HELD`` while ``graded_k < n`` so ungraded set-aside cards never read as failed.
    """
    test_cards = [c for c in cards if c.get("split") == "test"]
    dev_cards = [c for c in cards if c.get("split") == "dev"]
    all_cards = list(cards)

    per_pass: dict[str, dict[str, Any]] = {}
    total_in_tokens = 0
    total_out_tokens = 0
    total_replies = 0

    for pass_id in EXAM_PASSES:
        per_pass[pass_id] = {
            "test": _score_split_for_pass(test_cards, pass_id),
            "dev": _score_split_for_pass(dev_cards, pass_id),
            "all": _score_split_for_pass(all_cards, pass_id),
        }
        for c in all_cards:
            ev = _evaluate_card_pass(c, pass_id)
            total_in_tokens += ev["input_tokens"]
            total_out_tokens += ev["output_tokens"]
            total_replies += 1

    # Gate 1: Card vs single member (on test, across the human grading record)
    test_n = len(test_cards)
    p1_test = per_pass["1"]["test"]
    better_k = int(p1_test["better"]["k"])
    worse_k = int(p1_test["worse"]["k"])
    graded_k = int(p1_test["graded"])
    ungraded_k = int(p1_test["ungraded"])
    if test_n < MIN_TEST_CARDS:
        gate1_result = "FAIL"
    elif graded_k < test_n:
        gate1_result = "HELD"
    else:
        better_ok = (better_k / graded_k) >= GATE_BETTER_MIN_RATE
        worse_ok = (worse_k / graded_k) <= GATE_WORSE_MAX_RATE
        gate1_result = "PASS" if (better_ok and worse_ok) else "FAIL"

    # Gate 2: Relation truth (on test, per pass: 100% share parent & vary on axis, 0 duplicates)
    gate2_by_pass: dict[str, dict[str, Any]] = {}
    for pass_id in EXAM_PASSES:
        rel = per_pass[pass_id]["test"]["relation_truth"]
        dup = per_pass[pass_id]["test"]["duplicate_free"]
        n_val = int(rel["n"])
        rel_k = int(rel["k"])
        dup_members = n_val - int(dup["k"])
        pass_ok = (
            n_val >= MIN_TEST_CARDS
            and rel_k == n_val
            and dup_members == 0
        )
        gate2_by_pass[pass_id] = {
            "k": rel_k,
            "n": n_val,
            "duplicate_cards": dup_members,
            "result": "PASS" if pass_ok else "FAIL",
        }
    gate2_result = (
        "PASS"
        if all(cell["result"] == "PASS" for cell in gate2_by_pass.values())
        else "FAIL"
    )

    # Gate 3: Freshness and count (on test, per pass: 100% have 3-6 live unsettled members)
    gate3_by_pass: dict[str, dict[str, Any]] = {}
    for pass_id in EXAM_PASSES:
        fc = per_pass[pass_id]["test"]["freshness_and_count"]
        n_val = int(fc["n"])
        fc_k = int(fc["k"])
        pass_ok = n_val >= MIN_TEST_CARDS and fc_k == n_val
        gate3_by_pass[pass_id] = {
            "k": fc_k,
            "n": n_val,
            "result": "PASS" if pass_ok else "FAIL",
        }
    gate3_result = (
        "PASS"
        if all(cell["result"] == "PASS" for cell in gate3_by_pass.values())
        else "FAIL"
    )

    # Gate 4: Run-to-run stability (across 3 runs, >= 90% agree on their member set)
    all_n = len(all_cards)
    agreed_all = 0
    for c in all_cards:
        sets = {
            _evaluate_card_pass(c, pass_id)["member_set"]
            for pass_id in EXAM_PASSES
        }
        if len(sets) == 1 and next(iter(sets)):
            agreed_all += 1
    stability_ok = (
        all_n > 0
        and len(test_cards) >= MIN_TEST_CARDS
        and (agreed_all / all_n) >= GATE_STABILITY_MIN_RATE
    )
    gate4_result = "PASS" if stability_ok else "FAIL"

    gate1_observed: dict[str, Any] = {
        "k": better_k,
        "n": test_n,
        "better_k": better_k,
        "worse_k": worse_k,
        "graded_k": graded_k,
        "ungraded_k": ungraded_k,
        "better_pct": round((better_k / graded_k) * 100.0, 1) if graded_k else None,
        "worse_pct": round((worse_k / graded_k) * 100.0, 1) if graded_k else None,
        "better_wilson95": (
            list(wilson95_interval(better_k, graded_k)) if graded_k else None
        ),
        "worse_wilson95": (
            list(wilson95_interval(worse_k, graded_k)) if graded_k else None
        ),
        "result": gate1_result,
    }
    if "strict_amazing" in p1_test:
        sa = p1_test["strict_amazing"]
        gate1_observed["strict_amazing_k"] = int(sa["k"])
        gate1_observed["strict_amazing_pct"] = sa["pct"]
        gate1_observed["strict_amazing_wilson95"] = sa["wilson95"]
        gate1_observed["grade_mapping"] = "109-A: amazing + fine -> better, no -> worse"

    gate_results: list[dict[str, Any]] = [
        {
            "id": "card_vs_single_member",
            "bar": "Rated Better on >= 85% of held-out test cards (95% CI reported) and Worse on <= 10%",
            "scope": "test",
            "observed": gate1_observed,
            "result": gate1_result,
        },
        {
            "id": "relation_truth",
            "bar": "100% of member rows share the stated sibling_of parent and vary on the stated axis; 0 duplicate members",
            "scope": "test",
            "by_pass": gate2_by_pass,
            "result": gate2_result,
        },
        {
            "id": "freshness_and_count",
            "bar": "100% of held-out test cards have 3-6 live, unsettled members",
            "scope": "test",
            "by_pass": gate3_by_pass,
            "result": gate3_result,
        },
        {
            "id": "run_to_run_stability",
            "bar": "Across 3 runs, >= 90% of proposed cards agree on their member set",
            "scope": "all",
            "observed": {
                "k": agreed_all,
                "n": all_n,
                "wilson95": list(wilson95_interval(agreed_all, all_n)),
                "result": gate4_result,
            },
            "result": gate4_result,
        },
    ]

    if any(g["result"] == "FAIL" for g in gate_results):
        overall_result = "FAIL"
    elif any(g["result"] == "HELD" for g in gate_results):
        overall_result = "HELD"
    else:
        overall_result = "PASS"

    if overall_result == "FAIL":
        licence_state = "FAIL"
    elif overall_result == "PASS" and auto_publish_licensed:
        licence_state = "PASS"
    else:
        licence_state = "HELD"

    actual_usd = round(
        (total_in_tokens / 1_000_000.0) * PRICE_INPUT_PER_1M_USD
        + (total_out_tokens / 1_000_000.0) * PRICE_OUTPUT_PER_1M_USD,
        4,
    )
    est = estimate_sibling_family_exam_cost(len(all_cards), passes=len(EXAM_PASSES), model=model)

    dataset_canonical = json.dumps(
        [
            {
                "card_id": c.get("card_id"),
                "split": c.get("split"),
                "parent_subject": c.get("parent_subject"),
                "axis": c.get("axis"),
                "category": c.get("category"),
            }
            for c in all_cards
        ],
        sort_keys=True,
    ).encode("utf-8")
    dataset_sha256 = hashlib.sha256(dataset_canonical).hexdigest()
    scorer_sha256 = hashlib.sha256(
        b"sibling-family-exam-scorer/v1:85pct-better,10pct-worse,100pct-relation,3-6-fresh,90pct-stability"
    ).hexdigest()

    return {
        "schema": EXAM_SCHEMA_VERSION,
        "as_of": as_of,
        "ruling": ruling_ref,
        "receipt": receipt_ref,
        "model": model,
        "result": overall_result,
        "licences": {
            "sibling_family": licence_state,
        },
        "split_counts": {
            "test": len(test_cards),
            "dev": len(dev_cards),
            "all": len(all_cards),
        },
        "cost": {
            "estimated_usd": est.estimated_usd,
            "actual_usd": actual_usd,
            "basis": "usage_rated",
            "replies": total_replies,
            "input_tokens": total_in_tokens,
            "output_tokens": total_out_tokens,
            "per_run_cap_usd": PER_RUN_CAP_USD,
            "monthly_cap_usd": MONTHLY_BUDGET_CAP_USD,
        },
        "hashes": {
            "dataset_sha256": dataset_sha256,
            "scorer_sha256": scorer_sha256,
        },
        "gate_results": gate_results,
        "per_pass": per_pass,
    }


def export_sibling_family_exam_for_evals(exam_record: Mapping[str, Any]) -> dict[str, Any]:
    """Export the aggregate exam record for ``/evals`` with zero card-level private strings."""
    return {
        "schema": exam_record["schema"],
        "as_of": exam_record["as_of"],
        "ruling": exam_record["ruling"],
        "receipt": exam_record["receipt"],
        "model": exam_record["model"],
        "result": exam_record["result"],
        "licences": dict(exam_record["licences"]),
        "split_counts": dict(exam_record["split_counts"]),
        "cost": dict(exam_record["cost"]),
        "hashes": dict(exam_record["hashes"]),
        "gate_results": list(exam_record["gate_results"]),
        "per_pass": dict(exam_record["per_pass"]),
    }


def format_sibling_family_exam_markdown(
    exam_record: Mapping[str, Any],
    *,
    cost_banner: str | None = None,
) -> str:
    """Render the human-readable Markdown receipt for ``docs/discover/sibling-family-exam-2026-11.md``."""
    split_counts = exam_record["split_counts"]
    cost = exam_record["cost"]
    licences = exam_record["licences"]
    gates = exam_record["gate_results"]
    p1_test = exam_record["per_pass"]["1"]["test"]

    banner = cost_banner or (
        f"[sibling_family_exam 61-A] model={exam_record['model']} "
        f"cards={split_counts['all']} passes=3 calls={cost['replies']} "
        f"estimated_cost=${cost['estimated_usd']:.4f} actual_cost=${cost['actual_usd']:.4f}"
    )

    lines = [
        "# Sibling-Family Exam Receipt (November 2026 — #12374)",
        "",
        f"- **Date:** {exam_record['as_of']}",
        f"- **Model:** `{exam_record['model']}`",
        f"- **Split:** `{split_counts['dev']}` `dev` cards + `{split_counts['test']}` set-aside `test` cards (`{split_counts['all']}` total across 3 passes = `{cost['replies']}` proposer evaluations)",
        f"- **Overall Exam Verdict:** **{exam_record['result']}**",
        f"- **Licence (`licences.sibling_family`):** **{licences['sibling_family']}**",
        f"- **Ruling / Brief:** {exam_record['ruling']} (§3, Decide 61-A / 63-A)",
        f"- **Issue Receipt:** {exam_record['receipt']}",
        "",
        "## Pre-Run Model Spend Printout (Decide 61-A)",
        "",
        "```text",
        banner,
        "```",
        "",
        f"- **Estimated spend before run:** `${cost['estimated_usd']:.4f}` (cap: `${cost['per_run_cap_usd']:.2f}`/run, `${cost['monthly_cap_usd']:.2f}`/Nov)",
        f"- **Actual usage-rated spend:** `${cost['actual_usd']:.4f}` (`{cost['input_tokens']:,}` input tokens, `{cost['output_tokens']:,}` output tokens across `{cost['replies']}` replies)",
        "",
        "## Gate Verdict Summary (`PASS`, `FAIL`, or `HELD` waiting for grades)",
        "",
        "| Gate | Scope | Bar | Pass 1 | Pass 2 | Pass 3 | Across Passes | Verdict |",
        "|------|-------|-----|--------|--------|--------|---------------|---------|",
    ]

    for g in gates:
        gid = g["id"]
        scope = g["scope"]
        bar = g["bar"]
        verdict = g["result"]
        if "by_pass" in g:
            bp = g["by_pass"]
            p1 = f"{bp['1']['k']}/{bp['1']['n']} ({bp['1']['result']})"
            p2 = f"{bp['2']['k']}/{bp['2']['n']} ({bp['2']['result']})"
            p3 = f"{bp['3']['k']}/{bp['3']['n']} ({bp['3']['result']})"
            across = "—"
        else:
            obs = g["observed"]
            p1 = "—"
            p2 = "—"
            p3 = "—"
            if gid == "card_vs_single_member":
                b_ci = obs.get("better_wilson95")
                w_ci = obs.get("worse_wilson95")
                if obs["graded_k"] < obs["n"]:
                    if obs["graded_k"] > 0 and b_ci and w_ci:
                        across = (
                            f"Waiting for grades: {obs['graded_k']} of {obs['n']} graded "
                            f"({obs['ungraded_k']} ungraded); "
                            f"Better {obs['better_k']}/{obs['graded_k']} ({b_ci[0]}–{b_ci[1]}% CI), "
                            f"Worse {obs['worse_k']}/{obs['graded_k']} ({w_ci[0]}–{w_ci[1]}% CI)"
                        )
                    else:
                        across = (
                            f"Waiting for grades: {obs['graded_k']} of {obs['n']} graded "
                            f"({obs['ungraded_k']} ungraded)"
                        )
                else:
                    sa_str = ""
                    if "strict_amazing_k" in obs:
                        sa_str = f", Strict 'Amazing' {obs['strict_amazing_k']}/{obs['graded_k']} ({obs['strict_amazing_pct']}%)"
                    across = (
                        f"Better {obs['better_k']}/{obs['graded_k']} ({b_ci[0]}–{b_ci[1]}% CI, 109-A: amazing+fine->better){sa_str}, "
                        f"Worse {obs['worse_k']}/{obs['graded_k']} ({w_ci[0]}–{w_ci[1]}% CI), "
                        f"Graded {obs['graded_k']}/{obs['n']}"
                    )
            else:
                ci = obs["wilson95"]
                across = f"{obs['k']}/{obs['n']} ({ci[0]}–{ci[1]}% CI)"
        lines.append(
            f"| `{gid}` | `{scope}` | {bar} | {p1} | {p2} | {p3} | {across} | **{verdict}** |"
        )

    b_ci = p1_test["better"]["wilson95"]
    r_ci = p1_test["relation_truth"]["wilson95"]
    f_ci = p1_test["freshness_and_count"]["wilson95"]
    if p1_test["graded"] < p1_test["expected"]:
        if p1_test["graded"] > 0 and b_ci:
            better_line = (
                f"- **Card vs single member (`Better`):** Waiting for grades: "
                f"`{p1_test['graded']}` of `{p1_test['expected']}` graded "
                f"(`{p1_test['ungraded']}` ungraded); graded so far "
                f"`{p1_test['better']['k']}/{p1_test['better']['n']}` "
                f"(`{p1_test['better']['pct']}%`, 95% CI `{b_ci[0]}%–{b_ci[1]}%`) "
                f"on `/grade/groupings` (#12373)"
            )
        else:
            better_line = (
                f"- **Card vs single member (`Better`):** Waiting for grades: "
                f"`{p1_test['graded']}` of `{p1_test['expected']}` graded "
                f"(`{p1_test['ungraded']}` ungraded) on `/grade/groupings` (#12373)"
            )
    else:
        better_line = (
            f"- **Card vs single member (`Better`):** "
            f"`{p1_test['better']['k']}/{p1_test['better']['n']}` "
            f"(`{p1_test['better']['pct']}%`, 95% CI `{b_ci[0]}%–{b_ci[1]}%`), "
            f"graded `{p1_test['graded']}/{p1_test['expected']}` on `/grade/groupings` (#12373)"
        )
    lines.extend(
        [
            "",
            "## Held-Out `test` Split Detail (20 Set-Aside Cards, 95% Wilson CI)",
            "",
            better_line,
            f"- **Relation truth (`sibling_of` parent + axis variation + 0 duplicates):** `{p1_test['relation_truth']['k']}/{p1_test['relation_truth']['n']}` (`{p1_test['relation_truth']['pct']}%`, 95% CI `{r_ci[0]}%–{r_ci[1]}%`)",
            f"- **Freshness and count (`3–6` live, unsettled members):** `{p1_test['freshness_and_count']['k']}/{p1_test['freshness_and_count']['n']}` (`{p1_test['freshness_and_count']['pct']}%`, 95% CI `{f_ci[0]}%–{f_ci[1]}%`)",
            "",
            "## Record Hashes",
            "",
            f"- `dataset_sha256`: `{exam_record['hashes']['dataset_sha256']}`",
            f"- `scorer_sha256`: `{exam_record['hashes']['scorer_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def run_sibling_family_exam(
    cards: Sequence[Mapping[str, Any]] | None = None,
    *,
    model: str = DEFAULT_PROPOSER_MODEL,
    as_of: str = "2026-11-08",
    month_spent_before_usd: float = 0.0,
    printer: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Print the 61-A cost banner, verify spend caps, and score the sibling-family exam."""
    dataset = list(cards) if cards is not None else build_default_sibling_family_exam_dataset()
    est = estimate_sibling_family_exam_cost(
        len(dataset),
        passes=len(EXAM_PASSES),
        model=model,
        month_spent_before_usd=month_spent_before_usd,
    )
    banner = est.format_banner()
    printer(banner)
    if not est.within_caps:
        raise ValueError(f"Sibling-family exam spend cap exceeded: {banner}")
    record = score_sibling_family_exam(dataset, model=model, as_of=as_of)
    record["cost_banner"] = banner
    return record
