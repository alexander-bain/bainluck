"""Model proposer for new grouping kinds to Alex only, five example cards each (#9937).

Implements Row 11 of ``#12221`` / Item 10 of Epic ``#12288``:
- The model proposes candidate new grouping kinds to **Alex only**
  (``audience="alex_only"``), each backed by **five concrete example cards**
  (``REQUIRED_EXAMPLE_CARDS_PER_KIND = 5``) built from real uncovered market
  families alongside each card's strongest single-market alternative.
- Enforces Decide 61-A spend discipline: uses ``LEGACY_MODEL`` from
  ``app.services.llm_models``, prints the estimated cost before running, and
  enforces the ``$5.00``/run and ``$30.00``/Nov caps. Never runs during page
  loads.
- Catalog & reader isolation gate:
  1. A proposed kind joins the catalog only after ``>= 6`` graded cards with
     ``0`` ``"no"`` verdicts from Alex (``MIN_GRADED_CARDS_FOR_CATALOG = 6``).
  2. **Nothing reaches readers without a licence**: until a proposed kind earns
     a ``PASS`` licence in ``backend/data/grouping_licences.json``, its
     ``reader_reachable`` flag is strictly ``False`` and ``is_kind_licensed``
     refuses it for Discover and container serving.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from app.services.llm_models import LEGACY_MODEL
from app.utils.grouping_licences import UNLICENSED_PROPOSED_KINDS, is_kind_licensed
from app.utils.roundup_containers import (
    CLOSED_GROUPING_RELATIONS,
    CLOSED_PERMISSION_LEVELS,
    HAND_LIST_ID_RULE_KEYS,
    SELECTOR_RULE_KEYS,
)

DEFAULT_KIND_PROPOSER_MODEL = LEGACY_MODEL
KIND_PROPOSER_RUN_CAP_USD = 5.00
KIND_PROPOSER_MONTHLY_CAP_USD = 30.00

_INPUT_COST_PER_1M_USD = 0.15
_OUTPUT_COST_PER_1M_USD = 0.60

REQUIRED_EXAMPLE_CARDS_PER_KIND = 5
MIN_ROWS_PER_EXAMPLE_CARD = 3
MIN_GRADED_CARDS_FOR_CATALOG = 6

ALLOWED_CARD_FORMS: frozenset[str] = frozenset(
    {
        "ladder",
        "strip",
        "two_rows",
        "matrix",
        "bracket",
        "mover",
        "field",
    }
)

STANDING_EXCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:say|mention|tweet|truth social|word)\b", re.IGNORECASE),
    re.compile(r"\b(?:parlay|combo|same game parlay|sgp)\b", re.IGNORECASE),
    re.compile(r"\b(?:die|death|assassination|hospitalized|arrested|indicted|prison)\b", re.IGNORECASE),
)

_FORBIDDEN_QUESTION_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)
_KIND_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_CARD_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

DEFAULT_KIND_PROPOSALS_JSON_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "discover"
    / "new-kind-proposals-2026-11.json"
)
DEFAULT_KIND_PROPOSALS_MD_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "discover"
    / "new-kind-proposals-2026-11.md"
)


class KindProposalSpendCapExceededError(RuntimeError):
    """Raised when a new-kind proposal run would exceed Decide 61-A caps."""


def estimate_kind_proposal_spend(
    candidate_family_count: int,
    *,
    model: str = DEFAULT_KIND_PROPOSER_MODEL,
    avg_input_tokens: int = 1200,
    avg_output_tokens: int = 650,
    prior_november_spend_usd: float = 0.0,
) -> Dict[str, Any]:
    """Estimate token usage and USD cost before running the new-kind proposer (Decide 61-A)."""
    count = max(0, int(candidate_family_count))
    input_tokens = count * max(0, int(avg_input_tokens))
    output_tokens = count * max(0, int(avg_output_tokens))
    est_run_usd = round(
        (input_tokens / 1_000_000.0) * _INPUT_COST_PER_1M_USD
        + (output_tokens / 1_000_000.0) * _OUTPUT_COST_PER_1M_USD,
        6,
    )
    projected_monthly_usd = round(float(prior_november_spend_usd) + est_run_usd, 6)
    within_run_cap = est_run_usd <= KIND_PROPOSER_RUN_CAP_USD
    within_monthly_cap = projected_monthly_usd <= KIND_PROPOSER_MONTHLY_CAP_USD
    return {
        "model": model,
        "candidate_family_count": count,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_run_cost_usd": est_run_usd,
        "run_cap_usd": KIND_PROPOSER_RUN_CAP_USD,
        "prior_november_spend_usd": round(float(prior_november_spend_usd), 6),
        "projected_november_spend_usd": projected_monthly_usd,
        "monthly_cap_usd": KIND_PROPOSER_MONTHLY_CAP_USD,
        "within_caps": bool(within_run_cap and within_monthly_cap),
    }


def format_kind_proposal_pre_run_spend_line(estimate: Mapping[str, Any]) -> str:
    """Format the mandatory Decide 61-A pre-run spend line for the new-kind proposer."""
    return (
        f"[grouping-kind-proposer] model={estimate.get('model', DEFAULT_KIND_PROPOSER_MODEL)} "
        f"families={estimate.get('candidate_family_count', 0)} "
        f"est_run_cost=${float(estimate.get('estimated_run_cost_usd', 0.0)):.4f} "
        f"(cap=${float(estimate.get('run_cap_usd', KIND_PROPOSER_RUN_CAP_USD)):.2f}) "
        f"projected_november=${float(estimate.get('projected_november_spend_usd', 0.0)):.4f} "
        f"(cap=${float(estimate.get('monthly_cap_usd', KIND_PROPOSER_MONTHLY_CAP_USD)):.2f})"
    )


def _format_as_of_label(as_of_iso: str) -> str:
    """Format an ISO-8601 UTC timestamp into ``as of Mon DD, HH:MM UTC``."""
    cleaned = str(as_of_iso or "").strip()
    if not cleaned:
        return ""
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        return f"as of {dt.strftime('%b %d, %H:%M UTC')}"
    except ValueError:
        return f"as of {cleaned}"


def _validate_example_card(
    card: Mapping[str, Any],
    *,
    kind_name: str,
    default_as_of: str = "",
) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Validate one example card inside a proposed grouping kind."""
    slug = str(card.get("slug") or "").strip()
    if not slug or not _CARD_SLUG_RE.match(slug):
        return False, "invalid_example_card_slug", None

    title = str(card.get("title") or "").strip()
    kicker = str(card.get("kicker") or "").strip()
    footer = str(card.get("footer") or "").strip()
    if not title or not kicker or not footer:
        return False, f"missing_card_copy:{slug}", None

    for text_field in (title, kicker, footer):
        if _FORBIDDEN_QUESTION_RE.search(text_field):
            return False, f"forbidden_question_word:{slug}", None
        for pat in STANDING_EXCLUSION_PATTERNS:
            if pat.search(text_field):
                return False, f"standing_exclusion_triggered:{slug}", None

    selector = card.get("selector")
    if not isinstance(selector, Mapping) or not selector:
        return False, f"missing_selector:{slug}", None

    # 73-A: example card must use a selector, never a hand-picked ID list
    if any(
        isinstance(selector.get(k), (list, tuple)) and len(selector.get(k)) > 0
        for k in HAND_LIST_ID_RULE_KEYS
    ):
        return False, f"hand_list_forbidden_in_new_kind:{slug}", None

    if not any(bool(selector.get(k)) for k in SELECTOR_RULE_KEYS):
        return False, f"selector_missing_canonical_key:{slug}", None

    stronger_single = card.get("stronger_single_alternative")
    if not isinstance(stronger_single, Mapping) or not stronger_single.get("market_id") or not str(
        stronger_single.get("title") or ""
    ).strip():
        return False, f"missing_stronger_single_alternative:{slug}", None

    single_prob = stronger_single.get("probability")
    if (
        not isinstance(single_prob, (int, float))
        or isinstance(single_prob, bool)
        or float(single_prob) <= 0.0
        or float(single_prob) >= 1.0
    ):
        return False, f"invalid_stronger_single_probability:{slug}", None

    raw_rows = card.get("rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        return False, f"missing_rows:{slug}", None
    if len(raw_rows) < MIN_ROWS_PER_EXAMPLE_CARD:
        return False, f"fewer_than_{MIN_ROWS_PER_EXAMPLE_CARD}_rows:{slug}", None

    normalized_rows: List[Dict[str, Any]] = []
    seen_market_ids: set[int] = set()
    for r in raw_rows:
        if not isinstance(r, Mapping):
            return False, f"invalid_row:{slug}", None
        mid = r.get("market_id")
        if not isinstance(mid, int) or isinstance(mid, bool) or mid <= 0:
            return False, f"invalid_row_market_id:{slug}", None
        if mid in seen_market_ids:
            return False, f"duplicate_row_market_id:{slug}:{mid}", None
        seen_market_ids.add(mid)
        label = str(r.get("label") or "").strip()
        if not label or _FORBIDDEN_QUESTION_RE.search(label):
            return False, f"invalid_row_label:{slug}", None
        for pat in STANDING_EXCLUSION_PATTERNS:
            if pat.search(label):
                return False, f"standing_exclusion_in_row:{slug}", None
        prob = r.get("probability")
        if (
            not isinstance(prob, (int, float))
            or isinstance(prob, bool)
            or float(prob) <= 0.0
            or float(prob) >= 1.0
        ):
            return False, f"unpriced_or_settled_row:{slug}:{mid}", None
        pct = int(round(float(prob) * 100))
        source = str(r.get("source") or "kalshi").strip()
        dest_href = str(r.get("destination_href") or f"/futures/{mid}").strip()
        normalized_rows.append(
            {
                "market_id": mid,
                "label": label,
                "probability": round(float(prob), 4),
                "rendered_percent": pct,
                "source": source,
                "destination_href": dest_href,
            }
        )

    as_of_val = str(card.get("as_of") or default_as_of or "").strip()
    as_of_label_val = str(
        card.get("as_of_label") or _format_as_of_label(as_of_val)
    ).strip()

    return (
        True,
        None,
        {
            "slug": slug,
            "kind": kind_name,
            "title": title,
            "kicker": kicker,
            "footer": footer,
            "as_of": as_of_val or None,
            "as_of_label": as_of_label_val or None,
            "selector": dict(selector),
            "stronger_single_alternative": {
                "market_id": int(stronger_single["market_id"]),
                "title": str(stronger_single["title"]).strip(),
                "probability": round(float(single_prob), 4),
                "destination_href": str(
                    stronger_single.get("destination_href")
                    or f"/futures/{int(stronger_single['market_id'])}"
                ).strip(),
            },
            "rows": normalized_rows,
        },
    )


def validate_proposed_grouping_kind(
    raw: Mapping[str, Any],
    *,
    licences_path: Optional[Path | str] = None,
    default_as_of: str = "",
) -> Dict[str, Any]:
    """Validate a candidate new grouping kind proposal (#9937).

    Enforces:
    - Valid ``kind`` identifier, ``title``, ``rationale``, ``card_form`` in
      ``ALLOWED_CARD_FORMS``.
    - ``relations`` in ``CLOSED_GROUPING_RELATIONS`` and ``level`` in
      ``CLOSED_PERMISSION_LEVELS`` (71-A).
    - Exactly ``REQUIRED_EXAMPLE_CARDS_PER_KIND`` (5) valid example cards, each
      with a reproducible selector (73-A), a priced ``stronger_single_alternative``,
      and ``>= 3`` priced rows from current market IDs.
    - ``audience == "alex_only"`` and ``reader_reachable == False`` whenever the
      kind does not hold a ``PASS`` licence in ``grouping_licences.json``.
    """
    if not isinstance(raw, Mapping):
        return {"ok": False, "reason": "invalid_payload", "proposal": None}

    kind = str(raw.get("kind") or "").strip()
    if not kind or not _KIND_SLUG_RE.match(kind):
        return {"ok": False, "reason": "invalid_kind_slug", "proposal": None}

    title = str(raw.get("title") or "").strip()
    rationale = str(raw.get("rationale") or "").strip()
    if not title or not rationale:
        return {"ok": False, "reason": "missing_title_or_rationale", "proposal": None}
    if _FORBIDDEN_QUESTION_RE.search(title) or _FORBIDDEN_QUESTION_RE.search(rationale):
        return {"ok": False, "reason": "forbidden_question_word", "proposal": None}

    card_form = str(raw.get("card_form") or "").strip()
    if card_form not in ALLOWED_CARD_FORMS:
        return {"ok": False, "reason": f"invalid_card_form:{card_form}", "proposal": None}

    raw_relations = raw.get("relations")
    if not isinstance(raw_relations, (list, tuple)) or not raw_relations:
        return {"ok": False, "reason": "missing_relations", "proposal": None}
    relations: List[str] = []
    for rel in raw_relations:
        r_str = str(rel or "").strip()
        if not r_str or r_str not in CLOSED_GROUPING_RELATIONS:
            return {"ok": False, "reason": f"invalid_relation:{r_str}", "proposal": None}
        relations.append(r_str)

    level = str(raw.get("level") or "member").strip()
    if level not in CLOSED_PERMISSION_LEVELS:
        return {"ok": False, "reason": f"invalid_level:{level}", "proposal": None}
    if level == "equivalent" and "twin" not in relations:
        return {"ok": False, "reason": "equivalent_requires_twin_relation", "proposal": None}

    raw_selector_params = raw.get("selector_parameters")
    if not isinstance(raw_selector_params, (list, tuple)) or not raw_selector_params:
        return {"ok": False, "reason": "missing_selector_parameters", "proposal": None}
    selector_parameters = [str(p).strip() for p in raw_selector_params if str(p).strip()]
    if not any(p in SELECTOR_RULE_KEYS for p in selector_parameters):
        return {"ok": False, "reason": "selector_parameters_not_in_closed_keys", "proposal": None}

    raw_truth_checks = raw.get("truth_checks")
    if not isinstance(raw_truth_checks, (list, tuple)) or not raw_truth_checks:
        return {"ok": False, "reason": "missing_truth_checks", "proposal": None}
    truth_checks = [str(c).strip() for c in raw_truth_checks if str(c).strip()]

    raw_cards = raw.get("example_cards")
    if not isinstance(raw_cards, Sequence) or isinstance(raw_cards, (str, bytes)):
        return {"ok": False, "reason": "missing_example_cards", "proposal": None}
    if len(raw_cards) != REQUIRED_EXAMPLE_CARDS_PER_KIND:
        return {
            "ok": False,
            "reason": f"requires_{REQUIRED_EXAMPLE_CARDS_PER_KIND}_example_cards_got_{len(raw_cards)}",
            "proposal": None,
        }

    prop_as_of = str(raw.get("as_of") or default_as_of or "").strip()
    validated_cards: List[Dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for c in raw_cards:
        if not isinstance(c, Mapping):
            return {"ok": False, "reason": "invalid_example_card_entry", "proposal": None}
        ok, err, norm_card = _validate_example_card(
            c, kind_name=kind, default_as_of=prop_as_of
        )
        if not ok or norm_card is None:
            return {"ok": False, "reason": err or "invalid_example_card", "proposal": None}
        if norm_card["slug"] in seen_slugs:
            return {
                "ok": False,
                "reason": f"duplicate_example_card_slug:{norm_card['slug']}",
                "proposal": None,
            }
        seen_slugs.add(norm_card["slug"])
        validated_cards.append(norm_card)

    licensed = (
        is_kind_licensed(kind, path=licences_path)
        if licences_path is not None
        else is_kind_licensed(kind)
    )

    return {
        "ok": True,
        "reason": None,
        "proposal": {
            "kind": kind,
            "title": title,
            "rationale": rationale,
            "audience": "alex_only",
            "relations": relations,
            "level": level,
            "card_form": card_form,
            "selector_parameters": selector_parameters,
            "truth_checks": truth_checks,
            "example_card_count": len(validated_cards),
            "example_cards": validated_cards,
            "licence_status": "PASS" if licensed else "UNLICENSED",
            "reader_reachable": False,
        },
    }


def evaluate_kind_catalog_admission(
    kind: str,
    grades: Sequence[Mapping[str, Any]],
    *,
    licences_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Evaluate whether a proposed kind can join the catalog and/or reach readers (#9937).

    - Row 11 rule: "The model proposes new kinds to Alex only, five example cards
      each; one with six graded cards and no 'no' joins the catalog."
    - Licence rule: "nothing reaches readers without a licence." Even after
      joining the catalog, ``can_reach_readers`` is ``False`` unless
      ``is_kind_licensed(kind)`` is ``True``.
    """
    alex_grades = [
        g
        for g in (grades or [])
        if isinstance(g, Mapping)
        and str(g.get("kind") or "").strip() == kind
        and str(g.get("grader") or "alex").strip().lower() == "alex"
    ]
    yes_count = sum(
        1 for g in alex_grades if str(g.get("verdict") or "").strip().lower() == "yes"
    )
    no_count = sum(
        1 for g in alex_grades if str(g.get("verdict") or "").strip().lower() == "no"
    )
    total_graded = yes_count + no_count
    joins_catalog = (
        total_graded >= MIN_GRADED_CARDS_FOR_CATALOG and no_count == 0
    )
    licensed = (
        is_kind_licensed(kind, path=licences_path)
        if licences_path is not None
        else is_kind_licensed(kind)
    )
    return {
        "kind": kind,
        "total_alex_graded": total_graded,
        "yes_count": yes_count,
        "no_count": no_count,
        "required_graded_cards": MIN_GRADED_CARDS_FOR_CATALOG,
        "joins_catalog": joins_catalog,
        "is_licensed": licensed,
        "can_reach_readers": bool(joins_catalog and licensed),
    }


def propose_new_grouping_kinds(
    candidate_kinds: Sequence[Mapping[str, Any]],
    *,
    prior_november_spend_usd: float = 0.0,
    avg_input_tokens: int = 1200,
    avg_output_tokens: int = 650,
    licences_path: Optional[Path | str] = None,
    print_fn: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Run the offline new-kind proposer for Alex only under Decide 61-A (#9937).

    Prints the estimated spend before running, enforces the $5.00/run and
    $30.00/Nov caps, and validates that every accepted kind proposal carries
    five example cards and remains strictly unreachable by readers without a
    licence.
    """
    estimate = estimate_kind_proposal_spend(
        len(candidate_kinds),
        model=DEFAULT_KIND_PROPOSER_MODEL,
        avg_input_tokens=avg_input_tokens,
        avg_output_tokens=avg_output_tokens,
        prior_november_spend_usd=prior_november_spend_usd,
    )
    spend_line = format_kind_proposal_pre_run_spend_line(estimate)
    print_fn(spend_line)

    if not estimate["within_caps"]:
        raise KindProposalSpendCapExceededError(
            f"New-kind proposer run exceeds Decide 61-A cap: {spend_line}"
        )

    accepted: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []

    for raw in candidate_kinds:
        verdict = validate_proposed_grouping_kind(raw, licences_path=licences_path)
        if verdict["ok"] and verdict["proposal"] is not None:
            accepted.append(verdict["proposal"])
        else:
            refused.append(
                {
                    "kind": str(raw.get("kind") or "") if isinstance(raw, Mapping) else "",
                    "reason": verdict["reason"],
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audience": "alex_only",
        "spend_estimate": estimate,
        "pre_run_spend_line": spend_line,
        "accepted_count": len(accepted),
        "refused_count": len(refused),
        "proposals": accepted,
        "refused": refused,
    }


def load_committed_kind_proposals(
    path: Path | str = DEFAULT_KIND_PROPOSALS_JSON_PATH,
) -> Dict[str, Any]:
    """Load and re-validate the committed new-kind proposals artifact for Alex's grading.

    Raises ``FileNotFoundError`` when ``path`` is missing and ``ValueError``
    when the JSON payload is not a valid mapping with a non-empty ``proposals``
    list. Never silently drops a refused proposal: any proposal that fails
    re-validation is returned in ``refused`` with its explicit refusal reason.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"New-kind proposals file not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"Invalid new-kind proposals payload in {p}: expected mapping")
    raw_proposals = raw.get("proposals")
    if not isinstance(raw_proposals, list) or not raw_proposals:
        raise ValueError(
            f"Invalid new-kind proposals payload in {p}: expected non-empty proposals list"
        )
    generated_at = str(raw.get("generated_at") or "").strip()
    verified: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    for item in raw_proposals:
        if not isinstance(item, Mapping):
            refused.append({"kind": "", "reason": "invalid_payload"})
            continue
        res = validate_proposed_grouping_kind(item, default_as_of=generated_at)
        if res["ok"] and res["proposal"] is not None:
            verified.append(res["proposal"])
        else:
            refused.append(
                {
                    "kind": str(item.get("kind") or "").strip(),
                    "reason": res["reason"],
                }
            )
    return {
        "generated_at": raw.get("generated_at"),
        "audience": "alex_only",
        "spend_estimate": raw.get("spend_estimate"),
        "pre_run_spend_line": raw.get("pre_run_spend_line"),
        "accepted_count": len(verified),
        "refused_count": len(refused),
        "proposals": verified,
        "refused": refused,
    }
