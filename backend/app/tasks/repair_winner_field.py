"""CAL-P007 (#1527): attended, capped repair of the three-winner cohort.

CAL-P006 stopped the producers and shipped the bounded census. This is the write
half, approved by Alex 2026-08-07 under the same attended capped-batch discipline
as the ``event-final-scores`` apply pass: dry-run census first, then capped writes
while a human is attending, evidence to #1544.

**Why this is allowed to write at all** (gotcha #21 — never bulk-reset ``is_winner``
without a source that can immediately re-resolve). It is not a reset. Each leg of
one of these markets is its OWN Polymarket ``condition_id``, so the CLOB answers
the question directly, per leg, with no name-matching heuristic in the way::

    Will Slavia Praha beat Anderlecht?         closed=True   Yes=False
    Will Anderlecht beat Slavia Praha?         closed=True   Yes=True
    Will the match ... end in a draw?          closed=True   Yes=False

Exactly one winner, established independently of our (impossible) stored price.
That is stronger evidence than CAL-P003's cohort had, because there is no mapping
step that can be wrong — the id IS the identity.

**What gets written.**

* ``is_winner`` + ``current_probability`` from settlement (1.0 winner / 0.0 losers,
  the same shape the poller's ``api_settlement`` path writes), source
  ``clob_field_repair``.
* ``calibration_probability`` and the whole ``opening_*`` family NULLED where they
  hold an impossible near-certain value. This follows the reviewed both-1.0
  precedent in ``backfill_winners`` — whose predicate is ``COUNT(*) = 2``, so
  three-leg markets fall straight through it, which is the third instance of this
  bug's signature pattern (a guard exists; its predicate excludes this shape).

  Nulling is not caution, it is the honest state. CAL-P006 established these
  markets were first ingested ~2 years AFTER the fixture was played and that all
  72 snapshots per leg are 1.0 — there was never a real price, so there is nothing
  to restore and any "repaired" price would be invented.

**Fail closed, everywhere.** A market is skipped — never partially written —
unless every leg resolves and exactly one is a winner. Zero winners (a void), more
than one winner (contradictory upstream), any 404/429/error, or a foreign tier-3
source already present: all skip with a recorded reason.

The write cap is a MODULE CONSTANT rather than a query parameter, deliberately, so
"capped" cannot be dialled off mid-run. Attended discipline means the operator
re-invokes; it does not mean the operator can raise the ceiling.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.tasks.census_winner_fields import DEFAULT_SCAN, MAX_SCAN
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB

logger = logging.getLogger(__name__)

# The source name for everything this repair writes. Distinct from
# clob_authoritative / clob_never_graded / clob_ordinal purely so this cohort
# stays revertible in ONE predicate (the binding spec's Amendment-1 precedent,
# reused by CAL-P003).
WRITE_SOURCE = "clob_field_repair"

# Markets WRITTEN per invocation. Not a query param: see module docstring.
# The known cohort is ~214 markets, so this is ~5 attended invocations.
APPLY_MARKET_CAP = 50

# An impossible stored price. Anything at or above this on a leg of an incoherent
# single-winner field was never a real observation.
IMPOSSIBLE_PRICE = 0.999

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

_OUTCOMES_SQL = """
    SELECT o.id, o.name, o.external_id, o.is_winner, o.resolution_source,
           o.current_probability, o.opening_probability,
           o.calibration_probability
    FROM futures_outcomes o
    WHERE o.market_id = :mid
    ORDER BY o.id
"""


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
            return bool(w) if w is not None else None
    return None


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


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Repair one bounded market-id window. Dry-run by default.

    ``limit``  markets to WALK (not to write — see ``APPLY_MARKET_CAP``).
    ``offset`` market-id cursor, exclusive; pass the returned ``next_offset``.
    """
    from app.services.polymarket_api import PolymarketAPIService

    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(offset or 0)

    await session.execute(text("SET LOCAL statement_timeout = '20s'"))

    bounds = (
        await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan})
    ).mappings().first()
    walked = int(bounds["n"] or 0)

    if not walked:
        return {
            "repair": "winner-field-repair", "apply": apply,
            "markets_walked": 0, "exhausted": True, "next_offset": None,
            "candidates": 0, "repaired": 0, "skipped": 0, "capped_out": 0,
            "outcomes_written": 0, "openings_nulled": 0,
            "skip_reasons": {}, "ledger": [],
        }

    candidate_ids = [
        r[0] for r in (
            await session.execute(
                text(_CANDIDATE_SQL),
                {"cursor": cursor, "scan": scan, "bar": NEAR_CERTAIN_PROB},
            )
        ).all()
    ]

    ledger: list[dict] = []
    skip_reasons: dict[str, int] = {}
    repaired = outcomes_written = openings_nulled = capped_out = 0

    def _skip(mid: str | int, reason: str, **extra):
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        ledger.append({"market_id": mid, "action": "skip", "reason": reason, **extra})

    service = PolymarketAPIService()
    for mid in candidate_ids:
        if repaired >= APPLY_MARKET_CAP:
            capped_out += 1
            continue

        rows = (
            await session.execute(text(_OUTCOMES_SQL), {"mid": mid})
        ).mappings().all()

        foreign = foreign_authority(rows)
        if foreign:
            _skip(mid, "foreign_authority", detail=foreign)
            continue

        if not all(_is_condition_id(r["external_id"]) for r in rows):
            _skip(mid, "not_clob_addressable")
            continue

        legs = []
        fetch_failed = False
        for r in rows:
            try:
                clob = await service.get_clob_market_by_condition(str(r["external_id"]))
            except Exception as e:
                # 429/5xx/timeout is NOT "no winner" (gotcha #36). Skip the whole
                # market so it is retried intact next invocation.
                _skip(mid, "clob_error", detail=str(e)[:80])
                fetch_failed = True
                break
            legs.append({
                "outcome_id": r["id"], "name": r["name"],
                "yes_winner": yes_winner(clob),
            })
        if fetch_failed:
            continue

        decision = decide_market(legs)
        if decision["action"] == "skip":
            _skip(mid, decision["reason"], detail=decision.get("detail"))
            continue

        win_id = decision["winner_outcome_id"]
        entry = {
            "market_id": mid, "action": "repair",
            "winner": decision["winner_name"],
            "was_winners": sum(1 for r in rows if r["is_winner"]),
            "legs": len(rows),
            "outcomes": len(rows),
            "openings_to_null": sum(
                1 for r in rows
                if (r["opening_probability"] is not None
                    and r["opening_probability"] >= IMPOSSIBLE_PRICE)
                or (r["calibration_probability"] is not None
                    and r["calibration_probability"] >= IMPOSSIBLE_PRICE)
            ),
        }

        if apply:
            await session.execute(
                text("""
                    UPDATE futures_outcomes
                    SET is_winner = (id = :win_id),
                        current_probability = CASE WHEN id = :win_id
                                                   THEN 1.0 ELSE 0.0 END,
                        resolution_source = :src,
                        last_updated = NOW()
                    WHERE market_id = :mid
                """),
                {"win_id": win_id, "mid": mid, "src": WRITE_SOURCE},
            )
            # Null the impossible captured prices. There was never a real
            # observation here, so this restores "unknown", not a guess.
            nulled = await session.execute(
                text("""
                    UPDATE futures_outcomes
                    SET calibration_probability = NULL,
                        opening_probability = NULL,
                        opening_american_odds = NULL,
                        opening_captured_at = NULL,
                        opening_source = NULL
                    WHERE market_id = :mid
                      AND (opening_probability >= :bar
                           OR calibration_probability >= :bar)
                """),
                {"mid": mid, "bar": IMPOSSIBLE_PRICE},
            )
            await session.commit()
            openings_nulled += nulled.rowcount or 0
            outcomes_written += len(rows)

        repaired += 1
        ledger.append(entry)

    return {
        "repair": "winner-field-repair",
        "apply": apply,
        "write_source": WRITE_SOURCE,
        "apply_market_cap": APPLY_MARKET_CAP,
        "markets_walked": walked,
        "window": {"lo": bounds["lo"], "hi": bounds["hi"]},
        "next_offset": bounds["hi"] if walked == scan else None,
        "exhausted": walked < scan,
        "candidates": len(candidate_ids),
        "repaired": repaired,
        "skipped": sum(skip_reasons.values()),
        "capped_out": capped_out,
        "outcomes_written": outcomes_written,
        "openings_nulled": openings_nulled,
        "skip_reasons": skip_reasons,
        "ledger": ledger[:100],
    }
