"""A complete NFL week publishes itself; a wrong, partial or corrected one never does. #5341.

**SHIP: the next authority-defined NFL week becomes a complete usable hub
without a per-week declaration or publication command; wrong or partial weeks
stay withheld and corrected hubs stay corrected.** (Pillars: MATCHING /
DISCOVER / TRUTH.)

Assembly already finds the week (`container_assembly.nfl_weeks_in_window`, from
the authority's own ``stage / week`` label) and its members (by StatPal contest
id, `container_nfl`). What it never did is publish: `publish_container` says
"assembly never calls this; a named decision does", so every new week waited on
an operator (`scripts/collection_publication.py`). This module is the one
automatic decision, taken inside the same transaction as the pass that proved
the week, through the SAME helper and the same ledger an operator uses.

DARK BY DEFAULT. ``CONTAINER_NFL_AUTO_PUBLISH_ENABLED`` is read at call time and
is its own switch: the assembly flag (``CONTAINER_COLLECTIONS_ENABLED``) grants
edges, never publication, and no existing control is a publication policy.
With it off this module issues no statement; it still reports the harvest's
verdict, so a pass report shows what WOULD publish before anyone turns it on.

PUBLISH MEANS ALL OF THESE, AND FAILS CLOSED ON EACH:

* the pass applied, and the authority named the week (season known, it is the
  declared season, the week is in the schedule);
* every contest the authority files under the week is exactly one member game
  — compared as a SET of contest ids, never a count (gotcha #53) — with no
  contest lacking a row of ours, no two rows for one game, no contest also filed
  under another week, no capped question read, and no id-less or placeholder
  slot filed under this week;
* the hub is ``unpublished`` and its ledger holds no publication decision and
  no member withdrawal: a person who has touched the hub decides for it;
* the stored ``contains`` edges ARE the members this pass proved: the event set
  equal, every market edge one this pass would write. An edge left from a game
  the authority has since moved to another week is a wrong hub, not a bonus;
* the reader's own eligibility (`container_discovery.collection_card`) accepts
  it as a published root NFL-week edition of this exact season/stage/week.

WHAT IT NEVER DOES. It never withdraws, never unpublishes and never re-publishes
a ``withdrawn`` hub. A published week that a later pass cannot vouch for — a
schedule outage, a game that lost its row — keeps its published state and says
so (``retained``): a degraded read is not a retirement, and taking a hub back is
a named decision (`withdraw_publication`). It adds no member, writes no edge,
and never commits; the caller's transaction keeps or drops the publish together
with the assembly that proved it.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy import text

from app.utils.container_corrections import (
    LEDGER_TABLE,
    CorrectionRefused,
    correction_schema_present,
    current_members,
    lock_container_chain,
    publish_container,
    withdrawn_members,
)
from app.utils.container_nfl import (
    EXCLUDED_NO_CONTEST_ID,
    EXCLUDED_PLACEHOLDER,
    UNAVAILABLE_SEASON_MISMATCH,
    UNAVAILABLE_WEEK_NOT_SCHEDULED,
    NflWeek,
    parse_round_identity,
)

logger = logging.getLogger(__name__)

AUTO_PUBLISH_ENV = "CONTAINER_NFL_AUTO_PUBLISH_ENABLED"

#: Stamped on every report and in every ledger row this writes, so a later
#: policy change can tell which rule published a hub.
POLICY = "nfl_week_auto_publication/v1"

#: The ledger's ``actor`` (VARCHAR(64)). Never a person's name: nobody decided.
ACTOR = "auto:container_nfl_publication"

# --- decisions (closed; tests and the activation note read these names) -------

DECISION_DISABLED = "disabled"  # switch off: no statement issued
DECISION_NOT_APPLIED = "not_applied"  # dry run, or a stand-in with no row
DECISION_PUBLISHED = "published"  # this pass published the hub
DECISION_ALREADY_PUBLISHED = "already_published"  # complete, and already for readers
DECISION_RETAINED = "retained"  # published, this pass could not vouch; unchanged
DECISION_WITHHELD = "withheld"  # not for readers, and this pass did not change that

# --- why a week is withheld (closed) ------------------------------------------

REFUSED_NOT_SCHEDULED = UNAVAILABLE_WEEK_NOT_SCHEDULED
REFUSED_SEASON_MISMATCH = UNAVAILABLE_SEASON_MISMATCH
REFUSED_CONTESTS_UNACCOUNTED = "contests_not_exactly_members"
REFUSED_ID_LESS_SLOT = "week_slot_without_contest_id"
REFUSED_PLACEHOLDER_SLOT = "week_slot_is_placeholder"
REFUSED_SCHEMA_ABSENT = "publication_schema_absent"
REFUSED_ROW_ABSENT = "container_row_absent"
REFUSED_WITHDRAWN = "publication_withdrawn"
REFUSED_UNKNOWN_STATE = "unknown_publication_state"
REFUSED_PRIOR_DECISION = "prior_publication_decision"
REFUSED_MEMBER_WITHDRAWN = "member_withdrawn"
REFUSED_NOT_ASSEMBLED = "not_assembled"
REFUSED_ASSEMBLY_ERRORS = "assembly_errors"
REFUSED_STORED_DIFFER = "stored_members_differ"
REFUSED_WRONG_EDITION = "not_this_week_edition"
REFUSED_READER_PREFIX = "reader_ineligible:"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def auto_publish_enabled() -> bool:
    """Read at call time, so it flips without a restart, and off unless set."""
    return os.environ.get(AUTO_PUBLISH_ENV, "").strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# The pure half: does the harvest account for the whole week?
# ---------------------------------------------------------------------------


def harvest_refusal(harvest, target: NflWeek) -> Optional[str]:
    """None when this read accounts for every game the authority files under
    ``target``; otherwise the first reason it does not. Pure.

    The authority's own words first (`schedule_season_unknown`, …), then
    `week_incompleteness`'s, then the two set checks those leave open: the
    contest ids against the member games' ids, and the schedule slots that never
    reached the contest list because they carry no id or no real teams.
    """
    selection = harvest.selection
    if selection.unavailable:
        return selection.unavailable
    if selection.season != target.season:
        return REFUSED_SEASON_MISMATCH
    if not selection.contests:
        return REFUSED_NOT_SCHEDULED

    incomplete = harvest.incomplete
    if incomplete:
        return incomplete[0]

    contest_ids = [c.contest_id for c in selection.contests]
    game_ids = [g.get("statpal_id") for g in harvest.members.games]
    event_ids = [c.child_id for c in harvest.candidates if c.child_type == "event"]
    if (
        len(set(contest_ids)) != len(contest_ids)
        or sorted(game_ids) != sorted(contest_ids)
        or len(set(event_ids)) != len(contest_ids)
    ):
        return REFUSED_CONTESTS_UNACCOUNTED

    here = (target.stage, target.week)
    for receipt in selection.excluded.get(EXCLUDED_NO_CONTEST_ID, ()):
        # No id, so no join — and an unreadable round could be this week.
        identity = parse_round_identity(receipt.get("round"))
        if identity is None or identity == here:
            return REFUSED_ID_LESS_SLOT
    for receipt in selection.excluded.get(EXCLUDED_PLACEHOLDER, ()):
        # A bracket slot elsewhere in the schedule is normal; one in THIS week
        # is a game the authority has not named yet.
        if parse_round_identity(receipt.get("round")) == here:
            return REFUSED_PLACEHOLDER_SLOT
    return None


def _assembly_refusal(assembly: Optional[dict]) -> Optional[str]:
    if not assembly:
        return REFUSED_NOT_ASSEMBLED
    if assembly.get("errors") or assembly.get("unresolved"):
        return REFUSED_ASSEMBLY_ERRORS
    if assembly.get("withdrawn"):
        return REFUSED_MEMBER_WITHDRAWN
    return None


# ---------------------------------------------------------------------------
# The read half (only with the switch on, only on an applied pass)
# ---------------------------------------------------------------------------

_PUBLICATION_DECISIONS_SQL = (
    f"SELECT count(*) FROM {LEDGER_TABLE} "
    "WHERE container_id = :cid AND scope = 'publication'"
)

#: The hub as `collection_card` reads it: its own row, and the members whose row
#: we still hold. Flat by construction (NFL weeks have no draws), and a nested
#: row is refused by the card anyway.
_HUB_FACTS_SQL = (
    "SELECT c.id, c.slug, c.name, c.status, c.window_start, c.window_end, "
    "       c.parent_container_id, c.membership_revision, "
    "       COUNT(DISTINCT ev.id) AS game_count, "
    "       COUNT(DISTINCT fm.id) AS question_count "
    "FROM containers c "
    "LEFT JOIN event_edges e ON e.parent_type = 'container' AND e.kind = 'contains' "
    "      AND e.parent_id = c.id "
    "LEFT JOIN events ev ON e.child_type = 'event' AND ev.id = e.child_id "
    "LEFT JOIN futures_markets fm ON e.child_type = 'market' AND fm.id = e.child_id "
    "WHERE c.id = :cid "
    "GROUP BY c.id"
)


def _stored_difference(stored: dict, candidates: list) -> Optional[dict]:
    """What the stored edges hold that this pass did not prove, or lack. None = same."""
    events = {c.child_id for c in candidates if c.child_type == "event"}
    markets = {c.child_id for c in candidates if c.child_type == "market"}
    stored_events = {cid for (ct, cid) in stored if ct == "event"}
    stored_markets = {cid for (ct, cid) in stored if ct == "market"}
    other = sorted(f"{ct}:{cid}" for (ct, cid) in stored if ct not in ("event", "market"))
    diff = {
        "events_not_proved": sorted(stored_events - events),
        "events_missing": sorted(events - stored_events),
        "markets_not_proved": sorted(stored_markets - markets),
        "other_children": other,
    }
    return diff if any(diff.values()) else None


def _report(decision: str, reason: Optional[str], **extra) -> dict:
    return {"policy": POLICY, "decision": decision, "reason": reason, **extra}


async def publish_complete_week(
    session,
    container,
    target: NflWeek,
    harvest,
    assembly: Optional[dict],
    *,
    apply: bool,
) -> dict:
    """The publication decision for one NFL week, after its assembly. Never commits.

    ``harvest`` is the pass's `NflWeekHarvest`; ``assembly`` is its
    ``assemble_container`` report as a dict (None when nothing was assembled).
    Returns the ``publication`` block of the week's report.
    """
    refusal = harvest_refusal(harvest, target)
    if not auto_publish_enabled():
        return _report(
            DECISION_DISABLED,
            None,
            env=AUTO_PUBLISH_ENV,
            harvest_complete=refusal is None,
            harvest_refusal=refusal,
        )
    container_id = getattr(container, "id", None)
    if not apply or container_id is None:
        return _report(
            DECISION_NOT_APPLIED,
            None,
            harvest_complete=refusal is None,
            harvest_refusal=refusal,
        )

    schema = await correction_schema_present(session)
    if not schema.complete:
        return _report(DECISION_WITHHELD, REFUSED_SCHEMA_ABSENT)

    # Root-first, the order assembly and every correction take; re-entrant in
    # this transaction when assembly already holds it.
    row = await lock_container_chain(session, container_id)
    if row is None:
        return _report(DECISION_WITHHELD, REFUSED_ROW_ABSENT)
    state, revision = row[1], int(row[2])
    held = {"publication_state": state, "revision": revision}

    if state == "withdrawn":
        # A named decision took it back. Only another named decision restores it.
        return _report(DECISION_WITHHELD, REFUSED_WITHDRAWN, **held)
    if state == "published":
        if refusal is not None:
            return _report(DECISION_RETAINED, refusal, **held)
        return _report(DECISION_ALREADY_PUBLISHED, None, **held)
    if state != "unpublished":
        return _report(DECISION_WITHHELD, REFUSED_UNKNOWN_STATE, **held)
    if refusal is not None:
        return _report(DECISION_WITHHELD, refusal, **held)

    decisions = (
        await session.execute(text(_PUBLICATION_DECISIONS_SQL), {"cid": container_id})
    ).scalar()
    if decisions:
        return _report(DECISION_WITHHELD, REFUSED_PRIOR_DECISION, **held)
    if await withdrawn_members(session, container_id):
        return _report(DECISION_WITHHELD, REFUSED_MEMBER_WITHDRAWN, **held)

    assembly_refusal = _assembly_refusal(assembly)
    if assembly_refusal is not None:
        return _report(DECISION_WITHHELD, assembly_refusal, **held)

    difference = _stored_difference(
        await current_members(session, container_id), harvest.candidates
    )
    if difference is not None:
        return _report(DECISION_WITHHELD, REFUSED_STORED_DIFFER, difference=difference, **held)

    facts = (
        await session.execute(text(_HUB_FACTS_SQL), {"cid": container_id})
    ).mappings().one_or_none()
    if facts is None:
        return _report(DECISION_WITHHELD, REFUSED_ROW_ABSENT, **held)

    from app.services.container_discovery import collection_card

    card, excluded = collection_card(
        {
            **dict(facts),
            "revision": facts["membership_revision"],
            "publication_state": "published",
        },
        league="nfl",
        season=target.season,
    )
    if card is None:
        return _report(DECISION_WITHHELD, f"{REFUSED_READER_PREFIX}{excluded}", **held)
    edition = card["edition"]
    if (edition.get("stage"), edition.get("week")) != (target.stage, target.week):
        return _report(DECISION_WITHHELD, REFUSED_WRONG_EDITION, **held)

    contest_ids = sorted(c.contest_id for c in harvest.selection.contests)
    member_events = sorted(c.child_id for c in harvest.candidates if c.child_type == "event")
    evidence = {
        "policy": POLICY,
        "issue": 5341,
        "slug": target.slug,
        "season": target.season,
        "stage": target.stage,
        "week": target.week,
        "contest_ids": contest_ids,
        "member_event_ids": member_events,
        "game_count": int(facts["game_count"]),
        "question_count": int(facts["question_count"]),
        "revision_before": revision,
    }
    try:
        result = await publish_container(
            session,
            container_id=container_id,
            reason=(
                f"authority schedule assembly complete: all {len(contest_ids)} "
                f"contests of {target.slug} are exactly its member games"
            ),
            actor=ACTOR,
            evidence=evidence,
            expected_revision=revision,
        )
    except CorrectionRefused as exc:
        # The helper refused before writing (NothingToPublish, StaleRevision):
        # withheld, and the pass's edges stand.
        logger.warning("NFL week %s: publication refused: %s", target.slug, exc)
        return _report(DECISION_WITHHELD, type(exc).__name__, error=str(exc), **held)

    if not result.applied:
        return _report(
            DECISION_ALREADY_PUBLISHED,
            None,
            publication_state=result.publication_state,
            revision=result.revision,
        )
    logger.info("NFL week %s published at revision %s (%s)", target.slug, result.revision, POLICY)
    return _report(
        DECISION_PUBLISHED,
        None,
        publication_state=result.publication_state,
        revision=result.revision,
        revision_before=revision,
        contests=len(contest_ids),
    )
