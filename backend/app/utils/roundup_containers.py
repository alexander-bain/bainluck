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
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import UUID

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
    "MORE_SETS_BUDGET_SECONDS",
    "MORE_SETS_LIMIT",
    "MORE_SETS_MAX_LEAD_AGE_SECONDS",
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
    "select_more_sets",
    "serve_roundup",
    "summarize_more_set_card",
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

#: Closed list of publication stages for computed groupings (#13097, Fable 2:03 PM PT).
#: ``preview`` sets are served only when ``machinery=preview`` is requested (and by
#: direct container URL) so Fable can inspect live numbers before one-line promotion
#: to ``public``.
CLOSED_GROUPING_STAGES: frozenset[str] = frozenset({"public", "preview"})

#: Closed list of visual looks for computed groupings (Alex 1:18 PM PT / #13097).
CLOSED_GROUPING_LOOKS: frozenset[str] = frozenset({"bars", "map", "faces"})

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
    "sections",
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
#: #13103 Part 3 item 3 — server-picked follow-on sets attached to GET /api/containers/{slug}.
MORE_SETS_LIMIT = 2
MORE_SETS_BUDGET_SECONDS = 0.35
#: Maximum age of a follow-on set's first-row price observation (24 hours).
MORE_SETS_MAX_LEAD_AGE_SECONDS = 86400.0
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
    paired_metric_set: Optional[dict[str, Any]] = None
    machinery_card: Optional[dict[str, Any]] = None
    covered_market_ids: tuple[int, ...] = ()

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
        paired_metric_set: Optional[Mapping[str, Any]] = None,
        machinery_card: Optional[Mapping[str, Any]] = None,
        covered_market_ids: Sequence[int] = (),
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
        object.__setattr__(
            self,
            "paired_metric_set",
            copy.deepcopy(dict(paired_metric_set))
            if isinstance(paired_metric_set, Mapping)
            else None,
        )
        object.__setattr__(
            self,
            "machinery_card",
            copy.deepcopy(dict(machinery_card))
            if isinstance(machinery_card, Mapping)
            else None,
        )
        object.__setattr__(
            self,
            "covered_market_ids",
            tuple(int(cid) for cid in (covered_market_ids or ())),
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
    stage: str = "public"
    look: str = "bars"

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
        stage: Optional[str] = None,
        look: Optional[str] = None,
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
        # Publication stage (`public` / `preview`) lives at the top level of the
        # definition, never in `rule["stage"]` (which ceremony producers use for
        # award stages such as `"winner"` / `"nomination"`).
        stage_clean = str(stage or "public").strip().lower()
        if stage_clean not in CLOSED_GROUPING_STAGES:
            raise ValueError(
                f"RoundupProducer {slug!r} has invalid stage {stage!r}; "
                f"allowed: {sorted(CLOSED_GROUPING_STAGES)}"
            )
        raw_look = (
            look
            if look is not None
            else (rule.get("look") if isinstance(rule, Mapping) else None)
        )
        look_clean = str(raw_look or "bars").strip().lower()
        if look_clean not in CLOSED_GROUPING_LOOKS:
            raise ValueError(
                f"RoundupProducer {slug!r} has invalid look {raw_look!r}; "
                f"allowed: {sorted(CLOSED_GROUPING_LOOKS)}"
            )
        object.__setattr__(self, "stage", stage_clean)
        object.__setattr__(self, "look", look_clean)


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
    out_sec: dict[str, Any] = {
        "class": str(section.get("class") or "title"),
        "title": str(section.get("title") or default_title),
        "layout": str(section.get("layout") or "field"),
        "count": len(norm_members),
        "members": norm_members,
    }
    if section.get("note"):
        out_sec["note"] = str(section["note"])
    if isinstance(section.get("visual_block"), Mapping):
        out_sec["visual_block"] = copy.deepcopy(dict(section["visual_block"]))
    return out_sec


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
    if getattr(members, "paired_metric_set", None) is not None:
        out_payload["paired_metric_set"] = copy.deepcopy(members.paired_metric_set)
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
    all_member_ids = list(
        dict.fromkeys(
            [
                *member_ids,
                *(
                    int(cid)
                    for cid in (getattr(members, "covered_market_ids", None) or ())
                ),
            ]
        )
    )
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
    if getattr(members, "paired_metric_set", None) is not None:
        roundup_contract["paired_metric_set"] = copy.deepcopy(members.paired_metric_set)
    if getattr(members, "machinery_card", None) is not None:
        roundup_contract["machinery_card"] = copy.deepcopy(members.machinery_card)
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
            "member_ids": all_member_ids,
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


ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S = 300.0
#: Hard Redis retention for machinery snapshots so Discover feed splices
#: (`ROUNDUP_PRODUCER_TIMEOUT_SECONDS = 0.5`) can serve last-known-good snapshots
#: while background prewarm refreshes them, instead of hitting a 0.5 s cold DB
#: timeout and dropping groupings from Discover (#12288).
ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S = 1800.0
ROUNDUP_MACHINERY_LIVE_STALE_TTL_S = 300.0
#: Redis hash tracking `machinery-*` slugs that currently hold a live game (or one
#: starting within `MACHINERY_IMMINENT_START_WINDOW_S`), read by the 30s realtime
#: republisher (`_prewarm_live_feed_shapes`) so live slates never expire between
#: 120s host beats. TTL outlives the 120s host beat by 2.5x.
MACHINERY_LIVE_SLUGS_KEY = "bainluck:roundup:machinery:live_slugs"
MACHINERY_LIVE_SLUGS_TTL_S = 300
MACHINERY_IMMINENT_START_WINDOW_S = 180.0
_TERMINAL_EVENT_STATUSES = frozenset(
    {"final", "completed", "closed", "cancelled", "canceled", "postponed"}
)


def _roundup_payload_has_live_event(container_payload: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(container_payload, Mapping):
        return False
    for sec in container_payload.get("sections") or ():
        if not isinstance(sec, Mapping):
            continue
        for m in sec.get("members") or ():
            if not isinstance(m, Mapping) or m.get("type") != "event":
                continue
            card = m.get("card")
            if isinstance(card, Mapping):
                st = str(card.get("status") or "").strip().lower()
                if st in {"live", "in_progress", "halftime"}:
                    return True
    return False


def _roundup_payload_needs_live_rail(
    container_payload: Optional[Mapping[str, Any]],
    *,
    now_ts: Optional[float] = None,
) -> bool:
    """True when a machinery grouping should be refreshed on the 30s live rail.

    Enrolls any slate with a live event OR a non-final event commencing within
    ``MACHINERY_IMMINENT_START_WINDOW_S`` (3 min) so the slate is already on the
    30s rail before tipoff/kickoff with zero cold gap at the opening whistle.
    """
    if _roundup_payload_has_live_event(container_payload):
        return True
    if not isinstance(container_payload, Mapping):
        return False
    ref_ts = time.time() if now_ts is None else float(now_ts)
    for sec in container_payload.get("sections") or ():
        if not isinstance(sec, Mapping):
            continue
        for m in sec.get("members") or ():
            if not isinstance(m, Mapping) or m.get("type") != "event":
                continue
            card = m.get("card")
            if not isinstance(card, Mapping):
                continue
            st = str(card.get("status") or "").strip().lower()
            if st in _TERMINAL_EVENT_STATUSES:
                continue
            raw_ct = card.get("commence_time")
            if not isinstance(raw_ct, str) or not raw_ct.strip():
                continue
            try:
                ct_dt = datetime.fromisoformat(raw_ct.replace("Z", "+00:00"))
                if ct_dt.tzinfo is None:
                    ct_dt = ct_dt.replace(tzinfo=timezone.utc)
                ct_ts = ct_dt.timestamp()
            except ValueError:
                continue
            if (ref_ts - 21600.0) <= ct_ts <= (ref_ts + MACHINERY_IMMINENT_START_WINDOW_S):
                return True
    return False


def _record_machinery_live_origin(
    built_at: float,
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
) -> None:
    """Feed a cached live machinery grouping's origin into the LAT-P230 age sink."""
    if not (
        _is_machinery_producer_slug(slug)
        and _roundup_payload_has_live_event(container_payload)
    ):
        return
    try:
        from app.utils.principal_independent_cache import _age_sink_var

        sink = _age_sink_var.get()
        if sink is not None:
            sink.append(float(built_at))
    except Exception:  # noqa: BLE001 — telemetry sink is best-effort
        pass


def _roundup_cache_ttl_seconds(
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
) -> float:
    """TTL for a cached roundup entry.

    Machinery groupings (`machinery-*`) keep the tight 60s TTL whenever they hold
    a live game (matching `FEED_RESPONSE_STALE_TTL_LIVE_SECONDS`), and use a 300s
    TTL for scheduled/futures groupings so the 120s background prewarmer keeps
    every reader read warm across beat jitter.
    """
    if (
        _is_machinery_producer_slug(slug)
        and container_payload is not None
        and not _roundup_payload_has_live_event(container_payload)
    ):
        return ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S
    return ROUNDUP_CACHE_TTL_S


def _roundup_cache_stale_ttl_seconds(
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
) -> float:
    """Hard Redis retention TTL (stale-while-revalidate window) for a roundup entry."""
    if _is_machinery_producer_slug(slug) and container_payload is not None:
        if _roundup_payload_has_live_event(container_payload):
            return ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
        return ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
    return _roundup_cache_ttl_seconds(slug, container_payload)


def _roundup_cache_json_default(obj: Any) -> Any:
    """JSON fallback for roundup cache payloads containing non-primitive scalars."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _encode_roundup_cache_entry(
    *,
    ts: float,
    ttl_s: float,
    stale_ttl_s: float,
    feed_item: Optional[dict[str, Any]],
    container_payload: Optional[dict[str, Any]],
    clean_empty: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "built_at": ts,
        "ttl_s": ttl_s,
        "stale_ttl_s": stale_ttl_s,
        "feed_item": feed_item,
        "container_payload": container_payload,
    }
    if clean_empty:
        payload["clean_empty"] = True
    return json.dumps(
        payload,
        separators=(",", ":"),
        default=_roundup_cache_json_default,
    )


def store_roundup_cache_sync(
    rc: Any,
    slug: str,
    ts: float,
    feed_item: Optional[dict[str, Any]],
    container_payload: Optional[dict[str, Any]],
) -> bool:
    """Publish a roundup cache entry + live-slug registration via sync Redis.

    Used by Celery prewarm workers only (where `asyncio.run()` closes the event
    loop between tasks and breaks process-global async Redis pools). Never
    called from the web event loop (#969, #12288).
    """
    if rc is None or not hasattr(rc, "set"):
        return False
    ttl_s = _roundup_cache_ttl_seconds(slug, container_payload)
    stale_ttl_s = _roundup_cache_stale_ttl_seconds(slug, container_payload)
    try:
        encoded = _encode_roundup_cache_entry(
            ts=ts,
            ttl_s=ttl_s,
            stale_ttl_s=stale_ttl_s,
            feed_item=feed_item,
            container_payload=container_payload,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(stale_ttl_s))
        if _is_machinery_producer_slug(slug) and container_payload is not None:
            if _roundup_payload_needs_live_rail(container_payload, now_ts=ts):
                if hasattr(rc, "hset"):
                    rc.hset(MACHINERY_LIVE_SLUGS_KEY, slug, str(ts))
                if hasattr(rc, "expire"):
                    rc.expire(MACHINERY_LIVE_SLUGS_KEY, MACHINERY_LIVE_SLUGS_TTL_S)
            else:
                if hasattr(rc, "hdel"):
                    rc.hdel(MACHINERY_LIVE_SLUGS_KEY, slug)
        return True
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning(
            "roundup_containers: sync Redis cache write failed for %s",
            slug,
            exc_info=True,
        )
        return False


def store_roundup_clean_empty_sync(
    rc: Any,
    slug: str,
    ts: float,
    *,
    ttl_s: float = ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S,
    lifetime_s: float = ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
) -> bool:
    """Record a clean-empty marker in Redis when a grouping producer ran cleanly with nothing to show (#13183).

    Used by Celery prewarm workers only (never on the web event loop — #969).
    Lets `_publish_machinery_feed_from_prewarm_base` distinguish an intentionally
    quiet/out-of-season grouping from a failed or expired one.
    """
    if rc is None or not hasattr(rc, "set"):
        return False
    try:
        encoded = _encode_roundup_cache_entry(
            ts=ts,
            ttl_s=float(ttl_s),
            stale_ttl_s=float(lifetime_s),
            feed_item=None,
            container_payload=None,
            clean_empty=True,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(lifetime_s))
        if _is_machinery_producer_slug(slug) and hasattr(rc, "hdel"):
            rc.hdel(MACHINERY_LIVE_SLUGS_KEY, slug)
        return True
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning(
            "roundup_containers: sync Redis clean-empty write failed for %s",
            slug,
            exc_info=True,
        )
        return False


def verify_roundup_cache_sync(
    rc: Any,
    slug: str,
    *,
    allow_clean_empty: bool = False,
) -> tuple[bool, Optional[int]]:
    """Read back a just-written roundup cache key via sync Redis and verify TTL + decode.

    Used by Celery prewarm workers only (never on the web event loop — #969, #12288).
    Returns ``(ok, ttl_seconds)`` where ``ok`` is True only when the key exists,
    decodes through the same JSON reader path as ``evaluate_roundup_producer``,
    carries both ``feed_item`` and ``container_payload`` (or a valid ``clean_empty``
    marker when ``allow_clean_empty=True``), and (when ``rc.ttl`` is available)
    has a positive TTL remaining.
    """
    if rc is None or not hasattr(rc, "get"):
        return False, None
    key = _redis_cache_key(slug)
    try:
        raw_val = rc.get(key)
        if not raw_val:
            return False, None
        ttl_remaining: Optional[int] = None
        if hasattr(rc, "ttl"):
            raw_ttl = rc.ttl(key)
            if isinstance(raw_ttl, (int, float)):
                ttl_remaining = int(raw_ttl)
                if ttl_remaining <= 0:
                    return False, ttl_remaining
        decoded = json.loads(
            raw_val.decode("utf-8")
            if isinstance(raw_val, (bytes, bytearray))
            else raw_val
        )
        if not isinstance(decoded, dict):
            return False, ttl_remaining
        if not isinstance(decoded.get("built_at"), (int, float)):
            return False, ttl_remaining
        if allow_clean_empty and decoded.get("clean_empty") is True:
            return True, ttl_remaining
        if decoded.get("feed_item") is None or decoded.get("container_payload") is None:
            return False, ttl_remaining
        return True, ttl_remaining
    except Exception:  # noqa: BLE001 — verification is best-effort
        logger.warning(
            "roundup_containers: sync Redis read-back failed for %s",
            slug,
            exc_info=True,
        )
        return False, None


async def _store_roundup_cache_entry(
    cache_key: tuple[str, Any],
    slug: str,
    ts: float,
    feed_item: Optional[dict[str, Any]],
    container_payload: Optional[dict[str, Any]],
    db: Any,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    ttl_s = _roundup_cache_ttl_seconds(slug, container_payload)
    stale_ttl_s = _roundup_cache_stale_ttl_seconds(slug, container_payload)
    _roundup_local_cache[cache_key] = (
        ts,
        copy.deepcopy(feed_item),
        copy.deepcopy(container_payload),
    )
    if isinstance(db, AsyncSession):
        try:
            encoded = _encode_roundup_cache_entry(
                ts=ts,
                ttl_s=ttl_s,
                stale_ttl_s=stale_ttl_s,
                feed_item=feed_item,
                container_payload=container_payload,
            )
        except (TypeError, ValueError):
            logger.warning(
                "roundup_containers: shared cache encode failed for %s",
                slug,
                exc_info=True,
            )
            return
        wrote_async = False
        try:
            from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

            client = await get_shared_async_redis()
            set_res = await bounded_redis_call(
                lambda: client.set(
                    _redis_cache_key(slug),
                    encoded,
                    ex=int(stale_ttl_s),
                ),
                treat_none_as_miss=False,
            )
            wrote_async = bool(set_res.is_ok)
            if wrote_async and _is_machinery_producer_slug(slug) and container_payload is not None:
                if _roundup_payload_needs_live_rail(container_payload, now_ts=ts):
                    await bounded_redis_call(
                        lambda: client.hset(MACHINERY_LIVE_SLUGS_KEY, slug, str(ts)),
                        treat_none_as_miss=False,
                    )
                    await bounded_redis_call(
                        lambda: client.expire(
                            MACHINERY_LIVE_SLUGS_KEY, MACHINERY_LIVE_SLUGS_TTL_S
                        ),
                        treat_none_as_miss=False,
                    )
                else:
                    await bounded_redis_call(
                        lambda: client.hdel(MACHINERY_LIVE_SLUGS_KEY, slug),
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
    force_refresh: bool = False,
    allow_stale: bool = False,
    outcome_meta: Optional[dict[str, Any]] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Run ``producer`` once and return ``(feed_item, container_payload)``, cached 60s per slug."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    if outcome_meta is not None:
        outcome_meta["clean_empty"] = False
        outcome_meta["reason"] = None

    if producer.enabled is not None and not producer.enabled():
        if outcome_meta is not None:
            outcome_meta["reason"] = "disabled"
        return None, None

    is_fixture_seq = isinstance(db, (list, tuple))
    ts, now_dt = _normalize_roundup_now(now)
    # Check before either cache. An old card's warm payload must not outlive
    # its definition at the instant the dated successor takes over (65-A).
    if (producer.valid_from is not None and ts < producer.valid_from) or (
        producer.valid_until is not None and ts >= producer.valid_until
    ):
        if outcome_meta is not None:
            outcome_meta["clean_empty"] = True
            outcome_meta["reason"] = "outside_window"
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
            if outcome_meta is not None:
                outcome_meta["reason"] = "suspended"
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

    if use_cache and not force_refresh:
        is_machinery = _is_machinery_producer_slug(producer.slug)
        local_stale_fallback: Optional[tuple[float, dict[str, Any], dict[str, Any]]] = None
        cached = _roundup_local_cache.get(cache_key)
        if cached is not None:
            local_ttl = _roundup_cache_ttl_seconds(producer.slug, cached[2])
            if (ts - cached[0]) < local_ttl:
                _record_machinery_live_origin(cached[0], producer.slug, cached[2])
                return copy.deepcopy(cached[1]), copy.deepcopy(cached[2])
            if (
                allow_stale
                and is_machinery
                and cached[1] is not None
                and cached[2] is not None
            ):
                local_stale_ttl = _roundup_cache_stale_ttl_seconds(
                    producer.slug, cached[2]
                )
                if (ts - cached[0]) < local_stale_ttl:
                    local_stale_fallback = (cached[0], cached[1], cached[2])
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
                    raw_ttl = (
                        float(raw.get("ttl_s") or ROUNDUP_CACHE_TTL_S)
                        if isinstance(raw, dict)
                        else ROUNDUP_CACHE_TTL_S
                    )
                    if isinstance(raw, dict) and isinstance(
                        raw.get("built_at"), (int, float)
                    ):
                        built_at = float(raw["built_at"])
                        fi = raw.get("feed_item")
                        cp = raw.get("container_payload")
                        age_s = ts - built_at
                        if age_s < raw_ttl:
                            _roundup_local_cache[cache_key] = (built_at, fi, cp)
                            _record_machinery_live_origin(built_at, producer.slug, cp)
                            return copy.deepcopy(fi), copy.deepcopy(cp)
                        if allow_stale and is_machinery and fi is not None and cp is not None:
                            stale_max_s = float(
                                raw.get("stale_ttl_s")
                                or _roundup_cache_stale_ttl_seconds(producer.slug, cp)
                            )
                            if age_s < stale_max_s:
                                _record_machinery_live_origin(
                                    built_at, producer.slug, cp
                                )
                                return copy.deepcopy(fi), copy.deepcopy(cp)
            except Exception:  # noqa: BLE001 — cache read fails open
                logger.debug(
                    "roundup_containers: shared cache read failed for %s",
                    producer.slug,
                    exc_info=True,
                )
        if local_stale_fallback is not None:
            _record_machinery_live_origin(
                local_stale_fallback[0], producer.slug, local_stale_fallback[2]
            )
            return copy.deepcopy(local_stale_fallback[1]), copy.deepcopy(
                local_stale_fallback[2]
            )

    if now_dt is not None and "now" in inspect.signature(producer.produce).parameters:
        outcome = producer.produce(db, now=now_dt)
    else:
        outcome = producer.produce(db)
    if inspect.isawaitable(outcome):
        outcome = await outcome

    if outcome is None or isinstance(outcome, RoundupRefusal):
        reasons = list(outcome.reasons) if isinstance(outcome, RoundupRefusal) else []
        cacheable = _is_cacheable_refusal(reasons)
        if outcome_meta is not None:
            outcome_meta["clean_empty"] = bool(cacheable)
            outcome_meta["reason"] = "clean_empty_refusal" if cacheable else "transient_refusal"
        logger.warning(
            "flow_sentinel matching_defect: roundup %s refused reasons=%s",
            producer.slug,
            reasons,
        )
        if use_cache and cacheable:
            await _store_roundup_cache_entry(
                cache_key, producer.slug, ts, None, None, db
            )
        return None, None

    if not isinstance(outcome, RoundupMembers):
        outcome = RoundupMembers(outcome)

    container_payload = compose_roundup_container(producer, outcome)
    feed_item = compose_roundup_feed_item(producer, outcome)
    if (
        _is_machinery_producer_slug(producer.slug)
        and container_payload is not None
        and _roundup_payload_has_live_event(container_payload)
        and isinstance(feed_item, dict)
        and isinstance(feed_item.get("data"), dict)
    ):
        # Stamp `status="live"` so `feed_cache.payload_contains_live_event`
        # automatically bounds any Discover page carrying a live machinery slate
        # to the 60s live ceiling (`FEED_RESPONSE_STALE_TTL_LIVE_SECONDS`).
        feed_item["data"]["status"] = "live"
    if container_payload is None or (
        feed_item is None and not getattr(outcome, "suppress_feed_item", False)
    ):
        if outcome_meta is not None:
            outcome_meta["clean_empty"] = True
            outcome_meta["reason"] = "empty_payload"
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
                if outcome_meta is not None:
                    outcome_meta["clean_empty"] = False
                    outcome_meta["reason"] = "licence_violation"
                logger.warning(
                    "flow_sentinel matching_defect: roundup %s suspended kind %s (%s)",
                    producer.slug,
                    producer_kind,
                    bad_reason,
                )
                return None, None

    if (
        _is_machinery_producer_slug(producer.slug)
        and feed_item is not None
        and isinstance(db, AsyncSession)
    ):
        # Ruling 188 (#11937, #12288): screen every machinery Discover feed card
        # ONCE at build time before caching (covering BOTH Celery prewarm AND
        # reader-path inline rebuilds), so no unscreened entry can ever land in
        # Redis and hot `machinery_only` splices pay zero DB queries.
        try:
            from app.utils.not_trading import drop_not_trading_roundup_members

            _screened = await drop_not_trading_roundup_members(
                db,
                [feed_item],
                now_dt or datetime.now(timezone.utc),
                _roundup_covered_market_ids,
            )
            feed_item = _screened[0] if _screened else None
        except Exception:  # noqa: BLE001 — keep card on transient screen error
            logger.warning(
                "roundup_containers: not-trading screen failed for %s; keeping card",
                producer.slug,
                exc_info=True,
            )
        if feed_item is None:
            if outcome_meta is not None:
                outcome_meta["clean_empty"] = True
                outcome_meta["reason"] = "not_trading_screen_empty"
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


def _strip_parent_from_payload(out: dict[str, Any]) -> None:
    out.pop("parent", None)
    if isinstance(out.get("container"), dict):
        out["container"]["parent_container_id"] = None
        out["container"].pop("parent_slug", None)
        out["container"].pop("parent_name", None)


def ensure_optional_roundup_candidates() -> None:
    """Register flag-gated candidate roundup producers when explicitly enabled."""
    import importlib
    import os

    flag = os.environ.get("CONTAINER_MACHINERY_SLICE1_ENABLED", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        mod = importlib.import_module("app.utils.container_machinery")
        mod.register_machinery_slice1_candidates()


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _first_present_iso(*values: Any) -> Optional[str]:
    for val in values:
        if isinstance(val, str) and val.strip() and _parse_iso_timestamp(val) is not None:
            return val.strip()
    return None


def _valid_rendered_percent(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        return value
    return None


def _extract_more_set_lead(
    payload: Mapping[str, Any],
) -> tuple[Optional[str], Optional[float], Optional[int], Optional[str]]:
    """Extract the lead (label, probability, rendered_percent, as_of) strictly from the set's own first row."""
    sections = payload.get("sections")
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return None, None, None, None
    first_member: Optional[Mapping[str, Any]] = None
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        members = section.get("members")
        if isinstance(members, Sequence) and not isinstance(members, (str, bytes)) and len(members) > 0:
            candidate = members[0]
            if isinstance(candidate, Mapping):
                first_member = candidate
            break
    if first_member is None:
        return None, None, None, None

    card = first_member.get("card")
    if not isinstance(card, Mapping):
        return None, None, None, None
    mtype = first_member.get("type")

    if mtype == MEMBER_MARKET:
        outcomes = card.get("top_outcomes")
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            return None, None, None, None
        valid_outcomes: list[tuple[Mapping[str, Any], str, float]] = []
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                continue
            prob = outcome.get("probability")
            if (
                isinstance(prob, (int, float))
                and not isinstance(prob, bool)
                and 0.0 <= float(prob) <= 1.0
            ):
                valid_outcomes.append((outcome, str(outcome.get("name") or "").strip(), float(prob)))
        if not valid_outcomes:
            return None, None, None, None

        card_name = str(card.get("name") or "").strip()
        outcome_names_lower = {nm.lower() for _, nm, _ in valid_outcomes}
        if outcome_names_lower.issubset({"yes", "no"}):
            chosen_outcome, raw_name, prob = next(
                (item for item in valid_outcomes if item[1].lower() == "yes"),
                valid_outcomes[0],
            )
            label = card_name or raw_name
        else:
            chosen_outcome, raw_name, prob = max(valid_outcomes, key=lambda item: item[2])
            label = raw_name or card_name
        if not label:
            return None, None, None, None

        rendered_pct = _valid_rendered_percent(chosen_outcome.get("rendered_percent"))

        source_obs: Optional[str] = None
        smark = chosen_outcome.get("source_mark")
        sources = smark.get("sources") if isinstance(smark, Mapping) else None
        if isinstance(sources, Sequence) and not isinstance(sources, (str, bytes)):
            for src in sources:
                obs = src.get("observed_at") if isinstance(src, Mapping) else None
                if isinstance(obs, str) and obs.strip():
                    source_obs = obs.strip()
                    break
        as_of = _first_present_iso(
            card.get("price_observed_at"),
            card.get("prices_updated_at"),
            card.get("newest_outcome_updated_at"),
            source_obs,
            card.get("updated_at"),
            card.get("last_updated"),
            card.get("odds_updated_at"),
        )
        return label, round(prob, 4), rendered_pct, as_of

    if mtype == "event":
        home = str(card.get("home_team") or "").strip()
        away = str(card.get("away_team") or "").strip()
        hp = card.get("hero_probability")
        ap = card.get("hero_probability_away")
        odds = card.get("current_odds") if isinstance(card.get("current_odds"), Mapping) else {}
        if not (isinstance(hp, (int, float)) and not isinstance(hp, bool)):
            hp = odds.get("home_win_probability")
        if not (isinstance(ap, (int, float)) and not isinstance(ap, bool)):
            ap = odds.get("away_win_probability")
        pairs: list[tuple[str, float, Optional[int]]] = []
        if home and isinstance(hp, (int, float)) and not isinstance(hp, bool) and 0.0 <= float(hp) <= 1.0:
            pairs.append((home, float(hp), _valid_rendered_percent(odds.get("home_rendered_percent"))))
        if away and isinstance(ap, (int, float)) and not isinstance(ap, bool) and 0.0 <= float(ap) <= 1.0:
            pairs.append((away, float(ap), _valid_rendered_percent(odds.get("away_rendered_percent"))))
        if not pairs:
            return None, None, None, None
        pairs.sort(key=lambda item: item[1], reverse=True)
        label, prob, rendered_pct = pairs[0]
        src_updated: Optional[str] = None
        wps = card.get("win_probability_sources")
        if isinstance(wps, Mapping):
            for src in wps.values():
                if isinstance(src, Mapping):
                    u = src.get("updated_at")
                    if isinstance(u, str) and u.strip():
                        src_updated = u.strip()
                        break
        as_of = _first_present_iso(
            card.get("hero_probability_observed_at"),
            card.get("newest_outcome_updated_at"),
            odds.get("updated_at"),
            src_updated,
            card.get("updated_at"),
            card.get("last_updated"),
        )
        return label, round(prob, 4), rendered_pct, as_of

    return None, None, None, None


def summarize_more_set_card(
    payload: Mapping[str, Any],
    *,
    now: Optional[float | datetime] = None,
    max_age_seconds: float = MORE_SETS_MAX_LEAD_AGE_SECONDS,
) -> Optional[dict[str, Any]]:
    """Project a verified published container payload into a below-the-set link card (#13103).

    Requires a real priced first row observed within ``max_age_seconds`` (24h).
    Sets without a fresh first-row observation are never offered.
    """
    if not isinstance(payload, Mapping) or payload.get("state") != "published":
        return None
    container = payload.get("container")
    if not isinstance(container, Mapping):
        return None
    slug = str(payload.get("slug") or container.get("slug") or "").strip()
    name = str(container.get("name") or "").strip()
    if not slug or not name:
        return None
    raw_count = payload.get("member_count")
    member_count = (
        int(raw_count)
        if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count > 0
        else 0
    )
    if member_count <= 0:
        sections = payload.get("sections")
        if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
            member_count = sum(
                len(sec.get("members") or ())
                for sec in sections
                if isinstance(sec, Mapping)
                and isinstance(sec.get("members"), Sequence)
                and not isinstance(sec.get("members"), (str, bytes))
            )
    if member_count <= 0:
        return None

    lead_label, lead_probability, lead_rendered_percent, as_of = _extract_more_set_lead(payload)
    if not lead_label or lead_probability is None or not as_of:
        return None
    observed_dt = _parse_iso_timestamp(as_of)
    if observed_dt is None:
        return None
    ts, _now_dt = _normalize_roundup_now(now)
    age_s = ts - observed_dt.timestamp()
    if age_s > max_age_seconds or age_s < -300.0:
        return None

    raw_dek = payload.get("dek") or payload.get("subtitle")
    dek = raw_dek.strip() if isinstance(raw_dek, str) and raw_dek.strip() else None
    raw_cat = container.get("category")
    category = raw_cat.strip().lower() if isinstance(raw_cat, str) and raw_cat.strip() else None
    out: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "href": f"/collections/{slug}",
        "destination": container_destination(slug),
        "category": category,
        "dek": dek,
        "member_count": member_count,
        "lead_label": lead_label,
        "lead_probability": lead_probability,
        "as_of": as_of,
    }
    if lead_rendered_percent is not None:
        out["lead_rendered_percent"] = lead_rendered_percent
    return out


def _pick_diverse_more_sets(
    cards: Sequence[dict[str, Any]],
    *,
    current_slug: str,
    current_category: Optional[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Choose up to ``limit`` cards preferring distinct categories, live odds, and spread."""
    chosen: list[dict[str, Any]] = []
    remaining = list(cards)
    used_categories: set[str] = set()
    cur_cat = current_category.strip().lower() if isinstance(current_category, str) and current_category.strip() else None

    def _tie(slug: str) -> int:
        return zlib.crc32(f"{current_slug}:{slug}".encode("utf-8"))

    while remaining and len(chosen) < limit:
        best_idx = 0
        best_key: tuple[int, int, int, int] = (-1, -1, -1, 0)
        for idx, card in enumerate(remaining):
            cat = card.get("category")
            distinct_from_picked = 1 if (cat and cat not in used_categories) else 0
            distinct_from_current = 1 if (cur_cat is None or (cat and cat != cur_cat)) else 0
            prob = card.get("lead_probability")
            competitive = (
                1
                if isinstance(prob, (int, float)) and 0.05 <= float(prob) <= 0.95
                else 0
            )
            key = (distinct_from_picked, distinct_from_current, competitive, _tie(str(card.get("slug") or "")))
            if key > best_key:
                best_key = key
                best_idx = idx
        picked = remaining.pop(best_idx)
        chosen.append(picked)
        if picked.get("category"):
            used_categories.add(str(picked["category"]))
    return chosen


async def select_more_sets(
    db: Any,
    *,
    exclude_slugs: Sequence[str] | set[str] | frozenset[str],
    current_slug: str = "",
    current_category: Optional[str] = None,
    limit: int = MORE_SETS_LIMIT,
    budget_seconds: float = MORE_SETS_BUDGET_SECONDS,
    now: Optional[float | datetime] = None,
    evaluate_uncached: Optional[bool] = None,
) -> list[dict[str, Any]]:
    """Pick up to ``limit`` fresh published sets below a container page (#13103).

    - Each offered set's own first row must be priced within the last 24 hours.
    - Machinery sets are included whenever ``container_machinery_enabled()`` is on
      (the exact gate the set's own page reads) and excluded only while off.
    - Prefers warm process-local roundup cache entries (0 ms, zero extra DB
      queries), then evaluates additional eligible producers within
      ``budget_seconds`` on a live ``AsyncSession``, failing open.
    """
    import importlib

    from sqlalchemy.ext.asyncio import AsyncSession

    if limit <= 0:
        return []

    ensure_optional_roundup_candidates()
    machinery_public = bool(
        importlib.import_module("app.utils.container_machinery").container_machinery_enabled()
    )
    excluded = {str(s).strip() for s in exclude_slugs if str(s).strip()}
    ts, _now_dt = _normalize_roundup_now(now)
    cur_cat = current_category.strip().lower() if isinstance(current_category, str) and current_category.strip() else None
    cache_db_key: Any = "live" if isinstance(db, AsyncSession) else id(db)

    eligible: list[RoundupProducer] = []
    for producer in ROUNDUP_PRODUCERS.values():
        slug = producer.slug
        if (
            slug in excluded
            or slug.startswith("for-scale-")
            or (_is_machinery_producer_slug(slug) and not machinery_public)
            or getattr(producer, "stage", "public") != "public"
        ):
            continue
        if producer.enabled is not None and not producer.enabled():
            continue
        if (producer.valid_from is not None and ts < producer.valid_from) or (
            producer.valid_until is not None and ts >= producer.valid_until
        ):
            continue
        eligible.append(producer)

    warm_cards: list[dict[str, Any]] = []
    warm_slugs: set[str] = set()
    cold_candidates: list[RoundupProducer] = []

    for producer in sorted(
        eligible,
        key=lambda p: (
            0 if (cur_cat and (p.category or "").strip().lower() != cur_cat) else 1,
            -zlib.crc32(f"{current_slug}:{p.slug}".encode("utf-8")),
        ),
    ):
        cached = _roundup_local_cache.get((producer.slug, cache_db_key))
        if cached is not None:
            local_ttl = _roundup_cache_ttl_seconds(producer.slug, cached[2])
            if (ts - cached[0]) < local_ttl:
                card = (
                    summarize_more_set_card(cached[2], now=ts)
                    if isinstance(cached[2], Mapping)
                    else None
                )
                if card is not None:
                    warm_cards.append(card)
                    warm_slugs.add(producer.slug)
                continue
        cold_candidates.append(producer)

    collected = list(warm_cards)
    seen_slugs = set(warm_slugs)

    should_eval_cold = (
        bool(evaluate_uncached)
        if evaluate_uncached is not None
        else isinstance(db, AsyncSession)
    )
    if should_eval_cold and len(collected) < limit and cold_candidates and budget_seconds > 0:
        deadline = time.monotonic() + budget_seconds
        for producer in cold_candidates:
            if len(collected) >= limit + 2:
                break
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0.02:
                break
            try:
                _fi, payload = await asyncio.wait_for(
                    evaluate_roundup_producer(producer, db, now=now),
                    timeout=min(remaining_s, ROUNDUP_PRODUCER_TIMEOUT_SECONDS),
                )
            except Exception:  # noqa: BLE001 — fail open, never break container read
                logger.debug("select_more_sets: candidate %s skipped", producer.slug, exc_info=True)
                continue
            card = summarize_more_set_card(payload, now=ts) if isinstance(payload, Mapping) else None
            if card is not None and card["slug"] not in seen_slugs:
                collected.append(card)
                seen_slugs.add(card["slug"])

    return _pick_diverse_more_sets(
        collected,
        current_slug=current_slug,
        current_category=cur_cat,
        limit=limit,
    )


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

    ensure_optional_roundup_candidates()
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

    excluded = {slug}
    if isinstance(out.get("parent"), Mapping) and out["parent"].get("slug"):
        excluded.add(str(out["parent"]["slug"]))
    for ch in out.get("children") or ():
        if isinstance(ch, Mapping) and ch.get("slug"):
            excluded.add(str(ch["slug"]))
    cur_cat = (
        out.get("container", {}).get("category")
        if isinstance(out.get("container"), Mapping)
        else None
    )
    more_sets = await select_more_sets(
        db,
        exclude_slugs=excluded,
        current_slug=slug,
        current_category=cur_cat,
        now=now,
    )
    if more_sets:
        out["more_sets"] = more_sets
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

    if not (
        (mode or "discover").lower() == "discover"
        and bool(include_events)
        and bool(include_futures)
        and not my_teams_only
        and not debug
        and not category
        and not sport
        and containers_read_enabled()
    ):
        return False
    ensure_optional_roundup_candidates()
    return any(
        p.enabled is None or p.enabled() for p in ROUNDUP_PRODUCERS.values()
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


def _roundup_item_slug(item: Mapping[str, Any]) -> str:
    data = item.get("data")
    if not isinstance(data, Mapping):
        return ""
    cref = data.get("collection_ref")
    if isinstance(cref, Mapping):
        slug = str(cref.get("slug") or "").strip()
        if slug:
            return slug
    raw_id = str(data.get("id") or "").strip()
    if raw_id.startswith("roundup:"):
        return raw_id.removeprefix("roundup:")
    return raw_id


def _is_machinery_roundup_item(item: Mapping[str, Any]) -> bool:
    """Return True only for container-machinery groupings (#12288), never standing round-ups."""
    slug = _roundup_item_slug(item)
    if not slug:
        return False
    prod = ROUNDUP_PRODUCERS.get(slug)
    rule = prod.rule if prod is not None and isinstance(prod.rule, Mapping) else None
    if isinstance(rule, Mapping) and rule.get("producer") == "container_machinery":
        return True
    return slug.startswith("machinery-")


def _roundup_slug_variants(slug: str) -> set[str]:
    clean = str(slug or "").strip().lower()
    if not clean:
        return set()
    variants = {clean}
    if clean.startswith("roundup-"):
        variants.add(clean.removeprefix("roundup-"))
    else:
        variants.add(f"roundup-{clean}")
    return variants


def _roundup_replaces_spec(item: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """Return ``(replaces_themes, replaces_roundup_variants)`` declared on ``item``'s producer rule."""
    slug = _roundup_item_slug(item)
    prod = ROUNDUP_PRODUCERS.get(slug) if slug else None
    rule = prod.rule if prod is not None and isinstance(prod.rule, Mapping) else None
    if not isinstance(rule, Mapping):
        return set(), set()
    themes = {
        str(t or "").strip().lower()
        for t in (rule.get("replaces_themes") or ())
        if str(t or "").strip()
    }
    roundups: set[str] = set()
    for r in rule.get("replaces") or ():
        roundups.update(_roundup_slug_variants(str(r or "")))
    return themes, roundups


def _item_replaced_by_spec(
    item: Mapping[str, Any],
    replaces_themes: set[str],
    replaces_roundups: set[str],
) -> bool:
    if not isinstance(item, Mapping) or item.get("type") != "bundle":
        return False
    data = item.get("data")
    if not isinstance(data, Mapping):
        return False
    kind = str(data.get("kind") or "").strip().lower()
    if replaces_themes and kind == "theme":
        raw_id = str(data.get("id") or "").strip().lower()
        story_key = str(data.get("story_key") or item.get("story_key") or "").strip().lower()
        for t in replaces_themes:
            if (
                raw_id == f"theme:{t}"
                or raw_id.startswith(f"theme:{t}:")
                or story_key == t
            ):
                return True
    if replaces_roundups and _is_roundup_bundle_card(item):
        slug = _roundup_item_slug(item)
        if slug and (_roundup_slug_variants(slug) & replaces_roundups):
            return True
    return False


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
    preserve_existing_roundups: bool = False,
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

    replaces_by_rid: dict[Any, tuple[set[str], set[str]]] = {}
    all_replaces_roundups: set[str] = set()
    for r in valid_roundups:
        r_themes, r_roundups = _roundup_replaces_spec(r)
        if r_themes or r_roundups:
            replaces_by_rid[r["data"].get("id")] = (r_themes, r_roundups)
            all_replaces_roundups.update(r_roundups)
    if all_replaces_roundups:
        valid_roundups = [
            r
            for r in valid_roundups
            if not _item_replaced_by_spec(r, set(), all_replaces_roundups)
        ]

    reg_order = {slug: i for i, slug in enumerate(ROUNDUP_PRODUCERS.keys())}

    raw_items = list(items)
    initial_floor_idx = _opening_eligible_floor_index(raw_items, seat_floor, now=now)

    # #12288 (Fable 2:41 PM PT): when splicing machinery groupings onto a base feed
    # that already has standing round-ups seated, never extract or shift any non-replaced
    # standing round-up. Replace each target card IN-PLACE at its exact seat, and place
    # non-replacing groupings strictly after the last standing round-up.
    use_in_place_splice = preserve_existing_roundups or (
        bool(valid_roundups)
        and all(_is_machinery_roundup_item(r) for r in valid_roundups)
        and any(_is_roundup_bundle_card(it) for it in raw_items)
    )
    if use_in_place_splice:
        return _splice_machinery_in_place(
            raw_items,
            valid_roundups,
            replaces_by_rid=replaces_by_rid,
            reg_order=reg_order,
            initial_floor_idx=initial_floor_idx,
            seat_floor=seat_floor,
            page_window=page_window,
            now=now,
            returning_reader=returning_reader,
            seen_card_keys=seen_card_keys,
            seen_futures_ids=seen_futures_ids,
            seen_event_ids=seen_event_ids,
            novelty_seat_cap=novelty_seat_cap,
        )

    preexisting_post_opening_roundups: list[Mapping[str, Any]] = []
    preexisting_target_by_id: dict[Any, int] = {}
    opening_takeover_seat_by_id: dict[Any, int] = {}
    replaced_reg_rank_by_id: dict[Any, int] = {}
    replaced_non_sib_ids: set[Any] = set()
    result: list[dict[str, Any]] = []
    changed = False
    for idx, it in enumerate(raw_items):
        matched_replacer_id: Any = None
        for r_id, (r_themes, r_roundups) in replaces_by_rid.items():
            if _item_replaced_by_spec(it, r_themes, r_roundups):
                matched_replacer_id = r_id
                break
        if matched_replacer_id is not None:
            # A replacing grouping inherits the replaced card's seat, registry turn,
            # and non-sibling queue bucket (Fable 9:57 AM & 10:45 AM PT on #12288).
            if idx < initial_floor_idx:
                prev_open = opening_takeover_seat_by_id.get(matched_replacer_id)
                if prev_open is None or idx < prev_open:
                    opening_takeover_seat_by_id[matched_replacer_id] = idx
            prev_seat = preexisting_target_by_id.get(matched_replacer_id)
            if prev_seat is None or idx < prev_seat:
                preexisting_target_by_id[matched_replacer_id] = idx
            old_slug = _roundup_item_slug(it)
            if old_slug in reg_order:
                prev_rank = replaced_reg_rank_by_id.get(matched_replacer_id)
                if prev_rank is None or reg_order[old_slug] < prev_rank:
                    replaced_reg_rank_by_id[matched_replacer_id] = reg_order[old_slug]
            if not _is_sibling_family_bundle(it):
                replaced_non_sib_ids.add(matched_replacer_id)
            changed = True
            continue
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

        def _reg_sort_key(pair: tuple[int, Mapping[str, Any]]) -> tuple[int, int]:
            idx_in_combined, item = pair
            item_id = item.get("data", {}).get("id")
            if item_id in replaced_reg_rank_by_id:
                return (replaced_reg_rank_by_id[item_id], idx_in_combined)
            slug = _roundup_item_slug(item)
            return (reg_order.get(slug, 10_000 + idx_in_combined), idx_in_combined)

        combined_raw = [*preexisting_post_opening_roundups, *valid_roundups]
        sorted_combined = [
            it for _, it in sorted(enumerate(combined_raw), key=_reg_sort_key)
        ]
    else:
        sorted_combined = list(valid_roundups)

    def _is_effective_sib(item: Mapping[str, Any]) -> bool:
        if item.get("data", {}).get("id") in replaced_non_sib_ids:
            return False
        return _is_sibling_family_bundle(item)

    non_sibs = [it for it in sorted_combined if not _is_effective_sib(it)]
    sibs = [it for it in sorted_combined if _is_effective_sib(it)]
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
    dissolved_post_opening_seat_by_id: dict[Any, int] = {}
    for r_item in accepted_roundups:
        r_id = r_item["data"].get("id")
        is_machinery = _is_machinery_roundup_item(r_item)
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
                if (
                    isinstance(existing, Mapping)
                    and existing.get("type") == "bundle"
                    and isinstance(existing.get("data"), Mapping)
                    and existing["data"].get("kind") != "roundup"
                    and isinstance(existing["data"].get("items"), list)
                ):
                    orig_children = existing["data"]["items"]
                    kept_children = [
                        ch
                        for ch in orig_children
                        if not (
                            isinstance(ch, Mapping)
                            and ch.get("type") == "futures"
                            and isinstance(ch.get("data"), Mapping)
                            and ch["data"].get("id") in covered_ids
                        )
                    ]
                    if len(kept_children) != len(orig_children):
                        # Ruling 275 (#13100): a card never loses a row to a card seated
                        # below it. Only full dissolution where a machinery grouping takes
                        # over the card's own seat (e.g. Fed & Rates -> Fed & U.S. Macro)
                        # or a post-opening bundle dissolves runs before seating; partial
                        # overlap is pruned after final seats are known, and ONLY against
                        # round-ups seated strictly above the bundle.
                        if len(kept_children) < 2 and (
                            is_machinery or idx >= initial_floor_idx
                        ):
                            changed = True
                            if (
                                earliest_post_opening_seat is None
                                and seat_floor <= idx < page_window
                            ):
                                earliest_post_opening_seat = idx
                            # Absorbing an older bundle's markets so it dissolves takes
                            # over that card's seat for machinery groupings only; standing
                            # round-ups seat identically to master (Fable 12:16 PM PT, #12288).
                            if is_machinery:
                                if idx < initial_floor_idx:
                                    prev_open = opening_takeover_seat_by_id.get(r_id)
                                    if prev_open is None or idx < prev_open:
                                        opening_takeover_seat_by_id[r_id] = idx
                                else:
                                    prev_post = dissolved_post_opening_seat_by_id.get(r_id)
                                    if prev_post is None or idx < prev_post:
                                        dissolved_post_opening_seat_by_id[r_id] = idx
                            continue
                filtered.append(existing)
            result = filtered
        earliest_seat_by_id[r_id] = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else preexisting_target_by_id.get(r_id)
        )

    def _hydrate_card_at_seat(r_item: Mapping[str, Any], target_idx: int) -> dict[str, Any]:
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
        return card

    # Seat any grouping that took over an opening-seat card right back at the
    # replaced card's seat first, so opening seats do not shift and `seat_opening`
    # honors the inherited opening seat.
    opening_takeovers = sorted(
        [
            r_item
            for r_item in accepted_roundups
            if r_item["data"].get("id") in opening_takeover_seat_by_id
        ],
        key=lambda r_item: opening_takeover_seat_by_id[r_item["data"].get("id")],
    )
    post_opening_roundups = [
        r_item
        for r_item in accepted_roundups
        if r_item["data"].get("id") not in opening_takeover_seat_by_id
    ]
    for r_item in opening_takeovers:
        r_id = r_item["data"].get("id")
        target_idx = min(max(0, opening_takeover_seat_by_id[r_id]), len(result))
        card = _hydrate_card_at_seat(r_item, target_idx)
        card["data"]["inherited_opening_seat"] = True
        result.insert(target_idx, card)
        changed = True

    inserted_count = 0
    max_inserted_idx = -1
    for r_item in post_opening_roundups:
        r_id = r_item["data"].get("id")
        is_sibling_card = _is_sibling_family_bundle(r_item)
        floor_idx = _opening_eligible_floor_index(result, seat_floor, now=now)
        default_seat = floor_idx + inserted_count
        if preexisting_post_opening_roundups and max_inserted_idx >= 0:
            default_seat = max(default_seat, max_inserted_idx + 2)
        earliest_post_opening_seat = earliest_seat_by_id.get(r_id)
        target_seat = (
            earliest_post_opening_seat
            if earliest_post_opening_seat is not None
            else default_seat
        )
        # Absorbing a card that sits later than the grouping's own seat never moves
        # the grouping later (Fable 12:16 PM PT, #12288).
        if r_id in dissolved_post_opening_seat_by_id:
            target_seat = min(target_seat, dissolved_post_opening_seat_by_id[r_id])
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

        card = _hydrate_card_at_seat(r_item, target_idx)

        result.insert(target_idx, card)
        if target_idx > max_inserted_idx:
            max_inserted_idx = target_idx
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

    # Ruling 275 (#13100): a card never loses a row to a card seated below it.
    # Prune overlapping rows from surviving theme bundles ONLY when an accepted
    # round-up covering those markets ended up seated strictly ABOVE the bundle.
    accepted_ids = {r["data"].get("id") for r in accepted_roundups}
    return _prune_bundles_below_roundups(result, accepted_ids)


def _prune_bundles_below_roundups(
    result: list[dict[str, Any]],
    accepted_ids: set[Any],
) -> list[dict[str, Any]]:
    """Prune overlapping rows from theme bundles seated strictly BELOW accepted round-ups (Ruling 275)."""
    if not accepted_ids:
        return result
    covered_above: set[int] = set()
    pruned_result: list[dict[str, Any]] = []
    for card in result:
        if (
            isinstance(card, Mapping)
            and card.get("type") == "bundle"
            and isinstance(card.get("data"), Mapping)
            and card["data"].get("id") in accepted_ids
        ):
            covered_above.update(_roundup_covered_market_ids(card))
            pruned_result.append(card)
            continue
        if (
            covered_above
            and isinstance(card, Mapping)
            and card.get("type") == "bundle"
            and isinstance(card.get("data"), Mapping)
            and card["data"].get("kind") != "roundup"
            and isinstance(card["data"].get("items"), list)
        ):
            orig_children = card["data"]["items"]
            kept_children = [
                ch
                for ch in orig_children
                if not (
                    isinstance(ch, Mapping)
                    and ch.get("type") == "futures"
                    and isinstance(ch.get("data"), Mapping)
                    and ch["data"].get("id") in covered_above
                )
            ]
            if len(kept_children) != len(orig_children):
                if len(kept_children) < 2:
                    continue
                updated_card = copy.deepcopy(dict(card))
                updated_card["data"]["items"] = kept_children
                updated_card["data"]["item_count"] = len(kept_children)
                if isinstance(updated_card["data"].get("member_ids"), list):
                    updated_card["data"]["member_ids"] = [
                        mid
                        for mid in updated_card["data"]["member_ids"]
                        if mid not in covered_above
                    ]
                pruned_result.append(updated_card)
                continue
        pruned_result.append(card)

    return pruned_result


def _is_machinery_producer_slug(slug: Any) -> bool:
    return isinstance(slug, str) and slug.strip().lower().startswith("machinery-")


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
    include_machinery: bool = False,
    machinery_only: bool = False,
    include_preview: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate registered round-up producers and place their cards on Discover.

    Under Ruling 252: A (#12288), ``machinery-*`` candidate groupings are only
    included when ``include_machinery=True`` (sent by website and iOS 1.0.7+
    via ``machinery=1``), so older App Store versions (1.0.6) never receive
    machinery cards on the Discover feed.

    Under #13097 (Fable 2:03 PM PT), groupings with ``stage="preview"`` are
    omitted unless ``include_preview=True`` (``machinery=preview``), so new
    sets never reach public Discover before Fable inspects them with live numbers.
    """
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
    ensure_optional_roundup_candidates()
    started = time.perf_counter()
    if machinery_only:
        producers = [
            p for p in ROUNDUP_PRODUCERS.values() if _is_machinery_producer_slug(p.slug)
        ]
    elif include_machinery:
        producers = list(ROUNDUP_PRODUCERS.values())
    else:
        producers = [
            p for p in ROUNDUP_PRODUCERS.values() if not _is_machinery_producer_slug(p.slug)
        ]
    if not include_preview:
        producers = [
            p for p in producers if getattr(p, "stage", "public") != "preview"
        ]
    if not producers:
        return items
    produced: list[dict[str, Any]] = []
    machinery_producers = [
        p
        for p in producers
        if _is_machinery_producer_slug(p.slug) and (p.enabled is None or p.enabled())
    ]
    machinery_incomplete = False
    for idx, producer in enumerate(producers):
        elapsed = time.perf_counter() - started
        remaining = stage_budget - elapsed
        if remaining <= 0:
            if any(
                _is_machinery_producer_slug(rem.slug)
                and (rem.enabled is None or rem.enabled())
                for rem in producers[idx:]
            ):
                machinery_incomplete = True
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
        is_mach_prod = _is_machinery_producer_slug(producer.slug) and (
            producer.enabled is None or producer.enabled()
        )
        try:
            eval_coro = (
                evaluate_roundup_producer(producer, db, now=now, allow_stale=True)
                if _is_machinery_producer_slug(producer.slug)
                else evaluate_roundup_producer(producer, db, now=now)
            )
            feed_item, container_payload = await asyncio.wait_for(
                eval_coro,
                timeout=per_timeout,
            )
        except asyncio.TimeoutError:
            if is_mach_prod:
                machinery_incomplete = True
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug("roundup_containers: rollback failed after timeout")
            if (
                per_timeout >= ROUNDUP_PRODUCER_TIMEOUT_SECONDS
                and not _is_machinery_producer_slug(producer.slug)
            ):
                await _cache_roundup_timeout_refusal(producer, db)
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards",
                producer.slug,
                exc_info=True,
            )
            continue
        except Exception:
            if is_mach_prod:
                machinery_incomplete = True
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug("roundup_containers: rollback failed after error")
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards",
                producer.slug,
                exc_info=True,
            )
            continue
        if feed_item is not None and container_payload is not None:
            produced.append(feed_item)

    # Goal Step 7 (#12288): five or none during cold-restart warm-up.
    # If any registered machinery grouping timed out, errored, or was skipped
    # by stage budget exhaustion, drop all partial machinery cards from this
    # response (standing round-ups stay untouched) rather than serving 2/5 or 3/5.
    if machinery_incomplete and machinery_producers:
        ready_mach = sum(1 for it in produced if _is_machinery_roundup_item(it))
        if ready_mach > 0:
            produced = [it for it in produced if not _is_machinery_roundup_item(it)]
            logger.warning(
                "Discover machinery groupings incomplete (%d/%d ready); serving none until all ready",
                ready_mach,
                len(machinery_producers),
            )

    if not produced:
        return items
    # Ruling 188 (#11937): a market nobody is trading is not featured, and a
    # round-up is rated by its stalest member, so those members leave the card.
    # For `machinery_only=True` splices, `_prewarm_machinery_roundups` already
    # runs this screen once on the worker before saving each grouping to Redis,
    # so reader requests do not pay a ~580 ms PostgreSQL query on every hit.
    if not machinery_only:
        try:
            from app.utils.not_trading import drop_not_trading_roundup_members

            produced = await drop_not_trading_roundup_members(
                db, produced, now or datetime.now(timezone.utc), _roundup_covered_market_ids
            )
        except Exception:  # noqa: BLE001 — one failed read must not empty the page (gotcha #42)
            logger.warning("Discover round-up not-trading check failed; keeping the cards", exc_info=True)
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
        preserve_existing_roundups=machinery_only,
    )


def render_machinery_prewarm_bundle(
    *,
    mach_base: dict[str, Any],
    produced: list[dict[str, Any]],
    oldest_live_built_at: Optional[float],
    now_ts: float,
) -> Optional[dict[str, Any]]:
    """Pure-Python render of `machinery=1` page + `:machinery` page base + edition manifest (#12288).

    Lives in `utils/roundup_containers.py` so `precompute_category_pages.py` stays
    agnostic to opening seating (`#5105`) and `routes/feed.py` keeps a single
    `_publish_feed_item` call site inside `get_feed` (`#6444`).
    """
    from app.routes.feed import (
        DISCOVER_COMPOSITION_WINDOW,
        _apply_opening_envelope,
        _publish_feed_item,
    )
    from app.utils.discover_opening_edition import compose_opening_edition
    from app.utils.feed_cache import (
        FEED_EDITION_FIELD,
        FEED_PAGE_BASE_BUILT_AT_FIELD,
        build_feed_cache_metadata,
        dumps_feed_cache,
        feed_edition_token,
        feed_machinery_page_base_key,
        feed_response_cache_key,
        feed_response_cache_ttls,
        payload_contains_live_event,
        render_feed_page_from_base,
    )
    from app.utils.feed_editions import (
        EDITION_LEASE_SECONDS,
        build_edition_manifest,
        edition_manifest_cache_key,
    )

    base_body = mach_base["page_base_body"]
    base_items = list(base_body.get("items") or [])
    if not base_items:
        return None

    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    spliced_items = insert_roundup_feed_items(
        copy.deepcopy(base_items),
        produced,
        page_window=DISCOVER_COMPOSITION_WINDOW,
        now=now_dt,
        preserve_existing_roundups=True,
    )
    for item in spliced_items:
        _publish_feed_item(item)

    base_age_origin = float(mach_base.get("age_origin") or now_ts)
    mach_age_origin = (
        min(base_age_origin, oldest_live_built_at)
        if oldest_live_built_at is not None
        else base_age_origin
    )
    use_opening = bool(mach_base.get("opening_seating"))
    edition_policy = str(mach_base.get("edition_policy") or "default")
    limit = int(mach_base.get("limit") or 20)
    offset = int(mach_base.get("offset") or 0)

    mach_base_body = dict(base_body)
    mach_base_body["items"] = spliced_items
    mach_base_body["total"] = len(spliced_items)
    mach_base_body[FEED_PAGE_BASE_BUILT_AT_FIELD] = mach_age_origin

    manifest_key = None
    manifest_obj = None
    if use_opening:
        opening = compose_opening_edition(
            spliced_items,
            None,
            requested_token=None,
            requested_policy=edition_policy,
            now=now_dt,
        )
        if not opening.usable:
            return None
        for _per_req in (FEED_EDITION_FIELD, "continuation_start"):
            mach_base_body.pop(_per_req, None)
        if opening.token is not None:
            mach_base_body[FEED_EDITION_FIELD] = opening.token
            if opening.continuation_start is not None:
                mach_base_body["continuation_start"] = opening.continuation_start
            if opening.manifest is not None:
                manifest_key = edition_manifest_cache_key(
                    token=opening.token, policy=edition_policy
                )
                manifest_obj = opening.manifest
        page_payload = render_feed_page_from_base(
            {
                **mach_base_body,
                "items": opening.items,
                "total": len(opening.items),
            },
            limit=limit,
            offset=offset,
        )
        if page_payload is not None:
            _apply_opening_envelope(page_payload, opening, requested=False)
    else:
        ed_token = feed_edition_token(spliced_items)
        if ed_token is not None:
            mach_base_body[FEED_EDITION_FIELD] = ed_token
            manifest_obj = build_edition_manifest(
                spliced_items,
                token=ed_token,
                policy=edition_policy,
                built_at=now_ts,
            )
            if manifest_obj is not None:
                manifest_key = edition_manifest_cache_key(
                    token=ed_token, policy=edition_policy
                )
        page_payload = render_feed_page_from_base(
            mach_base_body, limit=limit, offset=offset
        )

    if page_payload is None:
        return None

    mach_live = payload_contains_live_event(mach_base_body)
    m_ttl, m_stale_ttl = feed_response_cache_ttls(
        my_teams_only=False, identified=False, live=mach_live
    )
    page_payload["cache"] = build_feed_cache_metadata(
        "miss",
        ttl_seconds=m_ttl,
        stale_ttl_seconds=m_stale_ttl,
        live=mach_live,
        built_at=mach_age_origin,
    )

    cache_shape = dict(mach_base["cache_shape"])
    cache_shape["machinery"] = True
    mach_cache_key = feed_response_cache_key(
        user_id=None, session_id=None, **cache_shape
    )
    mach_pb_key = feed_machinery_page_base_key(str(mach_base["page_base_key"]))

    return {
        "live": mach_live,
        "ttl": m_ttl,
        "stale_ttl": m_stale_ttl,
        "cache_key": mach_cache_key,
        "page_base_key": mach_pb_key,
        "page_json": dumps_feed_cache(page_payload),
        "page_base_json": dumps_feed_cache(mach_base_body),
        "manifest_key": manifest_key,
        "manifest_json": dumps_feed_cache(manifest_obj) if manifest_obj is not None else None,
        "manifest_ttl": EDITION_LEASE_SECONDS,
    }


def _splice_machinery_in_place(
    raw_items: list[dict[str, Any]],
    valid_roundups: Sequence[Mapping[str, Any]],
    *,
    replaces_by_rid: Mapping[Any, tuple[set[str], set[str]]],
    reg_order: Mapping[str, int],
    initial_floor_idx: int,
    seat_floor: int,
    page_window: int,
    now: Optional[datetime],
    returning_reader: bool,
    seen_card_keys: Optional[Sequence[str] | set[str]],
    seen_futures_ids: Optional[Sequence[int] | set[int]],
    seen_event_ids: Optional[Sequence[int] | set[int]],
    novelty_seat_cap: int,
) -> list[dict[str, Any]]:
    """Splice machinery groupings onto a seated Discover deck without moving standing round-ups.

    * Every non-replaced standing round-up keeps its exact index from ``raw_items``.
    * Each replacing machinery grouping overwrites its replaced card (standing round-up,
      dissolved theme bundle, or first covered standalone market) IN-PLACE at that exact seat.
    * Non-replacing machinery groupings (e.g. NBA Night, NFL Week) seat strictly after the
      last standing round-up with non-adjacent spacing so zero standing round-ups shift.
    """
    result: list[dict[str, Any]] = list(raw_items)
    existing_ids = {
        it.get("data", {}).get("id")
        for it in result
        if isinstance(it, Mapping)
        and it.get("type") == "bundle"
        and isinstance(it.get("data"), Mapping)
    }

    def _reg_key(pair: tuple[int, Mapping[str, Any]]) -> tuple[int, int]:
        idx_in, item = pair
        slug = _roundup_item_slug(item)
        return (reg_order.get(slug, 10_000 + idx_in), idx_in)

    ordered_roundups: list[Mapping[str, Any]] = []
    seen_rids: set[Any] = set()
    for _, r_item in sorted(enumerate(valid_roundups), key=_reg_key):
        r_id = r_item["data"].get("id")
        if r_id in existing_ids or r_id in seen_rids:
            continue
        seen_rids.add(r_id)
        ordered_roundups.append(r_item)

    if not ordered_roundups:
        return raw_items

    def _hydrate_at(r_item: Mapping[str, Any], target_idx: int) -> dict[str, Any]:
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
        return card

    placed_rids: set[Any] = set()
    remove_indices: set[int] = set()
    changed = False

    # Pass 1: Explicit `replaces` / `replaces_themes` -> exact in-place replacement.
    by_rid = {r["data"].get("id"): r for r in ordered_roundups}
    for idx, existing in enumerate(result):
        matched_rid: Any = None
        for r_id, (r_themes, r_roundups) in replaces_by_rid.items():
            if r_id in by_rid and _item_replaced_by_spec(existing, r_themes, r_roundups):
                matched_rid = r_id
                break
        if matched_rid is None:
            continue
        changed = True
        if matched_rid not in placed_rids:
            card = _hydrate_at(by_rid[matched_rid], idx)
            if idx < initial_floor_idx:
                card["data"]["inherited_opening_seat"] = True
            result[idx] = card
            placed_rids.add(matched_rid)
        else:
            remove_indices.add(idx)

    # Pass 2: Covered standalone futures and theme bundles -> in-place takeover on dissolution
    # or first covered standalone card; prune extra duplicates only.
    for r_item in ordered_roundups:
        r_id = r_item["data"].get("id")
        covered_ids = _roundup_covered_market_ids(r_item)
        if not covered_ids:
            continue
        for idx, existing in enumerate(result):
            if idx in remove_indices or not isinstance(existing, Mapping):
                continue
            if _is_roundup_bundle_card(existing):
                continue
            if (
                existing.get("type") == "futures"
                and isinstance(existing.get("data"), Mapping)
                and existing["data"].get("id") in covered_ids
            ):
                changed = True
                if r_id not in placed_rids:
                    card = _hydrate_at(r_item, idx)
                    if idx < initial_floor_idx:
                        card["data"]["inherited_opening_seat"] = True
                    result[idx] = card
                    placed_rids.add(r_id)
                else:
                    remove_indices.add(idx)
                continue
            if (
                existing.get("type") == "bundle"
                and isinstance(existing.get("data"), Mapping)
                and existing["data"].get("kind") != "roundup"
                and isinstance(existing["data"].get("items"), list)
            ):
                orig_children = existing["data"]["items"]
                kept_children = [
                    ch
                    for ch in orig_children
                    if not (
                        isinstance(ch, Mapping)
                        and ch.get("type") == "futures"
                        and isinstance(ch.get("data"), Mapping)
                        and ch["data"].get("id") in covered_ids
                    )
                ]
                if len(kept_children) != len(orig_children) and len(kept_children) < 2:
                    # Ruling 275 (#13100): only full dissolution runs before seating;
                    # partial overlap is pruned after final seats are settled via
                    # `_prune_bundles_below_roundups` so a card never loses a row to
                    # a machinery grouping seated below it.
                    changed = True
                    if r_id not in placed_rids:
                        card = _hydrate_at(r_item, idx)
                        if idx < initial_floor_idx:
                            card["data"]["inherited_opening_seat"] = True
                        result[idx] = card
                        placed_rids.add(r_id)
                    else:
                        remove_indices.add(idx)

    if remove_indices:
        for idx in sorted(remove_indices, reverse=True):
            result.pop(idx)

    # Pass 3: Non-replacing machinery groupings seat strictly after the last standing
    # round-up with non-adjacent spacing so zero standing round-ups shift.
    unplaced = [r for r in ordered_roundups if r["data"].get("id") not in placed_rids]
    if unplaced:
        floor_idx = _opening_eligible_floor_index(result, seat_floor, now=now)
        last_standing_idx = max(
            (i for i, it in enumerate(result) if _is_roundup_bundle_card(it)),
            default=-1,
        )
        next_desired = max(floor_idx, last_standing_idx + 2)
        for r_item in unplaced:
            desired_idx = min(next_desired, len(result))
            non_adj = _find_non_adjacent_roundup_seat(
                result,
                desired_idx,
                floor_idx=desired_idx,
                candidate_item=r_item,
                page_window=page_window,
            )
            target_idx = non_adj if non_adj is not None else len(result)
            card = _hydrate_at(r_item, target_idx)
            result.insert(target_idx, card)
            next_desired = target_idx + 2
            changed = True

    if not changed:
        return raw_items

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

    accepted_ids = {r["data"].get("id") for r in ordered_roundups}
    return _prune_bundles_below_roundups(result, accepted_ids)


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
    raw_stage = data.get("stage") if "stage" in data else None
    stage_clean = str(raw_stage or "public").strip().lower()
    if stage_clean not in CLOSED_GROUPING_STAGES:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} has invalid 'stage' {raw_stage!r}; "
            f"allowed: {sorted(CLOSED_GROUPING_STAGES)}"
        )
    raw_look = data.get("look") if "look" in data else rule_raw.get("look")
    look_clean = str(raw_look or "bars").strip().lower()
    if look_clean not in CLOSED_GROUPING_LOOKS:
        raise ValueError(
            f"Round-up definition {slug!r}{loc} has invalid 'look' {raw_look!r}; "
            f"allowed: {sorted(CLOSED_GROUPING_LOOKS)}"
        )
    out["stage"] = stage_clean
    out["look"] = look_clean
    rule_copy = dict(rule_raw)
    rule_copy["relations"] = list(relations_list)
    rule_copy["level"] = level_clean
    rule_copy["look"] = look_clean
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
    "container_machinery": (
        "app.utils.container_machinery",
        "build_container_machinery_producer",
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
