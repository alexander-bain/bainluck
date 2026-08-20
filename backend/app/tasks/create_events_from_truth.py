"""The attended CREATE consumer (#1796/#1902, queue 369). The apply path that never existed.

WHAT THIS IS, AND WHY IT IS BEING WRITTEN NOW RATHER THAN CITED

Queue 363 built the CREATE plan object. Queue 364 fixed its address scheme. Queue
368 put ``sport_id`` inside the address. Three windows of work on an artifact, and
two populations sat GREEN and approved waiting to be applied — against a consumer
that **did not exist on any branch**. Not on #1971, not on #1827, not on #1801, not
on any remote ref: every ``decode_create_plan`` call site in the tree was the
definition module, the deriver, or a test. The certification could not certify an
apply path, because there was no apply path. That is the claim-not-execution class,
and this module is the correction.

THE SHAPE, WHICH IS THE ONE ALREADY CERTIFIED ON TWO RAILS

    POST /api/admin/repairs/event-create-from-truth?apply=false&population=2
        -> derives the plan from the COMMITTED reviewed truth set, runs the live
           gate, persists the artifact, returns ``plan_hash``
    POST /api/admin/repairs/event-create-from-truth?apply=true&plan_hash=<hash>
        -> loads THAT artifact, writes ONLY its rows, re-derives nothing

Same contract as ``repair_event_team_binding`` (#1798) and
``repair_pm_never_graded`` (CAL-P065), and the primitives are theirs — imported,
not re-implemented.

HOW A CREATE DIFFERS FROM THE TWO UPDATE RAILS, AND WHAT FOLLOWS FROM IT

**The before state is ABSENCE.** There is no ``expected_before_id`` to compare,
because the row being compared does not exist. So the compare half of the
compare-and-set is the EXISTENCE CHECK, and it must sit inside the writing
statement rather than in front of it:

    INSERT INTO events (…) SELECT … WHERE NOT EXISTS (SELECT 1 FROM events
                                                       WHERE espn_id = :truth_id)

``rowcount == 0`` is then a finding — :data:`REASON_TRUTH_ID_PRESENT` — and never a
silent success. A check performed BEFORE the statement is a read of a world the
write then changes, which is #1798's defect restated in the create direction.

Two rules inherited from what the population-2 census cost to learn:

1. **Keyed on the truth id, never on (clubs, date).** A doubleheader is two real
   games with identical clubs on an identical date, and the 328-game set contains
   them. An existence check keyed on the matchup would refuse the second game of a
   twin bill as a duplicate of the first. The row key is ``espn:<id>`` throughout.
2. **The reviewed object is a SET OF IDS, not a count.** A count is a claim about
   the world's current state that the ordinary pipeline repairs on its own, so it
   expires while nothing is wrong — the measured Aug 10-12 ``2/14 -> 16/0``
   inversion. :func:`create_gate` compares SETS, and an id that has since been
   created retires THAT ROW ONLY. One upstream create must not cancel 327 approved
   siblings.

THE THREE READ REFUSALS ARE THREE, NOT ONE (gotcha #53, C-APPLY-PRE-R2 finding 1)

``PLAN_ARTIFACT_MISSING`` says the plan never existed and the correct next move is
to make one. ``PLAN_ARTIFACT_CORRUPT`` says an artifact IS there and cannot be
trusted — do not regenerate, investigate. ``PLAN_ARTIFACT_UNREADABLE`` says the
store could not be read right now. Telling an operator MISSING during a store
outage sends them to regenerate the plan, which is the one action that destroys the
evidence. The classification is not re-derived here: it comes from
:func:`plan_reason_for_read` over the durable layer's own status.

WHAT IT REFUSES TO INVENT

The insert writes SEVEN columns — sport, provider id, both club anchors, both club
names, kickoff — plus ``status='scheduled'``. Nothing else. Scores, opening lines,
EI, normalized names and alt-names are the ordinary pipeline's to fill, and a
create rail that guessed at them would be manufacturing history for a game that has
not been played. Correction, never invention.

CONCURRENCY, STATED HONESTLY RATHER THAN IMPLIED

``events.espn_id`` is indexed but **not unique** (``ix_events_espn_id``, non-unique).
So ``WHERE NOT EXISTS`` is a snapshot-time check: it closes the review-to-apply
window, which is hours wide and is the actual threat, but two writers inside the
same instant could both pass it. This rail therefore takes a transaction-scoped
advisory lock per truth id, which serialises it against ITSELF — two attended
applies, or one operator double-clicking. It does NOT serialise against the
ordinary ingest pipeline; nothing short of a unique index does, and that needs a
migration slot this lane does not own (#1946 has the same dependency). The residual
window is milliseconds against a threat measured in hours, the residual outcome is
a duplicate row rather than a wrong absorption — visible and reversible, per ruling
048's declared cost — and the after-verification below reports it by name.

AND THAT LOCK IS BOUNDED (#2016)

An advisory lock the rail WAITS on indefinitely re-imports the problem it solves:
measured on the sibling mapping rail in queue 377, a second attended apply sat
2m39s behind the first one's advisory lock while both clients had long since been
handed a 503. The write loop's wall-clock check cannot help — it is not running
while a statement is in flight. So the budget starts at :func:`repair` entry, and
every row issues a transaction-scoped ``lock_timeout`` before its advisory lock. A
contended row is a NAMED per-row finding (:data:`REASON_CREATE_ROW_LOCK_TIMEOUT`)
that retires alone; the gate makes it actionable again on the next invocation of
the same ``plan_hash``.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# The plan primitives are the ones certified on the calibration rail (CAL-P058 /
# C-CERT-1852) and reused by #1798. Imported, never re-implemented.
from app.utils.repair_apply_plan import (  # noqa: E402
    CREATE_PLAN_SCHEMA,
    REASON_CREATE_ROW_LOCK_TIMEOUT,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_UNREADABLE,
    REASON_TRUTH_ID_PRESENT,
    REASON_TRUTH_SET_DRIFT,
    bind_apply,
    build_create_plan,
    create_gate,
    decode_create_plan,
    plan_reason_for_read,
)
from app.utils.repair_lock_budget import (  # noqa: E402
    SET_LOCK_TIMEOUT_SQL,
    ApplyBudget,
    is_lock_timeout,
    lock_timeout_value,
)

# The row derivation is shared with `scripts/derive_event_create_plan.py` so the
# local dry run and this rail cannot mint different addresses from one approval.
from app.utils.event_create_derivation import (  # noqa: E402
    MLB_SPORT_ID,
    TRUTH_SET_REGISTRY,
    DerivationRefused,
    anchors_from_rows,
    build_rows,
    load_games,
    required_club_names,
    select_population,
    truth_set_path_for,
)

#: Durable identity of the reviewed plan artifact. ONE slot per population: an
#: operator applies the plan they just read, and an apply against an older hash must
#: fail loudly rather than find a convenient older artifact still lying around.
PLAN_IDENTITY_TEMPLATE = "repair:event_create_from_truth:apply_plan:pop{population}"

#: Rows written per call. A module constant, not a query param, so the cap cannot be
#: dialled off mid-run. The apply is naturally RESUMABLE without any cursor: the gate
#: drops ids that now exist, so re-invoking with the SAME plan_hash continues where
#: the last call stopped. That property is why a small cap costs nothing here.
APPLY_CREATE_CAP = 50

#: Wall-clock budget for the WHOLE REQUEST, against the web dyno's 30s HTTP wall,
#: started at :func:`repair` entry rather than at loop entry (#2016 — the plan load
#: and the gate query can both block, and both used to sit outside the budget they
#: were spending). A partial page is a NORMAL outcome and says
#: ``stopped_on_time_budget`` rather than pretending to be exhausted (gotcha #53 —
#: a run that did less than it could must not be indistinguishable from a run with
#: nothing left to do).
APPLY_REQUEST_BUDGET_S = 20.0

#: Namespace half of the advisory lock key, so this rail's locks cannot collide with
#: another rail's.
_ADVISORY_LOCK_NS = 1796

REASON_TRUTH_SET_MISSING = "TRUTH_SET_MISSING"
REASON_TRUTH_SET_UNREADABLE = "TRUTH_SET_UNREADABLE"
REASON_TRUTH_SET_CORRUPT = "TRUTH_SET_CORRUPT"

_RESOLVE_CLUBS_SQL = text(
    """
    SELECT name, id FROM teams
     WHERE sport_id = :sport_id
       AND name = ANY(:names)
     ORDER BY name, id
    """
)

# The gate's live half. Asked as a SET, never as a count.
_PRESENT_IDS_SQL = text(
    "SELECT DISTINCT espn_id FROM events WHERE espn_id = ANY(:ids)"
)

# COMPARE-AND-SET, create-shaped. The `WHERE NOT EXISTS` is the compare half and it
# is INSIDE the writing statement — see the module docstring. `CAST(:p AS …)` rather
# than `:p::…` because asyncpg's text() parser drops a bind param followed by a `::`
# cast (memory: asyncpg :param::jsonb bind gotcha).
#
# EVERY occurrence of `:truth_id` is cast, and that is the whole point rather than
# tidiness. It appears TWICE, in two positions that infer different types: bare in
# the SELECT list asyncpg deduces `text`, and compared against `events.espn_id` it
# deduces `character varying`. asyncpg then refuses the whole statement with
# `AmbiguousParameterError: inconsistent types deduced for parameter $2`. Measured
# in production, queue 376: the dry-run was GREEN on every gate — plan_hash
# re-derived identical, `still_missing 328`, `already_present 0` — and `apply=true`
# died before writing a single row. A bind param used ONCE is inferred from its one
# context and needs no help; a param used in TWO contexts must be pinned in BOTH, or
# the cast on one side simply relocates the disagreement.
_INSERT_SQL = text(
    """
    INSERT INTO events (sport_id, espn_id, home_team_id, away_team_id,
                        home_team_name, away_team_name, commence_time, status)
    SELECT CAST(:sport_id AS integer),
           CAST(:truth_id AS varchar),
           CAST(:home_team_id AS integer),
           CAST(:away_team_id AS integer),
           CAST(:home_name AS varchar),
           CAST(:away_name AS varchar),
           CAST(:commence_time AS timestamptz),
           'scheduled'
     WHERE NOT EXISTS (
         SELECT 1 FROM events WHERE espn_id = CAST(:truth_id AS varchar)
     )
    """
)

def _as_datetime(value):
    """Bind ``commence_time`` as a real ``datetime``, never as its ISO string.

    Queue 379: the wave fired with every gate green and died inside the write, nine
    calls in a row, writing nothing::

        asyncpg.exceptions.DataError: invalid input for query argument $7:
        '2026-06-21T02:10:00+00:00' (expected a datetime.date or datetime.datetime
        instance, got 'str')

    ``CAST(:commence_time AS timestamptz)`` does not save it. asyncpg type-checks the
    PYTHON argument before the statement ever reaches the server, so a server-side cast
    is applied to a value that was already rejected client-side. This is the same class
    as #2013's ``AmbiguousParameterError`` one parameter over, and it has the same
    tell: the dry-run is green because the dry-run never executes the INSERT.

    The coercion lives HERE, at the bind, and deliberately not on ``PlannedCreate``.
    ``commence_time`` is a string on the plan row because it is inside the plan's
    CONTENT ADDRESS — it is how a reviewer knows which game a row is. Retyping the
    field would change ``plan_hash`` and so invalidate the artifact Alex approved,
    turning a one-line bind fix into a re-review. The string is the reviewed object;
    the datetime is an implementation detail of talking to the driver.
    """
    if value is None or isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    # ``fromisoformat`` accepts "+00:00" but not the "Z" that JSON artifacts carry.
    if text_value.endswith(("Z", "z")):
        text_value = text_value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text_value)
    # A naive stamp would be read as the server's local zone; the truth set is UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_LOCK_SQL = text("SELECT pg_advisory_xact_lock(CAST(:ns AS integer), CAST(:key AS integer))")

# The after-verification reads the PLAN's own truth ids. A fresh population scan here
# is what produced the false comfort of `miswired_after=0` on the binding rail.
_VERIFY_SQL = text(
    """
    SELECT espn_id, id, sport_id, home_team_id, away_team_id,
           home_team_name, away_team_name, commence_time, status
      FROM events
     WHERE espn_id = ANY(:ids)
     ORDER BY espn_id, id
    """
)


def _lock_key(truth_id: str) -> int:
    """A stable 31-bit advisory-lock key for one provider id.

    Computed in Python rather than with ``hashtext`` so the key is identical in a
    test double and in production, and so the rail does not depend on a Postgres
    internal function whose hash is not contractual across versions.
    """
    return int(zlib.crc32(str(truth_id).encode("utf-8")) & 0x7FFFFFFF)


def _monotonic() -> float:
    """The rail's clock, as a module-level name so a test can replace it.

    Same seam and same reason as the mapping rail's: a budget test that cannot
    control the clock must sleep or patch the stdlib, and neither is a proof
    (gotcha #44).
    """
    return time.monotonic()


def _truth_set_path(population: str = "2") -> pathlib.Path:
    """The committed reviewed file this population is bound to, resolved absolutely."""
    return pathlib.Path(__file__).resolve().parents[2] / truth_set_path_for(population)


def _load_truth_set(population: str = "2") -> tuple[Optional[dict], str]:
    """``(truth, reason)`` — three named readings, never one flattened one.

    The same distinction the plan loader draws, for the same reason: an operator
    told the reviewed set is MISSING will go and make one, and that is exactly the
    wrong move when the file is present and torn, or present and unreadable.
    """
    path = _truth_set_path(population)
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None, REASON_TRUTH_SET_MISSING
    except OSError as exc:  # permissions, I/O — "I could not read it right now"
        logger.warning("#1796 truth set unreadable: %s", type(exc).__name__)
        return None, REASON_TRUTH_SET_UNREADABLE
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None, REASON_TRUTH_SET_CORRUPT
    if not isinstance(parsed, dict):
        return None, REASON_TRUTH_SET_CORRUPT
    return parsed, "ok"


async def _save_plan(plan, population: str) -> tuple[bool, str]:
    """Persist the reviewed plan. ``(ok, note)`` — a failure is REPORTED, never eaten.

    On the durable snapshot rail rather than Redis, for CAL-P058's reason: a SETEX on
    an allkeys-lru instance can be evicted, and an operator who cannot be handed a
    hash must be TOLD so, because the next thing they will do is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY_TEMPLATE.format(population=population),
                schema_version=CREATE_PLAN_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source="repair:event-create-from-truth",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"plan persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"plan persist rejected: {result.get('status')}"


async def _load_plan(population: str):
    """``(plan, reason)`` — the artifact, re-digested from its own content."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            PLAN_IDENTITY_TEMPLATE.format(population=population),
            expected_version=CREATE_PLAN_SCHEMA,
            max_age_s=14 * 86400,
        )
    except Exception as exc:  # noqa: BLE001
        # A raise is "I could not read", never "it is not there" (gotcha #53).
        logger.warning("#1796 plan read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not read.ok or read.envelope is None:
        logger.warning(
            "#1796 plan artifact not readable: status=%s error_class=%s",
            read.status, read.error_class,
        )
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_create_plan(read.envelope.payload)


async def _present_truth_ids(session, truth_ids) -> set[str]:
    """Which reviewed ids ALREADY exist. The live half of the gate, as a set."""
    ids = [str(i) for i in truth_ids]
    if not ids:
        return set()
    rows = (await session.execute(_PRESENT_IDS_SQL, {"ids": ids})).all()
    return {str(r[0]) for r in rows if r[0] is not None}


async def _apply_reviewed_plan(
    session,
    plan_hash: Optional[str],
    population: str,
    budget: Optional[ApplyBudget] = None,
) -> dict[str, Any]:
    """Create EXACTLY the reviewed rows, or refuse by name. Never re-derives.

    The derivation below the dry-run is not called from this path. That is the
    substance of the pattern: a work list that can be recomputed at apply time is a
    work list that can differ from the reviewed one, and no amount of
    after-measurement can tell you afterwards which of the two you wrote.

    ``budget`` is the REQUEST's, handed down from :func:`repair` so the plan load
    and the gate query below are already charged against it (#2016). It is
    optional only so this function stays directly callable.
    """
    budget = budget or ApplyBudget(APPLY_REQUEST_BUDGET_S, clock=_monotonic)
    plan, reason = await _load_plan(population)
    ok, refusals = bind_apply(plan, decode_reason=reason, presented_hash=plan_hash)
    if not ok:
        return {
            "issue": "#1796",
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": refusals,
            "presented_plan_hash": plan_hash,
            "artifact_plan_hash": plan.plan_hash if plan is not None else None,
            "artifact_note": reason,
            "note": (
                "Nothing was created. Re-run with apply=false to produce a plan, read it, "
                "then pass its plan_hash back."
            ),
        }

    # The gate's live half, asked BEFORE any write: every reviewed id must still be
    # missing. An id that now exists is not an error in the world — it is the
    # ordinary pipeline doing its job — but it IS an id this plan may no longer act
    # on, and it is NAMED rather than skipped. Its siblings survive.
    present = await _present_truth_ids(session, plan.truth_ids)
    gate_ok, no_longer_missing = create_gate(plan, set(plan.truth_ids) - present)
    actionable = [r for r in plan.rows if r.truth_id not in present]

    # Structural assertion BEFORE the loop, not after it: prove the write set is a
    # SUBSET of the approved set while nothing has been written. The binding rail
    # can check this afterwards because it commits once; this rail commits per row
    # (``events`` is hot — a single long transaction over 50 inserts contends with
    # live ingest), so a post-hoc discovery would have nothing left to roll back.
    approved_keys = set(plan.row_keys)
    outside = sorted({r.row_key for r in actionable} - approved_keys)
    if outside:
        return {
            "issue": "#1796",
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": [REASON_OUTSIDE_APPROVED],
            "outside_approved_set": outside,
            "note": "Nothing was created. The apply assembled rows the reviewed plan never named.",
        }

    created: list[dict[str, Any]] = []
    already_present: list[dict[str, Any]] = []
    lock_timeouts: list[dict[str, Any]] = []
    stopped_on_time_budget = False
    stopped_on_cap = False

    for row in actionable:
        if len(created) >= APPLY_CREATE_CAP:
            stopped_on_cap = True
            break
        # "Is there room to START another row", against the REQUEST's clock. A
        # boundary check cannot bound the statement it is about to issue (#2016).
        if not budget.has_room_for_a_row():
            stopped_on_time_budget = True
            break

        # Tripwire for anyone who later re-introduces a scan on this path. It cannot
        # fire while the loop iterates the plan, which is exactly the point.
        if row.row_key not in approved_keys:  # pragma: no cover — structural
            await session.rollback()
            return {
                "issue": "#1796",
                "apply": True,
                "applied": False,
                "refused": True,
                "reason_codes": [REASON_OUTSIDE_APPROVED],
                "outside_approved_set": [row.row_key],
                "note": "Rolled back mid-loop: a row outside the reviewed plan reached the writer.",
            }

        entry = {
            "truth_id": row.truth_id,
            "provider": row.provider,
            "label": row.label,
            "sport_id": row.sport_id,
            "home": {"id": row.home_team_id, "name": row.home_name},
            "away": {"id": row.away_team_id, "name": row.away_name},
            "commence_time": row.commence_time,
        }

        # Bound the STATEMENT (#2016). ``events`` is the hottest table in the
        # system; the advisory lock and the INSERT can both queue behind live
        # ingest, and neither is interruptible from here once issued.
        # ``set_config(..., true)`` is TRANSACTION-scoped and this loop commits
        # per row, so it is re-issued inside every row's transaction — hoisting
        # it above the loop would protect row 1 and nothing after the first commit.
        lock_ms = budget.lock_timeout_ms()
        try:
            await session.execute(
                SET_LOCK_TIMEOUT_SQL, {"ms": lock_timeout_value(lock_ms)}
            )
            await session.execute(
                _LOCK_SQL, {"ns": _ADVISORY_LOCK_NS, "key": _lock_key(row.truth_id)}
            )
            result = await session.execute(
                _INSERT_SQL,
                {
                    "sport_id": row.sport_id,
                    "truth_id": row.truth_id,
                    "home_team_id": row.home_team_id,
                    "away_team_id": row.away_team_id,
                    "home_name": row.home_name,
                    "away_name": row.away_name,
                    # asyncpg type-checks the Python argument before the server sees
                    # `CAST(... AS timestamptz)`, so the ISO string on the plan row must
                    # become a datetime HERE. See `_as_datetime`.
                    "commence_time": _as_datetime(row.commence_time),
                },
            )
        except Exception as exc:  # noqa: BLE001 — re-raised unless it is 55P03
            if not is_lock_timeout(exc):
                # A real write failure must never be dressed up as contention.
                raise
            await session.rollback()
            entry["reason_code"] = REASON_CREATE_ROW_LOCK_TIMEOUT
            entry["reason"] = (
                "another transaction holds a conflicting lock and the rail declined to "
                "keep waiting — nothing was created, and the SAME plan_hash will find "
                "this id still missing and still actionable on the next invocation"
            )
            entry["lock_timeout_ms"] = lock_ms
            lock_timeouts.append(entry)
            logger.warning(
                "#1796 truth id %s contended: lock_timeout %sms fired, row retires "
                "individually [plan %s]",
                row.truth_id, lock_ms, plan.plan_hash[:12],
            )
            continue

        if (result.rowcount or 0) == 1:
            # Per-row commit: `events` is a hot table and a long transaction over a
            # page of inserts contends with live ingest (measured — the one-off
            # lock-contention class). It also makes a deadline stop durable.
            await session.commit()
            created.append(entry)
            logger.info(
                "#1796 created event from venue truth espn:%s (%s) [plan %s]",
                row.truth_id, row.label, plan.plan_hash[:12],
            )
        else:
            await session.rollback()
            entry["reason_code"] = REASON_TRUTH_ID_PRESENT
            entry["reason"] = (
                "a row for this provider id appeared between the gate and the insert — "
                "the ordinary pipeline created it, so this row retires and its siblings continue"
            )
            already_present.append(entry)

    # Verify over the PLAN's own truth ids, not a population re-scan.
    verified = {"present": 0, "absent": [], "duplicated": [], "rows": []}
    after = (
        await session.execute(_VERIFY_SQL, {"ids": [r.truth_id for r in plan.rows]})
    ).mappings().all()
    by_truth: dict[str, list[Any]] = {}
    for r in after:
        by_truth.setdefault(str(r["espn_id"]), []).append(r)
    for row in plan.rows:
        hits = by_truth.get(row.truth_id, [])
        if not hits:
            verified["absent"].append(row.truth_id)
            continue
        verified["present"] += 1
        if len(hits) > 1:
            # The residual the non-unique index leaves. Named, never inferred away.
            verified["duplicated"].append(
                {"truth_id": row.truth_id, "event_ids": [int(h["id"]) for h in hits]}
            )
        hit = hits[0]
        verified["rows"].append(
            {
                "truth_id": row.truth_id,
                "event_id": int(hit["id"]),
                "sport_id": int(hit["sport_id"]) if hit["sport_id"] is not None else None,
                "home_team_id": hit["home_team_id"],
                "away_team_id": hit["away_team_id"],
                "matchup": f"{hit['away_team_name']} @ {hit['home_team_name']}",
                "commence_time": str(hit["commence_time"]),
                "status": hit["status"],
            }
        )

    # Invalidation obligation. New events are feed candidates and team-page rows, and
    # the Discover response cache would otherwise keep serving a world without them.
    # Reported rather than PERSISTED as a debt (the CAL-P062 shape) for a stated
    # reason: this cache carries a TTL and self-heals within it, whereas a
    # calibration generation does not and stays wrong until someone bumps it. A
    # failure here is therefore surfaced and bounded, not silent — but do NOT copy
    # this judgement to a rail whose invalidation target has no TTL.
    invalidation: dict[str, Any] = {"status": "skipped", "reason": "nothing created"}
    if created:
        from app.utils.feed_cache import invalidate_feed_response_cache

        invalidation = await invalidate_feed_response_cache("event-create-from-truth")
    invalidation_discharged = (not created) or invalidation.get("status") == "ok"

    remaining = len(plan.rows) - verified["present"]
    return {
        "issue": "#1796",
        "apply": True,
        "applied": True,
        "success": invalidation_discharged and not verified["duplicated"],
        "population": population,
        "plan_hash": plan.plan_hash,
        "plan_rows": len(plan.rows),
        "gate": {
            "rule": (
                "apply may proceed only for reviewed ids that are STILL missing; an id "
                "that now exists retires that row alone"
            ),
            "passes": gate_ok,
            "no_longer_missing": no_longer_missing,
            "retired_by_gate": len(no_longer_missing),
        },
        "census": {
            "planned": len(plan.rows),
            "actionable_this_call": len(actionable),
            "created": len(created),
            "already_present": len(already_present),
            "contended": len(lock_timeouts),
            "remaining": remaining,
        },
        "exhausted": remaining == 0 and not lock_timeouts,
        "stopped_on_cap": stopped_on_cap,
        "stopped_on_time_budget": stopped_on_time_budget,
        # #2016: contended rows are NAMED, one entry each, rather than folded into
        # a 503 that could equally mean nothing was written or everything was.
        "lock_timeouts": lock_timeouts,
        "stopped_on_lock": [e["truth_id"] for e in lock_timeouts],
        "request_budget_s": budget.total_s,
        "elapsed_s": round(budget.elapsed_s(), 2),
        "verified_plan_truth_ids": verified,
        "ledger": created,
        "skipped": already_present,
        "invalidation": invalidation,
        "invalidation_discharged": invalidation_discharged,
        "note": (
            "Bound to the reviewed plan: no derivation ran on this path, the existence "
            "check is inside the INSERT rather than in front of it, every row is keyed "
            "on the provider id so a doubleheader is two rows, and verification re-read "
            "the plan's own truth ids rather than the population. Re-invoke with the "
            "SAME plan_hash to continue — the gate makes the apply resumable."
        ),
    }


async def repair(
    session,
    apply: bool = False,
    plan_hash: Optional[str] = None,
    population: str = "2",
) -> dict[str, Any]:
    """Create the reviewed missing games from venue truth (#1796/#1902).

    Args:
        apply: False (default) derives and persists a plan. True consumes one.
        plan_hash: content address of the reviewed dry run. REQUIRED when ``apply``.
        population: which REVIEWED SET this call is bound to — ``"1"`` the single
            Aug 5 MIN@KC game (#1902), ``"2"`` the 328-game season backfill of
            which population 1 is a member, ``"3"`` the four Aug-19 games that
            have no row at all (#1947). Three is its OWN committed file and not an
            extension of two: two's declared scope ends 2026-08-17, so folding
            them in would silently change a set Alex already reviewed.

    A dry run returns the census, the per-row ledger with both club anchors named,
    and the ``plan_hash`` of the persisted artifact. An apply writes only that
    artifact's rows and re-derives nothing.
    """
    population = str(population)
    if population not in TRUTH_SET_REGISTRY:
        return {
            "issue": "#1796",
            "refused": True,
            "reason_codes": ["UNKNOWN_POPULATION"],
            "note": (
                f"population must be one of {sorted(TRUTH_SET_REGISTRY)}, got {population!r}"
            ),
        }

    if apply:
        # The derivation below does not run. See ``_apply_reviewed_plan``. The
        # request's wall clock starts HERE so the plan read and the gate query are
        # charged against the same budget the write loop spends (#2016).
        return await _apply_reviewed_plan(
            session,
            plan_hash,
            population,
            budget=ApplyBudget(APPLY_REQUEST_BUDGET_S, clock=_monotonic),
        )

    truth, truth_reason = _load_truth_set(population)
    if truth is None:
        return {
            "issue": "#1796",
            "apply": False,
            "refused": True,
            "reason_codes": [truth_reason],
            "truth_set_path": str(_truth_set_path(population)),
            "note": (
                "No plan was derived. MISSING means the reviewed set is not deployed; "
                "CORRUPT means it is there and cannot be trusted — do not regenerate it, "
                "investigate; UNREADABLE means the read failed right now."
            ),
        }

    try:
        wanted = select_population(truth, population)
        games = load_games(truth)
        names = required_club_names(wanted, games)
        club_rows = (
            await session.execute(
                _RESOLVE_CLUBS_SQL, {"sport_id": MLB_SPORT_ID, "names": names}
            )
        ).all()
        unresolved = sorted(set(names) - {str(r[0]) for r in club_rows})
        if unresolved:
            raise DerivationRefused(
                "CLUB_ANCHOR_NOT_UNIQUE",
                f"{len(unresolved)} club(s) have no row in sport_id={MLB_SPORT_ID}",
                unanchored=unresolved,
            )
        anchors = anchors_from_rows(club_rows)
        rows = build_rows(wanted, games, anchors, sport_id=MLB_SPORT_ID)
    except DerivationRefused as refusal:
        return {"issue": "#1796", "apply": False, **refusal.as_payload()}

    present = await _present_truth_ids(session, [r.truth_id for r in rows])
    live_missing = {r.truth_id for r in rows} - present

    plan = build_create_plan(
        rows,
        context={
            "issue": "#1796",
            "population": population,
            # NO `ruling` KEY, DELIBERATELY (queue 371 ruling (b)(3)).
            #
            # This deriver used to stamp every plan it built with
            # `"ruling": "Alex 2026-08-17 — attended CREATE from venue truth,
            # approved"`. That string is a claim about a HUMAN APPROVAL OF A
            # POPULATION, and the deriver cannot know it: population 3 was minted
            # fresh in window 369 with four Aug-19 games Alex had never seen, and
            # it inherited the sentence anyway. An auditor reading that artifact
            # would have found an approval that did not exist.
            #
            # A deriver must not emit a ruling it cannot cite — omit the field. An
            # inherited template ruling is a FORGED CREDENTIAL, and it is worse
            # than no credential, because a missing one prompts the question and a
            # forged one answers it. Approval provenance is recorded ON THE
            # ARTIFACT by whoever takes the MC, naming the date and the rows.
            #
            # (`context` is outside `plan_hash` — the address is the sorted row
            # digests — so recording provenance later never re-addresses a
            # reviewed plan, and dropping this key never re-addressed one either.)
            "truth_set_hash": truth.get("truth_id_hash"),
            "sport_id": MLB_SPORT_ID,
            "sport_key": "baseball_mlb",
        },
    )
    gate_ok, no_longer_missing = create_gate(plan, live_missing)
    plan_saved, plan_note = await _save_plan(plan, population)

    return {
        "issue": "#1796",
        "apply": False,
        "population": population,
        "plan_hash": plan.plan_hash if plan_saved else None,
        "plan_persisted": plan_saved,
        "plan_note": plan_note,
        "plan_rows": len(plan.rows),
        "schema": CREATE_PLAN_SCHEMA,
        "truth_set_hash": truth.get("truth_id_hash"),
        "census": {
            "reviewed": len(wanted),
            "still_missing": len(live_missing),
            "already_present": len(present),
            "clubs_anchored": len(anchors),
        },
        "gate": {
            "rule": truth.get("gate"),
            "passes": gate_ok,
            "no_longer_missing": no_longer_missing,
            # A count-shaped restatement is deliberately NOT the gate. See the
            # module docstring: a count expires while nothing is wrong.
            "reason_code": None if gate_ok else REASON_TRUTH_SET_DRIFT,
        },
        "duplicate_truth_ids": plan.duplicate_truth_ids(),
        "doubleheader_truth_ids": plan.doubleheaders(),
        "apply_command": (
            f"POST …/repairs/event-create-from-truth?apply=true&population={population}"
            f"&plan_hash={plan.plan_hash}"
            if plan_saved
            else "NO PLAN HASH — the artifact did not persist; an apply would be refused"
        ),
        "ledger": [r.as_payload() for r in rows],
        "note": (
            "Dry run only — this path cannot create a row. Club anchors are resolved "
            "against `teams` inside the regular-season sport and must be 1:1; the "
            "name->id index is NOT consulted, because that index is the poisoned path "
            "(#1918). Read the ledger, then apply by hash."
        ),
    }
