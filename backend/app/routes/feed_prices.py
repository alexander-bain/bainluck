"""Fresh quote projection for exact leaves already painted in a Discover page.

TRUTH / #9515: a market invalidation refreshes its card without rebuilding or
reranking the feed. Missing/refused rows are explicit; they are not deletion
instructions. Clients retain their parent/bundle membership and ordering.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket
from app.services import get_db
from app.utils.aggregation import newest_source_reading_time
from app.utils.draw_priced_winner import printable_away
from app.utils.futures_market_snapshot import from_plain, outcome_observed_at, to_plain
from app.utils.hero_probability import resolve_hero
from app.utils.personalization import PersonalizationContext
from app.utils.proven_duplicates import (
    FoldedBlendView,
    folded_probability_sources_with_revision,
)
from app.utils.settledness import market_assigned_settled

router = APIRouter()
MAX_IDENTITIES = 50


def _ids(raw: str) -> list[int]:
    if not raw:
        return []
    if len(raw) > 1100:
        raise HTTPException(400, detail="invalid card identities")
    parts = raw.split(",")
    if len(parts) > MAX_IDENTITIES or any(
        not part.isascii() or not part.isdecimal() or not 0 < int(part) <= 2147483647
        for part in parts
    ):
        raise HTTPException(400, detail="invalid card identities")
    return list(dict.fromkeys(map(int, parts)))


def _iso(stamp):
    return stamp.isoformat() if stamp is not None else None


def _public(item):
    """Use the existing full leaf, with private scoring instrumentation removed."""
    if isinstance(item, dict):
        return {key: _public(value) for key, value in item.items() if not key.startswith("_")}
    if isinstance(item, list):
        return [_public(value) for value in item]
    return item


async def _event_cards(db, ids, now):
    from app.routes.feed import _score_events, enrich_event_team_data

    rows = (await db.execute(
        select(Event).options(selectinload(Event.sport)).where(Event.id.in_(ids))
    )).scalars().all()
    dispositions = {f"event-{eid}": "missing" for eid in ids}
    views, revisions = [], {}
    for event in rows:
        dispositions[f"event-{event.id}"] = "unresolved"
        sources, revision = await folded_probability_sources_with_revision(db, event)
        # A partial fold cannot order or cover a stream invalidation.
        if revision is None:
            continue
        views.append(FoldedBlendView(event, sources))
        revisions[event.id] = revision
    if not views:
        return [], dispositions
    items = await _score_events(
        db, now, None, PersonalizationContext(), price_refresh_events=views
    )
    by_id = {view.id: view for view in views}
    for item in items:
        data = item["data"]
        eid = data["id"]
        view = by_id[eid]
        hero = resolve_hero(view)
        data["blend_fold_revision"] = revisions[eid]
        data["hero_probability_observed_at"] = None
        if hero is not None:
            data["hero_probability_source"] = hero.source
            if hero.source == "blend":
                data["hero_probability_observed_at"] = _iso(
                    newest_source_reading_time(view, require_complete=True)
                )
            if hero.source != "settled":
                data["hero_probability_away"] = printable_away(
                    hero.away_probability, hero.home_probability,
                    view.sport.key if view.sport else None,
                )
        # Opening-only/final-unresolved has no fresh quote, even if history has
        # a last value. The item can clear its price with an explicit disposition.
        dispositions[f"event-{eid}"] = (
            "updated" if hero is not None and hero.source in ("blend", "settled")
            else "withheld"
        )
    await enrich_event_team_data(db, items)
    return items, dispositions


async def _market_cards(db, ids, now):
    from app.routes.feed import (
        _futures_feed_load_options,
        _score_futures,
        withheld_price_outcome_ids_for_markets,
    )

    rows = (await db.execute(
        select(FuturesMarket).options(*_futures_feed_load_options())
        .where(FuturesMarket.id.in_(ids))
    )).scalars().unique().all()
    dispositions = {f"futures-{mid}": "missing" for mid in ids}
    for market in rows:
        dispositions[f"futures-{market.id}"] = "unresolved"
    # The current feed serializer does not represent every assigned-settlement
    # shape. Keep that debt explicit, rather than describing a final as open.
    eligible = [market for market in rows if not market_assigned_settled(market)]
    if not eligible:
        return [], dispositions
    snapshots = from_plain(to_plain(
        eligible,
        withheld_by_market=await withheld_price_outcome_ids_for_markets(db, eligible),
    ))
    items = await _score_futures(
        db, now, None, PersonalizationContext(),
        preloaded_base={"markets": snapshots, "curator_ids": set()},
        price_refresh=True,
    )
    by_id = {market.id: market for market in snapshots}
    for item in items:
        data = item["data"]
        market = by_id[data["id"]]
        clocks = {str(outcome.id): _iso(outcome_observed_at(outcome))
                  for outcome in market.outcomes}
        data["outcome_observed_at"] = clocks
        data["external_id"] = market.external_id
        for outcome in data.get("top_outcomes") or []:
            outcome["price_observed_at"] = clocks.get(str(outcome["id"]))
        dispositions[f"futures-{market.id}"] = "updated"
    return items, dispositions


@router.get("/price-cards")
async def get_price_cards(
    response: Response,
    event_ids: str = "",
    market_ids: str = "",
    db: AsyncSession = Depends(get_db),
):
    events, markets = _ids(event_ids), _ids(market_ids)
    if not 0 < len(events) + len(markets) <= MAX_IDENTITIES:
        raise HTTPException(400, detail={"reason": "card_identity_bound", "max_ids": MAX_IDENTITIES})
    now = datetime.now(timezone.utc)
    items, dispositions = [], {}
    # One AsyncSession, serial statements. No cached feed, candidate discovery,
    # global invalidation, LLM or full-page composition is involved.
    if events:
        leaves, states = await _event_cards(db, events, now)
        items.extend(leaves)
        dispositions.update(states)
    if markets:
        leaves, states = await _market_cards(db, markets, now)
        items.extend(leaves)
        dispositions.update(states)
    order = {("event", eid): i for i, eid in enumerate(events)}
    order.update({("futures", mid): len(events) + i for i, mid in enumerate(markets)})
    items.sort(key=lambda item: order[(item["type"], item["data"]["id"])])
    response.headers["Cache-Control"] = "no-store"
    return {"items": _public(items), "dispositions": dispositions,
            "built_at": now.timestamp()}
