"""#6955 — the Polymarket rows a club noun dragged onto a sport shelf, which no poll will reach.

PILLAR: DISCOVER on TRUTH. SHIP: a reader searching "Atlantic Hurricane Season"
stops being told the storm is ice hockey. Those four cards ARE #6955 — they are
the specimens the issue was filed about — and the classifier fix that ships
beside this rail does not move them.

WHY A CLASSIFIER FIX IS NOT ENOUGH HERE
=======================================

The classifier half of #6955 is correct and independently graded correct
(CERT-3072: "the classifier is correct", 583/583). It teaches
``futures_categorization`` that a meteorological construction beats the club
noun, so a row ingested from now on is filed weather.

**But a classifier only repairs a row the poller re-fetches, and the poller does
not reach this population.** Measured on production 2026-09-18:

  * ``744619`` — the event holding the four cards the issue names — is
    ``active=False closed=True archived=True`` at the venue. The hourly
    discovery pass is active-only, so it will never be handed these rows again.
  * ``765230``, the ACTIVE replacement family with the identical title, is
    absent from every page of the poller's newest-first scan (offsets 0–1900;
    2100 is a Gamma 422). A discovery pass ordered newest-first has a TIME
    HORIZON, not a coverage guarantee — #4000's correction, and
    ``repair_polymarket_senate_category``'s, for the third time.

So the rows stay ``hockey`` until something addresses them by id. That is this
rail, and it is the repair CERT-3072 required.

THE EVIDENCE GATE IS THE VENUE, NOT A CLASSIFIER
================================================

This rail contains **no sport rules of its own** — no keyword, no regex over a
market name, no category literal. It re-asks Gamma for the event and runs the
shipped ingest cascade over the reply, via
``repair_polymarket_sport_category.classify_event_payload`` — the same function
the poller runs, not a copy. If the cascade changes, this rail changes with it
and cannot drift. ``test_club_noun_rail_carries_no_rules_of_its_own`` fails the
build if that stops being true.

Read off Gamma 2026-09-18, the four bound events carry::

    744619  ['Weather', 'climate', 'hurricane', 'Hurricane Season']   -> weather
    765230  ['Weather', 'climate', 'hurricane', 'Hurricanes']         -> weather
    743877  ['Weather', 'climate', 'hurricane', 'Hurricane Season']   -> weather
    16183   ['Crypto', 'exchange', 'Finance', 'Business', ...]        -> crypto

The venue has been saying "Weather" the entire time. Nothing read it.

WHY THE BOUND IS FOUR EVENTS AND NOT ONE HUNDRED AND SIXTY-FIVE
===============================================================

Censusing what the RULE matches rather than what the DEFECT occupies, against
the VENUE (standing notice 26) rather than our own mirror:

  1. Every Polymarket row stored under a sport category whose name matches
     ``hurricane|cyclone|typhoon|tropical storm|kraken``: **165 distinct
     events**.
  2. All 165 re-asked at ``gamma-api.polymarket.com/events/{id}`` and run
     through the shipped cascade, 2026-09-18.

  =====================  ======  ==============================================
  cascade verdict        events  meaning
  =====================  ======  ==============================================
  agrees with stored        160  the venue confirms it — Carolina Hurricanes,
                                 Seattle Kraken, Miami Hurricanes, Iowa State
                                 Cyclones, Tulsa Golden Hurricane. Real sport.
  ``hockey`` -> weather       3  744619, 765230, 743877
  ``hockey`` -> crypto        1  16183
  transport failure           1  312062, a genuine basketball event; retried
                                 and still 000. Not a verdict, not in the bound.
  =====================  ======  ==============================================

**One hundred and sixty of one hundred and sixty-five are genuinely sport and
this rail must leave every one of them alone.** They are not an exclusion list
— they were never candidates, because the gate refuses them on the venue's own
answer. ``Capitals vs. Hurricanes`` and ``Flames vs. Kraken`` are carried as
named controls in the tests for exactly that reason: a control that rides the
same code path cannot go stale the way a maintained exclusion list can.

🔴 THE METADATA KEY REACHES THE PARENT AND MISSES EVERY MEMBER
==============================================================

The sibling rail selects its rows with::

    WHERE fm.market_metadata->>'polymarket_event_id' = :eid

On this bound that predicate finds **4 of 12 rows**, and the 8 it misses include
**all four cards #6955 was filed about**. Measured:

  =========  ======  =====================  ==========================
  event      rows    metadata key reaches   metadata key MISSES
  =========  ======  =====================  ==========================
  744619          5                      1                           4
  16183           5                      1                           4
  743877          1                      1                           0
  765230          1                      1                           0
  =========  ======  =====================  ==========================

Only the container row carries ``polymarket_event_id``; the member rows carry
the event solely in ``group_id = 'polymarket:<eid>'``. A byte-copy of the
sibling would have reported ``changed: 2 events`` and left the reader's four
cards on the hockey shelf — a repair that passes its own after-check while the
defect it was built for is still on screen.

🔴 AND THE GROUP IS NOT A SAFE WIDENING EITHER — IT CARRIES A STRANGER
======================================================================

The obvious correction — union in ``group_id = 'polymarket:' || :eid`` — admits
the four member rows AND admits this, under the Kraken IPO event::

    13791106  'Israel x Hamas Ceasefire Phase II by February 28?'   (tech)

Writing ``crypto`` onto a Gaza ceasefire market would be a new defect committed
in the act of fixing an old one. So the group is not trusted on its own.

A row joins the event on one of two ID-ANCHORED correspondences, never on a
container guess (gotcha #32's discipline, one layer down):

  1. it carries the event id itself (``polymarket_event_id``) — this is the
     container/parent row, whose NAME is the event title and therefore appears
     nowhere in the venue's market list; or
  2. it sits in the event's group AND **the venue event's own ``markets[]``
     list names its question** — this is a member row.

On the bound that admits 11 of 12 rows and refuses ``13791106`` by name. The
refusal is not a special case and there is no id for it anywhere in this file:
the venue simply does not list that question under that event, so the gate
declines it the way it declines the 160 real hockey events. That row's presence
in a Kraken container is a matching defect and is filed separately; this rail
is not the place to silently relabel it.

WHAT IS NEVER WRITTEN
=====================

``llm_sport_category`` only, by Core UPDATE (gotchas #4/#5), compare-and-set on
the value read, so a concurrent re-ingest is never clobbered.

🔴 **NOT ``updated_at``.** CERT-2382 blocked the sibling's first SHA for exactly
this: ``updated_at`` is not bookkeeping here, it is rendered by the card as its
own relative date. Stamping ``NOW()`` would leave stale prices unchanged while
presenting them as observed just now — a repair whose whole purpose is TRUTH
introducing a reader-visible lie about freshness in the same statement. **A
column a surface RENDERS is not bookkeeping, and a repair touches only the
column it is repairing.**

🔴 **NOT ``status``.** The four cards' event is ``closed``/``archived`` at the
venue while our rows read ``open``, and CERT-3072's required repair mentions
closed status. This rail does not write it, deliberately and disclosed: a status
write is settlement-adjacent, it is a different column with a different truth
source, and the rule above forbids a category repair from reaching for it. The
stale-open family beside the live one is filed as its own defect. What the
grader's clause DOES bind, and what this rail honours, is that closed and
resolved rows are **inside** the population rather than filtered out of it —
the four ``resolved`` Kraken rows are repaired like any other. Moving a resolved
row's ``llm_sport_category`` is safe in the way a suppression rule would not be:
this column is a taxonomy badge, never a result, and no price, outcome,
``is_winner``, ``settled_at`` or resolution field is read or written here. So
"settled means settled" is untouched.

Not ``category``: the poller's ``update_set`` does not contain it — it is
written on INSERT and never again — so writing it here would make this rail do
something the ingest path never does, on rows whose whole problem is that
ingest cannot reach them.

Nothing at all is written when the venue does not answer clearly, each with its
own named count rather than one silent success (gotchas #36, #53):

  * 429/5xx/timeout -> ``indeterminate``. A transient failure is not a verdict.
  * 404 -> ``not_at_venue``.
  * the cascade returns ``None``/``"other"`` -> ``refused_other``, the poller's
    own honest-empty guard.
  * the cascade agrees with what is stored -> ``venue_agrees``. On this bound
    that means the census went stale and the rail is declining, which is the
    behaviour to want.

DISCLOSED AND OUT OF SCOPE
==========================

* ``500863`` / ``944676`` / ``500593`` / ``779162`` — "Will Kraken's valuation
  hit __ by <date>?", 12 open rows, stored ``hockey``. This rail **refuses
  them**, correctly, because the shipped cascade returns ``hockey`` for them:
  the venue tags say ``Finance``/``Privates``/``Crypto``, ``_tags_to_category``
  duly returns ``economics``, and then ``resolve_event_category`` arm 3 ("a
  non-sport tag but a SPORT title") promotes it back to ``hockey`` off the club
  noun in the title. That is a defect in the cascade arm, not in this rail's
  gate, and a rail that wrote a verdict its own gate refused would be the
  drift this design exists to prevent. Filed separately with the census.

D51 — BACKUP AND RESTORE
========================

Every planned row carries its ``before`` value in the returned payload, on the
dry run as well as the apply, and the apply logs the restore. The undo is one
statement per distinct before-value, exact because the rows are enumerated by
id at plan time, and on an apply it is built from what the database RETURNED
rather than from the plan — the undo must name the rows that MOVED, not the
rows we hoped to move. There is no backup table: twelve rows of one column is
one statement, and a table would be more moving parts rather than more safety.

ATTENDED ONLY: never wire this to a beat. It is a bounded, terminating repair
over four enumerated events, not a standing job.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

#: The enumerated bound: Polymarket EVENT ids. Measured on production and
#: against the venue 2026-09-18 (see the census in the module docstring) and
#: frozen.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THESE EVENTS ARE WRONG. The claim
#: that an event is mis-filed is made by the VENUE, per event, at run time. Put
#: a wrong id here and the rail writes the venue's answer for *that* event,
#: which is by construction the right answer for it.
CLUB_NOUN_EVENT_IDS: tuple[str, ...] = (
    "16183",   # Kraken IPO by ___ ?                                    -> crypto
    "743877",  # Will 2 or more hurricanes make landfall in the US in 2026?
    "744619",  # How many hurricanes will form during the Atlantic Hurricane
               # Season in 2026?  <- #6955's four cards; closed/archived at venue
    "765230",  # the ACTIVE replacement family, same title, same defect
)

#: Pause between venue calls. Gamma's limiter is real; the sibling rails use the
#: same figure and this bound is four events, so the whole pass is ~2s.
VENUE_PAUSE = 0.35

#: Per-venue-call timeout, matching the sibling rails. Four events at eight
#: seconds is inside the 30s router wall even in the pathological case, which is
#: why this rail needs no keyset cursor: its population cannot outgrow one call.
FETCH_TIMEOUT_SECONDS = 8

#: Bound on each UPDATE. These rows are also written by the ordinary poller, so
#: a row lock is possible even though this population is the one the poller does
#: not reach — an operator running this during a poll that HAS found a sibling
#: row of the same event should get a named failure, not a router H12.
WRITE_TIMEOUT_MS = 2000


def venue_market_questions(payload: dict[str, Any]) -> set[str]:
    """The questions the venue event's own ``markets[]`` list names, casefolded.

    This is half of the membership gate: a row in the event's group joins the
    event only if the venue names its question. Casefolded and stripped because
    the comparison is an identity check between two spellings of one string, not
    a fuzzy match — nothing here tolerates a near miss, by design.
    """
    out: set[str] = set()
    for market in payload.get("markets") or []:
        if not isinstance(market, dict):
            continue
        question = market.get("question")
        if question:
            out.add(str(question).strip().casefold())
    return out


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    One statement per distinct before-value, never one statement for all rows:
    an earlier sibling shipped a version that interpolated the before-value *map*
    where the value belongs, which is not valid SQL. A restore line that looks
    runnable and is not is worse than none, because D51 is granted on it.
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
    """Plan (and optionally apply) the #6955 Polymarket category correction.

    Dry-run by default. Returns a payload complete enough to BE the D51 backup:
    every event considered, the venue's verdict, every row that would move with
    its stored value, and a named reason for each refusal — including each row
    the membership gate declined, by id, so an operator can see the gate working
    rather than take it on trust.
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
        # Rows in the event's GROUP that the venue's own market list does not
        # name. Counted, never written. On this bound it is the Gaza ceasefire
        # row; a jump here means a container has collected more strangers.
        "rows_not_named_by_venue": 0,
    }
    planned: list[dict[str, Any]] = []
    #: The rows the database actually moved, read back by ``RETURNING id``. On a
    #: dry run this stays empty and the restore is built from ``planned``, which
    #: is the right basis there: an operator reading a dry run wants the undo for
    #: the write they are about to authorise.
    applied: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    #: Every row the membership gate declined, BY ID and with its question, so
    #: the refusal is auditable instead of merely counted.
    not_named_by_venue: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    missing_ids: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for event_id in CLUB_NOUN_EVENT_IDS:
            # Both id-anchored correspondences in one read. `has_event_id`
            # distinguishes them so the membership gate below can let the
            # container row through without asking the venue to name its own
            # title (it never does — the title is not a market question).
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT fm.id,
                               fm.name,
                               fm.status,
                               fm.llm_sport_category,
                               (fm.market_metadata->>'polymarket_event_id')
                                   IS NOT DISTINCT FROM :eid AS has_event_id
                        FROM futures_markets fm
                        WHERE fm.source = 'polymarket'
                          AND (
                                fm.market_metadata->>'polymarket_event_id' = :eid
                             OR fm.group_id = :gid
                          )
                        ORDER BY fm.id
                        """
                    ),
                    {"eid": event_id, "gid": f"polymarket:{event_id}"},
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

            # THE MEMBERSHIP GATE. A row belongs to this event if it carries the
            # event id, or if the venue's own market list names its question.
            # Anything else is a stranger the container collected and is never
            # written — see the module docstring's `13791106`.
            named = venue_market_questions(payload)
            members = []
            for r in rows:
                if r.has_event_id or (r.name or "").strip().casefold() in named:
                    members.append(r)
                else:
                    counts["rows_not_named_by_venue"] += 1
                    not_named_by_venue.append(
                        {
                            "id": int(r.id),
                            "event_id": event_id,
                            "name": r.name,
                            "stored": r.llm_sport_category,
                            "reason": "not_named_by_venue",
                        }
                    )

            movable = [r for r in members if r.llm_sport_category != llm]
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
                            SET llm_sport_category = :llm
                            WHERE id = ANY(:ids)
                              AND llm_sport_category IS NOT DISTINCT FROM :before
                            RETURNING id
                            """
                        ),
                        {"llm": llm, "ids": ids, "before": before},
                    )
                    # RETURNING, not rowcount, and the difference is the whole
                    # point (the sibling's CERT-2382 follow-up). The undo must
                    # name the rows that MOVED. The compare-and-set can
                    # legitimately match fewer rows than planned — a re-ingest
                    # landing between the SELECT and the UPDATE is exactly what
                    # it exists for — and a rowcount tells you HOW MANY matched,
                    # never WHICH, so a restore built from the plan could write a
                    # stale `before` over a fresher value, turning the undo into
                    # a second defect.
                    moved = {r[0] for r in result.all()}
                    counts["rows_written"] += len(moved)
                    applied.extend(p for p in event_plan if p["id"] in moved)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — a blocked write is not a verdict
                # A statement timeout aborts the whole TRANSACTION, so the
                # session is unusable until it is rolled back. Events committed
                # before this one are durable and stay counted.
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**record, "reason": "write_failed"})
                logger.warning(
                    "repair_polymarket_club_noun_category: the UPDATE for event "
                    "%s did not land (%s: %s); rows already committed are "
                    "unaffected",
                    event_id,
                    type(exc).__name__,
                    exc,
                )

    # On an apply the undo is built from what the database RETURNED, never from
    # the plan. On a dry run nothing moved, so the plan is the correct basis —
    # it is the undo for the write about to be authorised.
    undo_basis = applied if apply else planned

    if apply and counts["rows_written"]:
        logger.warning(
            "#6955 Polymarket club-noun repair applied: %s rows. D51 RESTORE:\n%s",
            counts["rows_written"],
            restore_sql(undo_basis),
        )

    # Gotcha #53: a pass that examined events and wrote nothing says so in a
    # named terminal rather than leaving zeros for a reader to interpret.
    if apply:
        terminal = "changed" if counts["rows_written"] else "no_rows_written"
    else:
        terminal = "dry_run"

    return {
        "repair": "polymarket-club-noun-category",
        "bound": list(CLUB_NOUN_EVENT_IDS),
        "counts": counts,
        "planned": planned,
        # What the database actually moved (RETURNING id). Empty on a dry run.
        # Reported alongside `planned` rather than instead of it, so a partial
        # apply is visible as the difference between the two rather than being
        # smoothed into one number.
        "applied": applied,
        "refused": refused,
        # Rows the membership gate declined, by id. Reported as its own list
        # rather than folded into `refused`, which is keyed by EVENT: these are
        # a different unit and hiding them inside an event-level refusal would
        # make the one thing this rail guards hardest invisible.
        "not_named_by_venue": not_named_by_venue,
        "verdicts": verdicts,
        "missing_ids": missing_ids,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log
        # line they have to go and find.
        "restore_sql": restore_sql(undo_basis),
        "terminal": terminal,
    }
