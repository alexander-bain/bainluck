"""A market may become ``resolved`` only with a winner or a NAMED reason. Pure.

CAL-P086A, closing `C-WINNER-WRITER-1`'s [P0] "two live producers declare
resolution without proving a winner".

The defect, in one sentence: **``status='resolved'`` was a state transition that
asserted nothing.** Two producers wrote it — the generic clock task in
``tasks/futures.py`` when ``resolution_date`` elapsed, and the Polymarket
closed-status sync in ``tasks/polymarket.py`` when Gamma reported an event
closed — and neither required a venue result, a terminal price, exactly one
winner, or an explicit void. Meanwhile ``FuturesOutcome.is_winner`` defaults to
a **non-null ``False``**, so the ordinary outcome insert leaves an ungraded
field looking exactly like a field where everybody lost.

Why that combination is expensive rather than merely untidy: ``resolved`` is the
calibration census DENOMINATOR and the entry gate to every winner backfill. So
each of these writes enlarged the denominator while contributing nothing to the
numerator, and did it silently. 305,660 markets are missing a winner; Polymarket
supplies 92.79% of the July→August increase; every task involved reported
success throughout.

This is gotcha #53 with a state machine standing in for the API. *"This market
resolved and X won"* and *"this market's date passed and we have no idea who
won"* are different facts, and they were writing the same byte. An empty 200 and
a real empty look the same; so do these.

**What the gate does, and what it deliberately does not do.** It does not forbid
resolving without a winner — sometimes that is the honest state, and refusing it
would strand markets in ``open`` and break the downstream pipelines that key on
``resolved`` (gotcha #33). It forbids resolving without SAYING SO. Every gated
write records, in ``market_metadata.resolution_gate``, either the winner proof
or one of an **enumerated** set of reasons, so the population becomes
addressable by a query instead of inferable from a silence.

The enumeration is the load-bearing part. If any string counted as a reason the
gate would be satisfied by ``"ok"`` and would measure nothing — an escape hatch
that accepts anything is a rubber stamp, and a control that cannot fail is not a
control (ruling 050). An unrecognised reason is REFUSED.

Not decided here, and flagged for Alex rather than assumed: codex's stronger
fix-sketch, *"stop the generic clock task from resolving prediction-market
sources"*. That is a coverage change to a live producer, and the honest order is
to make the class countable first and rule on it second — on numbers, not on an
estimate.

Pure: no DB, no Redis, no network, no clock injection beyond an optional caller
timestamp. Safe to import from tasks and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

#: Where the record lives inside ``futures_markets.market_metadata``.
GATE_KEY = "resolution_gate"

#: The write carried a complete, authoritative winner/loser set.
PROOF_WINNER = "winner"

#: The write carried no winner, and said why — in the enumeration below.
PROOF_NAMED_REASON = "named_reason"

# ---------------------------------------------------------------------------
# The enumeration. Adding a member is a deliberate act: it declares a new,
# countable class of resolved-without-a-winner, and somebody should be able to
# say what would drain it.
# ---------------------------------------------------------------------------

#: The generic clock task: ``resolution_date`` passed and no venue was asked.
#: This is the single largest source of ungraded ``resolved`` rows.
REASON_RESOLUTION_DATE_ELAPSED = "resolution_date_elapsed_no_venue_result"

#: Polymarket reported the event closed, but the price envelope is nonterminal
#: (codex's 0.60/0.40 specimen), so no winner can be read from it honestly.
REASON_CLOSED_WITHOUT_TERMINAL_PRICE = "closed_without_terminal_price"

#: The venue settled the market to nobody — a void, cancellation or refund.
#: Distinct from "we do not know": this one is finished and needs no drain.
REASON_VENUE_VOID = "venue_void"

ALLOWED_REASONS = frozenset(
    {
        REASON_RESOLUTION_DATE_ELAPSED,
        REASON_CLOSED_WITHOUT_TERMINAL_PRICE,
        REASON_VENUE_VOID,
    }
)


@dataclass(frozen=True)
class ResolvedWriteVerdict:
    """Whether a ``status='resolved'`` write is permitted, and on what basis."""

    permitted: bool
    proof_kind: str | None = None
    reason: str | None = None


def classify_resolved_write(
    *, has_winner_proof: bool, named_reason: str | None = None
) -> ResolvedWriteVerdict:
    """Decide whether this write may set ``status='resolved'``.

    ``has_winner_proof`` means a complete winner/loser set is being written in
    the SAME transaction — not that one might arrive later from some other rail.
    A promise is not a proof; that distinction is the whole finding.
    """
    if has_winner_proof:
        return ResolvedWriteVerdict(permitted=True, proof_kind=PROOF_WINNER)
    reason = (named_reason or "").strip()
    if reason in ALLOWED_REASONS:
        return ResolvedWriteVerdict(
            permitted=True, proof_kind=PROOF_NAMED_REASON, reason=reason
        )
    return ResolvedWriteVerdict(permitted=False)


def gate_stamp(
    *,
    task: str,
    reason: str | None = None,
    proof_kind: str | None = None,
    at: datetime | None = None,
) -> dict:
    """Build the ``market_metadata`` fragment recording why this row resolved.

    Merged into the column with ``||`` so it never clobbers a sibling key. The
    stamp names its writer as well as its reason, because the next person to
    read a five-figure count of these will immediately want to know which
    producer made them.
    """
    if proof_kind == PROOF_WINNER:
        body = {"proof_kind": PROOF_WINNER}
    else:
        verdict = classify_resolved_write(
            has_winner_proof=False, named_reason=reason
        )
        if not verdict.permitted:
            raise ValueError(
                f"{reason!r} is not an enumerated resolution-gate reason; "
                f"add it to ALLOWED_REASONS deliberately or write a winner"
            )
        body = {"proof_kind": PROOF_NAMED_REASON, "reason": verdict.reason}
    body["task"] = task
    body["at"] = (at or datetime.now(timezone.utc)).isoformat()
    return {GATE_KEY: body}
