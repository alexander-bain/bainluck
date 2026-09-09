"""#4229 — the Polymarket half: US-Senate events filed under hockey, which no poll will ever reach.

PILLAR: TRUTH. SHIP: the "How many senators will vote for Trump's Fed chair
nominee?" card stops being badged HOCKEY. That card IS #4229 — it is the
specimen the issue was filed about — and the Kalshi backfill that shipped at
``edf9fe13`` does not touch it.

WHY THIS EXISTS: A CLAIM ABOUT THE WRITE IS NOT A CLAIM ABOUT THE ROW
=====================================================================

``app/tasks/repair_kalshi_senate_category.py`` scoped itself to Kalshi and said
so in prose::

    Polymarket is the opposite — ``app/tasks/polymarket.py`` assigns
    unconditionally, so its four rows in this class retag on the next poll and
    are deliberately NOT in scope here.

CERT-2376 quoted that sentence as covering the whole twelve-row cohort. **The
first clause is true and the second does not follow.** The poller's
``update_set`` really does write ``llm_sport_category`` unconditionally (any
non-``other`` value overwrites) — but a writer only rewrites a row it is
handed, and discovery never hands it these.

Falsified on production 2026-09-09 by three methods that share no assumption:

  * ``updated_at`` on ``114420`` is **2026-05-17** and on ``34676409`` is
    **2026-06-18** — 115 and 83 days. The poll stamps ``updated_at: func.now()``
    on every upsert, so these rows have not been upserted since.
  * Both events' venue ``startDate`` (2026-01-13, 2026-06-10) is months past.
  * The discovery pass's own live window, read from Gamma under its 2,000-event
    cap: offsets 0–99 span ``14:38Z→15:13Z`` and offsets 1900–1999 span
    ``04:38Z→05:03Z``. **The whole scan is 10.6 hours wide.** Neither event is
    inside it, and nothing scheduled will put them there.

This is #4000's own correction repeated: **a discovery pass ordered newest-first
has a TIME HORIZON, not a coverage guarantee.** Two of the four Polymarket rows
in the original filing *did* self-heal, because they were inside the horizon —
which is exactly why the claim survived a builder and a grader. A claim that is
true for the reachable half reads as true right up until you census the rest.

THE EVIDENCE GATE IS THE VENUE, NOT A CLASSIFIER
================================================

The Kalshi sibling gates on the shipped *name* classifier, because Kalshi's
ingest has nothing else. Polymarket does: the event carries **tags**, and the
tags are the strongest evidence there is. ``162276`` is tagged
``['Trump', 'Politics', 'Fed', 'Economy', 'Fed Chair']`` and ``578421``
``['Trump', 'Todd Blanche', 'Politics', 'Senate', 'attorney general']``.

So this rail re-asks Gamma and runs the shipped ingest cascade over the reply,
via ``repair_polymarket_sport_category.classify_event_payload`` — the same
function, not a copy. It contains **no sport rules of its own**: no keyword, no
regex over a market name, and no category literal at all. If the poller's
cascade changes, this rail changes with it and cannot drift.
``test_repair_polymarket_senate_carries_no_rules_of_its_own`` fails the build if
that stops being true.

That gate is stronger than an id list in the way that matters: put a wrong id in
:data:`SENATE_EVENT_IDS` and the rail writes the venue's answer for *that*
event, which is by construction the right answer for it — not a relabelled
hockey game. The controls below prove the gate discriminates rather than
asserting it.

WHY IT IS ID-BOUND AS WELL, AND WHY THE POPULATION IS SIX AND NOT SEVENTY-FOUR
==============================================================================

The sibling rail (``polymarket-sport-category``) pages a whole suspect CATEGORY.
That shape does not work here: the suspect category would be ``hockey``, which
is tens of thousands of real NHL rows, one venue call each, to move six events.
A drain whose expected yield is ~0.008% is not a drain.

So the bound is enumerated. It was measured, not guessed — and measured against
the VENUE (standing notice 26), not against our own mirror:

  1. Every Polymarket row whose name matches ``senat*`` and that is stored under
     a sport category: **267 rows / 74 distinct events** (all statuses, not just
     open — the ``senat*`` class is 1,264 rows and the open slice is a small
     minority of it).
  2. All 74 events re-asked at ``gamma-api.polymarket.com/events/{id}`` and run
     through the shipped cascade, 2026-09-09.

  =====================  ======  ==============================================
  cascade verdict        events  meaning
  =====================  ======  ==============================================
  ``hockey``                 68  the venue confirms it — Ottawa/Belleville, real
  ``politics``                6  the six below
  404 / 429 / ``other``       0  no non-verdicts in the whole census
  =====================  ======  ==============================================

**Sixty-eight of seventy-four are genuinely hockey and this rail must leave every
one of them alone.** They are not an exclusion list — they were never candidates,
because the gate refused them on the venue's own answer.

🔴 THE ISSUE NAMED TWO ROWS; THE RULE MATCHES SIX EVENTS
========================================================

#4229 is about the two OPEN rows. Censusing what the *rule* matches rather than
what the *defect* occupies — the discipline #4253 was nearly shipped without —
turned up four more, all ``resolved``, all genuinely political, none of them
reachable by a poll either:

    3230    How many Senators will vote to convict Donald Trump on incitement…
    16560   How many Senators vote to confirm Tulsi Gabbard?
    16748   Which Senators will vote to confirm Tulsi Gabbard?
    101980  How many Republican Senators not running in 2026?

They are included deliberately. Moving a resolved row's ``llm_sport_category``
is safe in the way #4253's suppression rule was NOT safe on resolved markets:
this column is a taxonomy badge, never a result. No price, outcome,
``is_winner``, ``settled_at`` or resolution field is read or written here, so
"settled means settled" is untouched — a resolved political market simply stops
being filed under hockey on category pages and in search over history.

DISCLOSED AND OUT OF SCOPE
==========================

* ``34496171`` — "Will Blake Masters win the 2022 Arizona Republican Senate
  nomination?" — is stored ``golf``, not ``hockey``, so it is outside this
  bound's census. One resolved 2022 row; it belongs to #4365.
* Four AHL "Belleville Senators vs. Hershey Bears" rows are classified
  ``football`` by the name-only branch (``Bears`` → NFL). Stored ``hockey``,
  which is correct, and the venue tags agree — so this rail refuses them and the
  defect is latent. Filed separately; it is not a #4229 symptom.

WHAT IS NEVER WRITTEN
=====================

``llm_sport_category`` only, by Core UPDATE (gotchas #4/#5), compare-and-set on
the value we read, so a concurrent re-ingest is never clobbered.

Not ``category``, and that is a measured decision rather than caution: the
poller's ``update_set`` in ``app/tasks/polymarket.py`` does **not** contain
``category`` — it is written on INSERT and never again. Writing it here would
make this rail do something the ingest path never does, on rows whose whole
problem is that ingest cannot reach them. ``578421`` therefore keeps
``category='championship'``; that is a pre-existing INSERT-time value, disclosed
rather than quietly corrected.

Nothing at all is written when the venue does not answer clearly, each with its
own named count rather than one silent success (gotchas #36, #53):

  * 429/5xx/timeout → ``indeterminate``. A transient failure is not a verdict.
  * 404 → ``not_at_venue``.
  * the cascade returns ``None``/``"other"`` → ``refused_other``, the poller's
    own honest-empty guard.
  * the cascade agrees with what is stored → ``unchanged``. On this bound that
    means the census went stale and the rail is declining, which is the
    behaviour to want.

D51 — BACKUP AND RESTORE
========================

Every planned row carries its ``before`` value in the returned payload, on the
dry run as well as the apply, and the apply logs the restore. The undo is one
statement per distinct before-value, exact because the rows are enumerated by
id at plan time. There is no backup table: fifteen rows of one column is one
statement, and a table would be more moving parts rather than more safety.

ATTENDED ONLY: never wire this to a beat. It is a bounded, terminating repair
over six enumerated events, not a standing job.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

#: The enumerated bound: Polymarket EVENT ids, as they appear in
#: ``market_metadata->>'polymarket_event_id'``. Measured on production
#: 2026-09-09 (see the census in the module docstring) and frozen.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THESE EVENTS ARE WRONG. The claim
#: that an event is mis-filed is made by the VENUE, per event, at run time.
SENATE_EVENT_IDS: tuple[str, ...] = (
    "3230",    # How many Senators will vote to convict Donald Trump on incitement by March 1?
    "16560",   # How many Senators vote to confirm Tulsi Gabbard?
    "16748",   # Which Senators will vote to confirm Tulsi Gabbard?
    "101980",  # How many Republican Senators not running in 2026?
    "162276",  # How many senators will vote for Trump's Fed chair nominee?  <- #4229's card
    "578421",  # How many senators will vote for Todd Blanche as Attorney General?
)

#: Pause between venue calls. Gamma's limiter is real; the sibling rail uses the
#: same figure and this bound is six events, so the whole pass is ~4s.
VENUE_PAUSE = 0.35

#: Per-venue-call timeout, matching the sibling rail. Six events at eight
#: seconds is inside the 30s router wall even in the pathological case, which is
#: why this rail needs no keyset cursor: its population cannot outgrow one call.
FETCH_TIMEOUT_SECONDS = 8

#: Bound on each UPDATE. These rows are also written by the ordinary poller, so
#: a row lock is possible even though this population is the one the poller does
#: not reach — an operator running this during a poll that HAS found a sibling
#: row of the same event should get a named failure, not a router H12.
WRITE_TIMEOUT_MS = 2000


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    One statement per distinct before-value, never one statement for all rows:
    the Kalshi sibling shipped a first version that interpolated the before-value
    *map* where the value belongs, which is not valid SQL. A restore line that
    looks runnable and is not is worse than none, because D51 is granted on the
    strength of it.

    Today every row is ``hockey``, so this emits one statement; if the bound ever
    spans two prior categories it emits two, and neither is wrong.
    """
    by_before: dict[Optional[str], list[int]] = {}
    for row in planned:
        by_before.setdefault(row["before"], []).append(int(row["id"]))

    lines = []
    for before, ids in sorted(by_before.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if before is None else f"'{before}'"
        lines.append(
            f"UPDATE futures_markets SET llm_sport_category = {value} "
            f"WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


async def _fetch_event(client: httpx.AsyncClient, event_id: str):
    """Return ``(status, payload)`` — ok / not_at_venue / indeterminate.

    Delegates to the sibling rail's fetch so the 404-vs-429 discipline (#36)
    exists in exactly one place. A catch-all that returned ``None`` for both
    would write a category verdict on a rate limit.
    """
    from app.tasks.repair_polymarket_sport_category import _fetch_event as _sibling_fetch

    return await _sibling_fetch(client, event_id)


async def repair(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """Plan (and optionally apply) the #4229 Polymarket category correction.

    Dry-run by default. Returns a payload complete enough to BE the D51 backup:
    every event considered, the venue's verdict, every row that would move with
    its stored value, and a named reason for each refusal.
    """
    from app.tasks.repair_polymarket_sport_category import classify_event_payload

    counts = {
        "events_examined": 0,
        "changed": 0,
        "unchanged": 0,
        "refused_other": 0,
        "not_at_venue": 0,
        "indeterminate": 0,
        "write_failed": 0,
        "rows_written": 0,
    }
    planned: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    missing_ids: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for event_id in SENATE_EVENT_IDS:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT fm.id, fm.name, fm.status, fm.llm_sport_category
                        FROM futures_markets fm
                        WHERE fm.source = 'polymarket'
                          AND fm.market_metadata->>'polymarket_event_id' = :eid
                        ORDER BY fm.id
                        """
                    ),
                    {"eid": event_id},
                )
            ).all()

            if not rows:
                # An id in the bound that names no row. Reported by NAME rather
                # than silently skipped: it means the census this list came from
                # has gone stale, and an operator should know that before
                # reading a small `changed` as success.
                missing_ids.append(event_id)
                continue

            counts["events_examined"] += 1

            status, payload = await _fetch_event(client, event_id)
            await asyncio.sleep(VENUE_PAUSE)

            record = {
                "event_id": event_id,
                "title": rows[0].name,
                "rows": len(rows),
                "stored": sorted({r.llm_sport_category for r in rows}, key=str),
            }

            if status != "ok" or payload is None:
                counts[status] += 1
                refused.append({**record, "reason": status})
                continue

            _category, llm = classify_event_payload(payload)
            record["venue_verdict"] = llm
            verdicts.append(record)

            if not llm or llm == "other":
                # The poller's own honest-empty guard: never overwrite a real
                # value with the "other" default.
                counts["refused_other"] += 1
                refused.append({**record, "reason": "refused_other"})
                continue

            movable = [r for r in rows if r.llm_sport_category != llm]
            if not movable:
                # THE GATE DECLINING. On this bound it means the venue agrees
                # with what is stored, so there is nothing to correct.
                counts["unchanged"] += 1
                refused.append({**record, "reason": "venue_agrees"})
                continue

            counts["changed"] += 1
            event_plan = [
                {
                    "id": int(r.id),
                    "event_id": event_id,
                    "name": r.name,
                    "status": r.status,
                    "before": r.llm_sport_category,
                    "after": llm,
                }
                for r in movable
            ]
            planned.extend(event_plan)

            if not apply:
                continue

            # Core UPDATE, never ORM attribute assignment (gotchas #4/#5).
            # Compare-and-set on the value we read, so a re-ingest that landed
            # between the SELECT and here is never clobbered by a verdict
            # computed before it.
            try:
                await session.execute(
                    text(f"SET LOCAL statement_timeout = {WRITE_TIMEOUT_MS}")
                )
                for before in sorted({p["before"] for p in event_plan}, key=str):
                    ids = [p["id"] for p in event_plan if p["before"] == before]
                    result = await session.execute(
                        text(
                            """
                            UPDATE futures_markets
                            SET llm_sport_category = :llm,
                                updated_at = NOW()
                            WHERE id = ANY(:ids)
                              AND llm_sport_category IS NOT DISTINCT FROM :before
                            """
                        ),
                        {"llm": llm, "ids": ids, "before": before},
                    )
                    counts["rows_written"] += result.rowcount or 0
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — a blocked write is not a verdict
                # A statement timeout aborts the whole TRANSACTION, so the
                # session is unusable until it is rolled back. Events committed
                # before this one are durable and stay counted.
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**record, "reason": "write_failed"})
                logger.warning(
                    "repair_polymarket_senate_category: the UPDATE for event %s "
                    "did not land (%s: %s); rows already committed are unaffected",
                    event_id,
                    type(exc).__name__,
                    exc,
                )

    if apply and counts["rows_written"]:
        logger.warning(
            "#4229 Polymarket repair applied: %s rows. D51 RESTORE:\n%s",
            counts["rows_written"],
            restore_sql(planned),
        )

    # Gotcha #53: a pass that examined events and wrote nothing says so in a
    # named terminal rather than leaving zeros for a reader to interpret.
    if apply:
        terminal = "changed" if counts["rows_written"] else "no_rows_written"
    else:
        terminal = "dry_run"

    return {
        "repair": "polymarket-senate-category",
        "bound": list(SENATE_EVENT_IDS),
        "counts": counts,
        "planned": planned,
        "refused": refused,
        "verdicts": verdicts,
        "missing_ids": missing_ids,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log
        # line they have to go and find.
        "restore_sql": restore_sql(planned),
        "terminal": terminal,
    }
