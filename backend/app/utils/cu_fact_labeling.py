"""Pure helpers for Content Understanding dual-rater fact labeling (#13900).

Design invariants:
1. Blindness: neither primary nor second rater ever sees the other's answers on
   a market while labeling. A tiebreak rater sees both fact answers only after
   both raters have submitted and disagree on >= 1 fact field.
2. Taste isolation: stakes and breadth are rated last (1-5), agreement counts
   within 1 step, and taste disagreements are NEVER tie-broken — they go to Alex.
3. No real labeler identities appear anywhere in code or defaults. Labelers type
   their own name in the UI.
4. No LLM `discover_llm` metadata is exposed in labeling candidates.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

VALID_SPLITS: tuple[str, ...] = ("sealed", "dev")
VALID_ROLES: tuple[str, ...] = ("primary", "second", "tiebreak")
VALID_SCOPES: tuple[str, ...] = ("shared_100", "all")
VALID_STRUCTURES: tuple[str, ...] = ("ladder", "dated_bucket", "neither")
VALID_SUBJECT_MODES: tuple[str, ...] = ("candidate", "custom", "none_of_these", "not_sure")
FACT_FIELDS: tuple[str, ...] = ("subjects", "event_date", "geography", "structure", "claim_frame")
TASTE_FIELDS: tuple[str, ...] = ("stakes", "breadth")
CLAIM_SLOTS: tuple[str, ...] = ("measure", "comparison", "value", "unit", "deadline")

SHARED_100_SEED_PREFIX = "cu-shared-100-v1:"
SHARED_100_TARGET = 100
SHARED_100_READER_WEIGHTED_TARGET = 67

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_DIR = _BACKEND_DIR.parent
DEFAULT_DATASET_PATHS: dict[str, Path] = {
    "sealed": _BACKEND_DIR / "data" / "evals" / "cu_sealed_300_v1.json",
    "dev": _BACKEND_DIR / "data" / "evals" / "cu_dev_200_v1.json",
}
DEFAULT_REPEATABILITY_PATH = _REPO_DIR / "handoffs" / "cu-repeatability-13899-2026-11-27.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COUNTRY_CODE_RE = re.compile(r"^country:[A-Za-z]{2,3}$")
_TITLE_CANDIDATE_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&'.-]+(?:\s+(?:of|the|and|for|in|on|at|vs\.?|v\.|[A-Z0-9][A-Za-z0-9&'.-]+)){0,4})\b"
)
_GENERIC_STOP = frozenset({
    "Will",
    "What",
    "Who",
    "When",
    "Where",
    "Which",
    "How",
    "The",
    "And",
    "Yes",
    "No",
    "Over",
    "Under",
    "Above",
    "Below",
    "Before",
    "After",
    "Winner",
    "Champion",
    "Total",
    "Highest",
    "Lowest",
    "More",
    "Less",
})
_BINARY_OUTCOMES = frozenset({"yes", "no", "over", "under", "draw", "tie"})


def load_frozen_split(
    split: str,
    *,
    dataset_paths: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    if split not in VALID_SPLITS:
        raise ValueError(f"Unsupported dataset split: {split!r}")
    paths = dataset_paths or DEFAULT_DATASET_PATHS
    path = paths.get(split)
    if not path or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    markets = payload.get("markets")
    return list(markets) if isinstance(markets, list) else []


def load_repeatability_priority_ids(repeatability_path: Path | None = None) -> list[int]:
    path = repeatability_path or DEFAULT_REPEATABILITY_PATH
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = payload.get("comparison", {}).get("changed_markets") or []
    out: list[int] = []
    for row in changed:
        try:
            out.append(int(row["market_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _shared_sort_key(market_id: int) -> str:
    return hashlib.sha256(f"{SHARED_100_SEED_PREFIX}{market_id}".encode("utf-8")).hexdigest()


def select_shared_100_ids(markets: list[dict[str, Any]]) -> list[int]:
    """Deterministically pick the shared 100 markets (67 reader-weighted + 33 spread)."""
    if len(markets) <= SHARED_100_TARGET:
        return [int(m["market_id"]) for m in markets]

    reader = sorted(
        (m for m in markets if m.get("draw_bucket") == "reader_weighted"),
        key=lambda m: _shared_sort_key(int(m["market_id"])),
    )
    other = sorted(
        (m for m in markets if m.get("draw_bucket") != "reader_weighted"),
        key=lambda m: _shared_sort_key(int(m["market_id"])),
    )
    rw_take = reader[:SHARED_100_READER_WEIGHTED_TARGET]
    rem = SHARED_100_TARGET - len(rw_take)
    other_take = other[:rem]
    selected = rw_take + other_take
    if len(selected) < SHARED_100_TARGET:
        used = {int(m["market_id"]) for m in selected}
        leftover = [
            m
            for m in sorted(markets, key=lambda m: _shared_sort_key(int(m["market_id"])))
            if int(m["market_id"]) not in used
        ]
        selected.extend(leftover[: SHARED_100_TARGET - len(selected)])
    selected.sort(key=lambda m: _shared_sort_key(int(m["market_id"])))
    return [int(m["market_id"]) for m in selected]


def order_queue_markets(
    markets: list[dict[str, Any]],
    *,
    split: str,
    scope: str = "shared_100",
    repeatability_priority_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Order labeling queue: dev leads with #13899 changed markets; sealed supports shared_100."""
    by_id = {int(m["market_id"]): m for m in markets}
    if split == "dev":
        ordered_ids: list[int] = []
        seen: set[int] = set()
        for mid in repeatability_priority_ids or []:
            if mid in by_id and mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        for m in markets:
            mid = int(m["market_id"])
            if mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        ordered = [by_id[mid] for mid in ordered_ids]
        return ordered[:SHARED_100_TARGET] if scope == "shared_100" else ordered

    shared_ids = select_shared_100_ids(markets)
    if scope == "shared_100":
        return [by_id[mid] for mid in shared_ids if mid in by_id]
    shared_set = set(shared_ids)
    rest = [m for m in markets if int(m["market_id"]) not in shared_set]
    return [by_id[mid] for mid in shared_ids if mid in by_id] + rest


def extract_subject_candidates(market: dict[str, Any]) -> list[str]:
    """Blind candidate extraction strictly from title + outcomes (never from LLM output)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        cleaned = " ".join(raw.split()).strip(" .,:;?\"'()")
        if not cleaned or len(cleaned) < 2 or len(cleaned) > 80:
            return
        if cleaned in _GENERIC_STOP or cleaned.lower() in _BINARY_OUTCOMES:
            return
        if cleaned[0].isdigit():
            return
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(cleaned)

    title = str(market.get("title") or "")
    for match in _TITLE_CANDIDATE_RE.findall(title):
        _add(match)

    outcomes = market.get("outcome_names") or [
        o.get("name") for o in (market.get("outcomes") or []) if isinstance(o, dict)
    ]
    for outcome_name in outcomes[:12]:
        if isinstance(outcome_name, str):
            text = outcome_name.strip()
            if text and not text.lower().startswith(("above ", "below ", "over ", "under ")):
                _add(text)
    return candidates[:12]


def normalize_subjects_answer(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("subjects_answer must be an object")
    mode = str(raw.get("selection_kind") or "").strip().lower()
    if mode not in VALID_SUBJECT_MODES:
        raise ValueError(f"subjects_answer.selection_kind must be one of {VALID_SUBJECT_MODES}")
    selected_raw = raw.get("selected") or []
    if not isinstance(selected_raw, list):
        raise ValueError("subjects_answer.selected must be a list")
    selected = sorted({ " ".join(str(x).split()).strip() for x in selected_raw if str(x).strip() })
    if mode in {"candidate", "custom"} and not selected:
        raise ValueError(f"subjects_answer.selected is required when selection_kind={mode!r}")
    if mode in {"none_of_these", "not_sure"}:
        selected = []
    return {"selection_kind": mode, "selected": selected}


def normalize_geography_answer(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    low = text.lower()
    if low in {"us", "global", "local"}:
        return low
    if _COUNTRY_CODE_RE.match(text):
        prefix, code = text.split(":", 1)
        return f"{prefix.lower()}:{code.upper()}"
    return text[:64]


def normalize_claim_frame(raw: Any) -> dict[str, str | None] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("claim_frame must be an object or null")
    cleaned: dict[str, str | None] = {}
    any_set = False
    for slot in CLAIM_SLOTS:
        val = raw.get(slot)
        if val is None:
            cleaned[slot] = None
            continue
        s = " ".join(str(val).split()).strip()
        cleaned[slot] = s or None
        if s:
            any_set = True
    return cleaned if any_set else None


def validate_label_submission(
    payload: dict[str, Any],
    *,
    existing_market_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and normalize one CU fact-labeling or tiebreak submission."""
    split = str(payload.get("dataset_split") or "").strip().lower()
    if split not in VALID_SPLITS:
        raise ValueError(f"Invalid dataset_split {split!r}")

    role = str(payload.get("role") or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role {role!r}")

    rater = " ".join(str(payload.get("rater") or "").split()).strip()
    if not rater or len(rater) > 64:
        raise ValueError("rater must be a non-empty typed name (<= 64 chars)")

    try:
        market_id = int(payload.get("market_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("market_id must be an integer") from exc

    no_single_day = bool(payload.get("no_single_day", False))
    event_date_raw = payload.get("event_date_answer")
    event_date: str | None
    if no_single_day or event_date_raw is None or not str(event_date_raw).strip():
        event_date = None
    else:
        event_date = str(event_date_raw).strip()
        if not _DATE_RE.match(event_date):
            raise ValueError("event_date_answer must be YYYY-MM-DD when provided")

    structure_raw = payload.get("structure_answer")
    if structure_raw is None:
        raise ValueError("structure_answer is required")
    structure = str(structure_raw).strip().lower()
    if structure not in VALID_STRUCTURES:
        raise ValueError(f"structure_answer must be one of {VALID_STRUCTURES}")

    subjects = normalize_subjects_answer(payload.get("subjects_answer"))
    geography = normalize_geography_answer(payload.get("geography_answer"))
    if not geography:
        raise ValueError("geography_answer is required (us, global, local, or a country)")
    claim_frame = normalize_claim_frame(payload.get("claim_frame"))

    evidence_note_raw = payload.get("evidence_note")
    evidence_note = str(evidence_note_raw).strip() if evidence_note_raw is not None else None
    if evidence_note == "":
        evidence_note = None

    stakes = payload.get("stakes")
    breadth = payload.get("breadth")

    if role == "tiebreak":
        # Standing #13900 rule: taste is NEVER tie-broken (goes to Alex).
        if stakes is not None or breadth is not None:
            raise ValueError("stakes and breadth cannot be submitted in tiebreak mode")
        if not evidence_note:
            raise ValueError("evidence_note explaining written evidence is required for tiebreak")
        if existing_market_rows is not None:
            pair = _extract_distinct_rater_pair(existing_market_rows)
            if pair is None:
                raise ValueError("Tiebreak requires both primary and second raters to finish first")
            if not fact_disagreements(pair[0], pair[1]):
                raise ValueError("Tiebreak only applies when primary and second disagree on a fact field")
    else:
        for name, val in (("stakes", stakes), ("breadth", breadth)):
            if not isinstance(val, int) or isinstance(val, bool) or val < 1 or val > 5:
                raise ValueError(f"{name} must be an integer from 1 to 5")

    return {
        "dataset_split": split,
        "market_id": market_id,
        "rater": rater,
        "role": role,
        "subjects_answer": subjects,
        "event_date_answer": event_date,
        "no_single_day": no_single_day if event_date is None else False,
        "geography_answer": geography,
        "structure_answer": structure,
        "claim_frame": claim_frame,
        "stakes": None if role == "tiebreak" else int(stakes),
        "breadth": None if role == "tiebreak" else int(breadth),
        "evidence_note": evidence_note,
    }


def _canonical_fact_value(row: dict[str, Any], field: str) -> Any:
    if field == "subjects":
        subj = row.get("subjects_answer") or {}
        mode = str(subj.get("selection_kind") or "").strip().lower()
        selected = tuple(sorted(str(x).strip().lower() for x in (subj.get("selected") or []) if str(x).strip()))
        return (mode, selected)
    if field == "event_date":
        if row.get("no_single_day"):
            return ("no_single_day", None)
        val = row.get("event_date_answer")
        return ("date", str(val).strip() if val else None)
    if field == "geography":
        val = row.get("geography_answer")
        return str(val).strip().lower() if val else None
    if field == "structure":
        val = row.get("structure_answer")
        return str(val).strip().lower() if val else None
    if field == "claim_frame":
        frame = row.get("claim_frame") or {}
        return tuple(
            (slot, str(frame.get(slot)).strip().lower() if frame.get(slot) is not None else None)
            for slot in CLAIM_SLOTS
        )
    raise ValueError(f"Unknown fact field: {field!r}")


def fact_disagreements(row_a: dict[str, Any], row_b: dict[str, Any]) -> list[str]:
    """Return list of fact fields where two submissions differ."""
    return [
        field
        for field in FACT_FIELDS
        if _canonical_fact_value(row_a, field) != _canonical_fact_value(row_b, field)
    ]


def _extract_distinct_rater_pair(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Pick the (primary, second) pair for one market when two distinct raters finished."""
    primary = [r for r in rows if r.get("role") == "primary"]
    second = [r for r in rows if r.get("role") == "second"]
    if primary and second:
        for a in primary:
            for b in second:
                if str(a.get("rater") or "").strip().lower() != str(b.get("rater") or "").strip().lower():
                    return (a, b)
    non_tb = [r for r in rows if r.get("role") in {"primary", "second"}]
    by_rater: dict[str, dict[str, Any]] = {}
    for r in non_tb:
        key = str(r.get("rater") or "").strip().lower()
        if key and key not in by_rater:
            by_rater[key] = r
    if len(by_rater) >= 2:
        vals = list(by_rater.values())
        return (vals[0], vals[1])
    return None


def _strip_taste(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rater": row.get("rater"),
        "role": row.get("role"),
        "subjects_answer": row.get("subjects_answer"),
        "event_date_answer": row.get("event_date_answer"),
        "no_single_day": bool(row.get("no_single_day")),
        "geography_answer": row.get("geography_answer"),
        "structure_answer": row.get("structure_answer"),
        "claim_frame": row.get("claim_frame"),
        "evidence_note": row.get("evidence_note"),
    }


def visible_labels_for_rater(
    market_rows: list[dict[str, Any]],
    *,
    role: str,
    rater: str,
) -> dict[str, Any]:
    """Enforce blind visibility on queue items.

    - Primary / second labelers only ever see their OWN submission (if any) plus a
      boolean indicating whether both raters have finished this market. Another rater's
      answers are NEVER returned while labeling.
    - Tiebreak raters see both primary and second FACT answers (never stakes/breadth)
      only when two distinct raters finished AND disagree on >= 1 fact field.
    """
    norm_rater = " ".join(rater.split()).strip().lower()
    own_row = next(
        (
            r
            for r in market_rows
            if str(r.get("rater") or "").strip().lower() == norm_rater and r.get("role") == role
        ),
        None,
    )
    pair = _extract_distinct_rater_pair(market_rows)
    if role in {"primary", "second"}:
        return {
            "own_label": own_row,
            "pair_complete": pair is not None,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    if pair is None:
        return {
            "own_label": own_row,
            "pair_complete": False,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    diffs = fact_disagreements(pair[0], pair[1])
    if not diffs:
        return {
            "own_label": own_row,
            "pair_complete": True,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    return {
        "own_label": own_row,
        "pair_complete": True,
        "peer_labels": [_strip_taste(pair[0]), _strip_taste(pair[1])],
        "disagreeing_fact_fields": diffs,
    }


def compute_cu_fact_agreement(rows: list[dict[str, Any]], *, split: str) -> dict[str, Any]:
    """Compute per-field dual-rater agreement: exact on facts, within-1 on taste."""
    by_market: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("dataset_split") != split:
            continue
        by_market.setdefault(int(row["market_id"]), []).append(row)

    paired_markets = 0
    needs_tiebreak = 0
    resolved_tiebreaks = 0
    counts: dict[str, dict[str, int]] = {
        f: {"agreed": 0, "total": 0}
        for f in (*FACT_FIELDS, *TASTE_FIELDS)
    }

    for market_id, mrows in sorted(by_market.items()):
        pair = _extract_distinct_rater_pair(mrows)
        if pair is None:
            continue
        paired_markets += 1
        a, b = pair
        has_fact_diff = False
        for field in FACT_FIELDS:
            counts[field]["total"] += 1
            if _canonical_fact_value(a, field) == _canonical_fact_value(b, field):
                counts[field]["agreed"] += 1
            else:
                has_fact_diff = True

        for taste_field in TASTE_FIELDS:
            va = a.get(taste_field)
            vb = b.get(taste_field)
            if isinstance(va, int) and isinstance(vb, int):
                counts[taste_field]["total"] += 1
                if abs(va - vb) <= 1:
                    counts[taste_field]["agreed"] += 1

        if has_fact_diff:
            tb = next((r for r in mrows if r.get("role") == "tiebreak"), None)
            if tb is not None:
                resolved_tiebreaks += 1
            else:
                needs_tiebreak += 1

    field_summary: list[dict[str, Any]] = []
    below_80_fields: list[str] = []
    for field in (*FACT_FIELDS, *TASTE_FIELDS):
        c = counts[field]
        total = c["total"]
        rate = round(c["agreed"] / total, 4) if total else None
        below_80 = rate is not None and rate < 0.80
        if below_80:
            below_80_fields.append(field)
        field_summary.append(
            {
                "field": field,
                "metric": "within_1" if field in TASTE_FIELDS else "exact",
                "agreed": c["agreed"],
                "total": total,
                "agreement_rate": rate,
                "below_80_pct": below_80,
                "tiebreak_allowed": field not in TASTE_FIELDS,
            }
        )

    return {
        "split": split,
        "paired_markets": paired_markets,
        "needs_tiebreak": needs_tiebreak,
        "resolved_tiebreaks": resolved_tiebreaks,
        "below_80_fields": below_80_fields,
        "fields": field_summary,
    }


def _row_to_scorecard_answers(
    row: dict[str, Any],
    *,
    taste_a: dict[str, Any] | None = None,
    taste_b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subj = row.get("subjects_answer") or {}
    mode = subj.get("selection_kind")
    selected = subj.get("selected") or []
    if mode in {"candidate", "custom"}:
        entities: Any = [{"name": s, "type": "unknown"} for s in selected]
    else:
        entities = []

    structure = row.get("structure_answer")
    junk_flags = [structure] if structure in {"ladder", "dated_bucket"} else []

    claim = row.get("claim_frame") or {}
    has_claim = any(claim.get(k) for k in CLAIM_SLOTS)
    frame = (
        {
            "measure": claim.get("measure"),
            "comparator": claim.get("comparison"),
            "value": claim.get("value"),
            "unit": claim.get("unit"),
            "deadline": claim.get("deadline"),
        }
        if has_claim
        else None
    )

    answers: dict[str, Any] = {
        "geography": row.get("geography_answer"),
        "event_date": None if row.get("no_single_day") else row.get("event_date_answer"),
        "junk_flags": junk_flags,
        "frame": frame,
        "entities": entities,
    }
    if taste_a and taste_b is None:
        answers["stakes"] = taste_a.get("stakes")
        answers["breadth"] = taste_a.get("breadth")
    return answers


def build_answer_key_rows(
    markets_by_id: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    split: str,
) -> list[dict[str, Any]]:
    """Build scorecard-compatible answer rows from primary/second/tiebreak labels."""
    by_market: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("dataset_split") != split:
            continue
        by_market.setdefault(int(row["market_id"]), []).append(row)

    exported: list[dict[str, Any]] = []
    for mid, mrows in sorted(by_market.items()):
        tiebreak = next((r for r in mrows if r.get("role") == "tiebreak"), None)
        pair = _extract_distinct_rater_pair(mrows)
        single = next((r for r in mrows if r.get("role") == "primary"), None) or mrows[0]
        source_row = tiebreak or (pair[0] if pair else single)

        meta = markets_by_id.get(mid) or {}
        answers = _row_to_scorecard_answers(
            source_row,
            taste_a=single if tiebreak is None and pair is None else None,
        )
        # If pair differed on facts and no tiebreak yet, drop un-broken fields so scorecard
        # only scores resolved facts; if pair existed without tiebreak, include agreed fields only.
        unresolved = []
        if pair and tiebreak is None:
            unresolved = fact_disagreements(pair[0], pair[1])
            field_to_answer_key = {
                "subjects": "entities",
                "event_date": "event_date",
                "geography": "geography",
                "structure": "junk_flags",
                "claim_frame": "frame",
            }
            for uf in unresolved:
                answers.pop(field_to_answer_key[uf], None)

        exported.append(
            {
                "market_id": mid,
                "dataset_split": split,
                "resolution_source": (
                    "tiebreak"
                    if tiebreak
                    else ("dual_agreed" if pair and not unresolved else "partial_or_single")
                ),
                "unresolved_fact_fields": unresolved,
                "market_meta": {
                    "market_id": mid,
                    "source": meta.get("source"),
                    "category": meta.get("llm_sport_category") or meta.get("category"),
                    "outcome_names": meta.get("outcome_names") or [],
                    "outcome_relation": meta.get("outcome_relation"),
                    "draw_bucket": meta.get("draw_bucket"),
                },
                "answers": answers,
            }
        )
    return exported
