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
from app.utils.futures_market_snapshot import from_plain, to_plain
from app.utils.game_state import normalize_live_game_state
from app.utils.hero_probability import resolve_hero
from app.utils.personalization import PersonalizationContext
from app.utils.proven_duplicates import (
    FoldedBlendView,
    folded_probability_sources_with_revision,
)
from app.utils.settled_feed_price_card import settled_feed_price_card

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


def _outcome_clock(outcome):
    # Feed's cached age codec intentionally truncates to whole seconds. Ordering
    # two pushes must retain subsecond fidelity; use the already-loaded column,
    # not the age codec and never a market/request/publication timestamp.
    stamp = outcome.__dict__.get("last_updated")
    if not isinstance(stamp, datetime):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


def _live_state(event) -> dict | None:
    """``{"period", "game_clock"}`` as `/api/events/search` normalises them."""
    if event is None:
        return None
    sport_key = event.sport.key if event.sport else None
    period, clock = normalize_live_game_state(sport_key, event.period, event.game_clock)
    return {"period": period or None, "game_clock": clock or None}


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
    rows_by_id = {event.id: event for event in rows}
    for item in items:
        data = item["data"]
        eid = data["id"]
        view = by_id[eid]
        hero = resolve_hero(view)
        data["blend_fold_revision"] = revisions[eid]
        # #10090: the period and clock from the SAME row read as this card's
        # score and probability, normalised exactly as `/api/events/search`
        # serves them (`espn.period` / `espn.game_clock`). A Search card patches
        # a live game's probability, score and clock together or not at all
        # (Fable, Nov 8), so all three must come from one reading.
        data["live_state"] = _live_state(rows_by_id.get(eid))
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
    # A stream's terminal invalidation must replace an already visible forecast
    # with its assigned result, even when the ordinary scorer omits that market.
    terminal_items = []
    for market in rows:
        item = settled_feed_price_card(market, {
            str(outcome.id): _outcome_clock(outcome) for outcome in market.outcomes
        })
        if item is not None:
            terminal_items.append(item)
            dispositions[f"futures-{market.id}"] = "updated"
    terminal_ids = {item["data"]["id"] for item in terminal_items}
    eligible = [market for market in rows if market.id not in terminal_ids]
    if not eligible:
        return terminal_items, dispositions
    clocks_by_id = {
        market.id: {str(outcome.id): _outcome_clock(outcome) for outcome in market.outcomes}
        for market in eligible
    }
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
        clocks = clocks_by_id[market.id]
        # These are loaded-row REVISION clocks, not proof a price was observed.
        # Preserve the original pre-release client keys only as ordering aliases;
        # never replace their values with differently ordered snapshot clocks.
        data["outcome_revision_at"] = clocks
        data["outcome_observed_at"] = clocks  # Deprecated ordering alias.
        data["outcome_clock_kind"] = "row_revision"
        data["external_id"] = market.external_id
        for outcome in data.get("top_outcomes") or []:
            outcome["price_revision_at"] = clocks.get(str(outcome["id"]))
            outcome["price_observed_at"] = outcome["price_revision_at"]  # Legacy ordering only.
        dispositions[f"futures-{market.id}"] = "updated"
    return terminal_items + items, dispositions


@router.get("/outcome-prices")
async def get_outcome_prices(
    response: Response,
    outcome_ids: str = "",
    db: AsyncSession = Depends(get_db),
):
    """#10090: the team page's on-screen rows, re-read by outcome id.

    `price-cards` returns a market's `top_outcomes` only, and a team's leg of a
    30-way field is rarely among them; the team page itself is a 2.7-5.8 s read
    (Nov 9). This returns each named leg's row fields, refused exactly where the
    team read refuses them (`routes.user._team_outcome_prices`).
    """
    from app.routes.user import _team_outcome_prices

    ids = _ids(outcome_ids)
    if not 0 < len(ids) <= MAX_IDENTITIES:
        raise HTTPException(400, detail={"reason": "outcome_identity_bound", "max_ids": MAX_IDENTITIES})
    items, dispositions = await _team_outcome_prices(db, ids)
    order = {oid: i for i, oid in enumerate(ids)}
    items.sort(key=lambda item: order[item["outcome_id"]])
    response.headers["Cache-Control"] = "no-store"
    return {"items": items, "dispositions": dispositions,
            "built_at": datetime.now(timezone.utc).timestamp()}


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
