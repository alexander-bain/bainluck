"""Attended correction of `events.espn_id` — #1947 population 1, per SPEC-Q370.

Built because window 368 found the gap and `READY-lane1-369.md` named it:

    🔴 **Population 1 has NO APPLY PATH.** No attended consumer writes
    `events.espn_id`.

Same shape as the CREATE gap window 369 closed, one table over. This is the
FIFTH rail on the `ApplyPlan` pattern, with the primitives IMPORTED from
`app/utils/repair_apply_plan.py` and never re-implemented — the four before it
are `repair_pm_never_graded` (CAL-P058), `repair_event_team_binding` (#1798),
`create_events_from_truth` (#1979) and the mapping repair (queue 370).

## The two-call contract, unchanged from its siblings

    ?apply=false                -> derives, gates, persists the artifact, returns plan_hash
    ?apply=true&plan_hash=…     -> loads THAT artifact, writes ONLY its rows, re-derives nothing

`apply` with no presented hash is REFUSED, never re-derived (#1949). A work list
that can be recomputed at apply time is a work list that can differ from the
reviewed one, and no amount of after-measurement can tell you afterwards which
of the two you wrote.

## What is different here, and it is the interesting part

**The BEFORE state exists.** The CREATE rail had to put its compare inside the
`INSERT` because there was no row yet. This is an ordinary `UPDATE`, so:

    SELECT id, espn_id, commence_time FROM events WHERE id = :id FOR UPDATE;
    UPDATE events SET espn_id = :true
     WHERE id = :id AND espn_id = :wrong;      -- the compare is IN the write
    COMMIT;                                    -- per row: `events` is hot

`AND espn_id = :wrong` is the compare half. A check performed *before* the
statement is a read of a world the write then changes — #1798's defect restated
in the UPDATE direction. `rowcount == 0` is a NAMED finding, never a silent
success. `FOR UPDATE` is not the compare; it is what makes the zero-rowcount
case legible, by distinguishing "the id moved" from "the row is gone".

## One column. Only one.

`espn_id`. Not `status`, not the scores, not `completed_at`, not
`commence_time`. Ruling (a) withdrew the status/score half of the queue-368 plan
because those fields oscillate on a ~2-minute cycle and #1981's writer owns
them; a correction rail that also "tidied" them would be manufacturing a result
for a game that has not been played. `commence_time` is ADDRESSED (it is how a
reviewer knows which game a row is) and never WRITTEN.

**Correction, never deletion** (ruling 079). No branch of this rail deletes a row.

## Ruling 095 is a precondition, not a footnote

*A census of a moving population is fiction.* #1947's rows are the charter case:
they flapped on a ~2-minute cycle, and `15199901` moved its `commence_time`
sixteen hours between two reads fifty minutes apart. A census over that
population SUCCEEDS — it returns rows, mints an artifact, and digests stably,
because a digest over fiction is a perfectly good digest.

So `?apply=false` will not derive until stillness is PROVEN: N >= 3 probes
spanning > 300 s with identity unchanged. Probes are recorded by `?probe=true`,
which is cheap and returns immediately — the alternative, sleeping 300 s inside
the derive, is a request that times out and a rail nobody can run.

An unstill population produces a REFUSAL, not a smaller plan. Narrowing to the
rows that held still selects for rows *between writes* — a sample biased toward
looking calm.

## Concurrency, stated honestly

`ix_events_espn_id` is **NOT unique** (verified). The `AND espn_id = :wrong`
compare is a snapshot-time check that closes the review-to-apply window, which
is hours wide and is the real threat. It does **not** serialise against ordinary
ingest; a transaction-scoped advisory lock per event id serialises the rail
against ITSELF (two attended applies, one operator double-clicking). The
residual against live ingest is milliseconds against hours, and its outcome is a
*visible* wrong id rather than a lost row.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
import zlib
from typing import Any, Optional

from sqlalchemy import text

from app.utils.repair_apply_plan import (
    ESPN_ID_PLAN_SCHEMA,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_MISSING,
    REASON_PLAN_UNREADABLE,
    REASON_POPULATION_NOT_STILL,
    PlannedEspnIdCorrection,
    bind_apply,
    build_espn_id_correction_plan,
    decode_espn_id_correction_plan,
    espn_id_correction_gate,
    plan_reason_for_read,
    stillness_verdict,
)

logger = logging.getLogger(__name__)

ISSUE = "#1947"

#: Durable identity of the reviewed plan artifact. ONE slot per population, so a
#: mismatch fails loudly rather than finding a convenient older artifact still
#: lying around.
PLAN_IDENTITY_TEMPLATE = "repair:event_espn_id:apply_plan:pop{population}"

#: Where the stillness probes accumulate. Separate slot — a probe is evidence
#: ABOUT the population, not a plan over it, and overloading one slot would mean
#: a probe could evict an approved plan.
PROBE_IDENTITY_TEMPLATE = "repair:event_espn_id:stillness:pop{population}"
PROBE_SCHEMA = "event-espn-id-stillness-probe/v1"

#: Ruling 095's thresholds, named once.
MIN_STILLNESS_READS = 3
MIN_STILLNESS_SPAN_S = 300

#: The committed reviewed set per population. A registry rather than an f-string
#: so an unknown token is REFUSED BY NAME instead of resolving to a path that
#: does not exist and reporting it as a missing file.
REVIEWED_SET_REGISTRY: dict[str, str] = {
    "1": "app/data/event_espn_id_reviewed_pop1.json",
    # Population 2 — #1980, queue 380. The `frozen_final_scores` flow's OTHER
    # class, and the one its printed remedy could never fix: 17 settled MLB rows
    # whose `espn_id` names a neighbouring game of the same series (offset ±15 or
    # ±30 in ESPN id space — one or two slate-days) while `commence_time` matches
    # the true start TO THE MINUTE. **9 of the 17 already hold the correct final
    # score**, so the score remedy the flow printed on every one of these lines
    # would have overwritten a correct score with another game's.
    "2": "app/data/event_espn_id_reviewed_pop2.json",
}

REASON_UNKNOWN_POPULATION = "UNKNOWN_POPULATION"
REASON_REVIEWED_SET_MISSING = "REVIEWED_SET_MISSING"
REASON_REVIEWED_SET_CORRUPT = "REVIEWED_SET_CORRUPT"
REASON_REVIEWED_SET_UNREADABLE = "REVIEWED_SET_UNREADABLE"

#: `FOR UPDATE` locks the row and reads the world we are about to change. The
#: three columns are exactly the ones the gate asks about — reading more would
#: invite a later edit to start depending on a field outside the digest.
_LOCK_AND_READ_SQL = text(
    """
    SELECT id, espn_id, commence_time
      FROM events
     WHERE id = :event_id
       FOR UPDATE
    """
)

#: The compare IS the WHERE clause. Never a pre-check followed by a bare UPDATE.
_CORRECT_SQL = text(
    """
    UPDATE events
       SET espn_id = :true_espn_id
     WHERE id = :event_id
       AND espn_id = :wrong_espn_id
    """
)

_OBSERVE_SQL = text(
    """
    SELECT id, espn_id, commence_time
      FROM events
     WHERE id = ANY(:ids)
    """
)

#: Who ELSE holds a true id. `ix_events_espn_id` is non-unique, so the database
#: will not stop a second row taking it; this is the only place it can be caught.
_TRUE_ID_HOLDERS_SQL = text(
    """
    SELECT espn_id, id
      FROM events
     WHERE espn_id = ANY(:espn_ids)
    """
)

_ADVISORY_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:key)")


def _lock_key(event_id: int) -> int:
    """A stable 31-bit advisory-lock key for one event id.

    Computed in Python rather than with `hashtext` so the key is identical in a
    test double and in production, and so the rail does not depend on a Postgres
    internal whose hash is not contractual across versions. Namespaced by prefix
    so this rail's lock for event N cannot collide with the CREATE rail's lock
    for provider id N.
    """
    return int(zlib.crc32(f"espn_id:{int(event_id)}".encode("utf-8")) & 0x7FFFFFFF)


def _reviewed_set_path(population: str) -> Optional[pathlib.Path]:
    rel = REVIEWED_SET_REGISTRY.get(str(population))
    if rel is None:
        return None
    return pathlib.Path(__file__).resolve().parents[2] / rel


def _load_reviewed_set(population: str) -> tuple[Optional[dict], str]:
    """`(reviewed, reason)` — three named readings, never one flattened one.

    An operator told the reviewed set is MISSING will go and make one, and that
    is exactly the wrong move when the file is present and torn.
    """
    path = _reviewed_set_path(population)
    if path is None:
        return None, REASON_UNKNOWN_POPULATION
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None, REASON_REVIEWED_SET_MISSING
    except OSError as exc:  # permissions, I/O — "I could not read it right now"
        logger.warning("%s reviewed set unreadable: %s", ISSUE, type(exc).__name__)
        return None, REASON_REVIEWED_SET_UNREADABLE
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None, REASON_REVIEWED_SET_CORRUPT
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rows"), list):
        return None, REASON_REVIEWED_SET_CORRUPT
    return parsed, "ok"


def rows_from_reviewed(reviewed: dict) -> list[PlannedEspnIdCorrection]:
    """The reviewed triples, in reviewed order. Pure — no DB, no clock.

    Subscript, never `.get()`: a reviewed row missing a field must raise here,
    where it is a corrupt reviewed set, rather than decode as `None` and travel
    into a digest (the queue-368 `sport_id` lesson).
    """
    out: list[PlannedEspnIdCorrection] = []
    for row in reviewed["rows"]:
        out.append(
            PlannedEspnIdCorrection(
                event_id=int(row["event_id"]),
                wrong_espn_id=str(row["wrong_espn_id"]),
                true_espn_id=str(row["true_espn_id"]),
                our_commence_time=str(row["our_commence_time"]),
                matchup=row.get("matchup"),
            )
        )
    return out


async def _save(identity: str, schema: str, payload: dict) -> tuple[bool, str]:
    """Persist to the durable snapshot rail. `(ok, note)` — never eaten.

    Not Redis, for CAL-P058's reason: a SETEX on an allkeys-lru instance can be
    evicted, and an operator who cannot be handed a hash must be TOLD so, because
    the next thing they will do is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=identity,
                schema_version=schema,
                payload=payload,
                complete=True,
                source="repair:event-espn-id",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"persist rejected: {result.get('status')}"


async def _read(identity: str, schema: str, max_age_s: int):
    """`(payload, reason)` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        got = await read_snapshot_standalone(
            identity, expected_version=schema, max_age_s=max_age_s
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, plan_reason_for_read(got.status, error_class=got.error_class)
    return got.envelope.payload, "ok"


async def _observe(session, event_ids) -> dict[int, dict[str, Any] | None]:
    """Current identity of each reviewed event. `None` for an id with no row."""
    ids = [int(i) for i in event_ids]
    observed: dict[int, dict[str, Any] | None] = {i: None for i in ids}
    if not ids:
        return observed
    for row in (await session.execute(_OBSERVE_SQL, {"ids": ids})).all():
        observed[int(row[0])] = {
            "espn_id": None if row[1] is None else str(row[1]),
            "commence_time": None if row[2] is None else str(row[2]),
        }
    return observed


async def _true_id_holders(session, espn_ids) -> dict[str, list[int]]:
    ids = sorted({str(i) for i in espn_ids})
    holders: dict[str, list[int]] = {}
    if not ids:
        return holders
    for row in (await session.execute(_TRUE_ID_HOLDERS_SQL, {"espn_ids": ids})).all():
        holders.setdefault(str(row[0]), []).append(int(row[1]))
    return holders


# ---------------------------------------------------------------------------
# Stillness (ruling 095)
# ---------------------------------------------------------------------------


async def _record_probe(session, population: str, now: float) -> dict[str, Any]:
    """One identity read of the whole reviewed population, appended to the slot."""
    reviewed, reason = _load_reviewed_set(population)
    if reviewed is None:
        return {
            "issue": ISSUE, "probe": True, "refused": True,
            "reason_codes": [reason],
            "reviewed_set_path": REVIEWED_SET_REGISTRY.get(str(population)),
        }

    rows = rows_from_reviewed(reviewed)
    observed = await _observe(session, [r.event_id for r in rows])

    identity = PROBE_IDENTITY_TEMPLATE.format(population=population)
    prior, _ = await _read(identity, PROBE_SCHEMA, max_age_s=86400)
    probes = list((prior or {}).get("probes") or [])
    probes.append(
        {"at": float(now), "rows": {str(k): v for k, v in observed.items()}}
    )
    # Keep a bounded window. Old probes cannot prove present stillness, and an
    # unbounded list would let a 3-day-old read satisfy the span requirement.
    probes = [p for p in probes if float(now) - float(p.get("at", 0)) <= 3600][-24:]

    saved, note = await _save(identity, PROBE_SCHEMA, {"probes": probes})
    still, detail = stillness_verdict(
        probes, min_reads=MIN_STILLNESS_READS, min_span_s=MIN_STILLNESS_SPAN_S
    )
    return {
        "issue": ISSUE,
        "probe": True,
        "population": population,
        "probe_persisted": saved,
        "probe_note": note,
        "stillness": {"still": still, **detail},
        "observed": {str(k): v for k, v in observed.items()},
        "note": (
            f"Probe recorded. Ruling 095 needs >= {MIN_STILLNESS_READS} reads spanning "
            f"> {MIN_STILLNESS_SPAN_S}s with identity unchanged before a derive is "
            "allowed. Probes older than 1h are dropped — an old read cannot prove "
            "present stillness."
        ),
    }


async def _stillness(population: str, now: float) -> tuple[bool, dict[str, Any]]:
    identity = PROBE_IDENTITY_TEMPLATE.format(population=population)
    payload, _reason = await _read(identity, PROBE_SCHEMA, max_age_s=86400)
    probes = [
        p for p in list((payload or {}).get("probes") or [])
        if float(now) - float(p.get("at", 0)) <= 3600
    ]
    return stillness_verdict(
        probes, min_reads=MIN_STILLNESS_READS, min_span_s=MIN_STILLNESS_SPAN_S
    )


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


async def _apply_reviewed_plan(
    session, plan_hash: Optional[str], population: str
) -> dict[str, Any]:
    """Write EXACTLY the reviewed rows, or refuse by name. Never re-derives."""
    identity = PLAN_IDENTITY_TEMPLATE.format(population=population)
    payload, read_reason = await _read(identity, ESPN_ID_PLAN_SCHEMA, max_age_s=14 * 86400)
    if payload is None:
        plan, reason = None, read_reason
    else:
        plan, reason = decode_espn_id_correction_plan(payload)

    ok, refusals = bind_apply(plan, decode_reason=reason, presented_hash=plan_hash)
    if not ok:
        return {
            "issue": ISSUE,
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": refusals,
            "presented_plan_hash": plan_hash,
            "artifact_plan_hash": plan.plan_hash if plan is not None else None,
            "artifact_note": reason,
            "note": (
                "Nothing was written. Re-run with apply=false to produce a plan, read "
                "it, then pass its plan_hash back. `apply` without a presented hash is "
                "refused, never re-derived."
            ),
        }

    observed = await _observe(session, plan.event_ids)
    holders = await _true_id_holders(session, [r.true_espn_id for r in plan.rows])
    actionable, retired = espn_id_correction_gate(
        plan, observed, true_id_holders=holders
    )

    # Structural assertion BEFORE the loop, while nothing has been written: prove
    # the write set is a SUBSET of the approved set. This rail commits per row
    # (`events` is hot), so a post-hoc discovery would have nothing left to roll
    # back — the binding rail can check afterwards only because it commits once.
    approved = set(plan.row_keys)
    outside = sorted({r.row_key for r in actionable} - approved)
    if outside:
        return {
            "issue": ISSUE,
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": ["MUTATION_OUTSIDE_APPROVED_SET"],
            "outside_approved": outside,
            "note": "Refused before any write. This is a bug in the gate, not in the world.",
        }

    corrected: list[dict[str, Any]] = []
    no_op: list[dict[str, Any]] = []
    for row in actionable:
        async with session.begin_nested():
            # Serialises the rail against ITSELF. Transaction-scoped, so it is
            # released by the commit below without a separate unlock.
            await session.execute(_ADVISORY_LOCK_SQL, {"key": _lock_key(row.event_id)})
            locked = (
                await session.execute(_LOCK_AND_READ_SQL, {"event_id": int(row.event_id)})
            ).first()
            if locked is None:
                # Between the gate and the lock. Named, not silent.
                no_op.append(
                    {
                        "event_id": int(row.event_id),
                        "reason_code": "EVENT_ROW_ABSENT",
                        "rowcount": 0,
                    }
                )
                continue
            result = await session.execute(
                _CORRECT_SQL,
                {
                    "event_id": int(row.event_id),
                    "true_espn_id": str(row.true_espn_id),
                    "wrong_espn_id": str(row.wrong_espn_id),
                },
            )
            if result.rowcount == 1:
                corrected.append(
                    {
                        "event_id": int(row.event_id),
                        "from": str(row.wrong_espn_id),
                        "to": str(row.true_espn_id),
                        "matchup": row.matchup,
                    }
                )
            else:
                # `rowcount == 0` is a FINDING. `FOR UPDATE` above is what makes
                # it legible: the row is present, so the id moved between the
                # gate and the write.
                no_op.append(
                    {
                        "event_id": int(row.event_id),
                        "reason_code": "ESPN_ID_MOVED",
                        "observed_espn_id": None if locked[1] is None else str(locked[1]),
                        "rowcount": int(result.rowcount or 0),
                    }
                )
        await session.commit()  # per row: `events` is hot

    # After-verification IN THE SAME RUN, re-reading the plan's own event ids.
    # A rail that reports only what it INTENDED is the claim-not-execution class.
    after = await _observe(session, plan.event_ids)
    after_holders = await _true_id_holders(session, [r.true_espn_id for r in plan.rows])
    still_wrong = [
        int(r.event_id)
        for r in plan.rows
        if (after.get(int(r.event_id)) or {}).get("espn_id") == str(r.wrong_espn_id)
    ]
    duplicated = {
        eid: sorted(holders_)
        for eid, holders_ in after_holders.items()
        if len(holders_) > 1
    }

    return {
        "issue": ISSUE,
        "apply": True,
        "applied": True,
        "population": population,
        "plan_hash": plan.plan_hash,
        "plan_rows": len(plan.rows),
        "corrected": corrected,
        "corrected_count": len(corrected),
        "retired": retired,
        "retired_count": len(retired),
        "no_op": no_op,
        "after_verification": {
            "by_event": {
                str(k): (v or {}).get("espn_id") for k, v in sorted(after.items())
            },
            "still_holding_wrong_id": still_wrong,
            "true_espn_ids_held_by_more_than_one_row": duplicated,
        },
        "note": (
            "Bound to the reviewed plan: no derivation ran on this path, the compare is "
            "inside the UPDATE rather than in front of it, each row commits alone, and "
            "verification re-read the plan's own event ids. Retired rows are NAMED and "
            "their siblings were written — one upstream repair does not cancel the set. "
            "Re-invoke with the SAME plan_hash to continue; the gate makes it resumable."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    plan_hash: Optional[str] = None,
    population: str = "1",
    probe: bool = False,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Correct `events.espn_id` for a reviewed population (#1947, SPEC-Q370).

    Args:
        apply: False (default) derives and persists a plan. True consumes one.
        plan_hash: content address of the reviewed dry run. REQUIRED when `apply`.
        population: which REVIEWED SET this call is bound to. `"1"` is the five
            contaminated rows of `population_1_CORRECT`.
        probe: record one stillness observation and return. Ruling 095's
            precondition — see the module docstring for why this is a separate
            call rather than a sleep inside the derive.
        now: injected clock for tests. Production passes nothing.
    """
    population = str(population)
    clock = time.time() if now is None else float(now)

    if population not in REVIEWED_SET_REGISTRY:
        return {
            "issue": ISSUE,
            "refused": True,
            "reason_codes": [REASON_UNKNOWN_POPULATION],
            "note": (
                f"population must be one of {sorted(REVIEWED_SET_REGISTRY)}, "
                f"got {population!r}"
            ),
        }

    if probe:
        return await _record_probe(session, population, clock)

    if apply:
        # The derivation below does not run on this path. That is the pattern.
        return await _apply_reviewed_plan(session, plan_hash, population)

    reviewed, reason = _load_reviewed_set(population)
    if reviewed is None:
        return {
            "issue": ISSUE,
            "apply": False,
            "refused": True,
            "reason_codes": [reason],
            "reviewed_set_path": REVIEWED_SET_REGISTRY.get(population),
            "note": (
                "No plan was derived. MISSING means the reviewed set is not deployed; "
                "CORRUPT means it is there and cannot be trusted — do NOT regenerate "
                "it, investigate; UNREADABLE means the read failed right now."
            ),
        }

    still, stillness = await _stillness(population, clock)
    if not still:
        return {
            "issue": ISSUE,
            "apply": False,
            "refused": True,
            "reason_codes": [REASON_POPULATION_NOT_STILL],
            "stillness": stillness,
            "note": (
                "Ruling 095: a census of a moving population is fiction, and it fails "
                "INVISIBLY — such a census returns rows, mints an artifact and digests "
                "stably. Run ?probe=true at least "
                f"{MIN_STILLNESS_READS} times spanning > {MIN_STILLNESS_SPAN_S}s first. "
                "If `moved_event_ids` is non-empty the population is being written and "
                "the answer is NOT to narrow to the rows that held still — that selects "
                "for rows between writes."
            ),
        }

    try:
        rows = rows_from_reviewed(reviewed)
    except (KeyError, TypeError, ValueError):
        return {
            "issue": ISSUE,
            "apply": False,
            "refused": True,
            "reason_codes": [REASON_REVIEWED_SET_CORRUPT],
            "note": "A reviewed row is missing a field the digest addresses.",
        }

    observed = await _observe(session, [r.event_id for r in rows])
    holders = await _true_id_holders(session, [r.true_espn_id for r in rows])

    plan = build_espn_id_correction_plan(
        rows,
        context={
            "issue": ISSUE,
            "population": population,
            "reviewed_at": reviewed.get("reviewed_at"),
            "source_artifact": reviewed.get("source_artifact"),
            # NO `ruling` KEY, DELIBERATELY (ruling 092). A deriver may not emit a
            # credential it cannot cite: an inherited "Alex approved" is a FORGED
            # credential, and worse than none, because a missing one prompts the
            # question and a forged one answers it. Approval provenance is recorded
            # ON the artifact by whoever takes the MC. `context` is outside
            # `plan_hash`, so recording it later never re-addresses a reviewed plan.
        },
    )
    actionable, retired = espn_id_correction_gate(
        plan, observed, true_id_holders=holders
    )
    saved, save_note = await _save(
        PLAN_IDENTITY_TEMPLATE.format(population=population),
        ESPN_ID_PLAN_SCHEMA,
        plan.as_payload(),
    )

    return {
        "issue": ISSUE,
        "apply": False,
        "population": population,
        "plan_hash": plan.plan_hash if saved else None,
        "plan_persisted": saved,
        "plan_note": save_note,
        "plan_rows": len(plan.rows),
        "schema": ESPN_ID_PLAN_SCHEMA,
        "stillness": stillness,
        "census": {
            "reviewed": len(plan.rows),
            "actionable": len(actionable),
            "retired": len(retired),
        },
        "actionable": [r.as_payload() for r in actionable],
        "retired": retired,
        "duplicate_event_ids": plan.duplicate_event_ids(),
        "self_pointing_event_ids": plan.self_pointing_rows(),
        "colliding_true_espn_ids": plan.colliding_true_ids(),
        "apply_command": (
            f"POST …/repairs/event-espn-id?apply=true&population={population}"
            f"&plan_hash={plan.plan_hash}"
            if saved
            else "NO PLAN HASH — the artifact did not persist; an apply would be refused"
        ),
        "ledger": [r.as_payload() for r in plan.rows],
        "note": (
            "Dry run only — this path cannot write a row. `actionable` is what an apply "
            "would change; `retired` names, per row, why the rest would not, and a "
            "retirement is not fatal to its siblings. ESPN_ID_ALREADY_CORRECT means the "
            "ordinary pipeline got there first — that row is DONE, not drifted."
        ),
    }
