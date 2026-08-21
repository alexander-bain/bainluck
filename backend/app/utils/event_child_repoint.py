"""The MERGE rail's repoint step — the operation ``event_fk_inventory`` refuses to name.

WHY THIS IS A SEPARATE MODULE FROM ``event_fk_inventory``
--------------------------------------------------------

``event_fk_inventory.Disposition`` is deliberately ``Literal["SUBSTANCE", "POINTER"]``
with **no ``TRANSFER``**, and that absence is load-bearing for the PRUNE rail: ruling
048's whole harm requires a repoint, and ``SET event_id = :keep`` before a delete is
exactly how 5,142 / 540 / 2,097 rows of one game's data landed on another's
(#1779/#1798). A vocabulary that cannot spell the harmful operation cannot be extended
into it by a well-meaning patch, so the prune rail's inventory does not spell it.

The MERGE rail is a **different rail with a different contract**. It repoints on
purpose, on a pair that ``event_merge_invariant.assert_mergeable`` plus
``event_absorption_guard.assert_absorbable_now`` have proven to be the same game — an
id-anchored correspondence, not a name-and-time guess. That authorized operation needs
somewhere to live that is not the prune rail's vocabulary. This is that place. The two
modules share the *derivation* of which tables exist and share nothing else.

WHAT THIS FIXES (``C-DELETE-RAIL-PRE`` finding R4, merge half)
--------------------------------------------------------------

Three rails transferred-then-DELETEd against a **hand-listed tuple of eight** tables
while SQLAlchemy metadata declared **ten** FKs to ``events.id``. The two omissions
failed in opposite directions, and neither was visible in any response:

* ``game_moments.event_id`` is ``ON DELETE CASCADE`` — the loser's moments were
  **silently destroyed** by every merge, named in no response and counted in no total.
* ``ranking_judgments.event_id`` has **no** ``ON DELETE`` action — a merge whose loser
  held a human judgment **failed** with an FK violation.

The fix is not "add the two tables", because that is the same hand-list one commit
later. The list is **derived from the schema on every call** (see
``event_fk_tables``), so it cannot go short again.

THE COLLISION THE DERIVATION EXPOSES
------------------------------------

Two of the ten children carry a UNIQUE constraint that **includes ``event_id``**, so a
plain ``UPDATE ... SET event_id = :keep`` can violate it — and the merge rail's whole
population is pairs of rows describing the SAME game, which is precisely when both
sides hold a child with the same key:

* ``game_moments (event_id, dedupe_key)`` — newly repointed by this change.
  ``canonical_dedupe_key`` is the *source play's* identity (``m2:<source>:p<play id>``
  or a content digest); it is deliberately NOT event-scoped in its value, because the
  constraint carries ``event_id``. Two duplicate rows of one game that both ran the
  moments engine over the same provider feed therefore produce **byte-identical**
  keys. Colliding on merge is the expected case, not the rare one.
* ``odds_aggregated (event_id, period_start)`` — **already in the shipped eight**, so
  this rail could already raise ``IntegrityError`` today whenever both duplicates held
  an aggregate for the same period. Found while deriving the list; fixed here rather
  than left standing next to its identical twin.

Both are handled by a **pre-dedupe**, not an exception and not a refusal: repoint only
the rows the survivor has no equivalent of, then delete the redundant remainder. A
refusal would block the merge of exactly the duplicates this rail exists to clean up,
and both collision classes are redundant observations — the survivor already holds a
row for that same source play / that same period of that same game. Nothing is lost
that is not already present under the keeper.

The remainder is **deleted explicitly rather than left to the FK**, for both halves of
R4's lesson: ``odds_aggregated`` is ``NO ACTION`` so leaving it would fail the parent
DELETE, and ``game_moments`` is ``CASCADE`` so leaving it would vanish unnamed. Every
dropped row is counted and returned, because an effect nothing in the output mentions
is an effect nobody reviews.
"""

from __future__ import annotations

from sqlalchemy import text as sa_text

from app.utils.event_fk_inventory import derive_event_child_tables

#: Children whose UNIQUE constraint INCLUDES ``event_id``, mapped to the OTHER columns
#: in that constraint. A repoint into an occupied key violates these, so they take the
#: pre-dedupe path below instead of a plain UPDATE.
#:
#: Restated rather than derived, and on purpose: the derivation answers "which tables"
#: (that is the part that drifted), while *which* unique key is the semantically right
#: one to dedupe on is a judgment about what the rows MEAN — that the survivor's copy
#: is the same observation, so the loser's is redundant. That judgment cannot be read
#: off a catalog. ``test_merge_rail_fk_repoint_r4.py`` asserts this dict stays in sync
#: with metadata in BOTH directions, so a new event-scoped unique constraint turns CI
#: red instead of turning merges into IntegrityErrors.
EVENT_SCOPED_UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "game_moments": ("dedupe_key",),
    "odds_aggregated": ("period_start",),
}


def event_fk_tables() -> tuple[str, ...]:
    """Every table whose ``event_id`` must repoint before its parent event is deleted.

    A **function, not a module constant**, and that is the whole point of R4. A
    module-level tuple evaluated at import time is still a snapshot — it just takes
    its snapshot by computation instead of by typing. ``Base.metadata`` is only
    complete once every model module has been imported, so an import-time constant in
    a task module can be short for exactly the reason the hand-written one was short:
    it froze before the thing it describes was finished. Evaluated at call time it
    cannot be.

    (There is no import cycle today — ``app.tasks.sports`` already imports
    ``app.models`` at module scope and ``models.py`` imports nothing from ``app.tasks``
    — so a constant would *work*. It would just be wrong in the way that stops being
    academic the first time a model lands in a module registered later.)

    Cheap enough to call per merge run (a walk over ~50 tables' foreign keys); callers
    still hoist it out of their per-pair loop, since metadata cannot change mid-run.
    """
    return derive_event_child_tables()


async def repoint_event_children(
    session, *, keep_id: int, orphan_id: int
) -> dict[str, dict[str, int]]:
    """Move every child row from ``orphan_id`` onto ``keep_id``.

    Call immediately before ``DELETE FROM events WHERE id = :orphan``, inside the same
    transaction, and only on a pair the merge invariants have already authorized. This
    function does **no** identity checking of its own — it is the mechanical half, and
    running it on an unproven pair is ruling 048's harm.

    Returns ``{"repointed": {table: n}, "dropped_as_duplicate": {table: n}}``, listing
    only non-zero tables. ``dropped_as_duplicate`` is the count the keeper already had
    an equivalent row for; it is returned so the caller can surface it, because both
    collision tables are ones whose loss would otherwise be invisible.
    """
    repointed: dict[str, int] = {}
    dropped: dict[str, int] = {}

    for table in event_fk_tables():
        extra_key = EVENT_SCOPED_UNIQUE_KEYS.get(table)
        if extra_key is None:
            result = await session.execute(
                sa_text(
                    f"UPDATE {table} SET event_id = :keep WHERE event_id = :orphan"
                ),
                {"keep": keep_id, "orphan": orphan_id},
            )
            moved = _rowcount(result)
            if moved:
                repointed[table] = moved
            continue

        # Pre-dedupe. The NOT EXISTS reads the statement-level snapshot, so rows
        # moving in during this same UPDATE are invisible to it — which is safe here
        # because every mover comes from ``event_id = :orphan`` and the survivor side
        # is ``event_id = :keep``, and the orphan's own copy of the constraint already
        # guarantees no two movers share a key.
        predicate = " AND ".join(
            f"survivor.{col} IS NOT DISTINCT FROM child.{col}" for col in extra_key
        )
        result = await session.execute(
            sa_text(
                f"UPDATE {table} AS child SET event_id = :keep "
                f"WHERE child.event_id = :orphan AND NOT EXISTS ("
                f"  SELECT 1 FROM {table} AS survivor "
                f"  WHERE survivor.event_id = :keep AND {predicate}"
                f")"
            ),
            {"keep": keep_id, "orphan": orphan_id},
        )
        moved = _rowcount(result)
        if moved:
            repointed[table] = moved

        # Whatever is left collided. Delete it HERE, named and counted, rather than
        # letting ON DELETE CASCADE take it unmentioned (game_moments) or letting
        # NO ACTION fail the parent delete (odds_aggregated).
        result = await session.execute(
            sa_text(f"DELETE FROM {table} WHERE event_id = :orphan"),
            {"orphan": orphan_id},
        )
        removed = _rowcount(result)
        if removed:
            dropped[table] = removed

    return {"repointed": repointed, "dropped_as_duplicate": dropped}


def _rowcount(result) -> int:
    """``rowcount`` off a result, tolerating drivers/mocks that do not supply one.

    A missing or non-integer rowcount reports zero rather than raising: this runs
    immediately before a DELETE, and a merge must not fail because its *bookkeeping*
    could not read a count. The counts are for the response, not for control flow —
    nothing above branches on them.
    """
    try:
        count = result.rowcount
    except Exception:  # pragma: no cover - driver/mock without rowcount
        return 0
    return count if isinstance(count, int) and count > 0 else 0
