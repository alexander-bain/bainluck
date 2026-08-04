"""Lifecycle-safe Label Pass decisions (#1542).

The Label Pass admin queue (``routes/admin_label_pass.py``) serves LLM-proposed
Discover ranking steers for a human verdict. Accept applies a bounded, expiring,
kill-switchable term to LIVE Discover ranking; Reject trains/downranks the
scorer. A **stale** proposal (resolved/closed market, past its resolution date,
missing, superseded, or premise-overtaken) therefore contaminates live ranking
or training whichever verdict Alex chooses.

This module is the runtime port of the dependency-free C143 oracle
(``scripts/evals/label_pass_lifecycle_contract.py``). The two ``classify_*``
functions are byte-equivalent to that oracle so the committed corpus fixture can
prove parity (``tests/test_label_pass_lifecycle.py``): the corpus is the
authority for the reason grammar, this is the code that runs in production.

Kept import-light on purpose (no app/DB imports) so it is safe to import from
the admin route and any task. The route supplies a plain ``row`` dict built from
the authoritative market lifecycle; the *reason grammar* — never title/LLM/news —
decides retirement, per the issue's "never infer staleness from prose alone".
"""

from __future__ import annotations

from typing import Any

# Terminal market lifecycle states — a proposal on any of these can no longer be
# a current, labelable steer. Mirrors the C143 oracle's TERMINAL set.
TERMINAL_STATUSES = {"resolved", "closed", "settled", "finalized"}

# `features` JSONB keys that carry the proposal's generation identity, tracked
# SEPARATELY from ``created_at`` (#1542 Item 5). ``created_at`` was the freshness
# clock AND was mutated by the daily evaluator, so an old candidate re-seen by
# the evaluator looked freshly generated. Generation is stamped once at creation
# and is NOT bumped when the evaluator merely re-sees the same candidate.
GENERATION_KEY = "generation"
EVIDENCE_GENERATION_KEY = "evidence_generation"


def read_generation(features: dict[str, Any] | None) -> Any:
    """The proposal's generation token (None for legacy rows)."""
    return (features or {}).get(GENERATION_KEY)


def read_evidence_generation(features: dict[str, Any] | None) -> Any:
    """The generation the CURRENT stored evidence corresponds to.

    Defaults to the proposal generation, so a well-formed row (evidence stamped
    with its generation) never trips ``generation_mismatch``; a row whose age was
    refreshed without re-deriving evidence would diverge and be retired.
    """
    f = features or {}
    return f.get(EVIDENCE_GENERATION_KEY, f.get(GENERATION_KEY))

# The bounded verdict magnitudes the real route applies (kept for the delta the
# oracle checks; the route itself clamps via eval_promote.EVAL_ADJ_CAP).
_ACCEPT_DELTA = 8
_REJECT_DELTA = -18
_ADJ_CAP = 20


def classify_pending(row: dict[str, Any]) -> tuple[str, str]:
    """Return ``(state, reason)`` for a proposal in the pending queue.

    ``state`` is one of ``actionable`` / ``retired`` / ``quarantine``. Only
    ``actionable`` proposals may be shown as labelable or accept a verdict.
    Authority-unavailable is ``quarantine`` (fail-closed, never ``valid``);
    title/LLM-only staleness is ``quarantine`` (prose is not retirement
    authority). Everything else with a hard authoritative signal is ``retired``.

    Byte-equivalent to ``scripts/evals/label_pass_lifecycle_contract.pending_decision``.
    """
    if row.get("authority_available") is False:
        return "quarantine", "authority_unavailable"
    if row.get("superseded"):
        return "retired", "proposal_superseded"
    if row.get("item_type") == "email" and not row.get("canonical_market_id"):
        return "retired", "canonical_identity_missing"
    if not row.get("market_exists"):
        return "retired", "market_missing"
    if row.get("canonical_market_id") != row.get("market_id"):
        return "retired", "canonical_identity_mismatch"
    if row.get("status") in TERMINAL_STATUSES:
        return "retired", "lifecycle_terminal"
    if row.get("resolution_date_past"):
        return "retired", "lifecycle_past"
    if row.get("authoritative_overtaken"):
        return "retired", "premise_overtaken"
    if row.get("title_or_llm_only_stale"):
        return "quarantine", "non_authoritative_staleness"
    if row.get("evidence_generation") != row.get("proposal_generation"):
        return "retired", "generation_mismatch"
    return "actionable", "current"


def classify_post(row: dict[str, Any]) -> dict[str, Any]:
    """Return the verdict-time decision for a proposal.

    Recomputes the pending state (a proposal can go stale between GET and POST),
    then layers the POST-only guards: a generation that advanced since the client
    read it (``posted_generation_mismatch``), a duplicate keypress, or a failed
    write transaction. A non-``actionable`` state yields a typed ``conflict``
    with ``writes: 0`` — no ranking/training row is created.

    Byte-equivalent to ``scripts/evals/label_pass_lifecycle_contract.post_decision``.
    """
    state, reason = classify_pending(row)
    if row.get("posted_generation") != row.get("proposal_generation"):
        state, reason = "retired", "posted_generation_mismatch"
    if row.get("duplicate_post"):
        return {"status": "conflict", "reason": "duplicate_verdict", "writes": 0, "delta": 0}
    if row.get("transaction_ok") is False:
        return {"status": "error", "reason": "transaction_failed", "writes": 0, "delta": 0}
    if state != "actionable":
        return {"status": "conflict", "reason": reason, "writes": 0, "delta": 0}
    verdict = row.get("verdict")
    kill = row.get("kill_switch_enabled")
    if verdict == "accept" and kill:
        delta = _ACCEPT_DELTA
    elif verdict == "reject" and kill:
        delta = _REJECT_DELTA
    else:
        delta = 0
    return {
        "status": "written",
        "reason": "current",
        "writes": 1,
        "delta": max(-_ADJ_CAP, min(_ADJ_CAP, delta)),
    }
