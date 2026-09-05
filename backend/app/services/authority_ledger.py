"""Durable home for the StatPal flip gate's daily rows (#2867, D50).

The storage half of `app.utils.authority_streak`, and the only part of it that
touches a database. One `durable_state_snapshots` row per sport, holding that
sport's bounded day history and its computed streak.

WHY THIS SUBSTRATE
══════════════════
The agreement row is banked in Redis task metrics, which is where the endpoint
reads it from — correct for "the last pass", useless for "the last seven days":
that instance is a shared 100MB allkeys-lru cache, so the key's survival is a
function of what else the app is doing. `durable_state_snapshots` is the
already-provisioned cross-process durable store (Queue 298 / #1512) and its
generation-guarded single-statement replace is exactly the write this needs.

Its docstring says it is *not a history table*, and this respects that: ONE row
per identity, replaced atomically, holding the latest generation of that sport's
ledger. The history lives INSIDE one bounded payload
(`LEDGER_RETAINED_DAYS` entries, ~9KB) — it is not a row per day.

THE ONE IRREVERSIBLE MISTAKE, AND THE RULE THAT PREVENTS IT
═══════════════════════════════════════════════════════════
This is a read-modify-write of the only copy of evidence that cannot be
regenerated: nobody can go back and ask StatPal what it served last Tuesday. So
a read that is anything other than `ok` or `missing` **does not write**:

  * `missing` — genuinely never published. Start a ledger. Safe.
  * `ok` — fold into what is there. Safe.
  * `unavailable` / checksum / version / completeness / age — DO NOT WRITE. We
    do not know what is in the row, and folding onto an empty ledger would
    replace real history with one day and reset a real streak to 1. The pass
    reports `UNRECORDED` with the reason and moves on.

The distinction is gotcha #53 in its most expensive form: "I read nothing" and
"there is nothing" are different answers, and only one of them licenses a write.

AND THE SECOND ONE, WHICH IS NOT THE SAME (CERT-952)
════════════════════════════════════════════════════
A read-modify-write also loses races. `publish_snapshot` answers `superseded`
when a newer generation already sits there, and for its original callers that IS
success: every writer of a calibration bank is producing the same artifact, so
the freshest copy winning is the desired outcome.

**A ledger is not that artifact.** Each writer produces a DIFFERENT thing — its
own day, folded onto whatever it happened to read — so `superseded` means our
fold was computed on a copy that is no longer true. Returning it anyway is how a
losing pass publishes `meets_flip_gate: true` while the durable winner reads
`BELOW`, and this function's return value is what the endpoint publishes.

So a lost race is retried, not reported: re-read, re-fold onto the winner, write
again (`LEDGER_FOLD_ATTEMPTS`). A retry's generation is bumped past what it read
— safe precisely because it re-folded, so the write CONTAINS the winner's days
— while the FIRST attempt is never bumped, because that is what lets the guard
detect the race at all. If every attempt loses, the winner's own count is
published when it covers this pass's day and `UNRECORDED` when it does not. The
one thing that never happens is a `recorded` count no stored row backs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.authority_streak import (
    LEDGER_SCHEMA_VERSION,
    empty_ledger,
    fold_day,
    utc_day,
)
from app.utils.durable_state import DurableEnvelope, generation_for

logger = logging.getLogger(__name__)

#: A ledger is SUPPOSED to be old. `read_snapshot`'s default age bound is seven
#: days, which would type a perfectly good ledger as `stale` after a week's
#: stamper outage and — under the rule above — stop us recording anything ever
#: again. Age is not a trust question here: whether a gap matters is decided by
#: the fold, which walks calendar days and stops on a missing one by name.
LEDGER_MAX_AGE_S = 400 * 24 * 3600

#: Reported on the row when the day could not be persisted. Not an exception and
#: not silence: the agreement row says the streak is unrecorded and why, so a
#: reader never mistakes "we failed to write it" for "the streak is 0".
STREAK_UNRECORDED = "UNRECORDED"

#: `publish_snapshot`'s word for "a newer generation is already there".
#:
#: For a snapshot whose every writer produces the SAME artifact — a calibration
#: bank, a sentinel scorecard — that is success: durability is satisfied and the
#: freshest copy won. **A ledger is not that artifact.** Each writer produces a
#: DIFFERENT thing (its own day, folded onto whatever it happened to read), so
#: losing the race does not mean somebody else stored our day — it means our
#: fold was computed on a stale copy and must be thrown away, not published.
#: CERT-952 reproduced the consequence: a superseded writer returning
#: `meets_flip_gate: true` while the durable winner read BELOW.
SUPERSEDED = "superseded"

#: How many times a pass will re-read and re-fold after losing the race. Four is
#: chosen against the real contention: the four stampers write four DIFFERENT
#: identities, so the only writers who can collide here are two passes of the
#: same sport overlapping — a retry or a beat lapping itself — and a fifth
#: attempt would say more about a wedged database than about contention.
LEDGER_FOLD_ATTEMPTS = 4


def ledger_identity(sport_key: str) -> str:
    """Durable identity for one sport's ledger. Stable, and namespaced so it
    cannot collide with a calibration bank or a sentinel scorecard."""
    return f"authority-agreement-ledger:{sport_key}"


def _unrecorded(reason: str, *, detail: Optional[str] = None) -> dict[str, Any]:
    return {
        "state": STREAK_UNRECORDED,
        "reason": reason,
        "detail": detail,
        "note": (
            "This day was NOT added to the durable ledger, so it does not count "
            "towards D50's seven. The number is unknown, not zero."
        ),
    }


async def record_agreement_day(
    row: dict[str, Any],
    *,
    at: datetime,
    apply: bool = True,
) -> dict[str, Any]:
    """Fold one agreement row into its sport's durable ledger; return the row.

    Attaches `row["streak"]` either way, so the agreement endpoint publishes the
    seven-day count beside the numbers it was computed from without the route
    having to know this module exists.

    `apply=False` (a dry run) still reads and still folds — you want to see what
    the day WOULD score — but never writes. Persisting from a dry run would let
    a rehearsal advance the real gate.

    Never raises. A stamper pass that read both StatPal endpoints and wrote its
    anchors has succeeded; failing it because a bookkeeping write did not land
    would trade a real ship for a receipt.
    """
    sport_key = row.get("sport_key") or ""
    identity = ledger_identity(sport_key)

    for attempt in range(1, LEDGER_FOLD_ATTEMPTS + 1):
        read = await _read_ledger(identity)
        if read.get("refuse"):
            row["streak"] = read["refuse"]
            return row

        folded = fold_day(read["ledger"], row, at=at)

        if not apply:
            streak = dict(folded.get("streak") or {})
            streak["dry_run"] = True
            streak["note_dry_run"] = (
                "computed but NOT persisted: this pass ran with apply=False."
            )
            row["streak"] = streak
            return row

        published = await _publish_ledger(
            identity,
            folded,
            sport_key=sport_key,
            at=at,
            stored_generation=read["generation"],
            is_retry=attempt > 1,
        )
        status = published.get("status")

        if status == "ok":
            streak = dict(folded.get("streak") or {})
            streak["recorded"] = True
            streak["publish_status"] = status
            streak["attempts"] = attempt
            row["streak"] = streak
            return row

        if status == SUPERSEDED:
            # We LOST the generation race. Our fold was computed on a ledger
            # that is no longer the truth, so it may not be published as one —
            # this is the whole of CERT-952: a losing writer that returns its
            # own stale fold can publish `meets_flip_gate: true` off a copy the
            # durable winner already contradicts. Re-read and re-fold onto
            # whatever won; do not keep what we computed.
            logger.info(
                "authority ledger fold superseded for %s (attempt %s/%s), refolding",
                identity,
                attempt,
                LEDGER_FOLD_ATTEMPTS,
            )
            continue

        row["streak"] = _unrecorded(
            f"durable-publish-{status}",
            detail=str(published.get("error") or "")[:200] or None,
        )
        return row

    # Out of attempts. Something else is writing this identity faster than we
    # can fold onto it. Publish the WINNER's count if it already covers this
    # pass's day — a true number from the durable row beats both a stale local
    # fold and a bare "unknown" — and otherwise say nothing was recorded.
    return _publish_the_winners_count(row, await _read_ledger(identity), at=at)


async def _read_ledger(identity: str) -> dict[str, Any]:
    """Read the stored ledger, or say why it may not be folded onto.

    Returns `{"ledger", "generation"}` when a fold is allowed, or
    `{"refuse": <streak block>}` when it is not.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            identity,
            expected_version=LEDGER_SCHEMA_VERSION,
            max_age_s=LEDGER_MAX_AGE_S,
        )
    # `read_snapshot_standalone` already classifies rather than raises; this arm
    # is for the case where it could not even open a session. (This comment is
    # also load bearing for `scan_mutation_residue.py` Pass B — without a line
    # here, the closing paren above plus the bare `noqa` below reproduce
    # `typeahead_outcome_arm_mutations:M2-NO-LIMIT`'s replacement literal
    # verbatim and this file reads as mutation residue. Do not delete it —
    # `repair_polymarket_leg_label.py` and `matcher_pass_runs.py` carry the same
    # note for the same reason.)
    except Exception as exc:  # noqa: BLE001 — classified, never swallowed
        logger.warning("authority ledger read failed for %s: %s", identity, exc)
        return {"refuse": _unrecorded("read-raised", detail=str(exc)[:200])}

    sport_key = identity.split(":", 1)[-1]

    if read.ok and read.envelope is not None:
        stored = read.envelope.payload
        if not isinstance(stored, dict):
            return {
                "refuse": _unrecorded(
                    "stored-payload-not-a-ledger",
                    detail=f"durable payload is {type(stored).__name__}, not a mapping",
                )
            }
        return {"ledger": stored, "generation": read.envelope.generation}

    if read.missing:
        return {"ledger": empty_ledger(sport_key), "generation": None}

    # The row exists but we could not trust what we read. Writing now would
    # overwrite history we cannot see with a ledger of one day.
    return {
        "refuse": _unrecorded(
            f"durable-read-{read.status}",
            detail=read.error
            or "the stored ledger could not be trusted; "
            "nothing was written, so nothing was lost",
        )
    }


async def _publish_ledger(
    identity: str,
    folded: dict[str, Any],
    *,
    sport_key: str,
    at: datetime,
    stored_generation: Optional[int],
    is_retry: bool,
) -> dict[str, Any]:
    """Publish one fold, at a generation that can actually win a RETRY.

    Generation is epoch-ms of the pass's own stamp, and **on the first attempt
    it stays that way** — that is what lets the substrate's
    `generation <= EXCLUDED.generation` guard do its job and tell us we lost.
    Bumping on the first attempt would make every writer win, which is not a
    fix for a lost race, it is the removal of the race detector.

    On a RETRY the bump is required and safe. Required, because the writer that
    beat us holds a later generation and re-sending ours would be refused
    forever — the loop would spin and the day would be lost. Safe, because a
    retry has already re-read and re-folded onto the winner's payload, so what
    we are about to write CONTAINS the winner's days rather than replacing them.

    It also decouples two things one timestamp was doing at once: WHICH WRITE IS
    NEWEST (the generation, monotonic per attempt) and WHICH DAY THE PASS
    BELONGS TO (`at`, inside the payload, untouched).
    """
    from app.services.durable_snapshots import publish_snapshot_standalone

    stamped = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    generation = generation_for(stamped)
    if is_retry and stored_generation is not None and generation <= stored_generation:
        generation = int(stored_generation) + 1

    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=LEDGER_SCHEMA_VERSION,
        payload=folded,
        generated_at=stamped,
        generation=generation,
        source=f"authority-shadow-stamper:{sport_key}",
    )
    try:
        return await publish_snapshot_standalone(envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("authority ledger publish raised for %s: %s", identity, exc)
        return {"status": "publish-raised", "error": str(exc)[:200]}


def _publish_the_winners_count(
    row: dict[str, Any], read: dict[str, Any], *, at: datetime
) -> dict[str, Any]:
    """Last resort after losing every retry: report the DURABLE row's streak.

    Only if the winner's ledger already covers this pass's day — otherwise the
    day genuinely did not land and saying anything else would be the stale-fold
    bug wearing a different hat.
    """
    ledger = read.get("ledger") if not read.get("refuse") else None
    day = utc_day(at)
    covered = bool(
        isinstance(ledger, dict)
        and any(
            isinstance(d, dict) and d.get("day") == day
            for d in ledger.get("days") or []
        )
    )
    if covered:
        streak = dict((ledger or {}).get("streak") or {})
        streak["recorded"] = True
        streak["publish_status"] = SUPERSEDED
        streak["attempts"] = LEDGER_FOLD_ATTEMPTS
        streak["note_superseded"] = (
            "this pass lost every generation race, so the count published here is "
            "the DURABLE winner's, not this pass's fold. The winner already covers "
            f"{day}."
        )
        row["streak"] = streak
        return row

    row["streak"] = _unrecorded(
        "lost-every-generation-race",
        detail=(
            f"{LEDGER_FOLD_ATTEMPTS} folds were superseded by a concurrent writer and "
            f"the durable winner does not cover {day}. Nothing was written and no "
            "count from this pass may be trusted."
        ),
    )
    return row
