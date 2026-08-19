"""#1798 — events bound to the wrong club's ``team_id``. Detect by DEREFERENCE, never by name.

THE DEFECT

``events`` carries both the team NAMES (``home_team_name``/``away_team_name``) and
FK ids (``home_team_id``/``away_team_id``). Measured in production 2026-08-12 over
the 2026 MLB season: **1,758 events, 153 sides whose id dereferences to a club
whose name disagrees with the row's own name field.** The names are right and the
ids point at other clubs, so *every name-based check in the codebase passes*:

    event 15194469  "Arizona Diamondbacks @ Boston Red Sox"
        away_team_id = 10707 -> Los Angeles Dodgers
        home_team_id =   855 -> Minnesota Twins (baseball_mlb_preseason)

Any surface keyed on ``team_id`` inherits this directly — team pages, My Stuff,
favourites, notifications, and the roster join in ``team_linking``. It is why
``GET /api/teams/10709`` served "Miami Marlins @ Cincinnati Reds" among the Red
Sox's upcoming games.

WHY THE DETECTOR MUST DEREFERENCE

Alex's ruling 2026-08-12: *names are never sufficient*. Nothing in the codebase
asserts, after binding, that ``teams[event.home_team_id].name`` agrees with
``event.home_team_name``; the only comparisons anywhere near this compare a name
to a name, which is exactly the comparison this defect survives. So the predicate
here joins through the FK and reads the club it actually lands on.

TWO CLASSES, DELIBERATELY SEPARATED

  CROSS_CLUB   the id resolves to a genuinely different club. Reciprocal pairs
               dominate the measured population (Diamondbacks<->Dodgers,
               White Sox<->Brewers, Mariners<->Athletics), which is the
               fingerprint of a swapped-orientation merge copying home/away ids
               without swapping them -- see ``_merge_duplicate_events_impl``.
  WRONG_SPORT  the id resolves to the RIGHT club's duplicate row on
               ``baseball_mlb_preseason`` (33178) instead of ``baseball_mlb``
               (53232). The name agrees; only the identity is the wrong half of
               the pair. A different defect with a different cause, so it is
               counted and repaired separately rather than folded in.

REPAIR DIRECTION, AND WHY IT FAILS CLOSED

Re-derive the id from the row's own ``*_team_name`` **within the event's own
``sport_id``**, requiring exactly one match. It deliberately does NOT fuzzy-match:
fuzzy resolution is the most likely producer of this bug in the first place
(``TeamIdentityService.resolve_team`` scopes by a ``sport_key`` PREFIX -- for
``baseball_mlb`` that prefix is ``baseball``, spanning preseason, NCAA and NPB --
accepts a mascot-only match at score >= 40, and then AUTO-REGISTERS the result,
so one bad fuzzy hit becomes a permanent exact hit for every later lookup).
Repairing with the same tool that broke it would launder the error.

Zero candidates or more than one -> ``review``, never a guess.

Dry-run is the default. Every planned change is returned in the ledger with the
before and after id AND the dereferenced club name for both, so the plan is
checkable without a second query.

PLAN-BOUND APPLY (queue 362, answering Codex's C-APPLY-PRE BLOCK)
-----------------------------------------------------------------

    POST /api/admin/repairs/event-team-binding?apply=false
        ...returns ``plan_hash`` and persists the plan artifact
    POST /api/admin/repairs/event-team-binding?apply=true&plan_hash=<hash>

Until queue 362 this rail's ``apply=true`` **re-derived its own work list**: it ran
the same scan again and wrote whatever that scan found. Alex had approved a specific
180-side population, and the rail could not tell that population from any other. The
certification's executable specimen: reviewed set ``[(1001, away)]``, a candidate
``2002:away`` that appeared after review, and the deployed function wrote **both**,
committed, and reported ``miswired_after=0`` — a true statement about the population,
and no statement whatsoever about whether the writes were the approved ones.

An after-census proves the writes LANDED. Only a plan proves they were the writes
APPROVED. So:

* the dry-run emits a content-addressed :class:`BindingApplyPlan` and persists it;
* ``apply=true`` without ``plan_hash`` is REFUSED (``PLAN_HASH_MISMATCH``), and so is
  a hash that does not match the artifact's own re-derived address;
* the apply **iterates the plan and nothing else** — the candidate scan does not run
  on the apply path at all, so a row that appeared after review is not merely
  rejected, it is never looked at;
* every write is a **compare-and-set** on the exact ``before`` id the plan recorded.
  A side whose binding moved since review is a side the reviewer did not see: it is
  skipped, counted as ``CONCURRENT_ROW_DRIFT``, and named in the response;
* the after-verification re-reads **the plan's own event ids** and reports each side's
  landed state, rather than re-measuring the whole population.

The primitives are the ones certified on the calibration rail
(``app/utils/repair_apply_plan``) — reused, not re-implemented. Two copies of a gate
is two gates to keep honest, and the second is always the one nobody re-reads.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional, Union

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _as_date(value: Union[str, date, datetime]) -> date:
    """Coerce ``since`` to a real ``date`` before it is bound as a query param.

    asyncpg binds parameters by TYPE, not by rendering them into SQL text: it
    rejects ``'2026-03-01'`` for a timestamp column with ``invalid input for
    query argument $2 ... (expected a datetime.date or datetime.datetime
    instance, got 'str')``. psycopg2 would have adapted the string silently, so
    this is asyncpg-specific and invisible to any test that does not bind
    against the real driver -- which is every test in this module's suite, all
    of which drive a ``_FakeSession`` double. The rail therefore shipped green
    (19/19) and 500-ed on its first production call.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()

# MLB regular season and the duplicate preseason sport that #1798 owns. Kept as
# the default scope because that is the population measured; ``sport`` widens it.
_DEFAULT_SPORT_IDS = (53232, 33178)

# A bound scan, not the whole table: this runs inside the web dyno on a request.
_DEFAULT_LIMIT = 500

_CANDIDATES_SQL = text(
    """
    SELECT e.id,
           e.sport_id,
           e.commence_time,
           e.status,
           e.home_team_name,
           e.home_team_id,
           ht.name      AS home_bound_name,
           ht.sport_id  AS home_bound_sport,
           e.away_team_name,
           e.away_team_id,
           at.name      AS away_bound_name,
           at.sport_id  AS away_bound_sport
      FROM events e
      LEFT JOIN teams ht ON ht.id = e.home_team_id
      LEFT JOIN teams at ON at.id = e.away_team_id
     WHERE e.sport_id = ANY(:sport_ids)
       AND e.commence_time >= :since
       AND e.commence_time < :until
       AND (
             (e.home_team_id IS NOT NULL AND ht.id IS NOT NULL)
          OR (e.away_team_id IS NOT NULL AND at.id IS NOT NULL)
           )
     ORDER BY e.commence_time DESC
     LIMIT :lim
    """
)

# Exact-name resolution inside the event's own sport. No ILIKE, no fuzzy.
_RESOLVE_SQL = text(
    """
    SELECT id, name FROM teams
     WHERE sport_id = :sport_id
       AND lower(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g'))
         = lower(regexp_replace(:target, '[^a-zA-Z0-9]', '', 'g'))
    """
)

# COMPARE-AND-SET. The ``AND <side>_team_id = :expected`` half is the whole point:
# it is the plan's before-image asserted at write time, so a side that moved between
# review and apply updates ZERO rows instead of being clobbered with a decision made
# about a state that no longer exists. ``rowcount == 0`` is therefore a finding
# (CONCURRENT_ROW_DRIFT), never a silent success.
_UPDATE_SQL = {
    "home": text(
        "UPDATE events SET home_team_id = :tid WHERE id = :eid AND home_team_id = :expected"
    ),
    "away": text(
        "UPDATE events SET away_team_id = :tid WHERE id = :eid AND away_team_id = :expected"
    ),
}

# The after-verification reads ONLY the plan's own events. A fresh population scan
# here is what produced the false comfort of `miswired_after=0`.
_VERIFY_SQL = text(
    """
    SELECT e.id,
           e.sport_id,
           e.home_team_name,
           e.home_team_id,
           ht.name      AS home_bound_name,
           ht.sport_id  AS home_bound_sport,
           e.away_team_name,
           e.away_team_id,
           at.name      AS away_bound_name,
           at.sport_id  AS away_bound_sport
      FROM events e
      LEFT JOIN teams ht ON ht.id = e.home_team_id
      LEFT JOIN teams at ON at.id = e.away_team_id
     WHERE e.id = ANY(:ids)
    """
)

#: Durable identity of the reviewed plan artifact. ONE slot: a dry-run supersedes
#: the previous plan, which is correct — the operator applies the plan they just
#: read, and an apply against an older hash must fail loudly rather than find a
#: convenient older artifact still lying around.
PLAN_IDENTITY = "repair:event_team_binding:apply_plan"


# The detector's predicate and the WRITE-TIME guard (#1918) are the same predicate,
# defined once in `app/utils/team_binding_invariant` and imported by both. Keeping two
# copies is how a repair rail ends up certifying rows its own writer would refuse — or
# worse, repairing toward a shape the guard then rejects on the next ingest.
from app.utils.team_binding_invariant import (  # noqa: E402
    binding_defect as _classify,
    normalize_club_name as _norm,
)

# The plan primitives are the ones certified on the calibration rail (CAL-P058 /
# C-CERT-1852). Imported, never re-implemented.
from app.utils.repair_apply_plan import (  # noqa: E402
    BINDING_APPLY_PLAN_SCHEMA,
    REASON_CONCURRENT_DRIFT,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_UNREADABLE,
    PlannedBinding,
    bind_apply,
    build_binding_plan,
    decode_binding_plan,
    mutations_outside_approved_keys,
    plan_reason_for_read,
)


async def _save_plan(plan) -> tuple[bool, str]:
    """Persist the reviewed plan. ``(ok, note)`` — a failure is REPORTED.

    On the durable snapshot rail rather than Redis, for the reason CAL-P058 gives:
    a SETEX on an allkeys-lru instance can be evicted, and an operator who cannot be
    handed a hash must be TOLD so, because the next thing they will do is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY,
                schema_version=BINDING_APPLY_PLAN_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source="repair:event-team-binding",
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
            expected_version=BINDING_APPLY_PLAN_SCHEMA,
            max_age_s=14 * 86400,
        )
    except Exception as exc:  # noqa: BLE001
        # A raise is "I could not read", never "it is not there" (gotcha #53).
        logger.warning("#1798 plan read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not read.ok or read.envelope is None:
        # Carry the durable layer's classification instead of flattening it into
        # prose that the binder cannot match — C-APPLY-PRE-R2 finding 1.
        logger.warning(
            "#1798 plan artifact not readable: status=%s error_class=%s",
            read.status, read.error_class,
        )
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_binding_plan(read.envelope.payload)


async def _apply_reviewed_plan(session, plan_hash: Optional[str]) -> dict[str, Any]:
    """Write EXACTLY the reviewed plan, or refuse by name. Never re-derives.

    The candidate scan is not called from this path. That is deliberate and is the
    substance of the fix: a work list that can be recomputed at apply time is a work
    list that can differ from the reviewed one, and no amount of after-measurement
    can tell you afterwards which of the two you wrote.
    """
    plan, reason = await _load_plan()
    ok, refusals = bind_apply(plan, decode_reason=reason, presented_hash=plan_hash)
    if not ok:
        return {
            "issue": "#1798",
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

    applied: list[dict[str, Any]] = []
    drifted: list[dict[str, Any]] = []
    attempted_keys: list[str] = []

    for row in plan.rows:
        attempted_keys.append(row.row_key)
        result = await session.execute(
            _UPDATE_SQL[row.side],
            {"tid": row.after_id, "eid": row.event_id, "expected": row.expected_before_id},
        )
        entry = {
            "event_id": row.event_id,
            "side": row.side,
            "defect": row.defect,
            "before": {"id": row.expected_before_id, "name": row.before_name},
            "after": {"id": row.after_id, "name": row.after_name},
            "matchup": row.matchup,
        }
        if (result.rowcount or 0) == 1:
            applied.append(entry)
            logger.info(
                "#1798 re-bound event %s %s_team_id %s (%s) -> %s (%s) [plan %s]",
                row.event_id, row.side, row.expected_before_id, row.before_name,
                row.after_id, row.after_name, plan.plan_hash[:12],
            )
        else:
            entry["reason_code"] = REASON_CONCURRENT_DRIFT
            entry["reason"] = (
                "the side's bound id is no longer the one the plan recorded — it moved "
                "between review and apply, so this is not the row that was approved"
            )
            drifted.append(entry)

    # Structural assertion, not decoration: prove the write set was a SUBSET of the
    # approved set. It cannot fail while the loop above iterates the plan — which is
    # the point. It is the tripwire for anyone who later re-introduces a scan here.
    outside = mutations_outside_approved_keys(plan, attempted_keys)
    if outside:
        await session.rollback()
        return {
            "issue": "#1798",
            "apply": True,
            "applied": False,
            "refused": True,
            "reason_codes": [REASON_OUTSIDE_APPROVED],
            "outside_approved_set": outside,
            "note": "Rolled back. The apply attempted rows the reviewed plan never named.",
        }

    if applied:
        await session.commit()

    # Verify over the PLAN's own events, side by side. Not a population re-scan.
    verified: dict[str, Any] = {"sound": 0, "still_defective": 0, "sides": []}
    if plan.event_ids:
        after_rows = (
            await session.execute(_VERIFY_SQL, {"ids": list(plan.event_ids)})
        ).mappings().all()
        by_id = {r["id"]: r for r in after_rows}
        for row in plan.rows:
            r = by_id.get(row.event_id)
            if r is None:
                verified["sides"].append(
                    {"event_id": row.event_id, "side": row.side, "state": "event_not_found"}
                )
                continue
            defect = _classify(
                r[f"{row.side}_team_name"],
                r[f"{row.side}_bound_name"],
                r[f"{row.side}_bound_sport"],
                r["sport_id"],
            )
            if defect is None:
                verified["sound"] += 1
            else:
                verified["still_defective"] += 1
                verified["sides"].append({
                    "event_id": row.event_id,
                    "side": row.side,
                    "state": defect,
                    "bound_to": {
                        "id": r[f"{row.side}_team_id"],
                        "name": r[f"{row.side}_bound_name"],
                    },
                })

    return {
        "issue": "#1798",
        "apply": True,
        "applied": True,
        "plan_hash": plan.plan_hash,
        "plan_rows": len(plan.rows),
        "census": {
            "planned": len(plan.rows),
            "applied": len(applied),
            "drifted": len(drifted),
        },
        "verified_plan_sides": verified,
        "ledger": applied,
        "drift": drifted,
        "note": (
            "Bound to the reviewed plan: no candidate scan ran on this path, every write "
            "was a compare-and-set on the plan's recorded before-id, and verification "
            "re-read the plan's own events rather than the whole population."
        ),
    }


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    sport: Optional[str] = None,
    since: str = "2026-03-01",
    until: Optional[str] = None,
    plan_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Re-bind events whose ``team_id`` dereferences to the wrong club (#1798).

    Args:
        apply: False (default) plans only. True consumes a reviewed plan.
        limit: max events scanned this call (dry-run only — an apply scans nothing).
        sport: optional comma-separated ``sport_id`` list overriding the MLB default.
        since: only events at/after this commence_time are considered (dry-run only).
        until: EXCLUSIVE upper bound on commence_time (dry-run only). Omit for no
            upper bound.
        plan_hash: content address of the reviewed dry-run. REQUIRED when ``apply``.

    A dry-run returns a census, a per-side ledger, and the ``plan_hash`` of the
    persisted artifact. Every ledger entry names the club the id resolved to BEFORE
    and AFTER, because an id on its own is not reviewable — and those names are
    inside the content address, so a plan that swapped a club while keeping the ids
    would be a different plan.

    WHY ``until`` EXISTS (queue 374 item 4)
    ---------------------------------------
    The reviewed 180-side population splits cleanly by month: **151 sides in
    2026-04** and 29 in 2026-08. Those halves are not equivalent risk. The April
    games are long completed — static damage, no ingestion touching them. The
    August ones sit in the live band where the absorber (#1989) is still writing,
    so a repair there races a writer, and Fable's queue-374 ruling (c) sequences
    them AFTER the absorber closes.

    Before this parameter there was no way to say that. ``since`` alone cannot
    express an upper bound, and — worse — ``since`` was not even reachable over
    HTTP: the dispatcher in ``admin_repairs`` passes through only the names it
    declares, and ``since`` was not one of them. So the only expressible
    population was "everything from the module default forward", and the only
    way to apply the April half was to apply the August half with it.

    That matters more than convenience, because ``apply`` is bound to a whole
    plan by content address. An operator who wants 151 rows and can only mint an
    address over 172 has exactly two options: write 21 rows nobody sanctioned, or
    do nothing. This parameter is what makes the reviewed half addressable on its
    own.

    Note the ordering interaction (gotcha #41): the scan is
    ``ORDER BY commence_time DESC LIMIT :lim``, i.e. newest-first. Filtering the
    month out in Python AFTER the scan would let the newer half consume the limit
    and starve the older half — the same shape as the combat-wps lesson. The
    bound is therefore in SQL, inside the LIMIT, not applied to its results.
    """
    if apply:
        # The scan below does not run. See ``_apply_reviewed_plan``.
        return await _apply_reviewed_plan(session, plan_hash)

    sport_ids = (
        [int(s) for s in sport.split(",") if s.strip()] if sport else list(_DEFAULT_SPORT_IDS)
    )
    scan_limit = int(limit) if limit else _DEFAULT_LIMIT
    # Coerced ONCE and reused by both scans. Both are bound params; the
    # after-census one is the more dangerous of the two, because it runs after
    # the commit and would 500 a run whose writes had already landed.
    since_date = _as_date(since)
    # No upper bound requested => a sentinel far past any real commence_time, so
    # the predicate is always true and the unbounded population is byte-identical
    # to what it was before this parameter existed. A sentinel rather than a
    # conditional predicate keeps ONE query text, so the bounded and unbounded
    # calls cannot drift into two different scans.
    until_date = _as_date(until) if until else date(9999, 12, 31)
    if until_date <= since_date:
        return {
            "issue": "#1798",
            "apply": False,
            "refused": True,
            "reason_codes": ["EMPTY_WINDOW"],
            "detail": (
                f"until ({until_date.isoformat()}) must be after since "
                f"({since_date.isoformat()}) — an empty window would mint an "
                "empty plan, and an empty plan is indistinguishable from "
                "'nothing to repair' at the moment an operator reads it."
            ),
            "scope": {
                "sport_ids": sport_ids,
                "since": since_date.isoformat(),
                "until": until_date.isoformat(),
                "limit": scan_limit,
            },
        }

    rows = (
        await session.execute(
            _CANDIDATES_SQL,
            {
                "sport_ids": sport_ids,
                "since": since_date,
                "until": until_date,
                "lim": scan_limit,
            },
        )
    ).mappings().all()

    census = {
        "scanned": len(rows),
        "cross_club": 0,
        "wrong_sport": 0,
        "sound": 0,
        "planned": 0,
        "applied": 0,
        "review": 0,
    }
    ledger: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    planned_rows: list[PlannedBinding] = []
    resolve_cache: dict[tuple[int, str], list] = {}

    for row in rows:
        for side in ("home", "away"):
            row_name = row[f"{side}_team_name"]
            bound_id = row[f"{side}_team_id"]
            bound_name = row[f"{side}_bound_name"]
            bound_sport = row[f"{side}_bound_sport"]

            if bound_id is None or bound_name is None:
                continue

            defect = _classify(row_name, bound_name, bound_sport, row["sport_id"])
            if defect is None:
                census["sound"] += 1
                continue
            census[defect] += 1

            key = (row["sport_id"], _norm(row_name))
            if key not in resolve_cache:
                resolve_cache[key] = (
                    await session.execute(
                        _RESOLVE_SQL, {"sport_id": row["sport_id"], "target": row_name}
                    )
                ).all()
            matches = resolve_cache[key]

            # Fail closed. A guess here re-points a foreign key on a live surface.
            if len(matches) != 1:
                census["review"] += 1
                review.append({
                    "event_id": row["id"],
                    "side": side,
                    "defect": defect,
                    "row_name": row_name,
                    "bound_to": {"id": bound_id, "name": bound_name, "sport_id": bound_sport},
                    "reason": (
                        f"{len(matches)} exact name matches in sport_id={row['sport_id']} "
                        "— refusing to guess"
                    ),
                })
                continue

            target_id, target_name = matches[0]
            if target_id == bound_id:
                # Name agrees and the id is already canonical: nothing to do.
                census["sound"] += 1
                continue

            entry = {
                "event_id": row["id"],
                "commence_time": str(row["commence_time"]),
                "status": row["status"],
                "matchup": f"{row['away_team_name']} @ {row['home_team_name']}",
                "side": side,
                "defect": defect,
                "before": {"id": bound_id, "name": bound_name, "sport_id": bound_sport},
                "after": {"id": target_id, "name": target_name, "sport_id": row["sport_id"]},
            }
            census["planned"] += 1
            ledger.append(entry)
            planned_rows.append(
                PlannedBinding(
                    event_id=row["id"],
                    side=side,
                    expected_before_id=bound_id,
                    before_name=bound_name,
                    after_id=target_id,
                    after_name=target_name,
                    defect=defect,
                    sport_id=row["sport_id"],
                    matchup=entry["matchup"],
                    commence_time=entry["commence_time"],
                )
            )

    # The plan IS the deliverable of a dry-run. It is persisted even when empty is
    # impossible to apply (bind_apply refuses PLAN_HAS_NOTHING_TO_APPLY), because an
    # operator handed no hash at all cannot tell "nothing to do" from "the rail did
    # not get that far".
    plan = build_binding_plan(
        planned_rows,
        context={
            "issue": "#1798",
            "sport_ids": sport_ids,
            "since": since_date.isoformat(),
            # Recorded ONLY when a bound was actually asked for. An unbounded run
            # must produce the same context dict it did before this parameter
            # existed — a sentinel written into the artifact would make every
            # historical plan look like it had been window-scoped.
            **({"until": until_date.isoformat()} if until else {}),
            "limit": scan_limit,
            "scanned": len(rows),
            "review_sides": len(review),
        },
    )
    plan_saved, plan_note = await _save_plan(plan)

    return {
        "issue": "#1798",
        "apply": False,
        # Echo the value actually used, not the caller's spelling of it.
        "scope": {
            "sport_ids": sport_ids,
            "since": since_date.isoformat(),
            **({"until": until_date.isoformat()} if until else {}),
            "limit": scan_limit,
        },
        "census": census,
        "plan_hash": plan.plan_hash if plan_saved else None,
        "plan_persisted": plan_saved,
        "plan_note": plan_note,
        "plan_rows": len(plan.rows),
        "defect_counts": plan.defect_counts(),
        "apply_command": (
            f"POST …/repairs/event-team-binding?apply=true&plan_hash={plan.plan_hash}"
            if plan_saved
            else "NO PLAN HASH — the artifact did not persist; an apply would be refused"
        ),
        "ledger": ledger,
        "review": review,
        "note": (
            "Detection dereferences the FK; it never compares a name to a name. "
            "Repair re-derives from the row's own team name within the event's own "
            "sport_id and requires exactly one exact match — 0 or >1 goes to review. "
            "An apply consumes THIS plan by hash and re-derives nothing."
        ),
    }
