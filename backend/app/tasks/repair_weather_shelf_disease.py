"""#4264 — drain the disease markets stranded on the ``weather`` shelf.

WHY A REPAIR EXISTS AT ALL. #4264 widened ``misfiled_subject`` so the epidemiology
arm may correct the ``weather`` shelf, and that fixes the *classifier*. It cannot
fix a *row* the ingest never rewrites. Measured on production 2026-09-09, the 22
affected open markets split by poller reach:

    16   touched within the hour  -> converge on the next Polymarket poll
     6   not re-seen in 1-83 days -> never self-heal

and one of the six is ``16630403`` — "Hantavirus pandemic in 2026?", **page one,
slot 5**, wearing a sun-and-cloud chip. CERT-2358 blocked the code-only ship for
exactly this reason: the named reader still sees the weather chip. This module is
the other half.

THIS REPAIR HAS NO CLASSIFICATION RULES OF ITS OWN, AND THAT IS THE POINT.
It re-runs the SHIPPED cascade — ``_tags_to_category`` then
``resolve_event_category`` — byte-for-byte as ``_process_polymarket_events`` runs
it, and stores that answer. A repair carrying its own copy of the rule is a second
classifier free to drift from the poller, and the drift is invisible until the two
disagree on a row nobody is looking at. Same principle as
``repair_polymarket_sport_category`` (Q495), one shelf over.

WHY IT READS STORED TAGS RATHER THAN RE-ASKING THE VENUE. Q495's rail re-fetches
``gamma/events/{id}``. That is right for its population and wrong for this one:
these six rows are stale *because* nothing has re-read them, so a venue fetch is
the most likely thing to fail, and a 404 would leave the page-one card wrong while
the run reported a clean terminal. We persist the venue's own tags in
``futures_markets.category_tags`` at ingest, so the cascade's input is already in
the database and needs no network. Five of the six carry ``['weather']``; the
sixth is a sub-market and is handled below.

TWO ROW KINDS, BECAUSE THE POLLER HAS TWO WRITE PATHS.

  PARENT   ``category_tags`` non-empty. The cascade runs on the row's own tags.
  CHILD    ``category_tags`` empty — a nested sub-market keyed by ``condition_id``,
           sharing its parent's ``group_id``. The poller writes these from the
           PARENT's resolved category (``polymarket.py`` sub-market branch), never
           from their own title, so this repair does the same.

That distinction is load-bearing, not tidiness. ``_tags_to_category([])`` returns
no category, which would drop a child into cascade arms 1 and 2 — the table-tennis
group heuristic and the title/league fallback — with a ``group_names`` list this
repair cannot reconstruct. A child classified alone could be relabelled
``table_tennis``. So a child is NEVER classified alone: it inherits, or it is
skipped and counted.

ONE TRANSITION ONLY: ``weather -> health``, DECIDED BY THE SUBJECT ARM (CERT-2364).

The first cut accepted whatever the cascade returned, reasoning that replaying the
shipped cascade cannot be wrong. It can, because the cascade answers a DIFFERENT
question than this repair asks. Against the live shelf it planned 23 writes for 22
disease rows. The 23rd was ``58435808`` — "How many tropical cyclones will make
landfall in China during 2026?" — whose stored tags are ``['china', 'weather']``.
The tag map sends ``china`` to geopolitics, so the cascade returned
``('geopolitics', 'geopolitics', 'tag')`` and this repair would have filed a
tropical-cyclone market under geopolitics: a genuine weather market moved, by a
repair whose whole ship is that disease markets are not weather.

The controls did not catch it because every one of them varied the TITLE while
holding tags at ``('weather',)`` — and the tags are the cascade's actual input. A
control that holds the deciding variable fixed is not a control.

So the gate is now the repair's ship, exactly: arm must be ``subject`` (which means
``misfiled_subject`` read the title and said health) and the destination must be
``health``. Arm ``tag`` means the venue's own tags already decided; re-litigating
that is the poller's job on its next pass, not a repair's.

REFUSALS, each counted separately so no zero is silent (gotcha #53):

    refused_no_tags_no_parent   a child whose parent is absent from the selection
    refused_parent_not_accepted a child whose parent this repair itself refused —
                                inheriting that would move children somewhere the
                                parent was not allowed to go
    refused_other               the cascade returned None/"other" — the writer's own
                                rule is that "other" never overwrites a real value
    refused_unchanged           the cascade agrees with what is stored; nothing to do
    refused_sport               the cascade promoted it to a SPORT category
    refused_not_health_subject  the cascade answered, but not `weather -> health` via
                                the subject arm. This is the `58435808` terminal and
                                it is expected to be NON-ZERO on the live shelf.

D51 — REVERSIBLE, THEREFORE UNATTENDED. The undo record is written to the durable
snapshot rail BEFORE any row is touched, and it stores each row's prior
``llm_sport_category`` and ``category``. If the record does not persist, NOTHING is
written and the run returns ``UNDO_NOT_PERSISTED``: a repair that cannot be undone
is not a repair this lane may apply unattended. Restore with

    POST /api/admin/repairs/weather-shelf-disease?undo_identity=<id>            # dry run
    POST /api/admin/repairs/weather-shelf-disease?undo_identity=<id>&apply=true # put back

Every write is a COMPARE-AND-SET on the exact value the plan selected on, so a
concurrent ordinary poll is never clobbered — if the poller got there first, the
row simply reports ``skipped_changed_under_us`` and the count says so.

ATTENDED-OPTIONAL, NEVER A BEAT. This is a drain with an end state, not a standing
job. It must not be wired into the beat schedule.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: The shelf this repair drains. A module constant, deliberately: making it a
#: parameter would turn a narrow, measured drain into a general re-classifier,
#: and the control population that makes it safe (982 genuine weather markets)
#: is specific to this shelf. #4288 covers the general case.
SUSPECT_CATEGORY = "weather"

#: Only this source. The 22 measured rows are all Polymarket, and the cascade
#: this repair replays is the POLYMARKET cascade — running it over a Kalshi row
#: would be applying one venue's rules to another's data.
SOURCE = "polymarket"

#: Non-sport shelves this repair may write. The cascade can in principle promote a
#: market to a sport (arm 3); that is out of scope here and is counted, not
#: written — see `refused_sport`.
NON_SPORT_DESTINATIONS = frozenset(
    {"health", "politics", "economics", "tech", "geopolitics", "legal",
     "culture", "entertainment", "weather", "crypto"}
)

UNDO_IDENTITY_PREFIX = "repair:weather_shelf_disease:undo"
UNDO_SCHEMA = "weather-shelf-disease-undo/v1"
UNDO_OWNER_KEY = "invocation"
UNDO_MAX_AGE_S = 365 * 86400

REASON_UNDO_UNWRITTEN = "UNDO_NOT_PERSISTED"
REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"

#: What the stored undo record actually lists, reported by every apply.
#: ``written`` — exactly the rows this apply wrote; "restored N of N" is literal.
#: ``plan_superset`` — the narrowing re-publish failed, so the pre-write record
#: (every PLANNED row) is still in force. Safe to restore from, because the
#: restore compare-and-sets on the value this apply wrote and an untouched row
#: cannot match — but it over-lists, so the operator is told.
RECEIPT_WRITTEN = "written"
RECEIPT_PLAN_SUPERSET = "plan_superset"

#: A hard ceiling on one invocation. The measured population is 22 and shrinking
#: as the poller converges the reachable ones; anything an order of magnitude
#: larger means the selection is wrong, and the right response to that is to stop,
#: not to write 500 rows.
APPLY_CAP = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_invocation() -> str:
    return uuid.uuid4().hex[:12]


def plan_hash_for(rows: list[dict[str, Any]]) -> str:
    """Content address of a plan: the rows and the exact transition each names."""
    canonical = json.dumps(
        [
            [r["id"], r["from_category"], r["to_category"], r["from_shelf"], r["to_shelf"]]
            for r in rows
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def undo_identity_for(plan_hash: str, *, at: datetime, invocation: str) -> str:
    stamp = at.strftime("%Y%m%dT%H%M%SZ")
    return f"{UNDO_IDENTITY_PREFIX}:{stamp}:{str(plan_hash)[:12]}:{invocation}"


def classify_from_stored(
    *, name: str, category: str, tags: Optional[list], group_names: list[str]
) -> tuple[Optional[str], Optional[str], str]:
    """Replay the SHIPPED Polymarket cascade against one stored row.

    Returns ``(category, llm_sport_category, arm)`` exactly as the poller's own
    ``resolve_event_category`` returns it. This function adds no rules; it only
    supplies the poller's inputs from columns instead of from a live API payload.
    """
    from app.tasks.polymarket import _tags_to_category, resolve_event_category

    tag_category, tag_shelf = _tags_to_category(list(tags or []))
    return resolve_event_category(tag_category, tag_shelf, name or "", group_names)


async def _select_population(session) -> list[dict[str, Any]]:
    """Every open Polymarket row on the suspect shelf, parents and children."""
    result = await session.execute(
        text(
            "SELECT id, name, category, llm_sport_category, category_tags, "
            "       group_id, external_id "
            "FROM futures_markets "
            "WHERE source = :src AND status = 'open' "
            "  AND llm_sport_category = :cat "
            "ORDER BY id"
        ),
        {"src": SOURCE, "cat": SUSPECT_CATEGORY},
    )
    return [dict(r._mapping) for r in result]


def build_plan(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Decide, for every row on the shelf, what the shipped cascade says about it.

    Pure: takes rows, returns (plan, counts). Everything a test needs to drive the
    decision is an argument, so the decision is testable without a database.
    """
    counts = {
        "examined": len(rows),
        "planned": 0,
        "refused_unchanged": 0,
        "refused_other": 0,
        "refused_sport": 0,
        "refused_not_health_subject": 0,
        "refused_no_tags_no_parent": 0,
        "refused_parent_not_accepted": 0,
        "children_inheriting": 0,
    }

    # A child's parent is the row in its group that carries the tags. Resolved from
    # the SAME selection, so a parent that is not on the suspect shelf (already
    # correct, or already repaired) cannot silently re-shelve its children.
    parents_by_group: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("group_id") and (r.get("category_tags") or []):
            parents_by_group.setdefault(r["group_id"], r)

    plan: list[dict[str, Any]] = []
    #: Parent id -> the shelf it was ACCEPTED into. Only accepted parents are in
    #: here: a child may not inherit a decision this repair itself refused.
    accepted_parents: dict[int, str] = {}

    # Parents first, so a child can read its parent's decided value rather than
    # re-deriving it — one decision per group, which is what the poller does.
    for r in rows:
        if not (r.get("category_tags") or []):
            continue
        new_cat, new_shelf, arm = classify_from_stored(
            name=r["name"],
            category=r["category"],
            tags=r["category_tags"],
            group_names=[r["name"] or ""],
        )
        if not new_shelf or new_shelf == "other":
            counts["refused_other"] += 1
            continue
        if new_shelf not in NON_SPORT_DESTINATIONS:
            counts["refused_sport"] += 1
            continue
        if new_shelf == r["llm_sport_category"]:
            counts["refused_unchanged"] += 1
            continue
        # ═══ THE ONLY TRANSITION THIS REPAIR MAY MAKE (CERT-2364) ═══
        #
        # `weather -> health`, decided by the SUBJECT arm — `misfiled_subject`
        # reading the title — and nothing else.
        #
        # The first cut accepted whatever the cascade returned, on the reasoning
        # that replaying the shipped cascade cannot be wrong. It can, because the
        # cascade answers a DIFFERENT question than this repair asks. Given the
        # live shelf it planned 23 writes for 22 disease rows, and the 23rd was
        # `58435808` — "How many tropical cyclones will make landfall in China
        # during 2026?" — whose stored tags are `['china', 'weather']`. The tag
        # map sends `china` to geopolitics, so the cascade returned
        # `('geopolitics', 'geopolitics', 'tag')` and this repair would have filed
        # a tropical-cyclone market under geopolitics. A genuine weather market,
        # moved, by a repair whose entire ship is that disease markets are not
        # weather.
        #
        # My controls could not see it: every one of them varied the TITLE while
        # holding tags at `('weather',)`, and the tags are the cascade's actual
        # input. A control that holds the deciding variable fixed is not a control.
        #
        # Narrowing to the subject arm makes the repair's scope exactly its ship.
        # Arm `tag` means the venue's own tags already decided, and re-litigating
        # that is the poller's job on its next pass, not a repair's.
        if arm != "subject" or new_shelf != "health":
            counts["refused_not_health_subject"] += 1
            continue
        accepted_parents[r["id"]] = new_shelf
        plan.append(
            {
                "id": r["id"],
                "name": r["name"],
                "kind": "parent",
                "arm": arm,
                "from_shelf": r["llm_sport_category"],
                "to_shelf": new_shelf,
                "from_category": r["category"],
                "to_category": new_cat,
            }
        )

    # Children inherit — from an ACCEPTED parent only. Never classified alone.
    for r in rows:
        if r.get("category_tags") or []:
            continue
        parent = parents_by_group.get(r.get("group_id") or "")
        if parent is None:
            counts["refused_no_tags_no_parent"] += 1
            continue
        new_shelf = accepted_parents.get(parent["id"])
        if new_shelf is None:
            # The parent was refused for one of the reasons above. Inheriting a
            # decision this repair declined to make on the parent would move the
            # children somewhere the parent itself was not allowed to go.
            counts["refused_parent_not_accepted"] += 1
            continue
        if new_shelf == r["llm_sport_category"]:
            counts["refused_unchanged"] += 1
            continue
        counts["children_inheriting"] += 1
        plan.append(
            {
                "id": r["id"],
                "name": r["name"],
                "kind": "child",
                "arm": f"inherit:{parent['id']}",
                "from_shelf": r["llm_sport_category"],
                "to_shelf": new_shelf,
                # A child's own `category` is its market shape (game_prop etc.) and
                # the poller does not rewrite it from the parent, so neither do we.
                "from_category": r["category"],
                "to_category": r["category"],
            }
        )

    counts["planned"] = len(plan)
    return plan, counts


def _receipt_rows(
    plan: list[dict[str, Any]], written: list[int]
) -> list[dict[str, Any]]:
    """The rows the undo record may honestly claim: those actually written.

    Pure, so the rule can be guarded without a session. Order follows the plan,
    not the write log, so the receipt is stable for a given plan.
    """
    written_ids = set(written)
    return [p for p in plan if p["id"] in written_ids]


async def _write_undo(identity: str, invocation: str, plan: list[dict[str, Any]]) -> bool:
    from app.services.durable_snapshots import publish_owned_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        source="repair_weather_shelf_disease",
        payload={
            "invocation": invocation,
            "written_at": _now().isoformat(),
            "rows": [
                {
                    "id": p["id"],
                    "prior_shelf": p["from_shelf"],
                    "prior_category": p["from_category"],
                    "applied_shelf": p["to_shelf"],
                    "applied_category": p["to_category"],
                }
                for p in plan
            ],
        },
    )
    stage = await publish_owned_snapshot_standalone(
        envelope, owner_key=UNDO_OWNER_KEY, owner=invocation
    )
    return stage.get("status") == "ok"


async def _read_undo(identity: str) -> tuple[Optional[dict[str, Any]], str]:
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
    )
    payload = getattr(read, "payload", None)
    if payload is None:
        return None, REASON_UNDO_MISSING
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


async def repair(
    session,
    apply: bool = False,
    *,
    limit: Optional[int] = None,
    undo_identity: Optional[str] = None,
    **_ignored,
) -> dict[str, Any]:
    """Drain the suspect shelf, or put one earlier apply back.

    Dry run by default: it returns the plan and its content address and writes
    nothing. ``apply=true`` writes the undo record first, then compare-and-sets
    each row.
    """
    if undo_identity:
        return await _restore(session, apply, undo_identity)

    rows = await _select_population(session)
    plan, counts = build_plan(rows)
    digest = plan_hash_for(plan)

    if len(plan) > APPLY_CAP:
        return {
            "measured": True,
            "applied": False,
            "reason": "PLAN_OVER_CAP",
            "detail": (
                f"{len(plan)} rows planned against a cap of {APPLY_CAP}. A population "
                "this size means the selection is wrong; stopping rather than writing."
            ),
            "counts": counts,
            "plan_hash": digest,
        }

    if limit is not None:
        plan = plan[: max(0, int(limit))]
        digest = plan_hash_for(plan)

    if not apply:
        return {
            "measured": True,
            "applied": False,
            "shelf": SUSPECT_CATEGORY,
            "counts": counts,
            "plan_hash": digest,
            "plan": plan,
        }

    if not plan:
        # A zero-yield apply gets its own terminal rather than a silent success.
        return {
            "measured": True,
            "applied": False,
            "reason": "NOTHING_TO_DO",
            "counts": counts,
            "plan_hash": digest,
        }

    invocation = new_invocation()
    identity = undo_identity_for(digest, at=_now(), invocation=invocation)
    if not await _write_undo(identity, invocation, plan):
        return {
            "measured": True,
            "applied": False,
            "reason": REASON_UNDO_UNWRITTEN,
            "detail": (
                "The undo record did not persist, so nothing was written. A repair "
                "that cannot be reversed is not one this lane may apply unattended."
            ),
            "counts": counts,
            "plan_hash": digest,
        }

    written, skipped = [], []
    for p in plan:
        result = await session.execute(
            text(
                "UPDATE futures_markets "
                "SET llm_sport_category = :new_shelf, category = :new_cat "
                "WHERE id = :mid "
                "  AND llm_sport_category = :old_shelf "
                "  AND category = :old_cat"
            ),
            {
                "mid": p["id"],
                "new_shelf": p["to_shelf"],
                "new_cat": p["to_category"],
                "old_shelf": p["from_shelf"],
                "old_cat": p["from_category"],
            },
        )
        (written if result.rowcount == 1 else skipped).append(p["id"])
    await session.commit()

    # FOLLOW-UP `4264-UNDO-RESTORES-ONLY-RECEIPTED-WRITES` (CERT-2364).
    #
    # The record written above lists every PLANNED row, because it has to exist
    # before the first write — a record written afterwards is not a safety net.
    # But a plan is not a receipt: a row whose compare-and-set missed was never
    # touched by this apply, and the restore must not claim it.
    #
    # The restore is already SAFE without this: it compare-and-sets on the value
    # this apply wrote, so an untouched row cannot match and is simply skipped.
    # What it was not, was HONEST — an untouched row landed in
    # `skipped_changed_since`, which names a cause that did not happen. Narrowing
    # the receipt to `written` makes "restored N of N" mean what it says.
    #
    # The re-publish can itself fail, and then the pre-write record — a strict
    # SUPERSET of what was written — stays in force. That is still safe to
    # restore from, for the same compare-and-set reason, but it is no longer the
    # honest receipt, so the caller is TOLD rather than left to assume. A silent
    # fallback here would be exactly the class of zero this module counts.
    receipt = _receipt_rows(plan, written)
    undo_receipt = RECEIPT_WRITTEN
    if len(receipt) != len(plan):
        if not await _write_undo(identity, invocation, receipt):
            undo_receipt = RECEIPT_PLAN_SUPERSET

    return {
        "measured": True,
        "applied": True,
        "shelf": SUSPECT_CATEGORY,
        "counts": counts,
        "plan_hash": digest,
        "undo_identity": identity,
        "undo_receipt": undo_receipt,
        "rows_written": len(written),
        "written_ids": written,
        "skipped_changed_under_us": skipped,
        "restore": (
            "POST /api/admin/repairs/weather-shelf-disease"
            f"?undo_identity={identity}&apply=true"
        ),
    }


async def _restore(session, apply: bool, identity: str) -> dict[str, Any]:
    payload, reason = await _read_undo(identity)
    if payload is None:
        return {
            "measured": False,
            "applied": False,
            "reason": reason,
            "undo_identity": identity,
        }

    rows = payload["rows"]
    if not apply:
        return {
            "measured": True,
            "applied": False,
            "undo_identity": identity,
            "would_restore": len(rows),
            "rows": rows,
        }

    restored, skipped = [], []
    for r in rows:
        # Compare-and-set on the value THIS repair applied: a row somebody has
        # since changed is left alone rather than dragged back.
        result = await session.execute(
            text(
                "UPDATE futures_markets "
                "SET llm_sport_category = :prior_shelf, category = :prior_cat "
                "WHERE id = :mid "
                "  AND llm_sport_category = :applied_shelf "
                "  AND category = :applied_cat"
            ),
            {
                "mid": r["id"],
                "prior_shelf": r["prior_shelf"],
                "prior_cat": r["prior_category"],
                "applied_shelf": r["applied_shelf"],
                "applied_cat": r["applied_category"],
            },
        )
        (restored if result.rowcount == 1 else skipped).append(r["id"])
    await session.commit()

    return {
        "measured": True,
        "applied": True,
        "undo_identity": identity,
        "rows_restored": len(restored),
        "restored_ids": restored,
        "skipped_changed_since": skipped,
    }
