"""Theme collection assembly + immutable snapshots — #9935 slice P2, unit A2.

PILLARS MATCHING · DISCOVER · TRUTH. SHIP (#9935): an AI or Oscars preview
opens the same complete collection at a stable URL, and the count on the card
is the count on the page. This module is the writer that ship rides on. On its
own it changes nothing a reader sees: it is behind ``THEME_ASSEMBLY_ENABLED``
(unset in production), it is wired by C1 (Authority), its table arrives with
C2 (Alex's word, D45), and assembly never publishes a container. The contract
is Authority's ``docs/theme-collection-producer-contract-9935.md`` §10.4
(v3.4); semantics numbers below refer to it.

ONE PASS, PER REGISTRY DEFINITION, ONE TRANSACTION PER CONTAINER.

1. **Gates** (semantics 1), all before any statement that writes: the flag,
   the containers tables, #9651's correction columns, the decisions table.
   Each refusal is ``terminal: skipped`` with its reason — a third state, never
   a success (gotcha #53).
2. **Container row** (2): ``INSERT … ON CONFLICT (slug) DO NOTHING``, then read.
   An existing row is never updated; publication stays where a human left it.
3. **Gather** (3): the definition's own §4 arms (P1's ``candidate_population``,
   prior decisions included) unioned and paged by id cursor inside
   ``PASS_BUDGET_S``. Every row is copied to plain data and decided at once.
4. **Under ``lock_container_chain``** (4–8): read the withdrawals, then plan.
   A withdrawn member is excluded whatever ``decide()`` said. Only
   ``theme_rule`` edges are ever upserted or deleted, and a truncated gather
   never retires a member it did not see.
5. **Revision** (7): at most ONE ``bump_revision`` per container per pass — on
   a membership change, OR when the stored snapshot at the current revision is
   absent, OR when its bytes differ from the snapshot built now. The payload
   is serialized before commit, under the lock.
6. **Publication** (9): after commit, ``SET key payload NX EX``. An existing key
   is never overwritten: identical bytes refresh its TTL, different bytes are
   a loud ``publication_conflict``. A delayed producer can only publish the
   key of the revision it committed, which is older than anything after it.

WHAT IT NEVER DOES. It never reads or writes ``market_match_receipts`` (a
receipt is one row per market and records how the market MATCHED; a theme
decision is not a match). It never touches an edge whose source is not
``theme_rule``. It never publishes, withdraws or renames a container. It never
issues an unconditional ``SET``/``SETEX``/``GETSET``/``DEL`` on a
``theme_snapshot:`` key. ``routes/feed.py`` never imports it (case 13).

TWO READINGS OF THE CONTRACT, STATED SO REVIEW SEES THEM.

* ``uq_event_edge`` is a unique INDEX (``containers_phase1`` creates it with
  ``op.create_index``), not a constraint, so ``ON CONFLICT ON CONSTRAINT
  uq_event_edge`` would raise on Postgres. The upsert names the index's five
  columns instead, which infers the same arbiter.
* ``plan_container_pass`` takes an optional ``foreign_held``: children whose
  slot on this container is already held by an edge of another source. The
  guarded upsert is a no-op for them, so counting it as a change would bump
  the revision on every pass.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import text

from app.tasks.container_assembly import containers_tables_present
from app.utils.container_corrections import (
    bump_revision,
    correction_schema_present,
    current_members,
    lock_container_chain,
    withdrawn_members,
)
from app.utils.container_graph import (
    validate_container_kind,
    validate_edge_kind_and_class,
    validate_edge_source,
)
from app.utils.discover_bundles import (
    _dedupe_same_question_members,
    theme_member_withhold_reason,
)
from app.utils.theme_definitions import (
    CONTAINER_MEMBER_WITHDRAWN,
    OUTCOME_ADMITTED,
    OUTCOME_EXCLUDED,
    OUTCOME_WITHHELD,
    REGISTRY,
    Decision,
    ThemeDefinition,
    candidate_population,
    decisions_table,
    parse_theme_slug,
)

logger = logging.getLogger(__name__)

#: The pass budget's clock. A module attribute so a test can drive it.
_monotonic = time.monotonic

THEME_ASSEMBLY_ENABLED_ENV = "THEME_ASSEMBLY_ENABLED"


def theme_assembly_enabled() -> bool:
    """Same truthy set as ``container_assembly.collections_enabled``."""
    return os.environ.get(THEME_ASSEMBLY_ENABLED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


EDGE_SOURCE = "theme_rule"
EDGE_CONFIDENCE = Decimal("1.000")
CLASS_RANK = {"title": 0, "advancement": 1, "side_question": 2}
_OTHER_CLASS_RANK = 3
SNAPSHOT_KEY = "theme_snapshot:{container_id}:{revision}"
SNAPSHOT_TTL_S = 3 * 86400
GATHER_PAGE = 500
PASS_BUDGET_S = 200  # under the wrapper's 240 s soft limit

REVISION_REASONS = ("membership_changed", "snapshot_absent", "content_changed", "identical")
PUBLICATION_OUTCOMES = ("written", "refreshed", "publication_conflict", "write_failed")

#: The hydration withholds a snapshot can carry (semantics 8). Every key is
#: always present in the payload so two snapshots of one membership serialize
#: to the same bytes whichever reasons happen to be empty.
SNAPSHOT_WITHHOLDS = ("row_missing", "suppressed", "low_quality", "public_source_disagreement")

#: Written on every theme decision row; matches the edges this module writes.
CHILD_TYPE = "market"

#: The decision-row columns the database defaults (semantics 6): never bound.
_DECISION_DEFAULTED = frozenset({"id", "first_decided_at", "last_decided_at", "attempt_count"})


# ---------------------------------------------------------------------------
# Plain data. Nothing below holds an ORM row (gotcha #6): a pass commits per
# container and a rollback expires every live object it touched.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomeRow:
    name: Optional[str]
    is_winner: Optional[bool]
    resolution_source: Optional[str]


@dataclass(frozen=True)
class MemberRow:
    """One ``futures_markets`` row as ``decide()`` and the gate read it."""

    id: int
    name: Optional[str]
    source: Optional[str]
    external_id: Optional[str]
    status: Optional[str]
    llm_sport_category: Optional[str]
    canonical_market_key: Optional[str] = None
    resolution_date: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    market_metadata: Optional[dict] = None
    outcomes: tuple[OutcomeRow, ...] = ()

    @property
    def outcome_names(self) -> list[str]:
        return [o.name for o in self.outcomes if o.name is not None]


def member_row(market: Any) -> MemberRow:
    """Copy a loaded ``FuturesMarket`` (outcomes loaded) to plain data."""
    meta = getattr(market, "market_metadata", None)
    return MemberRow(
        id=int(market.id),
        name=market.name,
        source=market.source,
        external_id=market.external_id,
        status=market.status,
        llm_sport_category=market.llm_sport_category,
        canonical_market_key=getattr(market, "canonical_market_key", None),
        resolution_date=getattr(market, "resolution_date", None),
        settled_at=getattr(market, "settled_at", None),
        market_metadata=json.loads(json.dumps(meta, default=str)) if isinstance(meta, dict) else None,
        outcomes=tuple(
            OutcomeRow(o.name, getattr(o, "is_winner", None), getattr(o, "resolution_source", None))
            for o in (getattr(market, "outcomes", None) or ())
        ),
    )


# ---------------------------------------------------------------------------
# Pure: the pass plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberDecision:
    child_id: int
    decision: Decision
    withdrawn: bool


@dataclass(frozen=True)
class PassPlan:
    edge_upserts: tuple[tuple[int, str], ...]  # (child_id, class)
    edge_deletes: tuple[int, ...]  # theme_rule edges only
    decision_rows: tuple[dict, ...]  # one per decided child; written whether or not anything changed
    membership_changed: bool


def _decision_row(md: MemberDecision) -> dict:
    d = md.decision
    if not md.withdrawn:
        return {
            "child_id": md.child_id,
            "outcome": d.outcome,
            "reason": d.reason,
            "rule_version": d.rule_version,
            "evidence": d.evidence,
        }
    # Case 12: the standing human decision wins, and the row says what the rule
    # would have said so a readmit can be judged against it.
    return {
        "child_id": md.child_id,
        "outcome": OUTCOME_EXCLUDED,
        "reason": CONTAINER_MEMBER_WITHDRAWN,
        "rule_version": d.rule_version,
        "evidence": {
            "correction": "withdraw",
            "rule_decision": {
                "outcome": d.outcome,
                "reason": d.reason,
                "edge_class": d.edge_class,
                "evidence": d.evidence,
            },
        },
    }


def plan_container_pass(
    decided: Sequence[MemberDecision],
    current_theme_edges: Mapping[int, str],
    *,
    inventory_complete: bool,
    foreign_held: Iterable[int] = (),
) -> PassPlan:
    """What one pass writes for one container (semantics 4–6).

    Admitted and not withdrawn → upsert the ``theme_rule`` edge with the
    decision's class. Anything else holding a ``theme_rule`` edge → delete it.
    On a COMPLETE pass a ``theme_rule`` member nobody decided is retired too
    (the prior-decision arm re-gathers every earlier member, so an undecided
    one is a row that no longer exists). On a TRUNCATED pass deletes are
    restricted to children decided this pass: a member the pass did not reach
    keeps its edge. The first decision for a child wins if one is repeated.
    """
    held = frozenset(int(i) for i in foreign_held)
    upserts: list[tuple[int, str]] = []
    deletes: list[int] = []
    rows: list[dict] = []
    seen: set[int] = set()
    changed = False

    for md in sorted(decided, key=lambda m: m.child_id):
        child = int(md.child_id)
        if child in seen:
            continue
        seen.add(child)
        rows.append(_decision_row(md))
        admit = md.decision.admitted and not md.withdrawn and md.decision.edge_class
        if admit:
            if child in held:
                continue  # another source's edge holds the slot; the upsert would be a no-op
            edge_class = md.decision.edge_class
            upserts.append((child, edge_class))
            if current_theme_edges.get(child) != edge_class:
                changed = True
        elif child in current_theme_edges:
            deletes.append(child)
            changed = True

    if inventory_complete:
        unseen = sorted(int(c) for c in current_theme_edges if int(c) not in seen)
        deletes.extend(unseen)
        changed = changed or bool(unseen)

    return PassPlan(tuple(upserts), tuple(deletes), tuple(rows), changed)


# ---------------------------------------------------------------------------
# Pure: the snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThemeSnapshot:
    container_id: int
    slug: str
    name: str
    revision: int
    inventory_complete: bool
    shown_ids: tuple[int, ...]  # page order (CLASS_RANK, id)
    folded_ids: tuple[int, ...]  # flat: step 4 reads shown ∪ folded only
    withheld: Mapping[str, tuple[int, ...]]  # SNAPSHOT_WITHHOLDS (+ any reason the gate adds)
    shown_count: int
    eligible_count: int

    def to_json(self) -> str:
        """sort_keys, compact; the canonical bytes are ``to_json().encode("utf-8")``."""
        return json.dumps(
            {
                "container_id": self.container_id,
                "slug": self.slug,
                "name": self.name,
                "revision": self.revision,
                "inventory_complete": self.inventory_complete,
                "shown_ids": list(self.shown_ids),
                "folded_ids": list(self.folded_ids),
                "withheld": {k: list(v) for k, v in self.withheld.items()},
                "shown_count": self.shown_count,
                "eligible_count": self.eligible_count,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def payload(self) -> bytes:
        return self.to_json().encode("utf-8")


def _page_order(members: Mapping[int, str]) -> list[int]:
    return sorted(
        (int(i) for i in members),
        key=lambda i: (CLASS_RANK.get(members[i], _OTHER_CLASS_RANK), i),
    )


def build_snapshot(
    container: Any,
    revision: int,
    members: Mapping[int, str],
    rows: Mapping[int, MemberRow],
    *,
    inventory_complete: bool,
) -> ThemeSnapshot:
    """The page one revision serves (semantics 8).

    ``members`` is ``{market_id: class}`` as the container's edges stand.
    Membership is not quality: a member the Discover gate withholds keeps its
    edge and decision, and is only left off the page here, through the gate
    Discover owns (imported, never copied — case 16). The rest fold to one row
    per question through Discover's fold (case 19). An empty membership is an
    empty snapshot, never a skipped one (case 25).
    """
    withheld: dict[str, list[int]] = {k: [] for k in SNAPSHOT_WITHHOLDS}
    eligible: list[dict] = []
    for child_id in _page_order(members):
        row = rows.get(child_id)
        if row is None:
            withheld["row_missing"].append(child_id)
            continue
        reason = theme_member_withhold_reason(
            market_name=row.name,
            sport_category=row.llm_sport_category,
            outcome_names=row.outcome_names,
            external_id=row.external_id,
            status=row.status,
            public_source_disagreement=False,
        )
        if reason is not None:
            withheld.setdefault(reason, []).append(child_id)
            continue
        eligible.append(
            {"type": "futures", "data": {"id": child_id, "name": row.name, "source": row.source}}
        )
    kept, folded = _dedupe_same_question_members(eligible)
    shown = tuple(int(item["data"]["id"]) for item in kept)
    return ThemeSnapshot(
        container_id=int(_field(container, "id")),
        slug=str(_field(container, "slug")),
        name=str(_field(container, "name")),
        revision=int(revision),
        inventory_complete=bool(inventory_complete),
        shown_ids=shown,
        folded_ids=tuple(int(item["data"]["id"]) for item in folded),
        withheld={k: tuple(v) for k, v in withheld.items()},
        shown_count=len(shown),
        eligible_count=len(members),
    )


def _field(obj: Any, name: str) -> Any:
    return obj[name] if isinstance(obj, Mapping) else getattr(obj, name)


# ---------------------------------------------------------------------------
# Pure: revision choice and immutable publication
# ---------------------------------------------------------------------------


def snapshot_key(container_id: int, revision: int) -> str:
    return SNAPSHOT_KEY.format(container_id=int(container_id), revision=int(revision))


def _as_bytes(value: Any) -> Optional[bytes]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def choose_revision(
    *, membership_changed: bool, stored: Optional[bytes], candidate_at_current: ThemeSnapshot
) -> tuple[bool, str]:
    """(bump, reason): the FIRST true reason in ``REVISION_REASONS`` order.

    A stored value of None is ABSENT — first publication, eviction, expiry, a
    revision a correction moved without publishing, or a read error — and an
    absent cache never proves the earlier content was equal, so it bumps.
    Keeping the revision on an absent key is how one revision could come to
    mean two different pages (the v3.3 race v3.4 corrects).
    """
    if membership_changed:
        return True, "membership_changed"
    stored_bytes = _as_bytes(stored)
    if stored_bytes is None:
        return True, "snapshot_absent"
    if stored_bytes != candidate_at_current.payload():
        return True, "content_changed"
    return False, "identical"


def publish_snapshot(redis_client: Any, snapshot: ThemeSnapshot) -> str:
    """Publish one revision's page without ever overwriting one. Never raises.

    ``SET NX EX`` accepted → ``written``. Refused → read it back: the same bytes
    → ``EXPIRE`` (the ONLY operation on an existing key) → ``refreshed``;
    different bytes → ``publication_conflict``, logged at ERROR and left
    exactly as found. The key gone between the two calls, an ``EXPIRE`` that
    found nothing, or any Redis error → ``write_failed``.
    """
    key = snapshot_key(snapshot.container_id, snapshot.revision)
    try:
        payload = snapshot.payload()
        if redis_client is None:
            return "write_failed"
        if redis_client.set(key, payload, nx=True, ex=SNAPSHOT_TTL_S):
            return "written"
        existing = _as_bytes(redis_client.get(key))
        if existing is None:
            return "write_failed"
        if existing != payload:
            logger.error(
                "theme snapshot publication_conflict at %s: stored bytes differ "
                "from this producer's payload; the stored value is left untouched",
                key,
            )
            return "publication_conflict"
        if not redis_client.expire(key, SNAPSHOT_TTL_S):
            return "write_failed"
        return "refreshed"
    except Exception:  # noqa: BLE001 — a cache write never fails the pass
        logger.exception("theme snapshot write failed at %s", key)
        return "write_failed"


def _read_stored(redis_client: Any, key: str) -> Optional[bytes]:
    """The stored value, or None for absent — a read error included."""
    if redis_client is None:
        return None
    try:
        return _as_bytes(redis_client.get(key))
    except Exception:  # noqa: BLE001 — unreadable is absent, which bumps
        logger.warning("theme snapshot read failed at %s; treated as absent", key, exc_info=True)
        return None


def _redis_client():
    """``get_redis_client()`` (bounded, gotcha #39), or None when unavailable."""
    from app.tasks.redis_state import get_redis_client

    try:
        return get_redis_client()
    except Exception:  # noqa: BLE001 — absent client: reads absent, writes fail loud
        logger.exception("theme assembly could not get a Redis client")
        return None


# ---------------------------------------------------------------------------
# Database statements. Every one is a plain read or a write this module owns.
# ---------------------------------------------------------------------------

DECISIONS_REGCLASS_SQL = "SELECT to_regclass('public.container_member_decisions') IS NOT NULL"

_SELECT_CONTAINER_BY_SLUG = "SELECT id, slug, name FROM containers WHERE slug = :slug"
_SELECT_CONTAINER_BY_ID = "SELECT id, slug, name FROM containers WHERE id = :cid"

_INSERT_CONTAINER = (
    "INSERT INTO containers (kind, name, slug, category, window_start, window_end) "
    "VALUES (:kind, :name, :slug, :category, NULL, :window_end) "
    "ON CONFLICT (slug) DO NOTHING"
)

_SELECT_MARKET_EDGES = (
    "SELECT child_id, class, source FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid "
    "  AND kind = 'contains' AND child_type = 'market'"
)

#: ``uq_event_edge`` is a unique index, so the arbiter is named by its columns.
#: The WHERE is the survivor guard: a slot another source holds is never taken.
_UPSERT_THEME_EDGE = (
    "INSERT INTO event_edges "
    "(parent_type, parent_id, child_type, child_id, kind, class, source, confidence, receipt_id) "
    "VALUES ('container', :cid, 'market', :child_id, 'contains', :class, "
    "        :source, :confidence, NULL) "
    "ON CONFLICT (parent_type, parent_id, child_type, child_id, kind) "
    "DO UPDATE SET class = EXCLUDED.class WHERE event_edges.source = 'theme_rule'"
)

_DELETE_THEME_EDGES = (
    "DELETE FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid "
    "  AND kind = 'contains' AND child_type = 'market' "
    "  AND source = 'theme_rule' AND child_id = ANY(:ids)"
)


def _upsert_decisions_sql() -> str:
    """Built from S0's one declaration, so a renamed column fails here, loudly."""
    table = decisions_table()
    columns = [c.name for c in table.c if c.name not in _DECISION_DEFAULTED]
    expected = {"container_id", "child_type", "child_id", "outcome", "reason",
                "rule_version", "evidence", "revision"}
    if set(columns) != expected:
        raise RuntimeError(f"decisions_table() columns drifted from the writer: {sorted(columns)}")
    values = ", ".join(
        "CAST(:evidence AS jsonb)" if c == "evidence" else f":{c}" for c in columns
    )
    return (
        f"INSERT INTO {table.name} ({', '.join(columns)}) VALUES ({values}) "
        "ON CONFLICT ON CONSTRAINT uq_cmd_member DO UPDATE SET "
        "outcome = EXCLUDED.outcome, reason = EXCLUDED.reason, "
        "rule_version = EXCLUDED.rule_version, evidence = EXCLUDED.evidence, "
        "revision = EXCLUDED.revision, last_decided_at = now(), "
        f"attempt_count = {table.name}.attempt_count + 1"
    )


async def _schema_gate(session) -> Optional[str]:
    """The first refusal reason (semantics 1), or None when every gate passes."""
    if not await containers_tables_present(session):
        return "containers_tables_absent"
    # Both halves of #9651: the columns carry the revision, and the ledger is
    # where a withdrawal is read before anything is written.
    if not (await correction_schema_present(session)).complete:
        return "correction_schema_absent"
    row = (await session.execute(text(DECISIONS_REGCLASS_SQL))).fetchone()
    if not row or not row[0]:
        return "decision_schema_absent"
    return None


def _skipped(reason: str, **extra) -> dict:
    return {"terminal": "skipped", "reason": reason, "containers": [], **extra}


async def _select_container(session, sql: str, params: dict) -> Optional[dict]:
    row = (await session.execute(text(sql), params)).fetchone()
    if row is None:
        return None
    return {"id": int(row[0]), "slug": row[1], "name": row[2]}


async def _ensure_container(session, defn: ThemeDefinition, *, apply: bool) -> Optional[dict]:
    slug = defn.slug()
    found = await _select_container(session, _SELECT_CONTAINER_BY_SLUG, {"slug": slug})
    if found is not None or not apply:
        return found
    await session.execute(
        text(_INSERT_CONTAINER),
        {
            "kind": validate_container_kind(defn.container_kind),
            "name": defn.display_name,
            "slug": slug,
            "category": defn.category,
            "window_end": defn.edition_backstop,
        },
    )
    return await _select_container(session, _SELECT_CONTAINER_BY_SLUG, {"slug": slug})


async def _page_ids(session, defn: ThemeDefinition, container_id: int, now: datetime,
                    cursor: int, limit: int) -> list[int]:
    """One page of the union of the definition's §4 arms, by id cursor."""
    from sqlalchemy import select, union

    arms = candidate_population(defn, container_id=container_id, now=now)
    candidates = union(*arms.values()).subquery("theme_candidates")
    stmt = (
        select(candidates.c.id)
        .where(candidates.c.id > cursor)
        .order_by(candidates.c.id)
        .limit(limit)
    )
    return [int(r[0]) for r in (await session.execute(stmt)).fetchall()]


async def _load_markets(session, ids: Sequence[int]) -> dict[int, MemberRow]:
    """``{id: MemberRow}`` for the ids that still have a row, outcomes loaded."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    out: dict[int, MemberRow] = {}
    ordered = sorted({int(i) for i in ids})
    for start in range(0, len(ordered), GATHER_PAGE):
        chunk = ordered[start : start + GATHER_PAGE]
        result = await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id.in_(chunk))
        )
        for market in result.scalars().all():
            row = member_row(market)
            out[row.id] = row
    return out


async def _market_edges(session, container_id: int) -> tuple[dict[int, str], set[int]]:
    """(``{child_id: class}`` of theme_rule edges, children held by any other source)."""
    rows = (await session.execute(text(_SELECT_MARKET_EDGES), {"cid": container_id})).fetchall()
    theme: dict[int, str] = {}
    foreign: set[int] = set()
    for child_id, edge_class, source in rows:
        if source == EDGE_SOURCE:
            theme[int(child_id)] = edge_class
        else:
            foreign.add(int(child_id))
    return theme, foreign


async def _market_members(session, container_id: int) -> dict[int, str]:
    members = await current_members(session, container_id)
    return {int(cid): cls for (ctype, cid), cls in members.items() if ctype == CHILD_TYPE}


async def _write_edges(session, container_id: int, plan: PassPlan) -> tuple[int, int]:
    source = validate_edge_source(EDGE_SOURCE)
    params = []
    for child_id, edge_class in plan.edge_upserts:
        _, edge_class = validate_edge_kind_and_class("contains", edge_class)
        params.append(
            {"cid": container_id, "child_id": child_id, "class": edge_class,
             "source": source, "confidence": EDGE_CONFIDENCE}
        )
    if params:
        await session.execute(text(_UPSERT_THEME_EDGE), params)
    deleted = 0
    if plan.edge_deletes:
        result = await session.execute(
            text(_DELETE_THEME_EDGES), {"cid": container_id, "ids": list(plan.edge_deletes)}
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)
    return len(params), deleted


async def _write_decisions(session, container_id: int, plan: PassPlan, revision: int) -> int:
    if not plan.decision_rows:
        return 0
    params = [
        {
            "container_id": container_id,
            "child_type": CHILD_TYPE,
            "child_id": row["child_id"],
            "outcome": row["outcome"],
            "reason": row["reason"],
            "rule_version": row["rule_version"],
            "evidence": json.dumps(row["evidence"], sort_keys=True, default=str),
            "revision": revision,
        }
        for row in plan.decision_rows
    ]
    await session.execute(text(_upsert_decisions_sql()), params)
    return len(params)


# ---------------------------------------------------------------------------
# Gather + decide (semantics 3)
# ---------------------------------------------------------------------------


@dataclass
class _Gathered:
    decisions: dict[int, Decision]
    rows: dict[int, MemberRow]
    complete: bool
    errors: list[str]


async def _gather_and_decide(session, defn: ThemeDefinition, container_id: int,
                             now: datetime) -> _Gathered:
    deadline = _monotonic() + PASS_BUDGET_S
    decisions: dict[int, Decision] = {}
    rows: dict[int, MemberRow] = {}
    errors: list[str] = []
    cursor = 0
    complete = False
    while True:
        if _monotonic() >= deadline:
            break
        ids = await _page_ids(session, defn, container_id, now, cursor, GATHER_PAGE)
        if not ids:
            complete = True
            break
        loaded = await _load_markets(session, ids)
        for market_id in ids:
            row = loaded.get(market_id)
            if row is None:
                continue  # gathered (a prior decision) but the row is gone
            rows[market_id] = row
            try:
                decisions[market_id] = defn.decide(row, now=now)
            except Exception as exc:  # noqa: BLE001 — gotcha #42, per member
                errors.append(f"market:{market_id}: {exc!r}")
                logger.exception("theme decide failed for market %s in %s", market_id, defn.slug())
        cursor = max(ids)
        if len(ids) < GATHER_PAGE:
            complete = True
            break
    # A member whose decision raised was not decided, and on a complete pass an
    # undecided theme_rule member is retired — so one bad row must not be able
    # to retire anything. The pass reports itself incomplete instead.
    return _Gathered(decisions, rows, complete and not errors, errors)


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def _count(decided: Sequence[MemberDecision]) -> dict:
    admitted = 0
    excluded: dict[str, int] = {}
    withheld: dict[str, int] = {}
    for md in decided:
        if md.withdrawn:
            excluded[CONTAINER_MEMBER_WITHDRAWN] = excluded.get(CONTAINER_MEMBER_WITHDRAWN, 0) + 1
        elif md.decision.outcome == OUTCOME_ADMITTED:
            admitted += 1
        elif md.decision.outcome == OUTCOME_WITHHELD:
            withheld[md.decision.reason] = withheld.get(md.decision.reason, 0) + 1
        else:
            excluded[md.decision.reason] = excluded.get(md.decision.reason, 0) + 1
    return {"decided": len(decided), "admitted": admitted, "excluded": excluded, "withheld": withheld}


def _container_terminal(report: dict) -> tuple[str, Optional[str]]:
    """One container's verdict. LOUD (``failed``) for a conflict or for zero
    decisions on a complete pass; ``partial`` for anything short of a full
    inventory published (gotcha #53: it returned is not it worked)."""
    if report.get("snapshot") == "publication_conflict":
        return "failed", "publication_conflict"
    if report.get("inventory_complete") and report.get("decided", 0) == 0:
        return "failed", "zero_decided"
    if not report.get("inventory_complete"):
        return "partial", "inventory_incomplete"
    if report.get("snapshot") == "write_failed":
        return "partial", "snapshot_write_failed"
    return "complete", None


def _roll_up(containers: list[dict]) -> tuple[str, Optional[str]]:
    reasons = [c.get("reason") for c in containers]
    terminals = [c.get("terminal") for c in containers]
    if "publication_conflict" in reasons:
        return "failed", "publication_conflict"
    if "zero_decided" in reasons:
        return "failed", "zero_decided"
    if terminals and all(t == "failed" for t in terminals):
        return "failed", "every_container_failed"
    if terminals and all(t == "complete" for t in terminals):
        return "complete", None
    return "partial", "some_container_incomplete"


async def _settle_revision(session, container: dict, revision: int, members: Mapping[int, str],
                           *, membership_changed: bool, inventory_complete: bool,
                           redis_client) -> tuple[ThemeSnapshot, str, bool]:
    """Semantics 7, under the caller's lock: build, compare, at most one bump,
    serialize. Returns (the snapshot to publish, revision_reason, bumped)."""
    rows = await _load_markets(session, list(members))
    candidate = build_snapshot(
        container, revision, members, rows, inventory_complete=inventory_complete
    )
    stored = _read_stored(redis_client, snapshot_key(container["id"], revision))
    bump, reason = choose_revision(
        membership_changed=membership_changed, stored=stored, candidate_at_current=candidate
    )
    snapshot = candidate
    if bump:
        new_revision = await bump_revision(session, container["id"])
        snapshot = dataclasses.replace(candidate, revision=new_revision)
    snapshot.payload()  # serialized before commit: an unserializable page commits nothing
    return snapshot, reason, bump


async def _assemble_one(session, defn: ThemeDefinition, *, apply: bool, now: datetime) -> dict:
    slug = defn.slug()
    container = await _ensure_container(session, defn, apply=apply)
    if container is None and apply:
        return {"slug": slug, "container_id": None, "terminal": "failed",
                "reason": "container_row_absent"}
    container_id = container["id"] if container else 0

    gathered = await _gather_and_decide(session, defn, container_id, now)
    report: dict[str, Any] = {
        "slug": slug,
        "container_id": container["id"] if container else None,
        "inventory_complete": gathered.complete,
        "errors": gathered.errors,
    }

    if not apply:
        withdrawn: set[int] = set()
        theme_edges: dict[int, str] = {}
        foreign: set[int] = set()
        if container is not None:
            withdrawn = {cid for ctype, cid in await withdrawn_members(session, container_id)
                         if ctype == CHILD_TYPE}
            theme_edges, foreign = await _market_edges(session, container_id)
        decided = [MemberDecision(cid, d, cid in withdrawn)
                   for cid, d in sorted(gathered.decisions.items())]
        plan = plan_container_pass(decided, theme_edges, inventory_complete=gathered.complete,
                                   foreign_held=foreign)
        await session.rollback()  # a dry run ends its read transaction, having written nothing
        report.update(_count(decided))
        report.update({
            "apply": False,
            "edges_upserted": len(plan.edge_upserts),
            "edges_deleted": len(plan.edge_deletes),
            "membership_changed": plan.membership_changed,
            "snapshot": None,
        })
        report["terminal"], report["reason"] = (
            ("partial", "inventory_incomplete") if not gathered.complete else ("complete", None)
        )
        return report

    redis_client = _redis_client()

    locked = await lock_container_chain(session, container_id)
    if locked is None:
        raise RuntimeError(f"theme container {slug} vanished under the lock")
    revision_before = int(locked[2])
    withdrawn = {cid for ctype, cid in await withdrawn_members(session, container_id)
                 if ctype == CHILD_TYPE}
    theme_edges, foreign = await _market_edges(session, container_id)
    decided = [MemberDecision(cid, d, cid in withdrawn)
               for cid, d in sorted(gathered.decisions.items())]
    plan = plan_container_pass(decided, theme_edges, inventory_complete=gathered.complete,
                               foreign_held=foreign)
    upserted, deleted = await _write_edges(session, container_id, plan)

    members = await _market_members(session, container_id)
    snapshot, revision_reason, bumped = await _settle_revision(
        session, container, revision_before, members,
        membership_changed=plan.membership_changed,
        inventory_complete=gathered.complete,
        redis_client=redis_client,
    )
    await _write_decisions(session, container_id, plan, snapshot.revision)
    await session.commit()

    outcome = publish_snapshot(redis_client, snapshot)
    report.update(_count(decided))
    report.update({
        "edges_upserted": upserted,
        "edges_deleted": deleted,
        "revision_before": revision_before,
        "revision_after": snapshot.revision,
        "bumped": bumped,
        "revision_reason": revision_reason,
        "snapshot": outcome,
        "shown_count": snapshot.shown_count,
        "eligible_count": snapshot.eligible_count,
        "snapshot_withheld": {k: len(v) for k, v in snapshot.withheld.items() if v},
    })
    report["terminal"], report["reason"] = _container_terminal(report)
    return report


async def _run_assemble_theme_collections(
    apply: bool = True, only: Optional[str] = None, *, now: Optional[datetime] = None
) -> dict:
    """Every registry definition, one transaction each, one verdict (semantics 11).

    ``apply=False`` gathers and decides and returns the plan counts; it writes
    nothing to the database or Redis and does not create a missing container.
    """
    started = datetime.now(timezone.utc)
    now = now or started
    if not theme_assembly_enabled():
        return _skipped("theme_assembly_disabled")
    definitions = [d for s, d in REGISTRY.items() if only is None or s == only]
    if not definitions:
        return _skipped("no_such_theme", only=only)

    from app.tasks.base import get_task_session

    containers: list[dict] = []
    async with get_task_session() as session:
        refused = await _schema_gate(session)
        if refused is not None:
            return _skipped(refused)
        for defn in definitions:
            try:
                containers.append(await _assemble_one(session, defn, apply=apply, now=now))
            except Exception as exc:  # noqa: BLE001 — gotcha #42, per container
                await session.rollback()
                logger.exception("theme assembly failed for %s", defn.slug())
                containers.append({"slug": defn.slug(), "terminal": "failed",
                                   "reason": "assembly_error", "error": repr(exc)})

    terminal, reason = _roll_up(containers)
    return {
        "terminal": terminal,
        "reason": reason,
        "apply": apply,
        "containers": containers,
        "started_at": started.isoformat(),
        "duration_s": (datetime.now(timezone.utc) - started).total_seconds(),
    }


async def _run_rebuild_theme_snapshot(container_id: int) -> dict:
    """Semantics 10: members and revision read together under the lock, then
    7–9 with ``membership_changed=False``. No gather, no decide, no edge or
    decision-row writes. A correction moves the revision without publishing,
    so a rebuild normally finds its key absent and allocates the next one.

    ``inventory_complete`` is False here: a rebuild reads the edges the last
    pass left and cannot know whether that pass reached the end of its gather,
    so it never claims a complete inventory it did not see.
    """
    if not theme_assembly_enabled():
        return _skipped("theme_assembly_disabled")

    from app.tasks.base import get_task_session

    container_id = int(container_id)
    async with get_task_session() as session:
        refused = await _schema_gate(session)
        if refused is not None:
            return _skipped(refused)
        container = await _select_container(session, _SELECT_CONTAINER_BY_ID, {"cid": container_id})
        if container is None:
            return _skipped("container_absent", container_id=container_id)
        if parse_theme_slug(container["slug"]) is None:
            return _skipped("not_a_theme_container", container_id=container_id)
        try:
            redis_client = _redis_client()
            locked = await lock_container_chain(session, container_id)
            if locked is None:
                return _skipped("container_absent", container_id=container_id)
            revision_before = int(locked[2])
            members = await _market_members(session, container_id)
            snapshot, revision_reason, bumped = await _settle_revision(
                session, container, revision_before, members,
                membership_changed=False, inventory_complete=False,
                redis_client=redis_client,
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — reported, never raised
            await session.rollback()
            logger.exception("theme snapshot rebuild failed for container %s", container_id)
            report = {"slug": container["slug"], "container_id": container_id,
                      "terminal": "failed", "reason": "rebuild_error", "error": repr(exc)}
            return {"terminal": "failed", "reason": "rebuild_error", "containers": [report]}

    outcome = publish_snapshot(redis_client, snapshot)
    report = {
        "slug": container["slug"],
        "container_id": container_id,
        "inventory_complete": False,
        "decided": 0,
        "edges_upserted": 0,
        "edges_deleted": 0,
        "revision_before": revision_before,
        "revision_after": snapshot.revision,
        "bumped": bumped,
        "revision_reason": revision_reason,
        "snapshot": outcome,
        "shown_count": snapshot.shown_count,
        "eligible_count": snapshot.eligible_count,
    }
    if outcome == "publication_conflict":
        terminal, reason = "failed", "publication_conflict"
    elif outcome == "write_failed":
        terminal, reason = "partial", "snapshot_write_failed"
    else:
        terminal, reason = "complete", None
    report["terminal"], report["reason"] = terminal, reason
    return {"terminal": terminal, "reason": reason, "containers": [report]}
