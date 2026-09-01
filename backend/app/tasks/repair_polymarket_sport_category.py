"""Polymarket sport-category recovery — Q495, the drain half of Q493.

PILLAR: MATCHING. SHIP: the US Open matches still filed under Table Tennis —
a category with no tile — move to Tennis, instead of waiting years for a
re-ingest that never arrives.

WHY THIS RAIL EXISTS
====================

Q493 (`d297f948`, merged `3ab15b20`, CERT-663) fixed the CLASSIFIER: Polymarket
tags Setka/TT-Cup events "Table Tennis" and real ATP/WTA events "Tennis", and
neither answer was being read. That fix is correct and was graded correct on
production — of the 44 rows the first `:15` beat after deploy re-ingested,
**44 of 44** migrated `table_tennis` -> `tennis`, and the Setka control event
`945534` held at `table_tennis`. No row the fix ran on stayed wrong.

**But a classifier only repairs a row the poller re-fetches, and the poller is
not reaching this population.** Measured on production at `3ab15b20`,
2026-09-01 08:25Z:

  * 283 of the 344 rows on the Q493 check predicate were still `table_tennis`.
    **Not one** had been touched by the beat that fixed the other 44.
  * **177 of those 283 (63%) had not been re-ingested since 2026-08-28** — four
    days.
  * Across the whole open `table_tennis` bucket (12,826 rows) only **866** were
    touched that day; 3,008 were 6d stale, 2,173 5d, 2,190 4d. Ingest reaches
    roughly **7%/day** of the bucket.
  * Every row on the predicate has a **PAST `commence_time` and
    `status='open'`** — the venue is not returning them in discovery, so the
    hourly upsert never sees them. Gotcha #33's shape (Kalshi settled markets
    stay `open`) on the Polymarket side.

Board item 23 claimed "NO BACKFILL NEEDED" on the strength of a single observed
row repair. That row was inside the ~7%/day slice the beat reaches. The claim
does not generalise, and this rail is the correction.

WHAT IT DOES — AND THE ONE RULE IT REFUSES TO INVENT
====================================================

It does **not** re-derive the sport from the stored row. The tags are not
persisted (`market_metadata` carries `event_title`, `matchup_title`,
`polymarket_event_id` and the shape block — no tags), so a DB-only rule would
have to guess the sport from the NAME. That would be a SECOND classifier, free
to drift from the shipped one, and reconciling two classifiers is the failure
this codebase already pays for elsewhere.

Instead it re-asks the venue and runs **the shipped cascade, unmodified**:

    category, llm = _tags_to_category(event.tags)
    group_names   = [title] + [m.question for m in event.markets]
    category, llm, arm = resolve_event_category(category, llm, title, group_names)

— byte-for-byte the sequence `_process_event_batch` runs at ingest
(`app/tasks/polymarket.py`). If this rail and the poller ever disagree, that is
a bug in one of them, not a policy difference. **The 44/44 beat migration is the
oracle this rail must reproduce**, and `tests/test_repair_polymarket_sport_category_q495.py`
pins exactly that: the real US Open specimen must come back `tennis`, the real
Setka specimen must come back `table_tennis`.

POPULATION, AND WHY SETKA IS THE CONTROL RATHER THAN AN EXCLUSION
=================================================================

The population is open Polymarket rows currently filed `table_tennis` — the
bug's own output. Setka/TT-Cup rows are **inside** that population and are not
excluded by a predicate: they are re-asked like everything else and the venue's
`Table Tennis` tag keeps them where they are. An exclusion list would have to be
maintained and could go stale; a control that rides the same code path cannot.
`counts["unchanged"]` rising on Setka events is the rail proving it is safe, so
a run that changes *everything* is as suspect as one that changes nothing.

WRITES, AND WHAT IS NEVER WRITTEN
=================================

Writes `llm_sport_category` (and `category` when the cascade promotes the event
to `championship`) on every row of the event, via Core UPDATE — never ORM
attribute assignment (gotchas #4/#5). Touches no prices, no outcomes, no
`is_winner`, no resolution fields.

Nothing is written when the venue does not answer clearly:

  * fetch 429/5xx/timeout -> ``indeterminate`` — counted, never written. A
    transient venue failure must not be recorded as a category verdict (#36).
  * fetch 404 -> ``not_at_venue`` — counted, never written.
  * the cascade returns ``None``/``"other"`` -> ``refused_other`` — counted,
    never written. Same guard the poller carries: never overwrite a real value
    with the "other" default.

An empty result is a response SHAPE, not an absence (gotcha #53): a pass that
examined events and wrote nothing says so in a named terminal rather than
leaving four zeros for a reader to interpret.

ORDERING — AND WHAT IT STARTS ON
================================

Newest `commence_time` first, deliberately, and gotcha #41 is the reason it is
spelled out rather than assumed. #41 warns that newest-first starves the old
tail. It does here too, and that is the accepted trade:

  * the ship is user-visible — the matches a reader opens today are the newest
    ones, and they are the rows on a category page with no tile;
  * the population is **not expiring**. Polymarket EVENT data is durable (unlike
    Kalshi MARKET data, `app/utils/kalshi_retention.py`), so the tail cannot rot
    while it waits — the argument that forces oldest-first-within-a-floor on the
    Kalshi rails does not apply;
  * the tail is never silent: ``remaining_events`` is reported on every call and
    the operator pages with ``next_cursor`` until ``scan_exhausted`` comes back
    true. NOT until ``remaining_events`` reaches zero — it counts the suspect
    category, which legitimately contains the control events, so it has a
    positive floor and zero is unreachable.

Paging is a KEYSET (``after_date`` + ``after_id``), never an offset: this
repair removes rows from its own population, so an offset would skip exactly as
many untouched rows as the last page fixed.

**The query parameter is ``after_date``.** Not ``after_commence`` — the
dispatcher does not declare that name, FastAPI drops an unknown query param
SILENTLY, and the resulting call re-reads page one forever while looking busy.
``tests/test_repair_polymarket_sport_category_q496.py`` fails the build if any
prose in ``routes/admin_repairs.py`` names a param the dispatcher cannot pass.

Q496 CORRECTIONS TO THE PAGER AND THE BUDGET
============================================

Three defects the CERT-664 follow-ups named, and one the fix for the third
exposed. None changes what the rail decides; all three change whether an
operator can finish a drain.

1. **The request budget could not fit under the router wall.** A synchronous
   ``POST /api/admin/repairs/...`` has 30s, after which Heroku returns H12 with
   **no body** — so the operator loses ``next_cursor`` and the drain loses its
   place. The old numbers were a 55s loop deadline, a 25s per-fetch timeout and
   a 60-event cap whose *sleep alone* was 21s: the DOCUMENTED DEFAULT was the
   case most likely to fail. Now derived from the wall and asserted by
   ``budget_headroom_seconds()``, which a guard requires to stay positive. The
   cap is sized on a MEASURED figure rather than a guess: the target query below
   runs in **179ms** on production (``EXPLAIN ANALYZE``, first page, no cursor,
   2026-09-01), so the database is not the cost and the budget belongs almost
   entirely to the venue calls.

2. **``terminal="complete"`` was unreachable.** It keyed on
   ``remaining_events == 0``, but ``remaining_events`` counts the suspect
   CATEGORY — which legitimately contains the Setka control. A fully drained
   population therefore reported ``no_work``, i.e. "your cursor is wrong",
   rather than "you are finished". Exhaustion is now proven by the pager
   (``scan_exhausted``: a short page, fully consumed) and ``remaining_events``
   is labelled as the floor it is.

3. **The NULL-``commence_time`` region was unresumable.** ``NULLS LAST`` puts it
   at the very end; a cursor there carries ``after_date: None``; the keyset
   gate required a truthy ``after_date``, so it never activated and the next
   call silently restarted at page one. The gate is now ``after_id is not
   None``, with an explicit second form for the NULL region.

4. **(Found while fixing 3.)** The keyset filtered the raw market rows while
   the cursor names two AGGREGATES over them. An event whose markets straddle
   the boundary would lose some rows, recompute a different
   ``max(commence_time)``, and move in the ordering between pages — a keyset
   that both repeats and skips. The aggregation now happens first and the
   cursor filters its output, so the filtered quantity is the quantity the
   cursor names.

CERT-666 CORRECTIONS — THE DRAIN COULD STILL SAY "FINISHED" WHEN IT WAS NOT
===========================================================================

Q496 made the end state REACHABLE. CERT-666 found it was also reachable when it
was FALSE, which is the worse half of the same bug.

1. **A transient venue failure was advanced past and reported as complete.**
   The cursor was assigned BEFORE the fetch, so a 429/5xx/timeout on the last
   short page left the event unchanged in the suspect category, moved the cursor
   PAST it, and — because exhaustion was computed from the page length alone —
   returned ``scan_exhausted=true`` and a terminal reading "this was the LAST
   page, so the drain is finished". The operator would stop with a user-visible
   match still hidden from Tennis, and the emitted cursor guaranteed nothing
   would ever look at it again. **A transient failure is not a verdict.**

   Now: the cursor advances only past RESOLVED events (``ok`` or a 404
   ``not_at_venue``), the scan STOPS at the first unresolved one, and exhaustion
   additionally requires ``indeterminate == 0`` so completion is impossible
   while any retryable result remains. The state has its own terminal,
   ``paused_unresolved``, and its own field, ``stopped_at_unresolved``.

2. **The advertised headroom omitted everything after the last fetch.** The
   worst case was reported as ``DEADLINE + FETCH_TIMEOUT + VENUE_PAUSE``, but
   the last event still classifies, UPDATEs and commits after that fetch, and
   the ``remaining_events`` count then ran with NO statement timeout at all —
   the one genuinely unbounded statement in the request. Now
   ``POST_LOOP_RESERVE_SECONDS`` is part of the budget, the deadline and cap came
   down to keep the headroom positive, and the count is armed with the time that
   ACTUALLY remains and reports itself unmeasured rather than dying.

ATTENDED ONLY: never wire this to a beat. It is a drain with an end state, not
a standing job — when ``scan_exhausted`` comes back true the poller's own fixed
classifier keeps new rows correct.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"

#: The Heroku router's hard wall on a synchronous request. Not ours to change,
#: and not a timeout we get to observe: past this the router returns **H12 and
#: the operator gets no body at all** — no counts, and crucially no
#: ``next_cursor``, so an attended drain loses its place rather than pausing.
#: Every budget below is derived from this number so the derivation is auditable
#: rather than three constants that happen to look reasonable.
ROUTER_WALL_SECONDS = 30

#: Per-venue-call timeout. Q496: this was 25s, which alone could carry a single
#: request past the wall no matter what the loop deadline said.
FETCH_TIMEOUT_SECONDS = 8

#: The point past which no NEW event is started. Checked at the top of the loop,
#: so the true worst case is this plus one whole fetch plus one pause — see
#: ``budget_headroom_seconds()``, which is asserted by a guard rather than left
#: as arithmetic in a comment.
#:
#: CERT-666 (P2) lowered this from 20. The loop deadline was being treated as if
#: the response were free after it, but the LAST event still classifies, UPDATEs
#: and commits after its fetch, and the terminal count then runs — see
#: ``POST_LOOP_RESERVE_SECONDS``.
DEADLINE_SECONDS = 15

#: Pause between venue calls. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35

#: CERT-666 (P2): time reserved for everything that happens AFTER the loop's last
#: fetch returns, all of which was previously unbudgeted and some of which was
#: unbounded:
#:
#:   * the last event's classify + Core UPDATE + ``commit()``,
#:   * the ``remaining_events`` terminal count — a ``count(DISTINCT ...)`` that
#:     carried NO statement timeout at all, so a lock or a bad plan could hold
#:     the request past the wall on its own,
#:   * response serialization and the request dependency's own commit, which
#:     runs after the handler has already returned.
#:
#: The deadline bounds when the rail stops STARTING work; this bounds the work it
#: has already committed to finishing. ``repair()`` arms a Postgres
#: ``statement_timeout`` from the budget genuinely remaining at that moment, so
#: the count cannot outlive its reservation even if this estimate is wrong.
POST_LOOP_RESERVE_SECONDS = 4.0

#: The slice of ``POST_LOOP_RESERVE_SECONDS`` that is NOT the terminal count: the
#: last event's write and commit, response serialization, and the request
#: dependency's own commit — which runs after the handler has returned and so
#: cannot be observed from inside it. The count is armed with whatever is left of
#: the wall once this is set aside, which is why an over-running loop shortens
#: the count's timeout instead of borrowing against work that still has to run.
POST_LOOP_NON_COUNT_RESERVE_SECONDS = 1.5

#: Events touched per apply call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
#:
#: Q496 lowered this from 60. At 60 the *sleep alone* was 60 x 0.35 = 21s before
#: a single byte of HTTP or DB time, against a 30s router wall — so the
#: DOCUMENTED DEFAULT was the case most likely to H12, and the operator would
#: have read that as the rail being broken.
#:
#: Sized on MEASURED numbers, not a guess. The target query was run against
#: production on 2026-09-01 (`EXPLAIN ANALYZE`, first page, no cursor): **179ms**
#: for 25 rows, so the DB is not the cost — the venue calls are.
#:
#: CERT-666 (P2) lowered this again, from 20 to 15, because reserving the
#: post-loop work took ``DEADLINE_SECONDS`` down to 15. At ~0.75s per event (a
#: Gamma fetch plus VENUE_PAUSE) a 15-event page lands near 11.3s, inside the 15s
#: deadline with margin — so a full page still normally COMPLETES and
#: ``stopped_before`` stays the exception it is meant to be. Had the cap stayed
#: at 20 the documented default would have run to ~15s and hit the deadline
#: routinely, which is safe (partial answer WITH a cursor) but would have made
#: the exceptional state the normal one.
APPLY_EVENT_CAP = 15

#: The category this rail drains. Named once so the census and the repair
#: cannot disagree about their own population.
SUSPECT_CATEGORY = "table_tennis"

#: Statement timeout for the census, which runs TWO queries under ONE router
#: wall. Q496: this was ``'25s'``, so its own permitted worst case was 50s
#: against a 30s wall — the census could H12 while still believing its
#: ``measured: false`` path had it covered. It cannot: an H12 returns no body,
#: so the honest "we could not look" answer never reaches the operator and the
#: rail's whole gotcha-#54 argument evaporates at exactly the moment it matters.
#: Both queries measured **94ms and 179ms** on production 2026-09-01, so 12s is
#: ~60x the observed cost and still leaves 6s of the wall for everything else.
CENSUS_STATEMENT_TIMEOUT_SECONDS = 12


def budget_headroom_seconds() -> float:
    """Seconds left under the router wall in the rail's WORST case.

    The deadline is checked at the top of the loop, so after it passes the rail
    may still start one fetch and one pause. And after THAT fetch returns the
    rail still has real work to do — the last event's write and commit, the
    terminal count, serialization, the dependency's commit. So the worst case is
    ``DEADLINE + FETCH_TIMEOUT + VENUE_PAUSE + POST_LOOP_RESERVE``, not
    ``DEADLINE``, and not the three-constant subtotal this function returned
    before CERT-666 (P2) — that version reported 1.65s of headroom the rail did
    not actually have, because it stopped counting at the last fetch.

    Expressed as a function so a guard can assert it stays positive, rather than
    as a comment that goes stale the first time someone raises one of the four
    numbers.

    Positive means an over-running call returns a partial answer WITH its
    cursor. Negative means it returns H12 with no body, and an attended drain
    silently loses its place.
    """
    return ROUTER_WALL_SECONDS - (
        DEADLINE_SECONDS + FETCH_TIMEOUT_SECONDS + VENUE_PAUSE + POST_LOOP_RESERVE_SECONDS
    )


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------


async def census(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """Size the mis-filed population and how stale it is. Writes nothing.

    `apply` is accepted and ignored so the census can never be turned into a
    write by a stray query parameter.
    """
    started = time.monotonic()
    try:
        await session.execute(
            text(f"SET statement_timeout = '{CENSUS_STATEMENT_TIMEOUT_SECONDS}s'")
        )

        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                      (CURRENT_DATE - fm.updated_at::date) AS days_since_touch,
                      count(*)                             AS markets,
                      count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                                                           AS events
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1
                    """
                ),
                {"cat": SUSPECT_CATEGORY},
            )
        ).all()

        # Q496: this second query used to sit OUTSIDE the try. It is the same
        # scan under the same statement timeout, so it can fail the same way —
        # and when it did, the exception escaped, the dispatcher turned it into
        # a 500, and the `measured: false` contract the block above exists to
        # honour was never reached. A census's whole job is to be honest about
        # not knowing; a second query that can only fail LOUDLY defeats that.
        #
        # Events are counted per staleness bucket above, so they do NOT sum: one
        # event's rows can straddle two buckets. Ask for the distinct figure.
        total_events = (
            await session.execute(
                text(
                    """
                    SELECT count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    """
                ),
                {"cat": SUSPECT_CATEGORY},
            )
        ).scalar() or 0
    except Exception as exc:  # noqa: BLE001 — a census timeout is not a zero
        # Gotcha #54: a census that could not measure returns `measured: false`
        # with a reason, NEVER a zero. A zero here would read as "the population
        # is drained" — the exact opposite of "we could not look".
        return {
            "repair": "polymarket-sport-category-census",
            "measured": False,
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "elapsed_s": round(time.monotonic() - started, 2),
        }

    by_staleness = [
        {"days_since_touch": int(r[0]), "markets": int(r[1]), "events": int(r[2])}
        for r in rows
    ]
    total_markets = sum(b["markets"] for b in by_staleness)

    stale_4d_plus = sum(b["markets"] for b in by_staleness if b["days_since_touch"] >= 4)

    return {
        "repair": "polymarket-sport-category-census",
        "measured": True,
        "population": f"source=polymarket status=open llm_sport_category={SUSPECT_CATEGORY}",
        "markets": total_markets,
        "events": int(total_events),
        "markets_stale_4d_plus": stale_4d_plus,
        "by_staleness": by_staleness,
        # Said out loud because the number is the argument for the rail: these
        # rows are not being re-fetched, so they do not self-heal.
        "note": (
            "markets_stale_4d_plus have not been re-ingested in 4+ days; the "
            "hourly poller is not reaching them, so the Q493 classifier fix "
            "cannot repair them without this drain"
        ),
        "elapsed_s": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------


async def _fetch_event(
    client: httpx.AsyncClient, event_id: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """Return ``(status, payload)`` where status is ok/not_at_venue/indeterminate.

    Never raises for a venue condition and never collapses "does not exist" into
    "did not answer" — 404 and 429 need opposite handling and a catch-all that
    returned ``None`` for both would write a verdict on a rate limit (#36).
    """
    try:
        r = await client.get(f"{GAMMA}/events/{event_id}", timeout=FETCH_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — transport failure is INDETERMINATE
        return "indeterminate", None
    if r.status_code == 404:
        return "not_at_venue", None
    if r.status_code != 200:
        return "indeterminate", None
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        return "indeterminate", None
    if not isinstance(payload, dict):
        return "indeterminate", None
    return "ok", payload


def classify_event_payload(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Run the SHIPPED ingest cascade over a raw Gamma event payload.

    Returns ``(category, llm_sport_category)`` exactly as
    ``_process_event_batch`` would compute them. Imported inside the function so
    this module stays import-light and `sport_keys`-style circularity cannot
    creep in via the task package.

    This function deliberately contains NO sport rules of its own. Every rule it
    applies lives in `app/tasks/polymarket.py`; if that file changes, this rail
    changes with it and cannot drift.
    """
    from app.tasks.polymarket import _tags_to_category, resolve_event_category

    raw_tags = payload.get("tags") or []
    tags: list[str] = []
    for t in raw_tags:
        # Gamma returns tags as objects ({"label": "Tennis", ...}); older shapes
        # and our own fixtures use bare strings. Accept both rather than assume.
        if isinstance(t, str):
            tags.append(t)
        elif isinstance(t, dict):
            label = t.get("label") or t.get("slug") or t.get("name")
            if label:
                tags.append(str(label))

    title = payload.get("title") or ""
    markets = payload.get("markets") or []
    group_names = [title] + [
        str((m or {}).get("question") or "") for m in markets if isinstance(m, dict)
    ]

    category, llm_sport_category = _tags_to_category(tags)
    category, llm_sport_category, _arm = resolve_event_category(
        category, llm_sport_category, title, group_names
    )
    return category, llm_sport_category


# ---------------------------------------------------------------------------
# Repair — the write half
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int = None,
    after_date: str = None,
    after_id: int = None,
    **_ignored,
) -> dict[str, Any]:
    """Re-ask the venue for each mis-filed event and store the shipped cascade's answer.

    Dry-run by default. Resumable by KEYSET (``after_date`` + ``after_id``
    from ``next_cursor``), never by offset — this repair removes rows from its
    own population.
    """
    started = time.monotonic()
    cap = min(int(limit or APPLY_EVENT_CAP), APPLY_EVENT_CAP)

    params: dict[str, Any] = {"cat": SUSPECT_CATEGORY, "cap": cap}

    # The cursor is a page position, and `after_id` alone is enough to name one.
    # Q496: the gate used to be `after_date AND after_id is not None`, so the
    # NULL-commence_time region — which `NULLS LAST` puts at the very end — was
    # unresumable: its cursor carries `after_date: None`, the keyset never
    # activated, and the next call silently re-read page ONE forever.
    keyset = ""
    if after_id is not None:
        params["after_id"] = int(after_id)
        if after_date:
            # In the non-NULL region. Everything still to come is either a
            # smaller (commence_time, anchor_id) tuple, or ANY row in the NULL
            # region — because NULLS LAST sorts the whole of it after us.
            keyset = """
                  AND ( ev.commence_time IS NULL
                        OR (ev.commence_time, ev.anchor_id) <
                           (CAST(:after_date AS timestamptz), CAST(:after_id AS integer)) )
            """
            params["after_date"] = after_date
        else:
            # Already inside the NULL region: ordering there is by anchor_id
            # alone, and no non-NULL row can follow.
            keyset = """
                  AND ev.commence_time IS NULL
                  AND ev.anchor_id < CAST(:after_id AS integer)
            """

    # One row per EVENT (the unit of a venue call), carrying the anchor row's
    # id/commence for the cursor. `min(id)` keeps the cursor deterministic.
    #
    # Q496: the keyset is applied AFTER the aggregation, never to the raw market
    # rows. The cursor is a pair of AGGREGATES (`max(commence_time)`,
    # `min(id)`), so filtering the inputs to those aggregates is filtering a
    # different quantity than the one the cursor names: an event whose markets
    # straddle the boundary would have some rows removed, recompute a DIFFERENT
    # `max(commence_time)`, and so move in the ordering between pages — which is
    # exactly how a keyset both repeats and skips events.
    targets = (
        await session.execute(
            text(
                f"""
                SELECT ev.event_id, ev.commence_time, ev.anchor_id, ev.markets
                FROM (
                  SELECT
                    fm.market_metadata->>'polymarket_event_id' AS event_id,
                    max(fm.commence_time)                      AS commence_time,
                    min(fm.id)                                 AS anchor_id,
                    count(*)                                   AS markets
                  FROM futures_markets fm
                  WHERE fm.source = 'polymarket'
                    AND fm.status = 'open'
                    AND fm.llm_sport_category = :cat
                    AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                  GROUP BY 1
                ) ev
                WHERE TRUE
                  {keyset}
                ORDER BY ev.commence_time DESC NULLS LAST, ev.anchor_id DESC
                LIMIT :cap
                """
            ),
            params,
        )
    ).all()

    counts = {
        "events_examined": 0,
        "changed": 0,
        "unchanged": 0,
        "refused_other": 0,
        "not_at_venue": 0,
        "indeterminate": 0,
        "markets_written": 0,
    }
    #: What it changed them TO. A single "changed" number cannot tell a correct
    #: drain from a rail that relabelled the bucket to one wrong answer.
    to_category: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    # CERT-666 (P1): the cursor starts where the OPERATOR already was, not at
    # None. A page whose very first event fails to resolve must hand back the
    # cursor it was given — handing back None reads as "start over" and silently
    # sends an attended drain to page one.
    incoming_cursor: Optional[dict[str, Any]] = (
        {"after_date": after_date, "after_id": int(after_id)} if after_id is not None else None
    )
    next_cursor: Optional[dict[str, Any]] = incoming_cursor
    stopped_before: Optional[str] = None
    stopped_at_unresolved: Optional[str] = None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for t in targets:
            if (time.monotonic() - started) > DEADLINE_SECONDS:
                stopped_before = f"event_id={t.event_id}"
                break

            counts["events_examined"] += 1

            status, payload = await _fetch_event(client, str(t.event_id))
            await asyncio.sleep(VENUE_PAUSE)

            if status == "indeterminate":
                # CERT-666 (P1) — THE CURSOR MUST NOT CROSS UNFINISHED WORK.
                #
                # This used to advance `next_cursor` BEFORE the fetch, then
                # `continue`. So an ordinary 429/5xx/timeout on the last short
                # page left the event unchanged in the suspect category, moved
                # the cursor PAST it, and — because exhaustion was computed from
                # the page length alone — reported the drain finished. The
                # operator stopped with a mis-filed, user-visible match still
                # hidden, and the emitted cursor guaranteed it would never be
                # looked at again. A transient venue failure is not a verdict.
                #
                # We stop here instead, leaving the cursor on the last RESOLVED
                # event, so re-running with `next_cursor` retries this one.
                # Backing off is also the correct response to the 429 that most
                # often causes this.
                counts["indeterminate"] += 1
                stopped_at_unresolved = f"event_id={t.event_id}"
                break

            # Resolved — `ok` or a 404 `not_at_venue`, both of which are real,
            # repeatable answers. Only now may the cursor move past this event.
            next_cursor = {
                "after_date": t.commence_time.isoformat() if t.commence_time else None,
                "after_id": int(t.anchor_id),
            }

            if status != "ok" or payload is None:
                counts[status] += 1
                continue

            category, llm_sport_category = classify_event_payload(payload)

            if not llm_sport_category or llm_sport_category == "other":
                # Never overwrite a real value with the "other" default — the
                # same guard the poller's own update_set carries.
                counts["refused_other"] += 1
                continue

            if llm_sport_category == SUSPECT_CATEGORY:
                # The venue confirms it. Setka/TT-Cup lands here, which is how
                # this rail proves it is safe rather than asserting it.
                counts["unchanged"] += 1
                continue

            counts["changed"] += 1
            to_category[llm_sport_category] = to_category.get(llm_sport_category, 0) + 1
            if len(samples) < 10:
                samples.append(
                    {
                        "event_id": str(t.event_id),
                        "title": str(payload.get("title") or "")[:100],
                        "from": SUSPECT_CATEGORY,
                        "to": llm_sport_category,
                        "markets": int(t.markets),
                    }
                )

            if not apply:
                continue

            # Core UPDATE, never ORM attribute assignment (gotchas #4/#5).
            # Compare-and-set on the category we selected on, so a concurrent
            # re-ingest that already corrected the row is never clobbered by a
            # verdict computed before it landed.
            r = await session.execute(
                text(
                    """
                    UPDATE futures_markets
                    SET llm_sport_category = :llm,
                        category = CASE
                            WHEN :cat_new = 'championship' THEN 'championship'
                            ELSE category
                        END,
                        updated_at = NOW()
                    WHERE source = 'polymarket'
                      AND status = 'open'
                      AND llm_sport_category = :cat_old
                      AND market_metadata->>'polymarket_event_id' = :eid
                    """
                ),
                {
                    "llm": llm_sport_category,
                    "cat_new": category,
                    "cat_old": SUSPECT_CATEGORY,
                    "eid": str(t.event_id),
                },
            )
            counts["markets_written"] += r.rowcount
            await session.commit()

    # CERT-666 (P2) — THE TERMINAL COUNT WAS THE LAST UNBOUNDED STATEMENT IN THE
    # REQUEST. It ran after the loop deadline had already passed, carried no
    # statement timeout, and a lock or a bad plan could therefore hold the
    # request past the router wall on its own — costing the operator the H12 with
    # no body, and so the cursor, which is the exact failure this rail exists to
    # avoid. Give it the budget that ACTUALLY remains rather than a constant: if
    # the loop over-ran, the count gets less time, not the same time.
    count_budget_s = max(
        0.25,
        ROUTER_WALL_SECONDS
        - (time.monotonic() - started)
        - POST_LOOP_NON_COUNT_RESERVE_SECONDS,
    )
    remaining: Optional[int] = None
    remaining_measured = True
    try:
        # Interpolated, not bound: `SET` takes no bind parameters. The value is
        # an int we computed from our own constants, never operator input.
        await session.execute(text(f"SET LOCAL statement_timeout = {int(count_budget_s * 1000)}"))
        remaining = (
            await session.execute(
                text(
                    """
                    SELECT count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    """
                ),
                {"cat": SUSPECT_CATEGORY},
            )
        ).scalar() or 0
    except Exception:  # noqa: BLE001 — a slow count must not cost the operator the cursor
        # A statement timeout aborts the whole TRANSACTION, not just the
        # statement, so the session is unusable until it is rolled back.
        await session.rollback()
        remaining_measured = False
        logger.warning(
            "repair_polymarket_sport_category: remaining_events count exceeded its "
            "%.2fs budget; reporting it unmeasured rather than losing the response",
            count_budget_s,
        )

    # Q496 — SCAN EXHAUSTION IS A DIFFERENT FACT FROM `remaining_events`, and
    # conflating them made the drain's success state unreachable.
    #
    # `remaining_events` counts the SUSPECT CATEGORY, and Setka/TT-Cup events
    # are legitimately in it — they are the control this rail deliberately does
    # not move. So `remaining_events` has a positive floor it can never go
    # below, `remaining == 0` is unreachable, and the old `terminal="complete"`
    # arm was dead code: a fully drained population reported `no_work`, which
    # reads as "the cursor is wrong", not "you are finished".
    #
    # Exhaustion is instead proven by the PAGER: the page came back short of the
    # cap (so no row sorts after it) and the loop consumed all of it (so nothing
    # was left unexamined by the deadline).
    #
    # CERT-666 (P1): exhaustion also requires that nothing on the page was left
    # UNRESOLVED. A short, fully-consumed page proves no row sorts after it — it
    # does not prove every row in it was answered, and a transient venue failure
    # leaves an event that may still be mis-filed sitting behind the cursor.
    #
    # Both terms are deliberate. `stopped_at_unresolved` is what the loop
    # actually sets today; the `indeterminate` count is the invariant — if a
    # later change turns that `break` back into a `continue`, completion still
    # cannot be claimed while any retryable result remains.
    scan_exhausted = (
        len(targets) < cap
        and stopped_before is None
        and stopped_at_unresolved is None
        and counts["indeterminate"] == 0
    )

    result: dict[str, Any] = {
        "repair": "polymarket-sport-category",
        "applied": bool(apply),
        "counts": counts,
        "changed_to": to_category,
        "samples": samples,
        "remaining_events": int(remaining) if remaining_measured else None,
        # CERT-666 (P2): "it returned" is not "it worked" (gotcha #53). A count
        # that ran out of budget reports itself unmeasured; it never reports 0.
        "remaining_events_measured": remaining_measured,
        # NB: this string may not name the control league. `SUSPECT_CATEGORY` is
        # the only sport literal permitted in executable code here, and the Q495
        # anti-drift guard scans string literals too — correctly, since a rule
        # table would arrive as literals long before it arrived as an `if`.
        "remaining_events_note": (
            "count of the SUSPECT CATEGORY, which legitimately includes the "
            "control events the venue confirms really do belong to it. It has a "
            "positive floor and reaching zero is NOT the end state — read "
            "`scan_exhausted` for that. `null` means the count ran out of its "
            "budget and was NOT measured; it never means zero — see "
            "`remaining_events_measured`."
        ),
        "scan_exhausted": scan_exhausted,
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        # CERT-666 (P1): the event the venue would not answer for. The cursor
        # stops BEFORE it, so re-running retries it. Never a verdict on the row.
        "stopped_at_unresolved": stopped_at_unresolved,
        "cap": cap,
        "ordering": (
            "newest commence_time first — the user-visible rows. Gotcha #41's "
            "tail-starvation is accepted here because Polymarket EVENT data is "
            "durable, so the tail cannot rot while it waits; `remaining_events` "
            "is reported every call so it is never silent."
        ),
        "budget": {
            "router_wall_s": ROUTER_WALL_SECONDS,
            "deadline_s": DEADLINE_SECONDS,
            "fetch_timeout_s": FETCH_TIMEOUT_SECONDS,
            "venue_pause_s": VENUE_PAUSE,
            "worst_case_headroom_s": round(budget_headroom_seconds(), 2),
        },
    }

    # "It returned" is not "it worked" (gotcha #53 / task_verdict). Each zero
    # state is a DIFFERENT real state and gets its own terminal rather than
    # sharing one silent success.
    # CERT-666 (P1): an unresolved event outranks every other terminal. The run
    # did NOT finish, whatever else it managed, and the operator must re-run
    # before reading anything as complete. Checked first so no arm below can
    # quietly describe this as a finished drain.
    if stopped_at_unresolved is not None:
        result["terminal"] = "paused_unresolved"
        result["reason"] = (
            f"the venue did not answer for {stopped_at_unresolved} — a transient "
            "failure (timeout, 429, 5xx, or an unreadable body), NOT a verdict on "
            "that event. The cursor deliberately stops BEFORE it, so re-running "
            "with `next_cursor` retries it. THIS IS NOT A COMPLETED DRAIN: the "
            "event may still be mis-filed, and anything already counted above it "
            "on this page is real and still applies."
        )
    elif counts["events_examined"] == 0:
        result["terminal"] = "complete" if scan_exhausted else "no_work"
        result["reason"] = (
            "the pager reached the end of the population under this cursor — "
            "every event still filed here has been examined and the venue "
            "confirmed it, so `remaining_events` is a floor, not a backlog"
            if scan_exhausted
            else "no events selected by this page — advance or clear the cursor"
        )
    elif counts["changed"] == 0:
        result["terminal"] = "examined_no_change_complete" if scan_exhausted else "examined_no_change"
        result["reason"] = (
            "every event examined was confirmed by the venue, refused as "
            "'other', or did not answer — see counts; this is a real state, "
            "not a silent success"
            + (
                " — and this was the LAST page, so the drain is finished"
                if scan_exhausted
                else ""
            )
        )
    else:
        result["terminal"] = "changed" if apply else "dry_run"
        result["reason"] = (
            f"{counts['changed']} event(s) disagree with the venue"
            + ("" if apply else " — nothing written, re-run with apply=true")
        )
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    return result
