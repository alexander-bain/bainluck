"""#1527: attended, capped transition of settled three-way soccer markets off ``open``.

## what a reader sees

Market 55254886 (*Slavia Praha vs. Anderlecht*, a December 2024 Europa League
fixture) is stored ``status='open'``. The outcome rail
(:mod:`app.tasks.repair_winner_field`) gives it one real winner, but an ``open``
board is still a live board: it sits on the ``status='open'`` lists
(``/api/futures/browse``, ``/categories``, ``/grouped-feed``) and the detail
page runs its live-only rules over it. After this transition it is
``resolved``: it leaves the live lists, and ``/api/futures/{id}`` serves it as a
result, with the one winner still shown.

## what is written, and on what proof

One row per market, ``futures_markets`` only. No outcome is touched::

    status        'open' -> 'resolved'
    settled_at    COALESCE(settled_at, NOW())           (first observation kept)
    market_metadata || {"resolution_gate": {"proof_kind": "winner", ...}}

That is the same write, stamp and gate the Polymarket resolve sync makes
(``sync_polymarket_resolved_status``), and ``resolved`` is the repository's one
settled status (``app.utils.resolved_write_gate``: a market may become
``resolved`` only with a winner or a named reason). This rail writes ONLY with a
winner. The proof is two independent facts that must agree:

* the stored field is already graded to one winner, by a named authority:
  exactly one leg ``is_winner=true`` priced at or above ``NEAR_CERTAIN_PROB`` and
  two ``is_winner=false`` priced at or below its complement, every leg carrying
  a ``resolution_source`` the authority ladder knows. A loss with no source is
  refused (``unknown_authority``): the column defaults to ``false``, so a sourceless
  ``false`` may be a leg nobody graded. The price bands, not exact 1.0 / 0.0,
  because the poll re-prices a settled loser to the venue's last trade (0.003 in
  the re-ingest gate); the grade, not the price, is what says who won. An
  incoherent field is refused here (``field_incoherent``) and belongs to the
  outcome rail first; this rail never grades anything.
* the venue closed the question and named the same winner: every leg's own
  condition id read from the CLOB is ``closed`` with a decided Yes token,
  exactly one leg won, and it is the stored winner.

Refused BY NAME, with nothing written: venue still open, void (nobody won),
contradictory (two winners), venue and stored winner disagreeing, an unknown
grading authority, anything not a Polymarket soccer three-way with one Draw leg,
a market not ``open``, and any CLOB error (gotcha #36: a 429 is not an answer).

## the apply is bound to a reviewed exact-id plan

Exact ids only, for the dry run AND the apply: the population is the
measurement lane's to name, so there is no discovery walk to widen it. The plan
hash covers the named ids, every market's stored fields and row version
(``xmin``), each leg's identity, grade and row version, and each leg's venue
answer. A same-value write between the reviewed dry run and the apply still
moves a row version, so the apply refuses whole (``refused_plan_drift``) and the
operator dry-runs again. Each market is then one transaction under its own
statement and lock timeouts: the market row is locked ``FOR UPDATE`` and its
legs ``FOR SHARE``, both re-checked against the plan, and the UPDATE itself
repeats ``status='open'`` and the row version in its ``WHERE`` with its row
count checked.

## D51: backup, audit and restore

The market's before-image (``status``, ``settled_at``, ``market_metadata``) goes
into :data:`BAK_TABLE` in the same transaction as the write, so a run stopped
part-way leaves every committed market banked and every other market untouched.
The bank also records the row version the write left. The restore's dry run is
the audit (per plan hash: still ``settled``, already ``restored``, or ``moved``),
and it puts a market back only while the row is still exactly the version this
rail's write left: a later writer, even one that changed nothing, makes it
``moved``, and a moved market is never restored::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/settled-status-repair-restore?apply=true"

ATTENDED ONLY: never wire this to a beat. Runtime DDL (the backup table) runs
only inside an attended apply.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text

from app.tasks import repair_winner_field as rwf
from app.utils.resolved_write_gate import GATE_KEY, PROOF_WINNER, gate_stamp
from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB

logger = logging.getLogger(__name__)

ISSUE = "#1527"

#: Names this writer in the ``resolution_gate`` stamp.
TASK = "repair_settled_status_1527"

OPEN_STATUS = "open"
SETTLED_STATUS = "resolved"

APPLY_MARKET_CAP = rwf.APPLY_MARKET_CAP

#: The most a graded loser may still be priced at: the complement of the
#: near-certain bar the winner must reach.
SETTLED_LOSER_MAX = round(1 - NEAR_CERTAIN_PROB, 6)

BAK_TABLE = "bak_1527_settled_status_markets"

#: Bumped whenever the plan's shape or the write changes.
PLAN_VERSION = "1527-status-v1"

WALL_BUDGET_S = rwf.WALL_BUDGET_S
STATEMENT_TIMEOUT = rwf.STATEMENT_TIMEOUT
LOCK_TIMEOUT = rwf.LOCK_TIMEOUT

_MARKET_COLS = """id, source, llm_sport_category, market_type, mutually_exclusive,
    status, settled_at, market_metadata, xmin::text AS row_version"""

_MARKET_SQL = f"SELECT {_MARKET_COLS} FROM futures_markets WHERE id = :mid"

_MARKET_LOCK_SQL = _MARKET_SQL + " FOR UPDATE"

_LEGS_SQL = """
    SELECT o.id, o.market_id, o.name, o.external_id, o.is_winner,
           o.current_probability, o.resolution_source, o.xmin::text AS row_version
    FROM futures_outcomes o
    WHERE o.market_id = :mid
    ORDER BY o.id
"""

_LEGS_LOCK_SQL = _LEGS_SQL + "    FOR SHARE\n"

_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
        market_id BIGINT PRIMARY KEY,
        prior_status VARCHAR(20) NOT NULL,
        prior_settled_at TIMESTAMPTZ,
        prior_market_metadata JSONB,
        prior_row_version TEXT NOT NULL,
        wrote_status VARCHAR(20) NOT NULL,
        plan_hash TEXT NOT NULL,
        wrote_row_version TEXT,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""

_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (
        market_id, prior_status, prior_settled_at, prior_market_metadata,
        prior_row_version, wrote_status, plan_hash)
    SELECT id, status, settled_at, market_metadata, xmin::text, :wrote, :plan_hash
    FROM futures_markets
    WHERE id = :mid
    ON CONFLICT (market_id) DO NOTHING
"""

_PRIOR_PAIR = """
    (b.prior_status, b.prior_settled_at, b.prior_market_metadata)
    IS NOT DISTINCT FROM
    (fm.status, fm.settled_at, fm.market_metadata)
"""

#: Does the bank hold exactly this market's locked prior? The copy keeps an older
#: bank row on conflict (a market restored and planned again), so a row count
#: would pass on a stale before-image.
_BAK_PAIRED = f"""
    SELECT EXISTS (
        SELECT 1 FROM {BAK_TABLE} b
        JOIN futures_markets fm ON fm.id = b.market_id
        WHERE b.market_id = :mid AND b.wrote_status = :wrote AND {_PRIOR_PAIR}
    )
"""

#: The bank row now describes THIS run; an older run's version token is cleared
#: and re-stamped after the write.
_BAK_STAMP = f"""
    UPDATE {BAK_TABLE}
    SET plan_hash = :plan_hash, prior_row_version = :ver, wrote_row_version = NULL
    WHERE market_id = :mid
"""

#: A JSON ``null`` is not SQL NULL: the column is JSONB without ``none_as_null``, so
#: an ORM or Core insert of ``None`` stores ``'null'``, and ``COALESCE(m, '{}') ||
#: stamp`` over it builds the ARRAY ``[null, {...}]``. Both nulls read as empty;
#: any other non-object is refused upstream (``metadata_not_an_object``).
_WRITE_STATUS = """
    UPDATE futures_markets
    SET status = :settled,
        settled_at = COALESCE(settled_at, NOW()),
        market_metadata = CASE WHEN market_metadata IS NULL
                                    OR jsonb_typeof(market_metadata) = 'null'
                               THEN '{}'::jsonb ELSE market_metadata END
                          || CAST(:stamp AS jsonb)
    WHERE id = :mid AND status = :open AND xmin::text = :ver
      AND (market_metadata IS NULL
           OR jsonb_typeof(market_metadata) IN ('object', 'null'))
"""

#: In the write's own transaction: the row version this rail's write left.
_BAK_VERSION = f"""
    UPDATE {BAK_TABLE} b SET wrote_row_version = fm.xmin::text
    FROM futures_markets fm
    WHERE fm.id = b.market_id AND b.market_id = :mid
"""

_EXISTS = "SELECT to_regclass(:t) IS NOT NULL"

_WROTE_VERSION = "fm.xmin::text = b.wrote_row_version"

_AUDIT_SQL = f"""
    SELECT b.plan_hash, b.market_id,
           (fm.id IS NOT NULL AND {_WROTE_VERSION}
            AND fm.status = b.wrote_status) AS still_settled,
           (fm.id IS NOT NULL AND {_PRIOR_PAIR}) AS at_prior
    FROM {BAK_TABLE} b
    LEFT JOIN futures_markets fm ON fm.id = b.market_id
    WHERE (CAST(:plan_hash AS TEXT) IS NULL OR b.plan_hash = CAST(:plan_hash AS TEXT))
      AND (CAST(:mid AS BIGINT) IS NULL OR b.market_id = CAST(:mid AS BIGINT))
    ORDER BY b.market_id
"""

_LOCK_MARKET = "SELECT id FROM futures_markets WHERE id = :mid FOR UPDATE"

_RESTORE_MARKET = f"""
    UPDATE futures_markets fm
    SET status = b.prior_status,
        settled_at = b.prior_settled_at,
        market_metadata = b.prior_market_metadata
    FROM {BAK_TABLE} b
    WHERE fm.id = b.market_id AND b.market_id = :mid
      AND {_WROTE_VERSION} AND fm.status = b.wrote_status
"""


# ---------------------------------------------------------------------------
# pure decisions
# ---------------------------------------------------------------------------

def status_cohort_refusal(market: dict | None, legs: list[dict]) -> Optional[str]:
    """None when this market is an ``open``, already-graded #1527 three-way
    soccer field; otherwise the reason it is not."""
    if market is None:
        return "market_missing"
    if market.get("source") != rwf.COHORT_SOURCE:
        return "not_polymarket"
    if market.get("llm_sport_category") != rwf.COHORT_SPORT:
        return "not_soccer"
    if market.get("market_type") not in rwf.COHORT_MARKET_TYPES:
        return "not_field_or_duel"
    if market.get("mutually_exclusive") is not True:
        return "not_mutually_exclusive"
    if len(legs) != rwf.COHORT_LEGS:
        return "not_three_way"
    if sum(1 for leg in legs if rwf._is_draw(leg.get("name"))) != 1:
        return "not_one_draw_leg"
    meta = market.get("market_metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    if meta is not None and not isinstance(meta, dict):
        # The stamp merges into an object; an array or a scalar here would be
        # rebuilt, not merged.
        return "metadata_not_an_object"
    if market.get("status") == SETTLED_STATUS:
        return "already_settled"
    if market.get("status") != OPEN_STATUS:
        return "not_open"
    winners = [leg for leg in legs if leg.get("is_winner") is True]
    near = sum(1 for leg in legs if rwf._near_certain(leg.get("current_probability")))
    if len(winners) > 1 or near > 1:
        # The outcome rail's cohort. Settling it first would publish a result
        # with three winners.
        return "field_incoherent"
    losers = [leg for leg in legs if leg.get("is_winner") is False]
    if len(winners) != 1 or len(losers) != 2:
        return "field_ungraded"
    win_p = winners[0].get("current_probability")
    if win_p is None or float(win_p) < NEAR_CERTAIN_PROB or any(
        leg.get("current_probability") is None
        or float(leg["current_probability"]) > SETTLED_LOSER_MAX
        for leg in losers
    ):
        return "field_prices_unsettled"
    return None


def leg_authority_refusal(legs: list[dict]) -> Optional[tuple[str, list]]:
    """No-network refusals: grading authority and venue identity."""
    if any(leg.get("resolution_source") is None for leg in legs):
        return "unknown_authority", [None]
    unknown = rwf.unknown_authority(legs)
    if unknown:
        return "unknown_authority", unknown
    if not all(rwf._is_condition_id(leg.get("external_id")) for leg in legs):
        return "not_clob_addressable", []
    cids = [str(leg["external_id"]).lower() for leg in legs]
    if len(set(cids)) != len(cids):
        return "duplicate_condition_ids", []
    return None


def venue_leg(condition_id: str, clob_market: dict | None) -> dict:
    """What the CLOB says about this one condition id. A body naming another id,
    or none, is not testimony: both fields read as unknown."""
    if not rwf.names_condition(condition_id, clob_market):
        return {"condition_id": condition_id, "closed": None, "yes_winner": None}
    closed = clob_market.get("closed")
    return {
        "condition_id": condition_id,
        "closed": closed if isinstance(closed, bool) else None,
        "yes_winner": rwf.venue_answer(condition_id, clob_market),
    }


def decide_status(legs: list[dict], venue: list[dict]) -> dict:
    """Settle, or skip with a reason. ``legs`` and ``venue`` are in the same order."""
    if any(v["closed"] is not True for v in venue):
        return {"action": "skip", "reason": "venue_not_closed",
                "detail": [leg.get("name") for leg, v in zip(legs, venue)
                           if v["closed"] is not True][:4]}
    decision = rwf.decide_market([
        {"outcome_id": int(leg["id"]), "name": leg.get("name"),
         "yes_winner": v["yes_winner"]}
        for leg, v in zip(legs, venue)
    ])
    if decision["action"] == "skip":
        return decision
    stored = next(int(leg["id"]) for leg in legs if leg.get("is_winner") is True)
    if int(decision["winner_outcome_id"]) != stored:
        return {"action": "skip", "reason": "venue_disagrees_with_stored_winner",
                "detail": {"venue": decision["winner_name"], "stored_outcome_id": stored}}
    return {"action": "settle", "winner_outcome_id": stored,
            "winner_name": decision["winner_name"]}


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _metadata_digest(meta) -> str:
    """Canonical digest of ``market_metadata``: the address holds this, not the
    blob, and any byte of a change still moves it."""
    if isinstance(meta, str):
        meta = json.loads(meta)
    body = json.dumps(meta, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def market_image(market: dict) -> dict:
    return {
        "market_id": int(market["id"]),
        "source": market.get("source"),
        "llm_sport_category": market.get("llm_sport_category"),
        "market_type": market.get("market_type"),
        "mutually_exclusive": market.get("mutually_exclusive"),
        "status": market.get("status"),
        "settled_at": _iso(market.get("settled_at")),
        "market_metadata": _metadata_digest(market.get("market_metadata")),
    }


def leg_image(row: dict) -> dict:
    return {
        "outcome_id": int(row["id"]),
        "name": row.get("name"),
        "external_id": row.get("external_id"),
        "is_winner": row.get("is_winner"),
        "current_probability": rwf._f(row.get("current_probability")),
        "resolution_source": row.get("resolution_source"),
    }


def plan_hash_for(named_ids: list[int], planned: list[dict]) -> str:
    """Content address of an exact-id status plan."""
    body = json.dumps(
        {
            "version": PLAN_VERSION,
            "task": TASK,
            "settled_status": SETTLED_STATUS,
            "named_ids": sorted(int(i) for i in named_ids),
            "markets": sorted(
                ({k: p[k] for k in ("market", "legs", "venue", "winner_outcome_id",
                                    "market_row_version", "leg_row_versions")}
                 for p in planned),
                key=lambda p: p["market"]["market_id"],
            ),
        },
        separators=(",", ":"), sort_keys=True, default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def write_stamp(digest: str) -> str:
    """The ``resolution_gate`` fragment: winner proof, this writer, this plan."""
    stamp = gate_stamp(task=TASK, proof_kind=PROOF_WINNER)
    stamp[GATE_KEY]["plan_hash"] = digest
    return json.dumps(stamp)


def restore_command() -> str:
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/settled-status-repair-restore?apply=true"'
    )


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

async def _set_bounds(session) -> None:
    await session.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


async def _plan_market(session, service, mid: int, deadline: float) -> dict:
    """One market: a planned entry, or a refusal with a reason. Reads only."""
    row = (await session.execute(text(_MARKET_SQL), {"mid": mid})).mappings().first()
    market = dict(row) if row else None
    legs = [dict(r) for r in
            (await session.execute(text(_LEGS_SQL), {"mid": mid})).mappings().all()]

    reason = status_cohort_refusal(market, legs)
    if reason:
        return {"market_id": mid, "action": "skip", "reason": reason}
    refused = leg_authority_refusal(legs)
    if refused:
        return {"market_id": mid, "action": "skip", "reason": refused[0],
                "detail": refused[1]}

    venue = []
    for leg in legs:
        if time.monotonic() > deadline:
            return {"market_id": mid, "action": "skip", "reason": "budget_exhausted"}
        cid = str(leg["external_id"])
        try:
            clob = await service.get_clob_market_by_condition(cid)
        except Exception as e:  # noqa: BLE001 — an error is not an answer (gotcha #36)
            return {"market_id": mid, "action": "skip", "reason": "clob_error",
                    "detail": str(e)[:80]}
        venue.append({"outcome_id": int(leg["id"]), **venue_leg(cid, clob)})

    decision = decide_status(legs, venue)
    if decision["action"] == "skip":
        return {"market_id": mid, "action": "skip", "reason": decision["reason"],
                "detail": decision.get("detail")}
    return {
        "market_id": mid,
        "action": "settle",
        "winner": decision["winner_name"],
        "winner_outcome_id": decision["winner_outcome_id"],
        "market": market_image(market),
        "legs": [leg_image(leg) for leg in legs],
        "venue": venue,
        "market_row_version": market["row_version"],
        "leg_row_versions": {str(int(leg["id"])): leg["row_version"] for leg in legs},
    }


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------

DRIFT = "drift"
BACKUP_MISMATCH = "backup_mismatch"
ROWCOUNT = "rowcount_mismatch"


async def _apply_market(session, p: dict, digest: str) -> Optional[str]:
    """One market, one transaction. None when written; otherwise the refusal
    reason, with nothing written."""
    mid = p["market_id"]
    row = (await session.execute(text(_MARKET_LOCK_SQL), {"mid": mid})).mappings().first()
    if (row is None or market_image(dict(row)) != p["market"]
            or row["row_version"] != p["market_row_version"]):
        await session.rollback()
        return DRIFT
    locked = [dict(r) for r in
              (await session.execute(text(_LEGS_LOCK_SQL), {"mid": mid})).mappings().all()]
    if ([leg_image(r) for r in locked] != p["legs"]
            or {str(int(r["id"])): r["row_version"] for r in locked}
            != p["leg_row_versions"]):
        await session.rollback()
        return DRIFT

    ver = p["market_row_version"]
    await session.execute(text(_BAK_COPY),
                          {"mid": mid, "wrote": SETTLED_STATUS, "plan_hash": digest})
    paired = (await session.execute(
        text(_BAK_PAIRED), {"mid": mid, "wrote": SETTLED_STATUS})).scalar_one()
    if not paired:
        await session.rollback()
        return BACKUP_MISMATCH
    await session.execute(text(_BAK_STAMP), {"mid": mid, "plan_hash": digest, "ver": ver})

    written = (await session.execute(text(_WRITE_STATUS), {
        "mid": mid, "settled": SETTLED_STATUS, "open": OPEN_STATUS, "ver": ver,
        "stamp": write_stamp(digest),
    })).rowcount
    if written != 1:
        await session.rollback()
        return ROWCOUNT
    stamped = (await session.execute(text(_BAK_VERSION), {"mid": mid})).rowcount
    if stamped != 1:
        await session.rollback()
        return ROWCOUNT
    await session.commit()
    return None


def _empty(base: dict) -> dict:
    return {**base, "candidates": 0, "settled": 0, "skipped": 0, "drift_refused": 0,
            "backup_refused": 0, "rowcount_refused": 0, "skip_reasons": {},
            "ledger": [], "refused_markets": []}


async def repair(
    session,
    apply: bool = False,
    only_ids: str | None = None,
    plan_hash: str | None = None,
) -> dict:
    """Plan exactly the named markets; with ``apply`` and the plan's own hash,
    settle them. Dry-run by default."""
    from app.services.polymarket_api import PolymarketAPIService

    started = time.monotonic()
    base: dict[str, Any] = {
        "repair": "settled-status-repair", "issue": ISSUE, "apply": apply,
        "task": TASK, "settled_status": SETTLED_STATUS,
        "apply_market_cap": APPLY_MARKET_CAP, "plan_version": PLAN_VERSION,
        "backup_table": BAK_TABLE, "restore_command": restore_command(),
    }
    try:
        named = rwf.parse_only_ids(only_ids)
    except ValueError as e:
        return {**_empty(base), "terminal": "refused_bad_only_ids", "detail": str(e)}
    if named is None:
        return {**_empty(base), "terminal": "refused_no_exact_ids",
                "detail": "name the exact market ids with ?only_ids= (dry run and apply)"}
    if apply and not plan_hash:
        return {**_empty(base), "terminal": "refused_no_plan_hash",
                "detail": "run the dry run with the same only_ids and pass its plan_hash"}

    await _set_bounds(session)
    deadline = started + WALL_BUDGET_S
    service = PolymarketAPIService()
    plans = [await _plan_market(session, service, mid, deadline) for mid in named]
    planned = [p for p in plans if p["action"] == "settle"]
    skip_reasons: dict[str, int] = {}
    for p in plans:
        if p["action"] != "settle":
            skip_reasons[p["reason"]] = skip_reasons.get(p["reason"], 0) + 1
    incomplete = skip_reasons.get("budget_exhausted", 0) > 0
    digest = plan_hash_for(named, planned)
    summary = {
        **_empty(base), "only_ids": named, "candidates": len(named),
        "planned_market_ids": [p["market_id"] for p in planned],
        "skipped": sum(skip_reasons.values()), "skip_reasons": skip_reasons,
        "plan_incomplete": incomplete, "plan_hash": digest,
        "ledger": [{k: p[k] for k in p if k not in ("market_row_version",)}
                   for p in plans],
    }
    if not apply:
        await session.rollback()
        return {**summary, "terminal": "dry_run"}
    if incomplete:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_incomplete",
                "detail": "the CLOB reads ran out of budget; name fewer markets"}
    if plan_hash != digest:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_drift",
                "detail": {"reviewed": plan_hash, "now": digest}}

    await session.commit()
    if planned:
        await session.execute(text(_BAK_CREATE))
        await session.commit()
    settled = 0
    counts = {DRIFT: 0, BACKUP_MISMATCH: 0, ROWCOUNT: 0, "error": 0}
    refused: list[dict] = []
    for p in planned:
        await _set_bounds(session)
        try:
            reason = await _apply_market(session, p, digest)
        except Exception as e:  # noqa: BLE001 — one market never stops its siblings
            await session.rollback()
            logger.warning("%s status market %s refused: %s", ISSUE, p["market_id"], e)
            reason = "error"
        if reason is None:
            settled += 1
            continue
        counts[reason] += 1
        refused.append({"market_id": p["market_id"], "reason": reason})
    if settled:
        logger.warning(
            "%s settled %s markets (%s refused). Backup in %s. D51 undo:\n%s",
            ISSUE, settled, len(refused), BAK_TABLE, restore_command(),
        )
    return {**summary, "terminal": "applied", "settled": settled,
            "drift_refused": counts[DRIFT], "backup_refused": counts[BACKUP_MISMATCH],
            "rowcount_refused": counts[ROWCOUNT], "error_refused": counts["error"],
            "refused_markets": refused}


# ---------------------------------------------------------------------------
# audit and restore
# ---------------------------------------------------------------------------

def _state(row) -> str:
    if row["still_settled"]:
        return "settled"
    return "restored" if row["at_prior"] else "moved"


async def restore(session, apply: bool = False, plan_hash: str | None = None) -> dict:
    """Audit (dry run) or put back every market this rail settled whose row is
    still exactly the version its write left. ``plan_hash`` scopes it to one run."""
    base = {"issue": ISSUE, "backup_table": BAK_TABLE, "apply": apply,
            "plan_hash": plan_hash}
    if not (await session.execute(text(_EXISTS), {"t": BAK_TABLE})).scalar_one():
        await session.rollback()
        return {**base, "terminal": "refused_no_backup", "restored_markets": 0}
    await _set_bounds(session)
    rows = (await session.execute(
        text(_AUDIT_SQL), {"plan_hash": plan_hash, "mid": None})).mappings().all()
    states = {int(r["market_id"]): {"plan_hash": r["plan_hash"], "state": _state(r)}
              for r in rows}
    by_plan: dict[str, dict[str, int]] = {}
    for m in states.values():
        tally = by_plan.setdefault(m["plan_hash"], {"settled": 0, "restored": 0, "moved": 0})
        tally[m["state"]] += 1
    audit = {
        **base, "markets_backed_up": len(states), "by_plan_hash": by_plan,
        "markets": [{"market_id": mid, **m} for mid, m in sorted(states.items())][:200],
    }
    if not apply:
        await session.rollback()
        return {**audit, "terminal": "dry_run", "restored_markets": 0}

    await session.rollback()
    restored, refused = 0, []
    for mid, m in sorted(states.items()):
        if m["state"] != "settled":
            continue
        await _set_bounds(session)
        try:
            await session.execute(text(_LOCK_MARKET), {"mid": mid})
            again = (await session.execute(
                text(_AUDIT_SQL), {"plan_hash": plan_hash, "mid": mid})).mappings().first()
            if again is None or _state(again) != "settled":
                await session.rollback()
                refused.append({"market_id": mid, "reason": DRIFT})
                continue
            n = (await session.execute(text(_RESTORE_MARKET), {"mid": mid})).rowcount
            if n != 1:
                await session.rollback()
                refused.append({"market_id": mid, "reason": ROWCOUNT})
                continue
            await session.commit()
            restored += 1
        except Exception as e:  # noqa: BLE001 — one market never stops its siblings
            await session.rollback()
            logger.warning("%s status restore of market %s refused: %s", ISSUE, mid, e)
            refused.append({"market_id": mid, "reason": "error"})
    logger.warning("%s status restore: %s markets put back, %s refused", ISSUE,
                   restored, len(refused))
    return {**audit, "terminal": "restored", "restored_markets": restored,
            "refused_markets": refused}
