"""#10590 — re-grade the Polymarket totals `poly_total_score` graded on the wrong quantity.

## the defect

`_resolve_polymarket_total_from_scores` (#140) graded every resolved Polymarket
market whose name ended ``: O/U N`` against ``home_score + away_score``. The
anchor refused a qualifier AFTER the colon and nothing BEFORE it, so team totals
("San Diego Padres Team Total: O/U 4.5"), team stat totals ("Alabama Total
Rushing Yards: O/U 125.5"), esports "Games Total: O/U 2.5" and cricket
over-lines were all graded as if they were the game total. Specimen: event
15323985, SD 3 – MIL 4, markets 64157611/12/16/17 stored Over-won while the CLOB
says Under won. Measured 2026-10-06: 3,624 team-total markets across 230 games
carry ``poly_total_score``; on 1,425 of them the stored winner is the leg the
venue prices below 0.5.

The grader is fixed in the same change (``_poly_total_line`` now requires the
"{A} vs. {B}" full-game prefix). This rail repairs the rows it already wrote.

## why these rows never healed on their own

``poly_total_score`` is tier 2 (ruling 038), so the ladder would let venue
settlement replace it, but the venue writers' UPDATE guard is
``resolution_source IS NULL OR IN OVERWRITABLE_WINNER_SOURCES``, and that list
holds only guesses and soft closes. Every candidate scan also drops a market
once ``BOOL_OR(is_winner)`` is true. So a wrong ``poly_total_score`` grade is
permanent unless something re-grades it.

## population: what the corrected grader refuses

A market is in scope when (a) it is a resolved Polymarket market whose legs
carry ``poly_total_score`` and (b) ``_poly_total_line`` (the grader's own,
corrected rule) refuses its name. Every such grade came from the old rule
alone, so the population is defined by the code that made the mistake and
cannot drift from it. Full-game "{A} vs. {B}: O/U N" grades are untouched.

## the re-grade source (gotcha #21)

Nothing is reset. Each market is ONE CLOB binary whose tokens are literally
"Over"/"Under" with a ``winner`` flag, so the venue answers per market, by
``condition_id``, through the same mapper and the same name-concordance guard
``clob_resolve`` uses (``map_clob_to_outcome`` rule 3, tier ``resolved_direct``).
It writes ``clob_authoritative``, the tier-3 name that mapper's direct tier
already writes, so every client verdict allowlist renders it unchanged (a new
source name would be invisible on web and iOS until both allowlists learned it).
Only ``is_winner`` and ``resolution_source`` change. The stored prices are
already the venue's settled prices.

Fail closed: a 404, a void (no single winner), a discordant question, any shape
other than a direct Over/Under mapping, a leg that does not carry
``poly_total_score``, or a tier-3 source already on the market are all SKIPPED
by name and leave the row exactly as it is.

## D51: backup and restore

Each market's legs are copied into :data:`BAK_TABLE` in the SAME transaction as
its write. The write is joined to that backup and compare-and-sets on
``resolution_source = 'poly_total_score'``, so an unbacked row is unreachable
and a leg another writer graded meanwhile is left alone, and its backup row is
pruned. The undo is one statement on the same rail::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/poly-total-scope-restore?apply=true"

The restore puts back only legs still carrying the ``clob_authoritative`` this
rail wrote. A later CLOB grade on the same leg would be the same venue answer.

## paging

Keyset by market id (``after_id``), ``limit`` markets EXAMINED per call, and a
wall clock below the router's 30 s, because each in-scope market costs one CLOB
fetch. A call that stops on the clock returns the last market it finished as
``next_after_id``. A CLOB error stops the call BEFORE that market, so it is
retried, never skipped (gotcha #36). Re-invoke until ``exhausted``.
ATTENDED ONLY: never wire this to a beat.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY

from app.tasks.backfill_winners import _poly_total_line
from app.tasks.clob_resolve import _name_concordance_ok, map_clob_to_outcome
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

logger = logging.getLogger(__name__)

ISSUE = "#10590"
BAK_TABLE = "bak_10590_poly_total_scope"
READ_SOURCE = "poly_total_score"
WRITE_SOURCE = "clob_authoritative"

DEFAULT_SCAN = 500
MAX_SCAN = 2000
#: Wall clock per call. Below the router's 30 s with room for the commit.
WALL_BUDGET_S = 20.0

#: Markets examined per page. ``m.name ~* ':[[:space:]]*o/u'`` is the OLD
#: grader's SQL prefilter, so it is a superset of everything the old rule ever
#: graded; the Python check below narrows it to what the new rule refuses.
#: Measured 2026-10-06: 500 markets from id 0 in 3.2 s (pk walk).
_PAGE_SQL = f"""
    SELECT m.id AS market_id, m.name AS market_name, m.external_id AS market_ext
    FROM futures_markets m
    WHERE m.source = 'polymarket'
      AND m.status = 'resolved'
      AND m.name ~* ':[[:space:]]*o/u'
      AND m.id > :after_id
      AND EXISTS (
          SELECT 1 FROM futures_outcomes o
          WHERE o.market_id = m.id AND o.resolution_source = '{READ_SOURCE}'
      )
    ORDER BY m.id
    LIMIT :scan
"""

_LEGS_SQL = """
    SELECT id, name, external_id, is_winner, resolution_source
    FROM futures_outcomes
    WHERE market_id = :mid
    ORDER BY id
"""

_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} AS
    SELECT fo.id AS outcome_id, fo.market_id, fo.is_winner,
           fo.resolution_source, NOW() AS backed_up_at
    FROM futures_outcomes fo
    WHERE false
"""
_BAK_INDEX = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk ON {BAK_TABLE} (outcome_id)"
)

#: Never overwrite a backup row: the FIRST copy is the one that predates this
#: rail. ``RETURNING`` names the rows THIS call inserted, for the prune.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, market_id, is_winner, resolution_source,
                             backed_up_at)
    SELECT fo.id, fo.market_id, fo.is_winner, fo.resolution_source, NOW()
    FROM futures_outcomes fo
    WHERE fo.id = ANY(:ids) AND fo.resolution_source = '{READ_SOURCE}'
    ON CONFLICT (outcome_id) DO NOTHING
    RETURNING outcome_id
"""

#: The write: joined to the backup (an unbacked row has nothing to join to) and
#: compare-and-set on the source this rail repairs.
_APPLY_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = (fo.id = :winner_id),
        resolution_source = '{WRITE_SOURCE}',
        last_updated = NOW()
    FROM {BAK_TABLE} b
    WHERE b.outcome_id = fo.id
      AND fo.id = ANY(:ids)
      AND fo.resolution_source = '{READ_SOURCE}'
    RETURNING fo.id
"""

_BAK_PRUNE = f"DELETE FROM {BAK_TABLE} WHERE outcome_id = ANY(:ids)"

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

_RESTORE_WHERE = f"""
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND fo.resolution_source = '{WRITE_SOURCE}'
      AND (fo.is_winner IS DISTINCT FROM b.is_winner
           OR fo.resolution_source IS DISTINCT FROM b.resolution_source)
"""
_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.is_winner, resolution_source = b.resolution_source,
        last_updated = NOW()
    {_RESTORE_WHERE}
"""
_RESTORE_PENDING = f"SELECT count(*) FROM futures_outcomes fo {_RESTORE_WHERE}"


def _ids(sql: str):
    """asyncpg needs the array type spelled out, or ``ANY(:ids)`` matches nothing."""
    return text(sql).bindparams(bindparam("ids", type_=ARRAY(BigInteger)))


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/poly-total-scope-restore?apply=true"'
    )


def condition_id_of(market_ext: Optional[str], legs: list[dict]) -> Optional[str]:
    """The CLOB ``condition_id``: the market's own external id, or a leg's minus
    its ``_yes``/``_no`` suffix. Only a ``0x`` id can be looked up on the CLOB."""
    cand = market_ext or ""
    if not cand.startswith("0x"):
        for leg in legs:
            ext = leg.get("external_id") or ""
            for suf in ("_yes", "_no"):
                if ext.endswith(suf):
                    cand = ext[: -len(suf)]
                    break
            if cand.startswith("0x"):
                break
    return cand if cand.startswith("0x") else None


def decide(market_name: str, legs: list[dict], clob: Optional[dict]) -> dict:
    """Pure decision for one in-scope market: re-grade from the venue, or skip.

    ``legs``: ``{"id","name","external_id","is_winner","resolution_source"}``.
    """
    foreign = sorted({
        leg["resolution_source"] for leg in legs
        if leg["resolution_source"] in AUTHORITATIVE_SOURCES
    })
    if foreign:
        return {"action": "skip", "reason": "foreign_authority", "detail": foreign}
    if len(legs) != 2 or any(leg["resolution_source"] != READ_SOURCE for leg in legs):
        return {"action": "skip", "reason": "mixed_sources"}
    if clob is None:
        return {"action": "skip", "reason": "clob_missing"}
    if not _name_concordance_ok(market_name, clob.get("question") or ""):
        return {"action": "skip", "reason": "name_discordant",
                "detail": clob.get("question")}
    res = map_clob_to_outcome(clob, legs, event_linked=True)
    if res.get("tier") != "resolved_direct":
        return {"action": "skip", "reason": res.get("skip") or res.get("tier"),
                "detail": res.get("why")}
    by_id = {leg["id"]: leg for leg in legs}
    return {
        "action": "regrade",
        "winner_id": res["winner_id"],
        "winner": by_id[res["winner_id"]]["name"],
        "verdict_changes": not bool(by_id[res["winner_id"]]["is_winner"]),
    }


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
) -> dict[str, Any]:
    """Plan (and with ``apply`` write) one page. Dry-run by default."""
    from app.services.polymarket_api import PolymarketAPIService

    started = time.monotonic()
    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(after_id or 0)

    await session.execute(text("SET LOCAL statement_timeout = '20s'"))
    page = (
        await session.execute(text(_PAGE_SQL), {"after_id": cursor, "scan": scan})
    ).all()

    skip_reasons: dict[str, int] = {}
    ledger: list[dict] = []
    in_scope = regraded = verdicts_changed = legs_written = conceded = 0
    next_after_id = cursor
    stopped_on: Optional[str] = None
    service = PolymarketAPIService() if page else None
    tables_ready = False

    for row in page:
        if _poly_total_line(row.market_name) is not None:
            # A full-game "{A} vs. {B}: O/U N" grade: right quantity, not ours.
            next_after_id = row.market_id
            continue
        if time.monotonic() - started > WALL_BUDGET_S:
            stopped_on = "wall_budget"
            break
        in_scope += 1
        legs = [
            dict(r._mapping)
            for r in (await session.execute(text(_LEGS_SQL), {"mid": row.market_id})).all()
        ]
        cond = condition_id_of(row.market_ext, legs)
        clob = None
        if cond is None:
            decision = {"action": "skip", "reason": "not_clob_addressable"}
        else:
            try:
                clob = await service.get_clob_market_by_condition(cond)
            except Exception as e:  # noqa: BLE001 — 429/5xx is not "no winner"
                stopped_on = f"clob_error: {str(e)[:80]}"
                in_scope -= 1
                break
            decision = decide(row.market_name, legs, clob)

        entry = {"market_id": row.market_id, "name": row.market_name, **decision}
        if decision["action"] == "skip":
            skip_reasons[decision["reason"]] = skip_reasons.get(decision["reason"], 0) + 1
            ledger.append(entry)
            next_after_id = row.market_id
            continue

        ids = [leg["id"] for leg in legs]
        if apply:
            if not tables_ready:
                await session.execute(text(_BAK_CREATE))
                await session.execute(text(_BAK_INDEX))
                tables_ready = True
            inserted = {
                r[0] for r in (await session.execute(_ids(_BAK_COPY), {"ids": ids})).all()
            }
            changed = [
                r[0] for r in (
                    await session.execute(
                        _ids(_APPLY_SQL),
                        {"ids": ids, "winner_id": decision["winner_id"]},
                    )
                ).all()
            ]
            stale = sorted(inserted - set(changed))
            if stale:
                await session.execute(_ids(_BAK_PRUNE), {"ids": stale})
                conceded += len(stale)
            await session.commit()
            legs_written += len(changed)
            entry["legs_written"] = len(changed)
        regraded += 1
        verdicts_changed += int(decision["verdict_changes"])
        ledger.append(entry)
        next_after_id = row.market_id

    exhausted = stopped_on is None and len(page) < scan
    result = {
        "issue": ISSUE,
        "apply": apply,
        "write_source": WRITE_SOURCE,
        "markets_examined": len(page),
        "in_scope": in_scope,
        "regraded": regraded,
        "verdicts_changed": verdicts_changed,
        "legs_written": legs_written,
        "conceded_to_another_writer": conceded,
        "skipped": sum(skip_reasons.values()),
        "skip_reasons": skip_reasons,
        "stopped_on": stopped_on,
        "exhausted": exhausted,
        "next_after_id": next_after_id,
        "backup_table": BAK_TABLE,
        "restore_command": restore_command(),
        "ledger": ledger[:100],
    }
    if apply and legs_written:
        logger.warning(
            "%s re-graded %s markets from the CLOB (%s verdicts flipped, %s legs). "
            "Backup in %s. D51 undo:\n%s",
            ISSUE, regraded, verdicts_changed, legs_written, BAK_TABLE,
            restore_command(),
        )
    return result


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put every backed-up leg back to the grade it carried before the repair."""
    if not (await session.execute(text(_BAK_EXISTS))).scalar_one():
        return {"issue": ISSUE, "terminal": "refused_no_backup",
                "backup_table": BAK_TABLE, "restored": 0}
    pending = (await session.execute(text(_RESTORE_PENDING))).scalar_one()
    backed_up = (
        await session.execute(text(f"SELECT count(*) FROM {BAK_TABLE}"))
    ).scalar_one()
    out = {"issue": ISSUE, "backup_table": BAK_TABLE,
           "backed_up_rows": int(backed_up), "pending": int(pending)}
    if not apply:
        return {**out, "terminal": "dry_run", "restored": 0}
    restored = (await session.execute(text(_RESTORE_SQL))).rowcount or 0
    await session.commit()
    logger.warning("%s restore: %s legs put back from %s", ISSUE, restored, BAK_TABLE)
    return {**out, "terminal": "restored", "restored": restored}
