"""#11007: take back the grades and the ``resolved`` status written on Polymarket
legs the venue has not closed. Attended, exact-id, dry-run by default.

## what a reader sees

``/futures/113883`` ("Fed rate cut by...?", Gamma event ``106884``) prints
"This market has been settled" with **October Meeting — Lost** and **December
Meeting — Lost**. Polymarket still trades both (``closed: false``). After this
rail, the page is an open market again: October and December carry no verdict
and keep their live price, while the six meetings the venue really closed keep
their results.

## what went wrong, and why the forward fix cannot undo it

On 2026-07-21 parent 113883 and its eight decomposed legs were stamped
``status='resolved'`` against a stored ``resolution_date`` of 2026-06-17. The
venue's event runs to 2028-01-29. That status selected the parent for
``_backfill_polymarket_winners_from_api``, which on 2026-09-28 graded every leg
on its quote: October ``is_winner=false`` at 0.0095, December at 0.023, both
``resolution_source='api_settlement'``. PR #11008 stops that grader touching an
open leg. It cannot take back a grade it already wrote, and nothing else does:

* the poll's outcome upsert sets price and book fields and never touches
  ``is_winner`` or ``resolution_source``;
* the poll never reaches the parent at all. It reads the newest 2,000 open
  events and 106884 started 2025-12-16, and the sunk-event recovery pass
  (``_recover_sunk_polymarket_events``) selects only ``status='open'`` parents
  with a ``resolution_date`` no older than its staleness floor. A status flip
  alone leaves 2026-06-17 below that floor, so the parent would stay
  unreachable.

## what is written, and on what proof

Per named parent, ONE fresh direct read of ``GET /events/{id}``
(``get_event_by_id``: ``None`` only for a 404, and a 429 is raised, never read as
an answer, gotcha #36). The venue's raw flags are read strictly: ``closed`` must
be the JSON boolean ``false`` for a leg to count as open and ``true`` for it to
count as closed. Anything else, including absent or ``"false"``, refuses the
whole parent. (The DTO parser defaults an absent ``closed`` to ``False``, so the
raw body is read here, not the DTO.)

For every stored leg the venue lists as open, and only those:

* each outcome on that leg graded ``api_settlement`` ->
  ``is_winner = NULL, resolution_source = NULL``. That is the repository's
  ungraded state: the reader prints no verdict for it, calibration does not count
  it, and the venue's own close grades it later through the normal rails;
* the leg's own decomposed market row ->
  ``status='open', settled_at=NULL, resolution_date=<the leg's venue endDate>``.

And the parent, when its event is open at the venue ->
``status='open', settled_at=NULL, resolution_date=<the event's venue endDate>``.
That is the same status and ``settled_at`` the poll's writer stamps on a venue-open
event (``_process_event_batch``), and the same dates it would write if it ever
reached them. The date is what puts the parent back inside the recovery pass, so
the venue's own refresh, not this rail, keeps it current from then on.

Legs the venue CLOSED are controls: none of their rows is written, whatever they
hold. No winner is ever written. No grade is inferred from a quote. The only
source cleared is ``api_settlement``, the grader that wrote these. A venue-open
leg graded by any other source, or holding a sourceless ``true`` (or, on the
parent's own outcomes, a sourceless ``false``), refuses the
parent by name for a person to read.

Refused BY NAME, with nothing written: event closed, inactive or archived at the
venue; malformed event or leg flags; an absent, elapsed or unparseable venue end
date; the event id the venue echoes differing from the one stored; a stored leg
the venue does not list; a duplicated condition id; a venue-open leg already in
UMA resolution; an outcome or group member whose id is not one of the condition
id forms the poll writes; a status other than ``open``/``resolved``; a venue 404
or a venue error; and nothing to repair.

## the apply is bound to a reviewed exact-id plan

Exact parent ids only, dry run and apply alike. The population is the
measurement lane's to name. Each parent expands to its own group
(``group_id = 'polymarket:<event id>'``), and the plan lists every member. The
plan hash covers the named ids, every row to be written (prior values and row
version, ``xmin``), every control grade, and the venue answer (flags and end
dates, never the moving quotes). A same-value write between the reviewed dry run
and the apply moves a row version, so the apply refuses whole
(``refused_plan_drift``). Each parent is then ONE transaction under statement and
lock timeouts: every row it writes is locked ``FOR UPDATE`` and re-compared with
the plan; each UPDATE repeats the prior values and the row version in its
``WHERE``, and each row count is checked. A parent never half-moves.

## D51: backup, audit and restore

The before-image of every written row goes into :data:`BAK_MARKETS` /
:data:`BAK_OUTCOMES` in the same transaction as the write, with the row version
the write left. The restore's dry run is the audit (per plan hash and parent:
``written``, ``restored`` or ``moved``). It puts a parent back only when EVERY row
it wrote is still exactly the version this rail's write left. A later writer
moves the row version even when it changes no value, so a parent touched by the
poll, a grader or anything else afterwards is ``moved`` and is never restored::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/pm-open-leg-false-grade-restore?apply=true"

ATTENDED ONLY: never wire this to a beat. Runtime DDL (the backup tables) runs
only inside an attended apply.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.tasks import repair_winner_field as rwf

logger = logging.getLogger(__name__)

ISSUE = "#11007"
TASK = "repair_pm_open_leg_grade_11007"

SOURCE = "polymarket"
OPEN_STATUS = "open"
RESOLVED_STATUS = "resolved"

#: The one grading source this rail takes back: the Gamma winner rail that wrote
#: the specimen's grades.
CLEARABLE_SOURCE = "api_settlement"

#: Exact parent ids per call.
APPLY_PARENT_CAP = 10

#: Decomposed members one parent may carry. The specimen has 8 stored and the
#: venue lists 13; anything far past that is not this shape.
MEMBER_CAP = 60

BAK_MARKETS = "bak_11007_open_leg_markets"
BAK_OUTCOMES = "bak_11007_open_leg_outcomes"

#: Bumped whenever the plan's shape or the write changes.
PLAN_VERSION = "11007-open-leg-v1"

WALL_BUDGET_S = rwf.WALL_BUDGET_S
STATEMENT_TIMEOUT = rwf.STATEMENT_TIMEOUT
LOCK_TIMEOUT = rwf.LOCK_TIMEOUT

_MARKET_COLS = """id, source, external_id, group_id, status, settled_at,
    resolution_date, xmin::text AS row_version"""

_PARENT_SQL = f"SELECT {_MARKET_COLS} FROM futures_markets WHERE id = :mid"

_MEMBERS_SQL = f"""
    SELECT {_MARKET_COLS} FROM futures_markets
    WHERE group_id = :gid AND id <> :mid
    ORDER BY id
    LIMIT :cap
"""

_OUTCOMES_SQL = """
    SELECT id, market_id, external_id, name, is_winner, resolution_source,
           xmin::text AS row_version
    FROM futures_outcomes
    WHERE market_id = ANY(:mids)
    ORDER BY id
"""

_LOCK_MARKETS = f"""
    SELECT {_MARKET_COLS} FROM futures_markets
    WHERE id = ANY(:ids) ORDER BY id FOR UPDATE
"""

_LOCK_OUTCOMES = """
    SELECT id, market_id, external_id, name, is_winner, resolution_source,
           xmin::text AS row_version
    FROM futures_outcomes
    WHERE id = ANY(:ids) ORDER BY id FOR UPDATE
"""

_BAK_MARKETS_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_MARKETS} (
        market_id BIGINT NOT NULL,
        plan_hash TEXT NOT NULL,
        parent_id BIGINT NOT NULL,
        prior_status VARCHAR(20) NOT NULL,
        prior_settled_at TIMESTAMPTZ,
        prior_resolution_date TIMESTAMPTZ,
        prior_row_version TEXT NOT NULL,
        wrote_status VARCHAR(20) NOT NULL,
        wrote_settled_at TIMESTAMPTZ,
        wrote_resolution_date TIMESTAMPTZ,
        wrote_row_version TEXT,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (market_id, plan_hash)
    )
"""

_BAK_OUTCOMES_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_OUTCOMES} (
        outcome_id BIGINT NOT NULL,
        plan_hash TEXT NOT NULL,
        parent_id BIGINT NOT NULL,
        market_id BIGINT NOT NULL,
        prior_is_winner BOOLEAN,
        prior_resolution_source VARCHAR(30),
        prior_row_version TEXT NOT NULL,
        wrote_row_version TEXT,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (outcome_id, plan_hash)
    )
"""

#: Copied FROM the locked row itself, so the bank holds what was really there.
_BAK_MARKET_COPY = f"""
    INSERT INTO {BAK_MARKETS} (
        market_id, plan_hash, parent_id, prior_status, prior_settled_at,
        prior_resolution_date, prior_row_version, wrote_status, wrote_settled_at,
        wrote_resolution_date)
    SELECT id, :plan_hash, :parent_id, status, settled_at, resolution_date,
           xmin::text, :wrote_status, CAST(:wrote_settled_at AS TIMESTAMPTZ),
           CAST(:wrote_resolution_date AS TIMESTAMPTZ)
    FROM futures_markets WHERE id = :id
    RETURNING prior_status, prior_settled_at, prior_resolution_date, prior_row_version
"""

_BAK_OUTCOME_COPY = f"""
    INSERT INTO {BAK_OUTCOMES} (
        outcome_id, plan_hash, parent_id, market_id, prior_is_winner,
        prior_resolution_source, prior_row_version)
    SELECT id, :plan_hash, :parent_id, market_id, is_winner, resolution_source,
           xmin::text
    FROM futures_outcomes WHERE id = :id
    RETURNING prior_is_winner, prior_resolution_source, prior_row_version
"""

_WRITE_MARKET = """
    UPDATE futures_markets
    SET status = :wrote_status,
        settled_at = CAST(:wrote_settled_at AS TIMESTAMPTZ),
        resolution_date = CAST(:wrote_resolution_date AS TIMESTAMPTZ)
    WHERE id = :id AND xmin::text = :ver
      AND status = :prior_status
      AND settled_at IS NOT DISTINCT FROM CAST(:prior_settled_at AS TIMESTAMPTZ)
      AND resolution_date IS NOT DISTINCT FROM CAST(:prior_resolution_date AS TIMESTAMPTZ)
"""

_WRITE_OUTCOME = """
    UPDATE futures_outcomes
    SET is_winner = NULL, resolution_source = NULL
    WHERE id = :id AND xmin::text = :ver
      AND is_winner IS NOT DISTINCT FROM CAST(:prior_is_winner AS BOOLEAN)
      AND resolution_source = :clearable
"""

_BAK_MARKET_VERSION = f"""
    UPDATE {BAK_MARKETS} b SET wrote_row_version = fm.xmin::text
    FROM futures_markets fm
    WHERE fm.id = b.market_id AND b.market_id = :id AND b.plan_hash = :plan_hash
"""

_BAK_OUTCOME_VERSION = f"""
    UPDATE {BAK_OUTCOMES} b SET wrote_row_version = fo.xmin::text
    FROM futures_outcomes fo
    WHERE fo.id = b.outcome_id AND b.outcome_id = :id AND b.plan_hash = :plan_hash
"""

_EXISTS = "SELECT to_regclass(:t) IS NOT NULL"

#: One row per banked row. ``still_written``: exactly the version this rail's
#: write left. ``at_prior``: every restored field equals the before-image.
_AUDIT_MARKETS = f"""
    SELECT 'market' AS kind, b.plan_hash, b.parent_id, b.market_id AS row_id,
           (fm.id IS NOT NULL AND fm.xmin::text = b.wrote_row_version) AS still_written,
           (fm.id IS NOT NULL
            AND (fm.status, fm.settled_at, fm.resolution_date) IS NOT DISTINCT FROM
                (b.prior_status, b.prior_settled_at, b.prior_resolution_date)) AS at_prior
    FROM {BAK_MARKETS} b
    LEFT JOIN futures_markets fm ON fm.id = b.market_id
    WHERE (CAST(:plan_hash AS TEXT) IS NULL OR b.plan_hash = CAST(:plan_hash AS TEXT))
      AND (CAST(:parent_id AS BIGINT) IS NULL OR b.parent_id = CAST(:parent_id AS BIGINT))
    ORDER BY b.plan_hash, b.parent_id, b.market_id
"""

_AUDIT_OUTCOMES = f"""
    SELECT 'outcome' AS kind, b.plan_hash, b.parent_id, b.outcome_id AS row_id,
           (fo.id IS NOT NULL AND fo.xmin::text = b.wrote_row_version) AS still_written,
           (fo.id IS NOT NULL
            AND (fo.is_winner, fo.resolution_source) IS NOT DISTINCT FROM
                (b.prior_is_winner, b.prior_resolution_source)) AS at_prior
    FROM {BAK_OUTCOMES} b
    LEFT JOIN futures_outcomes fo ON fo.id = b.outcome_id
    WHERE (CAST(:plan_hash AS TEXT) IS NULL OR b.plan_hash = CAST(:plan_hash AS TEXT))
      AND (CAST(:parent_id AS BIGINT) IS NULL OR b.parent_id = CAST(:parent_id AS BIGINT))
    ORDER BY b.plan_hash, b.parent_id, b.outcome_id
"""

_RESTORE_LOCK_MARKETS = f"""
    SELECT fm.id FROM futures_markets fm
    JOIN {BAK_MARKETS} b ON b.market_id = fm.id
    WHERE b.plan_hash = :plan_hash AND b.parent_id = :parent_id
    ORDER BY fm.id FOR UPDATE OF fm
"""

_RESTORE_LOCK_OUTCOMES = f"""
    SELECT fo.id FROM futures_outcomes fo
    JOIN {BAK_OUTCOMES} b ON b.outcome_id = fo.id
    WHERE b.plan_hash = :plan_hash AND b.parent_id = :parent_id
    ORDER BY fo.id FOR UPDATE OF fo
"""

_RESTORE_MARKETS = f"""
    UPDATE futures_markets fm
    SET status = b.prior_status,
        settled_at = b.prior_settled_at,
        resolution_date = b.prior_resolution_date
    FROM {BAK_MARKETS} b
    WHERE fm.id = b.market_id AND b.plan_hash = :plan_hash
      AND b.parent_id = :parent_id AND fm.xmin::text = b.wrote_row_version
"""

_RESTORE_OUTCOMES = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.prior_is_winner,
        resolution_source = b.prior_resolution_source
    FROM {BAK_OUTCOMES} b
    WHERE fo.id = b.outcome_id AND b.plan_hash = :plan_hash
      AND b.parent_id = :parent_id AND fo.xmin::text = b.wrote_row_version
"""


# ---------------------------------------------------------------------------
# pure decisions
# ---------------------------------------------------------------------------

def _iso(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def venue_date(raw) -> Optional[datetime]:
    """A Gamma ``endDate`` as an aware UTC datetime; ``None`` if absent or
    unreadable. Only an ISO string is accepted: a number has no stated unit."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(timezone.utc)


def _dt(iso: Optional[str]) -> Optional[datetime]:
    """An ISO string from a plan back to the datetime asyncpg binds."""
    return None if iso is None else datetime.fromisoformat(iso)


def _strict_bool(v) -> Optional[bool]:
    """The venue's flag only when it is a JSON boolean."""
    return v if isinstance(v, bool) else None


def leg_forms(cid: str) -> dict[str, str]:
    """The outcome ids the poll writes for one condition: the bare id on the
    parent's field, ``_yes`` / ``_no`` on the decomposed leg's own market."""
    c = cid.lower()
    return {c: "parent", f"{c}_yes": "yes", f"{c}_no": "no"}


def read_venue(raw: Any, stored_event_id: str, now: datetime) -> dict:
    """What the venue's own body says, or a refusal. Pure.

    ``{"refusal": reason}`` or ``{"event": {...}, "legs": {cid: {...}}}``.
    """
    if not isinstance(raw, dict):
        return {"refusal": "venue_unparseable"}
    if str(raw.get("id")) != str(stored_event_id):
        return {"refusal": "event_identity_mismatch",
                "detail": {"venue": raw.get("id"), "stored": stored_event_id}}
    closed = _strict_bool(raw.get("closed"))
    active = _strict_bool(raw.get("active"))
    archived = _strict_bool(raw.get("archived"))
    if closed is None or active is None or archived is None:
        return {"refusal": "event_flags_malformed",
                "detail": {k: raw.get(k) for k in ("closed", "active", "archived")}}
    if closed or not active or archived:
        # This rail only ever re-opens. A closed event belongs to the settle rails.
        return {"refusal": "event_not_open_at_venue",
                "detail": {"closed": closed, "active": active, "archived": archived}}
    end = venue_date(raw.get("endDate"))
    if end is None:
        return {"refusal": "venue_end_date_missing", "detail": raw.get("endDate")}
    if end <= now:
        return {"refusal": "venue_end_date_elapsed", "detail": _iso(end)}
    markets = raw.get("markets")
    if not isinstance(markets, list):
        return {"refusal": "venue_unparseable", "detail": "markets"}
    legs: dict[str, dict] = {}
    for m in markets:
        if not isinstance(m, dict):
            return {"refusal": "venue_unparseable", "detail": "market"}
        cid = m.get("conditionId")
        if not rwf._is_condition_id(cid):
            continue
        key = str(cid).lower()
        if key in legs:
            return {"refusal": "venue_duplicate_condition_ids", "detail": key}
        legs[key] = {
            "closed": _strict_bool(m.get("closed")),
            "closed_raw": m.get("closed"),
            "uma": m.get("umaResolutionStatus") or None,
            "end": venue_date(m.get("endDate")),
        }
    return {"event": {"id": str(raw.get("id")), "closed": closed, "active": active,
                      "archived": archived, "end": end},
            "legs": legs}


def stored_refusal(parent: Optional[dict], members: list[dict]) -> Optional[dict]:
    """The refusals the stored market rows alone can make, before any venue
    call. Pure. ``None`` when the venue should be asked."""
    if parent is None:
        return {"action": "skip", "reason": "market_missing"}
    if parent.get("source") != SOURCE:
        return {"action": "skip", "reason": "not_polymarket"}
    eid = str(parent.get("external_id") or "")
    if not eid.isdigit():
        return {"action": "skip", "reason": "not_an_event_parent"}
    if parent.get("group_id") != f"{SOURCE}:{eid}":
        return {"action": "skip", "reason": "group_mismatch",
                "detail": parent.get("group_id")}
    if len(members) >= MEMBER_CAP:
        return {"action": "skip", "reason": "too_many_members"}
    for m in members:
        if m.get("source") != SOURCE or not rwf._is_condition_id(m.get("external_id")):
            return {"action": "skip", "reason": "unexpected_group_member",
                    "detail": int(m["id"])}
    for m in [parent, *members]:
        if m.get("status") not in (OPEN_STATUS, RESOLVED_STATUS):
            return {"action": "skip", "reason": "status_unexpected",
                    "detail": {"market_id": int(m["id"]), "status": m.get("status")}}
    return None


def plan_parent(parent: Optional[dict], members: list[dict], outcomes: list[dict],
                raw_event: Any, now: datetime) -> dict:
    """One parent: the rows to write and the controls, or a refusal. Pure.

    ``members`` are the parent's group rows other than itself; ``outcomes`` are
    every outcome on the parent and on those members; ``raw_event`` is the body
    of ``GET /events/{id}`` (``None`` for a 404).
    """
    refused = stored_refusal(parent, members)
    if refused:
        return refused
    eid = str(parent["external_id"])
    if raw_event is None:
        return {"action": "skip", "reason": "venue_absent"}
    venue = read_venue(raw_event, eid, now)
    if "refusal" in venue:
        return {"action": "skip", "reason": venue["refusal"],
                "detail": venue.get("detail")}
    vlegs = venue["legs"]

    pid = int(parent["id"])
    child_by_cid: dict[str, dict] = {}
    for m in members:
        key = str(m["external_id"]).lower()
        if key in child_by_cid:
            return {"action": "skip", "reason": "duplicate_condition_ids", "detail": key}
        child_by_cid[key] = m
    by_market: dict[int, list[dict]] = {}
    for o in outcomes:
        by_market.setdefault(int(o["market_id"]), []).append(o)

    # Every stored leg, and the condition each outcome belongs to.
    stored: set[str] = set(child_by_cid)
    outcome_cid: dict[int, str] = {}
    leg_form_on_parent: list[tuple[int, str]] = []
    for o in by_market.get(pid, []):
        ext = str(o.get("external_id") or "").lower()
        base, sep, side = ext.rpartition("_")
        if (sep and side in ("yes", "no") and rwf._is_condition_id(base)
                and "_" not in base):
            # Production holds these: 113883 carries April's ``_yes`` / ``_no``
            # rows (written 2026-05-24, ungraded, filtered from the served
            # payload). Such a row belongs to its leg, and only to a leg this
            # parent already stores; it is then judged exactly like the
            # parent's own outcomes, so a venue-closed leg makes it a control.
            leg_form_on_parent.append((int(o["id"]), base))
            continue
        if not rwf._is_condition_id(ext) or "_" in ext:
            return {"action": "skip", "reason": "unexpected_parent_outcome",
                    "detail": int(o["id"])}
        stored.add(ext)
        outcome_cid[int(o["id"])] = ext
    for oid, base in leg_form_on_parent:
        if base not in stored:
            return {"action": "skip", "reason": "unexpected_parent_outcome",
                    "detail": oid}
        outcome_cid[oid] = base
    for cid, m in child_by_cid.items():
        forms = leg_forms(cid)
        for o in by_market.get(int(m["id"]), []):
            ext = str(o.get("external_id") or "").lower()
            if ext not in forms:
                return {"action": "skip", "reason": "unexpected_child_outcome",
                        "detail": int(o["id"])}
            outcome_cid[int(o["id"])] = cid

    venue_answer = {}
    for cid in sorted(stored):
        leg = vlegs.get(cid)
        if leg is None:
            return {"action": "skip", "reason": "stored_leg_absent_at_venue", "detail": cid}
        if leg["closed"] is None:
            return {"action": "skip", "reason": "leg_flag_malformed",
                    "detail": {"condition_id": cid, "closed": leg["closed_raw"]}}
        venue_answer[cid] = {"closed": leg["closed"], "uma": leg["uma"],
                             "end": _iso(leg["end"])}
    open_cids = {c for c, v in venue_answer.items() if v["closed"] is False}
    for cid in sorted(open_cids):
        if venue_answer[cid]["uma"]:
            return {"action": "skip", "reason": "leg_resolution_in_flight",
                    "detail": {"condition_id": cid, "uma": venue_answer[cid]["uma"]}}

    # Outcomes: clear an api_settlement grade on a venue-open leg; nothing else.
    outcome_writes, controls = [], []
    for o in outcomes:
        oid = int(o["id"])
        cid = outcome_cid[oid]
        image = outcome_image(o)
        if cid not in open_cids:
            controls.append(image)
            continue
        src = o.get("resolution_source")
        if src is None:
            # A sourceless grade has no writer we can name, so it is never
            # cleared; the question is only whether it refuses the parent. On
            # the parent's own outcomes — the rows the page reads — only
            # (None, None) is ungraded and any sourceless grade refuses. On a
            # leg's ``_yes``/``_no`` rows FALSE is the column's server default
            # (every row the poll inserts holds it; no reader prints a verdict
            # without a source), so only a sourceless TRUE refuses there.
            won = o.get("is_winner")
            if won is True or (won is not None and int(o["market_id"]) == pid):
                return {"action": "skip", "reason": "sourceless_grade_on_open_leg",
                        "detail": {"outcome_id": oid, "is_winner": won}}
            continue  # already ungraded
        if src != CLEARABLE_SOURCE:
            return {"action": "skip", "reason": "unexpected_grade_source",
                    "detail": {"outcome_id": oid, "resolution_source": src}}
        outcome_writes.append({**image, "row_version": o["row_version"]})

    # Markets: the parent, and each venue-open leg's own row.
    market_writes = []
    event_end = venue["event"]["end"]
    targets = [(parent, event_end)]
    for cid in sorted(open_cids):
        child = child_by_cid.get(cid)
        if child is None:
            continue
        end = vlegs[cid]["end"] or event_end
        if end <= now:
            return {"action": "skip", "reason": "venue_leg_end_date_elapsed",
                    "detail": {"condition_id": cid, "end": _iso(end)}}
        targets.append((child, end))
    for row, end in targets:
        reopening = row.get("status") == RESOLVED_STATUS
        wrote = {
            "status": OPEN_STATUS,
            "settled_at": None if reopening else _iso(row.get("settled_at")),
            "resolution_date": _iso(end),
        }
        image = market_image(row)
        if (not reopening and image["settled_at"] == wrote["settled_at"]
                and image["resolution_date"] == wrote["resolution_date"]):
            continue
        market_writes.append({**image, "row_version": row["row_version"], "wrote": wrote})

    if not market_writes and not outcome_writes:
        return {"action": "skip", "reason": "nothing_to_repair"}
    return {
        "action": "repair",
        "event_id": eid,
        "venue": {"event_end": _iso(event_end), "legs": venue_answer},
        "open_condition_ids": sorted(open_cids),
        "market_writes": market_writes,
        "outcome_writes": outcome_writes,
        "controls": sorted(controls, key=lambda c: c["outcome_id"]),
    }


def market_image(row: dict) -> dict:
    return {
        "market_id": int(row["id"]),
        "external_id": row.get("external_id"),
        "status": row.get("status"),
        "settled_at": _iso(row.get("settled_at")),
        "resolution_date": _iso(row.get("resolution_date")),
    }


def outcome_image(row: dict) -> dict:
    return {
        "outcome_id": int(row["id"]),
        "market_id": int(row["market_id"]),
        "external_id": row.get("external_id"),
        "name": row.get("name"),
        "is_winner": row.get("is_winner"),
        "resolution_source": row.get("resolution_source"),
    }


def plan_hash_for(named_ids: list[int], planned: list[dict]) -> str:
    """Content address of an exact-id plan: every row it writes (with its row
    version), every control grade, and the venue's flags and dates."""
    body = json.dumps(
        {
            "version": PLAN_VERSION,
            "task": TASK,
            "clearable_source": CLEARABLE_SOURCE,
            "named_ids": sorted(int(i) for i in named_ids),
            "parents": sorted(
                ({k: p[k] for k in ("market_id", "event_id", "venue", "market_writes",
                                    "outcome_writes", "controls")}
                 for p in planned),
                key=lambda p: p["market_id"],
            ),
        },
        separators=(",", ":"), sort_keys=True, default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def parse_only_ids(only_ids: Optional[str]) -> Optional[list[int]]:
    """``None`` = not named. An empty, non-integer or over-cap list raises."""
    if only_ids is None:
        return None
    parts = [p.strip() for p in str(only_ids).split(",")]
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"only_ids must be comma-separated market ids, got {only_ids!r}")
    ids = sorted({int(p) for p in parts})
    if len(ids) > APPLY_PARENT_CAP:
        raise ValueError(
            f"only_ids names {len(ids)} parents; at most {APPLY_PARENT_CAP} per call")
    return ids


def restore_command(plan_hash: str = "<plan_hash>") -> str:
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/pm-open-leg-false-grade-restore'
        f'?apply=true&plan_hash={plan_hash}"'
    )


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

def _now() -> datetime:
    """The clock the plan judges venue dates against (a seam for tests)."""
    return datetime.now(timezone.utc)


async def _set_bounds(session) -> None:
    await session.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


async def _read_parent(session, mid: int) -> tuple[Optional[dict], list[dict], list[dict]]:
    row = (await session.execute(text(_PARENT_SQL), {"mid": mid})).mappings().first()
    parent = dict(row) if row else None
    if parent is None or not parent.get("group_id"):
        return parent, [], []
    members = [dict(r) for r in (await session.execute(
        text(_MEMBERS_SQL),
        {"gid": parent["group_id"], "mid": mid, "cap": MEMBER_CAP})).mappings().all()]
    mids = [mid, *(int(m["id"]) for m in members)]
    outcomes = [dict(r) for r in (await session.execute(
        text(_OUTCOMES_SQL), {"mids": mids})).mappings().all()]
    return parent, members, outcomes


async def _plan_parent(session, service, mid: int, deadline: float, now: datetime) -> dict:
    """One parent: a planned entry, or a refusal with a reason. Reads only."""
    parent, members, outcomes = await _read_parent(session, mid)
    refused = stored_refusal(parent, members)
    if refused:
        return {"market_id": mid, **refused}
    if time.monotonic() > deadline:
        return {"market_id": mid, "action": "skip", "reason": "budget_exhausted"}
    try:
        raw = await service.get_event_by_id(str(parent["external_id"]))
    except Exception as e:  # noqa: BLE001 — an error is not an answer (gotcha #36)
        return {"market_id": mid, "action": "skip", "reason": "venue_error",
                "detail": str(e)[:80]}
    return {"market_id": mid, **plan_parent(parent, members, outcomes, raw, now)}


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------

DRIFT = "drift"
BACKUP_MISMATCH = "backup_mismatch"
ROWCOUNT = "rowcount_mismatch"


async def _apply_parent(session, p: dict, digest: str) -> Optional[str]:
    """One parent, one transaction. None when written; otherwise the refusal
    reason, with nothing written."""
    pid = p["market_id"]
    mws = {w["market_id"]: w for w in p["market_writes"]}
    ows = {w["outcome_id"]: w for w in p["outcome_writes"]}

    locked_m = [dict(r) for r in (await session.execute(
        text(_LOCK_MARKETS), {"ids": sorted(mws)})).mappings().all()]
    if ({int(r["id"]): (market_image(r), r["row_version"]) for r in locked_m}
            != {i: ({k: w[k] for k in w if k not in ("row_version", "wrote")},
                    w["row_version"]) for i, w in mws.items()}):
        await session.rollback()
        return DRIFT
    locked_o = [dict(r) for r in (await session.execute(
        text(_LOCK_OUTCOMES), {"ids": sorted(ows)})).mappings().all()]
    if ({int(r["id"]): (outcome_image(r), r["row_version"]) for r in locked_o}
            != {i: ({k: w[k] for k in w if k != "row_version"}, w["row_version"])
                for i, w in ows.items()}):
        await session.rollback()
        return DRIFT

    for mid, w in sorted(mws.items()):
        wrote = w["wrote"]
        bank = (await session.execute(text(_BAK_MARKET_COPY), {
            "id": mid, "plan_hash": digest, "parent_id": pid,
            "wrote_status": wrote["status"],
            "wrote_settled_at": _dt(wrote["settled_at"]),
            "wrote_resolution_date": _dt(wrote["resolution_date"]),
        })).mappings().first()
        if bank is None or (bank["prior_status"], _iso(bank["prior_settled_at"]),
                            _iso(bank["prior_resolution_date"]),
                            bank["prior_row_version"]) != (
                w["status"], w["settled_at"], w["resolution_date"], w["row_version"]):
            await session.rollback()
            return BACKUP_MISMATCH
        n = (await session.execute(text(_WRITE_MARKET), {
            "id": mid, "ver": w["row_version"],
            "wrote_status": wrote["status"],
            "wrote_settled_at": _dt(wrote["settled_at"]),
            "wrote_resolution_date": _dt(wrote["resolution_date"]),
            "prior_status": w["status"], "prior_settled_at": _dt(w["settled_at"]),
            "prior_resolution_date": _dt(w["resolution_date"]),
        })).rowcount
        if n != 1:
            await session.rollback()
            return ROWCOUNT
        if (await session.execute(text(_BAK_MARKET_VERSION),
                                  {"id": mid, "plan_hash": digest})).rowcount != 1:
            await session.rollback()
            return ROWCOUNT

    for oid, w in sorted(ows.items()):
        bank = (await session.execute(text(_BAK_OUTCOME_COPY), {
            "id": oid, "plan_hash": digest, "parent_id": pid})).mappings().first()
        if bank is None or (bank["prior_is_winner"], bank["prior_resolution_source"],
                            bank["prior_row_version"]) != (
                w["is_winner"], w["resolution_source"], w["row_version"]):
            await session.rollback()
            return BACKUP_MISMATCH
        n = (await session.execute(text(_WRITE_OUTCOME), {
            "id": oid, "ver": w["row_version"], "prior_is_winner": w["is_winner"],
            "clearable": CLEARABLE_SOURCE,
        })).rowcount
        if n != 1:
            await session.rollback()
            return ROWCOUNT
        if (await session.execute(text(_BAK_OUTCOME_VERSION),
                                  {"id": oid, "plan_hash": digest})).rowcount != 1:
            await session.rollback()
            return ROWCOUNT
    await session.commit()
    return None


def _empty(base: dict) -> dict:
    return {**base, "candidates": 0, "repaired_parents": 0, "markets_reopened": 0,
            "outcomes_cleared": 0, "skipped": 0, "skip_reasons": {},
            "drift_refused": 0, "backup_refused": 0, "rowcount_refused": 0,
            "ledger": [], "refused_parents": []}


async def repair(
    session,
    apply: bool = False,
    only_ids: str | None = None,
    plan_hash: str | None = None,
) -> dict:
    """Plan exactly the named parents; with ``apply`` and the plan's own hash,
    write them. Dry-run by default."""
    from app.services.polymarket_api import PolymarketAPIService

    started = time.monotonic()
    base: dict[str, Any] = {
        "repair": "pm-open-leg-false-grade", "issue": ISSUE, "apply": apply,
        "task": TASK, "clearable_source": CLEARABLE_SOURCE,
        "apply_parent_cap": APPLY_PARENT_CAP, "plan_version": PLAN_VERSION,
        "backup_tables": [BAK_MARKETS, BAK_OUTCOMES],
        "restore_command": restore_command(),
    }
    try:
        named = parse_only_ids(only_ids)
    except ValueError as e:
        return {**_empty(base), "terminal": "refused_bad_only_ids", "detail": str(e)}
    if named is None:
        return {**_empty(base), "terminal": "refused_no_exact_ids",
                "detail": "name the exact parent market ids with ?only_ids= (dry run and apply)"}
    if apply and not plan_hash:
        return {**_empty(base), "terminal": "refused_no_plan_hash",
                "detail": "run the dry run with the same only_ids and pass its plan_hash"}

    await _set_bounds(session)
    deadline = started + WALL_BUDGET_S
    now = _now()
    service = PolymarketAPIService()
    try:
        plans = [await _plan_parent(session, service, mid, deadline, now) for mid in named]
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001 — closing a client decides nothing
                pass
    planned = [p for p in plans if p["action"] == "repair"]
    skip_reasons: dict[str, int] = {}
    for p in plans:
        if p["action"] != "repair":
            skip_reasons[p["reason"]] = skip_reasons.get(p["reason"], 0) + 1
    incomplete = skip_reasons.get("budget_exhausted", 0) > 0
    digest = plan_hash_for(named, planned)
    summary = {
        **_empty(base), "only_ids": named, "candidates": len(named),
        "planned_parent_ids": [p["market_id"] for p in planned],
        "planned_market_writes": sum(len(p["market_writes"]) for p in planned),
        "planned_outcome_writes": sum(len(p["outcome_writes"]) for p in planned),
        "skipped": sum(skip_reasons.values()), "skip_reasons": skip_reasons,
        "plan_incomplete": incomplete, "plan_hash": digest, "ledger": plans,
    }
    if not apply:
        await session.rollback()
        return {**summary, "terminal": "dry_run"}
    if incomplete:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_incomplete",
                "detail": "the venue reads ran out of budget; name fewer parents"}
    if plan_hash != digest:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_drift",
                "detail": {"reviewed": plan_hash, "now": digest}}

    await session.commit()
    if planned:
        await session.execute(text(_BAK_MARKETS_CREATE))
        await session.execute(text(_BAK_OUTCOMES_CREATE))
        await session.commit()
    repaired, reopened, cleared = 0, 0, 0
    counts = {DRIFT: 0, BACKUP_MISMATCH: 0, ROWCOUNT: 0, "error": 0}
    refused: list[dict] = []
    for p in planned:
        await _set_bounds(session)
        try:
            reason = await _apply_parent(session, p, digest)
        except Exception as e:  # noqa: BLE001 — one parent never stops its siblings
            await session.rollback()
            logger.warning("%s parent %s refused: %s", ISSUE, p["market_id"], e)
            reason = "error"
        if reason is None:
            repaired += 1
            reopened += sum(1 for w in p["market_writes"]
                            if w["status"] != w["wrote"]["status"])
            cleared += len(p["outcome_writes"])
            continue
        counts[reason] += 1
        refused.append({"market_id": p["market_id"], "reason": reason})
    if repaired:
        logger.warning(
            "%s repaired %s parents (%s markets re-opened, %s grades cleared, %s refused)."
            " Backup in %s / %s. D51 undo:\n%s",
            ISSUE, repaired, reopened, cleared, len(refused), BAK_MARKETS, BAK_OUTCOMES,
            restore_command(digest),
        )
    return {**summary, "terminal": "applied", "restore_command": restore_command(digest),
            "repaired_parents": repaired,
            "markets_reopened": reopened, "outcomes_cleared": cleared,
            "drift_refused": counts[DRIFT], "backup_refused": counts[BACKUP_MISMATCH],
            "rowcount_refused": counts[ROWCOUNT], "error_refused": counts["error"],
            "refused_parents": refused}


# ---------------------------------------------------------------------------
# audit and restore
# ---------------------------------------------------------------------------

def group_state(rows: list[dict]) -> str:
    """A parent's state from its banked rows: all still exactly as written,
    all back at the before-image, or anything else."""
    if rows and all(r["still_written"] for r in rows):
        return "written"
    if rows and all(r["at_prior"] for r in rows):
        return "restored"
    return "moved"


async def _audit(session, plan_hash: Optional[str], parent_id: Optional[int]) -> dict:
    params = {"plan_hash": plan_hash, "parent_id": parent_id}
    rows = [dict(r) for r in (await session.execute(
        text(_AUDIT_MARKETS), params)).mappings().all()]
    rows += [dict(r) for r in (await session.execute(
        text(_AUDIT_OUTCOMES), params)).mappings().all()]
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["plan_hash"], int(r["parent_id"])), []).append(r)
    return groups


async def restore(session, apply: bool = False, plan_hash: str | None = None) -> dict:
    """Audit (dry run) or put back every parent one run wrote whose every
    written row is still exactly the version its write left. The audit may span
    every run; the apply names one run by its ``plan_hash``, exactly as the
    repair apply does, so it can never restore a run nobody reviewed."""
    base = {"issue": ISSUE, "backup_tables": [BAK_MARKETS, BAK_OUTCOMES],
            "apply": apply, "plan_hash": plan_hash}
    if apply and not plan_hash:
        return {**base, "terminal": "refused_no_plan_hash", "restored_parents": 0,
                "detail": "run the restore dry run and pass the one plan_hash to put back"}
    exists = [(await session.execute(text(_EXISTS), {"t": t})).scalar_one()
              for t in (BAK_MARKETS, BAK_OUTCOMES)]
    if not all(exists):
        await session.rollback()
        return {**base, "terminal": "refused_no_backup", "restored_parents": 0}
    await _set_bounds(session)
    groups = await _audit(session, plan_hash, None)
    states = {key: group_state(rows) for key, rows in groups.items()}
    by_plan: dict[str, dict[str, int]] = {}
    for (ph, _), st in states.items():
        tally = by_plan.setdefault(ph, {"written": 0, "restored": 0, "moved": 0})
        tally[st] += 1
    audit = {
        **base, "parents_backed_up": len(states), "by_plan_hash": by_plan,
        "parents": [
            {"plan_hash": ph, "market_id": pid, "state": st,
             "moved_rows": [f'{r["kind"]}:{int(r["row_id"])}' for r in groups[(ph, pid)]
                           if not r["still_written"]][:20]}
            for (ph, pid), st in sorted(states.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        ][:200],
    }
    if not apply:
        await session.rollback()
        return {**audit, "terminal": "dry_run", "restored_parents": 0}

    await session.rollback()
    restored, refused = 0, []
    for (ph, pid), st in sorted(states.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if st != "written":
            continue
        await _set_bounds(session)
        try:
            await session.execute(text(_RESTORE_LOCK_MARKETS),
                                  {"plan_hash": ph, "parent_id": pid})
            await session.execute(text(_RESTORE_LOCK_OUTCOMES),
                                  {"plan_hash": ph, "parent_id": pid})
            again = (await _audit(session, ph, pid)).get((ph, pid), [])
            if group_state(again) != "written":
                await session.rollback()
                refused.append({"market_id": pid, "plan_hash": ph, "reason": DRIFT})
                continue
            n = (await session.execute(text(_RESTORE_MARKETS),
                                       {"plan_hash": ph, "parent_id": pid})).rowcount
            k = (await session.execute(text(_RESTORE_OUTCOMES),
                                       {"plan_hash": ph, "parent_id": pid})).rowcount
            if (n, k) != (sum(1 for r in again if r["kind"] == "market"),
                          sum(1 for r in again if r["kind"] == "outcome")):
                await session.rollback()
                refused.append({"market_id": pid, "plan_hash": ph, "reason": ROWCOUNT})
                continue
            await session.commit()
            restored += 1
        except Exception as e:  # noqa: BLE001 — one parent never stops its siblings
            await session.rollback()
            logger.warning("%s restore of parent %s refused: %s", ISSUE, pid, e)
            refused.append({"market_id": pid, "plan_hash": ph, "reason": "error"})
    logger.warning("%s restore: %s parents put back, %s refused", ISSUE,
                   restored, len(refused))
    return {**audit, "terminal": "restored", "restored_parents": restored,
            "refused_parents": refused}
