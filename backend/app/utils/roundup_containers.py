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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_MARKET, market_destination

__all__ = [
    "CLOSED_GROUPING_RELATIONS",
    "CLOSED_PERMISSION_LEVELS",
    "CONTAINERS_DATA_DIR",
    "HAND_LIST_ID_RULE_KEYS",
    "OCCASION_ID_RULE_KEYS",
    "ROUNDUP_CACHE_TTL_S",
    "ROUNDUP_PREWARM_STAGE_BUDGET_SECONDS",
    "ROUNDUP_PRODUCERS",
    "ROUNDUP_PRODUCER_TIMEOUT_SECONDS",
    "ROUNDUP_READ_BUDGET_SECONDS",
    "ROUNDUP_SEAT_FLOOR",
    "SELECTOR_RULE_KEYS",
    "RoundupMembers",
    "RoundupProducer",
    "RoundupRefusal",
    "add_roundup_feed_items",
    "build_roundup_producer_from_definition",
    "compose_roundup_container",
    "compose_roundup_feed_item",
    "evaluate_roundup_producer",
    "insert_roundup_feed_items",
    "load_roundup_definition",
    "load_roundup_definitions_from_dir",
    "register_roundup_definitions_from_dir",
    "register_roundup_producer",
    "reset_roundup_cache_for_tests",
    "roundup_container_id",
    "roundup_feed_enabled",
    "roundup_feed_items",
    "roundup_revision",
    "serve_roundup",
    "validate_roundup_definition",
]

logger = logging.getLogger(__name__)

CONTAINERS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "containers"

#: Closed list of grouping relations from ``docs/design/grouping-primitives.md`` (§2).
CLOSED_GROUPING_RELATIONS: frozenset[str] = frozenset(
    {
        "same_subject",
        "same_measure",
        "same_window",
        "same_event",
        "same_series",
        "twin",
        "sibling",
        "yardstick",
        "movement",
        "implies",
        "path",
        "by_when",
    }
)

#: Closed list of permission levels from ``docs/design/grouping-primitives.md`` (§2, Decide 71-A).
CLOSED_PERMISSION_LEVELS: frozenset[str] = frozenset(
    {
        "related",
        "member",
        "equivalent",
    }
)

#: Rule keys that select members by query/pattern/window (Decide 73-A).
SELECTOR_RULE_KEYS: tuple[str, ...] = (
    "title_ilike",
    "group_id",
    "deadline",
    "deadline_phrase",
    "domain",
    "window",
    "sport",
    "ceremony",
    "category_name",
    "subject",
    "selector",
)

#: Rule keys that name an occasion/field/register/anchor ("an id, never a member", Decide 73-A).
OCCASION_ID_RULE_KEYS: tuple[str, ...] = (
    "field",
    "field_external_id",
    "second_section",
    "second_section_external_id",
    "register",
    "anchor",
)

#: Rule keys that hold a hand-listed array of market IDs (Decide 73-A).
HAND_LIST_ID_RULE_KEYS: tuple[str, ...] = (
    "candidates",
    "market_ids",
    "winner_market_ids",
    "nomination_market_ids",
)

ROUNDUP_CACHE_TTL_S = 60.0
ROUNDUP_PRODUCER_TIMEOUT_SECONDS = 0.5
ROUNDUP_READ_BUDGET_SECONDS = 2.5
ROUNDUP_PREWARM_STAGE_BUDGET_SECONDS = 10.0
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
    footer: Optional[str] = None
    count_line: Optional[str] = None
    title: Optional[str] = None
    kicker: Optional[str] = None
    sections: tuple[dict[str, Any], ...] = ()
    revision_ids: tuple[int, ...] = ()

    def __init__(
        self,
        members: Sequence[dict[str, Any]],
        rows: Sequence[dict[str, Any]] = (),
        *,
        feed_item: Optional[dict[str, Any]] = None,
        footer: Optional[str] = None,
        count_line: Optional[str] = None,
        title: Optional[str] = None,
        kicker: Optional[str] = None,
        sections: Sequence[dict[str, Any]] = (),
        revision_ids: Sequence[int] = (),
    ) -> None:
        object.__setattr__(self, "members", tuple(members))
        object.__setattr__(self, "rows", tuple(rows))
        object.__setattr__(self, "feed_item", feed_item)
        object.__setattr__(
            self, "footer", str(footer) if footer is not None else None
        )
        object.__setattr__(
            self, "count_line", str(count_line) if count_line is not None else None
        )
        object.__setattr__(
            self, "title", str(title) if title is not None else None
        )
        object.__setattr__(
            self, "kicker", str(kicker) if kicker is not None else None
        )
        object.__setattr__(self, "sections", tuple(sections))
        object.__setattr__(
            self, "revision_ids", tuple(int(rid) for rid in revision_ids)
        )


@dataclass(frozen=True)
class RoundupRefusal:
    """Why a round-up producer refused to emit a card and container."""

    reasons: tuple[Any, ...] = ()

    def __init__(self, reasons: Sequence[Any] = ()) -> None:
        object.__setattr__(self, "reasons", tuple(reasons))


def _definition_window(
    rule: Mapping[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    """Calendar trigger shared by a kind's card and container (#11935, 65-A).

    Dates are reviewed definition parameters, never inferred from venue close
    dates. Windows include their start and exclude their end.
    """
    bounds = []
    for key in ("valid_from", "valid_until"):
        raw = rule.get(key)
        if raw is None:
            bounds.append(None)
            continue
        if not isinstance(raw, str):
            raise ValueError(f"{key} must be an ISO timestamp with a timezone")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.utcoffset() is None:
            raise ValueError(f"{key} must include a timezone")
        bounds.append(value.timestamp())
    start, end = bounds
    if start is not None and end is not None and start >= end:
        raise ValueError("valid_from must precede valid_until")
    return start, end


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
    section_titles: tuple[str, ...] = ()
    membership: str = "computed-produced"
    relations: tuple[str, ...] = ()
    level: str = "member"
    rule: Optional[dict[str, Any]] = None
    tag: Optional[str] = None
    kicker: str = "Round-up"
    story_key: Optional[str] = None
    score: float = 0.0
    enabled: Optional[Callable[[], bool]] = None
    valid_from: Optional[float] = None
    valid_until: Optional[float] = None

    def __init__(
        self,
        slug: str,
        name: str,
        kind: str = "roundup",
        category: str = "",
        section_title: str | Sequence[str] = "",
        footer: str = "",
        produce: Optional[Callable[[Any], Any]] = None,
        *,
        membership: str = "computed-produced",
        relations: Optional[Sequence[str]] = None,
        level: Optional[str] = None,
        rule: Optional[Mapping[str, Any]] = None,
        tag: Optional[str] = None,
        kicker: str = "Round-up",
        story_key: Optional[str] = None,
        score: float = 0.0,
        enabled: Optional[Callable[[], bool]] = None,
    ) -> None:
        if produce is None:
            raise TypeError("RoundupProducer requires a 'produce' callable")
        if isinstance(section_title, (list, tuple)):
            titles_tuple = tuple(str(t) for t in section_title if str(t))
            primary_title = titles_tuple[0] if titles_tuple else ""
        else:
            primary_title = str(section_title)
            titles_tuple = (primary_title,) if primary_title else ()
        raw_relations = (
            relations
            if relations is not None
            else (
                rule.get("relations")
                if isinstance(rule, Mapping)
                and isinstance(rule.get("relations"), (list, tuple))
                else ()
            )
        )
        relations_tuple = tuple(
            str(r).strip() for r in (raw_relations or ()) if str(r).strip()
        )
        raw_level = (
            level
            if level is not None
            else (
                rule.get("level")
                if isinstance(rule, Mapping) and isinstance(rule.get("level"), str)
                else "member"
            )
        )
        object.__setattr__(self, "slug", str(slug))
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "kind", str(kind or "roundup"))
        object.__setattr__(self, "category", str(category))
        object.__setattr__(self, "section_title", primary_title)
        object.__setattr__(self, "section_titles", titles_tuple)
        object.__setattr__(self, "footer", str(footer))
        object.__setattr__(self, "produce", produce)
        object.__setattr__(
            self, "membership", str(membership or "computed-produced")
        )
        object.__setattr__(self, "relations", relations_tuple)
        object.__setattr__(self, "level", str(raw_level or "member"))
        object.__setattr__(
            self, "rule", dict(rule) if isinstance(rule, Mapping) else None
        )
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
        start, end = _definition_window(rule or {})
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_until", end)


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


def _normalize_section_entry(
    section: Mapping[str, Any], default_title: str
) -> dict[str, Any]:
    raw_sec_members = section.get("members") or ()
    norm_members = [_normalize_member_entry(m) for m in raw_sec_members]
    return {
        "class": str(section.get("class") or "title"),
        "title": str(section.get("title") or default_title),
        "layout": str(section.get("layout") or "field"),
        "count": len(norm_members),
        "members": norm_members,
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
    rev_ids = (
        list(members.revision_ids)
        if isinstance(members, RoundupMembers) and members.revision_ids
        else member_ids
    )
    subtitle = (
        members.footer
        if isinstance(members, RoundupMembers) and members.footer
        else producer.footer
    )
    container_name = (
        members.title
        if isinstance(members, RoundupMembers) and members.title
        else producer.name
    )
    if isinstance(members, RoundupMembers) and members.sections:
        sections = [
            _normalize_section_entry(sec, producer.section_title)
            for sec in members.sections
        ]
        total_members = sum(len(sec["members"]) for sec in sections)
    else:
        sections = [
            {
                "class": "title",
                "title": producer.section_title,
                "layout": "field",
                "count": len(normalized),
                "members": normalized,
            }
        ]
        total_members = len(normalized)
    return {
        "state": "published",
        "slug": producer.slug,
        "revision": roundup_revision(rev_ids),
        "relations": list(producer.relations),
        "level": producer.level,
        "reason": None,
        "edition": None,
        "container": {
            "id": roundup_container_id(producer.slug),
            "slug": producer.slug,
            "name": container_name,
            "kind": producer.kind,
            "category": producer.category,
            "status": "open",
            "window_start": None,
            "window_end": None,
            "parent_container_id": None,
        },
        "subtitle": subtitle,
        "sections": sections,
        "member_count": total_members,
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
    rev_ids = list(members.revision_ids) if members.revision_ids else member_ids
    item_id = producer.story_key or f"roundup:{producer.slug.removeprefix('roundup-')}"
    footer = members.footer or producer.footer
    effective_title = members.title or producer.name
    effective_kicker = members.kicker or producer.kicker
    base_score = (
        float(members.feed_item.get("score", producer.score) or 0.0)
        if isinstance(members.feed_item, Mapping)
        else float(producer.score)
    )
    member_items = [
        {
            "type": "event" if m.get("type") == "event" else "futures",
            "score": base_score,
            "reason": str(
                (
                    rows[idx].get("label")
                    if idx < len(rows) and isinstance(rows[idx], Mapping)
                    else None
                )
                or effective_title
            ),
            "headline": str(
                (
                    rows[idx].get("label")
                    if idx < len(rows) and isinstance(rows[idx], Mapping)
                    else None
                )
                or effective_title
            ),
            "data": dict(m["card"]),
        }
        for idx, m in enumerate(normalized)
        if isinstance(m.get("card"), Mapping)
    ]
    collection_ref = {
        "slug": producer.slug,
        "href": f"/collections/{producer.slug}",
        "name": effective_title,
        "revision": roundup_revision(rev_ids),
        "collection_count": len(member_ids),
    }
    if members.feed_item is not None:
        out = copy.deepcopy(members.feed_item)
        if isinstance(out.get("data"), dict):
            out["data"]["items"] = member_items
            out["data"]["collection_ref"] = collection_ref
        return out
    tag_value = (
        producer.tag if producer.tag is not None else producer.category.upper()
    ) or None
    roundup_contract: dict[str, Any] = {
        "kicker": effective_kicker,
        "tag": tag_value,
        "footer": footer,
        "rows": rows,
        "relations": list(producer.relations),
        "level": producer.level,
    }
    if members.count_line:
        roundup_contract["count_line"] = members.count_line
    return {
        "type": "bundle",
        "score": base_score,
        "reason": effective_title,
        "headline": effective_title,
        "context_summary": None,
        "data": {
            "id": item_id,
            "title": effective_title,
            "kind": producer.kind,
            "story_key": item_id,
            "shared_question": None,
            "item_count": len(member_ids),
            "member_ids": member_ids,
            "items": member_items,
            "collection_ref": collection_ref,
            "roundup": roundup_contract,
        },
    }


def _redis_cache_key(slug: str) -> str:
    return f"container_read:v1:{slug}"


def reset_roundup_cache_for_tests() -> None:
    _roundup_local_cache.clear()


_TRANSIENT_REFUSAL_TOKENS = (
    "source_unavailable",
    "hydrate_failed",
    "missing_db_session",
    "unsupported_session",
)


def _is_cacheable_refusal(reasons: Sequence[Any]) -> bool:
    """Return False when a refusal reflects a transient loader/session error rather than data state."""
    for item in reasons:
        parts = item if isinstance(item, (tuple, list)) else (item,)
        for part in parts:
            if not isinstance(part, str):
                continue
            tok = part.strip().lower()
            if any(
                tok == transient or tok.startswith(f"{transient}:")
                for transient in _TRANSIENT_REFUSAL_TOKENS
            ):
                return False
    return True


async def _store_roundup_cache_entry(
    cache_key: tuple[str, Any],
    slug: str,
    ts: float,
    feed_item: Optional[dict[str, Any]],
    container_payload: Optional[dict[str, Any]],
    db: Any,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

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
                    _redis_cache_key(slug),
                    encoded,
                    ex=int(ROUNDUP_CACHE_TTL_S),
                ),
                treat_none_as_miss=False,
            )
        except Exception:  # noqa: BLE001 — cache write is best-effort
            logger.debug(
                "roundup_containers: shared cache write failed for %s",
                slug,
                exc_info=True,
            )


async def _cache_roundup_timeout_refusal(
    producer: RoundupProducer,
    db: Any,
    *,
    ts: Optional[float] = None,
) -> None:
    """Cache a timed-out producer as a refusal ``(None, None)`` for ``ROUNDUP_CACHE_TTL_S``."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    is_fixture_seq = isinstance(db, (list, tuple))
    rule_cfg = producer.rule if isinstance(producer.rule, Mapping) else {}
    no_cache = (
        rule_cfg.get("cache") == "none"
        or rule_cfg.get("producer") == "yardstick_pair"
    )
    if is_fixture_seq or no_cache or not container_read_cache_enabled():
        return
    cache_key = (
        producer.slug,
        "live" if isinstance(db, AsyncSession) else id(db),
    )
    effective_ts = time.time() if ts is None else float(ts)
    await _store_roundup_cache_entry(
        cache_key, producer.slug, effective_ts, None, None, db
    )


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
    # Check before either cache. An old card's warm payload must not outlive
    # its definition at the instant the dated successor takes over (65-A).
    if (producer.valid_from is not None and ts < producer.valid_from) or (
        producer.valid_until is not None and ts >= producer.valid_until
    ):
        return None, None
    rule_cfg = producer.rule if isinstance(producer.rule, Mapping) else {}
    no_cache = (
        rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair"
    )
    use_cache = not is_fixture_seq and not no_cache and container_read_cache_enabled()
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
        if use_cache and _is_cacheable_refusal(reasons):
            await _store_roundup_cache_entry(
                cache_key, producer.slug, ts, None, None, db
            )
        return None, None

    if not isinstance(outcome, RoundupMembers):
        outcome = RoundupMembers(outcome)

    container_payload = compose_roundup_container(producer, outcome)
    feed_item = compose_roundup_feed_item(producer, outcome)
    if container_payload is None or feed_item is None:
        if use_cache:
            await _store_roundup_cache_entry(
                cache_key, producer.slug, ts, None, None, db
            )
        return None, None

    if use_cache:
        await _store_roundup_cache_entry(
            cache_key, producer.slug, ts, feed_item, container_payload, db
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


def _is_roundup_bundle_card(card: Any) -> bool:
    return (
        isinstance(card, Mapping)
        and card.get("type") == "bundle"
        and isinstance(card.get("data"), Mapping)
        and card["data"].get("kind") == "roundup"
    )


def _opening_eligible_floor_index(
    items: Sequence[dict[str, Any]],
    seat_floor: int,
    *,
    now: Optional[datetime] = None,
) -> int:
    """Index in ``items`` after at least ``seat_floor`` opening-eligible cards.

    ``seat_opening`` (#5105) moves restricted ordinary-live cards out of seats
    1..10 and promotes the first ``seat_floor`` opening-eligible cards into the
    opening ten. Seating a round-up at raw index ``seat_floor`` when restricted
    cards sit in ``0..seat_floor-1`` would let ``seat_opening`` pull the round-up
    into the vacated opening seats (#11902). Counting ``seat_floor``
    opening-eligible cards first keeps the round-up at ``index >= seat_floor``
    after the opening seating pass with the opening ten otherwise unchanged.
    """
    if seat_floor <= 0 or not items:
        return max(0, seat_floor)

    from app.utils.discover_opening_seating import (
        GROUP_KINDS,
        _group_members,
        classify_card,
    )

    effective_now = (
        now
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    seatings = [
        classify_card(card, now=effective_now) if isinstance(card, dict) else None
        for card in items
    ]
    by_event_id = {
        card["data"].get("id"): seating
        for card, seating in zip(items, seatings)
        if seating is not None
        and seating.kind == "event"
        and isinstance(card, dict)
        and isinstance(card.get("data"), dict)
    }
    for card, seating in zip(items, seatings):
        if (
            seating is not None
            and seating.kind in GROUP_KINDS
            and isinstance(card, dict)
        ):
            reason, restricted_by = _group_members(
                card, by_event_id, now=effective_now
            )
            if reason is None:
                seating.restricted_by = restricted_by
                seating.restricted = bool(restricted_by)

    eligible_seen = 0
    for idx, (card, seating) in enumerate(zip(items, seatings)):
        is_restricted = bool(seating.restricted) if seating is not None else False
        if not is_restricted and not _is_roundup_bundle_card(card):
            eligible_seen += 1
            if eligible_seen >= seat_floor:
                return max(seat_floor, idx + 1)
    return max(seat_floor, len(items))


def insert_roundup_feed_items(
    items: list[dict[str, Any]],
    roundup_items: Sequence[dict[str, Any]],
    *,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    page_window: int = 20,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Place served round-up cards on Discover in page one's back half without changing scores.

    Under the Oct 7–8 ranking rulings (#4080 / #5100 / #5105 / #10356 / #10357 / #11902):
    * Covered standalone ``futures`` members fold into the round-up wherever they sit
      in the deck (Rule 3, including inside indices ``0..seat_floor-1``), so no market
      appears twice on the feed.
    * Each round-up card is seated in page one's back half after at least
      ``seat_floor`` opening-eligible cards (``index >= seat_floor`` / ``seat >= 11``
      both before and after ``seat_opening``), or at its earliest replaced
      post-opening member's seat when that is past the opening-eligible floor,
      inheriting the neighbour's score at that seat without modifying any card's score.
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

        floor_idx = _opening_eligible_floor_index(result, seat_floor, now=now)
        default_seat = floor_idx + inserted_count
        target_seat = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else default_seat
        )
        target_idx = min(max(floor_idx, target_seat), len(result))

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
    stage_budget_seconds: Optional[float] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Evaluate registered round-up producers and place their cards on Discover."""
    if not items or len(items) < seat_floor:
        return items
    if budget_seconds <= 0:
        logger.warning(
            "Discover round-up stage skipped: feed budget exhausted (budget_seconds=%.3f)",
            budget_seconds,
        )
        return items

    stage_cap = (
        float(stage_budget_seconds)
        if stage_budget_seconds is not None
        else ROUNDUP_READ_BUDGET_SECONDS
    )
    stage_budget = min(float(budget_seconds), stage_cap)
    started = time.perf_counter()
    producers = list(ROUNDUP_PRODUCERS.values())
    produced: list[dict[str, Any]] = []
    for idx, producer in enumerate(producers):
        elapsed = time.perf_counter() - started
        remaining = stage_budget - elapsed
        if remaining <= 0:
            logger.warning(
                "Discover round-up stage budget exhausted after %d/%d producers "
                "(budget_seconds=%.3f, stage_budget=%.3f, produced=%d)",
                idx,
                len(producers),
                budget_seconds,
                stage_budget,
                len(produced),
            )
            break
        per_timeout = min(remaining, ROUNDUP_PRODUCER_TIMEOUT_SECONDS)
        try:
            feed_item, container_payload = await asyncio.wait_for(
                evaluate_roundup_producer(producer, db),
                timeout=per_timeout,
            )
        except asyncio.TimeoutError:
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            if per_timeout >= ROUNDUP_PRODUCER_TIMEOUT_SECONDS:
                await _cache_roundup_timeout_refusal(producer, db)
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards",
                producer.slug,
                exc_info=True,
            )
            continue
        except Exception:
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards",
                producer.slug,
                exc_info=True,
            )
            continue
        if feed_item is not None and container_payload is not None:
            produced.append(feed_item)

    if not produced:
        return items
    return insert_roundup_feed_items(
        items,
        produced,
        seat_floor=seat_floor,
        page_window=page_window,
        now=now,
    )


ROUNDUP_PRODUCERS: dict[str, RoundupProducer] = {}


def register_roundup_producer(producer: RoundupProducer) -> RoundupProducer:
    """Register a ``RoundupProducer`` by its slug."""
    ROUNDUP_PRODUCERS[producer.slug] = producer
    return producer


def validate_roundup_definition(
    data: Mapping[str, Any],
    *,
    path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Validate a round-up container definition against Decide 60-A, 71-A, and 73-A.

    * Requires a non-empty ``slug`` and a ``rule`` mapping with a ``producer`` kind.
    * Requires a non-empty ``relations`` list drawn from ``CLOSED_GROUPING_RELATIONS``.
    * Requires ``level`` in ``CLOSED_PERMISSION_LEVELS``; ``level == "equivalent"``
      is permitted only when ``"twin"`` is in ``relations`` (71-A).
    * Refuses a definition whose only member source is a hand list of market IDs
      without a selector or explicit ``id_list_reason`` (73-A), while allowing
      declared occasion IDs (``field``, ``register``, ``anchor``) as "an id, never
      a member".
    """
    loc = f" at {path}" if path is not None else ""
    if not isinstance(data, Mapping):
        raise ValueError(f"Round-up definition{loc} must be a JSON object")

    slug = str(data.get("slug") or "").strip()
    if not slug:
        raise ValueError(f"Round-up definition{loc} requires a non-empty 'slug'")

    if data.get("kind") != "roundup":
        raise ValueError(
            f"Round-up definition {slug!r}{loc} must declare kind='roundup'"
        )

    rule_raw = data.get("rule")
    if not isinstance(rule_raw, Mapping):
        raise ValueError(
            f"Round-up definition {slug!r}{loc} requires a 'rule' mapping"
        )
    producer_kind = str(rule_raw.get("producer") or "").strip()
    if not producer_kind:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} requires 'rule.producer'"
        )

    relations_raw = (
        data.get("relations")
        if "relations" in data
        else rule_raw.get("relations")
    )
    if not isinstance(relations_raw, (list, tuple)) or not relations_raw:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} requires a non-empty 'relations' list (71-A)"
        )
    relations_list: list[str] = []
    for rel in relations_raw:
        if not isinstance(rel, str) or not rel.strip():
            raise ValueError(
                f"Round-up definition {slug!r}{loc} has an empty relation in 'relations'"
            )
        rel_clean = rel.strip()
        if rel_clean not in CLOSED_GROUPING_RELATIONS:
            raise ValueError(
                f"Round-up definition {slug!r}{loc} has unknown relation {rel_clean!r}; "
                f"allowed: {sorted(CLOSED_GROUPING_RELATIONS)}"
            )
        relations_list.append(rel_clean)

    level_raw = (
        data.get("level") if "level" in data else rule_raw.get("level")
    )
    if not isinstance(level_raw, str) or level_raw.strip() not in CLOSED_PERMISSION_LEVELS:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} has invalid 'level' {level_raw!r}; "
            f"allowed: {sorted(CLOSED_PERMISSION_LEVELS)}"
        )
    level_clean = level_raw.strip()
    if level_clean == "equivalent" and "twin" not in relations_list:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} sets level='equivalent' without 'twin' in relations (71-A)"
        )

    has_primary_selector = any(
        bool(rule_raw.get(k)) for k in SELECTOR_RULE_KEYS
    )
    has_occasion_id = any(
        bool(rule_raw.get(k)) for k in OCCASION_ID_RULE_KEYS
    )
    has_non_empty_hand_list = any(
        isinstance(rule_raw.get(k), (list, tuple)) and len(rule_raw.get(k)) > 0
        for k in HAND_LIST_ID_RULE_KEYS
    )
    id_list_reason = str(
        data.get("id_list_reason") or rule_raw.get("id_list_reason") or ""
    ).strip()

    if has_non_empty_hand_list and not has_primary_selector and not id_list_reason:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} uses a hand list of market IDs "
            f"without a selector or 'id_list_reason' (73-A)"
        )
    if not has_primary_selector and not has_occasion_id and not (
        has_non_empty_hand_list and id_list_reason
    ):
        raise ValueError(
            f"Round-up definition {slug!r}{loc} requires a selector in 'rule' (73-A)"
        )

    out = dict(data)
    out["slug"] = slug
    out["relations"] = list(relations_list)
    out["level"] = level_clean
    rule_copy = dict(rule_raw)
    rule_copy["relations"] = list(relations_list)
    rule_copy["level"] = level_clean
    out["rule"] = rule_copy
    if id_list_reason:
        out["id_list_reason"] = id_list_reason
    return out


def load_roundup_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate one JSON round-up definition file from disk."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"Round-up definition at {p} must be a JSON object")
    return validate_roundup_definition(raw, path=p)


def load_roundup_definitions_from_dir(
    directory: Path | str = CONTAINERS_DATA_DIR,
    *,
    producer_kind: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Scan ``directory`` for ``*.json`` round-up definitions and validate each file (60-A)."""
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    definitions: list[dict[str, Any]] = []
    for path in sorted(dir_path.glob("*.json")):
        defn = load_roundup_definition(path)
        if (
            producer_kind is not None
            and defn["rule"].get("producer") != producer_kind
        ):
            continue
        definitions.append(defn)
    return definitions


_KIND_TO_MODULE_BUILDER: dict[str, tuple[str, str]] = {
    "sibling_family": (
        "app.utils.sibling_family",
        "build_sibling_family_producer",
    ),
    "same_deadline_board": (
        "app.utils.same_deadline_board",
        "build_same_deadline_board_producer",
    ),
    "yardstick_pair": (
        "app.utils.yardstick_pair",
        "build_yardstick_pair_producer",
    ),
    "field_leaders": (
        "app.utils.field_leaders",
        "build_field_leaders_producer",
    ),
    "field_band": (
        "app.utils.field_band",
        "build_field_band_producer",
    ),
    "field_selection": (
        "app.utils.field_selection",
        "build_field_selection_producer",
    ),
    "awards_ceremony": (
        "app.utils.awards_ceremony",
        "build_awards_ceremony_producer",
    ),
    "week_events": (
        "app.utils.week_events",
        "build_week_events_producer",
    ),
    "window_events_closest": (
        "app.utils.window_events_closest",
        "build_window_events_closest_producer",
    ),
    "register_closest": (
        "app.utils.register_closest",
        "build_register_closest_producer",
    ),
    "awards_category_roundup": (
        "app.utils.awards_category_roundup",
        "build_awards_category_producer",
    ),
}


def build_roundup_producer_from_definition(
    definition: Mapping[str, Any],
) -> RoundupProducer:
    """Build a ``RoundupProducer`` for any supported ``rule.producer`` kind (60-A)."""
    import importlib

    validated = validate_roundup_definition(definition)
    producer_kind = str(validated["rule"]["producer"])
    target = _KIND_TO_MODULE_BUILDER.get(producer_kind)
    if target is None:
        raise ValueError(
            f"Unsupported round-up producer kind {producer_kind!r} in definition {validated['slug']!r}"
        )
    mod_name, builder_name = target
    mod = importlib.import_module(mod_name)
    builder = getattr(mod, builder_name)
    return builder(validated)


_BUILTIN_SLUG_TO_MODULE_ATTR: dict[str, tuple[str, str]] = {
    "roundup-nfl-divisions": (
        "app.utils.discover_bundles",
        "NFL_DIVISION_ROUNDUP_PRODUCER",
    ),
    "roundup-closest-games-tonight": (
        "app.utils.window_events_closest",
        "CLOSEST_GAMES_TONIGHT_PRODUCER",
    ),
    "roundup-closest-races": (
        "app.utils.register_closest",
        "CLOSEST_RACES_PRODUCER",
    ),
    "roundup-golden-globes-best-picture": (
        "app.utils.awards_category_roundup",
        "GOLDEN_GLOBES_BEST_PICTURE_PRODUCER",
    ),
    "roundup-cfp-picture": (
        "app.utils.field_band",
        "CFP_PICTURE_PRODUCER",
    ),
    "by-november-30": (
        "app.utils.same_deadline_board",
        "BY_NOVEMBER_30_PRODUCER",
    ),
    "by-december-31": (
        "app.utils.same_deadline_board",
        "BY_DECEMBER_31_PRODUCER",
    ),
    "gta-vi-album-features": (
        "app.utils.sibling_family",
        "GTA_VI_ALBUM_FEATURES_PRODUCER",
    ),
    "snow-first-flakes-2026": (
        "app.utils.sibling_family",
        "SNOW_FIRST_FLAKES_2026_PRODUCER",
    ),
    "rt-scores-this-week": (
        "app.utils.sibling_family",
        "RT_SCORES_THIS_WEEK_PRODUCER",
    ),
    "who-announces-before-2027": (
        "app.utils.sibling_family",
        "WHO_ANNOUNCES_BEFORE_2027_PRODUCER",
    ),
    "alcaraz-sinner-two-majors-2027": (
        "app.utils.sibling_family",
        "ALCARAZ_SINNER_TWO_MAJORS_2027_PRODUCER",
    ),
    "golf-this-week": (
        "app.utils.week_events",
        "GOLF_THIS_WEEK_PRODUCER",
    ),
    "roundup-tomorrows-highs": (
        "app.utils.field_leaders",
        "TOMORROWS_HIGHS_PRODUCER",
    ),
    "roundup-opening-weekend": (
        "app.utils.field_leaders",
        "OPENING_WEEKEND_PRODUCER",
    ),
    "roundup-this-weeks-economic-data": (
        "app.utils.field_leaders",
        "THIS_WEEKS_ECONOMIC_DATA_PRODUCER",
    ),
    "for-scale-snow-in-dc": (
        "app.utils.yardstick_pair",
        "FOR_SCALE_SNOW_IN_DC_PRODUCER",
    ),
    "for-scale-snow-in-buffalo": (
        "app.utils.yardstick_pair",
        "FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER",
    ),
    "for-scale-us-recession-2026": (
        "app.utils.yardstick_pair",
        "FOR_SCALE_US_RECESSION_2026_PRODUCER",
    ),
}


def _yardstick_blocked_by_initializing_deadline_board() -> bool:
    import sys

    sdb_mod = sys.modules.get("app.utils.same_deadline_board")
    return (
        sdb_mod is not None
        and getattr(sdb_mod, "BY_DECEMBER_31_PRODUCER", None) is None
    )


def register_roundup_definitions_from_dir(
    directory: Path | str = CONTAINERS_DATA_DIR,
    *,
    replace: bool = False,
) -> dict[str, RoundupProducer]:
    """Load, validate, build, and register every ``*.json`` definition in ``directory`` (60-A)."""
    import importlib
    import sys

    dir_path = Path(directory)
    definitions = load_roundup_definitions_from_dir(dir_path)
    is_canonical_dir = (
        dir_path.exists()
        and CONTAINERS_DATA_DIR.exists()
        and dir_path.resolve() == CONTAINERS_DATA_DIR.resolve()
    )
    registered: dict[str, RoundupProducer] = {}
    for defn in definitions:
        slug = defn["slug"]
        if not replace and slug in ROUNDUP_PRODUCERS:
            registered[slug] = ROUNDUP_PRODUCERS[slug]
            continue
        if not replace and is_canonical_dir and slug in _BUILTIN_SLUG_TO_MODULE_ATTR:
            mod_name, attr_name = _BUILTIN_SLUG_TO_MODULE_ATTR[slug]
            if (
                mod_name == "app.utils.yardstick_pair"
                and _yardstick_blocked_by_initializing_deadline_board()
            ):
                continue
            mod = sys.modules.get(mod_name)
            if mod is None:
                mod = importlib.import_module(mod_name)
            named_producer = getattr(mod, attr_name, None)
            if named_producer is not None:
                register_roundup_producer(named_producer)
                registered[slug] = named_producer
            # Never fall through to build_roundup_producer_from_definition when
            # the module is still mid-import: its own bottom-of-file
            # register_roundup_producer call completes registration.
            continue
        producer_kind = str(defn["rule"]["producer"])
        target = _KIND_TO_MODULE_BUILDER.get(producer_kind)
        if not replace and target is not None:
            mod_name, builder_name = target
            if (
                mod_name == "app.utils.yardstick_pair"
                and _yardstick_blocked_by_initializing_deadline_board()
            ):
                continue
            existing_mod = sys.modules.get(mod_name)
            if (
                existing_mod is not None
                and getattr(existing_mod, builder_name, None) is None
            ):
                continue
        producer = build_roundup_producer_from_definition(defn)
        register_roundup_producer(producer)
        registered[slug] = producer
    return registered


def _register_builtin_producers() -> None:
    import importlib
    import sys

    for _slug, (mod_name, attr_name) in _BUILTIN_SLUG_TO_MODULE_ATTR.items():
        if (
            mod_name == "app.utils.yardstick_pair"
            and _yardstick_blocked_by_initializing_deadline_board()
        ):
            continue
        mod = sys.modules.get(mod_name)
        if mod is None:
            mod = importlib.import_module(mod_name)
        named_producer = getattr(mod, attr_name, None)
        if named_producer is not None:
            register_roundup_producer(named_producer)

    register_roundup_definitions_from_dir(CONTAINERS_DATA_DIR, replace=False)


_register_builtin_producers()
