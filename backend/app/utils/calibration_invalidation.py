"""When a calibration invalidation has actually been discharged — CAL-P062.

C-CERT-1852-R2 passed four of the five findings on ``-56`` and BLOCKED the
fifth on two false-green paths. Both live in the same seam: the repair writes
rows, then owes the published curve an invalidation, and the code that decided
whether that debt was paid asked the wrong question twice.

**Specimen one — the acknowledgement that proved nothing.** The rail published a
blank main checkpoint and accepted ``status in ("ok", "superseded")`` as proof
it had been cleared. A no-op publisher that returns ``ok`` without persisting
scored ``invalidated``; so did a publisher that returned ``superseded`` because
the invalidation LOST to a newer main checkpoint — the one case where the
banked phases the invalidation exists to discard are demonstrably still there.
The read-identity ledger of that run was ``[staged_futures, staged_futures]``:
the main checkpoint was never looked at. This is gotcha #53 one level up — a
write's own return value is a response shape, not a fact about the store — and
:func:`main_checkpoint_is_invalidation` is the after-read predicate that
replaces it.

**Specimen two — the retry that laundered a failure into success.** The apply
commits its rows BEFORE invalidating. When the invalidation failed, the response
said ``success: false`` correctly — but the obligation died with the response.
A retry of the same plan compare-and-set-drifted on the row it had already
written, built an empty ``written`` set, called the invalidation with no market
ids, got ``nothing_written``, and returned ``success: true``. Two calls, one
committed write, zero invalidations, and a green second answer.
:func:`invalidation_discharged` is the rule that makes ``nothing_written``
success ONLY for a plan proven never to have written, and the obligation
helpers below are what carry the debt across the call boundary so the retry has
something to retry.

Everything here is pure. The durable I/O lives in
``app.tasks.repair_kalshi_fabricated_loss``; the judgment lives here so it can
be driven by a table without a database, and so a future rail can reuse the
same rule rather than re-deriving a subtly different one.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

__all__ = [
    "INVALIDATION_OBLIGATION_SCHEMA",
    "OBLIGATION_DISCHARGED",
    "OBLIGATION_OPEN",
    "REAPPLY_DISCHARGES",
    "RESTORE_DISCHARGES",
    "discharge_obligation",
    "invalidation_discharged",
    "main_checkpoint_is_invalidation",
    "new_obligation",
    "obligation_contains",
    "obligation_is_open",
    "obligation_leg_ids",
    "obligation_market_ids",
    "obligation_plan_hash",
    "obligation_retry_instruction",
]

#: Envelope version for the obligation ledger. Bump when a reader must refuse an
#: older shape rather than guess at it.
INVALIDATION_OBLIGATION_SCHEMA = "calibration-invalidation-obligation/v1"

OBLIGATION_OPEN = "open"
OBLIGATION_DISCHARGED = "discharged"

#: Terminals a main-checkpoint record may carry and still count as invalidated.
#:
#: ``invalidated`` is the record this rail publishes. ``complete`` is admitted
#: only in combination with the zero-banked-phases test below: a build that
#: finished and cleared its checkpoint carries nothing a later run could resume,
#: which is the same fact the invalidation exists to establish. Anything else —
#: ``partial`` above all — is a resumable record and therefore a FAILURE, no
#: matter what the publish call returned.
_INVALIDATING_TERMINALS = frozenset({"invalidated", "complete"})


def main_checkpoint_is_invalidation(payload: Any) -> tuple[bool, str]:
    """Is this READ-BACK main-checkpoint payload an invalidation? ``(ok, why)``.

    The question is deliberately about the record that is in the store NOW, not
    about the call that tried to put one there. ``superseded`` is not consulted
    and cannot be: a superseding record either carries banked phases (in which
    case this returns False, which is the whole point) or it does not (in which
    case it is an equivalent invalidation on its own evidence).

    The test that does the work is **zero banked phase output**. A checkpoint's
    danger is not its name, it is ``phase_outputs`` — the thing a resumed build
    reads instead of recomputing. A record with any banked phase is a record the
    repair's rows would be invisible to.
    """
    if not isinstance(payload, dict):
        return False, "MAIN_CHECKPOINT_PAYLOAD_IS_NOT_A_RECORD"

    completed = payload.get("completed_phases")
    outputs = payload.get("phase_outputs")
    if not isinstance(completed, list) or not isinstance(outputs, dict):
        return False, "MAIN_CHECKPOINT_SHAPE_UNREADABLE"
    if completed or outputs:
        return False, (
            "MAIN_CHECKPOINT_STILL_CARRIES_BANKED_PHASES — "
            f"completed={len(completed)} outputs={len(outputs)}"
        )

    terminal = payload.get("terminal")
    if terminal not in _INVALIDATING_TERMINALS:
        return False, f"MAIN_CHECKPOINT_TERMINAL_IS_{terminal!r}_NOT_AN_INVALIDATION"
    if terminal == "invalidated":
        return True, "MAIN_CHECKPOINT_IS_THE_INVALIDATION_RECORD"
    return True, (
        "MAIN_CHECKPOINT_IS_AN_EQUIVALENT_INVALIDATION — a completed record "
        "carrying zero banked phases has nothing for a resume to read"
    )


# ---------------------------------------------------------------------------
# The obligation — what makes a retry retry the RIGHT thing
# ---------------------------------------------------------------------------


#: What discharges a debt an APPLY created.
REAPPLY_DISCHARGES = "Re-apply this exact plan_hash until this record reads discharged."

#: What discharges a debt a RESTORE created — and it is NOT the apply.
#:
#: CAL-P1009: the two actions move the same rows in opposite directions, so the
#: instruction cannot be shared. A restore's unpaid invalidation retried by
#: re-applying its plan pays the debt by REDOING the repair somebody just chose
#: to undo. The retry that is actually owed is the restore itself: it re-reads
#: this record's market ids and invalidates over them even when it has nothing
#: left to reverse.
RESTORE_DISCHARGES = (
    "Re-run the RESTORE of this exact plan_hash until this record reads "
    "discharged. Do NOT re-apply the plan — that pays the debt by redoing the "
    "repair this restore undid."
)


def new_obligation(
    *,
    plan_hash: str,
    market_ids: Iterable[int],
    leg_ids: Iterable[int],
    owner: str,
    retry_instruction: str = REAPPLY_DISCHARGES,
) -> dict[str, Any]:
    """An OPEN debt, bound to the plan and to the write receipt that created it.

    ``market_ids`` is the union of everything this plan has ever written across
    every call — not this call's ``written`` set. That distinction IS the fix:
    on the retry the rows are already committed, so ``written`` is empty and the
    only surviving record of what must be invalidated is this one.

    ``retry_instruction`` is carried in the record rather than known by the
    reader, because the ledger is ONE slot shared by two writers that move rows
    in opposite directions. A reader that assumed the instruction would tell an
    operator to re-apply a plan whose whole point was that it had been undone.
    """
    return {
        "schema": INVALIDATION_OBLIGATION_SCHEMA,
        "state": OBLIGATION_OPEN,
        "plan_hash": plan_hash,
        "market_ids": sorted({int(m) for m in market_ids}),
        "leg_ids": sorted({int(x) for x in leg_ids}),
        "owner": owner,
        "retry_instruction": retry_instruction,
        "note": (
            "Rows are committed and the calibration generation is NOT proven "
            f"discarded. {retry_instruction}"
        ),
    }


def discharge_obligation(
    obligation: dict[str, Any], *, proof: Any = None
) -> dict[str, Any]:
    """The same record, marked paid, carrying the after-read that paid it."""
    out = dict(obligation)
    out["state"] = OBLIGATION_DISCHARGED
    out["discharge_proof"] = proof
    out["note"] = (
        "The invalidation executed AND proved itself on re-read of both the "
        "staged cursor and the main checkpoint."
    )
    return out


def obligation_is_open(obligation: Any) -> bool:
    """Fail-closed: an unrecognisable record is treated as an OPEN debt.

    An obligation ledger this rail cannot parse is not an absence of debt. The
    only reading that is safe when the shape is wrong is the one that refuses.
    """
    if not isinstance(obligation, dict):
        return False  # nothing there at all — the caller distinguishes missing
    return obligation.get("state") != OBLIGATION_DISCHARGED


def obligation_market_ids(obligation: Any) -> list[int]:
    if not isinstance(obligation, dict):
        return []
    ids = obligation.get("market_ids")
    return sorted({int(m) for m in ids}) if isinstance(ids, list) else []


def obligation_leg_ids(obligation: Any) -> list[int]:
    if not isinstance(obligation, dict):
        return []
    ids = obligation.get("leg_ids")
    return sorted({int(m) for m in ids}) if isinstance(ids, list) else []


def obligation_plan_hash(obligation: Any) -> Optional[str]:
    if not isinstance(obligation, dict):
        return None
    value = obligation.get("plan_hash")
    return value if isinstance(value, str) else None


def obligation_contains(
    raw: Any,
    *,
    plan_hash: str,
    owner: str,
    market_ids: Iterable[int],
    leg_ids: Iterable[int],
) -> tuple[bool, str]:
    """Is THIS call's debt the OPEN record now in the slot? ``(ok, why)``.

    CAL-P1009-R (CERT-1872). A debt is staged as the price of committing rows,
    so the question it has to answer is the same one the applied receipt asks
    one slot over: after the write, is *my* record there?

    The staging call's STATUS cannot answer it. The durable layer answers
    ``superseded`` when a newer generation already sits at the identity, and in
    that case it writes NOTHING — for a plan artifact that still means "a good
    copy exists", which is why ``_save_plan`` accepts it, but for a debt it
    means somebody else's record is in the one slot and mine never landed
    (CERT-1863, the same specimen). So the gate is containment, read back from
    the store, and the status is only ever a note.

    Four things are checked and each is load-bearing. The record must be OPEN —
    a discharged record is not a debt anyone will retry. It must carry this
    plan_hash and this OWNER, because the ledger is one slot shared by two
    writers that move the same rows in opposite directions and the retry
    instruction a reader acts on comes from those fields. And it must cover
    every id this call owes: containment, not equality, because the union may
    legitimately carry an earlier call's ids forward as well.
    """
    if not isinstance(raw, dict):
        return False, "OBLIGATION_PAYLOAD_IS_NOT_A_RECORD"
    if raw.get("schema") != INVALIDATION_OBLIGATION_SCHEMA:
        return False, f"OBLIGATION_SCHEMA_IS_{raw.get('schema')!r}"
    if not obligation_is_open(raw):
        return False, "OBLIGATION_IN_THE_SLOT_IS_ALREADY_DISCHARGED"
    if obligation_plan_hash(raw) != plan_hash:
        return False, f"OBLIGATION_PLAN_HASH_IS_{obligation_plan_hash(raw)!r}"
    if raw.get("owner") != owner:
        return False, f"OBLIGATION_OWNER_IS_{raw.get('owner')!r}"
    missing = sorted({int(m) for m in market_ids} - set(obligation_market_ids(raw)))
    if missing:
        return False, f"OBLIGATION_MISSING_MARKET_IDS:{missing[:10]}"
    missing = sorted({int(x) for x in leg_ids} - set(obligation_leg_ids(raw)))
    if missing:
        return False, f"OBLIGATION_MISSING_LEG_IDS:{missing[:10]}"
    return True, "ok"


def obligation_retry_instruction(obligation: Any) -> str:
    """What the RECORD says pays it — never what the reader assumes.

    A record written before this field existed, or one whose field is the wrong
    shape, falls back to the apply's instruction: that is what every such record
    in the store was in fact created by.
    """
    if isinstance(obligation, dict):
        value = obligation.get("retry_instruction")
        if isinstance(value, str) and value:
            return value
    return REAPPLY_DISCHARGES


# ---------------------------------------------------------------------------
# The success rule
# ---------------------------------------------------------------------------


def invalidation_discharged(
    *,
    status: str,
    wrote_rows: bool,
    drift_count: int,
    prior_obligation_open: bool,
) -> tuple[bool, str]:
    """May this call claim the calibration generation was invalidated?

    The rule the certification asked for, stated once:

    * ``invalidated`` — the invalidation executed and proved itself. Paid.
    * anything other than ``nothing_written`` — not paid, by name.
    * ``nothing_written`` — success **only for a plan proven never to have
      written**. Three separate facts can defeat that proof, and each one is
      named rather than folded into a boolean:

      1. an obligation from an earlier call is still open (the retry specimen —
         this is exactly the state that used to launder into ``success: true``);
      2. this call wrote rows, which contradicts the status outright;
      3. this call saw unresolved concurrent drift. A row that moved under the
         plan may have moved because THIS plan already wrote it, so drift is
         precisely the state in which "never written" is unproven. Refusing
         here is the difference between a plan proven clean and a plan that
         merely looks quiet.
    """
    if status == "invalidated":
        return True, "invalidated — the write proved itself on re-read"
    if status != "nothing_written":
        return False, f"invalidation status is {status!r}, which is not a discharge"
    if prior_obligation_open:
        return False, (
            "an earlier apply of this plan committed rows and its invalidation "
            "never discharged — nothing_written cannot pay that debt"
        )
    if wrote_rows:
        return False, "nothing_written contradicts the legs this call wrote"
    if drift_count:
        return False, (
            f"{drift_count} leg(s) drifted under the plan, so this plan is NOT "
            "proven never to have written"
        )
    return True, "nothing_written on a plan proven never to have written"
