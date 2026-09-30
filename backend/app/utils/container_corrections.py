"""A corrected hub stays corrected. #9651 — the narrow #5344 contract.

THE SHIP. Somebody removes a wrong-edition game from an NFL-week hub. The next
hourly assembly pass must not put it back, and a reader must never see half of
one revision and half of another. Before this module, assembly only UPSERTED
`contains` edges: deleting a bad edge lasted until the next pass re-proved it
from the same venue grouping.

WHAT IT ADDS, EXHAUSTIVELY.

1. **An append-only correction ledger**, ``container_corrections``. One row per
   decision: withdraw or readmit a member (``scope='member'``), publish or
   withdraw the container (``scope='publication'``). The latest member row
   wins, which is what makes re-admission legitimate rather than a delete of
   the evidence that it was ever withdrawn.
2. **Two columns on ``containers``**: ``publication_state`` (default
   ``unpublished`` — assembly never publishes) and ``membership_revision``,
   bumped on the container AND every ancestor whenever anything a reader of
   that hub would see changes. The hub's root revision therefore covers its
   draws, and one number pins one payload.
3. **A per-container row lock** taken top-down (root first, then the chain to
   the target) by assembly and by every correction. It is what closes the race
   in which a pass gathers its candidates, a withdrawal lands, and the pass
   then writes the withdrawn member back: assembly reads the ledger only after
   it holds the lock, so the withdrawal is either committed before (and read)
   or waits until after (and deletes the edge).

WHAT IT DELIBERATELY DOES NOT DO.

* **No correction adds a member.** ``readmit`` lifts a withdrawal; the next
  pass re-admits the member only if its evidence still proves it. A correction
  that could write an edge would be a curated list with extra steps, and the
  program exists to end curated lists.
* **Assembly never retires a member it merely failed to see.** A member absent
  from one pass keeps its edge: a venue outage is degraded availability, never
  retirement (the T5 containers design). Only a named withdrawal subtracts.
* **Nothing here commits.** Callers own the transaction, exactly as assembly
  does; a correction is live when its caller commits.
* **The read route is not changed here.** ``read_published`` is the contract a
  route or the hydration producer calls; wiring it is that consumer's commit.

THE SCHEMA SHIPS BEFORE ITS MIGRATION RUNS (D45: migration-class merges on
Alex's word only). ``correction_schema_present`` is therefore a question, and
when the answer is "absent" assembly behaves byte-for-byte as it did before:
with no ledger there can be no correction to honour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text

from app.utils.container_graph import (
    validate_correction,
    validate_node_type,
    validate_publication_state,
)

LEDGER_TABLE = "container_corrections"
PUBLICATION_COLUMN = "publication_state"
REVISION_COLUMN = "membership_revision"

#: The report key a withheld candidate is counted under. Not a
#: ``market_match_receipts`` reason, on purpose: that table is one row per
#: MARKET (ON CONFLICT (market_id)), so "withdrawn from this hub" written there
#: would overwrite the receipt recording how the market actually matched — the
#: same reason a window exclusion writes none.
WITHHELD_WITHDRAWN = "container_member_withdrawn"

#: How far up a parent chain a revision bump or a lock walks. The one-hop cycle
#: is a CHECK; a longer one is refused by the sweep (#9149), and this bound is
#: the belt to that brace so a cycle can never turn one UPDATE into a loop.
MAX_CHAIN_DEPTH = 16

# ---------------------------------------------------------------------------
# DDL — the migration and the real-Postgres gates run these exact statements
# ---------------------------------------------------------------------------

_PUBLICATION_CHECK = "publication_state IN ('unpublished', 'published', 'withdrawn')"

ADD_CONTAINER_COLUMNS_SQL = (
    "ALTER TABLE containers "
    f"ADD COLUMN IF NOT EXISTS {PUBLICATION_COLUMN} VARCHAR(16) NOT NULL "
    "DEFAULT 'unpublished' "
    f"CONSTRAINT ck_container_publication_state CHECK ({_PUBLICATION_CHECK}), "
    f"ADD COLUMN IF NOT EXISTS {REVISION_COLUMN} INTEGER NOT NULL DEFAULT 0"
)

CREATE_LEDGER_SQL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    id BIGSERIAL PRIMARY KEY,
    container_id BIGINT NOT NULL REFERENCES containers(id) ON DELETE CASCADE,
    scope VARCHAR(16) NOT NULL,
    action VARCHAR(16) NOT NULL,
    child_type VARCHAR(16),
    child_id BIGINT,
    reason TEXT NOT NULL,
    actor VARCHAR(64) NOT NULL,
    evidence JSONB,
    revision INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_container_correction_shape CHECK (
        (scope = 'member' AND action IN ('withdraw', 'readmit')
         AND child_type IN ('container', 'event', 'market')
         AND child_id IS NOT NULL)
        OR
        (scope = 'publication' AND action IN ('publish', 'withdraw')
         AND child_type IS NULL AND child_id IS NULL)
    ),
    CONSTRAINT ck_container_correction_reason CHECK (length(btrim(reason)) > 0),
    CONSTRAINT ck_container_correction_actor CHECK (length(btrim(actor)) > 0)
)
"""

#: "The latest decision about this member of this container" — the one read
#: assembly makes per container, served by an index scan in id order.
CREATE_LEDGER_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_container_correction_member "
    f"ON {LEDGER_TABLE} (container_id, scope, child_type, child_id, id)"
)

UPGRADE_STATEMENTS = (
    ADD_CONTAINER_COLUMNS_SQL,
    CREATE_LEDGER_SQL,
    CREATE_LEDGER_INDEX_SQL,
)

DOWNGRADE_STATEMENTS = (
    f"DROP TABLE IF EXISTS {LEDGER_TABLE}",
    "ALTER TABLE containers "
    f"DROP COLUMN IF EXISTS {REVISION_COLUMN}, "
    f"DROP COLUMN IF EXISTS {PUBLICATION_COLUMN}",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CorrectionRefused(ValueError):
    """A correction that cannot be applied as asked. Never swallowed."""


class ContainerMissing(CorrectionRefused):
    pass


class StaleRevision(CorrectionRefused):
    """The caller decided against a revision that is no longer current.

    A correction written from a stale page would be a decision about members
    the decider never saw. Refusing it is the optimistic-concurrency half of
    "readers never see a mixture": deciders don't either.
    """

    def __init__(self, container_id: int, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(
            f"container {container_id} is at revision {current}, not {expected}"
        )


class NothingToPublish(CorrectionRefused):
    """Publishing a hub with no members renders "nothing on" (gotcha #53)."""


class CorrectionSchemaAbsent(CorrectionRefused):
    """The migration is not applied; there is nowhere to record a decision."""


# ---------------------------------------------------------------------------
# The schema probe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrectionSchema:
    ledger: bool
    columns: bool

    @property
    def complete(self) -> bool:
        return self.ledger and self.columns


async def correction_schema_present(session) -> CorrectionSchema:
    """Is #9651's migration applied here? A question, never an exception.

    The ledger and the columns are asked separately because they fail in
    different directions: a present ledger is honoured even if the columns
    somehow are not (withdrawals still bind — the safe side), while revision
    bumps need the column. An empty or missing answer reads as absent, which
    is also what every session double that predates this module returns.
    """
    row = (
        await session.execute(
            text(
                f"SELECT to_regclass('public.{LEDGER_TABLE}') IS NOT NULL, "
                "       EXISTS (SELECT 1 FROM information_schema.columns "
                "               WHERE table_schema = 'public' "
                "                 AND table_name = 'containers' "
                f"                AND column_name = '{REVISION_COLUMN}') "
                f"   AND EXISTS (SELECT 1 FROM information_schema.columns "
                "               WHERE table_schema = 'public' "
                "                 AND table_name = 'containers' "
                f"                AND column_name = '{PUBLICATION_COLUMN}')"
            )
        )
    ).fetchone()
    if not row:
        return CorrectionSchema(ledger=False, columns=False)
    return CorrectionSchema(ledger=bool(row[0]), columns=bool(row[1]))


# ---------------------------------------------------------------------------
# Locks, revisions and the ledger read
# ---------------------------------------------------------------------------

_CHAIN_CTE = (
    "WITH RECURSIVE chain(id, depth) AS ("
    "  SELECT CAST(:cid AS BIGINT), 0 "
    "  UNION ALL "
    "  SELECT c.parent_container_id, chain.depth + 1 "
    "  FROM containers c JOIN chain ON c.id = chain.id "
    f"  WHERE c.parent_container_id IS NOT NULL AND chain.depth < {MAX_CHAIN_DEPTH}"
    ") "
)


async def lock_container_chain(
    session, container_id: int, *, with_columns: bool = True
):
    """Lock the container and its ancestors, ROOT FIRST. Returns the target row.

    One order for every writer is what keeps this deadlock-free: assembly locks
    root then draws, a correction on a draw locks root then that draw, so both
    queue on the root. ``LockRows`` sits above the ``Sort``, so rows are locked
    in the ORDER BY order. Returns ``(id, publication_state,
    membership_revision)`` for the target, or None when it does not exist.
    """
    columns = (
        f"c.id, c.{PUBLICATION_COLUMN}, c.{REVISION_COLUMN}"
        if with_columns
        else "c.id, NULL, NULL"
    )
    rows = (
        await session.execute(
            text(
                _CHAIN_CTE + f"SELECT {columns}, chain.depth FROM containers c "
                "JOIN chain ON chain.id = c.id "
                "ORDER BY chain.depth DESC "
                "FOR UPDATE OF c"
            ),
            {"cid": container_id},
        )
    ).fetchall()
    for row in rows:
        if int(row[0]) == container_id and int(row[3]) == 0:
            return row
    return None


async def bump_revision(session, container_id: int) -> int:
    """+1 on the container and every ancestor. Returns the target's revision.

    Ancestors too, because a hub reads its draws' members: a withdrawal inside
    "Men's Doubles" changes what the US Open page shows, so the US Open's own
    revision has to move or a consumer pinned to it would keep serving the old
    payload.
    """
    rows = (
        await session.execute(
            text(
                _CHAIN_CTE
                + f"UPDATE containers SET {REVISION_COLUMN} = {REVISION_COLUMN} + 1, "
                "updated_at = now() "
                "WHERE id IN (SELECT id FROM chain) "
                f"RETURNING id, {REVISION_COLUMN}"
            ),
            {"cid": container_id},
        )
    ).fetchall()
    for row in rows:
        if int(row[0]) == container_id:
            return int(row[1])
    raise ContainerMissing(f"container {container_id} does not exist")


async def withdrawn_members(session, container_id: int) -> set:
    """``{(child_type, child_id)}`` whose LATEST member decision is withdraw."""
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (child_type, child_id) child_type, child_id, action "
                f"FROM {LEDGER_TABLE} "
                "WHERE container_id = :cid AND scope = 'member' "
                "ORDER BY child_type, child_id, id DESC"
            ),
            {"cid": container_id},
        )
    ).fetchall()
    return {(r[0], int(r[1])) for r in rows if r[2] == "withdraw"}


async def current_members(session, container_id: int) -> dict:
    """``{(child_type, child_id): class}`` — this container's edges as they stand."""
    rows = (
        await session.execute(
            text(
                "SELECT child_type, child_id, class FROM event_edges "
                "WHERE parent_type = 'container' AND parent_id = :cid "
                "  AND kind = 'contains'"
            ),
            {"cid": container_id},
        )
    ).fetchall()
    return {(r[0], int(r[1])): r[2] for r in rows}


async def delete_member_edges(session, container_id: int, members) -> int:
    """Remove the ``contains`` edges for these members of this container."""
    removed = 0
    for child_type, child_id in sorted(members):
        result = await session.execute(
            text(
                "DELETE FROM event_edges "
                "WHERE parent_type = 'container' AND parent_id = :cid "
                "  AND kind = 'contains' AND child_type = :ct AND child_id = :id"
            ),
            {"cid": container_id, "ct": child_type, "id": child_id},
        )
        removed += int(getattr(result, "rowcount", 0) or 0)
    return removed


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrectionResult:
    """What one correction did. ``applied=False`` is an idempotent no-op."""

    container_id: int
    scope: str
    action: str
    applied: bool
    revision: int
    edges_removed: int = 0
    publication_state: Optional[str] = None


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorrectionRefused(f"{name} is required and must be non-blank")
    return value.strip()


async def _locked_target(session, container_id: int, expected_revision: Optional[int]):
    schema = await correction_schema_present(session)
    if not schema.complete:
        raise CorrectionSchemaAbsent(
            "container corrections are not migrated on this database (#9651)"
        )
    row = await lock_container_chain(session, container_id)
    if row is None:
        raise ContainerMissing(f"container {container_id} does not exist")
    current = int(row[2])
    if expected_revision is not None and int(expected_revision) != current:
        raise StaleRevision(container_id, int(expected_revision), current)
    return row


async def _record(
    session,
    *,
    container_id: int,
    scope: str,
    action: str,
    reason: str,
    actor: str,
    revision: int,
    child_type: Optional[str] = None,
    child_id: Optional[int] = None,
    evidence: Optional[dict] = None,
) -> None:
    await session.execute(
        text(
            f"INSERT INTO {LEDGER_TABLE} "
            "(container_id, scope, action, child_type, child_id, reason, actor, "
            " evidence, revision) "
            "VALUES (:cid, :scope, :action, :ct, :child_id, :reason, :actor, "
            "        CAST(:evidence AS jsonb), :revision)"
        ),
        {
            "cid": container_id,
            "scope": scope,
            "action": action,
            "ct": child_type,
            "child_id": child_id,
            "reason": reason,
            "actor": actor,
            "evidence": json.dumps(evidence) if evidence else None,
            "revision": revision,
        },
    )


async def _member_correction(
    session,
    action: str,
    *,
    container_id: int,
    child_type: str,
    child_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict],
    expected_revision: Optional[int],
) -> CorrectionResult:
    validate_correction("member", action)
    validate_node_type(child_type, "child_type")
    reason = _require_text(reason, "reason")
    actor = _require_text(actor, "actor")
    child_id = int(child_id)

    row = await _locked_target(session, container_id, expected_revision)
    member = (child_type, child_id)
    is_withdrawn = member in await withdrawn_members(session, container_id)

    if (action == "withdraw") == is_withdrawn:
        # Already in the asked-for state: a retry, not a new decision.
        return CorrectionResult(container_id, "member", action, False, int(row[2]))

    removed = 0
    if action == "withdraw":
        removed = await delete_member_edges(session, container_id, [member])
    revision = await bump_revision(session, container_id)
    await _record(
        session,
        container_id=container_id,
        scope="member",
        action=action,
        child_type=child_type,
        child_id=child_id,
        reason=reason,
        actor=actor,
        evidence=evidence,
        revision=revision,
    )
    return CorrectionResult(container_id, "member", action, True, revision, removed)


async def withdraw_member(
    session,
    *,
    container_id: int,
    child_type: str,
    child_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict] = None,
    expected_revision: Optional[int] = None,
) -> CorrectionResult:
    """Remove one member now, and keep every later pass from re-adding it."""
    return await _member_correction(
        session,
        "withdraw",
        container_id=container_id,
        child_type=child_type,
        child_id=child_id,
        reason=reason,
        actor=actor,
        evidence=evidence,
        expected_revision=expected_revision,
    )


async def readmit_member(
    session,
    *,
    container_id: int,
    child_type: str,
    child_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict] = None,
    expected_revision: Optional[int] = None,
) -> CorrectionResult:
    """Lift a withdrawal. Writes NO edge — the next pass re-proves the member."""
    return await _member_correction(
        session,
        "readmit",
        container_id=container_id,
        child_type=child_type,
        child_id=child_id,
        reason=reason,
        actor=actor,
        evidence=evidence,
        expected_revision=expected_revision,
    )


async def _publication_correction(
    session,
    target_state: str,
    action: str,
    *,
    container_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict],
    expected_revision: Optional[int],
) -> CorrectionResult:
    validate_correction("publication", action)
    validate_publication_state(target_state)
    reason = _require_text(reason, "reason")
    actor = _require_text(actor, "actor")

    row = await _locked_target(session, container_id, expected_revision)
    if row[1] == target_state:
        return CorrectionResult(
            container_id,
            "publication",
            action,
            False,
            int(row[2]),
            publication_state=target_state,
        )

    if target_state == "published":
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM event_edges e "
                    "WHERE e.kind = 'contains' AND e.parent_type = 'container' "
                    "  AND (e.parent_id = :cid OR e.parent_id IN ("
                    "       SELECT id FROM containers WHERE parent_container_id = :cid "
                    f"         AND {PUBLICATION_COLUMN} <> 'withdrawn'))"
                ),
                {"cid": container_id},
            )
        ).scalar()
        if not count:
            raise NothingToPublish(f"container {container_id} has no members")

    await session.execute(
        text(
            f"UPDATE containers SET {PUBLICATION_COLUMN} = :state, updated_at = now() "
            "WHERE id = :cid"
        ),
        {"state": target_state, "cid": container_id},
    )
    revision = await bump_revision(session, container_id)
    await _record(
        session,
        container_id=container_id,
        scope="publication",
        action=action,
        reason=reason,
        actor=actor,
        evidence=evidence,
        revision=revision,
    )
    return CorrectionResult(
        container_id,
        "publication",
        action,
        True,
        revision,
        publication_state=target_state,
    )


async def publish_container(
    session,
    *,
    container_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict] = None,
    expected_revision: Optional[int] = None,
) -> CorrectionResult:
    """Make a hub readable. Assembly never calls this; a named decision does."""
    return await _publication_correction(
        session,
        "published",
        "publish",
        container_id=container_id,
        reason=reason,
        actor=actor,
        evidence=evidence,
        expected_revision=expected_revision,
    )


async def withdraw_publication(
    session,
    *,
    container_id: int,
    reason: str,
    actor: str,
    evidence: Optional[dict] = None,
    expected_revision: Optional[int] = None,
) -> CorrectionResult:
    """Take a whole hub off readers' screens, keeping its URL and its members.

    Membership is untouched so a re-publish after the fix is one decision, not
    a rebuild; the ledger row carries the reason a correction page can print.
    """
    return await _publication_correction(
        session,
        "withdrawn",
        "withdraw",
        container_id=container_id,
        reason=reason,
        actor=actor,
        evidence=evidence,
        expected_revision=expected_revision,
    )


# ---------------------------------------------------------------------------
# The read contract
# ---------------------------------------------------------------------------

READ_UNAVAILABLE = "unavailable"  # no such container
READ_UNPUBLISHED = "unpublished"  # exists, not (yet) for readers — incl. un-migrated
READ_WITHDRAWN = "withdrawn"  # was for readers, taken back; URL kept
READ_EMPTY = "empty"  # published, zero members right now
READ_PUBLISHED = "published"

READ_STATES = frozenset(
    {READ_UNAVAILABLE, READ_UNPUBLISHED, READ_WITHDRAWN, READ_EMPTY, READ_PUBLISHED}
)


def read_state(
    exists: bool, publication_state: Optional[str], member_count: int
) -> str:
    """The one classification every consumer shares. Pure; fails closed.

    An unknown publication state reads as unpublished, never as published — a
    value this code has never heard of is not permission to show a hub.
    """
    if not exists:
        return READ_UNAVAILABLE
    if publication_state == "withdrawn":
        return READ_WITHDRAWN
    if publication_state != "published":
        return READ_UNPUBLISHED
    return READ_PUBLISHED if member_count > 0 else READ_EMPTY


@dataclass
class PublishedRead:
    """One hub at one revision. ``members`` is filled ONLY when published.

    ``revision`` is the root's ``membership_revision``, which moves whenever the
    root or any draw changes, so two consumers holding the same revision hold
    the same members — the "one payload revision" the web and the iPhone are
    compared on.
    """

    state: str
    slug: str
    revision: Optional[int] = None
    container_id: Optional[int] = None
    reason: Optional[str] = None
    members: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "slug": self.slug,
            "revision": self.revision,
            "container_id": self.container_id,
            "reason": self.reason,
            "member_count": len(self.members),
            "members": list(self.members),
        }


async def read_published(session, slug: str) -> PublishedRead:
    """The hub's published membership, from ONE statement, so ONE snapshot.

    Under READ COMMITTED every statement gets its own snapshot; reading the
    revision and the members in two statements could straddle an assembly
    commit and hand a reader revision N's number with revision N+1's members.
    One statement cannot. Draws are included one level down, as the existing
    route does, except a draw that is itself ``withdrawn``.
    """
    schema = await correction_schema_present(session)
    if not schema.columns:
        exists = (
            await session.execute(
                text("SELECT 1 FROM containers WHERE slug = :slug"), {"slug": slug}
            )
        ).fetchone()
        return PublishedRead(
            state=read_state(bool(exists), None, 0),
            slug=slug,
            reason="publication_schema_absent" if exists else None,
        )

    rows = (
        await session.execute(
            text(
                "WITH hub AS ("
                f"  SELECT id, {PUBLICATION_COLUMN} AS pub, {REVISION_COLUMN} AS rev "
                "  FROM containers WHERE slug = :slug"
                "), parts AS ("
                "  SELECT id FROM hub "
                "  UNION ALL "
                "  SELECT c.id FROM containers c JOIN hub ON c.parent_container_id = hub.id "
                f"  WHERE c.{PUBLICATION_COLUMN} <> 'withdrawn'"
                ") "
                "SELECT hub.id, hub.pub, hub.rev, e.class, e.child_type, e.child_id, "
                "       e.parent_id, e.source, e.confidence "
                "FROM hub LEFT JOIN event_edges e "
                "  ON hub.pub = 'published' AND e.kind = 'contains' "
                " AND e.parent_type = 'container' "
                " AND e.parent_id IN (SELECT id FROM parts) "
                "ORDER BY e.class, e.child_id"
            ),
            {"slug": slug},
        )
    ).fetchall()
    if not rows:
        return PublishedRead(state=READ_UNAVAILABLE, slug=slug)

    head = rows[0]
    members = [
        {
            "class": r[3],
            "type": r[4],
            "id": int(r[5]),
            "container_id": int(r[6]),
            "source": r[7],
            "confidence": float(r[8]) if r[8] is not None else None,
        }
        for r in rows
        if r[4] is not None
    ]
    state = read_state(True, head[1], len(members))
    if state not in (READ_PUBLISHED, READ_EMPTY):
        members = []
    return PublishedRead(
        state=state,
        slug=slug,
        revision=int(head[2]),
        container_id=int(head[0]),
        members=members,
    )
