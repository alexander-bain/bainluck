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
import re
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import (
    MEMBER_MARKET,
    container_destination,
    market_destination,
)

__all__ = [
    "CLOSED_GROUPING_RELATIONS",
    "CLOSED_PERMISSION_LEVELS",
    "CONTAINERS_DATA_DIR",
    "HAND_LIST_ID_RULE_KEYS",
    "OCCASION_ID_RULE_KEYS",
    "ROUNDUP_CACHE_TTL_S",
    "ROUNDUP_NOVELTY_SEAT_CAP",
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
    "apply_novelty_seats",
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
    "team_slug",
    "series_code",
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
#: Decide 32-C (#12091 / #12376): a returning reader gets up to two novelty
#: seats in the opening ten when new (unseen) generated cards exist; first-time
#: readers get zero.
ROUNDUP_NOVELTY_SEAT_CAP = 2

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
    destination_href: Optional[str] = None
    sections: tuple[dict[str, Any], ...] = ()
    revision_ids: tuple[int, ...] = ()
    suppress_feed_item: bool = False
    caption: Optional[dict[str, Any]] = None
    parent_slug: Optional[str] = None
    parent_name: Optional[str] = None
    children: tuple[dict[str, Any], ...] = ()

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
        destination_href: Optional[str] = None,
        sections: Sequence[dict[str, Any]] = (),
        revision_ids: Sequence[int] = (),
        suppress_feed_item: bool = False,
        caption: Optional[Mapping[str, Any]] = None,
        parent_slug: Optional[str] = None,
        parent_name: Optional[str] = None,
        children: Sequence[Mapping[str, Any]] = (),
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
        object.__setattr__(
            self,
            "destination_href",
            str(destination_href) if destination_href is not None else None,
        )
        object.__setattr__(self, "sections", tuple(sections))
        object.__setattr__(
            self, "revision_ids", tuple(int(rid) for rid in revision_ids)
        )
        object.__setattr__(self, "suppress_feed_item", bool(suppress_feed_item))
        object.__setattr__(
            self, "caption", dict(caption) if isinstance(caption, Mapping) else None
        )
        object.__setattr__(
            self,
            "parent_slug",
            str(parent_slug).strip() if parent_slug is not None and str(parent_slug).strip() else None,
        )
        object.__setattr__(
            self,
            "parent_name",
            str(parent_name).strip() if parent_name is not None and str(parent_name).strip() else None,
        )
        object.__setattr__(
            self,
            "children",
            tuple(dict(c) for c in (children or ()) if isinstance(c, Mapping)),
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
    destination_href: Optional[str] = None
    order: Optional[str] = None
    presentation: Optional[str] = None
    caption: Optional[Any] = None
    parent_slug: Optional[str] = None
    parent_name: Optional[str] = None
    children: tuple[dict[str, Any], ...] = ()
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
        destination_href: Optional[str] = None,
        order: Optional[str] = None,
        presentation: Optional[str] = None,
        caption: Optional[Any] = None,
        parent_slug: Optional[str] = None,
        parent_name: Optional[str] = None,
        children: Optional[Sequence[Mapping[str, Any]]] = None,
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
        raw_dest_href = (
            destination_href
            if destination_href is not None
            else (
                rule.get("destination_href")
                if isinstance(rule, Mapping)
                and isinstance(rule.get("destination_href"), str)
                else None
            )
        )
        raw_order = (
            order
            if order is not None
            else (
                rule.get("order")
                if isinstance(rule, Mapping) and isinstance(rule.get("order"), str)
                else None
            )
        )
        raw_presentation = (
            presentation
            if presentation is not None
            else (
                rule.get("presentation")
                if isinstance(rule, Mapping)
                and isinstance(rule.get("presentation"), str)
                else None
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
        object.__setattr__(
            self,
            "destination_href",
            str(raw_dest_href).strip() if raw_dest_href else None,
        )
        object.__setattr__(
            self,
            "order",
            str(raw_order).strip() if raw_order else None,
        )
        object.__setattr__(
            self,
            "presentation",
            str(raw_presentation).strip() if raw_presentation else None,
        )
        raw_caption = (
            caption
            if caption is not None
            else (rule.get("caption") if isinstance(rule, Mapping) else None)
        )
        object.__setattr__(self, "caption", raw_caption)
        raw_parent_slug = (
            parent_slug
            if parent_slug is not None
            else (
                rule.get("parent_slug")
                if isinstance(rule, Mapping) and isinstance(rule.get("parent_slug"), str)
                else None
            )
        )
        raw_parent_name = (
            parent_name
            if parent_name is not None
            else (
                rule.get("parent_name")
                if isinstance(rule, Mapping) and isinstance(rule.get("parent_name"), str)
                else None
            )
        )
        raw_children = (
            children
            if children is not None
            else (
                rule.get("children")
                if isinstance(rule, Mapping)
                and isinstance(rule.get("children"), (list, tuple))
                else ()
            )
        )
        object.__setattr__(
            self,
            "parent_slug",
            str(raw_parent_slug).strip()
            if raw_parent_slug and str(raw_parent_slug).strip()
            else None,
        )
        object.__setattr__(
            self,
            "parent_name",
            str(raw_parent_name).strip()
            if raw_parent_name and str(raw_parent_name).strip()
            else None,
        )
        object.__setattr__(
            self,
            "children",
            tuple(dict(c) for c in (raw_children or ()) if isinstance(c, Mapping)),
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
    effective_dest_href = (
        (
            members.destination_href
            if isinstance(members, RoundupMembers) and members.destination_href
            else None
        )
        or producer.destination_href
    )
    effective_parent_slug = (
        (
            members.parent_slug
            if isinstance(members, RoundupMembers) and members.parent_slug
            else None
        )
        or producer.parent_slug
    )
    effective_parent_name = (
        (
            members.parent_name
            if isinstance(members, RoundupMembers) and members.parent_name
            else None
        )
        or producer.parent_name
        or effective_parent_slug
    )
    raw_children = (
        members.children
        if isinstance(members, RoundupMembers) and members.children
        else producer.children
    )
    children_payload: list[dict[str, Any]] = []
    for child in raw_children:
        if not isinstance(child, Mapping):
            continue
        c_slug = str(child.get("slug") or "").strip()
        if not c_slug:
            continue
        c_entry = dict(child)
        c_entry.setdefault("id", roundup_container_id(c_slug))
        c_entry["slug"] = c_slug
        c_entry.setdefault("name", c_slug)
        c_entry.setdefault("kind", "roundup")
        c_entry.setdefault("category", producer.category)
        c_entry.setdefault("status", "open")
        c_entry.setdefault("publication_state", "published")
        c_entry.setdefault("edition", None)
        c_entry.setdefault("destination", container_destination(c_slug))
        children_payload.append(c_entry)
    container_obj: dict[str, Any] = {
        "id": roundup_container_id(producer.slug),
        "slug": producer.slug,
        "name": container_name,
        "kind": producer.kind,
        "category": producer.category,
        "status": "open",
        "window_start": None,
        "window_end": None,
        "parent_container_id": (
            roundup_container_id(effective_parent_slug)
            if effective_parent_slug
            else None
        ),
    }
    if effective_dest_href:
        container_obj["destination_href"] = effective_dest_href
    if effective_parent_slug:
        container_obj["parent_slug"] = effective_parent_slug
        container_obj["parent_name"] = effective_parent_name
    raw_caption = (
        members.caption
        if isinstance(members, RoundupMembers) and members.caption is not None
        else producer.caption
    )
    verified_caption: Optional[dict[str, Any]] = None
    if raw_caption is not None:
        from app.utils.grouping_captions import compose_container_caption

        caption_members: Sequence[Mapping[str, Any]] = (
            members.rows
            if isinstance(members, RoundupMembers) and members.rows
            else normalized
        )
        verified_caption = compose_container_caption(
            {"caption": raw_caption},
            members=caption_members,
        )
    if verified_caption is not None:
        container_obj["caption"] = verified_caption
    out_payload: dict[str, Any] = {
        "state": "published",
        "slug": producer.slug,
        "revision": roundup_revision(rev_ids),
        "relations": list(producer.relations),
        "level": producer.level,
        "reason": None,
        "edition": None,
        "container": container_obj,
        "subtitle": subtitle,
        "caption": verified_caption,
        "sections": sections,
        "member_count": total_members,
        "withheld": [],
        "withheld_count": 0,
        "children": children_payload,
        "assembled": True,
    }
    if isinstance(members, RoundupMembers) and members.sections:
        first_sec = members.sections[0]
        if isinstance(first_sec, Mapping):
            sec_ctx = str(first_sec.get("context_line") or "").strip()
            if sec_ctx:
                out_payload["context_line"] = sec_ctx
    if effective_parent_slug:
        out_payload["parent"] = {
            "slug": effective_parent_slug,
            "name": effective_parent_name,
            "destination": container_destination(effective_parent_slug),
        }
    if effective_dest_href:
        out_payload["destination_href"] = effective_dest_href
    return out_payload


def compose_roundup_feed_item(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> Optional[dict[str, Any]]:
    """Build the Discover feed item for a round-up producer from its produced members."""
    if getattr(members, "suppress_feed_item", False):
        return None
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
    effective_href = (
        members.destination_href
        or producer.destination_href
        or f"/collections/{producer.slug}"
    )
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
        "href": effective_href,
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
    if members.destination_href or producer.destination_href:
        roundup_contract["destination_href"] = effective_href
    if producer.order:
        roundup_contract["order"] = producer.order
    if producer.presentation:
        roundup_contract["presentation"] = producer.presentation
    if members.count_line:
        roundup_contract["count_line"] = members.count_line
    context_summary_val: Optional[str] = None
    if members.sections and isinstance(members.sections[0], Mapping):
        sec_ctx = str(members.sections[0].get("context_line") or "").strip()
        if sec_ctx:
            roundup_contract["context_line"] = sec_ctx
            roundup_contract["subtitle"] = sec_ctx
            context_summary_val = sec_ctx
    raw_caption = (
        members.caption if members.caption is not None else producer.caption
    )
    if raw_caption is not None:
        from app.utils.grouping_captions import compose_container_caption

        caption_members: Sequence[Mapping[str, Any]] = (
            rows if rows else normalized
        )
        verified_caption = compose_container_caption(
            {"caption": raw_caption},
            members=caption_members,
        )
        if verified_caption is not None:
            roundup_contract["caption"] = verified_caption
    return {
        "type": "bundle",
        "score": base_score,
        "reason": effective_title,
        "headline": effective_title,
        "context_summary": context_summary_val,
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


def _normalize_roundup_now(
    now: Optional[float | datetime],
) -> tuple[float, Optional[datetime]]:
    if now is None:
        return time.time(), None
    if isinstance(now, datetime):
        dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        return dt.timestamp(), dt.astimezone(timezone.utc)
    ts = float(now)
    return ts, datetime.fromtimestamp(ts, tz=timezone.utc)


async def evaluate_roundup_producer(
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float | datetime] = None,
    licences_registry: Optional[dict[str, Any]] = None,
    licences_path: Optional[Path | str] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Run ``producer`` once and return ``(feed_item, container_payload)``, cached 60s per slug."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    if producer.enabled is not None and not producer.enabled():
        return None, None

    is_fixture_seq = isinstance(db, (list, tuple))
    ts, now_dt = _normalize_roundup_now(now)
    # Check before either cache. An old card's warm payload must not outlive
    # its definition at the instant the dated successor takes over (65-A).
    if (producer.valid_from is not None and ts < producer.valid_from) or (
        producer.valid_until is not None and ts >= producer.valid_until
    ):
        return None, None
    rule_cfg = producer.rule if isinstance(producer.rule, Mapping) else {}
    producer_kind = str(rule_cfg.get("producer") or "").strip()
    if producer_kind:
        from app.utils.grouping_licences import (
            get_kind_licence_status,
            load_grouping_licences,
        )

        active_licences = (
            licences_registry
            if licences_registry is not None
            else load_grouping_licences(licences_path)
        )
        if (
            producer_kind in (active_licences.get("kinds") or {})
            and get_kind_licence_status(active_licences, producer_kind) == "SUSPENDED"
        ):
            logger.warning(
                "flow_sentinel matching_defect: roundup %s skipped because kind %s is SUSPENDED",
                producer.slug,
                producer_kind,
            )
            return None, None
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

    if now_dt is not None and "now" in inspect.signature(producer.produce).parameters:
        outcome = producer.produce(db, now=now_dt)
    else:
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
    if container_payload is None or (
        feed_item is None and not getattr(outcome, "suppress_feed_item", False)
    ):
        if use_cache:
            await _store_roundup_cache_entry(
                cache_key, producer.slug, ts, None, None, db
            )
        return None, None

    if producer_kind:
        from app.utils.grouping_licences import (
            detect_served_card_violation,
            load_grouping_licences,
            record_runtime_kind_suspension,
        )

        active_licences = (
            licences_registry
            if licences_registry is not None
            else load_grouping_licences(licences_path)
        )
        if producer_kind in (active_licences.get("kinds") or {}):
            allow_settled = producer_kind == "series_hub"
            violation = detect_served_card_violation(
                container_payload, allow_settled_members=allow_settled
            ) or (
                detect_served_card_violation(
                    feed_item, allow_settled_members=allow_settled
                )
                if feed_item is not None
                else None
            )
            if violation is not None:
                bad_slug, bad_reason = violation
                record_runtime_kind_suspension(
                    producer_kind,
                    wrong_card_slug=bad_slug or producer.slug,
                    reason=bad_reason,
                    registry=licences_registry,
                    licences_path=licences_path,
                )
                logger.warning(
                    "flow_sentinel matching_defect: roundup %s suspended kind %s (%s)",
                    producer.slug,
                    producer_kind,
                    bad_reason,
                )
                return None, None

    if use_cache:
        await _store_roundup_cache_entry(
            cache_key, producer.slug, ts, feed_item, container_payload, db
        )

    return feed_item, container_payload


def _strip_parent_from_payload(out: dict[str, Any]) -> None:
    out.pop("parent", None)
    if isinstance(out.get("container"), dict):
        out["container"]["parent_container_id"] = None
        out["container"].pop("parent_slug", None)
        out["container"].pop("parent_name", None)


async def serve_roundup(
    slug: str,
    db: Any,
    *,
    include_children: bool = True,
    now: Optional[float | datetime] = None,
) -> dict[str, Any]:
    """Serve a registered round-up container, or raise 404 ``{state: unavailable, slug}``."""
    from fastapi import HTTPException

    from app.utils.container_corrections import (
        READ_PUBLISHED,
        READ_UNAVAILABLE,
        read_published,
    )

    producer = ROUNDUP_PRODUCERS.get(slug)
    if producer is None:
        raise HTTPException(
            status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug}
        )
    _feed_item, payload = await evaluate_roundup_producer(producer, db, now=now)
    if payload is None:
        raise HTTPException(
            status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug}
        )
    out = copy.deepcopy(payload)
    if not include_children:
        out["children"] = []
    elif out.get("children"):
        verified_children: list[dict[str, Any]] = []
        for ch in out["children"]:
            if not isinstance(ch, Mapping):
                continue
            ch_slug = str(ch.get("slug") or "").strip()
            if not ch_slug:
                continue
            ch_prod = ROUNDUP_PRODUCERS.get(ch_slug)
            if ch_prod is not None:
                _ch_fi, ch_payload = await evaluate_roundup_producer(ch_prod, db, now=now)
                if ch_payload is None or ch_payload.get("state") != "published":
                    continue
                ch_copy = dict(ch)
                ch_copy["publication_state"] = "published"
                ch_name = (ch_payload.get("container") or {}).get("name")
                if ch_name:
                    ch_copy["name"] = ch_name
                verified_children.append(ch_copy)
            else:
                try:
                    ch_pub = await read_published(db, ch_slug)
                except Exception:  # noqa: BLE001
                    ch_pub = None
                if getattr(ch_pub, "state", None) == READ_PUBLISHED:
                    ch_copy = dict(ch)
                    ch_copy["publication_state"] = "published"
                    verified_children.append(ch_copy)
        out["children"] = verified_children

    parent_obj = out.get("parent")
    if isinstance(parent_obj, Mapping):
        p_slug = str(parent_obj.get("slug") or "").strip()
        p_prod = ROUNDUP_PRODUCERS.get(p_slug) if p_slug else None
        if p_prod is not None:
            _p_fi, p_payload = await evaluate_roundup_producer(p_prod, db, now=now)
            if p_payload is None or p_payload.get("state") != "published":
                _strip_parent_from_payload(out)
        elif p_slug:
            try:
                p_pub = await read_published(db, p_slug)
            except Exception:  # noqa: BLE001
                p_pub = None
            if getattr(p_pub, "state", None) != READ_PUBLISHED:
                _strip_parent_from_payload(out)
        else:
            _strip_parent_from_payload(out)
    return out


async def roundup_feed_items(
    db: Any,
    *,
    now: Optional[float | datetime] = None,
) -> list[dict[str, Any]]:
    """Evaluate every registered producer and return feed cards whose containers would be served."""
    items: list[dict[str, Any]] = []
    for producer in list(ROUNDUP_PRODUCERS.values()):
        feed_item, container_payload = await evaluate_roundup_producer(
            producer, db, now=now
        )
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


def _roundup_card_candidate_keys(card: Mapping[str, Any]) -> set[str]:
    data = card.get("data")
    if not isinstance(data, Mapping):
        return set()
    keys: set[str] = set()
    r_id = str(data.get("id") or "").strip()
    if r_id:
        keys.add(r_id)
        keys.add(f"bundle:{r_id}")
    cref = data.get("collection_ref")
    slug = str(cref.get("slug") or "").strip() if isinstance(cref, Mapping) else ""
    if slug:
        keys.add(slug)
        keys.add(f"roundup:{slug}")
        keys.add(f"bundle:roundup:{slug}")
    return keys


def _is_unseen_roundup_card(
    card: Mapping[str, Any],
    *,
    seen_card_keys: Optional[Sequence[str] | set[str]] = None,
    seen_futures_ids: Optional[Sequence[int] | set[int]] = None,
    seen_event_ids: Optional[Sequence[int] | set[int]] = None,
) -> bool:
    """Return True when ``card`` has not already been seen/dismissed by the reader (#12376)."""
    if seen_card_keys:
        seen_keys_norm = {str(k).strip() for k in seen_card_keys if k}
        if _roundup_card_candidate_keys(card) & seen_keys_norm:
            return False

    covered_markets = _roundup_covered_market_ids(card)
    if covered_markets and seen_futures_ids:
        seen_fids = {int(fid) for fid in seen_futures_ids if isinstance(fid, int)}
        if covered_markets <= seen_fids:
            return False

    data = card.get("data")
    if isinstance(data, Mapping) and seen_event_ids:
        event_member_ids = {
            int(child["data"]["id"])
            for child in (data.get("items") or ())
            if isinstance(child, Mapping)
            and child.get("type") == "event"
            and isinstance(child.get("data"), Mapping)
            and isinstance(child["data"].get("id"), int)
        }
        if event_member_ids:
            seen_eids = {int(eid) for eid in seen_event_ids if isinstance(eid, int)}
            if event_member_ids <= seen_eids:
                return False

    return True


def _is_roundup_opening_eligible(
    card: Mapping[str, Any],
    items: Sequence[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Return True when ``card`` is opening-eligible under ``discover_opening_seating`` (#5105)."""
    from app.utils.discover_opening_seating import _group_members, classify_card

    effective_now = (
        now
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    by_event_id = {}
    for existing in items:
        if not isinstance(existing, dict):
            continue
        seating = classify_card(existing, now=effective_now)
        if (
            seating is not None
            and seating.kind == "event"
            and isinstance(existing.get("data"), dict)
        ):
            by_event_id[existing["data"].get("id")] = seating

    seating = classify_card(dict(card), now=effective_now)
    if seating is None:
        return False
    reason, restricted_by = _group_members(
        dict(card), by_event_id, now=effective_now
    )
    if reason is not None or restricted_by:
        return False
    return not bool(seating.restricted)


def apply_novelty_seats(
    items: list[dict[str, Any]],
    *,
    returning_reader: bool = False,
    seen_card_keys: Optional[Sequence[str] | set[str]] = None,
    seen_futures_ids: Optional[Sequence[int] | set[int]] = None,
    seen_event_ids: Optional[Sequence[int] | set[int]] = None,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    novelty_seat_cap: int = ROUNDUP_NOVELTY_SEAT_CAP,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Seat up to ``novelty_seat_cap`` unseen round-up cards in the opening ten for returning readers (#12376).

    First-time readers (``returning_reader=False``) receive zero novelty seats in
    the opening ten; all round-up cards remain at ``index >= seat_floor``.
    """
    if not returning_reader or novelty_seat_cap <= 0 or seat_floor <= 0 or not items:
        return items

    cap = min(int(novelty_seat_cap), int(seat_floor))
    novelty_indices: list[int] = []
    for idx, card in enumerate(items):
        if not _is_roundup_bundle_card(card):
            continue
        if not _is_unseen_roundup_card(
            card,
            seen_card_keys=seen_card_keys,
            seen_futures_ids=seen_futures_ids,
            seen_event_ids=seen_event_ids,
        ):
            continue
        if not _is_roundup_opening_eligible(card, items, now=now):
            continue
        novelty_indices.append(idx)
        if len(novelty_indices) >= cap:
            break

    if not novelty_indices:
        return items

    novelty_set = set(novelty_indices)
    novelty_cards = [items[i] for i in novelty_indices]
    remaining = [card for i, card in enumerate(items) if i not in novelty_set]

    target_non_roundup_eligible = max(0, int(seat_floor) - len(novelty_cards))
    insert_at = min(
        _opening_eligible_floor_index(
            remaining, target_non_roundup_eligible, now=now
        ),
        len(remaining),
    )

    result = list(remaining)
    for offset, raw_n_card in enumerate(novelty_cards):
        n_card = copy.deepcopy(dict(raw_n_card))
        if isinstance(n_card.get("data"), dict):
            n_card["data"]["novelty_seat"] = True
            if isinstance(n_card["data"].get("roundup"), dict):
                n_card["data"]["roundup"]["novelty_seat"] = True
        pos = min(insert_at + offset, len(result))
        result.insert(pos, n_card)
    return result


_SIBLING_TITLE_STOPWORDS: frozenset[str] = frozenset(
    {
        "who",
        "which",
        "what",
        "whose",
        "will",
        "the",
        "a",
        "an",
        "to",
        "with",
        "in",
        "of",
        "for",
        "on",
        "at",
        "by",
        "be",
        "from",
        "into",
        "team",
        "teams",
        "candidate",
        "candidates",
        "player",
        "players",
        "contender",
        "contenders",
        "city",
        "cities",
        "movie",
        "movies",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


def _is_sibling_family_bundle(item: Mapping[str, Any]) -> bool:
    data = item.get("data")
    if not isinstance(data, Mapping):
        return False
    roundup = data.get("roundup")
    if not isinstance(roundup, Mapping):
        return False
    rels = roundup.get("relations") or ()
    return "sibling" in rels or "sibling_of" in rels


def _sibling_family_row_labels(item: Mapping[str, Any]) -> set[str]:
    data = item.get("data")
    if not isinstance(data, Mapping):
        return set()
    roundup = data.get("roundup")
    if not isinstance(roundup, Mapping):
        return set()
    labels: set[str] = set()
    for r in roundup.get("rows") or ():
        if not isinstance(r, Mapping):
            continue
        lbl = str(r.get("label") or r.get("subject") or "").strip().lower()
        if lbl:
            labels.add(lbl)
    return labels


def _sibling_family_title_tokens(item: Mapping[str, Any]) -> set[str]:
    data = item.get("data")
    if not isinstance(data, Mapping):
        return set()
    title = str(data.get("title") or item.get("headline") or "").strip().lower()
    # Strip trailing deadline clause ('by December 31, 2026', 'in 2026', etc.)
    title = re.sub(
        r"\b(?:by|before|on)\s+[a-z]+\s+\d{1,2}(?:,\s*\d{4})?\b",
        " ",
        title,
    )
    title = re.sub(r"\b20\d{2}(?:[-–/]\d{2,4})?\b", " ", title)
    tokens = {
        tok
        for tok in re.findall(r"[a-z0-9]+", title)
        if tok not in _SIBLING_TITLE_STOPWORDS
    }
    return tokens


def _is_near_identical_sibling_family(
    candidate_item: Mapping[str, Any],
    seated_item: Mapping[str, Any],
) -> bool:
    """Return True when two ``sibling_family`` cards are near-identical (#12374).

    Prevents near-identical families (such as ``"Who will Trump meet with by December 31, 2026?"``
    and ``"Who will Trump speak to by November 30, 2026?"``, or ``"Which team will finish top 8 in UECL league phase?"``
    and ``"Which team will finish 9th–24th in UECL league phase?"``) from both taking
    seats on the same Discover screen:
    - Sharing ``>= 2`` row labels and ``>= 50%`` of the smaller card's shown rows, or
    - In the same category/tag, sharing ``>= 2`` content title tokens and ``>= 50%``
      of the smaller title's content tokens.
    """
    if not (_is_sibling_family_bundle(candidate_item) and _is_sibling_family_bundle(seated_item)):
        return False

    labels_a = _sibling_family_row_labels(candidate_item)
    labels_b = _sibling_family_row_labels(seated_item)
    if labels_a and labels_b:
        shared_labels = labels_a & labels_b
        min_rows = min(len(labels_a), len(labels_b))
        if len(shared_labels) >= 2 and (len(shared_labels) / min_rows) >= 0.5:
            return True

    tag_a = str(
        ((candidate_item.get("data") or {}).get("roundup") or {}).get("tag") or ""
    ).strip().upper()
    tag_b = str(
        ((seated_item.get("data") or {}).get("roundup") or {}).get("tag") or ""
    ).strip().upper()
    if not tag_a or not tag_b or tag_a == tag_b:
        toks_a = _sibling_family_title_tokens(candidate_item)
        toks_b = _sibling_family_title_tokens(seated_item)
        if toks_a and toks_b:
            shared_toks = toks_a & toks_b
            min_toks = min(len(toks_a), len(toks_b))
            if len(shared_toks) >= 2 and (len(shared_toks) / min_toks) >= 0.5:
                return True

    return False


MAX_SIBLING_FAMILY_IN_TOP_20 = 2

_CLIENT_SPORT_CATEGORIES: frozenset[str] = frozenset(
    {
        "basketball",
        "football",
        "baseball",
        "hockey",
        "soccer",
        "golf",
        "mma",
        "boxing",
        "tennis",
        "cricket",
        "motorsports",
        "americanfootball",
        "icehockey",
        "cycling",
    }
)


def _is_grouped_feed_card(item: Any) -> bool:
    """Return True when ``item`` is any grouped feed card (bundle, collection, or round-up)."""
    if not isinstance(item, Mapping):
        return False
    if item.get("type") in ("bundle", "collection"):
        return True
    return _is_roundup_bundle_card(item)


def _client_sport_category(item: Any) -> str:
    if not isinstance(item, Mapping):
        return "other"
    item_type = item.get("type")
    data = item.get("data")
    if not isinstance(data, Mapping):
        return "other"
    if item_type == "event":
        sport = str(data.get("sport") or "")
        return (sport.split("_")[0] if sport else "") or "sports"
    if item_type == "futures":
        return str(data.get("llm_sport_category") or "other")
    if item_type == "bundle":
        members = data.get("items")
        if isinstance(members, Sequence) and members:
            return _client_sport_category(members[0])
        return "other"
    return "golf"


def _client_space_by_sport(
    items: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if len(items) <= 2:
        return list(items)
    non_sports_count = sum(
        1 for it in items if _client_sport_category(it) not in _CLIENT_SPORT_CATEGORIES
    )
    max_sports_run = 2 if non_sports_count >= 4 else 3
    remaining = list(items)
    result: list[Mapping[str, Any]] = []
    last_sport = ""
    sports_since_non_sport = 0
    while remaining:
        pick = -1
        for idx, it in enumerate(remaining):
            cat = _client_sport_category(it)
            if cat not in _CLIENT_SPORT_CATEGORIES or (
                sports_since_non_sport < max_sports_run and cat != last_sport
            ):
                pick = idx
                break
        if pick == -1:
            for idx, it in enumerate(remaining):
                if _client_sport_category(it) != last_sport:
                    pick = idx
                    break
        if pick == -1:
            pick = 0
        chosen = remaining.pop(pick)
        cat = _client_sport_category(chosen)
        result.append(chosen)
        if cat in _CLIENT_SPORT_CATEGORIES:
            last_sport = cat
            sports_since_non_sport += 1
        else:
            last_sport = ""
            sports_since_non_sport = 0
    return result


def _spaced_has_adjacent_roundup(
    items: Sequence[Mapping[str, Any]],
) -> bool:
    spaced = _client_space_by_sport(_client_space_by_sport(items))
    for i in range(len(spaced) - 1):
        a, b = spaced[i], spaced[i + 1]
        if (
            _is_grouped_feed_card(a)
            and _is_grouped_feed_card(b)
            and (_is_roundup_bundle_card(a) or _is_roundup_bundle_card(b))
        ):
            return True
    return False


def _find_non_adjacent_roundup_seat(
    items: Sequence[Mapping[str, Any]],
    start_idx: int,
    *,
    floor_idx: int,
    candidate_item: Optional[Mapping[str, Any]] = None,
    page_window: int = 20,
) -> Optional[int]:
    """Find the earliest insertion index ``pos >= max(floor_idx, start_idx)`` where neither neighbour is a grouped card (Decision 123-A)."""
    start_pos = max(int(floor_idx), int(start_idx))
    n = len(items)
    first_raw_non_adjacent: Optional[int] = None
    pos = start_pos
    while pos <= n:
        prev_is_grouped = pos > 0 and _is_grouped_feed_card(items[pos - 1])
        next_is_grouped = pos < n and _is_grouped_feed_card(items[pos])
        if not prev_is_grouped and not next_is_grouped:
            if first_raw_non_adjacent is None:
                first_raw_non_adjacent = pos
            if candidate_item is None:
                return pos
            trial = [*items[:pos], candidate_item, *items[pos:]]
            window_slice = trial[: max(int(page_window), pos + 2)]
            if not _spaced_has_adjacent_roundup(window_slice):
                return pos
        pos += 1
    return first_raw_non_adjacent


def insert_roundup_feed_items(
    items: list[dict[str, Any]],
    roundup_items: Sequence[dict[str, Any]],
    *,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    page_window: int = 20,
    now: Optional[datetime] = None,
    returning_reader: bool = False,
    seen_card_keys: Optional[Sequence[str] | set[str]] = None,
    seen_futures_ids: Optional[Sequence[int] | set[int]] = None,
    seen_event_ids: Optional[Sequence[int] | set[int]] = None,
    novelty_seat_cap: int = ROUNDUP_NOVELTY_SEAT_CAP,
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
    * Under Decide 32-C (#12091 / #12376), when ``returning_reader=True``, up to
      ``novelty_seat_cap`` (2) unseen, opening-eligible round-up cards take the
      novelty seats at the back of the opening ten; first-time readers get zero.
    * Under Decision 123-A (#12374), at most ``MAX_SIBLING_FAMILY_IN_TOP_20`` (2)
      sibling-family round-up cards seat in Discover's first ``page_window`` (20)
      seats, and no two round-up cards sit in adjacent seats.
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

    raw_items = list(items)
    initial_floor_idx = _opening_eligible_floor_index(raw_items, seat_floor, now=now)
    preexisting_post_opening_roundups: list[Mapping[str, Any]] = []
    preexisting_target_by_id: dict[Any, int] = {}
    result: list[dict[str, Any]] = []
    changed = False
    for idx, it in enumerate(raw_items):
        if idx >= initial_floor_idx and _is_roundup_bundle_card(it):
            preexisting_post_opening_roundups.append(it)
            preexisting_target_by_id[it.get("data", {}).get("id")] = idx
            changed = True
        else:
            result.append(it)

    existing_bundle_ids = {
        it.get("data", {}).get("id")
        for it in result
        if isinstance(it, Mapping)
        and it.get("type") == "bundle"
        and isinstance(it.get("data"), Mapping)
    }
    seated_sibling_roundups: list[Mapping[str, Any]] = [
        it
        for it in result[:page_window]
        if isinstance(it, Mapping)
        and it.get("type") == "bundle"
        and _is_sibling_family_bundle(it)
    ]

    if preexisting_post_opening_roundups:
        reg_order = {slug: i for i, slug in enumerate(ROUNDUP_PRODUCERS.keys())}

        def _reg_sort_key(pair: tuple[int, Mapping[str, Any]]) -> tuple[int, int]:
            idx_in_combined, item = pair
            cref = item.get("data", {}).get("collection_ref")
            slug = (
                str(cref.get("slug") or "").strip() if isinstance(cref, Mapping) else ""
            )
            if not slug:
                raw_id = str(item.get("data", {}).get("id") or "").strip()
                slug = raw_id.removeprefix("roundup:")
            return (reg_order.get(slug, 10_000 + idx_in_combined), idx_in_combined)

        combined_raw = [*preexisting_post_opening_roundups, *valid_roundups]
        sorted_combined = [
            it for _, it in sorted(enumerate(combined_raw), key=_reg_sort_key)
        ]
    else:
        sorted_combined = list(valid_roundups)

    non_sibs = [it for it in sorted_combined if not _is_sibling_family_bundle(it)]
    sibs = [it for it in sorted_combined if _is_sibling_family_bundle(it)]
    if non_sibs and sibs:
        candidate_queue: list[Mapping[str, Any]] = []
        ns_idx = 0
        s_idx = 0
        while ns_idx < len(non_sibs) or s_idx < len(sibs):
            if ns_idx < len(non_sibs):
                candidate_queue.append(non_sibs[ns_idx])
                ns_idx += 1
            if s_idx < len(sibs) and (ns_idx >= 2 or ns_idx >= len(non_sibs)):
                candidate_queue.append(sibs[s_idx])
                s_idx += 1
    else:
        candidate_queue = sorted_combined
    accepted_roundups: list[Mapping[str, Any]] = []
    accepted_sibling_roundups: list[Mapping[str, Any]] = list(seated_sibling_roundups)
    for r_item in candidate_queue:
        r_id = r_item["data"].get("id")
        if r_id in existing_bundle_ids:
            continue
        if _is_sibling_family_bundle(r_item):
            r_score = float(r_item.get("score") or 0.0)
            if any(
                _is_near_identical_sibling_family(r_item, prev)
                for prev in accepted_sibling_roundups
            ) or any(
                other is not r_item
                and _is_sibling_family_bundle(other)
                and _is_near_identical_sibling_family(r_item, other)
                and float(other.get("score") or 0.0) > r_score
                for other in candidate_queue
            ):
                continue
            accepted_sibling_roundups.append(r_item)
        existing_bundle_ids.add(r_id)
        accepted_roundups.append(r_item)

    if not accepted_roundups and not changed:
        return items

    earliest_seat_by_id: dict[Any, Optional[int]] = {}
    for r_item in accepted_roundups:
        r_id = r_item["data"].get("id")
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
        earliest_seat_by_id[r_id] = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else preexisting_target_by_id.get(r_id)
        )

    inserted_count = 0
    for r_item in accepted_roundups:
        r_id = r_item["data"].get("id")
        is_sibling_card = _is_sibling_family_bundle(r_item)
        floor_idx = _opening_eligible_floor_index(result, seat_floor, now=now)
        default_seat = floor_idx + inserted_count
        earliest_post_opening_seat = earliest_seat_by_id.get(r_id)
        target_seat = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else default_seat
        )
        if is_sibling_card and len(seated_sibling_roundups) >= MAX_SIBLING_FAMILY_IN_TOP_20:
            target_seat = max(target_seat, page_window)

        desired_idx = min(max(floor_idx, target_seat), len(result))
        non_adj_idx = _find_non_adjacent_roundup_seat(
            result,
            desired_idx,
            floor_idx=max(
                floor_idx,
                page_window
                if (is_sibling_card and len(seated_sibling_roundups) >= MAX_SIBLING_FAMILY_IN_TOP_20)
                else floor_idx,
            ),
            candidate_item=r_item,
            page_window=page_window,
        )
        if non_adj_idx is None:
            continue
        target_idx = non_adj_idx
        if (
            is_sibling_card
            and len(seated_sibling_roundups) >= MAX_SIBLING_FAMILY_IN_TOP_20
            and target_idx < page_window
        ):
            continue

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
        if is_sibling_card and target_idx < page_window:
            seated_sibling_roundups.append(card)
        inserted_count += 1
        changed = True

    if not changed:
        return items

    if returning_reader and novelty_seat_cap > 0:
        result = apply_novelty_seats(
            result,
            returning_reader=returning_reader,
            seen_card_keys=seen_card_keys,
            seen_futures_ids=seen_futures_ids,
            seen_event_ids=seen_event_ids,
            seat_floor=seat_floor,
            novelty_seat_cap=novelty_seat_cap,
            now=now,
        )

    return result


async def add_roundup_feed_items(
    db: Any,
    items: list[dict[str, Any]],
    *,
    seat_floor: int = ROUNDUP_SEAT_FLOOR,
    page_window: int = 20,
    budget_seconds: float = ROUNDUP_READ_BUDGET_SECONDS,
    stage_budget_seconds: Optional[float] = None,
    now: Optional[datetime] = None,
    returning_reader: bool = False,
    seen_card_keys: Optional[Sequence[str] | set[str]] = None,
    seen_futures_ids: Optional[Sequence[int] | set[int]] = None,
    seen_event_ids: Optional[Sequence[int] | set[int]] = None,
    novelty_seat_cap: int = ROUNDUP_NOVELTY_SEAT_CAP,
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
                evaluate_roundup_producer(producer, db, now=now),
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
        returning_reader=returning_reader,
        seen_card_keys=seen_card_keys,
        seen_futures_ids=seen_futures_ids,
        seen_event_ids=seen_event_ids,
        novelty_seat_cap=novelty_seat_cap,
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
    parent_slug = str(
        data.get("parent_slug") or rule_raw.get("parent_slug") or ""
    ).strip()
    parent_name = str(
        data.get("parent_name") or rule_raw.get("parent_name") or ""
    ).strip()
    raw_children = (
        data.get("children")
        if "children" in data
        else rule_raw.get("children")
    )
    children_list: list[dict[str, Any]] = []
    if isinstance(raw_children, (list, tuple)):
        for ch in raw_children:
            if isinstance(ch, Mapping) and str(ch.get("slug") or "").strip():
                children_list.append(dict(ch))
    if parent_slug:
        out["parent_slug"] = parent_slug
        rule_copy["parent_slug"] = parent_slug
    if parent_name:
        out["parent_name"] = parent_name
        rule_copy["parent_name"] = parent_name
    if children_list:
        out["children"] = children_list
        rule_copy["children"] = children_list
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
    "subject_sequence": (
        "app.utils.subject_sequence",
        "build_subject_sequence_producer",
    ),
    "series_hub": (
        "app.utils.series_hub",
        "build_series_hub_producer",
    ),
    "tech_ai_race": (
        "app.utils.tech_ai_race",
        "build_tech_ai_race_producer",
    ),
    "team_active_streaks": (
        "app.utils.team_active_streaks",
        "build_team_active_streaks_producer",
    ),
    "big_movers_today": (
        "app.utils.big_movers_today",
        "build_big_movers_today_producer",
    ),
    "league_division_races": (
        "app.utils.league_division_races",
        "build_league_division_races_producer",
    ),
    "league_award_ladders": (
        "app.utils.league_award_ladders",
        "build_league_award_ladders_producer",
    ),
    "opening_weekend_slate": (
        "app.utils.opening_weekend_slate",
        "build_opening_weekend_slate_producer",
    ),
    "cross_domain_yardsticks": (
        "app.utils.cross_domain_yardsticks",
        "build_cross_domain_yardsticks_producer",
    ),
    "ceremony_award_categories": (
        "app.utils.ceremony_award_categories",
        "build_ceremony_award_categories_producer",
    ),
    "headliners_and_hosts": (
        "app.utils.headliners_and_hosts",
        "build_headliners_and_hosts_producer",
    ),
    "long_shot_movers": (
        "app.utils.long_shot_movers",
        "build_long_shot_movers_producer",
    ),
    "window_events_upsets": (
        "app.utils.window_events_upsets",
        "build_window_events_upsets_producer",
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
    "roundup-nfl-divisions": (
        "app.utils.discover_bundles",
        "NFL_DIVISION_ROUNDUP_PRODUCER",
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
    "celtics-next-3-games": (
        "app.utils.subject_sequence",
        "CELTICS_NEXT_3_GAMES_PRODUCER",
    ),
    "mlb-2026-alwc-bos-nyy": (
        "app.utils.series_hub",
        "MLB_2026_ALWC_BOS_NYY_PRODUCER",
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
