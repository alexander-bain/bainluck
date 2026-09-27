"""#9051 — a per-row revision for ``events.win_probability_sources``.

## the ship

A removed source stops influencing the held headline and chart, and valid
survivor quotes and re-admissions still land.

## why a revision and not a clock

The page holds a folded blend: the canonical row's source bag plus whatever its
tagged twins add (`proven_duplicates.folded_probability_sources`). A client that
holds one fold and is handed another must tell "newer read" from "older read"
without trusting any quote clock: a survivor quote observed BEFORE a removal can
commit AFTER it, and a twin's removal can commit after the canonical's even
though it was stamped earlier (Codex, twin-contract/CONTRACT-REVIEW.md). A
single maximum removal timestamp across rows loses exactly those cases.

So each row carries a counter the DATABASE bumps whenever its bag changes. The
row lock serializes writers of one row, and under READ COMMITTED the second
writer's UPDATE re-reads the first writer's committed row before the trigger
runs, so ``OLD.rev + 1`` follows COMMIT order for that row, whatever any clock
says. The trigger covers every writer, including ones nobody has listed.

A fold is served with ``{row_id: rev}`` for every row it read, paired with the
bag it read (ux 0558Z contract). Comparing two such vectors key by key is sound
where comparing clocks is not: each component only grows, and each component
identifies exactly the bag the served number was computed from.

## why this module holds the DDL

Both the migration (`alembic/versions/wps_rev_trigger.py`) and the model's
``after_create`` hook run these exact statements, so every real-Postgres gate
built by ``Base.metadata.create_all`` has the production trigger rather than a
copy of it. This module imports nothing from the app.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

REV_COLUMN = "win_probability_sources_rev"
FUNCTION_NAME = "bump_win_probability_sources_rev"
TRIGGER_NAME = "trg_bump_win_probability_sources_rev"

CREATE_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.{REV_COLUMN} := OLD.{REV_COLUMN} + 1;
    RETURN NEW;
END
$$
"""

# No `UPDATE OF win_probability_sources`: that form fires only when the column
# is NAMED in the SET list, so a bag changed any other way would not move the
# revision. The WHEN clause is evaluated by the executor without calling the
# function, so an UPDATE that leaves the bag alone pays one jsonb comparison.
CREATE_TRIGGER_SQL = f"""
CREATE TRIGGER {TRIGGER_NAME}
BEFORE UPDATE ON events
FOR EACH ROW
WHEN (OLD.win_probability_sources IS DISTINCT FROM NEW.win_probability_sources)
EXECUTE FUNCTION {FUNCTION_NAME}()
"""

DROP_TRIGGER_SQL = f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON events"
DROP_FUNCTION_SQL = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}()"


def _rev(value: Any) -> Optional[int]:
    """A stored revision, or None when the value makes no claim.

    ``bool`` is an ``int`` subclass and is refused: a True that reached a
    vector would compare as 1 and order a snapshot it never described.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def fold_revision_vector(
    canonical_id: Any,
    canonical_rev: Any,
    twin_revs: Iterable[tuple[Any, Any]],
) -> Optional[dict[str, int]]:
    """``{"<row_id>": rev}`` for the canonical and every twin the fold READ.

    Every row read, not every row that contributed: a twin whose only source
    was just removed contributes nothing to the new fold, and its bumped
    revision is precisely what tells a client the old fold is stale.

    All or nothing. One unreadable revision makes the whole vector None, the
    contract's "no claim" (the client falls back to its legacy rule), because a
    partial vector would order two folds by the rows it happened to include.
    """
    vector: dict[str, int] = {}
    for row_id, rev in ((canonical_id, canonical_rev), *twin_revs):
        parsed = _rev(rev)
        if row_id is None or parsed is None:
            return None
        vector[str(int(row_id))] = parsed
    return vector
