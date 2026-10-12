"""Provider event collection assembly — the writer. #5343 (correction safety #5344).

PILLARS MATCHING · DISCOVER · TRUTH. SHIP: a politics, economics, technology or
entertainment event on Polymarket becomes one complete collection at a stable
URL, assembled from the provider's own grouping, with no member list anywhere in
source. The rules are ``app.utils.provider_event_collections``; this module reads,
locks and writes.

NOT MOUNTED. Nothing imports this module: no Celery task, no beat entry, no route.
It is also behind ``PROVIDER_EVENT_COLLECTIONS_ENABLED`` (unset everywhere). The
mount, the cadence and every publication are named handoffs in
``docs/provider-event-collections-5343.md``.

ONE TRANSACTION PER PROVIDER EVENT.

1. **Gates**, before anything writes: the flag, the containers tables, #9651's
   correction columns + ledger, the decisions table. Each refusal is
   ``terminal: skipped`` with its reason — never a success (gotcha #53).
2. **Container row**: created only for an event with at least ``MIN_MEMBERS``
   admissible members (``INSERT … ON CONFLICT (slug) DO NOTHING``), so single
   markets and negRisk events — one row each — never mint a collection.
3. **Under ``lock_container_chain``** — the same lock every correction takes — the
   pass reads the withdrawals, its own edges, the last decisions and the provider
   rows, all inside the lock. A withdrawal is therefore either committed before
   the pass reads (and honoured) or waits for the pass to commit (and then deletes
   the edge). Two passes over one event serialize on the row lock.
4. **Writes**: this adapter's ``venue_grouping`` edges only (another source's slot
   is never taken), the header columns the provider changed, decision rows whose
   content changed, and at most ONE ``bump_revision`` — on a membership change or
   a header change. A pass that changes nothing writes nothing and keeps the
   revision.

WHAT IT NEVER DOES. It never publishes or withdraws a container, never writes a
``same_as`` edge, never touches a container whose slug is not this adapter's,
never reads or writes ``market_match_receipts``, and never runs on a request.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text

from app.tasks.container_assembly import containers_tables_present
from app.utils.container_corrections import (
    PUBLICATION_COLUMN,
    bump_revision,
    correction_schema_present,
    lock_container_chain,
    withdrawn_members,
)
from app.utils.container_graph import (
    validate_container_kind,
    validate_edge_kind_and_class,
    validate_edge_source,
)
from app.utils.provider_event_collections import (
    CHILD_TYPE,
    CONTAINER_KIND,
    EDGE_CLASS,
    EDGE_SOURCE,
    MIN_MEMBERS,
    RULE_VERSION,
    SUPPORTED_DOMAINS,
    EventAssembly,
    PriorDecision,
    ProviderEventIdentity,
    assemble_event,
    header_changes,
    identity_from_group_id,
    parse_collection_slug,
    plan_event_pass,
    provider_row,
    publication_eligibility,
)
from app.utils.theme_definitions import decisions_table

logger = logging.getLogger(__name__)

ENABLED_ENV = "PROVIDER_EVENT_COLLECTIONS_ENABLED"
EDGE_CONFIDENCE = Decimal("1.000")
PASS_BUDGET_S = 200  # under a 240 s soft limit, the theme producer's bound
CANDIDATE_PAGE = 500

#: The pass budget's clock. A module attribute so a test can drive it.
_monotonic = time.monotonic


def provider_event_collections_enabled() -> bool:
    """Same truthy set as the other container producers' flags."""
    return os.environ.get(ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Statements. Every one is a plain read or a write this module owns.
# ---------------------------------------------------------------------------

DECISIONS_REGCLASS_SQL = (
    "SELECT to_regclass('public.container_member_decisions') IS NOT NULL"
)

_SELECT_CONTAINER = (
    "SELECT id, slug, name, category, status, window_start, window_end, "
    "       publication_state, membership_revision "
    "FROM containers WHERE slug = :slug"
)

_INSERT_CONTAINER = (
    "INSERT INTO containers (kind, name, slug, category, status, window_start, window_end) "
    "VALUES (:kind, :name, :slug, :category, :status, :window_start, :window_end) "
    "ON CONFLICT (slug) DO NOTHING"
)

_SELECT_GROUP_ROWS = (
    "SELECT id, source, external_id, group_id, status, name, llm_sport_category, "
    "       commence_time, resolution_date, market_metadata "
    "FROM futures_markets "
    "WHERE (source = 'polymarket' AND group_id = :gid) OR id = ANY(:ids)"
)

#: Every ``contains`` edge, whatever its child type or source: the published
#: reader serves all of them, so the preflight must see all of them.
_SELECT_EDGES = (
    "SELECT child_type, child_id, class, source FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid AND kind = 'contains'"
)

#: Child containers the published reader folds in (it skips withdrawn ones).
_SELECT_CHILD_CONTAINERS = (
    f"SELECT id FROM containers WHERE parent_container_id = :cid "
    f"  AND {PUBLICATION_COLUMN} <> 'withdrawn'"
)

_SELECT_PRIOR = (
    "SELECT child_id, outcome, reason, evidence FROM container_member_decisions "
    "WHERE container_id = :cid AND child_type = 'market'"
)

#: ``uq_event_edge`` is a unique index, so the arbiter is named by its columns.
#: The WHERE is the survivor guard: a slot another source holds is never taken.
_UPSERT_EDGE = (
    "INSERT INTO event_edges "
    "(parent_type, parent_id, child_type, child_id, kind, class, source, confidence, receipt_id) "
    "VALUES ('container', :cid, 'market', :child_id, 'contains', :class, "
    "        :source, :confidence, NULL) "
    "ON CONFLICT (parent_type, parent_id, child_type, child_id, kind) "
    "DO UPDATE SET class = EXCLUDED.class WHERE event_edges.source = :source"
)

_DELETE_EDGES = (
    "DELETE FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid "
    "  AND kind = 'contains' AND child_type = 'market' "
    "  AND source = :source AND child_id = ANY(:ids)"
)

_HEADER_COLUMNS = ("name", "category", "status", "window_start", "window_end")

#: Candidate events: provider groups in a supported domain with enough rows to
#: hold ``MIN_MEMBERS`` members. The prefix and domains are BOUND, never inlined
#: (gotcha #45). Precise admission is the pure module's; this only bounds work.
_CANDIDATE_GROUPS = (
    "SELECT group_id FROM futures_markets "
    "WHERE source = 'polymarket' AND group_id LIKE :prefix AND group_id > :cursor "
    "  AND lower(llm_sport_category) = ANY(:domains) "
    "GROUP BY group_id HAVING count(*) >= :min_rows "
    "ORDER BY group_id LIMIT :limit"
)

#: Every collection this adapter already holds is re-assembled whatever its rows
#: say now — retirement and correction need the pass to visit it.
_EXISTING_SLUGS = "SELECT slug FROM containers WHERE slug LIKE :prefix"


def _upsert_decisions_sql() -> str:
    """Built from the decisions table's one declaration, so drift fails loudly."""
    table = decisions_table()
    expected = [
        "container_id",
        "child_type",
        "child_id",
        "outcome",
        "reason",
        "rule_version",
        "evidence",
        "revision",
    ]
    present = {c.name for c in table.c}
    if not set(expected) <= present:
        raise RuntimeError(f"decisions_table() lacks {sorted(set(expected) - present)}")
    values = ", ".join(
        "CAST(:evidence AS jsonb)" if c == "evidence" else f":{c}" for c in expected
    )
    return (
        f"INSERT INTO {table.name} ({', '.join(expected)}) VALUES ({values}) "
        "ON CONFLICT ON CONSTRAINT uq_cmd_member DO UPDATE SET "
        "outcome = EXCLUDED.outcome, reason = EXCLUDED.reason, "
        "rule_version = EXCLUDED.rule_version, evidence = EXCLUDED.evidence, "
        "revision = EXCLUDED.revision, last_decided_at = now(), "
        f"attempt_count = {table.name}.attempt_count + 1"
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _instant(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


async def _schema_gate(session) -> Optional[str]:
    if not await containers_tables_present(session):
        return "containers_tables_absent"
    if not (await correction_schema_present(session)).complete:
        return "correction_schema_absent"
    row = (await session.execute(text(DECISIONS_REGCLASS_SQL))).fetchone()
    if not row or not row[0]:
        return "decision_schema_absent"
    return None


async def _select_container(session, slug: str) -> Optional[dict]:
    row = (await session.execute(text(_SELECT_CONTAINER), {"slug": slug})).fetchone()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "slug": row[1],
        "name": row[2],
        "category": row[3],
        "status": row[4],
        "window_start": row[5],
        "window_end": row[6],
        "publication_state": row[7],
        "revision": int(row[8]),
    }


async def _read_rows(
    session, identity: ProviderEventIdentity, extra_ids: Sequence[int]
):
    result = await session.execute(
        text(_SELECT_GROUP_ROWS),
        {"gid": identity.group_id, "ids": sorted({int(i) for i in extra_ids})},
    )
    rows = []
    for r in result.fetchall():
        rows.append(
            provider_row(
                {
                    "id": r[0],
                    "source": r[1],
                    "external_id": r[2],
                    "group_id": r[3],
                    "status": r[4],
                    "name": r[5],
                    "llm_sport_category": r[6],
                    "commence_time": r[7],
                    "resolution_date": r[8],
                    "market_metadata": _json(r[9]),
                }
            )
        )
    return rows


@dataclass
class _EventState:
    edges: dict[int, str] = field(default_factory=dict)
    foreign: set[int] = field(default_factory=set)
    foreign_classes: dict[int, str] = field(default_factory=dict)
    other_slots: dict[tuple, str] = field(default_factory=dict)
    child_containers: list[int] = field(default_factory=list)
    withdrawn: set[int] = field(default_factory=set)
    prior: dict[int, PriorDecision] = field(default_factory=dict)
    prior_rows: dict[int, tuple] = field(default_factory=dict)
    rows: list = field(default_factory=list)

    def stored_slots(self) -> dict:
        """Every slot the published reader would serve, as the pure rule takes it."""
        slots: dict = {(CHILD_TYPE, c): cls for c, cls in self.edges.items()}
        slots.update(
            {(CHILD_TYPE, c): self.foreign_classes.get(c) for c in self.foreign}
        )
        slots.update(self.other_slots)
        slots.update({("container", c): None for c in self.child_containers})
        return slots


async def _read_state(
    session, identity: ProviderEventIdentity, container_id: Optional[int]
) -> _EventState:
    state = _EventState()
    if container_id is not None:
        for child_type, child_id, edge_class, source in (
            await session.execute(text(_SELECT_EDGES), {"cid": container_id})
        ).fetchall():
            if child_type != CHILD_TYPE:
                state.other_slots[(child_type, int(child_id))] = edge_class
            elif source == EDGE_SOURCE:
                state.edges[int(child_id)] = edge_class
            else:
                state.foreign.add(int(child_id))
                state.foreign_classes[int(child_id)] = edge_class
        state.child_containers = [
            int(r[0])
            for r in (
                await session.execute(
                    text(_SELECT_CHILD_CONTAINERS), {"cid": container_id}
                )
            ).fetchall()
        ]
        state.withdrawn = {
            cid
            for ctype, cid in await withdrawn_members(session, container_id)
            if ctype == CHILD_TYPE
        }
        for child_id, outcome, reason, evidence in (
            await session.execute(text(_SELECT_PRIOR), {"cid": container_id})
        ).fetchall():
            evidence = _json(evidence) or {}
            state.prior_rows[int(child_id)] = (outcome, reason, evidence)
            state.prior[int(child_id)] = PriorDecision(
                child_id=int(child_id),
                reason=reason,
                external_id=evidence.get("external_id"),
                applied_roster_at=_instant(evidence.get("applied_roster_at")),
            )
    state.rows = await _read_rows(
        session, identity, list(state.edges) + list(state.prior)
    )
    return state


def _assemble(
    identity: ProviderEventIdentity,
    state: _EventState,
    current_status: Optional[str],
    now: datetime,
) -> EventAssembly:
    return assemble_event(
        identity,
        state.rows,
        edged=state.edges,
        withdrawn=state.withdrawn,
        prior=state.prior,
        current_status=current_status,
        now=now,
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


async def _insert_container(session, assembly: EventAssembly) -> None:
    header = assembly.header
    await session.execute(
        text(_INSERT_CONTAINER),
        {
            "kind": validate_container_kind(CONTAINER_KIND),
            "name": header.name or assembly.identity.slug,
            "slug": assembly.identity.slug,
            "category": header.category,
            "status": header.status or "scheduled",
            "window_start": header.window_start,
            "window_end": header.window_end,
        },
    )


async def _write_edges(
    session, container_id: int, upserts: Sequence[int], deletes: Sequence[int]
) -> tuple[int, int]:
    source = validate_edge_source(EDGE_SOURCE)
    _, edge_class = validate_edge_kind_and_class("contains", EDGE_CLASS)
    if upserts:
        await session.execute(
            text(_UPSERT_EDGE),
            [
                {
                    "cid": container_id,
                    "child_id": int(c),
                    "class": edge_class,
                    "source": source,
                    "confidence": EDGE_CONFIDENCE,
                }
                for c in upserts
            ],
        )
    removed = 0
    if deletes:
        result = await session.execute(
            text(_DELETE_EDGES),
            {"cid": container_id, "source": source, "ids": list(deletes)},
        )
        removed = int(getattr(result, "rowcount", 0) or 0)
    return len(upserts), removed


async def _write_header(session, container_id: int, changes: Mapping[str, Any]) -> None:
    if not changes:
        return
    assignments = ", ".join(
        f"{column} = :{column}" for column in _HEADER_COLUMNS if column in changes
    )
    await session.execute(
        text(
            f"UPDATE containers SET {assignments}, updated_at = now() WHERE id = :cid"
        ),
        {
            **{c: changes[c] for c in _HEADER_COLUMNS if c in changes},
            "cid": container_id,
        },
    )


def _changed_decisions(
    assembly: EventAssembly, prior_rows: Mapping[int, tuple]
) -> list:
    changed = []
    for d in assembly.decisions:
        evidence = json.loads(json.dumps(d.evidence, sort_keys=True, default=str))
        if prior_rows.get(d.child_id) != (d.outcome, d.reason, evidence):
            changed.append((d, evidence))
    return changed


async def _write_decisions(
    session, container_id: int, changed: list, revision: int
) -> int:
    if not changed:
        return 0
    await session.execute(
        text(_upsert_decisions_sql()),
        [
            {
                "container_id": container_id,
                "child_type": CHILD_TYPE,
                "child_id": d.child_id,
                "outcome": d.outcome,
                "reason": d.reason,
                "rule_version": RULE_VERSION,
                "evidence": json.dumps(evidence, sort_keys=True),
                "revision": revision,
            }
            for d, evidence in changed
        ],
    )
    return len(changed)


# ---------------------------------------------------------------------------
# One event
# ---------------------------------------------------------------------------


def _summary(assembly: EventAssembly, eligibility) -> dict:
    return {
        "domain": assembly.domain,
        "domain_state": assembly.domain_state,
        "roster_state": assembly.roster_state,
        "roster_unstored": len(assembly.roster_unstored),
        "identity_conflicts": len(assembly.identity_conflicts),
        "complete": assembly.complete,
        "admitted": len(assembly.admitted),
        "eligibility": eligibility.as_dict(),
    }


async def assemble_provider_event(
    session, identity: ProviderEventIdentity, *, apply: bool, now: datetime
) -> dict:
    """Assemble one provider event. Commits on ``apply``; rolls back otherwise."""
    report: dict[str, Any] = {"slug": identity.slug, "group_id": identity.group_id}
    container = await _select_container(session, identity.slug)
    if container is None:
        state = _EventState(rows=await _read_rows(session, identity, ()))
        assembly = _assemble(identity, state, None, now)
        if len(assembly.admitted) < MIN_MEMBERS:
            await session.rollback()
            return {
                **report,
                "terminal": "complete",
                "reason": "not_a_collection",
                "container_id": None,
                "admitted": len(assembly.admitted),
                "roster_state": assembly.roster_state,
                "domain_state": assembly.domain_state,
            }
        if not apply:
            await session.rollback()
            eligibility = publication_eligibility(assembly, now=now)
            return {
                **report,
                "terminal": "complete",
                "reason": None,
                "apply": False,
                "container_id": None,
                "would_create": True,
                **_summary(assembly, eligibility),
            }
        await _insert_container(session, assembly)
        container = await _select_container(session, identity.slug)
        if container is None:
            raise RuntimeError(
                f"provider event container {identity.slug} absent after insert"
            )

    container_id = container["id"]
    if apply:
        locked = await lock_container_chain(session, container_id)
        if locked is None:
            raise RuntimeError(
                f"provider event container {identity.slug} vanished under the lock"
            )
        # Re-read under the lock: the header may have moved since the unlocked select.
        container = await _select_container(session, identity.slug)
    publication_state, revision_before = (
        container["publication_state"],
        container["revision"],
    )
    state = await _read_state(session, identity, container_id)
    assembly = _assemble(identity, state, container["status"], now)
    plan = plan_event_pass(assembly, state.edges, foreign_held=state.foreign)
    changes = header_changes(assembly.header, container)
    eligibility = publication_eligibility(
        assembly, now=now, publication_state=publication_state
    )
    changed_decisions = _changed_decisions(assembly, state.prior_rows)
    report.update(
        {
            "container_id": container_id,
            "revision_before": revision_before,
            "receipt": plan.receipt,
            "header_changes": sorted(changes),
            **_summary(assembly, eligibility),
        }
    )

    if not apply:
        await session.rollback()
        report.update(
            {
                "apply": False,
                "edges_upserted": len(plan.upserts),
                "edges_deleted": len(plan.deletes),
                "decisions_written": len(changed_decisions),
                "membership_changed": plan.membership_changed,
                "terminal": "complete",
                "reason": None,
            }
        )
        return report

    upserted, deleted = await _write_edges(
        session, container_id, plan.upserts, plan.deletes
    )
    await _write_header(session, container_id, changes)
    revision = revision_before
    if plan.membership_changed or changes:
        revision = await bump_revision(session, container_id)
    written = await _write_decisions(session, container_id, changed_decisions, revision)
    await session.commit()
    report.update(
        {
            "apply": True,
            "edges_upserted": upserted,
            "edges_deleted": deleted,
            "decisions_written": written,
            "revision_after": revision,
            "bumped": revision != revision_before,
            "terminal": "complete",
            "reason": None,
        }
    )
    return report


async def evaluate_provider_event_collection(
    session, slug: str, *, now: datetime
) -> dict:
    """Read-only eligibility for one collection, for a publication preflight.

    Takes no lock and writes nothing: a publisher that must not race assembly
    holds ``lock_container_chain`` itself, then calls this in the same
    transaction, so the answer describes what it is about to publish.

    Publication serves the STORED edges, not this re-assembly, so the answer is
    eligible only when the two agree slot for slot (every edge of any source or
    child type, and any child container): a pass that has not yet written what
    it now proves — a missing, extra or reclassified slot — refuses, by name.
    """
    identity = parse_collection_slug(slug)
    if identity is None:
        return {
            "slug": slug,
            "supported": False,
            "eligible": False,
            "reasons": ["not_a_provider_event_slug"],
        }
    container = await _select_container(session, slug)
    if container is None:
        return {
            "slug": slug,
            "supported": True,
            "exists": False,
            "eligible": False,
            "reasons": ["container_absent"],
        }
    state = await _read_state(session, identity, container["id"])
    assembly = _assemble(identity, state, container["status"], now)
    eligibility = publication_eligibility(
        assembly,
        now=now,
        publication_state=container["publication_state"],
        stored_slots=state.stored_slots(),
    )
    return {
        "slug": slug,
        "supported": True,
        "exists": True,
        "container_id": container["id"],
        "revision": container["revision"],
        "publication_state": container["publication_state"],
        "eligible": eligibility.eligible,
        "reasons": list(eligibility.reasons),
        **_summary(assembly, eligibility),
    }


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


async def _candidates(session) -> list[ProviderEventIdentity]:
    found: dict[str, ProviderEventIdentity] = {}
    cursor = ""
    while True:
        rows = (
            await session.execute(
                text(_CANDIDATE_GROUPS),
                {
                    "prefix": "polymarket:%",
                    "cursor": cursor,
                    "domains": sorted(SUPPORTED_DOMAINS),
                    "min_rows": MIN_MEMBERS,
                    "limit": CANDIDATE_PAGE,
                },
            )
        ).fetchall()
        for (group_id,) in rows:
            identity = identity_from_group_id(group_id)
            if identity is not None:
                found[identity.event_id] = identity
        if len(rows) < CANDIDATE_PAGE:
            break
        cursor = rows[-1][0]
    for (slug,) in (
        await session.execute(text(_EXISTING_SLUGS), {"prefix": "polymarket-event-%"})
    ).fetchall():
        identity = parse_collection_slug(slug)
        if identity is not None:
            found[identity.event_id] = identity
    return sorted(found.values(), key=lambda i: int(i.event_id))


async def _run_assemble_provider_event_collections(
    apply: bool = True,
    only: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    resume_after: Optional[str] = None,
) -> dict:
    """Every candidate provider event, one transaction each, one verdict.

    ``only`` is a provider event id. ``resume_after`` is the last event id a
    budget-truncated pass reached; the caller persists ``resume_after`` from the
    report so the tail is not starved (gotcha #41). A truncated pass is
    ``partial``, never ``complete``.
    """
    started = datetime.now(timezone.utc)
    now = now or started
    if not provider_event_collections_enabled():
        return {
            "terminal": "skipped",
            "reason": "provider_event_collections_disabled",
            "events": [],
        }

    from app.tasks.base import get_task_session

    events: list[dict] = []
    truncated_at: Optional[str] = None
    async with get_task_session() as session:
        refused = await _schema_gate(session)
        if refused is not None:
            return {"terminal": "skipped", "reason": refused, "events": []}
        if only is not None:
            identity = identity_from_group_id(f"polymarket:{only}")
            if identity is None:
                return {
                    "terminal": "skipped",
                    "reason": "malformed_event_id",
                    "events": [],
                }
            identities = [identity]
        else:
            identities = await _candidates(session)
            await session.rollback()  # end the read transaction before per-event work
        if resume_after is not None:
            later = [i for i in identities if int(i.event_id) > int(resume_after)]
            identities = later + [
                i for i in identities if int(i.event_id) <= int(resume_after)
            ]
        deadline = _monotonic() + PASS_BUDGET_S
        for identity in identities:
            if _monotonic() >= deadline:
                truncated_at = (
                    events[-1]["group_id"].split(":", 1)[1] if events else resume_after
                )
                break
            try:
                events.append(
                    await assemble_provider_event(
                        session, identity, apply=apply, now=now
                    )
                )
            except Exception as exc:  # noqa: BLE001 — gotcha #42, per event
                await session.rollback()
                logger.exception("provider event assembly failed for %s", identity.slug)
                events.append(
                    {
                        "slug": identity.slug,
                        "group_id": identity.group_id,
                        "terminal": "failed",
                        "reason": "assembly_error",
                        "error": repr(exc),
                    }
                )

    failed = [e for e in events if e.get("terminal") == "failed"]
    if events and len(failed) == len(events):
        terminal, reason = "failed", "every_event_failed"
    elif failed or truncated_at is not None:
        terminal, reason = "partial", (
            "budget_exhausted" if truncated_at is not None else "some_event_failed"
        )
    else:
        terminal, reason = "complete", None
    return {
        "terminal": terminal,
        "reason": reason,
        "apply": apply,
        "candidates": len(identities),
        "visited": len(events),
        "resume_after": truncated_at,
        "collections": sum(1 for e in events if e.get("container_id")),
        "eligible": sum(
            1 for e in events if (e.get("eligibility") or {}).get("eligible")
        ),
        "events": events,
        "started_at": started.isoformat(),
        "duration_s": (datetime.now(timezone.utc) - started).total_seconds(),
    }
