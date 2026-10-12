"""#2351 — re-grade the MLB team-total legs the old one-leg writer got wrong.

## what a reader sees

`KXMLBTEAMTOTAL` markets ("Tampa Bay vs New York Y: Team Total") carry one leg
per club per line — "Boston over 2.5 runs scored", "Tampa Bay over 5.5 runs
scored" — and every leg is its own yes/no question. Until CERT-495 the
team-total branch of `_resolve_kalshi_spread_total_from_scores` graded the FIRST
leg it saw and wrote that one verdict to every sibling, so a page showed
"Boston over 7.5 runs — Won" on a night Boston scored 1. Measured 2026-08-30
with the shipped helper: 507 of 1,296 `game_score` legs contradicted their own
linked final score (789 correct, 0 unresolved). That count is a dated
observation, not this population: the walk below re-derives it.

## why the rows never healed

The writer is fixed (`_team_total_outcome_is_winner`, one leg in, one verdict
out). It cannot reach what it already wrote: `game_score` is not in
OVERWRITABLE_WINNER_SOURCES_SQL, and the candidate scan drops every market that
already holds a non-overwritable winner. So an all-True ladder stays all-True.

## population and verdict

Kalshi markets in the `KXMLBTEAMTOTAL` series (the ticker's FAMILY segment —
`split_part(external_id, '-', 1)`, never a substring, #5023) holding at least one
`game_score` leg. Each `game_score` leg is graded by the SHIPPED helper against
its market's linked event's final score, and is written only when the stored
verdict contradicts it. Correct siblings, legs another source graded, legs whose
club the helper cannot attribute and legs it cannot parse are left exactly as
they are and counted by name. Nothing is reset (gotcha #21): every write is a
recomputed verdict, and `resolution_source` stays `game_score`.

## when the score itself is not trusted

The whole market is SKIPPED, by name, when: it has no linked event; the event is
not final or has no score; `completed_at` precedes `commence_time` (gotcha #46,
a cross-event merge); the market is period-scoped; or any `api_settlement` leg
the venue graded on the SAME event, in this series or in `KXMLBTOTAL`,
disagrees with what the stored score implies for it. That last check is the
venue testifying about our score: a doubleheader whose game-2 final was written
onto game 1 (#8278, event 14788069) fails it, and a repair over that score would
replace one wrong verdict with another. Markets with no venue witness on the
event are still graded, and the ledger says ``witness: none``.

## pinned identity and drift

An apply is bound to a dry run the operator read: ``plan_hash`` is the content
address of the page's planned writes (outcome, market, event, prior, verdict and
the score both rest on). An apply recomputes the plan with the same
``after_id``/``limit``/``only_ids`` and REFUSES, writing nothing, unless the hash
matches. Each write then compare-and-sets on the same facts: the row still
carries `game_score`, the prior verdict and the same name, and its event still
carries the same score and clubs and is still final with a completion no earlier
than its start — the planner's own validity test, re-asked at the write. A row
that moved is left alone, counted as ``drift_refused``, and its backup row is
pruned.

## D51: backup and restore

Each leg is copied into :data:`BAK_TABLE` (prior grade + the grade this rail
wrote) in the same transaction as its write, and the write joins to that row, so
an unbacked leg cannot be written. The backup also records the ROW VERSION the
write produced (``xmin``) and the ``last_updated`` stamp it set. The undo is one statement::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/team-total-game-score-restore?apply=true"

It puts back only legs whose row is still the exact version this rail wrote:
``xmin`` changes on EVERY later UPDATE, including one that re-states the same
verdict and source, so a later writer is never undone — its leg is reported as
diverged and left alone. A table rewrite that re-mints tuples (dump/restore,
pg_repack) also moves ``xmin``; the restore then refuses rather than guesses.

ATTENDED ONLY: never wire this to a beat.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text

from app.tasks.backfill_winners import (
    _TEAM_TOTAL_UNRESOLVED,
    _market_period,
    _team_total_outcome_is_winner,
    _total_outcome_is_winner,
)

logger = logging.getLogger(__name__)

ISSUE = "#2351"
SERIES = "KXMLBTEAMTOTAL"
#: Series whose venue-graded legs on the same event can testify about the score.
#: Both are graded by the module's own helpers from the full-game score.
WITNESS_SERIES = (SERIES, "KXMLBTOTAL")
READ_SOURCE = "game_score"
WITNESS_SOURCE = "api_settlement"
BAK_TABLE = "bak_2351_team_total_game_score"

DEFAULT_SCAN = 200
MAX_SCAN = 1000
#: Wall clock per call. Below the router's 30 s with room for the commit.
WALL_BUDGET_S = 20.0

FINAL_STATUSES = ("completed", "closed")

#: Legs and witnesses kept per ledger entry; a longer list says it was cut.
_EVIDENCE_LIST_CAP = 16

# The btree range is on the (source, external_id) unique index; the family test
# is the exact predicate. Both bounds end in a letter, so the range holds under
# C and locale collations alike (a trailing '-' does not, #5023's lesson).
_PAGE_SQL = f"""
    SELECT fm.id AS market_id, fm.external_id AS ticker, fm.name AS market_name,
           fm.event_id, e.status AS event_status,
           e.home_team_name, e.away_team_name, e.home_score, e.away_score,
           e.commence_time, e.completed_at, e.score_source
    FROM futures_markets fm
    LEFT JOIN events e ON e.id = fm.event_id
    WHERE fm.source = 'kalshi'
      AND fm.external_id >= '{SERIES}'
      AND fm.external_id < '{SERIES[:-1]}{chr(ord(SERIES[-1]) + 1)}'
      AND split_part(fm.external_id, '-', 1) = '{SERIES}'
      AND fm.id > :after_id
      AND EXISTS (
          SELECT 1 FROM futures_outcomes o
          WHERE o.market_id = fm.id AND o.resolution_source = '{READ_SOURCE}'
      )
    ORDER BY fm.id
    LIMIT :scan
"""

_LEGS_SQL = """
    SELECT id, name, is_winner, resolution_source
    FROM futures_outcomes
    WHERE market_id = :mid
    ORDER BY id
"""

_WITNESS_SQL = f"""
    SELECT fo.id, fo.name, fo.is_winner, fm.external_id AS ticker,
           fm.name AS market_name
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.event_id = :eid
      AND fm.source = 'kalshi'
      AND split_part(fm.external_id, '-', 1) IN ({", ".join(f"'{s}'" for s in WITNESS_SERIES)})
      AND fo.resolution_source = '{WITNESS_SOURCE}'
      AND fo.is_winner IS NOT NULL
    ORDER BY fo.id
"""

_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
        outcome_id BIGINT PRIMARY KEY,
        market_id BIGINT NOT NULL,
        event_id BIGINT NOT NULL,
        prior_is_winner BOOLEAN,
        prior_resolution_source TEXT,
        written_is_winner BOOLEAN NOT NULL,
        home_score INTEGER NOT NULL,
        away_score INTEGER NOT NULL,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        written_xmin TEXT,
        written_last_updated TIMESTAMPTZ
    )
"""

#: The FIRST copy is the one that predates this rail, so a conflict keeps it.
#: Copied only while the row still holds the state the plan read.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, market_id, event_id, prior_is_winner,
                             prior_resolution_source, written_is_winner,
                             home_score, away_score)
    SELECT fo.id, fo.market_id, :eid, fo.is_winner, fo.resolution_source, :won,
           :hs, :as_
    FROM futures_outcomes fo
    WHERE fo.id = :oid
      AND fo.resolution_source = '{READ_SOURCE}'
      AND fo.is_winner IS NOT DISTINCT FROM :prior
    ON CONFLICT (outcome_id) DO NOTHING
    RETURNING outcome_id
"""

#: Compare-and-set on every fact the verdict rests on, including the planner's
#: event-validity test (final, and `completed_at >= commence_time` when both are
#: set). Joined to the backup, so an unbacked row has nothing to join to.
_APPLY_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = :won, last_updated = NOW()
    FROM {BAK_TABLE} b, futures_markets fm, events e
    WHERE fo.id = :oid
      AND b.outcome_id = fo.id
      AND fo.market_id = :mid
      AND fm.id = fo.market_id
      AND fm.event_id = :eid
      AND e.id = fm.event_id
      AND e.home_score = :hs
      AND e.away_score = :as_
      AND e.home_team_name IS NOT DISTINCT FROM :home
      AND e.away_team_name IS NOT DISTINCT FROM :away
      AND e.status IN {FINAL_STATUSES!r}
      AND NOT (e.commence_time IS NOT NULL AND e.completed_at IS NOT NULL
               AND e.completed_at < e.commence_time)
      AND fo.resolution_source = '{READ_SOURCE}'
      AND fo.is_winner IS NOT DISTINCT FROM :prior
      AND fo.name IS NOT DISTINCT FROM :name
    RETURNING fo.id, fo.xmin::text AS row_version, fo.last_updated
"""

#: Every successful write stamps its backup row with what was written and the
#: row version it produced. A backup row that pre-dated this call keeps its
#: prior — the FIRST copy is the one from before the rail.
_BAK_MARK_WRITTEN = f"""
    UPDATE {BAK_TABLE}
    SET written_is_winner = :won, home_score = :hs, away_score = :as_,
        written_xmin = :row_version, written_last_updated = :stamp
    WHERE outcome_id = :oid
"""

_BAK_PRUNE = f"DELETE FROM {BAK_TABLE} WHERE outcome_id = :oid"

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

_RESTORE_WHERE = f"""
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND b.written_xmin IS NOT NULL
      AND fo.xmin::text = b.written_xmin
      AND fo.resolution_source = '{READ_SOURCE}'
      AND fo.is_winner IS NOT DISTINCT FROM b.written_is_winner
      AND b.prior_is_winner IS DISTINCT FROM b.written_is_winner
"""
_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.prior_is_winner,
        resolution_source = b.prior_resolution_source,
        last_updated = NOW()
    {_RESTORE_WHERE}
"""
_RESTORE_CENSUS = f"""
    SELECT count(*) AS backed_up,
           count(*) FILTER (
               WHERE b.written_xmin IS NOT NULL
                 AND fo.xmin::text = b.written_xmin
                 AND fo.resolution_source = '{READ_SOURCE}'
                 AND fo.is_winner IS NOT DISTINCT FROM b.written_is_winner
                 AND b.prior_is_winner IS DISTINCT FROM b.written_is_winner
           ) AS restorable,
           count(*) FILTER (
               WHERE fo.id IS NOT NULL
                 AND fo.is_winner IS NOT DISTINCT FROM b.prior_is_winner
                 AND fo.resolution_source IS NOT DISTINCT FROM b.prior_resolution_source
           ) AS already_at_prior,
           count(*) FILTER (WHERE fo.id IS NULL) AS row_gone
    FROM {BAK_TABLE} b
    LEFT JOIN futures_outcomes fo ON fo.id = b.outcome_id
"""


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/team-total-game-score-restore?apply=true"'
    )


# ---------------------------------------------------------------------------
# pure decisions
# ---------------------------------------------------------------------------

def grade_leg(name, home, away, home_score, away_score) -> tuple[str, Optional[bool]]:
    """One leg through the SHIPPED grader: ``("graded", bool)``,
    ``("unresolved_identity", None)`` or ``("unparseable", None)``."""
    won = _team_total_outcome_is_winner(name, home, away, home_score, away_score)
    if won is _TEAM_TOTAL_UNRESOLVED:
        return "unresolved_identity", None
    if won is None:
        return "unparseable", None
    return "graded", bool(won)


def witness_expected(w: dict, home, away, home_score, away_score) -> Optional[bool]:
    """What the stored score says a venue-graded leg should read, or None when
    the leg cannot testify (a period market, or a name no helper reads)."""
    if _market_period(w.get("ticker"), w.get("market_name")) is not None:
        return None
    family = (w.get("ticker") or "").split("-", 1)[0].upper()
    if family == SERIES:
        status, won = grade_leg(w.get("name"), home, away, home_score, away_score)
        return won if status == "graded" else None
    return _total_outcome_is_winner(w.get("name"), home_score, away_score)


def decide_market(m: dict, legs: list[dict], witnesses: list[dict]) -> dict:
    """Plan one market: ``{"action": "skip", "reason": ...}`` or
    ``{"action": "plan", "writes": [...], "legs": [...], "witness": {...}}``.

    ``m`` carries the page row's fields; ``legs`` the market's outcomes
    (``id, name, is_winner, resolution_source``); ``witnesses`` the venue-graded
    legs on the same event.
    """
    if m.get("event_id") is None:
        return {"action": "skip", "reason": "no_linked_event"}
    if m.get("event_status") not in FINAL_STATUSES:
        return {"action": "skip", "reason": "event_not_final",
                "detail": m.get("event_status")}
    hs, as_ = m.get("home_score"), m.get("away_score")
    if hs is None or as_ is None:
        return {"action": "skip", "reason": "no_final_score"}
    started, ended = m.get("commence_time"), m.get("completed_at")
    if started is not None and ended is not None and ended < started:
        return {"action": "skip", "reason": "completed_before_commence"}
    if _market_period(m.get("ticker"), m.get("market_name")) is not None:
        return {"action": "skip", "reason": "period_market"}

    home, away = m.get("home_team_name"), m.get("away_team_name")
    contradictions = []
    checked = 0
    for w in witnesses:
        expected = witness_expected(w, home, away, hs, as_)
        if expected is None:
            continue
        checked += 1
        if bool(w["is_winner"]) != expected:
            contradictions.append({"id": w["id"], "name": w.get("name"),
                                   "venue": bool(w["is_winner"]),
                                   "score_implies": expected})
    if contradictions:
        return {"action": "skip", "reason": "score_contradicted_by_venue",
                "detail": contradictions[:_EVIDENCE_LIST_CAP]}

    graded_legs, writes = [], []
    for leg in legs:
        prior = leg.get("is_winner")
        if leg.get("resolution_source") != READ_SOURCE:
            state, verdict = "not_game_score", None
        elif prior is None:
            state, verdict = "prior_unknown", None
        else:
            status, verdict = grade_leg(leg.get("name"), home, away, hs, as_)
            if status != "graded":
                state = status
            elif bool(prior) == verdict:
                state = "already_correct"
            else:
                state = "contradicted"
                writes.append({"outcome_id": leg["id"], "name": leg.get("name"),
                               "prior": bool(prior), "verdict": verdict})
        graded_legs.append({"id": leg["id"], "name": leg.get("name"),
                            "source": leg.get("resolution_source"),
                            "prior": prior, "verdict": verdict, "state": state})
    return {
        "action": "plan",
        "writes": writes,
        "legs": graded_legs,
        "witness": {"checked": checked, "concordant": checked} if checked else "none",
    }


def plan_hash_for(planned: list[dict]) -> str:
    """Content address of a page's writes, over every fact an apply re-checks."""
    rows = sorted(
        (p["outcome_id"], p["market_id"], p["event_id"], p["prior"], p["verdict"],
         p["home_score"], p["away_score"], p["name"], p["home"], p["away"])
        for p in planned
    )
    body = json.dumps(rows, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def parse_only_ids(only_ids: Optional[str]) -> Optional[set[int]]:
    """``None`` = whole plan. An empty or non-integer list raises — it is
    neither extreme, and reading it as one would act on the wrong rows."""
    if only_ids is None:
        return None
    parts = [p.strip() for p in only_ids.split(",")]
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"only_ids must be comma-separated outcome ids, got {only_ids!r}")
    return {int(p) for p in parts}


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------

def _count(d: dict, key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n


async def _plan_page(session, cursor: int, scan: int, pinned: Optional[set[int]],
                     started: float) -> dict:
    page = (await session.execute(text(_PAGE_SQL), {"after_id": cursor, "scan": scan})).all()
    planned: list[dict] = []
    ledger: list[dict] = []
    market_skips: dict[str, int] = {}
    leg_states: dict[str, int] = {}
    witnessed = 0
    next_after_id = cursor
    stopped_on: Optional[str] = None
    examined = 0

    for row in page:
        if time.monotonic() - started > WALL_BUDGET_S:
            stopped_on = "wall_budget"
            break
        examined += 1
        m = dict(row._mapping)
        legs = [dict(r._mapping) for r in
                (await session.execute(text(_LEGS_SQL), {"mid": m["market_id"]})).all()]
        witnesses = []
        if m.get("event_id") is not None:
            witnesses = [dict(r._mapping) for r in
                         (await session.execute(text(_WITNESS_SQL),
                                                {"eid": m["event_id"]})).all()]
        decision = decide_market(m, legs, witnesses)
        next_after_id = m["market_id"]
        evidence = {
            "event_id": m.get("event_id"),
            "score": [m.get("home_score"), m.get("away_score")],
            "clubs": [m.get("home_team_name"), m.get("away_team_name")],
            "score_source": m.get("score_source"),
        }
        if decision["action"] == "skip":
            _count(market_skips, decision["reason"])
            ledger.append({"market_id": m["market_id"], "ticker": m.get("ticker"),
                           **decision, "evidence": evidence})
            continue
        if decision["witness"] != "none":
            witnessed += 1
        for leg in decision["legs"]:
            _count(leg_states, leg["state"])
        writes = [w for w in decision["writes"]
                  if pinned is None or w["outcome_id"] in pinned]
        withheld = len(decision["writes"]) - len(writes)
        if withheld:
            _count(leg_states, "withheld_by_only_ids", withheld)
        for w in writes:
            planned.append({
                **w,
                "market_id": m["market_id"], "event_id": m["event_id"],
                "home_score": m["home_score"], "away_score": m["away_score"],
                "home": m.get("home_team_name"), "away": m.get("away_team_name"),
            })
        unknown = [g for g in decision["legs"]
                   if g["state"] in ("unresolved_identity", "unparseable", "prior_unknown")]
        if writes or unknown:
            ledger.append({
                "market_id": m["market_id"], "ticker": m.get("ticker"),
                "name": m.get("market_name"), "action": "plan",
                "writes": len(writes), "witness": decision["witness"],
                "evidence": {**evidence,
                             "legs": decision["legs"][:_EVIDENCE_LIST_CAP],
                             "legs_total": len(decision["legs"])},
            })

    exhausted = stopped_on is None and len(page) < scan
    return {
        "planned": planned, "ledger": ledger, "market_skips": market_skips,
        "leg_states": leg_states, "witnessed": witnessed, "examined": examined,
        "next_after_id": next_after_id, "stopped_on": stopped_on,
        "exhausted": exhausted,
    }


async def _write_leg(session, p: dict) -> bool:
    params = {"oid": p["outcome_id"], "mid": p["market_id"], "eid": p["event_id"],
              "prior": p["prior"], "won": p["verdict"], "hs": p["home_score"],
              "as_": p["away_score"], "home": p["home"], "away": p["away"],
              "name": p["name"]}
    inserted = bool((await session.execute(text(_BAK_COPY), params)).all())
    hit = (await session.execute(text(_APPLY_SQL), params)).all()
    if hit:
        await session.execute(text(_BAK_MARK_WRITTEN), {
            **params, "row_version": hit[0].row_version, "stamp": hit[0].last_updated,
        })
    elif inserted:
        await session.execute(text(_BAK_PRUNE), params)
    return bool(hit)


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
    only_ids: Optional[str] = None,
    plan_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan (and with ``apply`` + the plan's own hash, write) one page.
    Dry-run by default."""
    started = time.monotonic()
    scan = max(1, min(int(limit or DEFAULT_SCAN), MAX_SCAN))
    cursor = int(after_id or 0)
    base = {"issue": ISSUE, "apply": apply, "series": SERIES,
            "after_id": cursor, "limit": scan, "backup_table": BAK_TABLE,
            "restore_command": restore_command()}
    try:
        pinned = parse_only_ids(only_ids)
    except ValueError as e:
        return {**base, "terminal": "refused_bad_only_ids", "detail": str(e),
                "legs_written": 0}
    if apply and not plan_hash:
        return {**base, "terminal": "refused_no_plan_hash", "legs_written": 0,
                "detail": "run the dry run with the same after_id/limit/only_ids "
                          "and pass its plan_hash"}

    await session.execute(text("SET LOCAL statement_timeout = '20s'"))
    plan = await _plan_page(session, cursor, scan, pinned, started)
    digest = plan_hash_for(plan["planned"])
    summary = {
        **base,
        "only_ids": sorted(pinned) if pinned is not None else None,
        "markets_examined": plan["examined"],
        "markets_with_writes": len({p["market_id"] for p in plan["planned"]}),
        "legs_contradicted": len(plan["planned"]),
        "leg_states": plan["leg_states"],
        "market_skips": plan["market_skips"],
        "markets_with_venue_witness": plan["witnessed"],
        "stopped_on": plan["stopped_on"],
        "exhausted": plan["exhausted"],
        "next_after_id": plan["next_after_id"],
        "plan_hash": digest,
        "legs_written": 0,
        "drift_refused": 0,
        "ledger": plan["ledger"][:100],
        "ledger_truncated": len(plan["ledger"]) > 100,
    }
    if not apply:
        return {**summary, "terminal": "dry_run"}
    if plan_hash != digest:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_drift",
                "detail": {"reviewed": plan_hash, "now": digest}}

    if plan["planned"]:
        await session.execute(text(_BAK_CREATE))
    written = drift = 0
    by_market: dict[int, list[dict]] = {}
    for p in plan["planned"]:
        by_market.setdefault(p["market_id"], []).append(p)
    for legs in by_market.values():
        for p in legs:
            if await _write_leg(session, p):
                written += 1
            else:
                drift += 1
        # One market, one transaction: its backup rows and writes land together.
        await session.commit()
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
    if written:
        logger.warning(
            "%s re-graded %s team-total legs from their linked final scores "
            "(%s refused on drift). Backup in %s. D51 undo:\n%s",
            ISSUE, written, drift, BAK_TABLE, restore_command(),
        )
    return {**summary, "terminal": "applied", "legs_written": written,
            "drift_refused": drift}


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put every leg this rail wrote back to the grade it carried before."""
    if not (await session.execute(text(_BAK_EXISTS))).scalar_one():
        return {"issue": ISSUE, "terminal": "refused_no_backup",
                "backup_table": BAK_TABLE, "restored": 0}
    c = (await session.execute(text(_RESTORE_CENSUS))).one()
    backed_up, restorable = int(c.backed_up), int(c.restorable)
    at_prior, gone = int(c.already_at_prior), int(c.row_gone)
    out = {"issue": ISSUE, "backup_table": BAK_TABLE, "backed_up_rows": backed_up,
           "restorable": restorable, "already_at_prior": at_prior,
           "row_gone": gone,
           # Graded by someone else since this rail wrote it: left alone.
           "diverged": backed_up - restorable - at_prior - gone}
    if not apply:
        return {**out, "terminal": "dry_run", "restored": 0}
    restored = (await session.execute(text(_RESTORE_SQL))).rowcount or 0
    await session.commit()
    logger.warning("%s restore: %s legs put back from %s", ISSUE, restored, BAK_TABLE)
    return {**out, "terminal": "restored", "restored": restored}
