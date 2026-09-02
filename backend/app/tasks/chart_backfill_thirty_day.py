"""live/039 — the ONE-TIME drain: every attached event of the last 30 days.

Alex: *"if we had Polymarket integration we could backfill all the events we
don't have probabilities for from the last 30 days."* We do, so this runs it.

WHAT THIS IS NOT. It is not a second nightly. `backfill_thin_event_charts`
(live/036) pre-warms the ±7-day reader window on reader-reachable sports, and
`plan_on_demand_fill` catches whatever a person actually opens. Both are
steady-state. This is a one-off drain of the 30-day backlog those two were
explicitly told to stop chasing, and when it is done it is done — no beat entry,
no schedule. It is triggered, it checkpoints, it is re-triggered until it reports
`exhausted`.

MEASURED POPULATION, production 2026-09-02:

    events with commence_time in the last 30d and >=1 Kalshi/Polymarket market
                                                              19,646
    ... of which hold fewer than 20 Kalshi/Polymarket points  18,460
    ... of which hold NONE at all                             14,240

THE ORDER IS THE SHIP. 13,591 of those 19,646 are `soccer_other`, `esports` and
`americanfootball_other` — the half live/036 called "February soccer". Draining
in id or time order would spend the first several hours there and reach the US
Open last. So the sweep walks PRIORITY TIERS: the US Open cohort first, then
everything else a reader can reach, then the remainder. Each tier keeps its own
keyset cursor, and a tier is finished before the next one starts. A drain that
delivers the named ship in its first hour is worth more than one that delivers
everything in its eighth.

THE CURSOR IS A KEYSET ON (commence_time, event_id), for the reason live/035
learned the hard way: `futures_markets.created_at` is transaction-time and a
poll commits hundreds of rows inside one `now()`, so a cursor keyed on a
timestamp alone steps over the tail of any tied cohort larger than one page and
loses it permanently. `events.commence_time` ties just as readily — 438 events
share one value in this very window — so the id half is load-bearing here too.

GRANULARITY. The queue asked for a flat hourly fill as a cost bound. This uses
:func:`granularity_floor_minutes` instead, which is the same bound where it
matters (hourly past `COARSE_GRANULARITY_AGE_DAYS`) and finer where a reader
benefits (1-minute inside it) — a two-day-old US Open match drawn as 48 hourly
dots loses exactly the in-match swing the chart is opened for. `min_period_minutes`
overrides it for an operator who wants the cheap pass regardless.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import NamedTuple, Optional, Sequence

logger = logging.getLogger(__name__)


#: The window Alex named. Not Kalshi's retention floor (~74-86 days, gotcha #35)
#: — that is where history STOPS being available, and this is a deliberately
#: smaller, finishable bite inside it.
THIRTY_DAY_WINDOW_DAYS = 30

#: A chart is worth filling below this many points. The queue's number, and it is
#: deliberately a FLAT threshold rather than `is_thin_chart`'s lifetime-scaled
#: one: this pass is about the events that are a dot or a stub, not about topping
#: up a curve that already has a shape. Bounded inside the SQL by a `LIMIT`, so
#: the count costs at most this many index rows per event rather than a full
#: count over a very large table — the shape that made live/035's first
#: selection query time out.
THIRTY_DAY_THIN_POINTS = 20

#: Politeness between events. Both venues are being asked for history nobody is
#: paying us for, across tens of thousands of events. At ~2-3 requests per event
#: this holds the sweep near 3 req/s, which is far under either venue's limit and
#: still drains a 900s batch's worth of work.
INTER_EVENT_SLEEP_SECONDS = 0.25

#: Consecutive per-event failures before a batch gives up. A venue that has
#: started refusing us will refuse the next 200 events too, and burning the batch
#: to discover that costs the checkpoint nothing but costs the venue goodwill.
CONSECUTIVE_ERROR_ABORT = 25

#: Redis checkpoint. One key per tier, so finishing the US Open tier cannot be
#: undone by the remainder tier's progress and vice versa. Same reasoning as
#: live/035's sweep cursor: a hint, never a fact, so an evicted key costs one
#: re-scan and never a wrong row.
CHECKPOINT_KEY = "chart_backfill_30d:cursor:{tier}"
#: Set once a tier's scan has reached the end of its population. Without it a
#: re-trigger after exhaustion restarts the tier from the top and re-judges
#: thousands of now-thick charts before it can reach the next tier.
TIER_DONE_KEY = "chart_backfill_30d:done:{tier}"


class Tier(NamedTuple):
    """One priority band of the drain."""

    name: str
    #: Human-readable reason this band goes where it goes, echoed into the verdict.
    why: str


#: Ordered. Tier 0 is Alex's addendum ("prioritize POLYMARKET history for US Open
#: matches"); tier 1 is live/036's reader-reachable set; tier 2 is the remainder,
#: which is the bulk and which nobody is waiting on.
TIERS: tuple[Tier, ...] = (
    Tier("us_open", "Alex's addendum — the US Open cohort is the named ship"),
    Tier("reachable", "live/036's reader-reachable sports"),
    Tier("remainder", "everything else attached inside the window"),
)


def is_us_open_sport_key(sport_key: Optional[str]) -> bool:
    """Whether this sport key can hold a US Open match row.

    🔴 Both spellings, and the second one is the trap live/036 already documented.
    The tournament-keyed rows (`tennis_atp_us_open`, `tennis_wta_us_open`) are the
    obvious half. The other half carries the PLAIN tour key: measured 2026-09-02,
    28 of that day's and the day before's US Open singles matches exist as two
    event rows — a Kalshi-native one on `tennis_atp`/`tennis_wta` with a
    ticker-derived midnight `commence_time` (gotcha #14), and a Polymarket-native
    one on `tennis_*_us_open`. The specimen this whole rail was built for
    (15300759, Vallejo v Monfils) is plain `tennis_atp`. A tier that matched only
    the tournament keys would drain the Polymarket half of each split pair and
    leave the Kalshi half — which is the row most readers actually land on —
    for tier 2.

    `tennis_atp`/`tennis_wta` also carry non-US-Open tour and Challenger matches
    in this window. That is accepted: this is an ORDERING, not a filter, and
    every event in every tier is drained eventually.

    🔴 SEGMENTS, NOT A SUBSTRING. `"us_open" in key` is the obvious spelling and
    it is wrong twice over on the real sports table: it matches
    `tennis_atp_aus_open_singles` — the AUSTRALIAN Open, because `us_open` is a
    substring of `aus_open` — and it matches `golf_us_open_winner`, a different
    sport's tournament entirely. Neither belongs in the tier that exists to put
    Alex's tennis cohort first.
    """
    if not sport_key:
        return False
    key = sport_key.lower()
    if key in ("tennis_atp", "tennis_wta"):
        return True
    if not key.startswith("tennis"):
        return False
    segments = key.split("_")
    return any(
        segments[i] == "us" and segments[i + 1] == "open"
        for i in range(len(segments) - 1)
    )


async def tier_sport_ids(session) -> dict[str, list[int]]:
    """`sports.id` for each tier, partitioned so no event is drained twice.

    The whole table is ~176 rows, so this is one trivial scan and the rules stay
    in tested pure functions rather than being re-expressed as a `LIKE` ladder in
    SQL that would drift away from them — the same discipline (and the same
    reason) as live/035's :func:`reachable_sport_ids`.
    """
    from sqlalchemy import select

    from app.models.models import Sport
    from app.tasks.event_chart_backfill import is_reader_reachable_sport_key

    rows = (await session.execute(select(Sport.id, Sport.key))).all()
    buckets: dict[str, list[int]] = {tier.name: [] for tier in TIERS}
    for sport_id, key in rows:
        if is_us_open_sport_key(key):
            buckets["us_open"].append(int(sport_id))
        elif is_reader_reachable_sport_key(key):
            buckets["reachable"].append(int(sport_id))
        else:
            buckets["remainder"].append(int(sport_id))
    return buckets


#: MEASURED at 3.9s over the full 19,646-event window on production 2026-09-02.
#:
#: The point-count subquery is wrapped in an inner `LIMIT :thin_points`, and that
#: is the whole reason this returns at all. live/035's first attempt counted every
#: point for every candidate and hit `statement_timeout`; counting a bounded
#: prefix answers the only question being asked — "are there fewer than N?" — for
#: at most N index rows per event. `>= :thin_points` is not distinguishable from
#: "far more", and nothing here needs to distinguish them.
THIRTY_DAY_CANDIDATES_SQL = """
    SELECT
        e.id                AS event_id,
        e.commence_time     AS commence_time,
        (
            SELECT COUNT(*) FROM (
                SELECT 1 FROM win_prob_snapshots w
                WHERE w.event_id = e.id
                  AND w.source IN ('kalshi', 'polymarket')
                LIMIT :thin_points
            ) capped
        )                   AS point_count
    FROM events e
    WHERE e.commence_time >= NOW() - make_interval(days => :window_days)
      AND e.commence_time <= NOW() + INTERVAL '1 day'
      AND e.sport_id IN :sport_ids
      -- EXISTS, not a JOIN + GROUP BY. The join form multiplies an event by its
      -- market count before the DISTINCT can collapse it, and a US Open event
      -- carries up to 14 Polymarket rows.
      AND EXISTS (
          SELECT 1 FROM futures_markets fm
          WHERE fm.event_id = e.id
            AND fm.source IN ('kalshi', 'polymarket')
      )
      -- The keyset. See the module docstring: `commence_time` ties in bulk
      -- (a ticker-derived midnight is shared by every match on a card), so the
      -- id half is what stops a tied cohort larger than one page from being
      -- stepped over and lost.
      AND (
          CAST(:after_ts AS timestamptz) IS NULL
          OR (e.commence_time, e.id)
               > (CAST(:after_ts AS timestamptz), CAST(:after_id AS bigint))
      )
    ORDER BY e.commence_time ASC, e.id ASC
    LIMIT :scan
"""


class DrainPage(NamedTuple):
    """One page of candidates judged inside one tier."""

    event_ids: list[int]
    #: `(commence_time, event_id)` of the last candidate LOOKED AT, thin or not.
    next_cursor: Optional[tuple]
    #: True when the scan reached the end of this tier's population.
    exhausted: bool
    scanned: int


async def select_thirty_day_page(
    session, *, sport_ids: Sequence[int], limit: int,
    scan_multiple: int = 4, after: Optional[tuple] = None,
) -> DrainPage:
    """One page of fillable events inside one tier, after the keyset position."""
    from sqlalchemy import bindparam, text

    if not sport_ids:
        return DrainPage([], after, True, 0)

    after_ts, after_id = (after or (None, None))
    scan = max(1, limit * max(1, scan_multiple))
    # `expanding=True` renders a literal IN list at execution time, so the REAL
    # statement is the one the guards can run — live/035 lost a day to a phantom
    # required bind that no stubbed-session test could see.
    statement = text(THIRTY_DAY_CANDIDATES_SQL).bindparams(
        bindparam("sport_ids", expanding=True)
    )
    rows = (
        await session.execute(
            statement,
            {
                "thin_points": THIRTY_DAY_THIN_POINTS,
                "window_days": THIRTY_DAY_WINDOW_DAYS,
                "sport_ids": list(sport_ids),
                "after_ts": after_ts,
                "after_id": after_id,
                "scan": scan,
            },
        )
    ).fetchall()

    fillable: list[int] = []
    cursor: Optional[tuple] = None
    for row in rows:
        # Advance over every row JUDGED, not only the ones picked — a thick chart
        # the cursor did not pass would be re-counted on every re-trigger.
        if row.commence_time is not None:
            cursor = (row.commence_time, int(row.event_id))
        if int(row.point_count or 0) < THIRTY_DAY_THIN_POINTS:
            fillable.append(int(row.event_id))
        if len(fillable) >= limit:
            break
    return DrainPage(fillable, cursor, len(rows) < scan, len(rows))


# ---------------------------------------------------------------------------
# Checkpoint — a hint in Redis, never a fact in a column
# ---------------------------------------------------------------------------


def _read_checkpoint(tier: str) -> tuple[Optional[tuple], bool]:
    """`((commence_time, event_id) | None, tier_is_done)`.

    Every failure mode — no Redis, evicted key, half-written value — answers
    "start this tier from the top", which wastes a scan and never writes a wrong
    row. Routed through `get_redis_client()` so a socket with no timeout cannot
    freeze the worker's event loop (gotcha #39).
    """
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        done = bool(client.get(TIER_DONE_KEY.format(tier=tier)))
        raw = client.get(CHECKPOINT_KEY.format(tier=tier))
    except Exception:  # noqa: BLE001 — a hint that cannot be read is no hint
        return None, False
    if not raw:
        return None, done
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    stamp, _, event_id = str(raw).partition("|")
    try:
        parsed = datetime.fromisoformat(stamp)
        # Half a keyset is not a position — refuse it rather than key on the
        # timestamp alone and step over a tied cohort.
        parsed_id = int(event_id)
    except (TypeError, ValueError):
        return None, done
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed, parsed_id), done


def _write_checkpoint(tier: str, cursor: Optional[tuple], *, exhausted: bool) -> None:
    """Persist the position, and mark the tier done when its scan ran out.

    Marking done is what lets a re-trigger reach the NEXT tier instead of
    restarting this one. It is deliberately not the same thing as clearing the
    cursor, which live/035's ring sweep does — that sweep wraps forever because it
    is steady-state, and this one is a drain that must be able to finish.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if cursor is not None:
            stamp, event_id = cursor
            client.set(
                CHECKPOINT_KEY.format(tier=tier),
                f"{stamp.isoformat()}|{int(event_id)}",
            )
        if exhausted:
            client.set(TIER_DONE_KEY.format(tier=tier), "1")
    except Exception:  # noqa: BLE001 — losing the hint costs a re-scan, not a row
        logger.warning(
            "30d chart drain: checkpoint for tier %s not persisted", tier,
            exc_info=True,
        )


def reset_checkpoints() -> dict:
    """Forget every tier's position. For a re-run from the top, by hand."""
    cleared = []
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        for tier in TIERS:
            client.delete(CHECKPOINT_KEY.format(tier=tier.name))
            client.delete(TIER_DONE_KEY.format(tier=tier.name))
            cleared.append(tier.name)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:160], "cleared": cleared}
    return {"status": "reset", "cleared": cleared}


# ---------------------------------------------------------------------------
# The drain
# ---------------------------------------------------------------------------


async def _drain_events(
    session, event_ids: Sequence[int], *,
    kalshi_service, polymarket_service,
    min_period_minutes: Optional[int], dry_run: bool, summary: dict,
) -> str:
    """Fill each event, committing per event. Returns why the loop ended.

    Per-event commit, not one transaction over the page: a network drain that
    dies on item 40 must keep the 39 curves it already drew (gotcha #13's shape).
    One bad event never costs its siblings (gotcha #42) — the per-source guard is
    inside `backfill_event_chart`, and this adds the per-EVENT one around it.
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.tasks.event_chart_backfill import backfill_event_chart

    consecutive_errors = 0
    for event_id in event_ids:
        event = (
            await session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one_or_none()
        if event is None:
            summary["not_found"] += 1
            continue
        try:
            verdict = await backfill_event_chart(
                session, event,
                kalshi_service=kalshi_service,
                polymarket_service=polymarket_service,
                dry_run=dry_run,
                min_period_minutes=min_period_minutes,
            )
        except Exception as exc:  # noqa: BLE001 — one event, not the drain
            consecutive_errors += 1
            summary["errors"].append(f"{event_id}: {str(exc)[:120]}")
            logger.warning("30d chart drain: event %s failed", event_id, exc_info=True)
            if consecutive_errors >= CONSECUTIVE_ERROR_ABORT:
                return "consecutive_errors"
            continue

        consecutive_errors = 0
        summary["events_processed"] += 1
        summary["points_written"] += verdict["points_written"]
        if verdict["points_written"]:
            summary["events_written"] += 1
        _tally(summary, verdict)
        if verdict["errors"]:
            summary["errors"].extend(verdict["errors"][:2])

        if not dry_run:
            await session.commit()
        if INTER_EVENT_SLEEP_SECONDS:
            await asyncio.sleep(INTER_EVENT_SLEEP_SECONDS)
    return "page_complete"


def _tally(summary: dict, verdict: dict) -> None:
    """Fold one event's verdict into the running WHY-IT-DID-NOT-FILL census.

    This is the half of the report Alex asked for by name — "events still empty
    and WHY". A drain that reports only its successes cannot tell a resolver gap
    from a purged venue from a market we cannot orient, and those three want
    three different owners.
    """
    if verdict.get("status") == "no_linked_markets":
        summary["reasons"]["no_linked_markets"] += 1
        return
    filled_any = False
    for source, stats in verdict.get("sources", {}).items():
        status = stats.get("status")
        if status == "written":
            filled_any = True
            summary["by_source"][source] = summary["by_source"].get(source, 0) + (
                stats.get("points_written") or 0
            )
            continue
        if status:
            summary["reasons"][f"{source}:{status}"] += 1
        for signal in ("purged", "api_empty", "no_token_id"):
            if stats.get(signal):
                summary["reasons"][f"{source}:{signal}"] += stats[signal]
    if not filled_any and verdict.get("status") != "no_linked_markets":
        summary["still_empty"] += 1


def _new_summary() -> dict:
    import collections

    return {
        "events_processed": 0,
        "events_written": 0,
        "points_written": 0,
        "still_empty": 0,
        "not_found": 0,
        "by_source": {},
        "reasons": collections.Counter(),
        "errors": [],
        "tiers": {},
    }


async def run_thirty_day_chart_drain(
    *,
    limit: int = 200,
    dry_run: bool = False,
    min_period_minutes: Optional[int] = None,
    only_tier: Optional[str] = None,
) -> dict:
    """Drain up to ``limit`` fillable events, highest-priority tier first.

    Resumable and idempotent. Re-trigger until the verdict reports
    ``status: "drained"`` — that is the only thing that means finished. Anything
    else, including a clean-looking page that wrote zero points, means there is
    more behind it (gotcha #53 / `task_verdict`: "it returned" is not
    "it worked").
    """
    from app.services.kalshi_api import KalshiAPIService
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session

    summary = _new_summary()
    summary["window_days"] = THIRTY_DAY_WINDOW_DAYS
    summary["thin_below_points"] = THIRTY_DAY_THIN_POINTS
    summary["dry_run"] = dry_run

    remaining = max(1, limit)
    kalshi_service = KalshiAPIService()
    polymarket_service = PolymarketAPIService()
    stopped = None
    try:
        async with get_task_session() as session:
            buckets = await tier_sport_ids(session)
            for tier in TIERS:
                if only_tier and tier.name != only_tier:
                    continue
                if remaining <= 0:
                    break
                after, done = _read_checkpoint(tier.name)
                if done:
                    summary["tiers"][tier.name] = {"status": "already_drained"}
                    continue

                page = await select_thirty_day_page(
                    session, sport_ids=buckets[tier.name],
                    limit=remaining, after=after,
                )
                tier_report = {
                    "why": tier.why,
                    "sports": len(buckets[tier.name]),
                    "scanned": page.scanned,
                    "fillable": len(page.event_ids),
                    "resumed_from": _label(after),
                }
                if page.event_ids:
                    stopped = await _drain_events(
                        session, page.event_ids,
                        kalshi_service=kalshi_service,
                        polymarket_service=polymarket_service,
                        min_period_minutes=min_period_minutes,
                        dry_run=dry_run, summary=summary,
                    )
                    remaining -= len(page.event_ids)
                # The cursor is written even when the page filled nothing: those
                # candidates WERE judged, and not advancing past them is how a
                # drain re-reads the same head forever.
                if not dry_run:
                    _write_checkpoint(
                        tier.name, page.next_cursor, exhausted=page.exhausted
                    )
                tier_report["advanced_to"] = _label(page.next_cursor)
                tier_report["exhausted"] = page.exhausted
                tier_report["status"] = "drained" if page.exhausted else "in_progress"
                summary["tiers"][tier.name] = tier_report
                if stopped == "consecutive_errors":
                    summary["aborted"] = "consecutive_errors"
                    break
    finally:
        for service in (kalshi_service, polymarket_service):
            try:
                await service.close()
            except Exception:  # noqa: BLE001 — closing must never mask the run
                pass

    summary["reasons"] = dict(summary["reasons"])
    summary["errors"] = summary["errors"][:20]
    summary["status"] = _verdict(summary, only_tier=only_tier)
    if summary["status"] != "drained":
        logger.info(
            "30d chart drain: %s events, %s points, %s still empty — RE-TRIGGER, "
            "the window is not drained yet",
            summary["events_processed"], summary["points_written"],
            summary["still_empty"],
        )
    return summary


def _verdict(summary: dict, *, only_tier: Optional[str]) -> str:
    """`drained` ONLY when every tier in scope says so.

    A page that returned cleanly having written nothing looks exactly like a
    finished drain unless something asserts the difference, so this asserts it.
    """
    if summary.get("aborted"):
        return "aborted"
    scope = [t.name for t in TIERS if not only_tier or t.name == only_tier]
    seen = summary.get("tiers", {})
    if all(
        seen.get(name, {}).get("status") in ("drained", "already_drained")
        for name in scope
    ):
        return "drained"
    return "in_progress"


def _label(cursor: Optional[tuple]) -> Optional[str]:
    """A keyset position, readable in a verdict. Both halves or neither."""
    if not cursor:
        return None
    stamp, event_id = cursor
    return f"{stamp.isoformat()}|{event_id}"
