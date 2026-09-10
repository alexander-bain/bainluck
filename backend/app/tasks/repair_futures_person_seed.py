"""#4578 — delete the market legs that `seed_persons_from_futures_fields` minted as people.

    POST /api/admin/repairs/futures-person-seed-purge                      # dry run
    POST /api/admin/repairs/futures-person-seed-purge?apply=true&plan_hash=…
    POST /api/admin/repairs/futures-person-seed-purge?apply=true&undo_identity=…   # undo

`seed_persons_from_futures_fields` reads its names from `futures_outcomes.name`
on the premise that golf and motorsport entrant fields are unambiguously people.
Measured on production 2026-09-10, that premise is false for 4,913 of the 7,471
persons it produced: margin ladders ("1+ strokes", "Above 13500"), head-to-head
legs ("Jon Rahm beats McIlroy and Spieth"), and scoring placeholders ("Cut Line:
Even par (E)").

The reader-facing consequence is alias collapse. `player_key` takes the last
token, so **1,450** of these share the derived alias `strokes` and **1,124**
share `round`, and `resolve_alias` settles a collision by "highest confidence,
tie-break by entity id" with no signal to the caller — a mention resolves to one
arbitrary member. The head-to-head rows are worse than arbitrary: one `person`
row for "Jon Rahm beats McIlroy and Spieth" mints the aliases `mcilroy` and
`spieth`, pointing two distinct players at a composite that is neither.

#4458 shipped the prevention (`is_plausible_person_name`, refused at seed time).
This is the BACKWARD half, and it does not race the forward one: every
`kind='person'` row in production carries `created_at` on a single day,
2026-07-13, so nothing has minted one in two months. That check is not
ceremonial — CAL-P1004 spent three weeks draining a population its own live poll
was refilling every two hours (#4604), and the only thing that distinguishes
this repair from that one is having asked.

🔴 THE COHORT IS DERIVED BY THE SHIPPED PREDICATE, NEVER BY SQL THAT LOOKS LIKE IT.
#4578's filing counts the cohort with a SQL proxy — digit / " beats " / " vs " —
and gets 4,913 (65.8 %). Running the same rows through
:func:`is_plausible_person_name` refuses 67.2 %. The two disagree because the
predicate normalises first (`normalize_alias`), also refuses `len < 3` and a
closed list of field words, and the marker test is padded. A repair whose
membership rule is a re-statement of the guard's rule is a repair that deletes a
different set than the guard would refuse, and the difference is invisible until
it is a restore. So the rows come back from Postgres unfiltered and Python
decides, using the imported guard — this module contains no membership rule of
its own, and a test asserts it never grows one.

Reversal (D51): the apply stages an undo receipt carrying every deleted
`entities` row, every `entity_aliases` row that CASCADE would take with it, and
every `event_participants.entity_id` it clears, in the SAME transaction as the
delete. Nothing written and nothing claimed is the only state needing no
reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ISSUE = "#4578"

#: The seed marker `_upsert_person` stamps. Matched exactly, never with LIKE: a
#: prefix match would also take `seed_persons_events`, which is the CONTROL
#: population — 7,209 real competitors, of which the guard refuses 0 in a random
#: 1,000. Deleting the control is the one mistake this repair could make that no
#: alias count would reveal.
SEED_SOURCE = "seed_persons_futures"

PLAN_IDENTITY = "repair:futures_person_seed:apply_plan"
PLAN_SCHEMA = "futures-person-seed-plan/v1"
UNDO_SCHEMA = "futures-person-seed-undo/v1"
UNDO_OWNER_KEY = "invocation"

#: A year. The undo record's whole reason to exist is being readable long after
#: the apply, so it must outlive every default freshness bound in the store.
UNDO_MAX_AGE_S = 365 * 86400

#: Rows per apply. The cohort is ~4.9k and the receipt carries every deleted row
#: plus its aliases, so one call is a several-MB envelope; capping keeps the
#: receipt readable and the transaction short. The walk is a keyset on
#: `entities.id` and the population shrinks as it drains, so re-invoking until
#: `scan_exhausted` is the intended use.
APPLY_CAP = 1500

REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"
REASON_UNDO_UNREADABLE = "UNDO_UNREADABLE"


# --- membership --------------------------------------------------------------

#: Every seeded person, unfiltered. The WHERE clause selects the SEED, not the
#: defect — see the module docstring. `entity_metadata->>'seed_source'` is a
#: JSONB text extraction, so the comparison is a plain string equality.
_COHORT_SQL = text(
    """
    SELECT e.id, e.canonical_name, e.slug, e.kind, e.sport_id, e.sport_key,
           e.external_ref, e.entity_metadata, e.created_at,
           e.source_team_id, e.date_window_start, e.date_window_end,
           e.confidence
      FROM entities e
     WHERE e.kind = 'person'
       AND e.entity_metadata->>'seed_source' = :seed_source
       AND e.id > :after_id
     ORDER BY e.id
     LIMIT :scan_limit
    """
)


def refused_rows(rows: list[Any]) -> list[Any]:
    """The members of ``rows`` the shipped guard would not have seeded.

    Separated from the query so membership is testable without a database, and
    imported rather than restated so it cannot drift from the seed-time refusal.
    """
    from app.services.entity_registry import is_plausible_person_name

    return [r for r in rows if not is_plausible_person_name(r.canonical_name or "")]


def plan_hash_for(ids: list[int]) -> str:
    """Content address of a planned id set.

    Over the SORTED ids and nothing else: the apply's job is to act on the rows
    an operator reviewed, and a hash that moved with a name or a timestamp would
    refuse a plan whose membership had not changed.
    """
    body = json.dumps(sorted(int(i) for i in ids), separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def new_invocation() -> str:
    return secrets.token_hex(8)


def undo_identity_for(plan_hash: str, *, at: datetime, invocation: str) -> str:
    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"repair:futures_person_seed:undo:{stamp}:{plan_hash}:{invocation}"


def restore_command(identity: str) -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        "source ~/.claude/.env && curl -s -X POST -H "
        '"Authorization: Bearer $ADMIN_TOKEN" '
        f'"$BAINLUCK_API/api/admin/repairs/futures-person-seed-purge'
        f'?apply=true&undo_identity={identity}"'
    )


# --- durable receipt ---------------------------------------------------------


def _undo_envelope(identity: str, payload: dict[str, Any]):
    from app.utils.durable_state import DurableEnvelope

    return DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        payload=payload,
        # A property of the ARTIFACT ("this record was fully written"), not of
        # the run. `decode_envelope` types any incomplete envelope as MALFORMED,
        # so a partial run's receipt would be unreadable — unreachable reversal
        # for exactly the runs most likely to need it (CERT-1979).
        complete=True,
        source="repair:futures-person-seed-purge:undo",
    )


async def _save_undo_co_commit(session, identity: str, payload: dict[str, Any]):
    """Stage the receipt in the caller's OPEN transaction.

    Writing it on its own connection could only happen before or after the
    delete, and both orders are a lie waiting for a crash: before, the record
    claims rows that may roll back; after, a durable delete may have no record.
    """
    from app.services.durable_snapshots import publish_owned_snapshot_in_txn

    return await publish_owned_snapshot_in_txn(
        session,
        _undo_envelope(identity, payload),
        owner_key=UNDO_OWNER_KEY,
        owner=payload[UNDO_OWNER_KEY],
    )


async def _read_undo(identity: str) -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        got = await read_snapshot_standalone(
            identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
        )
    except Exception:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("%s undo read raised for %s", ISSUE, identity)
        return None, REASON_UNDO_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_UNDO_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


# --- census ------------------------------------------------------------------


def _alias_collapse(rows: list[Any]) -> dict[str, int]:
    """The top derived-alias collisions among the refused rows.

    This is the reader harm restated as a number, and it is the one figure an
    operator should read before applying: if `strokes` and `round` are not at
    the head of this list, the cohort is not the one #4578 measured.
    """
    from app.utils.event_matcher import player_key

    counts: dict[str, int] = {}
    for r in rows:
        key = player_key(r.canonical_name or "") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {k: v for k, v in top}


async def _participants_for(session, ids: list[int]) -> list[Any]:
    """`event_participants` rows pointing at the cohort.

    No FK holds this column — `models.py` says so explicitly, "no FK because the
    id space depends on the type" — so a delete leaves a DANGLING pointer that
    `ix_event_participant_entity` would answer "every event this player is in"
    with. `entity_name` is denormalised and never NULL, so nothing goes blank on
    a card; this degrades a join, not a render, which is why it is cleared
    rather than treated as a blocker.
    """
    if not ids:
        return []
    return (
        await session.execute(
            text(
                """
                SELECT id, entity_id, entity_type, entity_name
                  FROM event_participants
                 WHERE entity_type = 'person'
                   AND entity_id = ANY(:ids)
                 ORDER BY id
                """
            ),
            {"ids": ids},
        )
    ).fetchall()


async def _aliases_for(session, ids: list[int]) -> list[Any]:
    if not ids:
        return []
    return (
        await session.execute(
            text(
                """
                SELECT id, entity_id, alias, alias_norm, alias_type, source,
                       confidence, created_at
                  FROM entity_aliases
                 WHERE entity_id = ANY(:ids)
                 ORDER BY id
                """
            ),
            {"ids": ids},
        )
    ).fetchall()


async def _derive(session, after_id: int, scan_limit: int) -> dict[str, Any]:
    rows = (
        await session.execute(
            _COHORT_SQL,
            {
                "seed_source": SEED_SOURCE,
                "after_id": after_id,
                "scan_limit": scan_limit,
            },
        )
    ).fetchall()
    refused = refused_rows(rows)
    ids = [int(r.id) for r in refused]
    return {
        "scanned": len(rows),
        "scan_exhausted": len(rows) < scan_limit,
        "next_after_id": int(rows[-1].id) if rows else after_id,
        "kept": len(rows) - len(refused),
        "refused": refused,
        "ids": ids,
        "plan_hash": plan_hash_for(ids),
        "alias_collapse": _alias_collapse(refused),
        "samples": [r.canonical_name for r in refused[:8]],
    }


# --- entry point -------------------------------------------------------------


async def repair(
    db,
    apply: bool = False,
    *,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
    plan_hash: Optional[str] = None,
    undo_identity: Optional[str] = None,
) -> dict[str, Any]:
    """Dry-run census, plan-bound apply, or reversal. See the module docstring."""
    if undo_identity:
        return await _undo(db, apply, undo_identity)

    scan_limit = min(int(limit or APPLY_CAP), APPLY_CAP)
    cursor = int(after_id or 0)
    derived = await _derive(db, cursor, scan_limit)

    census = {
        "issue": ISSUE,
        "scanned": derived["scanned"],
        "would_delete": len(derived["ids"]),
        "kept_as_people": derived["kept"],
        "scan_exhausted": derived["scan_exhausted"],
        "next_after_id": derived["next_after_id"],
        "plan_hash": derived["plan_hash"],
        "alias_collapse_top": derived["alias_collapse"],
        "samples": derived["samples"],
    }

    if not apply:
        census["apply_hint"] = (
            "re-invoke with ?apply=true&plan_hash=" + derived["plan_hash"]
        )
        return census

    # An apply acts on the plan an operator READ. Re-deriving and acting on
    # whatever comes back is how a reviewed plan becomes an unreviewed one.
    if not plan_hash:
        census["refused"] = "PLAN_HASH_REQUIRED"
        return census
    if plan_hash != derived["plan_hash"]:
        census["refused"] = "PLAN_STALE"
        census["submitted_plan_hash"] = plan_hash
        return census
    if not derived["ids"]:
        census["applied"] = 0
        census["note"] = "nothing to delete in this page"
        return census

    ids = derived["ids"]
    aliases = await _aliases_for(db, ids)
    participants = await _participants_for(db, ids)

    invocation = new_invocation()
    taken_at = datetime.now(timezone.utc)
    identity = undo_identity_for(
        derived["plan_hash"], at=taken_at, invocation=invocation
    )
    payload = {
        UNDO_OWNER_KEY: invocation,
        "issue": ISSUE,
        "taken_at": taken_at.isoformat(),
        "plan_hash": derived["plan_hash"],
        "entities": [
            {
                "id": int(r.id),
                "kind": r.kind,
                "canonical_name": r.canonical_name,
                "slug": r.slug,
                "sport_id": int(r.sport_id) if r.sport_id is not None else None,
                "sport_key": r.sport_key,
                "external_ref": r.external_ref,
                "entity_metadata": r.entity_metadata,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                # Every remaining column, whether or not this cohort populates
                # it. A restore is judged on the row it puts back, not on the
                # columns the delete happened to look at.
                "source_team_id": (
                    int(r.source_team_id) if r.source_team_id is not None else None
                ),
                "date_window_start": (
                    r.date_window_start.isoformat() if r.date_window_start else None
                ),
                "date_window_end": (
                    r.date_window_end.isoformat() if r.date_window_end else None
                ),
                "confidence": (
                    float(r.confidence) if r.confidence is not None else None
                ),
            }
            for r in derived["refused"]
        ],
        # CASCADE takes these with the entity, so after the delete there is
        # nothing left to reconstruct them from. A backup of `entities` alone is
        # not a restore, it is half of one.
        "aliases": [
            {
                "id": int(a.id),
                "entity_id": int(a.entity_id),
                "alias": a.alias,
                "alias_norm": a.alias_norm,
                # NOT NULL in `models.py`. Omitting it made the restore INSERT
                # fail on the one path nobody exercises until it is needed, so
                # every non-nullable column of both tables is carried, not just
                # the ones the delete happens to read.
                "alias_type": a.alias_type,
                "source": a.source,
                "confidence": float(a.confidence) if a.confidence is not None else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in aliases
        ],
        "participants": [
            {"id": int(p.id), "entity_id": int(p.entity_id)} for p in participants
        ],
    }

    staged = await _save_undo_co_commit(db, identity, payload)
    if staged.get("status") != "ok":
        await db.rollback()
        census["refused"] = "UNDO_NOT_PERSISTED"
        census["undo_status"] = staged.get("status")
        return census

    if participants:
        await db.execute(
            text(
                "UPDATE event_participants SET entity_id = NULL "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [int(p.id) for p in participants]},
        )
    deleted = (
        await db.execute(
            text("DELETE FROM entities WHERE id = ANY(:ids)"), {"ids": ids}
        )
    ).rowcount
    await db.commit()

    logger.info(
        "%s purged %s seeded non-person entities (%s aliases, %s participants "
        "cleared) — undo %s",
        ISSUE, deleted, len(aliases), len(participants), identity,
    )
    census["applied"] = int(deleted)
    census["aliases_cascaded"] = len(aliases)
    census["participants_cleared"] = len(participants)
    census["undo_identity"] = identity
    census["restore_command"] = restore_command(identity)
    return census


async def _undo(db, apply: bool, identity: str) -> dict[str, Any]:
    """Put one earlier apply's rows back. Dry-run unless ``apply``."""
    payload, reason = await _read_undo(identity)
    if payload is None:
        return {"issue": ISSUE, "undo_identity": identity, "refused": reason}

    entities = payload.get("entities") or []
    aliases = payload.get("aliases") or []
    participants = payload.get("participants") or []
    out = {
        "issue": ISSUE,
        "undo_identity": identity,
        "would_restore_entities": len(entities),
        "would_restore_aliases": len(aliases),
        "would_restore_participants": len(participants),
        "taken_at": payload.get("taken_at"),
    }
    if not apply:
        out["apply_hint"] = "re-invoke with &apply=true"
        return out

    # Original ids on purpose: `event_participants.entity_id` and any stamped
    # `entity:<id>` reference point at the OLD id, so a restore that let the
    # sequence mint new ones would put the rows back where nothing looks. Every
    # id is below the sequence's current value, so no bump is owed.
    #
    # MEASURED against production DDL 2026-09-09, because an explicit-id INSERT
    # is refused outright by an identity column and this is the one path nobody
    # exercises until they need it: `information_schema.columns` reports
    # `is_identity='NO'` with `nextval('entities_id_seq')` for `entities.id` and
    # `nextval('entity_aliases_id_seq')` for `entity_aliases.id` — plain
    # serials, so supplying the id is allowed. Both tables' NOT NULL columns are
    # named in the INSERTs above (`kind`, `canonical_name`; `entity_id`,
    # `alias`, `alias_norm`, `alias_type`). `updated_at` is deliberately left to
    # its `now()` default: the row IS being written now, and forging the old
    # stamp would claim an observation that did not happen.
    for e in entities:
        await db.execute(
            text(
                """
                INSERT INTO entities
                    (id, kind, canonical_name, slug, sport_id, sport_key,
                     external_ref, entity_metadata, created_at,
                     source_team_id, date_window_start, date_window_end,
                     confidence)
                VALUES
                    (:id, :kind, :canonical_name, :slug, :sport_id, :sport_key,
                     :external_ref, CAST(:entity_metadata AS JSONB),
                     COALESCE(CAST(:created_at AS timestamptz), NOW()),
                     :source_team_id, CAST(:date_window_start AS date),
                     CAST(:date_window_end AS date), :confidence)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {**e, "entity_metadata": json.dumps(e.get("entity_metadata"))},
        )
    for a in aliases:
        await db.execute(
            text(
                """
                INSERT INTO entity_aliases
                    (id, entity_id, alias, alias_norm, alias_type, source,
                     confidence, created_at)
                VALUES
                    (:id, :entity_id, :alias, :alias_norm, :alias_type, :source,
                     :confidence,
                     COALESCE(CAST(:created_at AS timestamptz), NOW()))
                ON CONFLICT (id) DO NOTHING
                """
            ),
            a,
        )
    for p in participants:
        await db.execute(
            text(
                "UPDATE event_participants SET entity_id = :entity_id "
                "WHERE id = :id AND entity_id IS NULL"
            ),
            p,
        )
    await db.commit()

    out["restored_entities"] = len(entities)
    out["restored_aliases"] = len(aliases)
    out["restored_participants"] = len(participants)
    logger.info("%s reversed apply %s", ISSUE, identity)
    return out
