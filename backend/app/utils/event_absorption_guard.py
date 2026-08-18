"""#1947 — the ruling-048 check that runs INSIDE the delete transaction.

``event_merge_invariant`` is pure: it answers "may these two rows be absorbed?"
about whatever values you hand it. That is the right shape for a predicate and
the wrong shape for a guarantee, because every rail hands it values read
*earlier* — in a SELECT that ran before the branching, the metadata absorb, and
the FK repoint. Between that read and the DELETE there is a gap, and the rails
have been trusting it.

This module closes the gap the only way it can be closed: **re-read both rows
under ``FOR UPDATE`` in the caller's own transaction, and assert on THOSE
values, immediately before the destructive statement.** After it returns, the
rows are locked; nothing can change the answer before the DELETE lands.

## Why this exists as well as the invariant, and not instead of it

Three checks now sit on the same pair, and the redundancy is the design — it is
the same argument R6 made for having both ``shared_provider_id_sql`` and
``assert_mergeable``, extended one step:

1. the SELECT's ``shared_provider_id_sql`` keeps the candidate set honest and cheap;
2. ``assert_mergeable`` proves the row in hand was safe *when it was read*;
3. this proves it is safe *now*, on the row as the database currently holds it,
   with the row locked so the claim survives until the delete.

## What it is really protecting against

Not primarily the race. #1947's finding is that arm A — a shared provider id —
is **not sufficient**: production holds three ``espn_id`` values that join
genuinely different games. The only thing that has ever stopped the drain
deleting one of them is ``ABS(Δcommence) < 21600`` inside one caller's SQL
string. That number is not in the invariant, is absent from the other three
rails, and would vanish from a hand-edit to a 90-line query nobody re-reads.

So the corroboration lives in the invariant now, and this module is what makes
every rail consume it at the moment it matters. **No caller's time window is
the last line of defence any more** — which is the whole ask on #1947.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text

from app.utils.event_merge_invariant import (
    PROVIDER_ID_COLUMNS,
    UnanchoredMergeRefused,
    assert_absorbable,
)

#: Everything the two arms need. Selected explicitly rather than ``SELECT *``
#: so that a column added to ``PROVIDER_ID_COLUMNS`` and not to this list fails
#: the contract test rather than silently weakening the check.
_GUARD_COLUMNS = (
    "id",
    "commence_time",
    "home_team_name",
    "away_team_name",
    "home_team_normalized",
    "away_team_normalized",
    *PROVIDER_ID_COLUMNS,
)

_RELOAD_SQL = sa_text(
    f"SELECT {', '.join(_GUARD_COLUMNS)} FROM events "
    "WHERE id IN (:keep_id, :orphan_id) FOR UPDATE"
)


class AbsorptionRowVanished(UnanchoredMergeRefused):
    """One of the pair is no longer in ``events`` at delete time.

    A refusal, not a shrug. If the orphan is already gone the delete is a no-op
    and nothing is lost; if the KEEPER is gone we were about to delete the
    orphan in favour of a row that does not exist, which destroys the surviving
    copy of the game. Those must not share a code path with "merged fine".

    Subclasses :class:`UnanchoredMergeRefused` so the existing per-pair
    ``except`` in every rail catches it and drains the rest (gotcha #42).
    """


async def assert_absorbable_now(
    session: Any,
    *,
    keep_id: int,
    orphan_id: int,
    context: str,
) -> None:
    """Re-read both rows ``FOR UPDATE`` and assert ruling 048 on what is there.

    Call this in the same transaction as the DELETE, after the candidate SELECT
    and before any destructive statement. Raises a subclass of
    :class:`UnanchoredMergeRefused` on every refusal, so a caller that already
    handles the invariant's refusal handles this too.
    """
    rows = (
        await session.execute(
            _RELOAD_SQL, {"keep_id": keep_id, "orphan_id": orphan_id}
        )
    ).mappings().all()
    by_id = {row["id"]: row for row in rows}

    missing = [i for i in (keep_id, orphan_id) if i not in by_id]
    if missing:
        raise AbsorptionRowVanished(
            f"{context}: refusing to absorb {orphan_id} into {keep_id} — "
            f"event(s) {missing} are no longer in the table at delete time. "
            "The pair moved between the candidate SELECT and the DELETE; "
            "re-derive rather than proceed on a stale read."
        )

    if keep_id == orphan_id:
        raise AbsorptionRowVanished(
            f"{context}: refusing to absorb event {keep_id} into itself — "
            "the caller resolved both sides of the pair to one row."
        )

    assert_absorbable(by_id[keep_id], by_id[orphan_id], context=context)
