"""CAL-P007 (#1527): attended, capped repair of the three-winner soccer cohort.

## what a reader sees

A settled Europa League fixture (market 55254886, *Slavia Praha vs. Anderlecht*)
shows Slavia Praha, Anderlecht AND Draw each as the 100% winner. After this
repair it shows the one side that won, at 100%, and the other two as losses.

## why this is allowed to write at all

Gotcha #21: never bulk-reset ``is_winner`` without a source that can immediately
re-resolve. This is not a reset. Each leg of one of these markets is its OWN
Polymarket ``condition_id``, so the CLOB answers the question directly, per leg,
with no name-matching heuristic in the way::

    Will Slavia Praha beat Anderlecht?         closed=True   Yes=False
    Will Anderlecht beat Slavia Praha?         closed=True   Yes=True
    Will the match ... end in a draw?          closed=True   Yes=False

Exactly one winner, established independently of our (impossible) stored price.
The id IS the identity, so there is no mapping step that can be wrong.

## the cohort, and only the cohort

A market is in scope only when ALL of these hold (:func:`cohort_refusal`):
``source='polymarket'``, ``llm_sport_category='soccer'``, ``market_type`` field
or duel, ``mutually_exclusive``, exactly three legs, exactly one of them a Draw
leg, and the field incoherent (more than one winner, or more than one leg at or
above :data:`NEAR_CERTAIN_PROB`). Golf fields, football, two-leg duels, Kalshi
rows and anything else are refused BY NAME, even when an operator names them in
``only_ids``. Every leg must be a distinct 0x condition id, and no leg may carry
a tier-3 source other than this rail's own or a source the authority ladder does
not know (:func:`authority_refusal`).

## what gets written

* ``is_winner`` + ``current_probability`` from settlement (1.0 winner / 0.0
  losers, the same shape the poller's ``api_settlement`` path writes), source
  :data:`WRITE_SOURCE`.
* ``opening_*`` NULLED on a leg whose ``opening_probability`` is at or above
  :data:`IMPOSSIBLE_PRICE`, and ``calibration_probability`` NULLED on a leg
  whose own value is. The two are decided separately, so a genuine sub-certain
  opening survives beside an impossible calibration price, and a NULL stays
  NULL. CAL-P006 established these markets were first ingested ~2 years AFTER
  the fixture with every snapshot at 1.0: there was never a real price, so
  NULL is the honest state and any "repaired" price would be invented.

Fail closed: a market is written whole or not at all. Zero CLOB winners (a
void), more than one (contradictory upstream), any 404/429/error, a CLOB answer
for a different condition id, or a foreign/unknown authority: all refuse with a
recorded reason.

## the apply is bound to a reviewed exact-id plan

* ``apply=true`` requires ``only_ids`` (the exact market ids, at most
  :data:`APPLY_MARKET_CAP`) AND ``plan_hash``. The windowed walk is discovery
  only and can never write.
* The apply re-plans those ids (fresh stored values, fresh CLOB answers) and
  refuses everything unless the content address (:func:`plan_hash_for`, over the
  named ids, every planned leg's stored values, identity and row version, the
  venue verdict and the planned writes) equals the one the operator reviewed.
  The row version (``xmin``) is in the address because a write that leaves
  every value the same is still a write the operator never reviewed: a poll's
  touch, or a same-value UPDATE, between the dry run and the apply refuses the
  whole apply (``refused_plan_drift``), and the operator dry-runs again.
* Each market is then one transaction with its own statement and lock timeouts:
  the market row is share-locked and its cohort fields re-checked, the legs are
  row-locked and must still hold the planned values AND the reviewed row
  version. A moved row refuses its market (``drift_refused``). ``last_updated``
  is backed up and reported; it needs no place of its own in the address,
  because nothing can move it without moving ``xmin``.
* Every write checks its row count against the plan; a mismatch rolls the
  market back.

## D51: backup, audit and restore

Each leg's before-image and this plan's writes go into :data:`BAK_TABLE` in the
same transaction as the write, so a run stopped part-way (router timeout, dyno
restart) leaves every committed market with its backup and nothing else. The
copy keeps an older bank row on conflict, so the leg's bank row must equal its
locked prior and this plan's writes before anything is written; anything else is
``backup_refused``. The restore's dry run is the audit: per plan hash, which
markets still hold the repaired state, which are already back, which moved::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/winner-field-repair-restore?apply=true"

It restores a market only while every one of its legs still holds exactly what
this rail wrote AND the row version this rail's write left
(``wrote_row_version``, stamped in the write's own transaction), checked again
under the restore's row lock and in the restore's own ``WHERE``. A later writer
that touched a leg, even one that left every value the same, makes the market
``moved``, and a moved market is never restored. ``plan_hash`` scopes it to one
run.

The write cap is a MODULE CONSTANT rather than a query parameter, deliberately,
so "capped" cannot be dialled off mid-run.

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

from app.tasks.census_winner_fields import DEFAULT_SCAN, MAX_SCAN
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES, KNOWN_SOURCES
from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB

logger = logging.getLogger(__name__)

ISSUE = "#1527"

# The source name for everything this repair writes. Distinct from
# clob_authoritative / clob_never_graded / clob_ordinal purely so this cohort
# stays revertible in ONE predicate (the binding spec's Amendment-1 precedent,
# reused by CAL-P003).
WRITE_SOURCE = "clob_field_repair"

# Markets WRITTEN per invocation, and the most ids one apply may name. Not a
# query param: see module docstring.
APPLY_MARKET_CAP = 50

# An impossible stored price. Anything at or above this on a leg of an incoherent
# single-winner field was never a real observation.
IMPOSSIBLE_PRICE = 0.999

BAK_TABLE = "bak_1527_winner_field_outcomes"

#: Bumped whenever the plan's shape or the write changes, so a hash reviewed
#: against an older rail can never authorize this one.
PLAN_VERSION = "1527-guarded-v2"

#: Wall clock for the CLOB reads of one call, below the router's 30 s. A plan
#: that runs out of budget is incomplete and can never be applied.
WALL_BUDGET_S = 20.0

STATEMENT_TIMEOUT = "20s"
LOCK_TIMEOUT = "2s"

COHORT_SOURCE = "polymarket"
COHORT_SPORT = "soccer"
COHORT_MARKET_TYPES = ("field", "duel")
COHORT_LEGS = 3

# Discovery walk only. The cohort is decided by :func:`cohort_refusal`; this
# narrows the window to candidates cheaply and keeps the census's own predicate.
_CANDIDATE_SQL = """
    WITH win AS (
        SELECT id FROM futures_markets
        WHERE id > :cursor
        ORDER BY id ASC LIMIT :scan
    )
    SELECT m.id
    FROM win
    JOIN futures_markets m ON m.id = win.id
    JOIN futures_outcomes o ON o.market_id = m.id
    WHERE m.mutually_exclusive = true
      AND m.source = 'polymarket'
      AND m.llm_sport_category = 'soccer'
    GROUP BY m.id
    HAVING COUNT(*) > 1
       AND (COUNT(*) FILTER (WHERE o.is_winner) > 1
            OR COUNT(*) FILTER (WHERE o.current_probability >= :bar) > 1)
    ORDER BY m.id
"""

_BOUNDS_SQL = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_markets WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""

_MARKET_COLS = "id, source, llm_sport_category, market_type, mutually_exclusive"

_MARKET_SQL = f"SELECT {_MARKET_COLS} FROM futures_markets WHERE id = :mid"

_MARKET_LOCK_SQL = _MARKET_SQL + " FOR SHARE"

_OUTCOME_COLS = """
    o.id, o.market_id, o.name, o.external_id, o.is_winner, o.resolution_source,
    o.current_probability, o.opening_probability, o.opening_american_odds,
    o.opening_captured_at, o.opening_source, o.calibration_probability,
    o.last_updated, o.xmin::text AS row_version
"""

_OUTCOMES_SQL = f"""
    SELECT {_OUTCOME_COLS}
    FROM futures_outcomes o
    WHERE o.market_id = :mid
    ORDER BY o.id
"""

_OUTCOMES_LOCK_SQL = _OUTCOMES_SQL + "    FOR UPDATE\n"

_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
        outcome_id BIGINT PRIMARY KEY,
        market_id BIGINT NOT NULL,
        prior_is_winner BOOLEAN,
        prior_current_probability NUMERIC(7, 6),
        prior_resolution_source VARCHAR(30),
        prior_opening_probability NUMERIC(7, 6),
        prior_opening_american_odds INTEGER,
        prior_opening_captured_at TIMESTAMPTZ,
        prior_opening_source VARCHAR(30),
        prior_calibration_probability NUMERIC(7, 6),
        prior_last_updated TIMESTAMPTZ,
        wrote_is_winner BOOLEAN NOT NULL,
        wrote_current_probability NUMERIC(7, 6) NOT NULL,
        nulled_opening BOOLEAN NOT NULL,
        nulled_cp BOOLEAN NOT NULL,
        plan_hash TEXT NOT NULL,
        wrote_row_version TEXT,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""

#: A bank made by an older head of this rail lacks the version column. Its rows
#: then hold NULL, which the audit reads as "not this rail's write": never restored.
_BAK_ALTER = f"ALTER TABLE {BAK_TABLE} ADD COLUMN IF NOT EXISTS wrote_row_version TEXT"

_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (
        outcome_id, market_id, prior_is_winner, prior_current_probability,
        prior_resolution_source, prior_opening_probability,
        prior_opening_american_odds, prior_opening_captured_at,
        prior_opening_source, prior_calibration_probability, prior_last_updated,
        wrote_is_winner, wrote_current_probability, nulled_opening, nulled_cp,
        plan_hash)
    SELECT id, market_id, is_winner, current_probability, resolution_source,
           opening_probability, opening_american_odds, opening_captured_at,
           opening_source, calibration_probability, last_updated,
           :wrote_is_winner, :wrote_cp, :nulled_opening, :nulled_cp, :plan_hash
    FROM futures_outcomes
    WHERE id = :oid AND market_id = :mid
    ON CONFLICT (outcome_id) DO NOTHING
"""

_PRIOR_PAIR = """
    (b.prior_is_winner, b.prior_current_probability, b.prior_resolution_source,
     b.prior_opening_probability, b.prior_opening_american_odds,
     b.prior_opening_captured_at, b.prior_opening_source,
     b.prior_calibration_probability)
    IS NOT DISTINCT FROM
    (fo.is_winner, fo.current_probability, fo.resolution_source,
     fo.opening_probability, fo.opening_american_odds, fo.opening_captured_at,
     fo.opening_source, fo.calibration_probability)
"""

#: Does the bank hold exactly this leg's locked prior and this plan's writes? A
#: count of bank rows would pass on an older row the conflict clause kept.
_BAK_PAIRED = f"""
    SELECT EXISTS (
        SELECT 1 FROM {BAK_TABLE} b
        JOIN futures_outcomes fo ON fo.id = b.outcome_id
        WHERE b.outcome_id = :oid AND b.market_id = :mid
          AND b.wrote_is_winner = :wrote_is_winner
          AND b.wrote_current_probability = :wrote_cp
          AND b.nulled_opening = :nulled_opening
          AND b.nulled_cp = :nulled_cp
          AND {_PRIOR_PAIR}
    )
"""

#: After the pair check passes: the bank row now describes THIS run, so the audit
#: and a ``plan_hash``-scoped restore attribute a re-apply to the plan that made it.
#: An older run's version token is cleared here and re-stamped after the write.
_BAK_STAMP = f"""
    UPDATE {BAK_TABLE} SET plan_hash = :plan_hash, wrote_row_version = NULL
    WHERE outcome_id = :oid AND market_id = :mid
"""

#: After every write of the market, in the same transaction: the row version this
#: rail's write left on each leg. The restore requires it, so any later write to
#: the leg, same values or not, is visible to the audit.
_BAK_VERSION = f"""
    UPDATE {BAK_TABLE} b SET wrote_row_version = fo.xmin::text
    FROM futures_outcomes fo
    WHERE fo.id = b.outcome_id AND b.market_id = :mid AND fo.market_id = :mid
      AND b.outcome_id = ANY(:ids)
"""

_WRITE_WINNER = """
    UPDATE futures_outcomes
    SET is_winner = (id = :win_id),
        current_probability = CASE WHEN id = :win_id
                                   THEN 1.0 ELSE 0.0 END,
        resolution_source = :src,
        last_updated = NOW()
    WHERE market_id = :mid AND id = ANY(:ids)
"""

# Null the impossible captured prices. There was never a real observation here,
# so this restores "unknown", not a guess. The bar is re-stated in SQL so a
# plan that drifted under the lock still cannot null a real price.
_NULL_OPENING = """
    UPDATE futures_outcomes
    SET opening_probability = NULL,
        opening_american_odds = NULL,
        opening_captured_at = NULL,
        opening_source = NULL
    WHERE market_id = :mid AND id = ANY(:ids)
      AND opening_probability >= :bar
"""

_NULL_CP = """
    UPDATE futures_outcomes
    SET calibration_probability = NULL
    WHERE market_id = :mid AND id = ANY(:ids)
      AND calibration_probability >= :bar
"""

_EXISTS = "SELECT to_regclass(:t) IS NOT NULL"

_OPENING_NULL = """(fo.opening_probability IS NULL AND fo.opening_american_odds IS NULL
         AND fo.opening_captured_at IS NULL AND fo.opening_source IS NULL)"""

#: The leg is still the very row version this rail's write left.
_WROTE_VERSION = "fo.xmin::text = b.wrote_row_version"

#: Per backed-up leg: does it still hold exactly what this rail wrote, in the row
#: version that write left, or is it already back at its prior? ``CAST`` so a
#: NULL scope binds on asyncpg.
_AUDIT_SQL = f"""
    SELECT b.plan_hash, b.market_id, b.outcome_id,
           (fo.id IS NOT NULL
            AND {_WROTE_VERSION}
            AND fo.is_winner IS NOT DISTINCT FROM b.wrote_is_winner
            AND fo.current_probability = b.wrote_current_probability
            AND fo.resolution_source = :src
            AND (NOT b.nulled_opening OR {_OPENING_NULL})
            AND (NOT b.nulled_cp OR fo.calibration_probability IS NULL)
           ) AS still_repaired,
           (fo.id IS NOT NULL AND {_PRIOR_PAIR}) AS at_prior
    FROM {BAK_TABLE} b
    LEFT JOIN futures_outcomes fo ON fo.id = b.outcome_id
    WHERE (CAST(:plan_hash AS TEXT) IS NULL OR b.plan_hash = CAST(:plan_hash AS TEXT))
      AND (CAST(:mid AS BIGINT) IS NULL OR b.market_id = CAST(:mid AS BIGINT))
    ORDER BY b.market_id, b.outcome_id
"""

_LOCK_MARKET_LEGS = """
    SELECT id FROM futures_outcomes WHERE market_id = :mid ORDER BY id FOR UPDATE
"""

_RESTORE_MARKET = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.prior_is_winner,
        current_probability = b.prior_current_probability,
        resolution_source = b.prior_resolution_source,
        opening_probability = CASE WHEN b.nulled_opening
                                   THEN b.prior_opening_probability
                                   ELSE fo.opening_probability END,
        opening_american_odds = CASE WHEN b.nulled_opening
                                     THEN b.prior_opening_american_odds
                                     ELSE fo.opening_american_odds END,
        opening_captured_at = CASE WHEN b.nulled_opening
                                   THEN b.prior_opening_captured_at
                                   ELSE fo.opening_captured_at END,
        opening_source = CASE WHEN b.nulled_opening
                              THEN b.prior_opening_source
                              ELSE fo.opening_source END,
        calibration_probability = CASE WHEN b.nulled_cp
                                       THEN b.prior_calibration_probability
                                       ELSE fo.calibration_probability END,
        last_updated = NOW()
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id AND b.market_id = :mid
      AND fo.market_id = :mid AND fo.id = ANY(:ids)
      AND {_WROTE_VERSION}
"""


# ---------------------------------------------------------------------------
# pure decisions
# ---------------------------------------------------------------------------

def _is_condition_id(external_id) -> bool:
    """Only a 0x… condition_id can be looked up on the CLOB.

    Guarding this explicitly matters: CAL-P003 found that handing a 0x id to a
    Gamma endpoint expecting a numeric id returns 422, which was misread as a
    rate limit and tripped a circuit breaker for months. Route ids to the
    endpoint that can actually accept them.
    """
    return bool(external_id) and str(external_id).startswith("0x")


def yes_winner(clob_market: dict | None) -> bool | None:
    """Did the Yes side of this CLOB binary win?

    Returns None when the market is missing, unresolved, or does not carry a
    decided Yes token — the caller must treat None as "cannot say", never as No.
    """
    if not clob_market:
        return None
    tokens = clob_market.get("tokens") or []
    for t in tokens:
        if str(t.get("outcome") or "").strip().lower() == "yes":
            w = t.get("winner")
            # Only the JSON boolean is an answer: bool("false") is True.
            return w if isinstance(w, bool) else None
    return None


def names_condition(condition_id: str, clob_market: dict | None) -> bool:
    """Does this CLOB body name the condition id we asked about?

    A body naming a different id, or none at all (missing, empty, not a string),
    is not testimony about this leg (CERT-4102).
    """
    if not isinstance(clob_market, dict):
        return False
    echoed = clob_market.get("condition_id")
    return (isinstance(echoed, str) and bool(echoed.strip())
            and echoed.lower() == str(condition_id).lower())


def venue_answer(condition_id: str, clob_market: dict | None) -> bool | None:
    """:func:`yes_winner`, but only for the condition id we asked about.

    A CLOB body that does not name that condition id is not testimony about this
    leg, so it reads as "cannot say".
    """
    if not names_condition(condition_id, clob_market):
        return None
    return yes_winner(clob_market)


def decide_market(legs: list[dict]) -> dict:
    """Pure decision for one market: repair with a single winner, or skip.

    ``legs`` is a list of ``{"outcome_id", "name", "yes_winner"}``. Kept pure so
    every fail-closed branch is directly testable without a session or the
    network.
    """
    unresolved = [leg for leg in legs if leg.get("yes_winner") is None]
    if unresolved:
        return {
            "action": "skip",
            "reason": "unresolved_legs",
            "detail": [leg["name"] for leg in unresolved][:4],
        }
    winners = [leg for leg in legs if leg["yes_winner"]]
    if len(winners) == 0:
        # Nobody won: a void/cancelled fixture. Correctly stays excluded — we
        # never force a winner onto a field that had none.
        return {"action": "skip", "reason": "no_winner_void"}
    if len(winners) > 1:
        # Upstream itself is contradictory. Refuse rather than pick.
        return {
            "action": "skip",
            "reason": "multiple_clob_winners",
            "detail": [leg["name"] for leg in winners][:4],
        }
    return {"action": "repair", "winner_outcome_id": winners[0]["outcome_id"],
            "winner_name": winners[0]["name"]}


def foreign_authority(rows) -> list[str]:
    """Tier-3 sources already on this market that this repair must never clobber."""
    return sorted({
        r["resolution_source"] for r in rows
        if r["resolution_source"] in AUTHORITATIVE_SOURCES
        and r["resolution_source"] != WRITE_SOURCE
    })


def unknown_authority(rows) -> list[str]:
    """Sources the authority ladder does not know. Their rank is unknowable, so
    overwriting them could demote a stronger grade; refuse rather than guess."""
    return sorted({
        r["resolution_source"] for r in rows
        if r["resolution_source"] is not None
        and r["resolution_source"] not in KNOWN_SOURCES
    })


def _is_draw(name) -> bool:
    return "draw" in str(name or "").lower()


def _f(v) -> Optional[float]:
    return None if v is None else round(float(v), 6)


def _near_certain(v) -> bool:
    return v is not None and float(v) >= NEAR_CERTAIN_PROB


def cohort_refusal(market: dict | None, legs: list[dict]) -> Optional[str]:
    """None when this market is in the #1527 three-way soccer cohort; otherwise
    the reason it is not. The cohort is decided here and nowhere else."""
    if market is None:
        return "market_missing"
    if market.get("source") != COHORT_SOURCE:
        return "not_polymarket"
    if market.get("llm_sport_category") != COHORT_SPORT:
        return "not_soccer"
    if market.get("market_type") not in COHORT_MARKET_TYPES:
        return "not_field_or_duel"
    if market.get("mutually_exclusive") is not True:
        return "not_mutually_exclusive"
    if len(legs) != COHORT_LEGS:
        return "not_three_way"
    if sum(1 for leg in legs if _is_draw(leg.get("name"))) != 1:
        return "not_one_draw_leg"
    winners = sum(1 for leg in legs if leg.get("is_winner"))
    near = sum(1 for leg in legs if _near_certain(leg.get("current_probability")))
    if winners > 1 or near > 1:
        return None
    if winners == 1 and all(leg.get("resolution_source") == WRITE_SOURCE for leg in legs):
        return "already_repaired"
    return "coherent"


def authority_refusal(legs: list[dict]) -> Optional[tuple[str, list]]:
    """Leg-level refusals that need no network: authority and venue identity."""
    foreign = foreign_authority(legs)
    if foreign:
        return "foreign_authority", foreign
    unknown = unknown_authority(legs)
    if unknown:
        return "unknown_authority", unknown
    if not all(_is_condition_id(leg.get("external_id")) for leg in legs):
        return "not_clob_addressable", []
    cids = [str(leg["external_id"]).lower() for leg in legs]
    if len(set(cids)) != len(cids):
        return "duplicate_condition_ids", []
    return None


def leg_image(row: dict) -> dict:
    """The stored values a plan is reviewed on and an apply re-checks under lock.

    ``last_updated`` is deliberately absent and the row version is carried
    beside the image (``row_versions``); both are in the reviewed address.
    """
    at = row.get("opening_captured_at")
    return {
        "outcome_id": int(row["id"]),
        "name": row.get("name"),
        "external_id": row.get("external_id"),
        "is_winner": row.get("is_winner"),
        "resolution_source": row.get("resolution_source"),
        "current_probability": _f(row.get("current_probability")),
        "opening_probability": _f(row.get("opening_probability")),
        "opening_american_odds": row.get("opening_american_odds"),
        "opening_captured_at": at.isoformat() if hasattr(at, "isoformat") else at,
        "opening_source": row.get("opening_source"),
        "calibration_probability": _f(row.get("calibration_probability")),
    }


def market_image(market: dict) -> dict:
    return {
        "market_id": int(market["id"]),
        "source": market.get("source"),
        "llm_sport_category": market.get("llm_sport_category"),
        "market_type": market.get("market_type"),
        "mutually_exclusive": market.get("mutually_exclusive"),
    }


def planned_writes(legs: list[dict], win_id: int) -> list[dict]:
    """Per leg: what this rail writes. Decided on each leg's own values."""
    out = []
    for leg in legs:
        op, cp = leg.get("opening_probability"), leg.get("calibration_probability")
        out.append({
            "outcome_id": int(leg["id"]),
            "is_winner": int(leg["id"]) == int(win_id),
            "current_probability": 1.0 if int(leg["id"]) == int(win_id) else 0.0,
            "null_opening": op is not None and float(op) >= IMPOSSIBLE_PRICE,
            "null_cp": cp is not None and float(cp) >= IMPOSSIBLE_PRICE,
        })
    return out


def plan_hash_for(named_ids: list[int], planned: list[dict]) -> str:
    """Content address of an exact-id plan: the ids named, and for every planned
    market its cohort fields, every leg's stored values, identity and row
    version, the venue verdict per leg and the writes. Touch-stamps and timings
    are excluded; no write can move a touch-stamp without moving the version."""
    body = json.dumps(
        {
            "version": PLAN_VERSION,
            "write_source": WRITE_SOURCE,
            "impossible_price": IMPOSSIBLE_PRICE,
            "named_ids": sorted(int(i) for i in named_ids),
            "markets": sorted(
                ({**{k: p[k] for k in ("market", "legs", "venue", "winner_outcome_id",
                                       "writes")},
                  "row_versions": {str(k): v for k, v in p["row_versions"].items()}}
                 for p in planned),
                key=lambda p: p["market"]["market_id"],
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
    if len(ids) > APPLY_MARKET_CAP:
        raise ValueError(
            f"only_ids names {len(ids)} markets; at most {APPLY_MARKET_CAP} per call")
    return ids


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/winner-field-repair-restore?apply=true"'
    )


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

async def _set_bounds(session) -> None:
    """Per transaction: ``SET LOCAL`` ends with the transaction it is set in."""
    await session.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


async def _plan_market(session, service, mid: int, deadline: float) -> dict:
    """One market: a planned entry, or a refusal with a reason. Reads only."""
    market = (await session.execute(text(_MARKET_SQL), {"mid": mid})).mappings().first()
    legs = [dict(r) for r in
            (await session.execute(text(_OUTCOMES_SQL), {"mid": mid})).mappings().all()]
    market = dict(market) if market else None

    reason = cohort_refusal(market, legs)
    if reason:
        return {"market_id": mid, "action": "skip", "reason": reason}
    refused = authority_refusal(legs)
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
        except Exception as e:  # noqa: BLE001
            # 429/5xx/timeout is NOT "no winner" (gotcha #36). Skip the whole
            # market so it is retried intact next invocation.
            return {"market_id": mid, "action": "skip", "reason": "clob_error",
                    "detail": str(e)[:80]}
        venue.append({"outcome_id": int(leg["id"]), "condition_id": cid,
                      "yes_winner": venue_answer(cid, clob)})

    decision = decide_market([
        {"outcome_id": v["outcome_id"], "name": leg["name"], "yes_winner": v["yes_winner"]}
        for v, leg in zip(venue, legs)
    ])
    if decision["action"] == "skip":
        return {"market_id": mid, "action": "skip", "reason": decision["reason"],
                "detail": decision.get("detail")}

    win_id = decision["winner_outcome_id"]
    return {
        "market_id": mid,
        "action": "repair",
        "winner": decision["winner_name"],
        "winner_outcome_id": int(win_id),
        "market": market_image(market),
        "legs": [leg_image(leg) for leg in legs],
        "venue": venue,
        "writes": planned_writes(legs, win_id),
        # In the address, and checked again under the apply's row lock.
        "row_versions": {int(leg["id"]): leg.get("row_version") for leg in legs},
        "prior_last_updated": {
            int(leg["id"]): (leg["last_updated"].isoformat()
                             if hasattr(leg.get("last_updated"), "isoformat")
                             else leg.get("last_updated"))
            for leg in legs
        },
    }


def _ledger_view(p: dict) -> dict:
    if p["action"] != "repair":
        return {k: p[k] for k in ("market_id", "action", "reason", "detail") if k in p}
    return {
        "market_id": p["market_id"], "action": "repair", "winner": p["winner"],
        "winner_outcome_id": p["winner_outcome_id"],
        "was_winners": sum(1 for leg in p["legs"] if leg["is_winner"]),
        "legs": p["legs"], "venue": p["venue"], "writes": p["writes"],
        "row_versions": p["row_versions"],
        "prior_last_updated": p["prior_last_updated"],
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
    market = (await session.execute(text(_MARKET_LOCK_SQL), {"mid": mid})).mappings().first()
    if market is None or market_image(dict(market)) != p["market"]:
        await session.rollback()
        return DRIFT
    locked = [dict(r) for r in
              (await session.execute(text(_OUTCOMES_LOCK_SQL), {"mid": mid})).mappings().all()]
    if [leg_image(r) for r in locked] != p["legs"]:
        await session.rollback()
        return DRIFT
    if {int(r["id"]): r.get("row_version") for r in locked} != p["row_versions"]:
        await session.rollback()
        return DRIFT

    ids = [w["outcome_id"] for w in p["writes"]]
    # Every bank row is checked before the first UPDATE.
    for w in p["writes"]:
        args = {"oid": w["outcome_id"], "mid": mid, "wrote_is_winner": w["is_winner"],
                "wrote_cp": w["current_probability"], "nulled_opening": w["null_opening"],
                "nulled_cp": w["null_cp"]}
        await session.execute(text(_BAK_COPY), {**args, "plan_hash": digest})
        paired = (await session.execute(text(_BAK_PAIRED), args)).scalar_one()
        if not paired:
            await session.rollback()
            return BACKUP_MISMATCH
        await session.execute(text(_BAK_STAMP),
                              {"oid": w["outcome_id"], "mid": mid, "plan_hash": digest})

    written = (await session.execute(
        text(_WRITE_WINNER),
        {"win_id": p["winner_outcome_id"], "mid": mid, "ids": ids, "src": WRITE_SOURCE},
    )).rowcount
    if written != len(ids):
        await session.rollback()
        return ROWCOUNT
    open_ids = [w["outcome_id"] for w in p["writes"] if w["null_opening"]]
    if open_ids:
        n = (await session.execute(text(_NULL_OPENING),
                                   {"mid": mid, "ids": open_ids, "bar": IMPOSSIBLE_PRICE})).rowcount
        if n != len(open_ids):
            await session.rollback()
            return ROWCOUNT
    cp_ids = [w["outcome_id"] for w in p["writes"] if w["null_cp"]]
    if cp_ids:
        n = (await session.execute(text(_NULL_CP),
                                   {"mid": mid, "ids": cp_ids, "bar": IMPOSSIBLE_PRICE})).rowcount
        if n != len(cp_ids):
            await session.rollback()
            return ROWCOUNT
    stamped = (await session.execute(text(_BAK_VERSION), {"mid": mid, "ids": ids})).rowcount
    if stamped != len(ids):
        await session.rollback()
        return ROWCOUNT
    await session.commit()
    return None


def _empty(base: dict) -> dict:
    return {**base, "candidates": 0, "repaired": 0, "skipped": 0, "capped_out": 0,
            "outcomes_written": 0, "openings_nulled": 0, "cp_nulled": 0,
            "drift_refused": 0, "backup_refused": 0, "rowcount_refused": 0,
            "skip_reasons": {}, "ledger": [], "refused_markets": []}


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    only_ids: str | None = None,
    plan_hash: str | None = None,
) -> dict:
    """Plan one discovery window, or (with ``only_ids``) exactly the named
    markets; with ``apply`` + ``only_ids`` + the plan's own hash, write them.
    Dry-run by default.

    ``limit``  markets to WALK in discovery mode (never a write count).
    ``offset`` market-id cursor, exclusive; pass the returned ``next_offset``.
    """
    from app.services.polymarket_api import PolymarketAPIService

    started = time.monotonic()
    base: dict[str, Any] = {
        "repair": "winner-field-repair", "issue": ISSUE, "apply": apply,
        "write_source": WRITE_SOURCE, "apply_market_cap": APPLY_MARKET_CAP,
        "plan_version": PLAN_VERSION, "backup_table": BAK_TABLE,
        "restore_command": restore_command(),
    }
    try:
        named = parse_only_ids(only_ids)
    except ValueError as e:
        return {**_empty(base), "terminal": "refused_bad_only_ids", "detail": str(e)}
    if apply and named is None:
        return {**_empty(base), "terminal": "refused_no_exact_ids",
                "detail": "apply writes only the market ids a reviewed plan names: "
                          "dry-run with ?only_ids= and pass them with its plan_hash"}
    if apply and not plan_hash:
        return {**_empty(base), "terminal": "refused_no_plan_hash",
                "detail": "run the dry run with the same only_ids and pass its plan_hash"}

    await _set_bounds(session)
    walk: dict[str, Any] = {}
    if named is not None:
        candidate_ids = list(named)
        walk = {"mode": "exact", "only_ids": named}
    else:
        scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
        cursor = int(offset or 0)
        bounds = (
            await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan})
        ).mappings().first()
        walked = int(bounds["n"] or 0)
        if not walked:
            await session.rollback()
            return {**_empty(base), "terminal": "dry_run", "mode": "discovery",
                    "markets_walked": 0, "exhausted": True, "next_offset": None}
        candidate_ids = [
            r[0] for r in (
                await session.execute(
                    text(_CANDIDATE_SQL),
                    {"cursor": cursor, "scan": scan, "bar": NEAR_CERTAIN_PROB},
                )
            ).all()
        ]
        walk = {"mode": "discovery", "markets_walked": walked,
                "window": {"lo": bounds["lo"], "hi": bounds["hi"]},
                "next_offset": bounds["hi"] if walked == scan else None,
                "exhausted": walked < scan}

    deadline = started + WALL_BUDGET_S
    service = PolymarketAPIService()
    plans: list[dict] = []
    capped_out = 0
    for mid in candidate_ids:
        if sum(1 for p in plans if p["action"] == "repair") >= APPLY_MARKET_CAP:
            capped_out += 1
            continue
        plans.append(await _plan_market(session, service, int(mid), deadline))

    planned = [p for p in plans if p["action"] == "repair"]
    skip_reasons: dict[str, int] = {}
    for p in plans:
        if p["action"] != "repair":
            skip_reasons[p["reason"]] = skip_reasons.get(p["reason"], 0) + 1
    incomplete = skip_reasons.get("budget_exhausted", 0) > 0
    digest = plan_hash_for(named, planned) if named is not None else None

    summary = {
        **_empty(base), **walk,
        "candidates": len(candidate_ids),
        "planned_market_ids": [p["market_id"] for p in planned],
        "outcomes_planned": sum(len(p["writes"]) for p in planned),
        "openings_planned": sum(w["null_opening"] for p in planned for w in p["writes"]),
        "cp_planned": sum(w["null_cp"] for p in planned for w in p["writes"]),
        "skipped": sum(skip_reasons.values()),
        "capped_out": capped_out,
        "skip_reasons": skip_reasons,
        "plan_incomplete": incomplete,
        "plan_hash": digest,
        "ledger": [_ledger_view(p) for p in plans][:100],
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
        await session.execute(text(_BAK_ALTER))
        await session.commit()
    repaired = outcomes_written = openings_nulled = cp_nulled = 0
    counts = {DRIFT: 0, BACKUP_MISMATCH: 0, ROWCOUNT: 0}
    refused: list[dict] = []
    for p in planned:
        await _set_bounds(session)
        try:
            reason = await _apply_market(session, p, digest)
        except Exception as e:  # noqa: BLE001 — one market never stops its siblings
            await session.rollback()
            logger.warning("%s market %s refused: %s", ISSUE, p["market_id"], e)
            reason = "error"
        if reason is None:
            repaired += 1
            outcomes_written += len(p["writes"])
            openings_nulled += sum(w["null_opening"] for w in p["writes"])
            cp_nulled += sum(w["null_cp"] for w in p["writes"])
            continue
        counts[reason] = counts.get(reason, 0) + 1
        refused.append({"market_id": p["market_id"], "reason": reason})
    if repaired:
        logger.warning(
            "%s repaired %s markets to one winner (%s refused). Backup in %s. "
            "D51 undo:\n%s", ISSUE, repaired, len(refused), BAK_TABLE, restore_command(),
        )
    return {**summary, "terminal": "applied", "repaired": repaired,
            "outcomes_written": outcomes_written, "openings_nulled": openings_nulled,
            "cp_nulled": cp_nulled, "drift_refused": counts[DRIFT],
            "backup_refused": counts[BACKUP_MISMATCH],
            "rowcount_refused": counts[ROWCOUNT],
            "error_refused": counts.get("error", 0), "refused_markets": refused}


# ---------------------------------------------------------------------------
# audit and restore
# ---------------------------------------------------------------------------

def _market_states(rows) -> dict[int, dict]:
    """Group audit rows by market: ``repaired`` when every leg still holds this
    rail's write, ``restored`` when every leg is back at its prior, else
    ``moved`` (a later writer changed it; never restored)."""
    out: dict[int, dict] = {}
    for r in rows:
        m = out.setdefault(int(r["market_id"]), {"plan_hash": r["plan_hash"], "legs": [],
                                                 "repaired": True, "at_prior": True})
        m["legs"].append(int(r["outcome_id"]))
        m["repaired"] = m["repaired"] and bool(r["still_repaired"])
        m["at_prior"] = m["at_prior"] and bool(r["at_prior"])
    for m in out.values():
        m["state"] = ("repaired" if m["repaired"]
                      else "restored" if m["at_prior"] else "moved")
    return out


async def restore(session, apply: bool = False, plan_hash: str | None = None) -> dict:
    """Audit (dry run) or put back every market this rail repaired whose legs
    all still hold exactly what it wrote, in the row version its write left.
    ``plan_hash`` scopes it to one run."""
    base = {"issue": ISSUE, "backup_table": BAK_TABLE, "apply": apply,
            "plan_hash": plan_hash}
    if not (await session.execute(text(_EXISTS), {"t": BAK_TABLE})).scalar_one():
        await session.rollback()
        return {**base, "terminal": "refused_no_backup", "restored_markets": 0}
    await _set_bounds(session)
    rows = (await session.execute(
        text(_AUDIT_SQL), {"src": WRITE_SOURCE, "plan_hash": plan_hash, "mid": None},
    )).mappings().all()
    states = _market_states(rows)
    by_plan: dict[str, dict[str, int]] = {}
    for m in states.values():
        tally = by_plan.setdefault(m["plan_hash"], {"repaired": 0, "restored": 0, "moved": 0})
        tally[m["state"]] += 1
    audit = {
        **base,
        "markets_backed_up": len(states),
        "outcomes_backed_up": sum(len(m["legs"]) for m in states.values()),
        "by_plan_hash": by_plan,
        "markets": [{"market_id": mid, "state": m["state"], "plan_hash": m["plan_hash"],
                     "legs": m["legs"]} for mid, m in sorted(states.items())][:200],
    }
    if not apply:
        await session.rollback()
        return {**audit, "terminal": "dry_run", "restored_markets": 0}

    await session.rollback()
    restored, refused = 0, []
    for mid, m in sorted(states.items()):
        if m["state"] != "repaired":
            continue
        await _set_bounds(session)
        try:
            await session.execute(text(_LOCK_MARKET_LEGS), {"mid": mid})
            again = _market_states((await session.execute(
                text(_AUDIT_SQL), {"src": WRITE_SOURCE, "plan_hash": plan_hash, "mid": mid},
            )).mappings().all()).get(mid)
            if not again or again["state"] != "repaired" or again["legs"] != m["legs"]:
                await session.rollback()
                refused.append({"market_id": mid, "reason": DRIFT})
                continue
            n = (await session.execute(text(_RESTORE_MARKET),
                                       {"mid": mid, "ids": m["legs"]})).rowcount
            if n != len(m["legs"]):
                await session.rollback()
                refused.append({"market_id": mid, "reason": ROWCOUNT})
                continue
            await session.commit()
            restored += 1
        except Exception as e:  # noqa: BLE001 — one market never stops its siblings
            await session.rollback()
            logger.warning("%s restore of market %s refused: %s", ISSUE, mid, e)
            refused.append({"market_id": mid, "reason": "error"})
    logger.warning("%s restore: %s markets put back, %s refused", ISSUE, restored,
                   len(refused))
    return {**audit, "terminal": "restored", "restored_markets": restored,
            "refused_markets": refused}
