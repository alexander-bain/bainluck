"""#5637 — the wrong-sport rows the classifier fix cannot reach on its own.

PILLAR: TRUTH. SHIP: the Redblacks game a reader finds by searching their club
stops being filed under basketball. Today `KXCFLTOTAL-26SEP12OTTTOR`
("Ottawa Redblacks vs Toronto Argonauts: Total Points", kickoff 2026-09-12
20:00Z) is stored `llm_sport_category='basketball'`, and it will stay
basketball forever without this rail.

WHY THE CLASSIFIER FIX IS NOT ENOUGH — CERT-2737'S FINDING, AND IT IS RIGHT
==========================================================================

#5637's ship added step 1b to `_categorize_kalshi_market`: an UNMAPPED Kalshi
series is sorted by the sport tag the venue itself publishes, instead of by name
rules that read club names which happen to be sport words. That stops the defect
being MINTED. It does not move a single row that already exists, because
`app/tasks/kalshi.py` writes the tag through::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

which is #1888's honest-empty rule: **an existing real tag is never
overwritten.** So the `other` rows converge on the next poll and the rows that
carry a WRONG SPORT — the ones a reader actually trips over — do not.

CERT-2737 blocked the ship for exactly this: "the poll's coalescing update
preserves every current non-`other` wrong sport, so the cited Redblacks ghost
remains visible". Measured on production 2026-09-12 15:5xZ, over the five
families #5637's venue census named:

    open, wrong, and frozen:   28 rows
      basketball  17   (14 × KXNFLFFPTS NFL "Fantasy Points", 3 × KXCFLTOTAL)
      tennis       9   (KXEFLL1* — AFC Wimbledon, an EFL League One club)
      baseball     1   (KXNWSLGAME — Houston vs Utah Royals)
      motorsports  1   (KXARGPREMDIVGAME — Huracan vs Racing Avellaneda)
    open and 'other':          74 rows  — these the poll converges by itself
    open and already right:    26 rows  — soccer, and the gate leaves them alone

Every one of the 28 is a game being played between 2026-09-12 and 2026-09-17.
This is not a historical tidy-up; it is the current weekend.

🔴 AND THE POLLER CANNOT UNDO IT. That same `nullif(..., 'other')` rail is what
makes this repair durable: once a row reads `football`, the coalesce keeps
`football`. The #1888 comment's warning that "a repair backfill run against
still-open rows is self-undoing" was written about a rail that OVERWROTE with a
fresh seasonal guess; under the shipped coalesce the opposite is true. No
tap-off interlock is needed here, which is why this rail — unlike #5621's — does
not refuse to run outside `bainluck-heavy`.

NO SECOND CLASSIFIER, AND NO SPORT VOCABULARY AT ALL
====================================================

This module contains no sport keywords, no regex over market names, no ticker
literals and no target category. It cannot: it does not know what it is going to
write until the venue tells it. It asks, in order, the exact functions the
Kalshi ingest path calls:

    result = await _resolve_series_tag_result(service, ticker)   # the venue
    target = series_tag_to_category(result.tag)                  # our maps
    verdict = _categorize_kalshi_market(name, None, ticker,
                                        series_tag=result.tag)   # the cascade

If this rail and the poller ever disagree, that is a bug in one of them, not a
policy difference. `test_the_rail_has_no_sport_vocabulary_of_its_own` pins the
absence, which is a stronger guard than the sibling rails can carry — their
`TARGET_CATEGORY` is a sport word by necessity, and this one has no target.

THE GATES — ALL OF THEM, AND WHAT EACH REFUSES
==============================================

A row is written only when every gate passes. Each refusal is counted under its
own name, because "examined 500, changed 3" with no breakdown is the shape that
hides a rail quietly doing nothing (gotcha #53).

1. `not_kalshi` — the predicate says kalshi; the gate re-asserts it. A row from
   another venue has no Kalshi series to ask about.
2. `mapped_ticker` — `sport_keys.py` already maps this ticker, so step 1 of the
   cascade is authoritative and names the LEAGUE, not merely the sport. No
   network call is made and nothing is written. This is the majority of the
   scanned population and it is the reason a pass is cheap.
3. `indeterminate` — the venue could not be asked (429 past its backoff, 5xx,
   timeout, transport error). **Counted, never written, and the row keeps its
   place**: the cursor does not advance past it. A transient failure is not a
   verdict (#36), and this rail exists because one was treated as one.
4. `no_usable_tag` — the venue answered and the answer is not a sport we model
   (`Olympics`, `Television`, `Table Tennis`), or the series carries no tag, or
   there is no such series (404). Falling through is the safe failure; a guess
   is not.
5. `cascade_disagrees` — the venue's tag resolves to X but the SHIPPED cascade,
   given that tag, does not answer X. Something above step 1b spoke (the IPO
   rule, say). **This is the gate that makes the predicate safe rather than
   merely narrow** — the same role gate 2 plays in the enumerated sibling rails.
6. `already_correct` — the stored value is what the venue says. Counted, not
   written. On a healthy repeat pass this is where the whole population lands.

WHY A PREDICATE AND NOT A FROZEN ID LIST
========================================

`repair_kalshi_senate_category` and `repair_kalshi_nhl_prop_category` enumerate
their rows, and the second says a third of these should trigger consolidation.
This is the third, and it deliberately does not enumerate — for a reason that is
about this defect rather than about taste:

**the population is still growing.** The classifier fix is merged but is not yet
running: it lives in a `HEAVY_TASKS` path, so it does nothing until
`bainluck-heavy` carries it (standing notice 48). Every CFL and NFL fixture
ingested between the measurement above and that release mints more wrong rows.
An id list measured today would be incomplete by the time it could be applied,
and silently so.

The enumerated rails freeze ids because their evidence is a name shape and their
population is closed. Here the evidence is the venue's own published tag, which
is strictly stronger than an id list — the NHL module says as much about its own
gate 2: "gate 2 is what makes the id list safe rather than merely short". This
rail keeps that gate and drops the list the gate was protecting.

BOUNDS, ORDER AND RESUMPTION
============================

Newest `commence_time` first: the ship is the games a reader opens this weekend.
Gotcha #41 warns that newest-first starves the old tail, and it would here, so
the tail is never silent — `remaining` is reported on every call and the pass
emits a `next_cursor` until `scan_exhausted` comes back true.

Two budgets, because there are two costs and they are not the same cost:

* `ROW_SCAN_CAP` bounds the DB read and the local classifier work.
* `VENUE_CALL_BUDGET` bounds the only expensive thing — one `/series/{ticker}`
  read per DISTINCT UNMAPPED series. Mapped tickers cost nothing, so a page of
  500 NFL rows spends zero budget. When the budget runs out the pass STOPS,
  reports `terminal="paused_venue_budget"`, and emits a cursor.

The cursor is a keyset on `(commence_time, id)`, never an offset: this repair
removes rows from its own population, so an offset would skip exactly as many
untouched rows as the last page fixed.

🔴 The cursor advances only past RESOLVED rows. A row that came back
`indeterminate` stops the scan where it stands, and `scan_exhausted` additionally
requires `indeterminate == 0`, so "finished" is unreachable while any retryable
row remains. This is CERT-666's correction to the Polymarket sibling, adopted
here rather than re-learned.

D51 — BACKUP AND RESTORE
========================

Every planned change carries its `before` value in the returned payload, on the
dry run as well as the apply, and `apply=True` logs the restore statement. The
undo is one statement per distinct before-value and it is exact, because the
planned ids are enumerated in the payload::

    UPDATE futures_markets SET llm_sport_category = 'basketball'
     WHERE id IN (<the ids reported as changed>);

WHAT IS NEVER WRITTEN
=====================

`llm_sport_category` and nothing else, by Core UPDATE (gotchas #4/#5). No price,
no outcome, no `is_winner`, no resolution field, no `category`, no event row.
"Settled means settled" is untouched: a taxonomy badge is not a result.

🔴 THE GHOST EVENT ROWS ARE NOT THIS RAIL'S. Correcting the market does not
delete the `basketball_other` EVENT the wrong category already caused to be
created (event 15308761 for the Redblacks row; 15307874 `tennis_other`;
15305038 `basketball_other`; 15308754 `baseball_other`; 15308950
`motorsport_other`). Those are duplicate event rows under ruling 048 and D35 /
standing notice 14 — lane1's `#2693`, filed not fixed here, and named in the
cert body so the ship is not read as claiming more than it does.

ATTENDED ONLY: never wire this to a beat. It is a terminating repair, not a
standing job.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, update

from app.models import FuturesMarket

logger = logging.getLogger(__name__)


#: Rows read and locally classified per call. The DB read is not the cost here
#: (the predicate is indexed on `source`/`status`), the venue is — see below.
ROW_SCAN_CAP = 500

#: Distinct UNMAPPED series a single pass may ask the venue about. This is the
#: real budget: a mapped ticker short-circuits with no call at all, so a page of
#: NFL rows spends none of it, while a page of unmapped families spends one per
#: series (never one per row — the resolver caches by series).
#:
#: Sized against the 30s router wall the Polymarket sibling measured: each call
#: is one GET with a 3-attempt backoff, so a budget of 40 leaves room for the
#: scan, the writes and the commit inside the wall.
VENUE_CALL_BUDGET = 40

#: Wall clock for the loop, leaving the post-loop UPDATE/commit and the
#: `remaining` count inside the router's 30s.
LOOP_DEADLINE_SECONDS = 18.0


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    🔴 ONE STATEMENT PER DISTINCT BEFORE-VALUE, not one statement for all rows —
    the mistake the senate sibling shipped first, where the before-value MAP was
    interpolated where a value belongs, producing a line that looks like a
    restore and is not one.

    This rail spans several before-values by construction (the measured 28 rows
    are basketball, tennis, baseball and motorsports at once), so the multi
    statement case is the normal case here, not a hypothetical.
    """
    by_before: dict[Optional[str], list[int]] = {}
    for row in planned:
        by_before.setdefault(row["before"], []).append(row["id"])

    lines = []
    for before, ids in sorted(by_before.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if before is None else f"'{before}'"
        lines.append(
            f"UPDATE futures_markets SET llm_sport_category = {value} "
            f"WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


def _population_predicate():
    """Open Kalshi rows carrying a real sport tag — the bug's own output.

    `other` is excluded because the poll already converges those through
    #1888's `nullif` door; including them would make the rail claim credit for
    work ingest does by itself. NULL is excluded for the same reason.
    """
    return and_(
        FuturesMarket.source == "kalshi",
        FuturesMarket.status == "open",
        FuturesMarket.llm_sport_category.isnot(None),
        FuturesMarket.llm_sport_category != "other",
    )


def _parse_after_date(raw: Any):
    """The dispatcher hands `after_date` over as a STRING; the column is a
    timestamp.

    Parsed here rather than left to Postgres' implicit cast so a malformed
    cursor fails on this line, naming itself, instead of deep inside the
    statement as a type error about a column the operator did not mention.
    """
    if raw is None or isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _cursor_for(row) -> dict[str, Any]:
    """The resume cursor that points just past `row`.

    The date half is emitted as an ISO STRING, not a `datetime`, so what the
    payload shows is exactly what a client can hand back as `?after_date=`. A
    cursor a reader has to reformat before it works is a cursor that gets
    reformatted wrongly.
    """
    commence = row.commence_time
    return {
        "after_date": commence.isoformat() if commence is not None else None,
        "after_id": row.id,
    }


def _keyset_after(cursor: Optional[dict[str, Any]]):
    """Keyset gate for `(commence_time DESC, id DESC)`, NULLS LAST.

    Gated on `after_id is not None`, never on a truthy `after_date` — the
    Polymarket sibling's Q496 defect 3 was exactly that, and it made the
    NULL-`commence_time` region unresumable, silently restarting at page one.

    So `after_id` alone is NOT a malformed half-keyset here: it is the cursor
    this rail itself emits once the walk reaches the NULL-`commence_time`
    region, where there is no date to carry. Both keys always travel in
    `next_cursor`; a client echoing it back cannot send a null date as a query
    param, and `after_id` alone is exactly what that echo looks like.
    """
    if not cursor or cursor.get("after_id") is None:
        return None

    after_id = cursor["after_id"]
    after_date = _parse_after_date(cursor.get("after_date"))

    if after_date is None:
        # Already inside the NULL region: only lower ids remain.
        return and_(
            FuturesMarket.commence_time.is_(None),
            FuturesMarket.id < after_id,
        )

    return or_(
        FuturesMarket.commence_time < after_date,
        FuturesMarket.commence_time.is_(None),
        and_(
            FuturesMarket.commence_time == after_date,
            FuturesMarket.id < after_id,
        ),
    )


async def repair(
    session,
    apply: bool = False,
    after_date: Optional[str] = None,
    after_id: Optional[int] = None,
    **_ignored,
) -> dict[str, Any]:
    """Plan (and optionally apply) the #5637 current-row convergence.

    Returns a payload complete enough to BE the D51 backup: every row it
    changed with its `before`, every refusal under a named reason, a runnable
    `restore_sql`, and a cursor if there is more to do.
    """
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.kalshi import (
        _categorize_kalshi_market,
        _resolve_series_tag_result,
        series_tag_to_category,
    )

    started = time.monotonic()
    cursor = {"after_date": after_date, "after_id": after_id}

    stmt = (
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.llm_sport_category,
            FuturesMarket.commence_time,
        )
        .where(_population_predicate())
        .order_by(
            FuturesMarket.commence_time.desc().nullslast(),
            FuturesMarket.id.desc(),
        )
        .limit(ROW_SCAN_CAP)
    )
    keyset = _keyset_after(cursor)
    if keyset is not None:
        stmt = stmt.where(keyset)

    rows = (await session.execute(stmt)).all()

    service = KalshiAPIService()
    planned: list[dict[str, Any]] = []
    refused: dict[str, int] = {}
    indeterminate_rows: list[dict[str, Any]] = []
    series_asked: set[str] = set()
    venue_calls = 0
    examined = 0
    stopped_at_unresolved = False
    stopped_reason: Optional[str] = None
    next_cursor: Optional[dict[str, Any]] = None

    def _refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    for row in rows:
        if time.monotonic() - started > LOOP_DEADLINE_SECONDS:
            stopped_reason = "deadline"
            break

        # 🔴 Metered on calls ACTUALLY MADE, and checked at the top of the loop
        # rather than in front of the resolve. The first cut guessed, before
        # resolving, whether a row would cost a request — and guessed wrong for
        # a series already in the resolver's cache, charging budget for a free
        # answer and stalling a drain that had spent nothing. The resolver is
        # the only thing that knows (cache hit, TTL suppression and mapped
        # ticker all answer without touching the venue), so it reports
        # `called` and this only counts.
        #
        # Stopping here is conservative: the rows after this one might all be
        # mapped and cost nothing. That is the right way to be wrong — the
        # cursor makes it resumable, and the alternative is a second guess at
        # what the resolver is about to do.
        if venue_calls >= VENUE_CALL_BUDGET:
            stopped_reason = "venue_budget"
            break

        if row.source != "kalshi":
            _refuse("not_kalshi")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        from app.services.kalshi_api import event_series_ticker

        series = event_series_ticker(row.external_id or "")
        result = await _resolve_series_tag_result(service, row.external_id)
        if result.called:
            venue_calls += 1
            if series:
                series_asked.add(series)

        if result.not_asked:
            # A mapped ticker (or no ticker at all): step 1 of the cascade is
            # authoritative and more specific than any tag. No call was made.
            _refuse("mapped_ticker")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        if not result.resolved:
            # 🔴 The cursor does NOT advance past this row, and exhaustion is
            # impossible while any of these remain. A transient venue failure is
            # not a verdict about the series (#36) — the reason this rail exists.
            _refuse("indeterminate")
            indeterminate_rows.append({"id": row.id, "series": series})
            examined += 1
            stopped_at_unresolved = True
            stopped_reason = "indeterminate"
            break

        target = series_tag_to_category(result.tag)
        if not target:
            _refuse("no_usable_tag")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        # THE GATE THAT MAKES THE PREDICATE SAFE. The venue's tag resolves to
        # `target`, but the shipped cascade is what ingest actually runs, and
        # something above step 1b may legitimately override it.
        verdict = _categorize_kalshi_market(
            row.name or "", None, row.external_id, series_tag=result.tag
        )
        if verdict != target:
            _refuse("cascade_disagrees")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        if row.llm_sport_category == target:
            _refuse("already_correct")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        planned.append(
            {
                "id": row.id,
                "name": row.name,
                "external_id": row.external_id,
                "before": row.llm_sport_category,
                "after": target,
                "venue_tag": result.tag,
            }
        )
        examined += 1
        next_cursor = _cursor_for(row)

    changed = 0
    drifted: list[dict[str, Any]] = []
    if apply and planned:
        # 🔴 COMPARE-AND-SET on the value the plan was made from, grouped by
        # (before, after) — a blind write by id would not notice the column
        # moving between the scan and the write (CERT-2394's finding).
        by_pair: dict[tuple[Optional[str], str], list[int]] = {}
        for item in planned:
            by_pair.setdefault((item["before"], item["after"]), []).append(item["id"])

        for (before, after), ids in by_pair.items():
            result_ = await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id.in_(ids))
                .where(
                    FuturesMarket.llm_sport_category.is_(None)
                    if before is None
                    else FuturesMarket.llm_sport_category == before
                )
                .values(llm_sport_category=after)
            )
            matched = result_.rowcount or 0
            changed += matched
            if matched != len(ids):
                # Not an error, and NOT silent: somebody moved a row mid-pass,
                # its plan is stale and it was left alone. "planned 9, changed 7"
                # with no explanation reads as the write half-failing.
                drifted.append(
                    {
                        "before": before,
                        "after": after,
                        "ids": sorted(ids),
                        "matched": matched,
                    }
                )

        await session.commit()
        logger.warning(
            "#5637 series-tag category repair applied: %s of %s planned rows "
            "(drifted: %s). D51 RESTORE:\n%s",
            changed,
            len(planned),
            drifted or "none",
            restore_sql(planned),
        )

    remaining = (
        await session.execute(
            select(func.count()).select_from(FuturesMarket).where(_population_predicate())
        )
    ).scalar_one()

    # Exhaustion is proven by the pager AND by there being nothing retryable.
    # A short page alone is not enough: CERT-666 found the sibling reporting
    # "finished" on a page whose last row had failed transiently.
    scan_exhausted = (
        len(rows) < ROW_SCAN_CAP
        and stopped_reason is None
        and refused.get("indeterminate", 0) == 0
    )

    if scan_exhausted:
        terminal = "complete"
        next_cursor = None
    elif stopped_at_unresolved:
        terminal = "paused_unresolved"
    elif stopped_reason == "venue_budget":
        terminal = "paused_venue_budget"
    elif stopped_reason == "deadline":
        terminal = "paused_deadline"
    elif not rows:
        terminal = "no_work"
    else:
        terminal = "changed" if apply else "dry_run"

    return {
        "examined": examined,
        "scanned_rows": len(rows),
        "planned": planned,
        "refused": refused,
        "indeterminate_rows": indeterminate_rows,
        # Distinct UNMAPPED series this pass actually asked the venue about.
        # Zero on a page of mapped tickers, which is the common case and is what
        # makes a full drain affordable.
        "series_asked": len(series_asked),
        # Requests actually issued. Equal to `series_asked` within one pass and
        # potentially larger across a drain (a series can be asked once, fail,
        # and be asked again after its suppression lapses) — the budget meters
        # THIS, because this is the cost.
        "venue_calls": venue_calls,
        "venue_call_budget": VENUE_CALL_BUDGET,
        "changed": changed,
        "drifted": drifted,
        # `remaining` counts the POPULATION, which legitimately contains rows the
        # gate refuses (`already_correct`, `mapped_ticker`). It is a floor with a
        # positive value, never a progress bar — exhaustion is `scan_exhausted`.
        "remaining_population_floor": remaining,
        "scan_exhausted": scan_exhausted,
        "stopped_at_unresolved": stopped_at_unresolved,
        "next_cursor": next_cursor,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log.
        "restore_sql": restore_sql(planned),
        "terminal": terminal,
    }
