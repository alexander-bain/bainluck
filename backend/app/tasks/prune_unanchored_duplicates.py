"""#2020 — the bounded delete rail for the unanchored-duplicate surplus.

WHY THIS EXISTS RATHER THAN A LIST OF IDS
------------------------------------------

Alex authorized a Tranche A cleanup on 2026-08-20 with an explicit safety device:
*a per-batch dry-run whose census must match, stop-on-mismatch.* Queue 382 went to
execute it and found **there was nothing to run the dry-run against**. The only
capable endpoint, ``DELETE /api/admin/events/delete-duplicates``, takes a
comma-separated id list and has no ``apply=false``, no census and no cap — so the
authorized shape would have been ~500 unverifiable destructive calls, and the queue
stopped rather than improvise one.

This module is that missing device. Five properties, each of which was a named gap:

1. **``apply=False`` is the default.** The destructive path is opt-in at the call
   site, not merely gated by a token the caller might happen to hold.
2. **The census is in the response**, on both paths, computed from the same
   predicate the delete is bound to — so the number an operator reads is the number
   the delete acts on, not a number from a different query written at a different
   time. (Q381's 240-row discrepancy was exactly that: a total and a per-sport
   breakdown taken minutes apart while the population grew at ~1,580/h.)
3. **A per-call cap.** No call can delete more than ``max_delete`` rows, whatever
   the census says.
4. **Explicit bounded binding.** The DELETE is bound to an id list materialised in
   this transaction and re-verified row by row immediately before it runs. There is
   no ``WHERE`` predicate on the destructive statement that could widen under it.
5. **Stop-on-mismatch is mechanical.** ``apply`` refuses unless the observed
   deletable count falls inside a caller-supplied band. The caller states what it
   expects to see; disagreeing with production aborts the call. A human promise to
   check the census is not the same object as a refusal.

THE PARTITION, AND WHY THE KEEPER IS THE LINKED COPY
-----------------------------------------------------

A "fixture" is ``(home_team_name, away_team_name, commence_time)`` — exact time. That
key reproduces the authorized plan's fixture partition exactly (2,565 / 35 / 103).

Fixtures are split by how many of their copies hold a futures-market link:

* ``linked_copies == 1`` — **Tranche A.** One copy carries every Kalshi market for
  the game; the rest carry nothing. The linked copy is the keeper because it is the
  one the product actually reads, and deleting the others discards no market data.
* ``linked_copies == 0`` — **Tranche B.** No copy is distinguishable by link, so the
  keeper would have to be chosen on some other evidence. Not this rail's decision.
* ``linked_copies >= 2`` — **Tranche C.** More than one copy holds markets, so a
  delete would orphan real links. Not this rail's decision.

The rail takes ``linked_copies`` as a parameter and will only ever *delete* unlinked
copies. For any partition where the keeper is not uniquely determined by the link,
the deletable set is empty by construction — B and C cannot be pruned by this rail
even if someone passes their selector, and the tests assert that.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

UNANCHORED_TAG = "provenance:unanchored"

#: Hard ceiling on a single call, above the default and below anything that could
#: be mistaken for "just run it once". ~61K rows is ~31 calls at the default.
MAX_DELETE_CEILING = 5000
DEFAULT_MAX_DELETE = 2000

def _fk_tables() -> tuple[str, ...]:
    """Tables carrying ``event_id``.

    Imported from the merge rail rather than restated, because a table in one list
    and not the other is a silent orphan — the same drift the merge invariant exists
    to prevent one layer up.
    """
    from app.tasks.sports import _EVENT_FK_TABLES  # noqa: PLC0415

    return _EVENT_FK_TABLES


class PruneRefused(Exception):
    """The rail declined to delete. Never raised after a destructive statement."""


# The census and the batch come from ONE common table expression, so the number
# reported and the rows acted on cannot drift apart. ``linked`` is computed per row;
# ``linked_copies`` per fixture.
_PARTITION_CTE = """
    WITH tagged AS (
        SELECT e.id,
               e.home_team_name,
               e.away_team_name,
               e.commence_time,
               EXISTS (
                   SELECT 1 FROM futures_markets fm WHERE fm.event_id = e.id
               ) AS linked
          FROM events e
         WHERE e.sport_id = :sport_id
           AND e.event_tags @> CAST(:tag AS jsonb)
    ),
    fixtures AS (
        SELECT home_team_name, away_team_name, commence_time,
               COUNT(*) AS copies,
               COUNT(*) FILTER (WHERE linked) AS linked_copies
          FROM tagged
         GROUP BY 1, 2, 3
    ),
    partition_fixtures AS (
        SELECT * FROM fixtures WHERE linked_copies = :linked_copies
    )
"""

_CENSUS_SQL = text(
    _PARTITION_CTE
    + """
    SELECT COUNT(*)                        AS fixtures,
           COALESCE(SUM(copies), 0)        AS total_rows,
           COALESCE(SUM(linked_copies), 0) AS keepers,
           COALESCE(SUM(copies - linked_copies), 0) AS deletable
      FROM partition_fixtures
    """
)

# The batch. Deterministic ordering (oldest fixture first, then id) so two callers
# reading the same census see the same batch, and a resumed run continues where the
# last one stopped rather than re-sampling the population.
_BATCH_SQL = text(
    _PARTITION_CTE
    + """
    SELECT t.id
      FROM tagged t
      JOIN partition_fixtures p
        ON p.home_team_name = t.home_team_name
       AND p.away_team_name = t.away_team_name
       AND p.commence_time  = t.commence_time
     WHERE t.linked = false
     ORDER BY t.commence_time ASC, t.id ASC
     LIMIT :cap
    """
)

# The in-transaction re-verification. Locks the candidate rows and re-derives every
# property the batch was selected on, from the row itself. A row that fails any of
# them is not deleted and the whole batch is refused.
_VERIFY_SQL = text(
    """
    SELECT e.id,
           (e.sport_id = :sport_id)                          AS right_sport,
           (e.event_tags @> CAST(:tag AS jsonb))             AS tagged,
           NOT EXISTS (
               SELECT 1 FROM futures_markets fm WHERE fm.event_id = e.id
           )                                                 AS unlinked,
           EXISTS (
               SELECT 1
                 FROM events k
                 JOIN futures_markets fm ON fm.event_id = k.id
                WHERE k.id <> e.id
                  AND k.sport_id       = e.sport_id
                  AND k.home_team_name = e.home_team_name
                  AND k.away_team_name = e.away_team_name
                  AND k.commence_time  = e.commence_time
           )                                                 AS keeper_exists
      FROM events e
     WHERE e.id = ANY(:ids)
       FOR UPDATE
    """
)


async def census(session, *, sport_id: int, linked_copies: int) -> dict[str, int]:
    """Count the partition. Pure read — safe to call on any path."""
    row = (await session.execute(
        _CENSUS_SQL,
        {"sport_id": sport_id, "tag": f'["{UNANCHORED_TAG}"]',
         "linked_copies": linked_copies},
    )).mappings().one()
    return {
        "fixtures": int(row["fixtures"] or 0),
        "total_rows": int(row["total_rows"] or 0),
        "keepers": int(row["keepers"] or 0),
        "deletable": int(row["deletable"] or 0),
    }


async def _verify_batch(session, *, ids: list[int], sport_id: int) -> None:
    """Re-derive every selection property from the locked rows, or refuse.

    The batch query is already correct. This runs anyway, because the batch query
    proves the *candidate set* was chosen correctly and this proves the *rows in
    hand* are still safe to destroy — the two are different claims once anything
    else can write to ``events`` between them. Same redundancy, same reason, as
    ``event_absorption_guard.assert_absorbable_now``.
    """
    rows = (await session.execute(
        _VERIFY_SQL,
        {"ids": ids, "sport_id": sport_id, "tag": f'["{UNANCHORED_TAG}"]'},
    )).mappings().all()

    seen = {r["id"] for r in rows}
    missing = [i for i in ids if i not in seen]
    if missing:
        raise PruneRefused(
            f"{len(missing)} candidate row(s) vanished between selection and lock: "
            f"{missing[:10]}"
        )

    for r in rows:
        for prop in ("right_sport", "tagged", "unlinked", "keeper_exists"):
            if not r[prop]:
                raise PruneRefused(
                    f"event {r['id']} failed re-verification on '{prop}' — batch "
                    "refused, nothing deleted"
                )


async def prune(
    session,
    *,
    sport_id: int,
    linked_copies: int = 1,
    apply: bool = False,
    max_delete: int = DEFAULT_MAX_DELETE,
    expected_min: int | None = None,
    expected_max: int | None = None,
) -> dict[str, Any]:
    """Census the partition, and on ``apply`` delete at most ``max_delete`` surplus rows.

    Returns the census on every path. ``apply=True`` additionally requires a band
    (``expected_min``/``expected_max``) and refuses when the live deletable count
    falls outside it — that refusal IS the stop-on-mismatch, and it happens before
    any statement that writes.
    """
    if max_delete < 1 or max_delete > MAX_DELETE_CEILING:
        raise PruneRefused(
            f"max_delete must be 1..{MAX_DELETE_CEILING}; got {max_delete}"
        )

    counts = await census(session, sport_id=sport_id, linked_copies=linked_copies)

    result: dict[str, Any] = {
        "rail": "prune_unanchored_duplicates",
        "issue": "#2020",
        "sport_id": sport_id,
        "linked_copies": linked_copies,
        "keeper_rule": (
            "the futures-linked copy" if linked_copies == 1
            else "UNDETERMINED — this rail only prunes partitions with exactly one "
                 "linked copy, so nothing is deletable here"
        ),
        "apply": apply,
        "max_delete": max_delete,
        "census": counts,
        "expected_band": [expected_min, expected_max],
    }

    # A partition whose keeper is not uniquely determined by the link is not this
    # rail's to prune. Tranches B and C reach here and get an empty batch, by
    # construction rather than by the caller remembering not to ask.
    if linked_copies != 1:
        return {
            **result,
            "batch": [],
            "deleted": 0,
            "terminal": "refused",
            "reason": (
                f"linked_copies={linked_copies}: the keeper is not determined by the "
                "futures link, so this rail has no keeper rule for it"
            ),
        }

    if apply:
        if expected_min is None or expected_max is None:
            return {
                **result, "batch": [], "deleted": 0, "terminal": "refused",
                "reason": "apply requires expected_min and expected_max — the band "
                          "is what makes stop-on-mismatch mechanical",
            }
        if not (expected_min <= counts["deletable"] <= expected_max):
            return {
                **result, "batch": [], "deleted": 0, "terminal": "refused",
                "reason": (
                    f"CENSUS MISMATCH: deletable={counts['deletable']} is outside the "
                    f"authorized band [{expected_min}, {expected_max}] — nothing "
                    "deleted. Re-authorize against the live number or investigate "
                    "the drift before retrying."
                ),
            }

    batch = [
        int(r[0]) for r in (await session.execute(
            _BATCH_SQL,
            {"sport_id": sport_id, "tag": f'["{UNANCHORED_TAG}"]',
             "linked_copies": linked_copies, "cap": int(max_delete)},
        )).all()
    ]

    if not batch:
        return {
            **result, "batch": [], "deleted": 0, "terminal": "no_work",
            "reason": "no unlinked surplus rows in this partition",
        }

    # The dry run runs the apply path's guard query TOO, and this is the point of
    # it. A dry run that exercises a different set of statements than the apply is
    # not a rehearsal — it is a second, easier query wearing the apply's name, and
    # the first thing the operator would learn about a broken `_VERIFY_SQL` is a 500
    # on the first destructive call. The locks it takes are released by the caller's
    # rollback on this path.
    verified = True
    verify_refusal: str | None = None
    try:
        await _verify_batch(session, ids=batch, sport_id=sport_id)
    except PruneRefused as exc:
        verified = False
        verify_refusal = str(exc)
        if apply:
            raise

    if not apply:
        return {
            **result,
            "batch": batch,
            "batch_size": len(batch),
            "deleted": 0,
            "verified": verified,
            "verify_refusal": verify_refusal,
            "terminal": "dry_run" if verified else "refused",
            "reason": (
                verify_refusal if not verified else
                f"DRY RUN — would delete {len(batch)} of {counts['deletable']} "
                f"deletable rows; {counts['deletable'] - len(batch)} would remain "
                "after this batch"
            ),
        }

    # ── destructive from here, and not before ────────────────────────────────

    for table in _fk_tables():
        await session.execute(
            text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"),
            {"ids": batch},
        )
    await session.execute(
        text("UPDATE user_pins SET target_id = NULL "
             "WHERE pin_type = 'event' AND target_id = ANY(:ids)"),
        {"ids": batch},
    )
    deleted = (await session.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": batch}
    )).rowcount

    if deleted != len(batch):
        # Bound to an explicit id list, so this cannot happen without something
        # else having deleted the rows concurrently. Say so rather than round it off.
        raise PruneRefused(
            f"deleted {deleted} but the batch held {len(batch)} — rolling back"
        )

    remaining = counts["deletable"] - deleted
    return {
        **result,
        "batch": batch[:50],
        "batch_size": len(batch),
        "deleted": deleted,
        "remaining_deletable": remaining,
        "exhausted": remaining <= 0,
        "terminal": "complete",
        "reason": f"deleted {deleted}; {remaining} deletable rows remain",
    }
