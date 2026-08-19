"""The attended MAPPING consumer (#1918, queue 373). The apply path that never existed.

WHY THIS EXISTS, AND WHY IT READS LIKE THE CREATE RAIL

Queue 363 built the mapping plan object. Queue 367 re-derived it. Queue 368
measured the delta. Queue 370 minted the 130-row address and staged it. Four
windows of work on an artifact — and `C-APPLY-PRE-MAPPING` blocked, because
every ``decode_mapping_repair_plan`` call site in the tree was going to be the
definition module, the deriver, or a test. The rows were certified clean; the
consumer did not exist. That is the identical claim-not-execution shape #1796
hit one table over, so this module is deliberately the same module with the
verbs changed, rather than a fresh design.

    POST /api/admin/repairs/team-identity-mapping-repair?apply=false
        -> loads the STAGED reviewed artifact, runs the live gate, persists the
           plan, returns ``plan_hash``
    POST /api/admin/repairs/team-identity-mapping-repair?apply=true&plan_hash=<hash>
        -> loads THAT artifact, writes ONLY its rows, re-derives nothing

WHAT A RE-POINT IS, AND WHERE ITS COMPARE HALF GOES

The create rail's compare half is an EXISTENCE check, because the row it writes
does not exist yet. Here the row exists and carries a known ``before.team_id``,
so the compare half is an ordinary compare-and-set — and it goes INSIDE the
UPDATE for the same reason::

    UPDATE team_identity_mapping SET team_id = :after
     WHERE id = :mapping_id AND team_id = :before

``rowcount == 0`` is then a finding — :data:`REASON_MAPPING_BEFORE_DRIFT` — and
never a silent success. This is not a hypothetical race. ``resolve_team`` step 3
filters by sport prefix, NOT by source, and then AUTO-REGISTERS its hit, so
these very rows are written by live traffic: three of the original 133
(``4168917``, ``4168971``, ``35192094``) were observed rotating between review
and apply, which is exactly why they are held out of the 130 rather than
repaired. A ``before`` check placed in FRONT of the statement would read a world
the statement then changes — #1798's defect, restated in the update direction.

WHAT IT REFUSES TO INVENT

The update writes ONE column: ``team_id``. Not ``source_name``, not
``sport_key``, not ``source_id``. If a mapping's ``source_name`` is itself
wrong, that is a different defect with a different reviewed population, and a
rail that "tidied it up while it was there" would be writing rows nobody
approved. Correction, never invention.

THE THREE READ REFUSALS ARE THREE, NOT ONE (gotcha #53)

``PLAN_ARTIFACT_MISSING`` says the plan never existed and the right next move is
to make one. ``PLAN_ARTIFACT_CORRUPT`` says an artifact IS there and cannot be
trusted — do not regenerate, investigate. ``PLAN_ARTIFACT_UNREADABLE`` says the
store could not be read right now. Telling an operator MISSING during a store
outage sends them to regenerate, which is the one action that destroys the
evidence.

A NOTE ON THE /v1 ARTIFACTS

The staged 130 (`6b4a42f85a3cd169b611ac7105a7a1e8`) and its parents
(`2cf5fd35…`, `04d24862…`) were addressed under a raw ``"|".join`` digest, which
is not injective over free text — ``source="poly|market"`` with
``sport_key="baseball_mlb"`` and ``source="poly"`` with
``sport_key="market|baseball_mlb"`` produce one address. Those artifacts are
``/v1`` and this consumer refuses them as CORRUPT by schema. The /v2
re-derivation is `scripts/derive_mapping_repair_plan.py`, and its membership was
proved byte-identical to the reviewed 130 before the address was re-minted — so
Alex's approval carries to the new address rather than needing to be re-asked.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
import zlib
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# The plan primitives are the ones certified on the calibration rail and reused
# by #1798 and #1796. Imported, never re-implemented.
from app.utils.repair_apply_plan import (  # noqa: E402
    MAPPING_REPAIR_PLAN_SCHEMA,
    REASON_MAPPING_BEFORE_DRIFT,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_UNREADABLE,
    PlannedMappingRepair,
    bind_apply,
    build_mapping_repair_plan,
    decode_mapping_repair_plan,
    mapping_repair_gate,
    plan_reason_for_read,
)

#: Durable identity of the reviewed plan artifact. ONE slot: an operator applies
#: the plan they just read, and an apply against an older hash must fail loudly
#: rather than find a convenient older artifact still lying around.
PLAN_IDENTITY = "repair:team_identity_mapping:apply_plan"

#: The COMMITTED reviewed set this rail is bound to. A FILE, not a re-derivation:
#: the whole substance of the pattern is that the work list cannot be recomputed
#: at apply time, because a recomputed list can differ from the reviewed one and
#: no after-measurement can tell you which of the two you wrote.
#:
#: Under ``app/data/`` and NOT ``.claude/handoff/``, which is where the plan was
#: staged. That directory is **gitignored**: a consumer pointed at it reads the
#: file on the machine that wrote it and finds nothing on Heroku, so the rail
#: would refuse in production while passing every local test — a rail that only
#: works where it was written. Same placement and same reason as
#: ``app/data/event_create_truth_set.json``.
STAGED_ARTIFACT = "app/data/mapping_repair_reviewed_130.json"

#: Rows written per call. A module constant, not a query param, so the cap cannot
#: be dialled off mid-run. The apply is RESUMABLE without a cursor: the gate drops
#: rows that already hold their ``after`` value, so re-invoking with the SAME
#: plan_hash continues where the last call stopped.
APPLY_MAPPING_CAP = 50

#: Wall-clock budget against the web dyno's 30s HTTP wall. A partial page is a
#: NORMAL outcome and says ``stopped_on_time_budget`` rather than pretending to be
#: exhausted (gotcha #53).
APPLY_TIME_BUDGET_S = 20.0

#: Namespace half of the advisory lock key, so this rail's locks cannot collide
#: with another rail's.
_ADVISORY_LOCK_NS = 1918

REASON_STAGED_MISSING = "STAGED_ARTIFACT_MISSING"
REASON_STAGED_UNREADABLE = "STAGED_ARTIFACT_UNREADABLE"
REASON_STAGED_CORRUPT = "STAGED_ARTIFACT_CORRUPT"

# The gate's live half. Asked as a SET of the PLAN's own ids, never as a count and
# never as a fresh population scan — a re-scan here is what produced the false
# comfort of `miswired_after=0` on the binding rail.
_OBSERVED_SQL = text(
    "SELECT id, team_id FROM team_identity_mapping WHERE id = ANY(:ids)"
)

# COMPARE-AND-SET. The `AND team_id = :before_team_id` is the compare half and it
# is INSIDE the writing statement — see the module docstring. `CAST(:p AS ...)`
# rather than `:p::...` because asyncpg's text() parser drops a bind param
# followed by a `::` cast (memory: asyncpg :param::jsonb bind gotcha).
_UPDATE_SQL = text(
    """
    UPDATE team_identity_mapping
       SET team_id = CAST(:after_team_id AS integer),
           updated_at = NOW()
     WHERE id = CAST(:mapping_id AS integer)
       AND team_id = CAST(:before_team_id AS integer)
    """
)

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(CAST(:ns AS integer), CAST(:key AS integer))")

# The after-verification reads the PLAN's own mapping ids.
_VERIFY_SQL = text(
    """
    SELECT m.id, m.team_id, m.source, m.sport_key, m.source_name, t.name AS club
      FROM team_identity_mapping m
      LEFT JOIN teams t ON t.id = m.team_id
     WHERE m.id = ANY(:ids)
     ORDER BY m.id
    """
)


def _lock_key(mapping_id: int) -> int:
    """A stable 31-bit advisory-lock key for one mapping id.

    Computed in Python rather than with ``hashtext`` so the key is identical in a
    test double and in production, and so the rail does not depend on a Postgres
    internal whose hash is not contractual across versions.
    """
    return int(zlib.crc32(str(mapping_id).encode("utf-8")) & 0x7FFFFFFF)


def _staged_path() -> pathlib.Path:
    # parents[2] is `backend/`, which is what `app/data/...` is relative to.
    return pathlib.Path(__file__).resolve().parents[2] / STAGED_ARTIFACT


def _load_staged() -> tuple[Optional[dict], str]:
    """``(payload, reason)`` — three named readings, never one flattened one."""
    path = _staged_path()
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None, REASON_STAGED_MISSING
    except OSError as exc:  # permissions, I/O — "I could not read it right now"
        logger.warning("#1918 staged artifact unreadable: %s", type(exc).__name__)
        return None, REASON_STAGED_UNREADABLE
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None, REASON_STAGED_CORRUPT
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rows"), list):
        return None, REASON_STAGED_CORRUPT
    return parsed, "ok"


def _rows_from_staged(payload: dict) -> list[PlannedMappingRepair]:
    """The reviewed rows, in the shape the plan object addresses.

    Raises ``KeyError``/``TypeError``/``ValueError`` on a malformed row rather
    than skipping it: a reviewed set that quietly loses a row at load time is a
    different set, and the address is supposed to notice.
    """
    rows: list[PlannedMappingRepair] = []
    for r in payload["rows"]:
        rows.append(
            PlannedMappingRepair(
                mapping_id=int(r["mapping_id"]),
                source=str(r["source"]),
                sport_key=str(r["sport_key"]),
                source_name=str(r["source_name"]),
                before_team_id=int(r["before"]["team_id"]),
                before_club=str(r["before"]["club"]),
                after_team_id=int(r["after"]["team_id"]),
                after_club=str(r["after"]["club"]),
            )
        )
    return rows


async def _save_plan(plan) -> tuple[bool, str]:
    """Persist the reviewed plan. ``(ok, note)`` — a failure is REPORTED, never eaten."""
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY,
                schema_version=MAPPING_REPAIR_PLAN_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source="repair:team-identity-mapping-repair",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"plan persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"plan persist rejected: {result.get('status')}"


async def _load_plan():
    """``(plan, reason)`` — the artifact, re-digested from its own content."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            PLAN_IDENTITY,
            expected_version=MAPPING_REPAIR_PLAN_SCHEMA,
            max_age_s=14 * 86400,
        )
    except Exception as exc:  # noqa: BLE001
        # A raise is "I could not read", never "it is not there" (gotcha #53).
        logger.warning("#1918 plan read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not read.ok or read.envelope is None:
        logger.warning(
            "#1918 plan artifact not readable: status=%s error_class=%s",
            read.status, read.error_class,
        )
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_mapping_repair_plan(read.envelope.payload)


async def _observed_team_ids(session, mapping_ids) -> dict[int, int | None]:
    """Current ``team_id`` per reviewed mapping id. Absent id -> not in the dict.

    :func:`mapping_repair_gate` reads a missing key as ``None`` and reports it as
    ``MAPPING_ROW_MISSING``, so a deleted row is a named finding rather than an
    implicit pass.
    """
    ids = [int(i) for i in mapping_ids]
    if not ids:
        return {}
    rows = (await session.execute(_OBSERVED_SQL, {"ids": ids})).all()
    return {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in rows}


async def _dry_run(session) -> dict[str, Any]:
    """Build the plan from the COMMITTED reviewed artifact, gate it, persist it."""
    staged, reason = _load_staged()
    if staged is None:
        return {
            "issue": "#1918",
            "apply": False,
            "refused": True,
            "reason_codes": [reason],
            "note": f"No plan produced. Staged artifact at {STAGED_ARTIFACT}.",
        }
    try:
        rows = _rows_from_staged(staged)
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "issue": "#1918",
            "apply": False,
            "refused": True,
            "reason_codes": [REASON_STAGED_CORRUPT],
            "note": f"Staged artifact row malformed: {type(exc).__name__}",
        }

    plan = build_mapping_repair_plan(
        rows,
        context={
            "issue": "#1918",
            "staged_artifact": STAGED_ARTIFACT,
            "staged_v1_plan_hash": staged.get("plan_hash"),
            "approval": (
                "Alex approved the 133; three rows a live before-check would abort "
                "and one never-reviewed row are held out, leaving these 130 as a "
                "STRICT SUBSET. Membership proved byte-identical under the /v2 digest."
            ),
        },
    )

    observed = await _observed_team_ids(session, plan.mapping_ids)
    gate_ok, drifted = mapping_repair_gate(plan, observed)
    saved, note = await _save_plan(plan)

    return {
        "issue": "#1918",
        "apply": False,
        "refused": False,
        "plan_hash": plan.plan_hash,
        "plan_persisted": saved,
        "plan_persist_note": note,
        "row_count": len(plan.rows),
        "staged_v1_plan_hash": staged.get("plan_hash"),
        "gate_ok": gate_ok,
        "drifted": drifted,
        "actionable": len(plan.rows) - len(drifted),
        "note": (
            "Read the plan, then re-invoke with apply=true&plan_hash=<plan_hash>. "
            "Drifted rows are NAMED and will retire individually; their siblings apply."
        ),
    }


async def _apply_reviewed_plan(session, plan_hash: Optional[str]) -> dict[str, Any]:
    """Re-point EXACTLY the reviewed mappings, or refuse by name. Never re-derives."""
    plan, reason = await _load_plan()
    ok, refusals = bind_apply(plan, decode_reason=reason, presented_hash=plan_hash)
    if not ok:
        return {
            "issue": "#1918",
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": refusals,
            "presented_plan_hash": plan_hash,
            "artifact_plan_hash": plan.plan_hash if plan is not None else None,
            "artifact_note": reason,
            "note": (
                "Nothing was written. Re-run with apply=false to produce a plan, read it, "
                "then pass its plan_hash back."
            ),
        }

    # The gate's live half, asked BEFORE any write. A row whose team_id has
    # rotated is NAMED and retires; its siblings survive.
    observed = await _observed_team_ids(session, plan.mapping_ids)
    _gate_ok, drifted = mapping_repair_gate(plan, observed)
    drifted_ids = {int(d["mapping_id"]) for d in drifted}
    actionable = [r for r in plan.rows if int(r.mapping_id) not in drifted_ids]

    # Structural assertion BEFORE the loop, while nothing has been written: prove
    # the write set is a SUBSET of the approved set. This rail commits per row
    # (``team_identity_mapping`` is written by live ``resolve_team`` traffic, and
    # a single long transaction over 50 updates contends with it), so a post-hoc
    # discovery would have nothing left to roll back.
    approved_keys = set(plan.row_keys)
    outside = sorted({r.row_key for r in actionable} - approved_keys)
    if outside:
        return {
            "issue": "#1918",
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": [REASON_OUTSIDE_APPROVED],
            "outside_approved_set": outside,
            "note": "Nothing was written. The apply assembled rows the reviewed plan never named.",
        }

    repointed: list[dict[str, Any]] = []
    lost_cas: list[dict[str, Any]] = []
    started = time.monotonic()
    stopped_on_time_budget = False
    stopped_on_cap = False

    for row in actionable:
        if len(repointed) >= APPLY_MAPPING_CAP:
            stopped_on_cap = True
            break
        if time.monotonic() - started > APPLY_TIME_BUDGET_S:
            stopped_on_time_budget = True
            break

        # Tripwire for anyone who later re-introduces a scan on this path. It
        # cannot fire while the loop iterates the plan, which is exactly the point.
        if row.row_key not in approved_keys:  # pragma: no cover — structural
            await session.rollback()
            return {
                "issue": "#1918",
                "apply": True,
                "applied": False,
                "refused": True,
                "reason_codes": [REASON_OUTSIDE_APPROVED],
                "outside_approved_set": [row.row_key],
                "note": "Rolled back mid-loop: a row outside the reviewed plan reached the writer.",
            }

        await session.execute(
            _LOCK_SQL, {"ns": _ADVISORY_LOCK_NS, "key": _lock_key(row.mapping_id)}
        )
        result = await session.execute(
            _UPDATE_SQL,
            {
                "mapping_id": int(row.mapping_id),
                "before_team_id": int(row.before_team_id),
                "after_team_id": int(row.after_team_id),
            },
        )
        entry = {
            "mapping_id": int(row.mapping_id),
            "source": row.source,
            "sport_key": row.sport_key,
            "source_name": row.source_name,
            "before": {"team_id": int(row.before_team_id), "club": row.before_club},
            "after": {"team_id": int(row.after_team_id), "club": row.after_club},
        }
        if (result.rowcount or 0) == 1:
            await session.commit()
            repointed.append(entry)
            logger.info(
                "#1918 re-pointed mapping %s: team %s (%s) -> %s (%s) [plan %s]",
                row.mapping_id, row.before_team_id, row.before_club,
                row.after_team_id, row.after_club, plan.plan_hash[:12],
            )
        else:
            await session.rollback()
            entry["reason_code"] = REASON_MAPPING_BEFORE_DRIFT
            entry["reason"] = (
                "the row's team_id changed between the gate and the update — "
                "resolve_team re-registered it, so this row retires and its siblings continue"
            )
            lost_cas.append(entry)

    # Verify over the PLAN's own mapping ids, not a population re-scan.
    verified: dict[str, Any] = {"at_after": 0, "at_before": 0, "elsewhere": [], "absent": []}
    after = (
        await session.execute(_VERIFY_SQL, {"ids": list(plan.mapping_ids)})
    ).mappings().all()
    by_id = {int(r["id"]): r for r in after}
    for row in plan.rows:
        hit = by_id.get(int(row.mapping_id))
        if hit is None:
            verified["absent"].append(int(row.mapping_id))
            continue
        current = int(hit["team_id"]) if hit["team_id"] is not None else None
        if current == int(row.after_team_id):
            verified["at_after"] += 1
        elif current == int(row.before_team_id):
            verified["at_before"] += 1
        else:
            # Neither reviewed value. Named, never inferred away — it means a
            # third writer moved the row and the plan no longer describes it.
            verified["elsewhere"].append(
                {
                    "mapping_id": int(row.mapping_id),
                    "observed_team_id": current,
                    "observed_club": hit["club"],
                    "expected_before": int(row.before_team_id),
                    "expected_after": int(row.after_team_id),
                }
            )

    remaining = len(plan.rows) - verified["at_after"]
    return {
        "issue": "#1918",
        "apply": True,
        "applied": True,
        "refused": False,
        "plan_hash": plan.plan_hash,
        "plan_row_count": len(plan.rows),
        "repointed_count": len(repointed),
        "repointed": repointed,
        "gate_drifted": drifted,
        "lost_cas": lost_cas,
        "verified": verified,
        "remaining": remaining,
        "stopped_on_cap": stopped_on_cap,
        "stopped_on_time_budget": stopped_on_time_budget,
        # gotcha #53: a run that did less than it could must not read the same as
        # a run with nothing left to do.
        "exhausted": remaining == 0 and not stopped_on_cap and not stopped_on_time_budget,
        "note": (
            f"{len(repointed)} re-pointed, {len(drifted)} refused by the gate, "
            f"{len(lost_cas)} lost the CAS. Re-invoke with the SAME plan_hash to continue."
        ),
    }


async def repair(session, apply: bool = False, plan_hash: Optional[str] = None) -> dict[str, Any]:
    """Entry point shared by the admin dispatcher and the CLI. Dry run by default."""
    if not apply:
        return await _dry_run(session)
    return await _apply_reviewed_plan(session, plan_hash)
