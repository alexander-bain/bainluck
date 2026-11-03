"""Generic round-up container registry, composer, route helper, and feed helper (#10357 Amendment 1).

PILLAR: DISCOVER · SHIP: any round-up card and the container it opens are
defined by one ``RoundupProducer`` entry in ``ROUNDUP_PRODUCERS``, served by one
generic branch in ``GET /api/containers/{slug}`` and composed by one pure
``compose_roundup_container(producer, members)`` function.

These registry fields (``slug``, ``name``, ``kind``, ``category``,
``section_title``, ``footer``, ``produce``) mirror the week-3 stored container
definition so moving from code to data is a storage change, not a shape change.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import time
import zlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_MARKET, market_destination

__all__ = [
    "ROUNDUP_CACHE_TTL_S",
    "ROUNDUP_PRODUCERS",
    "ROUNDUP_READ_BUDGET_SECONDS",
    "ROUNDUP_SEAT_FLOOR",
    "RoundupMembers",
    "RoundupProducer",
    "RoundupRefusal",
    "add_roundup_feed_items",
    "compose_roundup_container",
    "compose_roundup_feed_item",
    "evaluate_roundup_producer",
    "insert_roundup_feed_items",
    "register_roundup_producer",
    "reset_roundup_cache_for_tests",
    "roundup_container_id",
    "roundup_feed_enabled",
    "roundup_feed_items",
    "roundup_revision",
    "serve_roundup",
]

logger = logging.getLogger(__name__)

ROUNDUP_CACHE_TTL_S = 60.0
ROUNDUP_READ_BUDGET_SECONDS = 0.5
#: Oct 7–8 Discover opening ruling (#4080 / #5100 / #5105): seats 1–10 (indices
#: 0–9) are the dated why-now opening ten. Standing round-ups sit in page one's
#: back half starting at index 10 (seat 11), with no ranking change.
ROUNDUP_SEAT_FLOOR = 10

_roundup_local_cache: dict[
    tuple[str, Any], tuple[float, Optional[dict[str, Any]], Optional[dict[str, Any]]]
] = {}


@dataclass(frozen=True)
class RoundupMembers:
    """Ordered member cards and feed-card rows produced from a single read."""

    members: tuple[dict[str, Any], ...]
    rows: tuple[dict[str, Any], ...] = ()
    feed_item: Optional[dict[str, Any]] = None

    def __init__(
        self,
        members: Sequence[dict[str, Any]],
        rows: Sequence[dict[str, Any]] = (),
        *,
        feed_item: Optional[dict[str, Any]] = None,
    ) -> None:
        object.__setattr__(self, "members", tuple(members))
        object.__setattr__(self, "rows", tuple(rows))
        object.__setattr__(self, "feed_item", feed_item)


@dataclass(frozen=True)
class RoundupRefusal:
    """Why a round-up producer refused to emit a card and container."""

    reasons: tuple[Any, ...] = ()

    def __init__(self, reasons: Sequence[Any] = ()) -> None:
        object.__setattr__(self, "reasons", tuple(reasons))


@dataclass(frozen=True)
class RoundupProducer:
    """Definition of a computed round-up card and its throwaway container."""

    slug: str
    name: str
    kind: str
    category: str
    section_title: str
    footer: str
    produce: Callable[[Any], Any]
    tag: Optional[str] = None
    kicker: str = "Round-up"
    story_key: Optional[str] = None
    score: float = 0.0
    enabled: Optional[Callable[[], bool]] = None

    def __init__(
        self,
        slug: str,
        name: str,
        kind: str = "roundup",
        category: str = "",
        section_title: str = "",
        footer: str = "",
        produce: Optional[Callable[[Any], Any]] = None,
        *,
        tag: Optional[str] = None,
        kicker: str = "Round-up",
        story_key: Optional[str] = None,
        score: float = 0.0,
        enabled: Optional[Callable[[], bool]] = None,
    ) -> None:
        if produce is None:
            raise TypeError("RoundupProducer requires a 'produce' callable")
        object.__setattr__(self, "slug", str(slug))
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "kind", str(kind or "roundup"))
        object.__setattr__(self, "category", str(category))
        object.__setattr__(self, "section_title", str(section_title))
        object.__setattr__(self, "footer", str(footer))
        object.__setattr__(self, "produce", produce)
        object.__setattr__(
            self,
            "tag",
            tag if tag is not None else str(category).upper(),
        )
        object.__setattr__(self, "kicker", str(kicker or "Round-up"))
        object.__setattr__(
            self,
            "story_key",
            story_key or f"roundup:{str(slug).removeprefix('roundup-')}",
        )
        object.__setattr__(self, "score", float(score))
        object.__setattr__(self, "enabled", enabled)


def roundup_container_id(slug: str) -> int:
    """Stable synthetic positive int derived from the slug (CRC32)."""
    cid = zlib.crc32(str(slug).encode("utf-8")) & 0xFFFFFFFF
    return cid if cid > 0 else 1


def roundup_revision(member_ids: Sequence[int]) -> int:
    """Stable positive integer from the ordered member ids (CRC32 of comma-joined ids).

    Changes when the shown members or their order change, and only then;
    prices moving never bump it.
    """
    joined = ",".join(str(int(mid)) for mid in member_ids)
    rev = zlib.crc32(joined.encode("utf-8")) & 0xFFFFFFFF
    return rev if rev > 0 else 1


def _normalize_member_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Ensure a member entry carries the container section's member envelope."""
    if "card" in entry and "destination" in entry and "id" in entry:
        mid = int(entry["id"])
        return {
            "type": entry.get("type") or MEMBER_MARKET,
            "id": mid,
            "destination": entry["destination"],
            "card": entry["card"],
            "event_id": entry.get("event_id"),
        }
    mid = int(entry["id"])
    return {
        "type": MEMBER_MARKET,
        "id": mid,
        "destination": market_destination(mid),
        "card": dict(entry),
        "event_id": None,
    }


def compose_roundup_container(
    producer: RoundupProducer,
    members: RoundupMembers | Sequence[Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Pure composer building §4's container payload from ``producer`` and ``members``."""
    raw_members = (
        members.members if isinstance(members, RoundupMembers) else tuple(members)
    )
    if not raw_members:
        return None
    normalized = [_normalize_member_entry(m) for m in raw_members]
    member_ids = [int(m["id"]) for m in normalized]
    return {
        "state": "published",
        "slug": producer.slug,
        "revision": roundup_revision(member_ids),
        "reason": None,
        "edition": None,
        "container": {
            "id": roundup_container_id(producer.slug),
            "slug": producer.slug,
            "name": producer.name,
            "kind": producer.kind,
            "category": producer.category,
            "status": "open",
            "window_start": None,
            "window_end": None,
            "parent_container_id": None,
        },
        "subtitle": producer.footer,
        "sections": [
            {
                "class": "title",
                "title": producer.section_title,
                "layout": "field",
                "count": len(normalized),
                "members": normalized,
            }
        ],
        "member_count": len(normalized),
        "withheld": [],
        "withheld_count": 0,
        "children": [],
        "assembled": True,
    }


def compose_roundup_feed_item(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> Optional[dict[str, Any]]:
    """Build the Discover feed item for a round-up producer from its produced members."""
    if not members.members:
        return copy.deepcopy(members.feed_item) if members.feed_item is not None else None
    rows = list(members.rows)
    normalized = [_normalize_member_entry(x) for x in members.members]
    member_ids = [int(m["id"]) for m in normalized]
    item_id = producer.story_key or f"roundup:{producer.slug.removeprefix('roundup-')}"
    base_score = (
        float(members.feed_item.get("score", producer.score) or 0.0)
        if isinstance(members.feed_item, Mapping)
        else float(producer.score)
    )
    member_items = [
        {
            "type": "futures",
            "score": base_score,
            "reason": str(
                (
                    rows[idx].get("label")
                    if idx < len(rows) and isinstance(rows[idx], Mapping)
                    else None
                )
                or producer.name
            ),
            "headline": str(
                (
                    rows[idx].get("label")
                    if idx < len(rows) and isinstance(rows[idx], Mapping)
                    else None
                )
                or producer.name
            ),
            "data": dict(m["card"]),
        }
        for idx, m in enumerate(normalized)
        if isinstance(m.get("card"), Mapping)
    ]
    collection_ref = {
        "slug": producer.slug,
        "href": f"/collections/{producer.slug}",
        "name": producer.name,
        "revision": roundup_revision(member_ids),
        "collection_count": len(member_ids),
    }
    if members.feed_item is not None:
        out = copy.deepcopy(members.feed_item)
        if isinstance(out.get("data"), dict):
            out["data"]["items"] = member_items
            out["data"]["collection_ref"] = collection_ref
        return out
    return {
        "type": "bundle",
        "score": base_score,
        "reason": producer.name,
        "headline": producer.name,
        "context_summary": None,
        "data": {
            "id": item_id,
            "title": producer.name,
            "kind": producer.kind,
            "story_key": item_id,
            "shared_question": None,
            "item_count": len(member_ids),
            "member_ids": member_ids,
            "items": member_items,
            "collection_ref": collection_ref,
            "roundup": {
                "kicker": producer.kicker,
                "tag": producer.tag or producer.category.upper(),
                "footer": producer.footer,
                "rows": rows,
            },
        },
    }


def _redis_cache_key(slug: str) -> str:
    return f"container_read:v1:{slug}"


def reset_roundup_cache_for_tests() -> None:
    _roundup_local_cache.clear()


async def evaluate_roundup_producer(
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Run ``producer`` once and return ``(feed_item, container_payload)``, cached 60s per slug."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    if producer.enabled is not None and not producer.enabled():
        return None, None

    is_fixture_seq = isinstance(db, (list, tuple))
    ts = time.time() if now is None else float(now)
    use_cache = not is_fixture_seq and container_read_cache_enabled()
    cache_key = (
        producer.slug,
        "live" if isinstance(db, AsyncSession) else id(db),
    )

    if use_cache:
        cached = _roundup_local_cache.get(cache_key)
        if cached is not None and (ts - cached[0]) < ROUNDUP_CACHE_TTL_S:
            return copy.deepcopy(cached[1]), copy.deepcopy(cached[2])
        if isinstance(db, AsyncSession):
            try:
                from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

                client = await get_shared_async_redis()
                res = await bounded_redis_call(
                    lambda: client.get(_redis_cache_key(producer.slug))
                )
                if res.is_ok and res.value:
                    raw = json.loads(
                        res.value.decode("utf-8")
                        if isinstance(res.value, (bytes, bytearray))
                        else res.value
                    )
                    if (
                        isinstance(raw, dict)
                        and isinstance(raw.get("built_at"), (int, float))
                        and (ts - float(raw["built_at"])) < ROUNDUP_CACHE_TTL_S
                    ):
                        fi = raw.get("feed_item")
                        cp = raw.get("container_payload")
                        _roundup_local_cache[cache_key] = (
                            float(raw["built_at"]),
                            fi,
                            cp,
                        )
                        return copy.deepcopy(fi), copy.deepcopy(cp)
            except Exception:  # noqa: BLE001 — cache read fails open
                logger.debug(
                    "roundup_containers: shared cache read failed for %s",
                    producer.slug,
                    exc_info=True,
                )

    outcome = producer.produce(db)
    if inspect.isawaitable(outcome):
        outcome = await outcome

    if outcome is None or isinstance(outcome, RoundupRefusal):
        reasons = list(outcome.reasons) if isinstance(outcome, RoundupRefusal) else []
        logger.warning(
            "flow_sentinel matching_defect: roundup %s refused reasons=%s",
            producer.slug,
            reasons,
        )
        return None, None

    if not isinstance(outcome, RoundupMembers):
        outcome = RoundupMembers(outcome)

    container_payload = compose_roundup_container(producer, outcome)
    feed_item = compose_roundup_feed_item(producer, outcome)
    if container_payload is None or feed_item is None:
        return None, None

    if use_cache:
        _roundup_local_cache[cache_key] = (
            ts,
            copy.deepcopy(feed_item),
            copy.deepcopy(container_payload),
        )
        if isinstance(db, AsyncSession):
            try:
                from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

                encoded = json.dumps(
                    {
                        "built_at": ts,
                        "feed_item": feed_item,
                        "container_payload": container_payload,
                    },
                    separators=(",", ":"),
                )
                client = await get_shared_async_redis()
                await bounded_redis_call(
                    lambda: client.set(
                        _redis_cache_key(producer.slug),
                        encoded,
                        ex=int(ROUNDUP_CACHE_TTL_S),
                    ),
                    treat_none_as_miss=False,
                )
            except Exception:  # noqa: BLE001 — cache write is best-effort
                logger.debug(
                    "roundup_containers: shared cache write failed for %s",
                    producer.slug,
                    exc_info=True,
                )

    return feed_item, container_payload


async def serve_roundup(slug: str, db: Any) -> dict[str, Any]:
    """Serve a registered round-up container, or raise 404 ``{state: unavailable, slug}``."""
    from fastapi import HTTPException

    from app.utils.container_corrections import READ_UNAVAILABLE

    producer = ROUNDUP_PRODUCERS.get(slug)
    if producer is None:
        raise HTTPException(
            status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug}
        )
    _feed_item, payload = await evaluate_roundup_producer(producer, db)
    if payload is None:
        raise HTTPException(
            status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug}
        )
    return payload


async def roundup_feed_items(db: Any) -> list[dict[str, Any]]:
    """Evaluate every registered producer and return feed cards whose containers would be served."""
    items: list[dict[str, Any]] = []
    for producer in list(ROUNDUP_PRODUCERS.values()):
        feed_item, container_payload = await evaluate_roundup_producer(producer, db)
        if feed_item is not None and container_payload is not None:
            items.append(feed_item)
    return items


def roundup_feed_enabled(
    *,
    mode: Optional[str],
    include_events: bool = True,
    include_futures: bool = True,
    my_teams_only: bool = False,
    debug: bool = False,
    category: Optional[str] = None,
    sport: Optional[str] = None,
) -> bool:
    """Whether Discover should place registered round-up cards on the canonical feed."""
    from app.routes.containers import containers_read_enabled

    return (
        (mode or "discover").lower() == "discover"
        and bool(include_events)
        and bool(include_futures)
        and not my_teams_only
        and not debug
        and not category
        and not sport
        and containers_read_enabled()
        and any(
            p.enabled is None or p.enabled() for p in ROUNDUP_PRODUCERS.values()
        )
    )


def _roundup_covered_market_ids(roundup_item: Mapping[str, Any]) -> set[int]:
    """All market IDs (shown and paired across venues) represented by ``roundup_item``."""
    data = roundup_item.get("data")
    if not isinstance(data, Mapping):
        return set()
    covered: set[int] = set()
    for mid in data.get("member_ids") or ():
        if isinstance(mid, int) and not isinstance(mid, bool):
            covered.add(int(mid))
    roundup = data.get("roundup")
    if isinstance(roundup, Mapping):
        for row in roundup.get("rows") or ():
            if not isinstance(row, Mapping):
                continue
            rmid = row.get("market_id")
            if isinstance(rmid, int) and not isinstance(rmid, bool):
                covered.add(int(rmid))
            pair = row.get("pair")
            if isinstance(pair, Mapping):
                for k in ("kalshi_market_id", "polymarket_market_id"):
                    pmid = pair.get(k)
                    if isinstance(pmid, int) and not isinstance(pmid, bool):
                        covered.add(int(pmid))
    return covered


def insert_roundup_feed_items(
    items: list[dict[str, Any]],
    roundup_items: Sequence[dict[str, Any]],
    *,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    page_window: int = 20,
) -> list[dict[str, Any]]:
    """Place served round-up cards on Discover after the opening ten without changing scores.

    Under the Oct 7–8 ranking rulings (#4080 / #5100 / #5105 / #10356 / #10357):
    * Seats 1–10 (indices ``0..seat_floor-1``) remain the untouched why-now opening ten.
    * Any standalone ``futures`` card whose market id is represented by the round-up
      is suppressed so no market appears twice on the feed.
    * Each round-up card is seated in page one's back half starting at ``seat_floor``
      (or at its earliest replaced member's seat when ``>= seat_floor``), inheriting
      the neighbour's score at that seat without modifying any card's score.
    """
    if not items or not roundup_items:
        return items

    valid_roundups = [
        r
        for r in roundup_items
        if isinstance(r, Mapping)
        and isinstance(r.get("data"), Mapping)
        and r["data"].get("collection_ref")
    ]
    if not valid_roundups:
        return items

    result = list(items)
    existing_bundle_ids = {
        it.get("data", {}).get("id")
        for it in result
        if isinstance(it, Mapping)
        and it.get("type") == "bundle"
        and isinstance(it.get("data"), Mapping)
    }

    inserted_count = 0
    changed = False
    for r_item in valid_roundups:
        r_id = r_item["data"].get("id")
        if r_id in existing_bundle_ids:
            continue

        covered_ids = _roundup_covered_market_ids(r_item)
        earliest_post_opening_seat: Optional[int] = None
        if covered_ids:
            filtered: list[dict[str, Any]] = []
            for idx, existing in enumerate(result):
                if (
                    isinstance(existing, Mapping)
                    and existing.get("type") == "futures"
                    and isinstance(existing.get("data"), Mapping)
                    and existing["data"].get("id") in covered_ids
                ):
                    changed = True
                    if (
                        earliest_post_opening_seat is None
                        and seat_floor <= idx < page_window
                    ):
                        earliest_post_opening_seat = idx
                    continue
                filtered.append(existing)
            result = filtered

        default_seat = seat_floor + inserted_count
        target_seat = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else default_seat
        )
        target_idx = min(max(seat_floor, target_seat), len(result))

        card = copy.deepcopy(dict(r_item))
        if result:
            anchor = result[target_idx] if target_idx < len(result) else result[-1]
            if not card.get("score"):
                card["score"] = float(anchor.get("score", 0.0) or 0.0)
            if "_rank_score" in anchor and "_rank_score" not in card:
                card["_rank_score"] = anchor["_rank_score"]
            if "_sort_time" in anchor and "_sort_time" not in card:
                card["_sort_time"] = anchor["_sort_time"]
            for child in card.get("data", {}).get("items") or ():
                if isinstance(child, dict) and not child.get("score"):
                    child["score"] = card["score"]

        result.insert(target_idx, card)
        existing_bundle_ids.add(r_id)
        inserted_count += 1
        changed = True

    return result if changed else items


async def add_roundup_feed_items(
    db: Any,
    items: list[dict[str, Any]],
    *,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    page_window: int = 20,
    budget_seconds: float = ROUNDUP_READ_BUDGET_SECONDS,
) -> list[dict[str, Any]]:
    """Evaluate registered round-up producers and place their cards on Discover."""
    if not items or len(items) < seat_floor or budget_seconds <= 0:
        return items
    try:
        produced = await asyncio.wait_for(
            roundup_feed_items(db),
            timeout=min(budget_seconds, ROUNDUP_READ_BUDGET_SECONDS),
        )
    except Exception:
        if hasattr(db, "rollback") and callable(db.rollback):
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.warning(
            "Discover round-up read failed; keeping ordinary cards", exc_info=True
        )
        return items

    if not produced:
        return items
    return insert_roundup_feed_items(
        items, produced, seat_floor=seat_floor, page_window=page_window
    )


ROUNDUP_PRODUCERS: dict[str, RoundupProducer] = {}


def register_roundup_producer(producer: RoundupProducer) -> RoundupProducer:
    """Register a ``RoundupProducer`` by its slug."""
    ROUNDUP_PRODUCERS[producer.slug] = producer
    return producer


def _register_builtin_producers() -> None:
    import app.utils.discover_bundles as _bundles

    producer = getattr(_bundles, "NFL_DIVISION_ROUNDUP_PRODUCER", None)
    if producer is not None:
        register_roundup_producer(producer)


_register_builtin_producers()
