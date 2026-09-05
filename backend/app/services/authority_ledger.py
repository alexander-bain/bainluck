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
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.authority_streak import (
    LEDGER_SCHEMA_VERSION,
    empty_ledger,
    fold_day,
)
from app.utils.durable_state import DurableEnvelope

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
    from app.services.durable_snapshots import (
        publish_snapshot_standalone,
        read_snapshot_standalone,
    )

    sport_key = row.get("sport_key") or ""
    identity = ledger_identity(sport_key)

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
        row["streak"] = _unrecorded("read-raised", detail=str(exc)[:200])
        return row

    if read.ok and read.envelope is not None:
        stored = read.envelope.payload
        if not isinstance(stored, dict):
            row["streak"] = _unrecorded(
                "stored-payload-not-a-ledger",
                detail=f"durable payload is {type(stored).__name__}, not a mapping",
            )
            return row
        ledger = stored
    elif read.missing:
        ledger = empty_ledger(sport_key)
    else:
        # The row exists but we could not trust what we read. Writing now would
        # overwrite history we cannot see with a ledger of one day.
        row["streak"] = _unrecorded(
            f"durable-read-{read.status}",
            detail=read.error
            or "the stored ledger could not be trusted; "
            "nothing was written, so nothing was lost",
        )
        return row

    folded = fold_day(ledger, row, at=at)

    if not apply:
        streak = dict(folded.get("streak") or {})
        streak["dry_run"] = True
        streak["note_dry_run"] = (
            "computed but NOT persisted: this pass ran with apply=False."
        )
        row["streak"] = streak
        return row

    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=LEDGER_SCHEMA_VERSION,
        payload=folded,
        generated_at=at if at.tzinfo else at.replace(tzinfo=timezone.utc),
        source=f"authority-shadow-stamper:{sport_key}",
    )
    try:
        published = await publish_snapshot_standalone(envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("authority ledger publish raised for %s: %s", identity, exc)
        row["streak"] = _unrecorded("publish-raised", detail=str(exc)[:200])
        return row

    status = published.get("status")
    if status not in ("ok", "superseded"):
        row["streak"] = _unrecorded(
            f"durable-publish-{status}",
            detail=str(published.get("error") or "")[:200] or None,
        )
        return row

    streak = dict(folded.get("streak") or {})
    streak["recorded"] = True
    streak["publish_status"] = status
    row["streak"] = streak
    return row
