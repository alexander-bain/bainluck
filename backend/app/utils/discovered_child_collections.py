"""Automatic discovery and read-time serving of child collections from event/theme hubs (#11340).

PILLARS: DISCOVER / MATCHING / TRUTH / FORMATTING
SHIP: Readers open useful, automatically discovered child collections from a broad event hub
(such as Oscars Nominations or a recurring multi-category film like The Odyssey) and return via
Back without losing scroll/context, while sparse or unsupported subgroups stay inline sections.

Switched OFF for public readers by default via ``EVENT_HUB_CHILD_DISCOVERY_ENABLED`` (admin
previewers can inspect live hubs and child pages before Alex flips the switch).
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Mapping, Optional, Sequence

from fastapi import HTTPException

from app.services.paired_metric_register import fold_outcome_key
from app.utils.container_corrections import (
    READ_EMPTY,
    READ_PUBLISHED,
    READ_UNAVAILABLE,
    read_published,
)
from app.utils.container_presentation import (
    MEMBER_MARKET,
    container_destination,
    market_destination,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    ensure_optional_roundup_candidates,
    evaluate_roundup_producer,
    roundup_container_id,
    roundup_revision,
)

MIN_CLASS_CHILD_MARKETS = 6
MIN_PARENT_TITLE_SIBLINGS = 3
MIN_SUBJECT_CHILD_MARKETS = 6
MAX_SUBJECT_CHILDREN = 3
MIN_MENTION_CHILD_MARKETS = 4

_GENERIC_OUTCOME_RE = re.compile(
    r"^(?:yes|no|other|any\s+other|field|none(?:\s+of\s+the\s+above)?|someone\s+else|tbd|tie|draw)$",
    re.IGNORECASE,
)
_NUMERIC_BUCKET_RE = re.compile(
    r"^(?:above|below|over|under|at\s+least|more\s+than|fewer\s+than|before|after|\d+(?:\.\d+)?(?:\s*[-–+%]|\s*(?:bps|or\s+more|or\s+fewer))?)\b",
    re.IGNORECASE,
)
_MENTION_TITLE_RE = re.compile(
    r"\b(?:mention(?:ed|s)?|what\s+will\s+.+\s+say|acceptance\s+speech(?:es)?|monologue\s+mention)\b",
    re.IGNORECASE,
)
_SLUG_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_CHILD_SLUG_RE = re.compile(
    r"^(?P<parent>ai|oscars-\d{4})-(?:(?P<kind>nominations|mentions)|subject-(?P<subject>[a-z0-9]+(?:-[a-z0-9]+)*))$"
)


def event_hub_child_discovery_enabled() -> bool:
    """True only when explicitly turned on; default OFF for public readers."""
    return os.getenv("EVENT_HUB_CHILD_DISCOVERY_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def subject_to_child_token(name: str) -> str:
    folded = fold_outcome_key(name) or name.lower()
    return _SLUG_TOKEN_RE.sub("-", folded).strip("-")[:64].strip("-")


def parse_discovered_child_slug(slug: str) -> Optional[tuple[str, str, Optional[str]]]:
    """Return ``(parent_slug, kind, subject_token)`` if ``slug`` is a discovered child slug."""
    if not isinstance(slug, str) or len(slug) > 200:
        return None
    m = _CHILD_SLUG_RE.match(slug.strip())
    if not m:
        return None
    parent_slug = m.group("parent")
    if m.group("kind"):
        return parent_slug, m.group("kind"), None
    subj = m.group("subject")
    if not subj:
        return None
    return parent_slug, "subject", subj


def is_discovered_child_collection_slug(slug: str) -> bool:
    return parse_discovered_child_slug(slug) is not None


def _parent_display_name(parent_slug: str, header_name: Optional[str] = None) -> str:
    if header_name and str(header_name).strip():
        return str(header_name).strip()
    if parent_slug == "ai":
        return "AI"
    m = re.match(r"^oscars-(\d{4})$", parent_slug)
    if m:
        return f"Oscars {m.group(1)}"
    return parent_slug.replace("-", " ").title()


def _excluded_unsafe_subject_tokens() -> set[str]:
    """Exclude horror (TMDB genre 27) and documentary-crime ({99, 80}) subjects (#12850)."""
    import json
    from pathlib import Path

    reg_path = Path(__file__).resolve().parents[2] / "data" / "groupings" / "paired_metric_register.json"
    blocked: set[str] = set()
    if not reg_path.exists():
        return blocked
    try:
        raw = json.loads(reg_path.read_text(encoding="utf-8"))
        for pset in (raw.get("sets") or {}).values():
            if not isinstance(pset, Mapping):
                continue
            for entry in pset.get("entries") or ():
                if not isinstance(entry, Mapping):
                    continue
                art = entry.get("art") if isinstance(entry.get("art"), Mapping) else {}
                genres = set(art.get("genre_ids") or ())
                if art.get("adult") is True or 27 in genres or {99, 80}.issubset(genres):
                    tok = subject_to_child_token(str(entry.get("subject") or ""))
                    if tok:
                        blocked.add(tok)
    except Exception:
        return blocked
    return blocked


def _card_is_open_and_priced(card: Mapping[str, Any]) -> bool:
    status = str(card.get("status") or "").strip().lower()
    if status not in {"open", "active"}:
        return False
    outs = card.get("top_outcomes") or card.get("outcomes") or ()
    return any(
        isinstance(o, Mapping)
        and isinstance(o.get("probability"), (int, float))
        and 0.0 < float(o["probability"]) < 1.0
        for o in outs
    )


def _valid_subject_outcomes(card: Mapping[str, Any], blocked_tokens: set[str]) -> list[tuple[str, str]]:
    """Return ``[(subject_token, display_name)]`` for real named contenders in an open market."""
    outs = card.get("top_outcomes") or card.get("outcomes") or ()
    seen_tokens: set[str] = set()
    results: list[tuple[str, str]] = []
    for o in outs:
        if not isinstance(o, Mapping):
            continue
        prob = o.get("probability")
        if not isinstance(prob, (int, float)) or not (0.0 < float(prob) < 1.0):
            continue
        raw_name = str(o.get("name") or "").strip()
        if not raw_name or len(raw_name) < 2:
            continue
        if _GENERIC_OUTCOME_RE.match(raw_name) or _NUMERIC_BUCKET_RE.match(raw_name):
            continue
        tok = subject_to_child_token(raw_name)
        if not tok or len(tok) < 2 or tok in blocked_tokens or tok in seen_tokens:
            continue
        seen_tokens.add(tok)
        results.append((tok, raw_name))
    return results


def discover_children_from_admitted_inventory(
    parent_slug: str,
    parent_name: str,
    own_members: Sequence[Mapping[str, Any]],
    market_cards: Mapping[int, Mapping[str, Any]],
    *,
    category: str = "entertainment",
) -> list[dict[str, Any]]:
    """Pure automatic child-collection discovery over a parent hub's admitted members.

    Never relies on hand-maintained member lists or loose title similarity:
    1. Admitted ``advancement`` class graduates to ``{parent_slug}-nominations`` only when
       ``>= MIN_CLASS_CHILD_MARKETS`` open trading nomination markets AND
       ``>= MIN_PARENT_TITLE_SIBLINGS`` open title markets exist on the parent hub.
    2. Named contender subjects graduate to ``{parent_slug}-subject-{token}`` only when the
       exact contender appears as a priced outcome across ``>= MIN_SUBJECT_CHILD_MARKETS``
       distinct open markets spanning ``>= 2`` markets/categories on the parent hub.
    3. Coherent ceremony-mention markets graduate to ``{parent_slug}-mentions`` only when
       ``>= MIN_MENTION_CHILD_MARKETS`` open trading mention markets exist in the admitted set.
    """
    blocked = _excluded_unsafe_subject_tokens()
    open_rows: list[tuple[int, str, Mapping[str, Any]]] = []
    for m in own_members:
        if m.get("type") != MEMBER_MARKET:
            continue
        mid = int(m["id"])
        card = market_cards.get(mid)
        if card is None or not _card_is_open_and_priced(card):
            continue
        cls = str(m.get("class") or "unclassified")
        open_rows.append((mid, cls, card))

    if not open_rows:
        return []

    title_rows = [r for r in open_rows if r[1] == "title"]
    adv_rows = [r for r in open_rows if r[1] == "advancement"]
    mention_rows = [
        r for r in open_rows if _MENTION_TITLE_RE.search(str(r[2].get("name") or ""))
    ]

    discovered: list[dict[str, Any]] = []

    # 1. Nominations subgroup (admitted advancement class)
    if len(adv_rows) >= MIN_CLASS_CHILD_MARKETS and len(title_rows) >= MIN_PARENT_TITLE_SIBLINGS:
        c_slug = f"{parent_slug}-nominations"
        discovered.append(
            {
                "id": roundup_container_id(c_slug),
                "slug": c_slug,
                "name": f"{parent_name} · Nominations ({len(adv_rows)} markets)",
                "kind": "roundup",
                "category": category,
                "status": "open",
                "publication_state": "published",
                "member_count": len(adv_rows),
                "cross_listed_in_parent": True,
                "discovery_kind": "admitted_class_advancement",
                "edition": None,
                "destination": container_destination(c_slug),
            }
        )

    # 2. Multi-category recurring subject subgroups (e.g., The Odyssey across categories)
    by_subject_mids: dict[str, list[int]] = defaultdict(list)
    by_subject_classes: dict[str, set[str]] = defaultdict(set)
    by_subject_label: dict[str, str] = {}
    for mid, cls, card in open_rows:
        for tok, display_name in _valid_subject_outcomes(card, blocked):
            by_subject_mids[tok].append(mid)
            by_subject_classes[tok].add(cls)
            if tok not in by_subject_label or (
                display_name[0].isupper() and not by_subject_label[tok][0].isupper()
            ):
                by_subject_label[tok] = display_name

    qualifying_subjects: list[tuple[int, str, str]] = []
    for tok, mids in by_subject_mids.items():
        unique_mids = sorted(set(mids))
        if len(unique_mids) >= MIN_SUBJECT_CHILD_MARKETS and (
            len(by_subject_classes[tok]) >= 2 or len(unique_mids) >= MIN_SUBJECT_CHILD_MARKETS + 2
        ):
            qualifying_subjects.append((len(unique_mids), tok, by_subject_label[tok]))

    qualifying_subjects.sort(key=lambda item: (-item[0], item[2].casefold()))
    for m_count, tok, label in qualifying_subjects[:MAX_SUBJECT_CHILDREN]:
        c_slug = f"{parent_slug}-subject-{tok}"
        discovered.append(
            {
                "id": roundup_container_id(c_slug),
                "slug": c_slug,
                "name": f"{label} ({m_count} markets)",
                "kind": "roundup",
                "category": category,
                "status": "open",
                "publication_state": "published",
                "member_count": m_count,
                "cross_listed_in_parent": True,
                "discovery_kind": "multi_category_subject",
                "subject": label,
                "edition": None,
                "destination": container_destination(c_slug),
            }
        )

    # 3. Coherent ceremony-mention subgroup (only when >= MIN_MENTION_CHILD_MARKETS open markets exist)
    if len(mention_rows) >= MIN_MENTION_CHILD_MARKETS:
        c_slug = f"{parent_slug}-mentions"
        discovered.append(
            {
                "id": roundup_container_id(c_slug),
                "slug": c_slug,
                "name": f"{parent_name} · Speech & Ceremony Mentions ({len(mention_rows)} markets)",
                "kind": "roundup",
                "category": category,
                "status": "open",
                "publication_state": "published",
                "member_count": len(mention_rows),
                "cross_listed_in_parent": True,
                "discovery_kind": "ceremony_mentions",
                "edition": None,
                "destination": container_destination(c_slug),
            }
        )

    return discovered


async def _discover_published_roundup_children(
    parent_slug: str, db: Any
) -> list[dict[str, Any]]:
    """Automatically surface enabled, published RoundupProducers whose parent_slug == parent_slug."""
    ensure_optional_roundup_candidates()
    children: list[dict[str, Any]] = []
    for c_slug, prod in sorted(ROUNDUP_PRODUCERS.items()):
        if getattr(prod, "parent_slug", None) != parent_slug:
            continue
        try:
            _feed_item, c_payload = await evaluate_roundup_producer(prod, db)
        except Exception:
            continue
        if not isinstance(c_payload, Mapping) or c_payload.get("state") != "published":
            continue
        m_count = int(c_payload.get("member_count") or 0)
        if m_count <= 0:
            continue
        c_header = c_payload.get("container") if isinstance(c_payload.get("container"), Mapping) else {}
        c_name = str(c_header.get("name") or prod.name or c_slug)
        children.append(
            {
                "id": roundup_container_id(c_slug),
                "slug": c_slug,
                "name": c_name,
                "kind": "roundup",
                "category": prod.category,
                "status": "open",
                "publication_state": "published",
                "member_count": m_count,
                "cross_listed_in_parent": True,
                "discovery_kind": "published_roundup_child",
                "edition": None,
                "destination": container_destination(c_slug),
            }
        )
    return children


async def attach_discovered_theme_children(
    hub_payload: dict[str, Any],
    db: Any,
    *,
    include_children: bool = True,
) -> dict[str, Any]:
    """Populate ``children`` on a published theme hub from its admitted snapshot membership."""
    if not include_children or hub_payload.get("state") != READ_PUBLISHED:
        hub_payload["children"] = []
        return hub_payload

    parent_slug = str(hub_payload.get("slug") or "").strip()
    if not parent_slug:
        return hub_payload

    from app.routes.containers import _hydrate_market_cards, _read_theme_snapshot

    published = await read_published(db, parent_slug)
    if published.state != READ_PUBLISHED:
        hub_payload["children"] = []
        return hub_payload

    snap = await _read_theme_snapshot(int(published.container_id), int(published.revision))
    shown_set = set(int(i) for i in (snap.get("shown_ids") or ())) if isinstance(snap, Mapping) else None

    own = [
        m
        for m in published.members
        if m.get("container_id") == published.container_id
        and m.get("type") == MEMBER_MARKET
        and (shown_set is None or int(m["id"]) in shown_set)
    ]
    if not own:
        hub_payload["children"] = []
        return hub_payload

    # Reuse cards already hydrated on page 1 so we only fetch remaining IDs in one batch.
    existing_cards: dict[int, Mapping[str, Any]] = {}
    for sec in hub_payload.get("sections") or ():
        for m in sec.get("members") or ():
            if m.get("type") == MEMBER_MARKET and isinstance(m.get("card"), Mapping):
                existing_cards[int(m["id"])] = m["card"]

    missing_ids = sorted({int(m["id"]) for m in own if int(m["id"]) not in existing_cards})
    if missing_ids:
        extra_cards, _ev_ids, _failed = await _hydrate_market_cards(db, missing_ids)
        existing_cards.update(extra_cards)

    header = hub_payload.get("container") if isinstance(hub_payload.get("container"), Mapping) else {}
    parent_name = _parent_display_name(parent_slug, header.get("name") if header else None)
    category = str((header or {}).get("category") or "entertainment")

    roundup_children = await _discover_published_roundup_children(parent_slug, db)
    auto_children = discover_children_from_admitted_inventory(
        parent_slug, parent_name, own, existing_cards, category=category
    )

    seen_slugs: set[str] = set()
    merged: list[dict[str, Any]] = []
    for ch in [*roundup_children, *auto_children]:
        cs = str(ch.get("slug") or "")
        if cs and cs not in seen_slugs:
            seen_slugs.add(cs)
            merged.append(ch)

    hub_payload["children"] = merged
    if isinstance(hub_payload.get("counts"), dict):
        hub_payload["counts"]["discovered_children_count"] = len(merged)
        hub_payload["counts"]["children_cross_listed"] = True
    return hub_payload


def _section_label_for_child_class(cls: str, child_kind: str) -> str:
    if child_kind == "nominations":
        return "Nomination Markets"
    if child_kind == "mentions":
        return "Speech & Ceremony Mentions"
    if cls == "title":
        return "Award Winner Markets"
    if cls == "advancement":
        return "Nomination Markets"
    return "Related Markets"


async def serve_discovered_child_collection(
    slug: str,
    db: Any,
    *,
    include_children: bool = True,
) -> dict[str, Any]:
    """Serve an automatically discovered child hub at ``/api/containers/{child_slug}``."""
    parsed = parse_discovered_child_slug(slug)
    if parsed is None:
        raise HTTPException(status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug})

    parent_slug, child_kind, subject_tok = parsed
    published = await read_published(db, parent_slug)
    if published.state == READ_UNAVAILABLE:
        raise HTTPException(status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug})

    # Withdrawn or unpublished parent: never leak any member or parent breadcrumb!
    if published.state not in (READ_PUBLISHED, READ_EMPTY):
        return {
            "state": published.state,
            "slug": slug,
            "revision": published.revision,
            "reason": published.reason,
            "edition": None,
            "container": None,
            "children": [],
            "sections": [],
            "member_count": 0,
            "withheld": [],
            "withheld_count": 0,
            "assembled": False,
        }

    from sqlalchemy import text
    from app.routes.containers import _hydrate_market_cards, _read_theme_snapshot

    snap = await _read_theme_snapshot(int(published.container_id), int(published.revision))
    shown_set = set(int(i) for i in (snap.get("shown_ids") or ())) if isinstance(snap, Mapping) else None

    own = [
        m
        for m in published.members
        if m.get("container_id") == published.container_id
        and m.get("type") == MEMBER_MARKET
        and (shown_set is None or int(m["id"]) in shown_set)
    ]
    all_ids = sorted({int(m["id"]) for m in own})
    market_cards, market_event_ids, _failed = await _hydrate_market_cards(db, all_ids)

    head_row = (
        await db.execute(
            text("SELECT name, category FROM containers WHERE id = :id"),
            {"id": published.container_id},
        )
    ).fetchone()
    parent_name = _parent_display_name(
        parent_slug, head_row[0] if head_row is not None else None
    )
    parent_category = str(head_row[1] if head_row is not None and head_row[1] else "entertainment")

    blocked = _excluded_unsafe_subject_tokens()
    if child_kind == "subject" and subject_tok in blocked:
        raise HTTPException(status_code=404, detail={"state": READ_UNAVAILABLE, "slug": slug})

    matched_rows: list[tuple[int, str, Mapping[str, Any]]] = []
    resolved_subject_label: Optional[str] = None
    title_open_count = 0

    for m in own:
        mid = int(m["id"])
        card = market_cards.get(mid)
        if card is None or not _card_is_open_and_priced(card):
            continue
        cls = str(m.get("class") or "unclassified")
        if cls == "title":
            title_open_count += 1
        if child_kind == "nominations":
            if cls == "advancement":
                matched_rows.append((mid, cls, card))
        elif child_kind == "mentions":
            if _MENTION_TITLE_RE.search(str(card.get("name") or "")):
                matched_rows.append((mid, cls, card))
        elif child_kind == "subject" and subject_tok:
            for tok, label in _valid_subject_outcomes(card, blocked):
                if tok == subject_tok:
                    matched_rows.append((mid, cls, card))
                    if resolved_subject_label is None or (
                        label[0].isupper() and not resolved_subject_label[0].isupper()
                    ):
                        resolved_subject_label = label
                    break

    # Enforce the exact same graduation thresholds as parent discovery so sparse subgroups 404.
    if child_kind == "nominations" and (
        len(matched_rows) < MIN_CLASS_CHILD_MARKETS or title_open_count < MIN_PARENT_TITLE_SIBLINGS
    ):
        raise HTTPException(status_code=404, detail={"state": "sparse_ungrouped", "slug": slug})
    if child_kind == "mentions" and len(matched_rows) < MIN_MENTION_CHILD_MARKETS:
        raise HTTPException(status_code=404, detail={"state": "sparse_ungrouped", "slug": slug})
    if child_kind == "subject":
        distinct_classes = {cls for _mid, cls, _c in matched_rows}
        if len(matched_rows) < MIN_SUBJECT_CHILD_MARKETS or (
            len(distinct_classes) < 2 and len(matched_rows) < MIN_SUBJECT_CHILD_MARKETS + 2
        ):
            raise HTTPException(status_code=404, detail={"state": "sparse_ungrouped", "slug": slug})

    # Group into clean ordered sections (title -> advancement -> other) without duplicating members
    class_order = ("title", "advancement", "side_question", "unclassified")
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_mids: set[int] = set()
    ordered_mids: list[int] = []
    for mid, cls, card in matched_rows:
        if mid in seen_mids:
            continue
        seen_mids.add(mid)
        ordered_mids.append(mid)
        bucket = cls if cls in class_order else "unclassified"
        by_class[bucket].append(
            {
                "type": MEMBER_MARKET,
                "id": mid,
                "destination": market_destination(mid),
                "card": card,
                "event_id": market_event_ids.get(mid),
            }
        )

    sections: list[dict[str, Any]] = []
    for cls in class_order:
        sec_members = by_class.get(cls) or []
        if not sec_members:
            continue
        sections.append(
            {
                "class": cls,
                "title": _section_label_for_child_class(cls, child_kind),
                "layout": "field",
                "count": len(sec_members),
                "members": sec_members,
            }
        )

    if child_kind == "nominations":
        child_title = f"{parent_name} · Nominations"
    elif child_kind == "mentions":
        child_title = f"{parent_name} · Speech & Ceremony Mentions"
    else:
        subj_label = resolved_subject_label or (subject_tok or "").replace("-", " ").title()
        child_title = f"{subj_label} · {parent_name}"

    total = len(ordered_mids)
    return {
        "state": "published",
        "slug": slug,
        "revision": roundup_revision(ordered_mids),
        "relations": ["same_event", "same_subject"] if child_kind == "subject" else ["same_event"],
        "level": "member",
        "reason": None,
        "edition": None,
        "container": {
            "id": roundup_container_id(slug),
            "slug": slug,
            "name": child_title,
            "kind": "roundup",
            "category": parent_category,
            "status": "open",
            "window_start": None,
            "window_end": None,
            "parent_container_id": int(published.container_id),
            "parent_slug": parent_slug,
            "parent_name": parent_name,
            "cross_listed_in_parent": True,
        },
        "parent": {
            "slug": parent_slug,
            "name": parent_name,
            "destination": container_destination(parent_slug),
        },
        "subtitle": f"Cross-listed from {parent_name} · {total} open markets",
        "sections": sections,
        "member_count": total,
        "withheld": [],
        "withheld_count": 0,
        "children": [] if include_children else [],
        "assembled": True,
    }
