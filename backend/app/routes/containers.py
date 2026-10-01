"""`GET /api/containers/{slug}` — one container, its members, by section.

#2927 Phase 4. The generic read path the hub flips to once container output
covers what the register renders (spec §5 M4). Until then it is behind
``CONTAINERS_READ_ENABLED`` and serves 404, so the route can ship, be exercised
and be measured without any user reaching a half-assembled hub.

THE HUB READS SECTIONS; IT DOES NOT CLASSIFY. Every member arrives with the
class that was computed once at assembly and stored on its edge (doctrine
§C.4). Three consumers re-deriving a class is how six sections become four in
one place and eight in another, so this route does no classification at all —
it groups by a column.

`unclassified` IS RETURNED, ALWAYS, AND LAST. A member we could not classify is
a member we would otherwise silently lose, which is the failure this program
exists to end. It is never filtered out here and never folded into another
section; it gets the last slot so a hub can render it as a trailing group or a
count without deciding to hide it.

WHY THE FLAG DEFAULTS TO OFF. A container that has not been assembled yet
returns an honest 404 rather than an empty hub. An empty section list rendered
as a page is indistinguishable, from outside, from a tournament with nothing
on — and #2215's empty-card lesson is that the fail-closed direction is the
only safe one.

#9636 — A READER SEES ONLY A PUBLISHED COLLECTION, AS CARDS IT ALREADY KNOWS.
Membership now comes from ``read_published`` (#9651), which returns the
revision and the members from ONE statement, so a payload can never pair
revision N with revision N+1's members. The route never re-reads membership.
Only ``published`` carries members; ``unpublished`` (the default, and every
state this code has not heard of), ``withdrawn`` and ``empty`` are explicit 200
states with no members, and a slug with no collection is a 404 that names its
state. Every member is then batch-hydrated through the serializers the events
list and search already serve (a constant number of queries, however many
members), and a member whose row is gone is WITHHELD WITH A REASON — never a
card we invented and never a link to a page that does not exist. The pure half
lives in ``app.utils.container_presentation``.

#9982 — THE PUBLISHED READ IS LIVE; THE CARDS BEHIND IT ARE CACHED. Week 4's
3,479 members took ~5 s to hydrate on every request. The published read still
runs every time and names the revision; the hydrated, rendered body is cached
per (slug, revision) and ages on the Discover feed's clock — see
``app.utils.container_read_cache`` and the section at the end of this file.
``CONTAINERS_READ_CACHE_ENABLED=false`` is the kill switch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.utils.container_corrections import (
    READ_EMPTY,
    READ_PUBLISHED,
    READ_UNAVAILABLE,
    read_published,
)
from app.utils.container_graph import CLASS_UNCLASSIFIED, EDGE_CLASSES
from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    WITHHELD_UNSERIALIZABLE,
    container_destination,
    edition_for_slug,
    present_sections,
)
from app.utils.container_read_cache import (
    CachedRead,
    container_read_cache_enabled,
    container_read_cache_key,
    decode_entry,
    encode_entry,
    payload_deadlines,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Containers"])


def containers_read_enabled() -> bool:
    """Read at call time, not at import.

    A module-level constant would freeze the flag at dyno boot, so turning the
    hub on would need a restart — and a flag you have to restart to flip is a
    flag nobody flips during an incident.
    """
    return os.getenv("CONTAINERS_READ_ENABLED", "false").lower() == "true"


#: The order sections are rendered in. Explicit rather than alphabetical: the
#: hub's first screen should be the draw, not the props.
#:
#: `unclassified` is pinned LAST by construction below rather than by sitting
#: last in this tuple, so a future edit that reorders these cannot accidentally
#: promote it above a real section.
CLASS_ORDER = (
    "match_winner",
    "doubles",
    "advancement",
    "title",
    "prop",
    "side_question",
)


def order_classes(present: set) -> list:
    """Named sections in policy order, then anything new, then unclassified.

    The middle term matters: a class added to the vocabulary and not to
    ``CLASS_ORDER`` still renders, at the end but before `unclassified`. The
    alternative — dropping it — would make adding a class a silent way to hide
    a whole section, which is the same failure as dropping a member.
    """
    ordered = [c for c in CLASS_ORDER if c in present]
    extras = sorted(present - set(CLASS_ORDER) - {CLASS_UNCLASSIFIED})
    tail = [CLASS_UNCLASSIFIED] if CLASS_UNCLASSIFIED in present else []
    return ordered + extras + tail


async def _hydrate_event_cards(db: AsyncSession, event_ids: list) -> tuple[dict, dict]:
    """``({event_id: card}, {("event", id): reason})`` in a constant query count.

    The card is ``GET /api/events``' card, built by the same calls in the same
    order (odds → EI percentiles → team lookup → fold → venue settlement), so a
    hub card and a list card of one game cannot disagree. The page-level
    duplicate drains of the list are deliberately NOT applied: membership was
    decided by assembly on the authority's ids, and a reader route that dropped
    members would be a second, unaudited membership rule.
    """
    if not event_ids:
        return {}, {}
    from collections import defaultdict
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Event
    from app.routes.events import (
        _build_team_lookup,
        _filter_stale_bookmaker_snapshots,
        _format_event_with_aggregated_odds,
        _load_gei_percentiles,
        aggregate_bookmaker_odds,
        detect_reversed_bookmakers,
        latest_odds_per_bookmaker_query,
    )
    from app.utils.proven_duplicates import folded_card_numbers_batch
    from app.utils.venue_settlement_reader import attach_venue_settlement

    events = (
        await db.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(Event.id.in_(event_ids))
            .order_by(Event.id)
        )
    ).scalars().all()
    if not events:
        return {}, {}

    snapshots_by_event: dict = defaultdict(list)
    for snap in (
        await db.execute(latest_odds_per_bookmaker_query([e.id for e in events]))
    ).scalars().all():
        snapshots_by_event[snap.event_id].append(snap)

    by_id = {e.id: e for e in events}
    odds_map: dict = {}
    for event_id, snaps in snapshots_by_event.items():
        ev = by_id.get(event_id)
        filtered = _filter_stale_bookmaker_snapshots(
            snaps,
            event_status=(ev.status if ev else "scheduled"),
            commence_time=(ev.commence_time if ev else None),
        )
        reversed_bks = detect_reversed_bookmakers(filtered)
        agg = [s for s in filtered if s.bookmaker not in reversed_bks] if reversed_bks else filtered
        odds_map[event_id] = {
            "snapshots": filtered,
            "all_snapshots": snaps,
            "aggregated": aggregate_bookmaker_odds(agg if agg else filtered),
            "captured_at": max(s.captured_at for s in filtered) if filtered else None,
        }

    gei_percentiles = await _load_gei_percentiles(db)
    names = {n for e in events for n in (e.home_team_name, e.away_team_name) if n}
    team_lookup = await _build_team_lookup(db, sorted(names))
    folded_map = await folded_card_numbers_batch(db, events)

    cards: dict = {}
    failed: dict = {}
    formatted_events = []
    formatted = []
    for e in events:
        folded = folded_map.get(e.id)
        # Gotcha #42: one row the serializer cannot draw is withheld with a
        # reason; it never takes the rest of the hub down with it.
        try:
            card = _format_event_with_aggregated_odds(
                e,
                odds_map.get(e.id),
                gei_percentiles,
                team_lookup=team_lookup,
                folded_sources=folded.win_probability_sources if folded is not None else None,
                folded_opening=folded.opening if folded is not None else None,
            )
        except Exception:  # noqa: BLE001 — per-item guard, logged loudly
            logger.exception("container hub: event %s card failed", e.id)
            failed[(MEMBER_EVENT, int(e.id))] = WITHHELD_UNSERIALIZABLE
            continue
        formatted_events.append(e)
        formatted.append(card)
        cards[int(e.id)] = card

    await attach_venue_settlement(db, formatted_events, formatted, datetime.now(timezone.utc))
    return cards, failed


async def _hydrate_market_cards(
    db: AsyncSession, market_ids: list
) -> tuple[dict, dict, dict]:
    """``({market_id: card}, {market_id: event_id}, failures)``, constant queries.

    The card is search's futures card (``_format_futures_for_search``) with
    #6993's withheld-price set computed for ALL boards in one pass
    (``withheld_price_outcome_ids_for_markets``, at most four queries), so a hub
    card never prints a price its own page refuses. A board whose withheld set
    could not be computed is served unscreened, exactly as search serves it.
    """
    if not market_ids:
        return {}, {}, {}
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import FuturesMarket
    from app.routes.events import _format_futures_for_search
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    markets = (
        await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.sport), selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id.in_(market_ids))
            .order_by(FuturesMarket.id)
        )
    ).scalars().all()
    if not markets:
        return {}, {}, {}

    withheld = await withheld_price_outcome_ids_for_markets(db, markets)
    cards: dict = {}
    event_ids: dict = {}
    failed: dict = {}
    for m in markets:
        try:
            card = _format_futures_for_search(m, withheld.get(m.id))
        except Exception:  # noqa: BLE001 — per-item guard (gotcha #42)
            logger.exception("container hub: market %s card failed", m.id)
            failed[(MEMBER_MARKET, int(m.id))] = WITHHELD_UNSERIALIZABLE
            continue
        cards[int(m.id)] = card
        event_ids[int(m.id)] = int(m.event_id) if m.event_id is not None else None
    return cards, event_ids, failed


def _state_payload(published, edition: Optional[dict]) -> dict:
    """The fields every 200 carries, whatever the state."""
    return {
        "state": published.state,
        "slug": published.slug,
        "revision": published.revision,
        "reason": published.reason,
        "edition": edition,
    }


def _container_header(row) -> dict:
    return {
        "id": int(row[0]),
        "kind": row[1],
        "name": row[2],
        "slug": row[3],
        "category": row[4],
        "status": row[5],
        "window_start": row[6].isoformat() if row[6] else None,
        "window_end": row[7].isoformat() if row[7] else None,
        "parent_container_id": int(row[8]) if row[8] is not None else None,
    }


@router.get("/discover")
async def get_discoverable_containers(
    league: Optional[Literal["nfl", "mlb"]] = Query(None),
    season: int = Query(2026, ge=2000, le=2100),
    limit: int = Query(20, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Browse published NFL/MLB hubs using the shared discovery contract."""
    from app.services.container_discovery import discover_collections

    read = await discover_collections(db, league=league, season=season, limit=limit)
    return {"collections": read.collections}


@router.get("/{slug}")
async def get_container(
    slug: str = Path(..., min_length=1, max_length=200),
    include_children: bool = Query(
        True, description="Include members of nested containers (draws)."
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One published collection: header, nested collections, and its members as
    familiar cards grouped by class.

    ``include_children=false`` keeps only the collection's own members; the
    published read itself is unchanged, so the revision still covers the draws.
    """
    if not containers_read_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    published = await read_published(db, slug)
    if published.state == READ_UNAVAILABLE:
        raise HTTPException(
            status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug}
        )

    edition = edition_for_slug(slug)
    payload = _state_payload(published, edition)
    base_empty = {
        "container": None,
        "children": [],
        "sections": [],
        "member_count": 0,
        "withheld": [],
        "withheld_count": 0,
        "assembled": False,
        "known_classes": sorted(EDGE_CLASSES),
    }
    if published.state not in (READ_PUBLISHED, READ_EMPTY):
        # unpublished / withdrawn: nothing a reader could open, not even the
        # nested collections — no member and no path leaks out of a collection
        # that is not for readers.
        return {**payload, **base_empty}

    if not container_read_cache_enabled():
        return await _build_published_payload(db, published, include_children)
    return await _serve_cached(db, slug, published, include_children)


async def _build_published_payload(db: AsyncSession, published, include_children: bool) -> dict:
    """The full 200 for a ``published`` / ``empty`` read — the uncached build."""
    payload = _state_payload(published, edition_for_slug(published.slug))
    # Header and nested collections in ONE statement, keyed on the id the
    # published read returned (not the slug again), so both halves describe the
    # same row. A nested collection that is withdrawn is left out, matching the
    # published read, which leaves its members out.
    rows = (
        await db.execute(
            text(
                "SELECT id, kind, name, slug, category, status, "
                "       window_start, window_end, parent_container_id, "
                "       publication_state "
                "FROM containers "
                "WHERE id = :id "
                "   OR (parent_container_id = :id AND publication_state <> 'withdrawn') "
                "ORDER BY (id = :id) DESC, name, id"
            ),
            {"id": published.container_id},
        )
    ).fetchall()
    head = next((r for r in rows if int(r[0]) == published.container_id), None)
    child_rows = [r for r in rows if int(r[0]) != published.container_id]
    children = [
        {
            "id": int(c[0]),
            "kind": c[1],
            "name": c[2],
            "slug": c[3],
            "status": c[5],
            "publication_state": c[9],
            "edition": edition_for_slug(c[3]),
            # Only a published nested collection is a destination; any other
            # would open onto a state with nothing in it.
            "destination": container_destination(c[3]) if c[9] == READ_PUBLISHED else None,
        }
        for c in child_rows
    ]

    members = list(published.members)
    if not include_children:
        members = [m for m in members if m.get("container_id") == published.container_id]

    event_ids = sorted({int(m["id"]) for m in members if m.get("type") == MEMBER_EVENT})
    market_ids = sorted({int(m["id"]) for m in members if m.get("type") == MEMBER_MARKET})
    event_cards, event_failed = await _hydrate_event_cards(db, event_ids)
    market_cards, market_event_ids, market_failed = await _hydrate_market_cards(db, market_ids)

    sections, withheld = present_sections(
        members,
        event_cards=event_cards,
        market_cards=market_cards,
        market_event_ids=market_event_ids,
        failed={**event_failed, **market_failed},
        order_classes=order_classes,
        unclassified=CLASS_UNCLASSIFIED,
    )
    member_count = sum(s["count"] for s in sections)
    return {
        **payload,
        "container": _container_header(head) if head is not None else None,
        "children": children,
        "sections": sections,
        "member_count": member_count,
        "withheld": withheld,
        "withheld_count": len(withheld),
        # Kept for released readers of the pre-#9636 shape: true when the
        # published read returned any member at all, withheld or not.
        "assembled": bool(members),
        "known_classes": sorted(EDGE_CLASSES),
    }


# ---------------------------------------------------------------------------
# #9982 — the served bytes, cached per (slug, revision)
# ---------------------------------------------------------------------------
#
# Week 4 (3,479 members) took ~5 s to build on every request, and the web hub
# re-reads on every Back. The published read above stays on the request path —
# it is what names the revision — and only the hydration and rendering behind
# it are cached, keyed on that revision, so a republish is never served stale
# membership. Policy and envelope: ``app.utils.container_read_cache``.
#
# Two tiers: a small process-local one (a Back on the same worker costs
# nothing) and Redis (another worker's build is one GET away). Both fail OPEN —
# a Redis stall or a malformed entry means "build it", never an error. A stale
# entry inside its servable window is served at once and ONE rebuild runs in
# the background, so the next reader gets fresh cards without waiting.

#: A Week 4 body is ~3.5 MB raw, so the process-local tier stays small.
_LOCAL_MAX_ENTRIES = 4
_local_entries: dict = {}

#: How long a request waits on another request's in-flight build of the same
#: key before building itself — well under the web client's 12 s abort.
_COALESCE_WAIT_S = 8.0


def _render(payload: dict) -> bytes:
    """The bytes FastAPI's default ``JSONResponse`` renders for ``payload``.

    Rendered once per build instead of once per request; byte-identical to the
    uncached path (the same encoder, the same ``json.dumps`` arguments).
    """
    return json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
    ).encode("utf-8")


def _remember_local(key: str, entry: CachedRead) -> None:
    if key not in _local_entries and len(_local_entries) >= _LOCAL_MAX_ENTRIES:
        oldest = min(_local_entries, key=lambda k: _local_entries[k].built_at)
        _local_entries.pop(oldest, None)
    _local_entries[key] = entry


def _reset_read_cache_for_tests() -> None:
    _local_entries.clear()


async def _load_entry(key: str, now: float) -> tuple[Optional[CachedRead], bool]:
    """``(entry, from_shared)`` — the freshest servable copy of ``key``, or None."""
    local = _local_entries.get(key)
    if local is not None and local.is_fresh(now):
        return local, False
    if local is not None and not local.is_servable(now):
        _local_entries.pop(key, None)
        local = None

    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

    shared = None
    try:
        client = await get_shared_async_redis()
        res = await bounded_redis_call(lambda: client.get(key))
        if res.is_ok:
            shared = decode_entry(res.value)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — fail open: a cache read never fails a hub
        logger.debug("container hub cache: shared read failed for %s", key, exc_info=True)
    if shared is not None and not shared.is_servable(now):
        shared = None
    if shared is not None and (local is None or shared.built_at > local.built_at):
        _remember_local(key, shared)
        return shared, True
    return local, False


async def _publish_shared(key: str, entry: CachedRead) -> None:
    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

    ttl = max(1, int(math.ceil(entry.stale_until - time.time())))
    try:
        client = await get_shared_async_redis()
        await bounded_redis_call(
            lambda: client.set(key, encode_entry(entry), ex=ttl),
            treat_none_as_miss=False,
        )
    except Exception:  # noqa: BLE001 — publication is best-effort
        logger.debug("container hub cache: shared write failed for %s", key, exc_info=True)


def _store_entry(key: str, entry: CachedRead) -> None:
    from app.utils.request_cache import schedule_background

    _remember_local(key, entry)
    schedule_background(_publish_shared(key, entry))


async def _build_entry(db: AsyncSession, published, include_children: bool) -> CachedRead:
    # The age origin is when the build STARTED reading, not when it finished.
    built_at = time.time()
    payload = await _build_published_payload(db, published, include_children)
    fresh_until, stale_until = payload_deadlines(payload, built_at)
    return CachedRead(
        body=_render(payload), built_at=built_at, fresh_until=fresh_until, stale_until=stale_until
    )


def _cached_response(entry: CachedRead, label: str) -> Response:
    # `X-Feed-Cache` is the header the latency middleware buckets every route's
    # cache outcome by; the labels are from its allowlist.
    return Response(
        content=entry.body,
        media_type="application/json",
        headers={"X-Feed-Cache": label},
    )


async def _refresh_in_background(slug: str, include_children: bool, key: str, future) -> None:
    """Rebuild a stale entry on its own session.

    The caller claims ``future`` (``begin_build``) BEFORE scheduling this, so a
    burst of stale readers schedules one rebuild, not one per reader that
    arrived before the first task got to run.
    """
    from app.services.database import async_session_maker
    from app.utils.request_cache import finish_build

    result = None
    try:
        async with async_session_maker() as session:
            published = await read_published(session, slug)
            if published.state in (READ_PUBLISHED, READ_EMPTY):
                entry = await _build_entry(session, published, include_children)
                fresh_key = container_read_cache_key(slug, published.revision, include_children)
                _store_entry(fresh_key, entry)
                if fresh_key == key:
                    result = entry
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — the stale copy was already served
        logger.warning("container hub cache: background rebuild of %s failed", key, exc_info=True)
    finally:
        finish_build(key, future, result=result)


async def _serve_cached(db: AsyncSession, slug: str, published, include_children: bool) -> Response:
    from app.utils.request_cache import begin_build, finish_build, schedule_background

    key = container_read_cache_key(slug, published.revision, include_children)
    now = time.time()
    entry, from_shared = await _load_entry(key, now)
    if entry is not None and not entry.is_fresh(now):
        # The shared read awaited; a rebuild on this worker may have landed
        # meanwhile. Re-checked with no await between it and the claim below,
        # so a just-finished rebuild is served instead of started again.
        landed = _local_entries.get(key)
        if landed is not None and landed.is_fresh(now):
            entry, from_shared = landed, False
    if entry is not None:
        if entry.is_fresh(now):
            return _cached_response(entry, "shared_hit" if from_shared else "hit")
        leader, future = begin_build(key)
        if leader:
            schedule_background(_refresh_in_background(slug, include_children, key, future))
        return _cached_response(entry, "shared_stale_hit" if from_shared else "stale_hit")

    leader, future = begin_build(key)
    if not leader:
        try:
            joined = await asyncio.wait_for(asyncio.shield(future), timeout=_COALESCE_WAIT_S)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a timed-out or failed leader: build here
            joined = None
        if isinstance(joined, CachedRead):
            return _cached_response(joined, "coalesced")
        entry = await _build_entry(db, published, include_children)
        _store_entry(key, entry)
        return _cached_response(entry, "miss")

    entry = None
    try:
        entry = await _build_entry(db, published, include_children)
    finally:
        # Resolved on EVERY exit (request_cache's single-owner invariant); a
        # failed build hands waiters None and each builds for itself.
        finish_build(key, future, result=entry)
    _store_entry(key, entry)
    return _cached_response(entry, "miss")
