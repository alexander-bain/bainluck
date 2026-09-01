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
  * the tail is never silent: ``remaining`` is reported on every call and the
    operator pages with ``next_cursor`` until it reaches zero.

Paging is a KEYSET (``after_date`` + ``after_id``), never an offset: this
repair removes rows from its own population, so an offset would skip exactly as
many untouched rows as the last page fixed.

ATTENDED ONLY: never wire this to a beat. It is a drain with an end state, not
a standing job — when ``remaining`` reaches zero the poller's own fixed
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

#: Events touched per apply call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
APPLY_EVENT_CAP = 60

#: Wall-clock bound for one call. Bounds the longest single uninterrupted
#: operation, not the loop boundary (the budget-guard lesson).
DEADLINE_SECONDS = 55

#: Pause between venue calls. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35

#: The category this rail drains. Named once so the census and the repair
#: cannot disagree about their own population.
SUSPECT_CATEGORY = "table_tennis"


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
        await session.execute(text("SET statement_timeout = '25s'"))

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
        r = await client.get(f"{GAMMA}/events/{event_id}", timeout=25)
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
    keyset = ""
    if after_date and after_id is not None:
        # Strict keyset on the exact ORDER BY, so a page boundary can neither
        # repeat an event nor skip one when commence_time ties.
        keyset = """
              AND (fm.commence_time, fm.id) <
                  (CAST(:after_date AS timestamptz), CAST(:after_id AS integer))
        """
        params["after_date"] = after_date
        params["after_id"] = int(after_id)

    # One row per EVENT (the unit of a venue call), carrying the anchor row's
    # id/commence for the cursor. `min(id)` keeps the cursor deterministic.
    targets = (
        await session.execute(
            text(
                f"""
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
                  {keyset}
                GROUP BY 1
                ORDER BY max(fm.commence_time) DESC NULLS LAST, min(fm.id) DESC
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
    next_cursor: Optional[dict[str, Any]] = None
    stopped_before: Optional[str] = None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for t in targets:
            if (time.monotonic() - started) > DEADLINE_SECONDS:
                stopped_before = f"event_id={t.event_id}"
                break

            counts["events_examined"] += 1
            next_cursor = {
                "after_date": t.commence_time.isoformat() if t.commence_time else None,
                "after_id": int(t.anchor_id),
            }

            status, payload = await _fetch_event(client, str(t.event_id))
            await asyncio.sleep(VENUE_PAUSE)

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

    result: dict[str, Any] = {
        "repair": "polymarket-sport-category",
        "applied": bool(apply),
        "counts": counts,
        "changed_to": to_category,
        "samples": samples,
        "remaining_events": int(remaining),
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        "cap": cap,
        "ordering": (
            "newest commence_time first — the user-visible rows. Gotcha #41's "
            "tail-starvation is accepted here because Polymarket EVENT data is "
            "durable, so the tail cannot rot while it waits; `remaining_events` "
            "is reported every call so it is never silent."
        ),
    }

    # "It returned" is not "it worked" (gotcha #53 / task_verdict). Each zero
    # state is a DIFFERENT real state and gets its own terminal rather than
    # sharing one silent success.
    if counts["events_examined"] == 0:
        result["terminal"] = "complete" if remaining == 0 else "no_work"
        result["reason"] = (
            "the mis-filed population is drained"
            if remaining == 0
            else "no events selected by this page — advance or clear the cursor"
        )
    elif counts["changed"] == 0:
        result["terminal"] = "examined_no_change"
        result["reason"] = (
            "every event examined was confirmed by the venue, refused as "
            "'other', or did not answer — see counts; this is a real state, "
            "not a silent success"
        )
    else:
        result["terminal"] = "changed" if apply else "dry_run"
        result["reason"] = (
            f"{counts['changed']} event(s) disagree with the venue"
            + ("" if apply else " — nothing written, re-run with apply=true")
        )
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    return result
