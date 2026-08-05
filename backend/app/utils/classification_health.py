"""Classification health — one pure contract from taxonomy state to a verdict.

UX-P001. The Taxonomy admin page used to fire "Needs attention" whenever ANY
active event or open futures market had empty stored tags
(``event_coverage.untagged > 0 || futures_coverage.untagged > 0``). That is a
false alarm: the persisted ``event_tags`` / ``market_tags`` JSONB columns are
*backfill debt* — inline classification from the source columns
(``compute_event_tags`` / ``compute_market_tags``, the authority) still works,
so the user sees a correctly-classified card. Pure backfill debt tripping the
headline is exactly the "the health signal cries wolf" failure the grid health
score was retired for (CLAUDE.md, Grid Sentinel).

This module separates two orthogonal axes, mirroring the discipline of
``app/utils/task_verdict.py``:

* **Actionable defect** — an *eligible* (product-visible) record whose
  classification is genuinely broken. Three kinds, all proved against the
  inline authority:

  ``missing``
      Inline classification yields no sport identity at all — we cannot
      classify the record, so a user sees an unclassified card.
  ``invalid``
      A *stored* tag is not in the controlled vocabulary (``validate_tag``
      fails) — e.g. left behind by a vocabulary change.
  ``authority_disagree``
      A *stored* identity tag (sport / league / category) contradicts what the
      inline authority computes — the persisted tag is stale-wrong.

* **Backfill debt** — an eligible record with empty stored tags whose inline
  classification succeeds. Real maintenance work, never a product defect, so it
  is reported separately and never alarms.

The verdict follows the four-state discipline of ``task_verdict``:

``green``
    A COMPLETE census of the eligible population found zero actionable defects.
    Debt may coexist — GREEN is "healthy-with-debt". Hard to earn: the census
    must cover every eligible record.
``yellow``
    Zero actionable defects found, but the census could not be completed
    (bounded enumeration truncated) — incomplete evidence, so GREEN cannot be
    asserted.
``red``
    At least one proved actionable defect on eligible content. A proved defect
    reads RED regardless of census completeness — evidence of a real problem is
    not weakened by not having finished looking.
``unknown``
    The census itself failed (a query raised). Fail-closed — never GREEN.

The module is pure: no DB, no Redis, no imports from ``app.tasks``. Its only
dependency is the pure taxonomy vocabulary (``validate_tag``). It never raises
on caller-supplied data — a shape it cannot read contributes no defect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.utils.event_taxonomy import validate_tag

# --- Envelope version -------------------------------------------------------
#: Bump when the envelope shape or the classification semantics change, so a
#: stale cached payload is recognisable to the consumer.
VERSION = 1

# --- Verdicts ---------------------------------------------------------------
GREEN = "green"
YELLOW = "yellow"
RED = "red"
UNKNOWN = "unknown"

# --- Actionable defect reasons ---------------------------------------------
MISSING = "missing"
INVALID = "invalid"
AUTHORITY_DISAGREE = "authority_disagree"

#: Identity-bearing namespaces compared for ``authority_disagree``. A stored
#: value in one of these that is disjoint from the inline-computed value is a
#: proved contradiction. Non-identity namespaces (status, timing, signal, ei …)
#: change legitimately over a record's life and are never compared.
_IDENTITY_NAMESPACES = ("sport", "league", "category")

#: How many representative defect IDs to surface. Bounded so the payload stays
#: small and the page never leads with a raw-ID dump.
_MAX_REPRESENTATIVE_IDS = 10


@dataclass(frozen=True)
class RecordInput:
    """One eligible record examined by the census.

    ``inline_tags`` are the AUTHORITY — the tags ``compute_event_tags`` /
    ``compute_market_tags`` produce from the record's source columns right now.
    ``stored_tags`` are the persisted JSONB (the backfill debt axis).
    """

    kind: str  # "event" | "futures"
    id: int
    inline_tags: list[str] = field(default_factory=list)
    stored_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KindCensus:
    """The census outcome for one record kind (events or futures).

    ``verified`` is the number of eligible records this run can VOUCH for
    (examined-and-clean, examined-and-defective, or clean-by-construction). It
    equals ``eligible_total`` exactly when ``census_complete`` is True.
    ``records`` carries only the eligible records actually examined for defects
    (for futures this is the SQL-narrowed candidate set; the rest are clean by
    construction).
    """

    eligible_total: int
    verified: int
    census_complete: bool
    records: list[RecordInput] = field(default_factory=list)


def _by_namespace(tags: Optional[Iterable[str]]) -> dict[str, set[str]]:
    """Group ``namespace:value`` tags into ``{namespace: {values}}``.

    Malformed entries (no colon, non-str) are skipped — never raises.
    """
    out: dict[str, set[str]] = {}
    for tag in tags or ():
        if not isinstance(tag, str) or ":" not in tag:
            continue
        ns, val = tag.split(":", 1)
        out.setdefault(ns, set()).add(val)
    return out


def classify_record(record: RecordInput) -> frozenset[str]:
    """Return the set of actionable-defect reasons for one eligible record.

    Empty set = the record is clean (it may still carry backfill debt, which is
    not a defect and is measured separately). Never raises.
    """
    reasons: set[str] = set()

    try:
        inline = _by_namespace(record.inline_tags)
        stored = _by_namespace(record.stored_tags)

        # MISSING — inline authority cannot establish a sport identity.
        if not inline.get("sport"):
            reasons.add(MISSING)

        # INVALID — a stored tag is outside the controlled vocabulary.
        # Non-str entries are malformed noise, not a vocabulary tag; skip them
        # (and keep ``validate_tag``, which is not None-safe, from raising).
        for tag in record.stored_tags or ():
            if not isinstance(tag, str):
                continue
            if not validate_tag(tag):
                reasons.add(INVALID)
                break

        # AUTHORITY_DISAGREE — a stored identity tag contradicts the authority.
        # Only fires when BOTH sides carry that namespace and are disjoint, so a
        # record with empty stored tags (pure debt) is never flagged.
        for ns in _IDENTITY_NAMESPACES:
            s_vals = stored.get(ns)
            i_vals = inline.get(ns)
            if s_vals and i_vals and not (s_vals & i_vals):
                reasons.add(AUTHORITY_DISAGREE)
                break
    except Exception:  # noqa: BLE001 — a health probe must never crash its caller
        return frozenset()

    return frozenset(reasons)


def _derive_verdict(actionable_count: int, census_complete: bool) -> tuple[str, str]:
    """Map (defect count, completeness) to (verdict, machine reason)."""
    if actionable_count > 0:
        return RED, f"actionable_defects={actionable_count}"
    if not census_complete:
        return YELLOW, "census_incomplete"
    return GREEN, "complete_census_zero_defects"


def unknown_envelope(reason: str, generated_at: str) -> dict:
    """Fail-closed envelope for a census that could not run. Never GREEN."""
    return {
        "version": VERSION,
        "verdict": UNKNOWN,
        "reason": reason,
        "generated_at": generated_at,
        "census_complete": False,
        "eligible": {
            "numerator": 0,
            "denominator": 0,
            "events": 0,
            "futures": 0,
        },
        "actionable": {
            "count": 0,
            "reasons": {},
            "representative_ids": [],
        },
    }


def evaluate(
    *,
    events: KindCensus,
    futures: KindCensus,
    generated_at: str,
) -> dict:
    """Build the versioned ``classification_health`` envelope from two censuses.

    Pure: takes already-loaded records + census metadata, returns the envelope.
    The DB work (eligibility filtering, SQL denominators, candidate narrowing)
    belongs to the caller; this is the decision layer.
    """
    reason_counts: dict[str, int] = {}
    representative: list[dict] = []
    actionable_count = 0

    for census in (events, futures):
        for record in census.records:
            defects = classify_record(record)
            if not defects:
                continue
            actionable_count += 1
            for r in defects:
                reason_counts[r] = reason_counts.get(r, 0) + 1
            if len(representative) < _MAX_REPRESENTATIVE_IDS:
                representative.append(
                    {
                        "kind": record.kind,
                        "id": record.id,
                        "reasons": sorted(defects),
                    }
                )

    census_complete = events.census_complete and futures.census_complete
    verdict, reason = _derive_verdict(actionable_count, census_complete)

    return {
        "version": VERSION,
        "verdict": verdict,
        "reason": reason,
        "generated_at": generated_at,
        "census_complete": census_complete,
        "eligible": {
            "numerator": events.verified + futures.verified,
            "denominator": events.eligible_total + futures.eligible_total,
            "events": events.eligible_total,
            "futures": futures.eligible_total,
        },
        "actionable": {
            "count": actionable_count,
            "reasons": dict(sorted(reason_counts.items())),
            "representative_ids": representative,
        },
    }
