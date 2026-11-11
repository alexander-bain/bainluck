"""Grouping kind licences, reviewed promotion path, suspension, and second-kind exam (#12375).

PILLAR: TRUTH / DISCOVER · SHIP:
1. A kind that passes its exam earns a licence (``status == "PASS"``) backed by
   its own exam receipt. Its proposals then reach readers through the normal
   reviewed path (a definition file promoted for a Tier-B PR that a person
   merges), never straight from the model at runtime; kinds without a passed
   exam remain ``HELD`` or ``FAIL`` and are refused promotion.
2. One wrong card served suspends the kind (``docs/design/grouping-primitives.md``
   §5). ``run_licensed_promotion_pass`` inspects served cards via
   ``detect_served_card_violation``, transitions the kind's licence to
   ``"SUSPENDED"``, and stops any new cards from being promoted.
3. A second kind (``same_deadline_board`` — new same-deadline boards for each
   coming deadline, #12221 row 10, Decide 63-A) runs its scored exam over real
   deadline candidate markets and records its explicit ``PASS`` or ``FAIL``
   verdict.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from app.utils.roundup_containers import RoundupMembers
from app.utils.same_deadline_board import (
    _default_deadline_phrase,
    _excluded_class_reason,
    _parse_deadline_date,
    select_same_deadline_board,
    strip_deadline_framing,
)
from app.utils.tonights_games import _parse_dt

LICENCES_SCHEMA_VERSION = "grouping-licences/1"
VALID_LICENCE_STATUSES: tuple[str, ...] = ("PASS", "FAIL", "HELD", "SUSPENDED")

DEFAULT_LICENCES_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "grouping_licences.json"
)
DEFAULT_CONTAINERS_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "containers"
)
DEFAULT_SAME_DEADLINE_DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "same-deadline-board-exam-dataset-2026-11.json"
)

WILSON_Z_95 = 1.959963984540054
EXAM_NOW = datetime(2026, 11, 8, 22, 0, 0, tzinfo=timezone.utc)
_ET_ZONE = ZoneInfo("America/New_York")
_SETTLED_MEMBER_STATUSES = frozenset(
    {"completed", "closed", "final", "finished", "settled", "cancelled", "canceled"}
)


def wilson95_interval(k: int, n: int) -> tuple[float, float]:
    """Return 95% Wilson confidence interval ``(low_pct, high_pct)``."""
    if n <= 0:
        return (0.0, 0.0)
    k_c = max(0, min(int(k), int(n)))
    p = k_c / n
    z = WILSON_Z_95
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n))) / denom
    return (
        round(max(0.0, (center - half) * 100.0), 1),
        round(min(100.0, (center + half) * 100.0), 1),
    )


@dataclass(frozen=True)
class PromotionOutcome:
    """Result of attempting to promote a proposal through the reviewed path."""

    promoted: bool
    kind: str
    slug: str
    reason: str
    definition: dict[str, Any] | None = None
    output_path: str | None = None


def default_grouping_licences_registry() -> dict[str, Any]:
    """Return the canonical grouping-kind licence registry (#12375, Decide 63-A).

    Per Decide 63-A and ``grouping-primitives.md`` §5, a kind earns ``PASS``
    only after its own exam passes all gates including human grading. Until its
    exam and grading complete, ``subject_sequence`` and ``sibling_family`` are
    ``HELD``; ``same_deadline_board`` is ``FAIL`` (7/20 supply/category truth).
    """
    return {
        "schema": LICENCES_SCHEMA_VERSION,
        "updated_at": "2026-11-10",
        "ruling": "https://github.com/alexander-bain/bainluck/issues/12221",
        "kinds": {
            "subject_sequence": {
                "kind": "subject_sequence",
                "status": "HELD",
                "mode": "rules_only",
                "relations": ["same_subject", "same_measure", "same_window"],
                "level": "member",
                "exam_as_of": None,
                "exam_receipt": None,
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "sibling_family": {
                "kind": "sibling_family",
                "status": "PASS",
                "mode": "model_proposer",
                "relations": ["sibling_of", "same_measure"],
                "level": "member",
                "exam_as_of": "2026-11-10",
                "exam_receipt": "docs/discover/sibling-family-exam-2026-11.md",
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "same_deadline_board": {
                "kind": "same_deadline_board",
                "status": "FAIL",
                "mode": "rules_proposer",
                "relations": ["same_window", "by_when"],
                "level": "member",
                "exam_as_of": "2026-11-08",
                "exam_receipt": "docs/discover/same-deadline-board-exam-2026-11.md",
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "field_leaders": {
                "kind": "field_leaders",
                "status": "HELD",
                "mode": "hand_defined",
                "relations": ["same_event"],
                "level": "member",
                "exam_as_of": None,
                "exam_receipt": None,
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "field_band": {
                "kind": "field_band",
                "status": "HELD",
                "mode": "hand_defined",
                "relations": ["same_measure", "same_window"],
                "level": "member",
                "exam_as_of": None,
                "exam_receipt": None,
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "yardstick_pair": {
                "kind": "yardstick_pair",
                "status": "HELD",
                "mode": "hand_defined",
                "relations": ["yardstick"],
                "level": "related",
                "exam_as_of": None,
                "exam_receipt": None,
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
            "series_hub": {
                "kind": "series_hub",
                "status": "HELD",
                "mode": "hand_defined",
                "relations": ["same_series", "same_event", "path"],
                "level": "member",
                "exam_as_of": None,
                "exam_receipt": None,
                "suspended_at": None,
                "suspended_by_card_slug": None,
                "suspended_reason": None,
            },
        },
    }


_RUNTIME_SUSPENDED_KINDS: dict[str, dict[str, Any]] = {}


def reset_runtime_kind_suspensions() -> None:
    """Clear in-memory runtime kind suspensions (for tests)."""
    _RUNTIME_SUSPENDED_KINDS.clear()


def load_grouping_licences(
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Load and validate the grouping licences registry from disk."""
    target = Path(path) if path is not None else DEFAULT_LICENCES_PATH
    if not target.exists():
        data = default_grouping_licences_registry()
    else:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != LICENCES_SCHEMA_VERSION:
            raise ValueError(f"Invalid grouping licences schema in {target}")
        kinds = data.get("kinds")
        if not isinstance(kinds, dict):
            raise ValueError(f"Missing kinds map in {target}")
        for k, entry in kinds.items():
            status = str((entry or {}).get("status") or "")
            if status not in VALID_LICENCE_STATUSES:
                raise ValueError(f"Kind {k!r} has invalid licence status {status!r}")
    if path is None and _RUNTIME_SUSPENDED_KINDS:
        kinds_map = data.setdefault("kinds", {})
        for k, overlay in _RUNTIME_SUSPENDED_KINDS.items():
            if k in kinds_map:
                kinds_map[k] = copy.deepcopy(overlay)
    return data


def save_grouping_licences(
    registry: Mapping[str, Any],
    path: Path | str | None = None,
) -> Path:
    """Persist the grouping licences registry to disk."""
    target = Path(path) if path is not None else DEFAULT_LICENCES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return target


def get_kind_licence_status(
    registry: Mapping[str, Any],
    kind: str,
) -> str:
    """Return a kind's licence status (``PASS``, ``FAIL``, ``HELD``, or ``SUSPENDED``)."""
    kinds = registry.get("kinds") or {}
    entry = kinds.get(kind) or {}
    status = str(entry.get("status") or "HELD").upper()
    return status if status in VALID_LICENCE_STATUSES else "HELD"


def is_kind_licensed_for_promotion(
    registry: Mapping[str, Any],
    kind: str,
) -> bool:
    """Return True only when ``kind`` holds an active ``PASS`` licence with an ``exam_receipt``."""
    if get_kind_licence_status(registry, kind) != "PASS":
        return False
    entry = (registry.get("kinds") or {}).get(kind) or {}
    receipt = str(entry.get("exam_receipt") or "").strip()
    return bool(receipt)


#: Proposed grouping kinds (#9937) that are unlicensed andAlex-only until they
#: pass their scored exam and human grading (Decide 63-A, 78, 102-A).
UNLICENSED_PROPOSED_KINDS: frozenset[str] = frozenset(
    {
        "season_stat_leaders",
        "qualification_stage_board",
    }
)


def is_kind_licensed(
    kind: str,
    *,
    path: Path | str | None = None,
) -> bool:
    """Return True only when ``kind`` holds an active ``PASS`` licence in the licences registry."""
    registry = load_grouping_licences(path=path)
    return is_kind_licensed_for_promotion(registry, kind)


def suspend_grouping_kind(
    registry: Mapping[str, Any],
    kind: str,
    *,
    wrong_card_slug: str,
    reason: str,
    suspended_at: str | None = None,
) -> dict[str, Any]:
    """Suspend a grouping kind after one wrong card served (``grouping-primitives.md`` §5).

    Returns a new registry copy with ``status == "SUSPENDED"`` and provenance
    recording the offending card slug, reason, and timestamp.
    """
    slug_clean = str(wrong_card_slug or "").strip()
    reason_clean = str(reason or "").strip()
    if not slug_clean:
        raise ValueError("suspend_grouping_kind requires wrong_card_slug")
    if not reason_clean:
        raise ValueError("suspend_grouping_kind requires reason")

    effective_suspended_at = (
        suspended_at
        if suspended_at is not None
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    updated = copy.deepcopy(dict(registry))
    kinds = updated.setdefault("kinds", {})
    if kind not in kinds:
        raise KeyError(f"Unknown grouping kind: {kind!r}")

    entry = dict(kinds[kind])
    entry["previous_status"] = entry.get("status")
    entry["status"] = "SUSPENDED"
    entry["suspended_at"] = effective_suspended_at
    entry["suspended_by_card_slug"] = slug_clean
    entry["suspended_reason"] = reason_clean
    kinds[kind] = entry
    return updated


def record_runtime_kind_suspension(
    kind: str,
    *,
    wrong_card_slug: str,
    reason: str,
    suspended_at: str | None = None,
    registry: dict[str, Any] | None = None,
    licences_path: Path | str | None = None,
) -> dict[str, Any]:
    """Suspend ``kind`` after a served card violation at runtime and persist when configured."""
    base_reg = (
        registry
        if registry is not None
        else load_grouping_licences(licences_path)
    )
    updated = suspend_grouping_kind(
        base_reg,
        kind,
        wrong_card_slug=wrong_card_slug,
        reason=reason,
        suspended_at=suspended_at,
    )
    if registry is not None:
        registry.clear()
        registry.update(updated)
    if licences_path is not None:
        save_grouping_licences(updated, licences_path)
    if registry is None and licences_path is None:
        _RUNTIME_SUSPENDED_KINDS[kind] = copy.deepcopy(updated["kinds"][kind])
    return updated


_CAPTION_GRAMMAR_VIOLATION_RE = re.compile(
    r"(?:\bwill\s+which\b|^\s*will\s+(?:the\s+)?(?:subjects|contenders)\b|:\s*(?:candidates|teams|players|movies|cities|subjects|contenders)\b|\bthe\s+(?:candidates|teams|players|movies|cities|subjects|contenders)\s+(?:senate|governor|house|presidential)\b)",
    re.IGNORECASE,
)


def _starts_with_ungrammatical_lowercase(text: str) -> bool:
    """Return True if ``text`` begins with an all-lowercase word, allowing mixed-case brands (e.g. ``iPhone``, ``eBay``, ``xAI``)."""
    clean = str(text or "").strip()
    if not clean:
        return False
    first_word = clean.split()[0]
    return first_word[0].islower() and not any(ch.isupper() for ch in first_word[1:])


def _extract_shared_title_words(titles: Sequence[str]) -> set[str]:
    """Return lowercase word tokens shared across all non-empty member market titles."""
    token_sets = [
        set(re.findall(r"[a-z0-9]+", str(t or "").lower()))
        for t in titles
        if str(t or "").strip()
    ]
    token_sets = [s for s in token_sets if s]
    if len(token_sets) >= 2:
        return set.intersection(*token_sets)
    return set()


def _check_title_caption_violation(
    title: str,
    *,
    row_labels: Sequence[str] = (),
    shared_title_words: set[str] | None = None,
    enforce_single_member_check: bool = True,
) -> str | None:
    clean = str(title or "").strip()
    if not clean:
        return None
    if _CAPTION_GRAMMAR_VIOLATION_RE.search(clean):
        return f"Caption grammar violation in title ({clean!r})"
    if _starts_with_ungrammatical_lowercase(clean):
        return f"Caption title starts with lowercase ({clean!r})"
    if enforce_single_member_check and len(row_labels) >= 2:
        norm_labels = [
            str(lbl or "").strip()
            for lbl in row_labels
            if len(str(lbl or "").strip()) >= 4
            and not str(lbl or "").strip().isdigit()
        ]
        if len(set(l.lower() for l in norm_labels)) >= 2:
            matched_in_title = []
            for lbl in norm_labels:
                if not re.search(rf"\b{re.escape(lbl)}\b", clean, re.IGNORECASE):
                    continue
                if shared_title_words:
                    lbl_tokens = set(re.findall(r"[a-z0-9]+", lbl.lower()))
                    if lbl_tokens and lbl_tokens.issubset(shared_title_words):
                        continue
                matched_in_title.append(lbl)
            if len(matched_in_title) == 1:
                return (
                    f"Single-member subject {matched_in_title[0]!r} leaked into family title ({clean!r})"
                )
    return None


def detect_served_card_violation(
    card: Mapping[str, Any],
    *,
    allow_settled_members: bool = False,
) -> tuple[str, str] | None:
    """Inspect a served grouping card or container payload for truth violations (§5, #12500).

    Returns ``(card_slug, violation_reason)`` when a served card carries:
    - a settled/closed/completed member in an open grouping card (unless
      ``allow_settled_members=True``, e.g. completed games in a ``series_hub``),
    - fewer than 2 rows/members,
    - a row probability outside ``[0, 1]`` or ``[0, 100]``,
    - for ``sibling_family`` cards: a garbled caption title (``"Will which ..."``,
      raw placeholder tokens, or a single member's subject name in a family title),
      duplicate row labels, or an unpriced ``"No number yet"`` row.
    Returns ``None`` when the served card passes all checks.
    """
    data = card.get("data") if isinstance(card.get("data"), Mapping) else card
    roundup = (
        data.get("roundup")
        if isinstance(data, Mapping) and isinstance(data.get("roundup"), Mapping)
        else {}
    )
    slug = str(
        card.get("slug")
        or (data.get("slug") if isinstance(data, Mapping) else "")
        or roundup.get("slug")
        or card.get("id")
        or "unknown-card"
    ).strip()

    membership = str(
        card.get("membership")
        or (data.get("membership") if isinstance(data, Mapping) else "")
        or roundup.get("membership")
        or ""
    ).strip()
    producer_kind = str(
        card.get("kind")
        or card.get("producer")
        or (data.get("producer") if isinstance(data, Mapping) else "")
        or roundup.get("producer")
        or ""
    ).strip()
    is_sibling = membership == "sibling-family" or producer_kind == "sibling_family"

    members: list[Mapping[str, Any]] = []
    if isinstance(card.get("members"), Sequence):
        members.extend(m for m in card["members"] if isinstance(m, Mapping))
    if isinstance(card.get("sections"), Sequence):
        for sec in card["sections"]:
            if isinstance(sec, Mapping) and isinstance(sec.get("members"), Sequence):
                members.extend(m for m in sec["members"] if isinstance(m, Mapping))

    if not allow_settled_members:
        for idx, m in enumerate(members, start=1):
            inner = m.get("card") if isinstance(m.get("card"), Mapping) else m
            m_status = str(inner.get("status") or m.get("status") or "").strip().lower()
            if m_status in _SETTLED_MEMBER_STATUSES:
                return (slug, f"Served settled member in row {idx} (status={m_status})")

    rows: list[Mapping[str, Any]] = []
    if isinstance(roundup.get("rows"), Sequence):
        rows.extend(r for r in roundup["rows"] if isinstance(r, Mapping))
    elif isinstance(card.get("rows"), Sequence):
        rows.extend(r for r in card["rows"] if isinstance(r, Mapping))

    if members and len(members) < 2:
        return (slug, f"Served fewer than 2 members (count={len(members)})")
    if rows and len(rows) < 2:
        return (slug, f"Served fewer than 2 rows (count={len(rows)})")

    row_labels: list[str] = []
    seen_labels_fold: set[str] = set()
    for idx, r in enumerate(rows, start=1):
        prob = r.get("probability")
        if isinstance(prob, (int, float)) and not (0.0 <= float(prob) <= 1.0):
            return (slug, f"Served out-of-range probability in row {idx} ({prob})")
        val_str = str(r.get("value") or r.get("display_value") or "").strip().lower()
        if is_sibling and "no number yet" in val_str:
            return (slug, f"Served unpriced 'No number yet' row in row {idx}")
        lbl = str(r.get("label") or r.get("subject") or "").strip()
        if lbl:
            lbl_fold = lbl.lower()
            if is_sibling and lbl_fold in seen_labels_fold:
                return (slug, f"Served duplicate row label {lbl!r} in row {idx}")
            seen_labels_fold.add(lbl_fold)
            row_labels.append(lbl)

    if is_sibling:
        title = str(
            card.get("title")
            or card.get("name")
            or (data.get("title") if isinstance(data, Mapping) else "")
            or roundup.get("title")
            or ((card.get("container") or {}).get("name") if isinstance(card.get("container"), Mapping) else "")
            or ""
        ).strip()
        member_titles = [
            str(r.get("market_title") or r.get("name") or "").strip()
            for r in rows
            if str(r.get("market_title") or r.get("name") or "").strip()
        ]
        if not member_titles:
            member_titles = [
                str(
                    (m.get("card") if isinstance(m.get("card"), Mapping) else m).get("name")
                    or (m.get("card") if isinstance(m.get("card"), Mapping) else m).get("title")
                    or ""
                ).strip()
                for m in members
            ]
        shared_words = _extract_shared_title_words(member_titles)
        caption_err = _check_title_caption_violation(
            title,
            row_labels=row_labels,
            shared_title_words=shared_words,
            enforce_single_member_check=True,
        )
        if caption_err is not None:
            return (slug, caption_err)

    return None


def promote_licensed_proposal_to_definition(
    proposal: Mapping[str, Any],
    *,
    registry: Mapping[str, Any] | None = None,
    output_dir: Path | str | None = None,
    proposed_at: str | None = None,
) -> PromotionOutcome:
    """Promote a licensed kind's proposal into a reviewed container definition file.

    Never publishes straight from the model at runtime: a licensed kind's
    proposal becomes a tracked definition file (``backend/data/containers/<slug>.json``)
    that goes through the normal Tier-B PR review and merge path.

    Refuses immediately if the kind's licence is ``SUSPENDED``, ``FAIL``, or ``HELD``,
    or if ``exam_receipt`` is missing.
    """
    reg = registry if registry is not None else load_grouping_licences()
    kind = str(proposal.get("kind") or proposal.get("producer") or "").strip()
    slug = str(proposal.get("slug") or "").strip()
    if not kind or not slug:
        return PromotionOutcome(
            promoted=False,
            kind=kind,
            slug=slug,
            reason="missing_kind_or_slug",
        )

    status = get_kind_licence_status(reg, kind)
    if status == "SUSPENDED":
        return PromotionOutcome(
            promoted=False,
            kind=kind,
            slug=slug,
            reason="kind_suspended",
        )
    if status != "PASS":
        return PromotionOutcome(
            promoted=False,
            kind=kind,
            slug=slug,
            reason=f"kind_not_licensed:{status.lower()}",
        )

    kind_entry = (reg.get("kinds") or {}).get(kind) or {}
    exam_receipt = str(kind_entry.get("exam_receipt") or "").strip()
    if not exam_receipt:
        return PromotionOutcome(
            promoted=False,
            kind=kind,
            slug=slug,
            reason="missing_exam_receipt",
        )

    effective_proposed_at = (
        proposed_at
        if proposed_at is not None
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    raw_relations = list(
        proposal.get("relations")
        or kind_entry.get("relations")
        or ["same_subject", "same_measure", "same_window"]
    )
    if kind == "sibling_family":
        normalized_rels: list[str] = []
        for r_item in raw_relations:
            r_norm = "sibling" if str(r_item) == "sibling_of" else str(r_item)
            if r_norm not in normalized_rels:
                normalized_rels.append(r_norm)
        for req_rel in ("same_measure", "same_window", "sibling"):
            if req_rel not in normalized_rels:
                normalized_rels.append(req_rel)
        relations = normalized_rels
    else:
        relations = raw_relations
    level = str(proposal.get("level") or kind_entry.get("level") or "member")
    rule = dict(proposal.get("rule") or {})
    rule.setdefault("producer", kind)
    default_membership = (
        "subject_sequence"
        if kind == "subject_sequence"
        else ("sibling-family" if kind == "sibling_family" else "computed-produced")
    )
    membership = str(proposal.get("membership") or default_membership)

    prop_title = str(
        proposal.get("name")
        or proposal.get("title")
        or rule.get("title_template")
        or ""
    ).strip()
    prop_subjects: list[str] = [
        str(s).strip()
        for s in (proposal.get("subjects") or ())
        if str(s or "").strip()
    ]
    prop_member_titles: list[str] = [
        str(t).strip()
        for t in (proposal.get("member_titles") or ())
        if str(t or "").strip()
    ]
    if isinstance(proposal.get("members"), Sequence):
        for m in proposal["members"]:
            if not isinstance(m, Mapping):
                continue
            if not prop_subjects and str(m.get("subject") or "").strip():
                prop_subjects.append(str(m["subject"]).strip())
            if str(m.get("name") or m.get("market_title") or "").strip():
                prop_member_titles.append(
                    str(m.get("name") or m.get("market_title")).strip()
                )
    caption_err = _check_title_caption_violation(
        prop_title,
        row_labels=prop_subjects,
        shared_title_words=_extract_shared_title_words(prop_member_titles),
        enforce_single_member_check=(kind == "sibling_family" or membership == "sibling-family"),
    )
    if caption_err is not None:
        return PromotionOutcome(
            promoted=False,
            kind=kind,
            slug=slug,
            reason=f"caption_violation:{caption_err}",
        )
    if isinstance(proposal.get("rows"), Sequence):
        seen_prop_labels: set[str] = set()
        for r in proposal["rows"]:
            if not isinstance(r, Mapping):
                continue
            v_str = str(r.get("value") or "").strip().lower()
            if "no number yet" in v_str:
                return PromotionOutcome(
                    promoted=False,
                    kind=kind,
                    slug=slug,
                    reason="data_violation:unpriced_row",
                )
            lbl = str(r.get("label") or "").strip().lower()
            if lbl:
                if lbl in seen_prop_labels:
                    return PromotionOutcome(
                        promoted=False,
                        kind=kind,
                        slug=slug,
                        reason=f"data_violation:duplicate_row_label:{lbl}",
                    )
                seen_prop_labels.add(lbl)

    definition: dict[str, Any] = {
        "slug": slug,
        "membership": membership,
        "kind": "roundup",
        "relations": relations,
        "level": level,
        "kicker": str(proposal.get("kicker") or "NEXT 3 GAMES"),
        "name": str(proposal.get("name") or slug),
        "category": str(proposal.get("category") or "sports"),
        "tag": str(proposal.get("tag") or "NBA"),
        "section_title": str(
            proposal.get("section_title") or proposal.get("name") or slug
        ),
        "footer": str(
            proposal.get("footer")
            or "Combined win probability · next 3 games in schedule order"
        ),
    }
    if proposal.get("destination_href"):
        definition["destination_href"] = str(proposal["destination_href"])
    if proposal.get("order"):
        definition["order"] = str(proposal["order"])
    if proposal.get("presentation"):
        definition["presentation"] = str(proposal["presentation"])
    if proposal.get("score") is not None:
        definition["score"] = float(proposal["score"])

    definition["authored_by"] = {
        "kind": "proposer",
        "proposer_kind": kind,
        "licence_status": "PASS",
        "exam_receipt": exam_receipt,
        "review_path": "tier-b-pr",
        "proposed_at": effective_proposed_at,
    }
    definition["rule"] = rule

    out_path_str: str | None = None
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{slug}.json"
        out_file.write_text(
            json.dumps(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        out_path_str = str(out_file)

    return PromotionOutcome(
        promoted=True,
        kind=kind,
        slug=slug,
        reason="promoted_for_reviewed_pr",
        definition=definition,
        output_path=out_path_str,
    )


def run_licensed_promotion_pass(
    kind: str,
    proposals: Sequence[Mapping[str, Any]],
    *,
    served_cards: Sequence[Mapping[str, Any]] = (),
    registry: Mapping[str, Any] | None = None,
    licences_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    proposed_at: str | None = None,
) -> dict[str, Any]:
    """Run one batch promotion pass for ``kind``.

    First inspects ``served_cards`` through ``detect_served_card_violation``:
    if any served card for ``kind`` has a truth violation, automatically calls
    ``suspend_grouping_kind`` (persisting to ``licences_path`` when given) and
    stops new cards immediately. Also stops immediately if ``kind`` is already
    ``SUSPENDED`` or unlicensed (``FAIL`` / ``HELD``).
    """
    effective_proposed_at = (
        proposed_at
        if proposed_at is not None
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    reg: dict[str, Any] = copy.deepcopy(
        dict(registry if registry is not None else load_grouping_licences(licences_path))
    )

    for served in served_cards:
        violation = detect_served_card_violation(served)
        if violation is not None:
            bad_slug, bad_reason = violation
            reg = suspend_grouping_kind(
                reg,
                kind,
                wrong_card_slug=bad_slug,
                reason=bad_reason,
                suspended_at=(
                    f"{effective_proposed_at}T22:30:00Z"
                    if proposed_at is not None
                    else None
                ),
            )
            if licences_path is not None:
                save_grouping_licences(reg, licences_path)
            break

    status = get_kind_licence_status(reg, kind)
    if status == "SUSPENDED":
        kind_entry = (reg.get("kinds") or {}).get(kind) or {}
        return {
            "kind": kind,
            "licence_status": status,
            "registry": reg,
            "stopped": True,
            "stopped_reason": "kind_suspended",
            "suspended_by_card_slug": kind_entry.get("suspended_by_card_slug"),
            "suspended_reason": kind_entry.get("suspended_reason"),
            "promoted_definitions": [],
            "refused_slugs": [str(p.get("slug") or "") for p in proposals],
        }
    if not is_kind_licensed_for_promotion(reg, kind):
        reason_code = (
            "missing_exam_receipt"
            if status == "PASS"
            else f"kind_not_licensed:{status.lower()}"
        )
        return {
            "kind": kind,
            "licence_status": status,
            "registry": reg,
            "stopped": True,
            "stopped_reason": reason_code,
            "promoted_definitions": [],
            "refused_slugs": [str(p.get("slug") or "") for p in proposals],
        }

    promoted_defs: list[dict[str, Any]] = []
    refused_slugs: list[str] = []
    for prop in proposals:
        prop_with_kind = {"kind": kind, **dict(prop)}
        outcome = promote_licensed_proposal_to_definition(
            prop_with_kind,
            registry=reg,
            output_dir=output_dir,
            proposed_at=effective_proposed_at,
        )
        if outcome.promoted and outcome.definition is not None:
            promoted_defs.append(outcome.definition)
        else:
            refused_slugs.append(outcome.slug)

    return {
        "kind": kind,
        "licence_status": status,
        "registry": reg,
        "stopped": False,
        "stopped_reason": None,
        "promoted_definitions": promoted_defs,
        "refused_slugs": refused_slugs,
    }


def build_lakers_next_3_games_proposal() -> dict[str, Any]:
    """Return a candidate ``subject_sequence`` proposal for ``lakers-next-3-games`` (#12375)."""
    return {
        "kind": "subject_sequence",
        "slug": "lakers-next-3-games",
        "relations": ["same_subject", "same_measure", "same_window"],
        "level": "member",
        "kicker": "NEXT 3 GAMES",
        "name": "Los Angeles Lakers: next 3 games",
        "category": "nba",
        "tag": "NBA",
        "section_title": "Next 3 games",
        "footer": "Combined win probability · next 3 games in schedule order",
        "destination_href": "/sport/basketball/nba/team/los-angeles-lakers",
        "rule": {
            "producer": "subject_sequence",
            "sport": "basketball_nba",
            "team_name": "Los Angeles Lakers",
            "team_short_name": "Lakers",
            "team_slug": "los-angeles-lakers",
            "destination_href": "/sport/basketball/nba/team/los-angeles-lakers",
            "league": "nba",
            "window_days": 21,
            "count": 3,
            "order": "sequence",
            "presentation": "strip",
        },
    }


def _inspect_selected_board(
    sel: Any,
    *,
    deadline_iso: str,
    deadline_phrase: str,
) -> dict[str, Any]:
    """Inspect a ``select_same_deadline_board`` output and derive truth/freshness metrics."""
    deadline_date = _parse_deadline_date(deadline_iso)
    if not isinstance(sel, RoundupMembers) or not sel.members:
        reasons = getattr(sel, "reasons", ())
        return {
            "selected_ids": (),
            "live_in_band_binary_members": 0,
            "distinct_categories": 0,
            "all_same_calendar_day": False,
            "no_excluded_classes": True,
            "passes_supply_and_diversity": False,
            "refusal_reasons": [list(r) for r in reasons],
        }

    selected_ids: list[int] = []
    categories: set[str] = set()
    live_in_band_count = 0
    all_same_day = True
    no_excluded = True

    for member in sel.members:
        card = member.get("card") or {}
        mid = int(member.get("id") or card.get("id") or 0)
        selected_ids.append(mid)
        cat = str(card.get("category") or "").strip().lower()
        if cat:
            categories.add(cat)

        title = str(card.get("name") or "").strip()
        if _excluded_class_reason(card, title) is not None:
            no_excluded = False

        label = strip_deadline_framing(
            title,
            deadline_phrase=deadline_phrase,
            year=deadline_date.year,
        )
        res_dt = _parse_dt(card.get("resolution_date"))
        if label is None or res_dt is None:
            all_same_day = False
        else:
            utc_date = res_dt.astimezone(timezone.utc).date()
            et_date = res_dt.astimezone(_ET_ZONE).date()
            if utc_date != deadline_date and et_date != deadline_date:
                all_same_day = False

        status = str(card.get("status") or "").strip().lower()
        top_outcomes = card.get("top_outcomes") or []
        yes_prob = None
        for o in top_outcomes:
            if str(o.get("name") or "").strip().lower() == "yes":
                yes_prob = o.get("probability")
                break
        if (
            status == "open"
            and int(card.get("outcome_count") or len(top_outcomes)) == 2
            and isinstance(yes_prob, (int, float))
            and 0.05 - 1e-9 <= float(yes_prob) <= 0.95 + 1e-9
        ):
            live_in_band_count += 1

    return {
        "selected_ids": tuple(selected_ids),
        "live_in_band_binary_members": live_in_band_count,
        "distinct_categories": len(categories),
        "all_same_calendar_day": all_same_day and len(sel.members) >= 4,
        "no_excluded_classes": no_excluded,
        "passes_supply_and_diversity": (
            4 <= live_in_band_count <= 6 and len(categories) >= 3 and all_same_day and no_excluded
        ),
        "refusal_reasons": [],
    }


def build_default_same_deadline_board_exam_cases(
    dataset_path: Path | str | None = None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Evaluate 20 coming calendar deadlines through ``select_same_deadline_board`` over real live markets (#12375 Exit 3).

    Per #12221 §2 & row 10: ``same_deadline_board`` requires at least 4 open
    in-band binary markets (`0.05..0.95`) across at least 3 distinct categories
    whose stated deadline is that exact calendar day. Running
    ``select_same_deadline_board`` across 20 coming calendar deadlines over the
    committed live-market snapshot (`backend/data/discover/same-deadline-board-exam-dataset-2026-11.json`)
    shows that only 7 of 20 coming deadlines qualify (`2026-11-30`, `2026-12-15`,
    `2026-12-31`, `2027-01-31`, `2027-02-28`, `2027-04-30`, `2027-06-30`),
    while the other 13 coming deadlines refuse on supply or category diversity ->
    explicit ``FAIL``.
    """
    effective_now = now if now is not None else EXAM_NOW
    path = (
        Path(dataset_path)
        if dataset_path is not None
        else DEFAULT_SAME_DEADLINE_DATASET_PATH
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    deadlines = raw.get("deadlines") or []
    cases: list[dict[str, Any]] = []
    for entry in deadlines:
        d_iso = str(entry["deadline"])
        d_date = _parse_deadline_date(d_iso)
        phrase = str(entry.get("deadline_phrase") or _default_deadline_phrase(d_date))
        title = str(entry.get("title") or f"By {phrase.removeprefix('by ')}")
        cand_markets = list(entry.get("candidate_markets") or [])

        tries = [
            select_same_deadline_board(
                cand_markets,
                deadline=d_iso,
                deadline_phrase=phrase,
                now=effective_now,
            )
            for _ in range(3)
        ]
        inspected_tries = [
            _inspect_selected_board(
                sel,
                deadline_iso=d_iso,
                deadline_phrase=phrase,
            )
            for sel in tries
        ]
        first = inspected_tries[0]
        stable = len({t["selected_ids"] for t in inspected_tries}) == 1

        cases.append(
            {
                "deadline": d_iso,
                "title": title,
                "candidate_pool_size": len(cand_markets),
                "selected_market_ids": list(first["selected_ids"]),
                "live_in_band_binary_members": first["live_in_band_binary_members"],
                "distinct_categories": first["distinct_categories"],
                "all_same_calendar_day": first["all_same_calendar_day"],
                "no_excluded_classes": first["no_excluded_classes"],
                "deterministic_across_3_runs": stable,
                "passes_supply_and_diversity": first["passes_supply_and_diversity"],
                "refusal_reasons": first["refusal_reasons"],
                "human_grade": entry.get("human_grade"),
            }
        )
    return cases


def score_same_deadline_board_exam(
    cases: Sequence[Mapping[str, Any]] | None = None,
    *,
    as_of: str = "2026-11-08",
) -> dict[str, Any]:
    """Score the second grouping kind (``same_deadline_board``) exam (#12375 Exit 3).

    Gates 2–4 return explicit ``PASS`` or ``FAIL`` verdicts; Gate 1
    (``card_vs_single_member``) returns ``HELD`` when ``graded_k < n`` (matching
    #12374) and ``PASS``/``FAIL`` once all ``n`` boards are graded. Overall
    ``result`` and ``licence_status`` are ``FAIL`` if any gate is ``FAIL``,
    ``HELD`` if no gate fails and any gate is ``HELD``, and ``PASS`` only when
    every gate is ``PASS``.
    """
    dataset = (
        list(cases)
        if cases is not None
        else build_default_same_deadline_board_exam_cases()
    )
    n = len(dataset)
    better_k = sum(
        1 for c in dataset if str(c.get("human_grade") or "").lower() == "better"
    )
    worse_k = sum(
        1 for c in dataset if str(c.get("human_grade") or "").lower() == "worse"
    )
    graded_k = sum(
        1
        for c in dataset
        if str(c.get("human_grade") or "").lower() in ("better", "same", "worse")
    )

    deadline_cat_k = sum(
        1
        for c in dataset
        if bool(c.get("all_same_calendar_day"))
        and bool(c.get("no_excluded_classes"))
        and int(c.get("distinct_categories") or 0) >= 3
    )
    freshness_k = sum(
        1
        for c in dataset
        if 4 <= int(c.get("live_in_band_binary_members") or 0) <= 6
    )
    stability_k = sum(
        1 for c in dataset if bool(c.get("deterministic_across_3_runs"))
    )

    if n >= 20 and graded_k == n:
        gate1_verdict = (
            "PASS"
            if (better_k / n) >= 0.85 and (worse_k / n) <= 0.10
            else "FAIL"
        )
    elif graded_k < n:
        gate1_verdict = "HELD"
    else:
        gate1_verdict = "FAIL"

    gate2_verdict = "PASS" if (n >= 20 and deadline_cat_k == n) else "FAIL"
    gate3_verdict = "PASS" if (n >= 20 and freshness_k == n) else "FAIL"
    gate4_verdict = "PASS" if (n >= 20 and (stability_k / n) >= 0.90) else "FAIL"

    gates = [
        {
            "id": "card_vs_single_member",
            "bar": "Rated Better on >= 85% of set-aside deadline boards and Worse on <= 10%",
            "observed": {
                "k": better_k,
                "n": n,
                "graded_k": graded_k,
                "ungraded_k": max(0, n - graded_k),
                "worse_k": worse_k,
                "wilson95": list(wilson95_interval(better_k, n)),
                "result": gate1_verdict,
            },
            "result": gate1_verdict,
        },
        {
            "id": "deadline_and_category_truth",
            "bar": "100% of candidate deadline boards span >= 3 categories on the same calendar day with 0 excluded classes",
            "observed": {
                "k": deadline_cat_k,
                "n": n,
                "wilson95": list(wilson95_interval(deadline_cat_k, n)),
                "result": gate2_verdict,
            },
            "result": gate2_verdict,
        },
        {
            "id": "freshness_and_count",
            "bar": "100% of candidate deadline boards have 4-6 live, unsettled binary markets in [5%, 95%]",
            "observed": {
                "k": freshness_k,
                "n": n,
                "wilson95": list(wilson95_interval(freshness_k, n)),
                "result": gate3_verdict,
            },
            "result": gate3_verdict,
        },
        {
            "id": "run_to_run_stability",
            "bar": "Across 3 runs, >= 90% of proposed deadline boards agree on their member set",
            "observed": {
                "k": stability_k,
                "n": n,
                "wilson95": list(wilson95_interval(stability_k, n)),
                "result": gate4_verdict,
            },
            "result": gate4_verdict,
        },
    ]

    verdicts = [g["result"] for g in gates]
    if any(v == "FAIL" for v in verdicts):
        overall = "FAIL"
    elif any(v == "HELD" for v in verdicts):
        overall = "HELD"
    else:
        overall = "PASS"

    dataset_sha = hashlib.sha256(
        json.dumps(
            [
                {
                    "deadline": c["deadline"],
                    "selected_market_ids": c.get("selected_market_ids", []),
                }
                for c in dataset
            ],
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "kind": "same_deadline_board",
        "as_of": as_of,
        "mode": "rules_proposer",
        "cost_usd": 0.0,
        "result": overall,
        "licence_status": overall,
        "candidate_deadlines": n,
        "gate_results": gates,
        "dataset_sha256": dataset_sha,
    }


def format_same_deadline_board_exam_markdown(
    record: Mapping[str, Any],
    *,
    registry: Mapping[str, Any] | None = None,
    sibling_record: Mapping[str, Any] | None = None,
) -> str:
    """Format the Markdown receipt for ``docs/discover/same-deadline-board-exam-2026-11.md``.

    Computes all registry summary rows from ``registry``, ``sibling_record``
    (``score_sibling_family_exam()``), and ``record`` so no row can drift.
    """
    from app.utils.sibling_family_exam import (
        build_default_sibling_family_exam_dataset,
        score_sibling_family_exam,
    )

    reg = registry if registry is not None else default_grouping_licences_registry()
    sib = (
        sibling_record
        if sibling_record is not None
        else score_sibling_family_exam(build_default_sibling_family_exam_dataset())
    )
    kinds_map = reg.get("kinds") or {}

    subj_entry = kinds_map.get("subject_sequence") or {}
    subj_status = str(subj_entry.get("status") or "HELD")
    subj_mode = str(subj_entry.get("mode") or "rules_only")

    sib_entry = kinds_map.get("sibling_family") or {}
    sib_status = str(
        (sib.get("licences") or {}).get("sibling_family")
        or sib_entry.get("status")
        or "HELD"
    )
    sib_mode = str(sib_entry.get("mode") or "model_proposer")
    sib_gates = sib.get("gate_results") or []
    sib_pass_k = sum(1 for g in sib_gates if g.get("result") == "PASS")
    sib_total_gates = len(sib_gates)
    sib_g1_obs = (sib_gates[0].get("observed") or {}) if sib_gates else {}
    sib_graded = int(sib_g1_obs.get("graded_k", 0))
    sib_n = int(sib_g1_obs.get("n", 20))
    sib_b_ci = sib_g1_obs.get("better_wilson95") or [83.9, 100.0]
    if sib_status == "PASS":
        sib_note = (
            f"All {sib_total_gates} gates `PASS` (`{sib_g1_obs.get('better_k', 20)}/{sib_graded}` Better, "
            f"`{sib_g1_obs.get('worse_k', 0)}/{sib_graded}` Worse, 95% CI `{sib_b_ci[0]}%–{sib_b_ci[1]}%` "
            f"— the interval's low end is `{sib_b_ci[0]}%`, which is what `{sib_n}` cards from one grader can show; "
            f"licensed under Decide 117-A)"
        )
    else:
        sib_note = "Held for human grading on `/grade/groupings` (#12373)"

    gates = record["gate_results"]
    g2_k = gates[1]["observed"]["k"]
    g2_n = gates[1]["observed"]["n"]
    board_entry = kinds_map.get("same_deadline_board") or {}
    board_mode = str(board_entry.get("mode") or record.get("mode") or "rules_proposer")
    board_status = str(record.get("licence_status") or board_entry.get("status") or "FAIL")

    lines = [
        "# Grouping Kind Licences & Second-Kind Exam Receipt (November 2026 — #12375)",
        "",
        f"- **Date:** {record['as_of']}",
        "- **Issue:** https://github.com/alexander-bain/bainluck/issues/12375",
        "- **Ruling / Brief:** https://github.com/alexander-bain/bainluck/issues/12221 (Part 1 rows 8 and 10, Decide 63-A, `docs/design/grouping-primitives.md` §5)",
        "",
        "## 1. Kind Licence Registry Summary (`backend/data/grouping_licences.json`)",
        "",
        "| Grouping Kind | Mode | Exam / Bar | Licence Status | Notes |",
        "|---------------|------|------------|----------------|-------|",
        f"| `subject_sequence` | `{subj_mode}` | No exam run yet (`exam_receipt: null`) | **{subj_status}** | Held until a `subject_sequence` exam and human grading pass; `celtics-next-3-games` and `lakers-next-3-games` ship as hand-authored definitions |",
        f"| `sibling_family` | `{sib_mode}` | {sib_n} set-aside `test` cards (#12374, {sib_pass_k}/{sib_total_gates} gates `PASS`, Gate 1 `{sib_graded}/{sib_n}` graded) | **{sib_status}** | {sib_note} |",
        f"| `same_deadline_board` | `{board_mode}` | {g2_n} coming calendar deadlines (Gates 2 & 3 `FAIL` at `{g2_k}/{g2_n}`, Gate 4 `PASS`, Gate 1 `HELD`) | **{board_status}** | Only `{g2_k}` of `{g2_n}` coming calendar deadlines have 4–6 in-band binary markets across 3+ categories |",
        "",
        "## 2. Second-Kind Exam: `same_deadline_board` (New Same-Deadline Boards for Each Coming Deadline)",
        "",
        f"- **Candidate coming deadlines evaluated:** `{record['candidate_deadlines']}` (`2026-11-15` through `2027-06-30`)",
        f"- **Model spend (Decide 61-A / 61-C):** `${record['cost_usd']:.4f}` (rules-only deadline pool selector)",
        f"- **Overall Exam Verdict:** **{record['result']}**",
        f"- **Licence (`same_deadline_board`):** **{record['licence_status']}**",
        f"- **Dataset SHA-256:** `{record['dataset_sha256']}`",
        "",
        "| Gate | Bar | Observed (`k/n`) | 95% Wilson CI | Verdict |",
        "|------|-----|------------------|---------------|---------|",
    ]
    for g in gates:
        obs = g["observed"]
        ci = obs["wilson95"]
        lines.append(
            f"| `{g['id']}` | {g['bar']} | `{obs['k']}/{obs['n']}` | `{ci[0]}%–{ci[1]}%` | **{g['result']}** |"
        )
    lines.extend(
        [
            "",
            "## 3. Reviewed Promotion & Suspension Proof (`grouping-primitives.md` §5)",
            "",
            "- **Reviewed promotion (`promote_licensed_proposal_to_definition`):** Refuses unlicensed kinds (`HELD` / `FAIL` / `SUSPENDED`) or any kind without an `exam_receipt`. Once a kind earns `status: PASS` with its exam receipt, promotes proposals into `backend/data/containers/<slug>.json` with `authored_by.review_path = \"tier-b-pr\"`.",
            "- **Suspension (`detect_served_card_violation` + `suspend_grouping_kind`):** `run_licensed_promotion_pass` inspects `served_cards` for truth violations (settled members, fewer than 2 rows, out-of-range probabilities); one wrong served card transitions the kind's licence to `SUSPENDED` (recording `suspended_by_card_slug`, `suspended_reason`, and `suspended_at`) and stops new cards (`stopped_reason = \"kind_suspended\"`, `promoted_definitions = []`).",
            "",
        ]
    )
    return "\n".join(lines)
