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
from collections import deque
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
    "ROUNDUP_BG_REFRESH_TIMEOUT_S",
    "ROUNDUP_CACHE_TTL_S",
    "ROUNDUP_NOVELTY_SEAT_CAP",
    "ROUNDUP_PAGE_SWR_MAX_AGE_S",
    "ROUNDUP_PREWARM_STAGE_BUDGET_SECONDS",
    "ROUNDUP_PREVIEW_PRODUCER_TIMEOUT_SECONDS",
    "ROUNDUP_PREVIEW_STAGE_BUDGET_SECONDS",
    "ROUNDUP_PRODUCERS",
    "ROUNDUP_PRODUCER_TIMEOUT_SECONDS",
    "ROUNDUP_READ_BUDGET_SECONDS",
    "ROUNDUP_READ_FAILURE_WINDOW_S",
    "ROUNDUP_SEAT_FLOOR",
    "ROUNDUP_SETTLED_RETIRED_TTL_S",
    "ROUNDUP_STANDING_LIVE_STALE_TTL_S",
    "ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S",
    "STANDING_RETIRED_SLUGS_KEY",
    "STANDING_RETIRED_SLUGS_TTL_S",
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
    "get_roundup_read_failure_breakdown_10m",
    "get_roundup_read_failure_stats_10m",
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
    "store_roundup_settled_retired_sync",
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
#: Best-effort budget for cold `"stage": "preview"` groupings on `machinery=preview`
#: requests; kept strictly outside the public stage budget and public all-or-nothing gate.
ROUNDUP_PREVIEW_PRODUCER_TIMEOUT_SECONDS = 3.5
ROUNDUP_PREVIEW_STAGE_BUDGET_SECONDS = 12.0
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
_roundup_bg_refresh_tasks: dict[tuple[str, Any], asyncio.Task[Any]] = {}
_roundup_inflight_builds: dict[
    tuple[str, Any],
    asyncio.Future[
        tuple[
            Optional[dict[str, Any]],
            Optional[dict[str, Any]],
            Optional[dict[str, Any]],
        ]
    ],
] = {}


class _RoundupBuildAbandoned(Exception):
    """Internal signal when a singleflight roundup build is cancelled/abandoned."""


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
    unpriced_outcomes: tuple[dict[str, Any], ...] = ()
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
        unpriced_outcomes: Sequence[Mapping[str, Any]] = (),
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
            "unpriced_outcomes",
            tuple(
                copy.deepcopy(dict(u))
                for u in (unpriced_outcomes or ())
                if isinstance(u, Mapping)
            ),
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
        object.__setattr__(self, "kicker", str(kicker) if kicker is not None else "Round-up")
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
        "name": producer.name or effective_title,
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
    unpriced_outcomes = list(getattr(members, "unpriced_outcomes", None) or ())
    if unpriced_outcomes:
        roundup_contract["unpriced_outcomes"] = copy.deepcopy(unpriced_outcomes)
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


ROUNDUP_READ_FAILURE_WINDOW_S = 600.0
#: Rolling 10-minute ledger of Discover round-up read outcomes when refresh
#: times out, errors, or hits stage budget on this process:
#: ``(ts, slug, outcome_kind, reason)`` where ``outcome_kind`` is one of
#: ``"kept_last_good"``, ``"dropped_no_copy"``, or ``"had_nothing_to_show"``.
#: Bounded so memory is O(1).
_roundup_read_failures: deque[tuple[float, str, str, str]] = deque(maxlen=5000)
#: Local companion marker for unexpired ``(ts, None, None)`` entries in
#: ``_roundup_local_cache`` that came from a clean "nothing to show" refusal
#: (never a timeout/error refusal), keyed identically to ``_roundup_local_cache``.
_roundup_nothing_to_show_local: dict[tuple[str, Any], tuple[float, Optional[str]]] = {}
#: Local companion marker for fixed-member settled round-ups retired from Discover (#13718).
_roundup_settled_retired_local: dict[tuple[str, Any], float] = {}


def _prune_roundup_read_failures(now_ts: float) -> None:
    cutoff = float(now_ts) - ROUNDUP_READ_FAILURE_WINDOW_S
    while _roundup_read_failures and _roundup_read_failures[0][0] < cutoff:
        _roundup_read_failures.popleft()


def _record_roundup_read_failure(
    slug: str,
    *,
    kept_last_good: bool,
    reason: str,
    had_nothing_to_show: bool = False,
    now: Optional[float | datetime] = None,
) -> dict[str, int]:
    """Record a Discover round-up read fallback/loss and return rolling 10-minute counts."""
    ts, _ = _normalize_roundup_now(now)
    _prune_roundup_read_failures(ts)
    if kept_last_good:
        outcome_kind = "kept_last_good"
    elif had_nothing_to_show:
        outcome_kind = "had_nothing_to_show"
    else:
        outcome_kind = "dropped_no_copy"
    _roundup_read_failures.append((ts, str(slug), outcome_kind, str(reason)))
    return get_roundup_read_failure_stats_10m(now=ts)


def get_roundup_read_failure_stats_10m(
    now: Optional[float | datetime] = None,
) -> dict[str, int]:
    """Return Discover round-up read counts over the last 10 minutes (#13146).

    Splits round-ups that cleanly had nothing to show from ones where a reader
    actually lost a card, so ``dropped_no_copy > 0`` can be used as an alarm:

    - ``failed``: ``kept_last_good + dropped_no_copy`` (reads where a card was
      at risk or lost due to timeout, error, or stage budget).
    - ``kept_last_good``: failed reads where a valid last good copy under its
      keep-time was kept in the list instead of dropping the card.
    - ``dropped_no_copy``: failed reads where a reader actually lost a card
      (no last good copy under keep-time and not known to have nothing to show).
    - ``had_nothing_to_show``: timed-out/errored/budget-exhausted reads whose
      unexpired prior state cleanly had nothing to show (never inflates
      ``dropped_no_copy`` or ``failed``).
    """
    ts, _ = _normalize_roundup_now(now)
    _prune_roundup_read_failures(ts)
    kept = 0
    dropped = 0
    nothing_to_show = 0
    for _ev_ts, _slug, outcome_kind, _reason in _roundup_read_failures:
        if outcome_kind == "kept_last_good":
            kept += 1
        elif outcome_kind == "had_nothing_to_show":
            nothing_to_show += 1
        else:
            dropped += 1
    return {
        "window_seconds": int(ROUNDUP_READ_FAILURE_WINDOW_S),
        "failed": kept + dropped,
        "kept_last_good": kept,
        "dropped_no_copy": dropped,
        "had_nothing_to_show": nothing_to_show,
    }


def get_roundup_read_failure_breakdown_10m(
    now: Optional[float | datetime] = None,
    *,
    limit: int = 10,
) -> dict[str, dict[str, Any]]:
    """Return rolling 10-minute Discover round-up failure counts keyed by slug (#13718)."""
    ts, _ = _normalize_roundup_now(now)
    _prune_roundup_read_failures(ts)
    counts: dict[str, dict[str, Any]] = {}
    for _ev_ts, ev_slug, outcome_kind, reason in _roundup_read_failures:
        entry = counts.setdefault(
            ev_slug,
            {
                "failed": 0,
                "kept_last_good": 0,
                "dropped_no_copy": 0,
                "had_nothing_to_show": 0,
                "last_reason": None,
            },
        )
        if outcome_kind == "kept_last_good":
            entry["kept_last_good"] += 1
            entry["failed"] += 1
        elif outcome_kind == "had_nothing_to_show":
            entry["had_nothing_to_show"] += 1
        else:
            entry["dropped_no_copy"] += 1
            entry["failed"] += 1
        entry["last_reason"] = reason
    failing = [
        (slug, data)
        for slug, data in counts.items()
        if data["failed"] > 0 or data["had_nothing_to_show"] > 0
    ]
    failing.sort(
        key=lambda item: (
            -int(item[1]["failed"]),
            -int(item[1]["dropped_no_copy"]),
            -int(item[1]["had_nothing_to_show"]),
            item[0],
        )
    )
    cap = max(1, int(limit))
    return dict(failing[:cap])


def _reset_roundup_swr_state_for_tests() -> None:
    """Clear in-flight background refreshes and singleflight futures between tests (#13475)."""
    for task in list(_roundup_bg_refresh_tasks.values()):
        try:
            if not task.done():
                task.cancel()
        except Exception:  # noqa: BLE001
            pass
    _roundup_bg_refresh_tasks.clear()
    _roundup_inflight_builds.clear()


def reset_roundup_cache_for_tests() -> None:
    _roundup_local_cache.clear()
    _roundup_nothing_to_show_local.clear()
    _roundup_settled_retired_local.clear()
    _roundup_read_failures.clear()
    _reset_roundup_swr_state_for_tests()


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
#: Hard Redis retention (keep-time) for round-up and machinery snapshots so
#: Discover feed builds (`ROUNDUP_PRODUCER_TIMEOUT_SECONDS = 0.5`) keep the
#: last good copy across restarts, outages, and overnight quiet spells instead
#: of dropping cards (#11259, #12288, #13146). Live-slate keep-time stays 5m.
ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S = 21600.0
ROUNDUP_MACHINERY_LIVE_STALE_TTL_S = 300.0
ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S = 21600.0
ROUNDUP_STANDING_LIVE_STALE_TTL_S = 300.0
#: #12529: Non-live standing round-ups warmed by Celery Beat hold a 300s fresh
#: window (above the 120s host cadence) so cold Discover builds read Redis MGET
#: with zero Postgres wait, while live standing round-ups keep the 60s ceiling.
ROUNDUP_STANDING_PREWARM_FRESH_TTL_S = 300.0
#: #13475: Set-page SWR bound for sets with no live game (30 minutes, matching 170-A).
#: Copies aged < 1800s serve immediately and trigger one background rebuild.
ROUNDUP_PAGE_SWR_MAX_AGE_S = 1800.0
ROUNDUP_BG_REFRESH_TIMEOUT_S = 45.0
#: Per-producer timeout for a genuinely cold public machinery grouping (no
#: Redis copy, e.g. a live slate whose 5m TTL expired during an outage).
ROUNDUP_MACHINERY_COLD_TIMEOUT_SECONDS = 1.5
#: Redis hash tracking `machinery-*` slugs that currently hold a live game (or one
#: starting within `MACHINERY_IMMINENT_START_WINDOW_S`), read by the 30s realtime
#: republisher (`_prewarm_live_feed_shapes`) so live slates never expire between
#: 120s host beats. TTL outlives the 120s host beat by 2.5x.
MACHINERY_LIVE_SLUGS_KEY = "bainluck:roundup:machinery:live_slugs"
MACHINERY_LIVE_SLUGS_TTL_S = 300
#: Companion 30s-rail live-slug + armed-slug hashes for standing round-ups (#12529).
STANDING_LIVE_SLUGS_KEY = "bainluck:roundup_standing:live_slugs"
STANDING_LIVE_SLUGS_TTL_S = 300
STANDING_WARM_SLUGS_KEY = "bainluck:roundup_standing:warm_slugs"
STANDING_WARM_SLUGS_TTL_S = 86_400
STANDING_RETIRED_SLUGS_KEY = "bainluck:roundup:retired_settled_slugs:v1"
STANDING_RETIRED_SLUGS_TTL_S = 86_400
ROUNDUP_SETTLED_RETIRED_TTL_S = 86_400.0
MACHINERY_IMMINENT_START_WINDOW_S = 180.0
# True terminal/resulted statuses (#13718 + Fable ask 2): ONLY these qualify a
# fixed-member standing set for the 24-hour Discover retirement skip. A market
# with status == "closed" and no result yet is temporarily halted/non-trading
# (see `_roundup_members_settlement_state` returning `'all_closed'`) and must
# keep the ordinary short cache TTL so it recovers automatically if trading resumes.
_RESULT_MEMBER_STATUSES = frozenset(
    {"settled", "completed", "final", "finished", "graded", "resolved"}
)
_ROLLING_DISCOVER_PRODUCER_KINDS = frozenset(
    {
        "window_events_closest",
        "subject_sequence",
        "week_events",
        "same_deadline_board",
        "field_leaders",
        "register_closest",
        "field_band",
    }
)
_TERMINAL_EVENT_STATUSES = frozenset(
    {"final", "completed", "closed", "cancelled", "canceled", "postponed"}
)


def _roundup_members_settlement_state(
    container_payload: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """Return ``'all_settled'``, ``'all_closed'``, or ``None`` for a built container (#13718).

    - ``'all_settled'``: >=1 members and every member carries a settled/resulted
      status (or ``baseline_status == 'settled_preserved'``).
    - ``'all_closed'``: >=1 members and every member is non-trading, with at least
      one ``status == 'closed'`` lacking a result yet (eligible to hide from
      Discover briefly, NEVER for the 24-hour standing retirement skip).
    - ``None``: empty container or at least one active/open/scheduled member.
    """
    if not isinstance(container_payload, Mapping):
        return None
    members: list[Mapping[str, Any]] = []
    for sec in container_payload.get("sections") or ():
        if isinstance(sec, Mapping):
            for m in sec.get("members") or ():
                if isinstance(m, Mapping):
                    members.append(m)
    if not members and isinstance(container_payload.get("members"), Sequence):
        for m in container_payload.get("members") or ():
            if isinstance(m, Mapping):
                members.append(m)
    if not members:
        return None
    saw_closed_without_result = False
    for m in members:
        card = m.get("card")
        if not isinstance(card, Mapping):
            return None
        st = str(card.get("status") or "").strip().lower()
        has_result = (
            st in _RESULT_MEMBER_STATUSES
            or card.get("baseline_status") == "settled_preserved"
        )
        if has_result:
            continue
        if st == "closed":
            saw_closed_without_result = True
            continue
        return None
    return "all_closed" if saw_closed_without_result else "all_settled"


def _roundup_all_members_settled(
    container_payload: Optional[Mapping[str, Any]],
) -> bool:
    """True when a built container has >=1 members and every member has a result (#13718)."""
    return _roundup_members_settlement_state(container_payload) == "all_settled"


def _producer_has_fixed_members(producer: RoundupProducer) -> bool:
    """True for hand-scoped / series-hub sets whose member IDs cannot become newly active (#13718)."""
    rule = producer.rule if isinstance(producer.rule, Mapping) else {}
    kind = str(rule.get("producer") or "").strip().lower()
    if kind == "series_hub":
        return True
    if kind in _ROLLING_DISCOVER_PRODUCER_KINDS:
        return False
    for key in (
        "event_ids",
        "series_market_ids",
        "market_ids",
        "candidates",
        "winner_market_ids",
        "nomination_market_ids",
    ):
        val = rule.get(key)
        if isinstance(val, Sequence) and not isinstance(val, (str, bytes)) and len(val) > 0:
            return True
    return False


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
            if isinstance(raw_ct, datetime):
                ct_dt = (
                    raw_ct
                    if raw_ct.tzinfo is not None
                    else raw_ct.replace(tzinfo=timezone.utc)
                )
                ct_ts = ct_dt.timestamp()
            elif isinstance(raw_ct, str) and raw_ct.strip():
                try:
                    ct_dt = datetime.fromisoformat(raw_ct.replace("Z", "+00:00"))
                    if ct_dt.tzinfo is None:
                        ct_dt = ct_dt.replace(tzinfo=timezone.utc)
                    ct_ts = ct_dt.timestamp()
                except ValueError:
                    continue
            else:
                continue
            if (ref_ts - 21600.0) <= ct_ts <= (ref_ts + MACHINERY_IMMINENT_START_WINDOW_S):
                return True
    return False


def _roundup_effective_keep_seconds(
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
    *,
    now_ts: float,
    stored_stale_ttl: Optional[float] = None,
) -> float:
    """Judge a cached copy's keep-time by the clock at serve time (#13146).

    If any non-final game in the cached copy has already started or starts
    within ``MACHINERY_IMMINENT_START_WINDOW_S`` (3 min), cap keep-time to the
    5-minute live window even when the copy was built before tip-off.
    """
    live_cap = (
        ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
        if _is_machinery_producer_slug(slug)
        else ROUNDUP_STANDING_LIVE_STALE_TTL_S
    )
    if _roundup_payload_needs_live_rail(container_payload, now_ts=now_ts):
        return live_cap
    if isinstance(stored_stale_ttl, (int, float)) and stored_stale_ttl > 0:
        return float(stored_stale_ttl)
    return _roundup_cache_stale_ttl_seconds(slug, container_payload)


def _record_roundup_live_origin(
    built_at: float,
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
) -> None:
    """Feed any cached live round-up or grouping's origin into the LAT-P230 age sink."""
    if not _roundup_payload_has_live_event(container_payload):
        return
    try:
        from app.utils.principal_independent_cache import _age_sink_var

        sink = _age_sink_var.get()
        if sink is not None:
            sink.append(float(built_at))
    except Exception:  # noqa: BLE001 — telemetry sink is best-effort
        logger.debug("roundup_containers: live origin sink update skipped for %s", slug)


def _record_machinery_live_origin(
    built_at: float,
    slug: str,
    container_payload: Optional[Mapping[str, Any]],
) -> None:
    """Feed a cached live machinery grouping's origin into the LAT-P230 age sink."""
    if not _is_machinery_producer_slug(slug):
        return
    _record_roundup_live_origin(built_at, slug, container_payload)


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
    """Hard Redis retention TTL (keep-time / stale-while-revalidate window) for a roundup entry.

    Applies to both standing round-ups and machinery groupings when a good copy
    exists (``container_payload is not None``) so a timed-out refresh can keep
    the last good copy instead of dropping the card (#13146). Negative refusals
    (``container_payload is None``) stay on the short 60s TTL.
    """
    if container_payload is not None:
        is_live = _roundup_payload_has_live_event(container_payload)
        if _is_machinery_producer_slug(slug):
            return (
                ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
                if is_live
                else ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
            )
        return (
            ROUNDUP_STANDING_LIVE_STALE_TTL_S
            if is_live
            else ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S
        )
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
    clean_empty_reason: Optional[str] = None,
    nothing_to_show: bool = False,
    nothing_to_show_reason: Optional[str] = None,
    settled_retired: bool = False,
    long_skip: bool = False,
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
        if clean_empty_reason:
            payload["clean_empty_reason"] = str(clean_empty_reason)
    if nothing_to_show:
        payload["nothing_to_show"] = True
        if nothing_to_show_reason:
            payload["nothing_to_show_reason"] = str(nothing_to_show_reason)
    if settled_retired:
        payload["settled_retired"] = True
        if long_skip:
            payload["long_skip"] = True
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
    *,
    prewarm_fresh_ttl_s: Optional[float] = None,
) -> bool:
    """Publish a roundup cache entry + live-slug registration via sync Redis.

    Used by Celery prewarm workers only (where `asyncio.run()` closes the event
    loop between tasks and breaks process-global async Redis pools). Never
    called from the web event loop (#969, #12288).
    """
    if rc is None or not hasattr(rc, "set"):
        return False
    prod = ROUNDUP_PRODUCERS.get(slug)
    rule_cfg = prod.rule if (prod is not None and isinstance(prod.rule, Mapping)) else {}
    if rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair":
        return False
    ttl_s = _roundup_cache_ttl_seconds(slug, container_payload)
    stale_ttl_s = _roundup_cache_stale_ttl_seconds(slug, container_payload)
    if (
        prewarm_fresh_ttl_s is not None
        and not _is_machinery_producer_slug(slug)
        and container_payload is not None
        and not _roundup_payload_needs_live_rail(container_payload, now_ts=ts)
    ):
        ttl_s = min(float(stale_ttl_s), max(float(ttl_s), float(prewarm_fresh_ttl_s)))
    try:
        encoded = _encode_roundup_cache_entry(
            ts=ts,
            ttl_s=ttl_s,
            stale_ttl_s=stale_ttl_s,
            feed_item=feed_item,
            container_payload=container_payload,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(stale_ttl_s))
        if container_payload is not None:
            is_mach = _is_machinery_producer_slug(slug)
            live_hash = MACHINERY_LIVE_SLUGS_KEY if is_mach else STANDING_LIVE_SLUGS_KEY
            live_ttl = MACHINERY_LIVE_SLUGS_TTL_S if is_mach else STANDING_LIVE_SLUGS_TTL_S
            if _roundup_payload_needs_live_rail(container_payload, now_ts=ts):
                if hasattr(rc, "hset"):
                    rc.hset(live_hash, slug, str(ts))
                if hasattr(rc, "expire"):
                    rc.expire(live_hash, live_ttl)
            else:
                if hasattr(rc, "hdel"):
                    rc.hdel(live_hash, slug)
            if not is_mach and feed_item is not None and hasattr(rc, "hdel"):
                rc.hdel(STANDING_RETIRED_SLUGS_KEY, slug)
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
    reason: Optional[str] = None,
    ttl_s: float = ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S,
    lifetime_s: float = ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
) -> bool:
    """Record a clean-empty marker in Redis when a grouping producer ran cleanly with nothing to show (#13183).

    Used by Celery prewarm workers only (never on the web event loop — #969).
    Lets `_publish_machinery_feed_from_prewarm_base` and `add_roundup_feed_items`
    distinguish an intentionally quiet/out-of-season grouping from a failed or
    expired one, carrying ``clean_empty_reason`` so data faults are visible in
    logs instead of misread as a quiet night.
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
            clean_empty_reason=reason,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(lifetime_s))
        if hasattr(rc, "hdel"):
            live_hash = (
                MACHINERY_LIVE_SLUGS_KEY
                if _is_machinery_producer_slug(slug)
                else STANDING_LIVE_SLUGS_KEY
            )
            rc.hdel(live_hash, slug)
        return True
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning(
            "roundup_containers: sync Redis clean-empty write failed for %s",
            slug,
            exc_info=True,
        )
        return False


def store_roundup_nothing_to_show_sync(
    rc: Any,
    slug: str,
    ts: float,
    *,
    reason: Optional[str] = None,
    ttl_s: float = ROUNDUP_STANDING_PREWARM_FRESH_TTL_S,
    lifetime_s: float = ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S,
) -> bool:
    """Record a standing producer's cacheable empty result via sync Redis (#12529).

    Used by Celery prewarm workers so cold Discover builds read the shared MGET
    instead of spending per-producer DB time on intentionally empty round-ups.
    """
    if rc is None or not hasattr(rc, "set"):
        return False
    prod = ROUNDUP_PRODUCERS.get(slug)
    rule_cfg = prod.rule if (prod is not None and isinstance(prod.rule, Mapping)) else {}
    if rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair":
        return False
    try:
        encoded = _encode_roundup_cache_entry(
            ts=ts,
            ttl_s=float(ttl_s),
            stale_ttl_s=float(lifetime_s),
            feed_item=None,
            container_payload=None,
            nothing_to_show=True,
            nothing_to_show_reason=reason,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(lifetime_s))
        if hasattr(rc, "hdel") and not _is_machinery_producer_slug(slug):
            rc.hdel(STANDING_LIVE_SLUGS_KEY, slug)
        return True
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning(
            "roundup_containers: sync Redis nothing-to-show write failed for %s",
            slug,
            exc_info=True,
        )
        return False


def store_roundup_settled_retired_sync(
    rc: Any,
    slug: str,
    ts: float,
    container_payload: Optional[dict[str, Any]],
    *,
    reason: Optional[str] = "all_members_settled",
    fixed_members: bool = True,
    long_skip: Optional[bool] = None,
) -> bool:
    """Cache a settled/closed round-up as hidden from Discover while keeping its page (#13718)."""
    if rc is None or not hasattr(rc, "set") or container_payload is None:
        return False
    prod = ROUNDUP_PRODUCERS.get(slug)
    rule_cfg = prod.rule if (prod is not None and isinstance(prod.rule, Mapping)) else {}
    if rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair":
        return False
    is_mach = _is_machinery_producer_slug(slug)
    effective_long_skip = (
        bool(fixed_members and not is_mach and reason != "all_members_closed")
        if long_skip is None
        else bool(long_skip and fixed_members and not is_mach)
    )
    if effective_long_skip:
        ttl_s = ROUNDUP_SETTLED_RETIRED_TTL_S
    elif is_mach:
        ttl_s = ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S
    elif reason == "all_members_closed":
        ttl_s = ROUNDUP_CACHE_TTL_S
    else:
        ttl_s = ROUNDUP_STANDING_PREWARM_FRESH_TTL_S
    stale_ttl_s = max(
        ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S if is_mach else ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S,
        float(ttl_s),
    )
    try:
        encoded = _encode_roundup_cache_entry(
            ts=ts,
            ttl_s=float(ttl_s),
            stale_ttl_s=float(stale_ttl_s),
            feed_item=None,
            container_payload=container_payload,
            clean_empty=True,
            clean_empty_reason=reason,
            nothing_to_show=True,
            nothing_to_show_reason=reason,
            settled_retired=True,
            long_skip=effective_long_skip,
        )
        rc.set(_redis_cache_key(slug), encoded, ex=int(stale_ttl_s))
        if hasattr(rc, "hdel"):
            if is_mach:
                rc.hdel(MACHINERY_LIVE_SLUGS_KEY, slug)
            else:
                rc.hdel(STANDING_LIVE_SLUGS_KEY, slug)
                rc.hdel(STANDING_WARM_SLUGS_KEY, slug)
                if not effective_long_skip:
                    rc.hdel(STANDING_RETIRED_SLUGS_KEY, slug)
        if effective_long_skip:
            if hasattr(rc, "hset"):
                rc.hset(STANDING_RETIRED_SLUGS_KEY, slug, str(ts))
            if hasattr(rc, "expire"):
                rc.expire(STANDING_RETIRED_SLUGS_KEY, STANDING_RETIRED_SLUGS_TTL_S)
        return True
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning(
            "roundup_containers: sync Redis settled-retired write failed for %s",
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
    *,
    keep_tombstone: bool = False,
    nothing_to_show: bool = False,
    nothing_to_show_reason: Optional[str] = None,
    settled_retired: bool = False,
    fixed_members: bool = False,
    long_skip: Optional[bool] = None,
    ttl_override_s: Optional[float] = None,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    ttl_s = (
        float(ttl_override_s)
        if ttl_override_s is not None
        else _roundup_cache_ttl_seconds(slug, container_payload)
    )
    stale_ttl_s = max(_roundup_cache_stale_ttl_seconds(slug, container_payload), ttl_s)
    redis_ex_s = stale_ttl_s
    if container_payload is None and keep_tombstone:
        # Keep a proper withdrawal note in Redis as long as copies are kept so
        # another web dyno cannot resurrect an older local copy after the 60s
        # retry window passes (#13146). Retry time (`ttl_s`) stays 60s.
        redis_ex_s = max(
            stale_ttl_s,
            ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S,
            ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
        )
    _roundup_local_cache[cache_key] = (
        ts,
        copy.deepcopy(feed_item),
        copy.deepcopy(container_payload),
    )
    is_nts_flag = bool(
        feed_item is None and nothing_to_show and (container_payload is None or settled_retired)
    )
    if is_nts_flag:
        _roundup_nothing_to_show_local[cache_key] = (ts, nothing_to_show_reason)
    else:
        _roundup_nothing_to_show_local.pop(cache_key, None)
    is_fixed_retired = bool(
        settled_retired
        and fixed_members
        and not _is_machinery_producer_slug(slug)
        and (
            (nothing_to_show_reason != "all_members_closed")
            if long_skip is None
            else bool(long_skip)
        )
    )
    if is_fixed_retired:
        _roundup_settled_retired_local[cache_key] = ts
    else:
        _roundup_settled_retired_local.pop(cache_key, None)
    if isinstance(db, AsyncSession):
        try:
            encoded = _encode_roundup_cache_entry(
                ts=ts,
                ttl_s=ttl_s,
                stale_ttl_s=redis_ex_s,
                feed_item=feed_item,
                container_payload=container_payload,
                clean_empty=bool(settled_retired),
                clean_empty_reason=nothing_to_show_reason if settled_retired else None,
                nothing_to_show=is_nts_flag,
                nothing_to_show_reason=nothing_to_show_reason if is_nts_flag else None,
                settled_retired=bool(settled_retired),
                long_skip=is_fixed_retired,
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
                    ex=int(redis_ex_s),
                ),
                treat_none_as_miss=False,
            )
            wrote_async = bool(set_res.is_ok)
            if wrote_async and is_fixed_retired:
                await bounded_redis_call(
                    lambda: client.hset(STANDING_RETIRED_SLUGS_KEY, slug, str(ts)),
                    treat_none_as_miss=False,
                )
                await bounded_redis_call(
                    lambda: client.expire(STANDING_RETIRED_SLUGS_KEY, STANDING_RETIRED_SLUGS_TTL_S),
                    treat_none_as_miss=False,
                )
                await bounded_redis_call(
                    lambda: client.hdel(STANDING_LIVE_SLUGS_KEY, slug),
                    treat_none_as_miss=False,
                )
                await bounded_redis_call(
                    lambda: client.hdel(STANDING_WARM_SLUGS_KEY, slug),
                    treat_none_as_miss=False,
                )
            elif wrote_async and not _is_machinery_producer_slug(slug) and (feed_item is not None or settled_retired):
                await bounded_redis_call(
                    lambda: client.hdel(STANDING_RETIRED_SLUGS_KEY, slug),
                    treat_none_as_miss=False,
                )
            elif wrote_async and _is_machinery_producer_slug(slug) and container_payload is not None and not settled_retired:
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
            elif wrote_async and _is_machinery_producer_slug(slug) and settled_retired:
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
    """Cache a timed-out producer cooldown locally for ``ROUNDUP_CACHE_TTL_S``.

    Never writes ``(None, None)`` to shared Redis: a web dyno that times out
    within 0.5 s when a copy just expired (or races a pre-warmer writing a
    fresh copy) must not overwrite shared Redis or poison sibling dynos' last
    good copies (#11259, #13146).
    """
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
    prev = _roundup_local_cache.get(cache_key)
    if prev is not None and prev[1] is not None and prev[2] is not None:
        return
    effective_ts = time.time() if ts is None else float(ts)
    _roundup_local_cache[cache_key] = (effective_ts, None, None)
    _roundup_nothing_to_show_local.pop(cache_key, None)
    _roundup_settled_retired_local.pop(cache_key, None)


async def _load_last_good_after_failure(
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float | datetime],
    pref_val: Any,
    public_shared_ok: bool,
    quiet_out: dict[str, Any],
) -> Optional[tuple[dict[str, Any], dict[str, Any], float, float]]:
    """Load the last good copy after a timeout/error, re-checking live Redis if needed."""
    last_good = await _load_last_good_roundup_copy(
        producer,
        db,
        now=now,
        prefetched_shared=pref_val if public_shared_ok else _PREFETCH_UNSET,
        shared_read_ok=public_shared_ok,
        quiet_out=quiet_out,
    )
    if (
        last_good is None
        and public_shared_ok
        and not quiet_out.get("clean_empty")
        and not quiet_out.get("nothing_to_show")
    ):
        # A pre-warmer or sibling dyno may have published a fresh copy while
        # this request spent its timeout waiting on Postgres (#11259).
        last_good = await _load_last_good_roundup_copy(
            producer,
            db,
            now=now,
            prefetched_shared=_PREFETCH_UNSET,
            shared_read_ok=True,
            quiet_out=quiet_out,
        )
    return last_good


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


_PREFETCH_UNSET = object()


async def _prefetch_shared_roundup_entries(
    producers: Sequence[RoundupProducer],
    db: Any,
) -> tuple[dict[str, Any], bool]:
    """Fetch shared Redis entries for multiple round-up producers together (#13184 follow-up).

    Uses one ``MGET`` when supported by the async Redis client (falling back to a
    single ``asyncio.gather`` of ``get`` calls for minimal test doubles), wrapped
    in one ``bounded_redis_call`` so the out-of-time branch never issues N serial
    Redis round-trips.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    if not producers or isinstance(db, (list, tuple)) or not isinstance(db, AsyncSession):
        return {}, True
    if not container_read_cache_enabled():
        return {}, True

    eligible_slugs: list[str] = []
    for p in producers:
        rule_cfg = p.rule if isinstance(p.rule, Mapping) else {}
        no_cache = (
            rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair"
        )
        if not no_cache:
            eligible_slugs.append(p.slug)
    if not eligible_slugs:
        return {}, True

    keys = [_redis_cache_key(slug) for slug in eligible_slugs]
    try:
        from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

        client = await get_shared_async_redis()
        if hasattr(client, "mget") and callable(client.mget):
            res = await bounded_redis_call(
                lambda: client.mget(keys),
                treat_none_as_miss=False,
            )
        else:
            res = await bounded_redis_call(
                lambda: asyncio.gather(*(client.get(k) for k in keys)),
                treat_none_as_miss=False,
            )
        if not res.is_ok or not isinstance(res.value, (list, tuple)):
            return {}, False
        return dict(zip(eligible_slugs, res.value)), True
    except Exception:  # noqa: BLE001 — fail-closed signal returned to caller
        logger.debug(
            "roundup_containers: batch shared cache prefetch failed for %d slugs",
            len(eligible_slugs),
            exc_info=True,
        )
        return {}, False


async def _load_last_good_roundup_copy(
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float | datetime] = None,
    local_only: bool = False,
    fail_closed_on_shared_error: bool = False,
    prefetched_shared: Any = _PREFETCH_UNSET,
    shared_read_ok: bool = True,
    quiet_out: Optional[dict[str, Any]] = None,
) -> Optional[tuple[dict[str, Any], dict[str, Any], float, float]]:
    """Return ``(feed_item, container_payload, age_s, keep_s)`` for the last good cached copy.

    Used when a Discover round-up refresh times out or errors so both standing
    round-ups and machinery groupings keep their last good copy while it is
    within its keep-time instead of disappearing from Discover (#13146).
    Respects ``producer.enabled`` and ``valid_from`` / ``valid_until`` (65-A),
    compares local vs shared Redis freshness so the newer entry always decides
    (including newer proper withdrawals), and judges live keep-time by ``now``.
    When ``quiet_out`` is provided and the winning shared entry is an unexpired
    ``clean_empty`` marker (#13183/#13186), populates ``quiet_out["clean_empty"] = True``
    and ``quiet_out["reason"]``.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled

    if quiet_out is not None:
        quiet_out["clean_empty"] = False
        quiet_out["nothing_to_show"] = False
        quiet_out["reason"] = None

    if producer.enabled is not None and not producer.enabled():
        return None
    ts, _now_dt = _normalize_roundup_now(now)
    if (producer.valid_from is not None and ts < producer.valid_from) or (
        producer.valid_until is not None and ts >= producer.valid_until
    ):
        return None
    is_fixture_seq = isinstance(db, (list, tuple))
    rule_cfg = producer.rule if isinstance(producer.rule, Mapping) else {}
    no_cache = (
        rule_cfg.get("cache") == "none" or rule_cfg.get("producer") == "yardstick_pair"
    )
    if is_fixture_seq or no_cache or not container_read_cache_enabled():
        return None

    cache_key = (
        producer.slug,
        "live" if isinstance(db, AsyncSession) else id(db),
    )
    # Candidate tuple: (built_at, feed_item, container_payload, stored_stale_ttl,
    #                   from_shared, clean_empty, clean_empty_reason, nothing_to_show, nts_reason,
    #                   settled_retired, settled_long_skip)
    local_candidate: Optional[
        tuple[
            float,
            Optional[dict[str, Any]],
            Optional[dict[str, Any]],
            Optional[float],
            bool,
            bool,
            Optional[str],
            bool,
            Optional[str],
            bool,
            bool,
        ]
    ] = None
    cached = _roundup_local_cache.get(cache_key)
    if cached is not None:
        local_nts = _roundup_nothing_to_show_local.get(cache_key)
        is_local_settled_long = bool(
            cached[1] is None
            and cached[2] is not None
            and cache_key in _roundup_settled_retired_local
            and float(_roundup_settled_retired_local[cache_key]) == float(cached[0])
        )
        local_nts_reason = (
            local_nts[1]
            if local_nts is not None and float(local_nts[0]) == float(cached[0])
            else None
        )
        is_local_settled = bool(
            is_local_settled_long
            or (
                cached[1] is None
                and cached[2] is not None
                and local_nts_reason in ("all_members_settled", "all_members_closed")
            )
        )
        is_local_nts = bool(
            cached[1] is None
            and local_nts is not None
            and float(local_nts[0]) == float(cached[0])
        ) or is_local_settled
        local_candidate = (
            float(cached[0]),
            cached[1],
            cached[2],
            None,
            False,
            is_local_settled,
            local_nts_reason if is_local_settled else None,
            is_local_nts,
            local_nts_reason or ("all_members_settled" if is_local_settled_long else None),
            is_local_settled,
            is_local_settled_long,
        )

    shared_candidate: Optional[
        tuple[
            float,
            Optional[dict[str, Any]],
            Optional[dict[str, Any]],
            Optional[float],
            bool,
            bool,
            Optional[str],
            bool,
            Optional[str],
            bool,
            bool,
        ]
    ] = None
    if not local_only and isinstance(db, AsyncSession):
        raw_val: Any = None
        if prefetched_shared is not _PREFETCH_UNSET:
            if not shared_read_ok:
                if fail_closed_on_shared_error:
                    return None
            else:
                raw_val = prefetched_shared
        else:
            try:
                from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

                client = await get_shared_async_redis()
                res = await bounded_redis_call(
                    lambda: client.get(_redis_cache_key(producer.slug)),
                    treat_none_as_miss=False,
                )
                if not res.is_ok:
                    if fail_closed_on_shared_error:
                        return None
                else:
                    raw_val = res.value
            except Exception:  # noqa: BLE001 — stale fallback read fails open unless fail-closed
                logger.debug(
                    "roundup_containers: last-good shared cache read failed for %s",
                    producer.slug,
                    exc_info=True,
                )
                if fail_closed_on_shared_error:
                    return None
        if raw_val:
            try:
                raw = json.loads(
                    raw_val.decode("utf-8")
                    if isinstance(raw_val, (bytes, bytearray))
                    else raw_val
                )
                if isinstance(raw, dict) and isinstance(raw.get("built_at"), (int, float)):
                    raw_stale_ttl = raw.get("stale_ttl_s")
                    raw_ttl = raw.get("ttl_s")
                    is_sr = raw.get("settled_retired") is True
                    is_sr_long = bool(
                        is_sr
                        and (
                            raw.get("long_skip") is True
                            or (
                                isinstance(raw_ttl, (int, float))
                                and float(raw_ttl) >= ROUNDUP_SETTLED_RETIRED_TTL_S
                            )
                        )
                    )
                    shared_candidate = (
                        float(raw["built_at"]),
                        raw.get("feed_item"),
                        raw.get("container_payload"),
                        float(raw_stale_ttl)
                        if isinstance(raw_stale_ttl, (int, float))
                        else None,
                        True,
                        (raw.get("clean_empty") is True) or is_sr,
                        str(raw.get("clean_empty_reason"))
                        if raw.get("clean_empty_reason")
                        else ("all_members_settled" if is_sr else None),
                        (raw.get("nothing_to_show") is True) or is_sr,
                        str(raw.get("nothing_to_show_reason"))
                        if raw.get("nothing_to_show_reason")
                        else ("all_members_settled" if is_sr else None),
                        is_sr,
                        is_sr_long,
                    )
            except Exception:  # noqa: BLE001 — malformed shared entry fails open/closed per flag
                logger.debug(
                    "roundup_containers: last-good shared cache decode failed for %s",
                    producer.slug,
                    exc_info=True,
                )
                if fail_closed_on_shared_error:
                    return None

    if shared_candidate is not None and local_candidate is not None:
        chosen = (
            shared_candidate
            if shared_candidate[0] >= local_candidate[0]
            else local_candidate
        )
    else:
        chosen = shared_candidate if shared_candidate is not None else local_candidate

    if chosen is None:
        return None

    (
        built_at,
        fi,
        cp,
        stored_stale_ttl,
        from_shared,
        is_clean_empty,
        ce_reason,
        is_nothing_to_show,
        nts_reason,
        is_settled_retired,
        is_settled_long_skip,
    ) = chosen
    if fi is None or cp is None:
        if from_shared:
            _roundup_local_cache[cache_key] = (built_at, None, cp)
            if is_nothing_to_show or is_settled_retired:
                _roundup_nothing_to_show_local[cache_key] = (
                    built_at,
                    nts_reason or ("all_members_settled" if is_settled_retired else None),
                )
            else:
                _roundup_nothing_to_show_local.pop(cache_key, None)
            if (
                is_settled_long_skip
                and _producer_has_fixed_members(producer)
                and not _is_machinery_producer_slug(producer.slug)
            ):
                _roundup_settled_retired_local[cache_key] = built_at
            else:
                _roundup_settled_retired_local.pop(cache_key, None)
        if (is_clean_empty or is_settled_retired) and quiet_out is not None:
            quiet_keep_s = (
                float(stored_stale_ttl)
                if isinstance(stored_stale_ttl, (int, float)) and stored_stale_ttl > 0
                else (
                    ROUNDUP_SETTLED_RETIRED_TTL_S
                    if is_settled_long_skip
                    else (
                        ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
                        if _is_machinery_producer_slug(producer.slug)
                        else ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S
                    )
                )
            )
            if max(0.0, ts - built_at) < quiet_keep_s:
                quiet_out["clean_empty"] = True
                quiet_out["nothing_to_show"] = True
                quiet_out["reason"] = ce_reason or nts_reason or (
                    "all_members_settled" if is_settled_retired else None
                )
        elif is_nothing_to_show and quiet_out is not None:
            nts_keep_s = (
                float(stored_stale_ttl)
                if isinstance(stored_stale_ttl, (int, float)) and stored_stale_ttl > 0
                else ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S
            )
            if max(0.0, ts - built_at) < nts_keep_s:
                quiet_out["nothing_to_show"] = True
                quiet_out["reason"] = nts_reason
        return None

    keep_s = _roundup_effective_keep_seconds(
        producer.slug,
        cp,
        now_ts=ts,
        stored_stale_ttl=stored_stale_ttl,
    )
    age_s = max(0.0, ts - built_at)
    if age_s < keep_s:
        if from_shared:
            _roundup_local_cache[cache_key] = (built_at, fi, cp)
        _record_roundup_live_origin(built_at, producer.slug, cp)
        return copy.deepcopy(fi), copy.deepcopy(cp), age_s, keep_s
    return None


def _open_roundup_bg_session() -> Any:
    """Open a standalone AsyncSession for detached SWR background rebuilds (#13475)."""
    from app.services.database import async_session_maker

    return async_session_maker()


def _roundup_entry_swr_eligible(
    container_payload: Optional[Mapping[str, Any]],
    *,
    age_s: float,
    now_ts: float,
    swr_max_age_s: float,
) -> bool:
    """True when an expired set copy holds no live game and sits under ``swr_max_age_s`` (#13475)."""
    if container_payload is None or swr_max_age_s <= 0:
        return False
    if _roundup_payload_needs_live_rail(container_payload, now_ts=now_ts):
        return False
    return 0.0 <= float(age_s) < float(swr_max_age_s)


def _trigger_roundup_bg_refresh(
    cache_key: tuple[str, Any],
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float | datetime],
    licences_registry: Optional[dict[str, Any]],
    licences_path: Optional[Path | str],
) -> None:
    """Start at most one detached background rebuild per cache key on SWR hits (#13475)."""
    if cache_key in _roundup_inflight_builds:
        return
    existing = _roundup_bg_refresh_tasks.get(cache_key)
    if existing is not None and not existing.done():
        return

    from sqlalchemy.ext.asyncio import AsyncSession

    is_async_session = isinstance(db, AsyncSession)

    async def _runner() -> None:
        try:
            if is_async_session:
                async with _open_roundup_bg_session() as bg_db:
                    await asyncio.wait_for(
                        evaluate_roundup_producer(
                            producer,
                            bg_db,
                            now=now,
                            licences_registry=licences_registry,
                            licences_path=licences_path,
                            force_refresh=True,
                        ),
                        timeout=ROUNDUP_BG_REFRESH_TIMEOUT_S,
                    )
            else:
                await asyncio.wait_for(
                    evaluate_roundup_producer(
                        producer,
                        db,
                        now=now,
                        licences_registry=licences_registry,
                        licences_path=licences_path,
                        force_refresh=True,
                    ),
                    timeout=ROUNDUP_BG_REFRESH_TIMEOUT_S,
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — failed rebuild keeps existing copy untouched
            logger.warning(
                "roundup_containers: background SWR rebuild failed for %s; keeping copy",
                producer.slug,
                exc_info=True,
            )
        finally:
            if _roundup_bg_refresh_tasks.get(cache_key) is task:
                _roundup_bg_refresh_tasks.pop(cache_key, None)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_runner())
    _roundup_bg_refresh_tasks[cache_key] = task


async def _singleflight_roundup_build(
    cache_key: tuple[str, Any],
    builder: Callable[[], Any],
    *,
    outcome_meta: Optional[dict[str, Any]] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Coalesce simultaneous inline rebuilds onto one execution per cache key (#13475)."""
    while True:
        shared = _roundup_inflight_builds.get(cache_key)
        if shared is None:
            break
        try:
            fi, cp, meta_snapshot = await asyncio.shield(shared)
            if outcome_meta is not None and isinstance(meta_snapshot, Mapping):
                outcome_meta.update(meta_snapshot)
            return copy.deepcopy(fi), copy.deepcopy(cp)
        except _RoundupBuildAbandoned:
            continue

    loop = asyncio.get_running_loop()
    shared = loop.create_future()
    shared.add_done_callback(lambda f: f.cancelled() or f.exception())
    _roundup_inflight_builds[cache_key] = shared
    try:
        fi, cp, meta_snapshot = await builder()
    except Exception as exc:
        if _roundup_inflight_builds.get(cache_key) is shared:
            _roundup_inflight_builds.pop(cache_key, None)
        if not shared.done():
            shared.set_exception(exc)
        raise
    except BaseException:
        if _roundup_inflight_builds.get(cache_key) is shared:
            _roundup_inflight_builds.pop(cache_key, None)
        if not shared.done():
            shared.set_exception(_RoundupBuildAbandoned())
        raise
    if _roundup_inflight_builds.get(cache_key) is shared:
        _roundup_inflight_builds.pop(cache_key, None)
    if not shared.done():
        shared.set_result((fi, cp, meta_snapshot))
    if outcome_meta is not None and isinstance(meta_snapshot, Mapping):
        outcome_meta.update(meta_snapshot)
    return copy.deepcopy(fi), copy.deepcopy(cp)


async def evaluate_roundup_producer(
    producer: RoundupProducer,
    db: Any,
    *,
    now: Optional[float | datetime] = None,
    licences_registry: Optional[dict[str, Any]] = None,
    licences_path: Optional[Path | str] = None,
    force_refresh: bool = False,
    allow_stale: bool = False,
    stale_while_revalidate_seconds: Optional[float] = None,
    trigger_bg_refresh: bool = True,
    prefetched_shared: Any = _PREFETCH_UNSET,
    shared_read_ok: bool = True,
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

    swr_limit = (
        float(stale_while_revalidate_seconds)
        if stale_while_revalidate_seconds is not None and stale_while_revalidate_seconds > 0
        else None
    )

    if use_cache and not force_refresh:
        local_stale_fallback: Optional[tuple[float, dict[str, Any], dict[str, Any]]] = None
        local_swr_fallback: Optional[tuple[float, dict[str, Any], dict[str, Any]]] = None
        chosen_swr: Optional[tuple[float, dict[str, Any], dict[str, Any]]] = None
        local_timeout_cooldown: Optional[tuple[float, Any, Any]] = None
        cached = _roundup_local_cache.get(cache_key)
        if cached is not None:
            local_ttl = _roundup_cache_ttl_seconds(producer.slug, cached[2])
            local_sr_ts = _roundup_settled_retired_local.get(cache_key)
            is_local_sr = bool(
                cached[1] is None
                and cached[2] is not None
                and local_sr_ts is not None
                and float(local_sr_ts) == float(cached[0])
            )
            if is_local_sr:
                local_ttl = max(local_ttl, ROUNDUP_SETTLED_RETIRED_TTL_S)
            local_nts = _roundup_nothing_to_show_local.get(cache_key)
            is_local_nts = bool(
                is_local_sr
                or (
                    cached[1] is None
                    and local_nts is not None
                    and float(local_nts[0]) == float(cached[0])
                )
            )
            if (ts - cached[0]) < local_ttl:
                if (
                    cached[1] is None
                    and cached[2] is None
                    and not is_local_sr
                    and not is_local_nts
                    and isinstance(db, AsyncSession)
                ):
                    # Local timeout cooldown only skips Postgres on this dyno; allow
                    # a newer valid copy published in shared Redis to supersede it.
                    local_timeout_cooldown = cached
                else:
                    _record_roundup_live_origin(cached[0], producer.slug, cached[2])
                    return copy.deepcopy(cached[1]), copy.deepcopy(cached[2])
            is_local_nts_cached = bool(is_local_nts and cached[2] is not None)
            if (
                allow_stale
                and cached[2] is not None
                and (cached[1] is not None or is_local_nts_cached)
            ):
                local_stale_ttl = _roundup_effective_keep_seconds(
                    producer.slug,
                    cached[2],
                    now_ts=ts,
                )
                if max(0.0, ts - cached[0]) < local_stale_ttl:
                    local_stale_fallback = (cached[0], cached[1], cached[2])
            elif (
                not allow_stale
                and swr_limit is not None
                and cached[2] is not None
                and (cached[1] is not None or is_local_nts_cached)
                and _roundup_entry_swr_eligible(
                    cached[2],
                    age_s=max(0.0, ts - cached[0]),
                    now_ts=ts,
                    swr_max_age_s=swr_limit,
                )
            ):
                local_swr_fallback = (cached[0], cached[1], cached[2])
        if isinstance(db, AsyncSession):
            try:
                raw_val: Any = None
                if prefetched_shared is not _PREFETCH_UNSET:
                    if shared_read_ok:
                        raw_val = prefetched_shared
                else:
                    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

                    client = await get_shared_async_redis()
                    res = await bounded_redis_call(
                        lambda: client.get(_redis_cache_key(producer.slug))
                    )
                    if res.is_ok:
                        raw_val = res.value
                if raw_val:
                    raw = json.loads(
                        raw_val.decode("utf-8")
                        if isinstance(raw_val, (bytes, bytearray))
                        else raw_val
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
                        is_sr = raw.get("settled_retired") is True
                        sr_reason = (
                            str(raw.get("nothing_to_show_reason"))
                            if raw.get("nothing_to_show_reason")
                            else ("all_members_settled" if is_sr else None)
                        )
                        age_s = max(0.0, ts - built_at)
                        cooldown_superseded = (
                            local_timeout_cooldown is None
                            or (
                                fi is not None
                                and cp is not None
                                and built_at > float(local_timeout_cooldown[0])
                            )
                        )
                        if age_s < raw_ttl and cooldown_superseded:
                            _roundup_local_cache[cache_key] = (built_at, fi, cp)
                            if is_sr and fi is None:
                                _roundup_nothing_to_show_local[cache_key] = (built_at, sr_reason)
                                is_sr_long = bool(
                                    (
                                        raw.get("long_skip") is True
                                        or raw_ttl >= ROUNDUP_SETTLED_RETIRED_TTL_S
                                    )
                                    and raw_ttl >= ROUNDUP_SETTLED_RETIRED_TTL_S
                                    and _producer_has_fixed_members(producer)
                                    and not _is_machinery_producer_slug(producer.slug)
                                )
                                if is_sr_long:
                                    _roundup_settled_retired_local[cache_key] = built_at
                                else:
                                    _roundup_settled_retired_local.pop(cache_key, None)
                            elif fi is not None:
                                _roundup_settled_retired_local.pop(cache_key, None)
                            _record_roundup_live_origin(built_at, producer.slug, cp)
                            return copy.deepcopy(fi), copy.deepcopy(cp)
                        if allow_stale and cooldown_superseded:
                            if (fi is None and not (is_sr and cp is not None)) or cp is None:
                                if (
                                    local_stale_fallback is not None
                                    and built_at >= local_stale_fallback[0]
                                ):
                                    local_stale_fallback = None
                                    _roundup_local_cache[cache_key] = (built_at, None, None)
                            else:
                                raw_stale_ttl = raw.get("stale_ttl_s")
                                stale_max_s = _roundup_effective_keep_seconds(
                                    producer.slug,
                                    cp,
                                    now_ts=ts,
                                    stored_stale_ttl=(
                                        float(raw_stale_ttl)
                                        if isinstance(raw_stale_ttl, (int, float))
                                        else None
                                    ),
                                )
                                if age_s < stale_max_s and (
                                    local_stale_fallback is None
                                    or built_at >= local_stale_fallback[0]
                                ):
                                    _roundup_local_cache[cache_key] = (built_at, fi, cp)
                                    if is_sr and fi is None:
                                        _roundup_nothing_to_show_local[cache_key] = (built_at, sr_reason)
                                    _record_roundup_live_origin(
                                        built_at, producer.slug, cp
                                    )
                                    return copy.deepcopy(fi), copy.deepcopy(cp)
                        elif swr_limit is not None and cooldown_superseded:
                            if (fi is None and not (is_sr and cp is not None)) or cp is None:
                                if (
                                    local_swr_fallback is not None
                                    and built_at >= local_swr_fallback[0]
                                ):
                                    local_swr_fallback = None
                                    _roundup_local_cache[cache_key] = (built_at, None, None)
                            elif _roundup_entry_swr_eligible(
                                cp,
                                age_s=age_s,
                                now_ts=ts,
                                swr_max_age_s=swr_limit,
                            ) and (
                                local_swr_fallback is None
                                or built_at >= local_swr_fallback[0]
                            ):
                                _roundup_local_cache[cache_key] = (built_at, fi, cp)
                                if is_sr and fi is None:
                                    _roundup_nothing_to_show_local[cache_key] = (built_at, sr_reason)
                                chosen_swr = (built_at, fi, cp)
            except Exception:  # noqa: BLE001 — cache read fails open
                logger.debug(
                    "roundup_containers: shared cache read failed for %s",
                    producer.slug,
                    exc_info=True,
                )
        if local_stale_fallback is not None:
            _record_roundup_live_origin(
                local_stale_fallback[0], producer.slug, local_stale_fallback[2]
            )
            return copy.deepcopy(local_stale_fallback[1]), copy.deepcopy(
                local_stale_fallback[2]
            )
        swr_entry = chosen_swr or local_swr_fallback
        if swr_entry is not None:
            _record_roundup_live_origin(swr_entry[0], producer.slug, swr_entry[2])
            if trigger_bg_refresh:
                _trigger_roundup_bg_refresh(
                    cache_key,
                    producer,
                    db,
                    now=now,
                    licences_registry=licences_registry,
                    licences_path=licences_path,
                )
            return copy.deepcopy(swr_entry[1]), copy.deepcopy(swr_entry[2])
        if local_timeout_cooldown is not None:
            return None, None

    async def _produce_and_store() -> tuple[
        Optional[dict[str, Any]],
        Optional[dict[str, Any]],
        Optional[dict[str, Any]],
    ]:
        local_meta: Optional[dict[str, Any]] = (
            {"clean_empty": False, "reason": None}
            if (outcome_meta is not None or (use_cache and not force_refresh))
            else None
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
            reason_text = ",".join(str(r) for r in reasons if r) or (
                "clean_empty_refusal" if cacheable else "transient_refusal"
            )
            if local_meta is not None:
                local_meta["clean_empty"] = bool(cacheable)
                local_meta["reason"] = reason_text
            logger.warning(
                "flow_sentinel matching_defect: roundup %s refused reasons=%s",
                producer.slug,
                reasons,
            )
            if use_cache and cacheable:
                await _store_roundup_cache_entry(
                    cache_key,
                    producer.slug,
                    ts,
                    None,
                    None,
                    db,
                    keep_tombstone=True,
                    nothing_to_show=True,
                    nothing_to_show_reason=reason_text,
                )
            return None, None, local_meta

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
            if local_meta is not None:
                local_meta["clean_empty"] = True
                local_meta["reason"] = "empty_payload"
            if use_cache:
                await _store_roundup_cache_entry(
                    cache_key,
                    producer.slug,
                    ts,
                    None,
                    None,
                    db,
                    keep_tombstone=True,
                    nothing_to_show=True,
                    nothing_to_show_reason="empty_payload",
                )
            return None, None, local_meta

        settlement_state = _roundup_members_settlement_state(container_payload)
        all_settled = settlement_state == "all_settled"
        all_closed = settlement_state == "all_closed"
        settled_suppressed = (
            all_settled
            or all_closed
            or bool(getattr(outcome, "suppress_feed_item", False))
        )
        if settled_suppressed:
            feed_item = None

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
                allow_settled = (producer_kind == "series_hub") or all_settled
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
                    if local_meta is not None:
                        local_meta["clean_empty"] = False
                        local_meta["reason"] = "licence_violation"
                    logger.warning(
                        "flow_sentinel matching_defect: roundup %s suspended kind %s (%s)",
                        producer.slug,
                        producer_kind,
                        bad_reason,
                    )
                    return None, None, local_meta

        if settled_suppressed:
            fixed_members = _producer_has_fixed_members(producer)
            is_mach = _is_machinery_producer_slug(producer.slug)
            sr_reason = (
                "all_members_settled"
                if all_settled
                else ("all_members_closed" if all_closed else "suppressed_feed_item")
            )
            long_skip = bool(all_settled and fixed_members and not is_mach)
            if local_meta is not None:
                local_meta["clean_empty"] = True
                local_meta["settled_retired"] = True
                local_meta["fixed_members"] = fixed_members
                local_meta["long_skip"] = long_skip
                local_meta["reason"] = sr_reason
            if use_cache:
                ttl_ov = ROUNDUP_SETTLED_RETIRED_TTL_S if long_skip else None
                await _store_roundup_cache_entry(
                    cache_key,
                    producer.slug,
                    ts,
                    None,
                    container_payload,
                    db,
                    keep_tombstone=True,
                    nothing_to_show=True,
                    nothing_to_show_reason=sr_reason,
                    settled_retired=True,
                    fixed_members=fixed_members,
                    long_skip=long_skip,
                    ttl_override_s=ttl_ov,
                )
            return None, container_payload, local_meta

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
                if local_meta is not None:
                    local_meta["clean_empty"] = True
                    local_meta["reason"] = "not_trading_screen_empty"
                if use_cache:
                    await _store_roundup_cache_entry(
                        cache_key,
                        producer.slug,
                        ts,
                        None,
                        None,
                        db,
                        keep_tombstone=True,
                    )
                return None, None, local_meta

        if use_cache:
            await _store_roundup_cache_entry(
                cache_key, producer.slug, ts, feed_item, container_payload, db
            )

        return feed_item, container_payload, local_meta

    if use_cache and not force_refresh:
        return await _singleflight_roundup_build(
            cache_key, _produce_and_store, outcome_meta=outcome_meta
        )

    fi_out, cp_out, meta_out = await _produce_and_store()
    if outcome_meta is not None and isinstance(meta_out, Mapping):
        outcome_meta.update(meta_out)
    return fi_out, cp_out


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
                    evaluate_roundup_producer(
                        producer,
                        db,
                        now=now,
                        stale_while_revalidate_seconds=ROUNDUP_PAGE_SWR_MAX_AGE_S,
                        trigger_bg_refresh=False,
                    ),
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
    _feed_item, payload = await evaluate_roundup_producer(
        producer,
        db,
        now=now,
        stale_while_revalidate_seconds=ROUNDUP_PAGE_SWR_MAX_AGE_S,
    )
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
                _ch_fi, ch_payload = await evaluate_roundup_producer(
                    ch_prod,
                    db,
                    now=now,
                    stale_while_revalidate_seconds=ROUNDUP_PAGE_SWR_MAX_AGE_S,
                )
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
            _p_fi, p_payload = await evaluate_roundup_producer(
                p_prod,
                db,
                now=now,
                stale_while_revalidate_seconds=ROUNDUP_PAGE_SWR_MAX_AGE_S,
            )
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
    if type(card) is not dict and not isinstance(card, Mapping):
        return False
    if card.get("type") != "bundle":
        return False
    data = card.get("data")
    return (type(data) is dict or isinstance(data, Mapping)) and data.get("kind") == "roundup"


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
    raw_candidates: list[str] = []
    r_id = str(data.get("id") or "").strip()
    if r_id:
        raw_candidates.append(r_id)
    story_key = str(data.get("story_key") or "").strip()
    if story_key:
        raw_candidates.append(story_key)
    set_id = str(data.get("set_id") or "").strip()
    if set_id:
        raw_candidates.append(set_id)
    cref = data.get("collection_ref")
    slug = str(cref.get("slug") or "").strip() if isinstance(cref, Mapping) else ""
    if slug:
        raw_candidates.append(slug)
    roundup_contract = data.get("roundup")
    if isinstance(roundup_contract, Mapping):
        machinery = roundup_contract.get("machinery_card")
        if isinstance(machinery, Mapping):
            mslug = str(machinery.get("slug") or "").strip()
            if mslug:
                raw_candidates.append(mslug)
    for val in raw_candidates:
        keys.add(val)
        keys.add(f"bundle:{val}")
        keys.add(f"bundle-{val}")
        keys.add(f"roundup:{val}")
        keys.add(f"bundle:roundup:{val}")
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
    if type(item) is not dict and not isinstance(item, Mapping):
        return False
    if item.get("type") in ("bundle", "collection"):
        return True
    return _is_roundup_bundle_card(item)


def _client_sport_category(item: Any) -> str:
    if type(item) is not dict and not isinstance(item, Mapping):
        return "other"
    item_type = item.get("type")
    data = item.get("data")
    if type(data) is not dict and not isinstance(data, Mapping):
        return "other"
    if item_type == "event":
        sport = str(data.get("sport") or "")
        return (sport.split("_")[0] if sport else "") or "sports"
    if item_type == "futures":
        return str(data.get("llm_sport_category") or "other")
    if item_type == "bundle":
        members = data.get("items")
        if (type(members) is list or isinstance(members, Sequence)) and members:
            return _client_sport_category(members[0])
        return "other"
    return "golf"


def _space_sport_tags(
    tagged: Sequence[tuple[str, bool, Any]],
) -> list[tuple[str, bool, Any]]:
    """O(M) per-category FIFO deque equivalent of ``_client_space_by_sport`` (#13445)."""
    n = len(tagged)
    if n <= 2:
        return list(tagged)
    non_sport_q: deque[tuple[int, tuple[str, bool, Any]]] = deque()
    sport_qs: dict[str, deque[tuple[int, tuple[str, bool, Any]]]] = {}
    for orig_idx, entry in enumerate(tagged):
        cat, is_sport, _ = entry
        if is_sport:
            q = sport_qs.get(cat)
            if q is None:
                q = deque()
                sport_qs[cat] = q
            q.append((orig_idx, entry))
        else:
            non_sport_q.append((orig_idx, entry))

    non_sports_count = len(non_sport_q)
    max_sports_run = 2 if non_sports_count >= 4 else 3
    result: list[tuple[str, bool, Any]] = []
    last_sport = ""
    sports_since_non_sport = 0

    for _ in range(n):
        best_idx = n
        best_q: deque[tuple[int, tuple[str, bool, Any]]] | None = None
        if non_sport_q:
            best_idx = non_sport_q[0][0]
            best_q = non_sport_q
        if sports_since_non_sport < max_sports_run:
            for cat, q in sport_qs.items():
                if q and cat != last_sport and q[0][0] < best_idx:
                    best_idx = q[0][0]
                    best_q = q
        if best_q is None:
            for cat, q in sport_qs.items():
                if q and cat != last_sport and q[0][0] < best_idx:
                    best_idx = q[0][0]
                    best_q = q
        if best_q is None:
            if non_sport_q and non_sport_q[0][0] < best_idx:
                best_idx = non_sport_q[0][0]
                best_q = non_sport_q
            for q in sport_qs.values():
                if q and q[0][0] < best_idx:
                    best_idx = q[0][0]
                    best_q = q
        assert best_q is not None
        _, chosen = best_q.popleft()
        cat, is_sport, _ = chosen
        result.append(chosen)
        if is_sport:
            last_sport = cat
            sports_since_non_sport += 1
        else:
            last_sport = ""
            sports_since_non_sport = 0
    return result


def _client_space_by_sport(
    items: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if len(items) <= 2:
        return list(items)
    tagged = []
    for it in items:
        cat = _client_sport_category(it)
        tagged.append((cat, cat in _CLIENT_SPORT_CATEGORIES, it))
    return [entry[2] for entry in _space_sport_tags(tagged)]


def _spaced_tags_have_adjacent_roundup(
    tagged: Sequence[tuple[str, bool, tuple[bool, bool]]],
) -> bool:
    spaced = _space_sport_tags(_space_sport_tags(tagged))
    for i in range(len(spaced) - 1):
        a_grp, a_rnd = spaced[i][2]
        b_grp, b_rnd = spaced[i + 1][2]
        if a_grp and b_grp and (a_rnd or b_rnd):
            return True
    return False


def _spaced_has_adjacent_roundup(
    items: Sequence[Mapping[str, Any]],
) -> bool:
    tagged = []
    for it in items:
        cat = _client_sport_category(it)
        tagged.append(
            (
                cat,
                cat in _CLIENT_SPORT_CATEGORIES,
                (_is_grouped_feed_card(it), _is_roundup_bundle_card(it)),
            )
        )
    return _spaced_tags_have_adjacent_roundup(tagged)


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
    if start_pos > n:
        return None
    if candidate_item is None:
        item_grouped = [_is_grouped_feed_card(it) for it in items]
        pos = start_pos
        while pos <= n:
            prev_is_grouped = pos > 0 and item_grouped[pos - 1]
            next_is_grouped = pos < n and item_grouped[pos]
            if not prev_is_grouped and not next_is_grouped:
                return pos
            pos += 1
        return None

    item_tags: list[tuple[str, bool, tuple[bool, bool]]] = []
    for it in items:
        cat = _client_sport_category(it)
        item_tags.append(
            (
                cat,
                cat in _CLIENT_SPORT_CATEGORIES,
                (_is_grouped_feed_card(it), _is_roundup_bundle_card(it)),
            )
        )
    cand_cat = _client_sport_category(candidate_item)
    cand_tag = (
        cand_cat,
        cand_cat in _CLIENT_SPORT_CATEGORIES,
        (
            _is_grouped_feed_card(candidate_item),
            _is_roundup_bundle_card(candidate_item),
        ),
    )

    first_raw_non_adjacent: Optional[int] = None
    pos = start_pos
    win_floor = int(page_window)
    while pos <= n:
        prev_is_grouped = pos > 0 and item_tags[pos - 1][2][0]
        next_is_grouped = pos < n and item_tags[pos][2][0]
        if not prev_is_grouped and not next_is_grouped:
            if first_raw_non_adjacent is None:
                first_raw_non_adjacent = pos
            win_end = max(win_floor, pos + 2)
            window_tags = item_tags[:pos] + [cand_tag] + item_tags[pos : win_end - 1]
            if not _spaced_tags_have_adjacent_roundup(window_tags):
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


def _is_preview_producer(producer: RoundupProducer) -> bool:
    """Return True when a producer is staged as ``preview`` (never on public Discover)."""
    return str(getattr(producer, "stage", "public") or "public").strip().lower() == "preview"


def _roundup_lesser_soccer_penalty(item: Mapping[str, Any]) -> int:
    """Return ``MINOR_LEAGUE_PENALTY`` or ``OBSCURE_SOCCER_PENALTY`` for lesser soccer cards (#13093).

    Multi-row soccer round-ups and sibling families carry no individual market
    score before insertion, so they otherwise inherit their anchor neighbour's
    high seat on Discover. Matches single-market futures parity in
    ``app.utils.futures_highlights``: minor-league regex pays ``-15``, any
    non-top-tier soccer competition pays ``-20``, and top-tier leagues
    (Champions League, Premier League, La Liga, Bundesliga, Serie A, Ligue 1,
    Europa League, MLS, World Cup, Liga MX, etc.) pay ``0``.
    """
    from app.utils.futures_highlights import (
        MINOR_LEAGUE_PENALTY,
        OBSCURE_SOCCER_PENALTY,
        is_minor_league_market,
        is_top_tier_soccer_market,
    )

    if not isinstance(item, Mapping):
        return 0
    slug = _roundup_item_slug(item)
    prod = ROUNDUP_PRODUCERS.get(slug) if slug else None
    data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
    roundup = data.get("roundup") if isinstance(data.get("roundup"), Mapping) else {}
    tag = str(roundup.get("tag") or "").strip().lower()
    kicker = str(roundup.get("kicker") or "").strip().lower()
    children = [
        ch.get("data")
        for ch in (data.get("items") or ())
        if isinstance(ch, Mapping) and isinstance(ch.get("data"), Mapping)
    ]
    child_cats = [str(ch.get("llm_sport_category") or "").strip().lower() for ch in children]
    is_soccer = (
        (prod is not None and str(prod.category or "").strip().lower() == "soccer")
        or ("soccer" in tag or "soccer" in kicker)
        or (len(child_cats) > 0 and all(cat == "soccer" for cat in child_cats))
    )
    if not is_soccer:
        return 0

    texts: list[str] = []
    for raw in (
        data.get("title"),
        item.get("headline"),
        prod.name if prod is not None else None,
    ):
        if raw and str(raw).strip():
            texts.append(str(raw).strip())
    for ch in children:
        for key in ("name", "title"):
            val = ch.get(key)
            if val and str(val).strip():
                texts.append(str(val).strip())
    for row in roundup.get("rows") or ():
        if isinstance(row, Mapping):
            for key in ("market_name", "title", "subtitle"):
                val = row.get(key)
                if val and str(val).strip():
                    texts.append(str(val).strip())

    def _grade_text(text: str) -> int:
        if is_minor_league_market(text):
            return int(MINOR_LEAGUE_PENALTY)
        if is_top_tier_soccer_market(text):
            return 0
        return int(OBSCURE_SOCCER_PENALTY)

    return max(
        (_grade_text(text) for text in texts),
        default=int(OBSCURE_SOCCER_PENALTY),
    )


def _penalized_roundup_score(
    item: Mapping[str, Any],
    anchor: Optional[Mapping[str, Any]],
    penalty: int,
) -> float:
    base = float(item.get("score") or 0.0)
    if base <= 0.0 and isinstance(anchor, Mapping):
        base = float(anchor.get("score") or 0.0)
    return max(0.0, base + float(penalty))


def _score_demoted_seat_index(
    items: Sequence[Mapping[str, Any]],
    min_idx: int,
    penalized_score: float,
) -> int:
    """Seat index at/after ``min_idx`` placing a penalized card alongside equal-or-lower scores."""
    last_higher = max(
        (
            i
            for i in range(max(0, min_idx), len(items))
            if float(items[i].get("score") or 0.0) > penalized_score
        ),
        default=None,
    )
    return max(min_idx, (last_higher + 1) if last_higher is not None else min_idx)


def _is_preview_roundup_item(item: Mapping[str, Any]) -> bool:
    """Return True when a composed feed item belongs to a ``stage="preview"`` grouping."""
    slug = _roundup_item_slug(item)
    if slug:
        prod = ROUNDUP_PRODUCERS.get(slug)
        if prod is not None and _is_preview_producer(prod):
            return True
    data = item.get("data") if isinstance(item.get("data"), Mapping) else None
    roundup = (
        data.get("roundup")
        if isinstance(data, Mapping) and isinstance(data.get("roundup"), Mapping)
        else None
    )
    card = (
        roundup.get("machinery_card")
        if isinstance(roundup, Mapping) and isinstance(roundup.get("machinery_card"), Mapping)
        else None
    )
    return isinstance(card, Mapping) and str(card.get("stage") or "").strip().lower() == "preview"


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

    def _hydrate_card_at_seat(
        r_item: Mapping[str, Any],
        target_idx: int,
        *,
        penalty: int = 0,
        anchor_override: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        card = copy.deepcopy(dict(r_item))
        if result:
            anchor = (
                anchor_override
                if anchor_override is not None
                else (result[target_idx] if target_idx < len(result) else result[-1])
            )
            if penalty < 0:
                card["score"] = _penalized_roundup_score(card, anchor, penalty)
                if "_rank_score" in anchor and "_rank_score" not in card:
                    card["_rank_score"] = max(
                        0.0, float(anchor["_rank_score"] or 0.0) + float(penalty)
                    )
            else:
                if not card.get("score"):
                    card["score"] = float(anchor.get("score", 0.0) or 0.0)
                if "_rank_score" in anchor and "_rank_score" not in card:
                    card["_rank_score"] = anchor["_rank_score"]
            if "_sort_time" in anchor and "_sort_time" not in card:
                card["_sort_time"] = anchor["_sort_time"]
            for child in card.get("data", {}).get("items") or ():
                if isinstance(child, dict) and (penalty < 0 or not child.get("score")):
                    child["score"] = card["score"]
        elif penalty < 0:
            card["score"] = _penalized_roundup_score(card, None, penalty)
            for child in card.get("data", {}).get("items") or ():
                if isinstance(child, dict):
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
    # Track each post-opening round-up's natural unpenalized turn before
    # ordering unpenalized round-ups first so any penalized lesser-soccer card
    # computes its penalized score from its true pre-penalty seat anchor rather
    # than whichever tail item happens to follow all later round-ups.
    post_opening_turns = [
        (idx, r_item, _roundup_lesser_soccer_penalty(r_item))
        for idx, r_item in enumerate(post_opening_roundups)
    ]
    post_opening_ordered = [
        *[t for t in post_opening_turns if t[2] == 0],
        *[t for t in post_opening_turns if t[2] < 0],
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
    for natural_turn, r_item, lesser_soccer_pen in post_opening_ordered:
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
        anchor_override: Optional[Mapping[str, Any]] = None
        if lesser_soccer_pen < 0 and result:
            anchor_seat = (
                earliest_post_opening_seat
                if earliest_post_opening_seat is not None
                else floor_idx + (2 * natural_turn)
            )
            anchor_idx = min(max(floor_idx, anchor_seat), len(result) - 1)
            anchor_override = result[anchor_idx]
            pen_score = _penalized_roundup_score(r_item, anchor_override, lesser_soccer_pen)
            desired_idx = _score_demoted_seat_index(result, floor_idx, pen_score)
        effective_floor = (
            max(floor_idx, desired_idx)
            if lesser_soccer_pen < 0
            else max(
                floor_idx,
                page_window
                if (is_sibling_card and len(seated_sibling_roundups) >= MAX_SIBLING_FAMILY_IN_TOP_20)
                else floor_idx,
            )
        )
        non_adj_idx = _find_non_adjacent_roundup_seat(
            result,
            desired_idx,
            floor_idx=effective_floor,
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

        card = _hydrate_card_at_seat(
            r_item,
            target_idx,
            penalty=lesser_soccer_pen,
            anchor_override=anchor_override,
        )

        result.insert(target_idx, card)
        if lesser_soccer_pen == 0 and target_idx > max_inserted_idx:
            max_inserted_idx = target_idx
        if is_sibling_card and target_idx < page_window:
            seated_sibling_roundups.append(card)
        if lesser_soccer_pen == 0:
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
    apply_opening_mix: bool = False,
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
        producers = [p for p in producers if not _is_preview_producer(p)]
    if not producers:
        return items
    # Keep public producers strictly ahead of preview producers so a slow or
    # cold preview set can never consume the public stage budget or trigger
    # the public all-or-nothing drop.
    if include_preview:
        public_producers = [p for p in producers if not _is_preview_producer(p)]
        preview_producers = [p for p in producers if _is_preview_producer(p)]
    else:
        public_producers = producers
        preview_producers = []
    now_ts, _ = _normalize_roundup_now(now)
    # #12529: Skip disabled and out-of-window producers up front so seasonal
    # retired producers never burn stage budget or trigger false `dropped_no_copy`.
    public_producers = [
        p
        for p in public_producers
        if (p.enabled is None or p.enabled())
        and (p.valid_from is None or now_ts >= p.valid_from)
        and (p.valid_until is None or now_ts < p.valid_until)
    ]
    machinery_producers = [
        p
        for p in public_producers
        if _is_machinery_producer_slug(p.slug) and (p.enabled is None or p.enabled())
    ]
    machinery_incomplete = False
    # #12529: Evaluate intentionally uncacheable producers (e.g. `yardstick_pair`,
    # rule `cache == "none"`) first so cached round-ups can never starve them into
    # `dropped_no_copy`, while placing every card back into `public_producers` order.
    def _is_no_cache_producer(prod: RoundupProducer) -> bool:
        rcfg = prod.rule if isinstance(prod.rule, Mapping) else {}
        return rcfg.get("cache") == "none" or rcfg.get("producer") == "yardstick_pair"

    indexed_public = list(enumerate(public_producers))
    eval_order = [
        *(pair for pair in indexed_public if _is_no_cache_producer(pair[1])),
        *(pair for pair in indexed_public if not _is_no_cache_producer(pair[1])),
    ]
    slot_results: dict[int, dict[str, Any]] = {}
    # One batched Redis MGET up front hydrates every warm machinery grouping
    # and standing round-up across a cold dyno restart in a single round-trip
    # instead of 20+ sequential Redis GETs and serial 0.5s DB timeouts.
    public_prefetched, public_shared_ok = await _prefetch_shared_roundup_entries(
        public_producers, db
    )
    for loop_idx, (orig_idx, producer) in enumerate(eval_order):
        is_mach_prod = _is_machinery_producer_slug(producer.slug) and (
            producer.enabled is None or producer.enabled()
        )
        pref_val = public_prefetched.get(producer.slug)
        if not is_mach_prod:
            from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSess

            sr_key = (
                producer.slug,
                "live" if isinstance(db, _AsyncSess) else id(db),
            )
            local_sr_ts = _roundup_settled_retired_local.get(sr_key)
            if (
                local_sr_ts is not None
                and 0.0 <= (now_ts - float(local_sr_ts)) < ROUNDUP_SETTLED_RETIRED_TTL_S
            ):
                continue
            if public_shared_ok and pref_val:
                try:
                    raw_pref = json.loads(
                        pref_val.decode("utf-8")
                        if isinstance(pref_val, (bytes, bytearray))
                        else pref_val
                    )
                    if (
                        isinstance(raw_pref, dict)
                        and raw_pref.get("settled_retired") is True
                        and isinstance(raw_pref.get("built_at"), (int, float))
                    ):
                        pref_built_at = float(raw_pref["built_at"])
                        pref_ttl = float(raw_pref.get("ttl_s") or ROUNDUP_CACHE_TTL_S)
                        is_pref_long = bool(
                            raw_pref.get("long_skip") is True
                            or pref_ttl >= ROUNDUP_SETTLED_RETIRED_TTL_S
                        )
                        if 0.0 <= (now_ts - pref_built_at) < pref_ttl:
                            if is_pref_long and pref_ttl >= ROUNDUP_SETTLED_RETIRED_TTL_S:
                                _roundup_settled_retired_local[sr_key] = pref_built_at
                            else:
                                _roundup_settled_retired_local.pop(sr_key, None)
                            continue
                        if not is_pref_long:
                            _roundup_settled_retired_local.pop(sr_key, None)
                except Exception:  # noqa: BLE001 — fail open to normal evaluation
                    pass
        elapsed = time.perf_counter() - started
        remaining = stage_budget - elapsed
        if remaining <= 0:
            kept_after_budget = 0
            quiet_after_budget = 0
            dropped_after_budget = 0
            kept_slugs: list[str] = []
            dropped_slugs: list[str] = []
            rem_entries = eval_order[loop_idx:]
            rem_producers = [p for _, p in rem_entries]
            if public_shared_ok:
                prefetched_shared, shared_read_ok = public_prefetched, True
            else:
                prefetched_shared, shared_read_ok = await _prefetch_shared_roundup_entries(
                    rem_producers, db
                )
            for rem_idx, rem_producer in rem_entries:
                quiet_meta: dict[str, Any] = {}
                last_good = await _load_last_good_roundup_copy(
                    rem_producer,
                    db,
                    now=now,
                    local_only=False,
                    fail_closed_on_shared_error=True,
                    prefetched_shared=prefetched_shared.get(rem_producer.slug),
                    shared_read_ok=shared_read_ok,
                    quiet_out=quiet_meta,
                )
                if last_good is not None:
                    fi_lg, _cp_lg, _age_lg, _keep_lg = last_good
                    slot_results[rem_idx] = fi_lg
                    kept_after_budget += 1
                    kept_slugs.append(rem_producer.slug)
                    _record_roundup_read_failure(
                        rem_producer.slug,
                        kept_last_good=True,
                        reason="budget_exhausted",
                        now=now_ts,
                    )
                elif quiet_meta.get("clean_empty") is True:
                    # #13184/#13186 follow-up: an unexpired quiet mark means the
                    # grouping is properly empty, not missing/incomplete.
                    quiet_after_budget += 1
                    _record_roundup_read_failure(
                        rem_producer.slug,
                        kept_last_good=False,
                        had_nothing_to_show=True,
                        reason="budget_exhausted",
                        now=now_ts,
                    )
                elif quiet_meta.get("nothing_to_show") is True and not (
                    _is_machinery_producer_slug(rem_producer.slug)
                    and (rem_producer.enabled is None or rem_producer.enabled())
                ):
                    # Standing round-up cleanly had nothing to show — split from
                    # dropped_no_copy so dropped_no_copy alarms only on lost cards.
                    quiet_after_budget += 1
                    _record_roundup_read_failure(
                        rem_producer.slug,
                        kept_last_good=False,
                        had_nothing_to_show=True,
                        reason="budget_exhausted",
                        now=now_ts,
                    )
                else:
                    if _is_machinery_producer_slug(rem_producer.slug) and (
                        rem_producer.enabled is None or rem_producer.enabled()
                    ):
                        machinery_incomplete = True
                    dropped_after_budget += 1
                    dropped_slugs.append(rem_producer.slug)
                    _record_roundup_read_failure(
                        rem_producer.slug,
                        kept_last_good=False,
                        reason="budget_exhausted",
                        now=now_ts,
                    )
            stats_10m = get_roundup_read_failure_stats_10m(now=now_ts)
            logger.warning(
                "Discover round-up stage budget exhausted after %d/%d producers "
                "(budget_seconds=%.3f, stage_budget=%.3f, produced=%d, "
                "kept_last_good=%d, quiet=%d, dropped_no_copy=%d, failed_10m=%d, "
                "dropped_10m=%d, nothing_to_show_10m=%d, kept_slugs=%s, dropped_slugs=%s)",
                loop_idx,
                len(eval_order),
                budget_seconds,
                stage_budget,
                len(slot_results),
                kept_after_budget,
                quiet_after_budget,
                dropped_after_budget,
                stats_10m["failed"],
                stats_10m["dropped_no_copy"],
                stats_10m["had_nothing_to_show"],
                kept_slugs[:10],
                dropped_slugs[:10],
            )
            break
        per_timeout = min(remaining, ROUNDUP_PRODUCER_TIMEOUT_SECONDS)
        # On a fresh process after a restart (`_roundup_local_cache` empty for
        # this slug), let standing round-ups reuse their warm shared Redis copy
        # immediately rather than burning DB budget and dropping cards.
        standing_cold_restart = (
            not is_mach_prod
            and public_shared_ok
            and pref_val is not None
            and (producer.slug, "live") not in _roundup_local_cache
        )
        try:
            eval_coro = evaluate_roundup_producer(
                producer,
                db,
                now=now,
                allow_stale=(
                    _is_machinery_producer_slug(producer.slug)
                    or standing_cold_restart
                ),
                prefetched_shared=pref_val if public_shared_ok else _PREFETCH_UNSET,
                shared_read_ok=public_shared_ok,
            )
            feed_item, container_payload = await asyncio.wait_for(
                eval_coro,
                timeout=per_timeout,
            )
        except asyncio.TimeoutError:
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "roundup_containers: rollback after timeout failed for %s",
                        producer.slug,
                    )
            timeout_quiet: dict[str, Any] = {}
            last_good = await _load_last_good_after_failure(
                producer,
                db,
                now=now,
                pref_val=pref_val,
                public_shared_ok=public_shared_ok,
                quiet_out=timeout_quiet,
            )
            if last_good is not None:
                fi_lg, _cp_lg, age_lg, keep_lg = last_good
                slot_results[orig_idx] = fi_lg
                stats_10m = _record_roundup_read_failure(
                    producer.slug,
                    kept_last_good=True,
                    reason="timeout",
                    now=now_ts,
                )
                logger.warning(
                    "Discover round-up read timed out for %s; kept last good copy "
                    "(age=%.1fs, keep_s=%.0f, failed_10m=%d, kept_10m=%d, dropped_10m=%d)",
                    producer.slug,
                    age_lg,
                    keep_lg,
                    stats_10m["failed"],
                    stats_10m["kept_last_good"],
                    stats_10m["dropped_no_copy"],
                )
                continue
            if timeout_quiet.get("clean_empty") is True or (
                timeout_quiet.get("nothing_to_show") is True and not is_mach_prod
            ):
                stats_10m = _record_roundup_read_failure(
                    producer.slug,
                    kept_last_good=False,
                    had_nothing_to_show=True,
                    reason="timeout",
                    now=now_ts,
                )
                logger.info(
                    "Discover round-up read timed out for %s; prior copy had nothing to show "
                    "(reason=%s, nothing_to_show_10m=%d, dropped_10m=%d)",
                    producer.slug,
                    timeout_quiet.get("reason") or "nothing_to_show",
                    stats_10m["had_nothing_to_show"],
                    stats_10m["dropped_no_copy"],
                )
                continue
            if is_mach_prod:
                machinery_incomplete = True
            if (
                per_timeout >= ROUNDUP_PRODUCER_TIMEOUT_SECONDS
                and not _is_machinery_producer_slug(producer.slug)
            ):
                await _cache_roundup_timeout_refusal(producer, db, ts=now_ts)
            stats_10m = _record_roundup_read_failure(
                producer.slug,
                kept_last_good=False,
                reason="timeout",
                now=now_ts,
            )
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards "
                "(no last good copy under keep-time, failed_10m=%d, kept_10m=%d, dropped_10m=%d)",
                producer.slug,
                stats_10m["failed"],
                stats_10m["kept_last_good"],
                stats_10m["dropped_no_copy"],
                exc_info=True,
            )
            continue
        except Exception:
            if hasattr(db, "rollback") and callable(db.rollback):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "roundup_containers: rollback after error failed for %s",
                        producer.slug,
                    )
            error_quiet: dict[str, Any] = {}
            last_good = await _load_last_good_after_failure(
                producer,
                db,
                now=now,
                pref_val=pref_val,
                public_shared_ok=public_shared_ok,
                quiet_out=error_quiet,
            )
            if last_good is not None:
                fi_lg, _cp_lg, age_lg, keep_lg = last_good
                slot_results[orig_idx] = fi_lg
                stats_10m = _record_roundup_read_failure(
                    producer.slug,
                    kept_last_good=True,
                    reason="error",
                    now=now_ts,
                )
                logger.warning(
                    "Discover round-up read errored for %s; kept last good copy "
                    "(age=%.1fs, keep_s=%.0f, failed_10m=%d, kept_10m=%d, dropped_10m=%d)",
                    producer.slug,
                    age_lg,
                    keep_lg,
                    stats_10m["failed"],
                    stats_10m["kept_last_good"],
                    stats_10m["dropped_no_copy"],
                    exc_info=True,
                )
                continue
            if error_quiet.get("clean_empty") is True or (
                error_quiet.get("nothing_to_show") is True and not is_mach_prod
            ):
                stats_10m = _record_roundup_read_failure(
                    producer.slug,
                    kept_last_good=False,
                    had_nothing_to_show=True,
                    reason="error",
                    now=now_ts,
                )
                logger.info(
                    "Discover round-up read errored for %s; prior copy had nothing to show "
                    "(reason=%s, nothing_to_show_10m=%d, dropped_10m=%d)",
                    producer.slug,
                    error_quiet.get("reason") or "nothing_to_show",
                    stats_10m["had_nothing_to_show"],
                    stats_10m["dropped_no_copy"],
                )
                continue
            if is_mach_prod:
                machinery_incomplete = True
            stats_10m = _record_roundup_read_failure(
                producer.slug,
                kept_last_good=False,
                reason="error",
                now=now_ts,
            )
            logger.warning(
                "Discover round-up read failed for %s; keeping ordinary cards "
                "(no last good copy under keep-time, failed_10m=%d, kept_10m=%d, dropped_10m=%d)",
                producer.slug,
                stats_10m["failed"],
                stats_10m["kept_last_good"],
                stats_10m["dropped_no_copy"],
                exc_info=True,
            )
            continue
        if feed_item is not None and container_payload is not None:
            slot_results[orig_idx] = feed_item
    produced: list[dict[str, Any]] = [
        slot_results[idx] for idx in sorted(slot_results)
    ]

    # Goal Step 7 (#12288): all-or-nothing during cold-restart warm-up for PUBLIC
    # machinery groupings. If any registered public machinery grouping timed out,
    # errored, or was skipped by stage budget exhaustion, drop all partial public
    # machinery cards (standing round-ups stay untouched). Preview groupings run
    # separately below and never trigger this drop.
    if machinery_incomplete and machinery_producers:
        ready_mach = sum(
            1
            for it in produced
            if _is_machinery_roundup_item(it) and not _is_preview_roundup_item(it)
        )
        if ready_mach > 0:
            produced = [
                it
                for it in produced
                if not (_is_machinery_roundup_item(it) and not _is_preview_roundup_item(it))
            ]
            logger.warning(
                "Discover machinery groupings incomplete (%d/%d ready); serving none until all ready",
                ready_mach,
                len(machinery_producers),
            )

    # Best-effort preview pass (`machinery=preview`): serve every warm preview
    # copy first via batched MGET, then build cold preview sets under a bounded
    # preview budget. A slow or failing preview set is skipped without dropping
    # the six public groupings or any other preview set that built.
    if preview_producers:
        prefetched_preview, preview_shared_ok = await _prefetch_shared_roundup_entries(
            preview_producers, db
        )
        cold_preview_producers: list[RoundupProducer] = []
        for prev_prod in preview_producers:
            if prev_prod.enabled is not None and not prev_prod.enabled():
                continue
            prev_quiet: dict[str, Any] = {}
            warm_copy = await _load_last_good_roundup_copy(
                prev_prod,
                db,
                now=now,
                local_only=False,
                fail_closed_on_shared_error=True,
                prefetched_shared=prefetched_preview.get(prev_prod.slug),
                shared_read_ok=preview_shared_ok,
                quiet_out=prev_quiet,
            )
            if warm_copy is not None:
                fi_warm, _cp_warm, _age_warm, _keep_warm = warm_copy
                produced.append(fi_warm)
            elif prev_quiet.get("clean_empty") is True:
                continue
            else:
                cold_preview_producers.append(prev_prod)

        if cold_preview_producers:
            preview_started = time.perf_counter()
            preview_budget = min(
                max(0.0, float(budget_seconds) - (preview_started - started)),
                max(stage_cap, ROUNDUP_PREVIEW_STAGE_BUDGET_SECONDS),
            )
            for prev_prod in cold_preview_producers:
                prev_remaining = preview_budget - (time.perf_counter() - preview_started)
                if prev_remaining <= 0:
                    logger.warning(
                        "Discover preview grouping %s skipped (preview budget exhausted); "
                        "keeping built groupings",
                        prev_prod.slug,
                    )
                    break
                prev_timeout = min(
                    prev_remaining, ROUNDUP_PREVIEW_PRODUCER_TIMEOUT_SECONDS
                )
                try:
                    prev_fi, prev_cp = await asyncio.wait_for(
                        evaluate_roundup_producer(
                            prev_prod, db, now=now, allow_stale=True
                        ),
                        timeout=prev_timeout,
                    )
                except asyncio.TimeoutError:
                    if hasattr(db, "rollback") and callable(db.rollback):
                        try:
                            await db.rollback()
                        except Exception:  # noqa: BLE001
                            logger.debug(
                                "roundup_containers: rollback after preview timeout failed for %s",
                                prev_prod.slug,
                            )
                    logger.warning(
                        "Discover preview grouping %s timed out after %.2fs; "
                        "keeping public and built preview groupings",
                        prev_prod.slug,
                        prev_timeout,
                    )
                    continue
                except Exception:  # noqa: BLE001
                    if hasattr(db, "rollback") and callable(db.rollback):
                        try:
                            await db.rollback()
                        except Exception:  # noqa: BLE001
                            logger.debug(
                                "roundup_containers: rollback after preview error failed for %s",
                                prev_prod.slug,
                            )
                    logger.warning(
                        "Discover preview grouping %s failed on preview build; "
                        "keeping public and built preview groupings",
                        prev_prod.slug,
                        exc_info=True,
                    )
                    continue
                if prev_fi is not None and prev_cp is not None:
                    produced.append(prev_fi)

    if not produced:
        if apply_opening_mix:
            from app.utils.discover_opening_mix import apply_discover_opening_mix

            return apply_discover_opening_mix(items, now=now, page_window=page_window)
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
        if apply_opening_mix:
            from app.utils.discover_opening_mix import apply_discover_opening_mix

            return apply_discover_opening_mix(items, now=now, page_window=page_window)
        return items
    result = insert_roundup_feed_items(
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
    if apply_opening_mix:
        from app.utils.discover_opening_mix import apply_discover_opening_mix

        result = apply_discover_opening_mix(result, now=now, page_window=page_window)
    return result


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
        live_stale_ceiling_seconds,
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

    use_opening = bool(mach_base.get("opening_seating"))
    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    spliced_items = insert_roundup_feed_items(
        copy.deepcopy(base_items),
        produced,
        page_window=DISCOVER_COMPOSITION_WINDOW,
        now=now_dt,
        preserve_existing_roundups=True,
    )
    if use_opening:
        from app.utils.discover_opening_mix import apply_discover_opening_mix

        spliced_items = apply_discover_opening_mix(
            spliced_items,
            now=now_dt,
            page_window=DISCOVER_COMPOSITION_WINDOW,
        )
    for item in spliced_items:
        _publish_feed_item(item)

    base_age_origin = float(mach_base.get("age_origin") or now_ts)
    mach_age_origin = (
        min(base_age_origin, oldest_live_built_at)
        if oldest_live_built_at is not None
        else base_age_origin
    )
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
    mach_input_age_s = (
        max(0.0, float(now_ts) - float(mach_age_origin)) if mach_live else 0.0
    )
    m_ttl, m_stale_ttl = feed_response_cache_ttls(
        my_teams_only=False,
        identified=False,
        live=mach_live,
        oldest_artifact_age_s=mach_input_age_s,
        live_stale_ceiling_s=live_stale_ceiling_seconds(mach_base_body),
    )
    if mach_live and (m_ttl <= 0 or m_stale_ttl <= 0):
        return None
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

    def _hydrate_at(
        r_item: Mapping[str, Any],
        target_idx: int,
        *,
        penalty: int = 0,
        anchor_override: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        card = copy.deepcopy(dict(r_item))
        if result:
            anchor = (
                anchor_override
                if anchor_override is not None
                else (result[target_idx] if target_idx < len(result) else result[-1])
            )
            if penalty < 0:
                card["score"] = _penalized_roundup_score(card, anchor, penalty)
                if "_rank_score" in anchor and "_rank_score" not in card:
                    card["_rank_score"] = max(
                        0.0, float(anchor["_rank_score"] or 0.0) + float(penalty)
                    )
            else:
                if not card.get("score"):
                    card["score"] = float(anchor.get("score", 0.0) or 0.0)
                if "_rank_score" in anchor and "_rank_score" not in card:
                    card["_rank_score"] = anchor["_rank_score"]
            if "_sort_time" in anchor and "_sort_time" not in card:
                card["_sort_time"] = anchor["_sort_time"]
            for child in card.get("data", {}).get("items") or ():
                if isinstance(child, dict) and (penalty < 0 or not child.get("score")):
                    child["score"] = card["score"]
        elif penalty < 0:
            card["score"] = _penalized_roundup_score(card, None, penalty)
            for child in card.get("data", {}).get("items") or ():
                if isinstance(child, dict):
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
    # or first covered standalone card ONLY when it sits at or above where non-replacing
    # groupings would seat on their own (Fable 12:16 PM PT & 4:37 AM PT on #12288:
    # absorbing a far-down card like seat 95 never drags a grouping down to seat 95).
    pre_pass2_standing_last = max(
        (
            i
            for i, it in enumerate(result)
            if _is_roundup_bundle_card(it)
            and not _is_machinery_roundup_item(it)
            and _roundup_lesser_soccer_penalty(it) == 0
        ),
        default=-1,
    )
    own_seat_ceiling = max(initial_floor_idx, pre_pass2_standing_last + 2)
    for r_item in ordered_roundups:
        if _roundup_lesser_soccer_penalty(r_item) < 0:
            continue
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
                if r_id not in placed_rids and idx <= own_seat_ceiling:
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
                    if r_id not in placed_rids and idx <= own_seat_ceiling:
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
    # round-up (never counting already-placed machinery groupings or score-demoted
    # lesser-soccer round-ups!) with non-adjacent spacing so zero standing round-ups shift.
    unplaced = [r for r in ordered_roundups if r["data"].get("id") not in placed_rids]
    if unplaced:
        floor_idx = _opening_eligible_floor_index(result, seat_floor, now=now)
        last_standing_idx = max(
            (
                i
                for i, it in enumerate(result)
                if _is_roundup_bundle_card(it)
                and not _is_machinery_roundup_item(it)
                and _roundup_lesser_soccer_penalty(it) == 0
            ),
            default=-1,
        )
        next_desired = max(floor_idx, last_standing_idx + 2)
        for r_item in unplaced:
            lesser_soccer_pen = _roundup_lesser_soccer_penalty(r_item)
            desired_idx = min(next_desired, len(result))
            anchor_override = None
            if lesser_soccer_pen < 0 and result:
                anchor_idx = min(desired_idx, len(result) - 1)
                anchor_override = result[anchor_idx]
                pen_score = _penalized_roundup_score(r_item, anchor_override, lesser_soccer_pen)
                desired_idx = _score_demoted_seat_index(result, desired_idx, pen_score)
            non_adj = _find_non_adjacent_roundup_seat(
                result,
                desired_idx,
                floor_idx=desired_idx,
                candidate_item=r_item,
                page_window=page_window,
            )
            target_idx = non_adj if non_adj is not None else len(result)
            card = _hydrate_at(
                r_item,
                target_idx,
                penalty=lesser_soccer_pen,
                anchor_override=anchor_override,
            )
            result.insert(target_idx, card)
            if lesser_soccer_pen == 0:
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
    "fun_scout_set": (
        "app.utils.discover_fun_scout",
        "build_fun_scout_set_producer",
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
