"""A discovered ceremony's card and page use the same member set (#11935).

DISCOVER / TRUTH. Venue categories become sections and retain the shared market
cards. The source loader is supplied by the worker/snapshot consumer. Rendering
never fetches a venue or calls a model, and registration remains the caller's.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select, tuple_

from app.services.awards_occasion_source import AwardsOccasionSourceError
from app.utils.awards_occasion_finder import (
    AwardsOccasion,
    OccasionDiscovery,
    validate_awards_selector,
)
from app.utils.container_presentation import MEMBER_MARKET, market_destination

if TYPE_CHECKING:
    from app.utils.roundup_containers import (
        RoundupMembers,
        RoundupProducer,
        RoundupRefusal,
    )


def awards_ceremony_slug(label: str) -> str:
    validate_awards_selector(
        {"evidence": "primary_rules_ordinal_awards", "label": label}
    )
    return "roundup-awards-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def awards_ceremony_definition(selector: Mapping[str, str]) -> dict[str, Any]:
    """Emit one reviewable definition from the finder's source-established label."""
    validate_awards_selector(selector)
    label = selector["label"]
    return {
        "slug": awards_ceremony_slug(label),
        "membership": "computed-produced",
        "kind": "roundup",
        "name": label,
        "category": "entertainment",
        "section_title": "Awards markets",
        "footer": "Ceremony date unknown · Completion unknown",
        "relations": ["same_event"],
        "level": "member",
        "enabled": False,
        "rule": {
            "producer": "awards_ceremony",
            "selector": dict(selector),
            "trigger": "market_availability",
        },
    }


async def _ceremony_members(
    db: Any, occasion: AwardsOccasion
) -> RoundupMembers | RoundupRefusal:
    from app.models.models import FuturesMarket
    from app.routes.containers import _hydrate_market_cards
    from app.utils.roundup_containers import RoundupMembers, RoundupRefusal

    if not occasion.events:
        return RoundupRefusal(((occasion.label, "occasion_empty"),))
    keys = [(event.provider, event.event_id) for event in occasion.events]
    provider_event = case(
        (
            FuturesMarket.source == "kalshi",
            func.coalesce(
                FuturesMarket.market_metadata["kalshi_event_ticker"].astext,
                FuturesMarket.external_id,
            ),
        ),
        (
            FuturesMarket.source == "polymarket",
            FuturesMarket.market_metadata["polymarket_event_id"].astext,
        ),
    )
    rows = (
        await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.source,
                provider_event,
                FuturesMarket.mutually_exclusive,
            )
            .where(tuple_(FuturesMarket.source, provider_event).in_(keys))
            .order_by(FuturesMarket.id)
        )
    ).all()
    # Copy the identity facts before hydration can encounter a rollback.
    facts = [(int(row[0]), str(row[1]), str(row[2]), row[3]) for row in rows]
    by_event = defaultdict(list)
    for market_id, provider, event_id, exclusive in facts:
        by_event[(provider, event_id)].append((market_id, exclusive))
    missing = [key for key in keys if not by_event[key]]
    if missing:
        return RoundupRefusal([(*key, "stored_category_missing") for key in missing])

    cards, _, failures = await _hydrate_market_cards(db, [fact[0] for fact in facts])
    unavailable = sorted(
        {fact[0] for fact in facts if fact[0] not in cards}
        | {market_id for (kind, market_id) in failures if kind == MEMBER_MARKET}
    )
    if unavailable:
        return RoundupRefusal(
            [("market", market_id, "card_unavailable") for market_id in unavailable]
        )

    members = []
    sections = []
    for event in occasion.events:
        category_members = []
        for market_id, exclusive in by_event[(event.provider, event.event_id)]:
            card = dict(cards[market_id])
            card["mutually_exclusive"] = exclusive
            category_members.append(
                {
                    "type": MEMBER_MARKET,
                    "id": market_id,
                    "destination": market_destination(market_id),
                    "card": card,
                    "event_id": None,
                }
            )
        members.extend(category_members)
        sections.append(
            {
                "class": f"awards-{event.provider}-{event.event_id.lower()}",
                "title": event.title or "Category unknown",
                "layout": "field",
                "members": category_members,
            }
        )

    label = occasion.label
    story_key = "ceremony:" + awards_ceremony_slug(label)
    feed_item = {
        "type": "bundle",
        "score": 0,
        "headline": label,
        "reason": label,
        "data": {
            "id": story_key,
            "title": label,
            "kind": "theme",
            "story_key": story_key,
            "shared_question": None,
            "item_count": len(members),
            "member_ids": [member["id"] for member in members],
            "relations": ["same_event"],
            "level": "member",
        },
    }
    return RoundupMembers(
        members,
        sections=sections,
        title=label,
        footer="Ceremony date unknown · Completion unknown",
        feed_item=feed_item,
    )


def build_awards_ceremony_producer(
    definition: Mapping[str, Any],
    *,
    load_occasions: Callable[[Any], Awaitable[OccasionDiscovery]] | None = None,
) -> RoundupProducer:
    """Build both presentations from a selector and a current evidence loader."""
    from app.services.awards_occasion_snapshot import read_cached_awards_occasions
    from app.utils.roundup_containers import (
        RoundupProducer,
        RoundupRefusal,
        validate_roundup_definition,
    )

    # Retain the saved-preview API. The folder loader supplies a full definition.
    if "rule" not in definition:
        definition = awards_ceremony_definition(definition)
        definition.pop("enabled")
    definition = validate_roundup_definition(deepcopy(definition))
    rule = definition["rule"]
    if rule.get("producer") != "awards_ceremony":
        raise ValueError("Expected the awards_ceremony producer kind")
    selector = rule.get("selector")
    validate_awards_selector(selector)
    if (
        definition["slug"] != awards_ceremony_slug(selector["label"])
        or definition.get("name") != selector["label"]
        or definition["relations"] != ["same_event"]
        or definition["level"] != "member"
    ):
        raise ValueError(
            "A ceremony definition must retain its source identity and member relation"
        )
    if "enabled" in definition and not isinstance(definition["enabled"], bool):
        raise ValueError("Ceremony definition enabled must be boolean")
    parameters = dict(selector)
    loader = load_occasions or read_cached_awards_occasions

    async def produce(db: Any) -> RoundupMembers | RoundupRefusal:
        try:
            discovery = await loader(db)
        except AwardsOccasionSourceError as error:
            return RoundupRefusal((("source", str(error)),))
        occasion = next(
            (row for row in discovery.occasions if row.selector == parameters), None
        )
        if occasion is None:
            return RoundupRefusal(((parameters["label"], "occasion_unavailable"),))
        return await _ceremony_members(db, occasion)

    return RoundupProducer(
        slug=awards_ceremony_slug(parameters["label"]),
        name=parameters["label"],
        kind="roundup",
        category="entertainment",
        section_title="Awards markets",
        footer="Ceremony date unknown · Completion unknown",
        produce=produce,
        rule=dict(rule),
        relations=definition["relations"],
        level=definition["level"],
        story_key="ceremony:" + awards_ceremony_slug(parameters["label"]),
        enabled=(lambda: definition["enabled"]) if "enabled" in definition else None,
    )
