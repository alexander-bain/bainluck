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

REFUSALS, each counted separately so no zero is silent (gotcha #53):

    refused_no_tags_no_parent   a child whose parent is absent or itself unresolved
    refused_other               the cascade returned None/"other" — the writer's own
                                rule is that "other" never overwrites a real value
    refused_unchanged           the cascade agrees with what is stored; nothing to do
    refused_sport               the cascade promoted it to a SPORT category. Out of
                                scope here and a signal something else is wrong;
                                this repair only moves rows between non-sport
                                shelves, exactly as its ship describes.

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
        "refused_no_tags_no_parent": 0,
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
    resolved_parent_shelf: dict[int, Optional[str]] = {}

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
        resolved_parent_shelf[r["id"]] = new_shelf
        if not new_shelf or new_shelf == "other":
            counts["refused_other"] += 1
            continue
        if new_shelf not in NON_SPORT_DESTINATIONS:
            counts["refused_sport"] += 1
            continue
        if new_shelf == r["llm_sport_category"]:
            counts["refused_unchanged"] += 1
            continue
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

    # Children inherit. Never classified alone — see the module docstring.
    for r in rows:
        if r.get("category_tags") or []:
            continue
        parent = parents_by_group.get(r.get("group_id") or "")
        if parent is None:
            counts["refused_no_tags_no_parent"] += 1
            continue
        new_shelf = resolved_parent_shelf.get(parent["id"])
        if not new_shelf or new_shelf == "other":
            counts["refused_other"] += 1
            continue
        if new_shelf not in NON_SPORT_DESTINATIONS:
            counts["refused_sport"] += 1
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

    return {
        "measured": True,
        "applied": True,
        "shelf": SUSPECT_CATEGORY,
        "counts": counts,
        "plan_hash": digest,
        "undo_identity": identity,
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
