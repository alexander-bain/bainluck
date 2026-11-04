"""Bounded live hydration of the reviewed Midterms markets and venue twins."""

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesMarket
from app.utils.cross_source_matching import clean_outcomes
from app.utils.midterms_collection import (
    MARKET_IDS,
    MIDTERMS_TWIN_BY_KALSHI_ID,
    is_residual,
    outcome_key,
)

logger = logging.getLogger(__name__)


def is_midterms_twin(a: FuturesMarket, b: FuturesMarket) -> bool:
    if a.source == b.source:
        return False
    entry = MIDTERMS_TWIN_BY_KALSHI_ID.get(a.id)
    if (
        entry is None
        or entry.polymarket_market_id is None
        or entry.polymarket_market_id != b.id
    ):
        return False
    left = {outcome_key(o.name, entry) for o in clean_outcomes(a.outcomes)}
    right = {
        outcome_key(o.name, entry)
        for o in clean_outcomes(b.outcomes)
        if not (
            outcome_key(o.name, entry) not in left
            and outcome_key(o.name, entry) == "other"
            and is_residual({"probability": getattr(o, "current_probability", None)})
        )
    }
    return len(left - {"yes", "no"}) >= 2 and left == right


async def load_midterms_cards(
    db: AsyncSession, market_ids: Iterable[int]
) -> tuple[dict, dict, list]:
    from app.routes.events import _format_futures_for_search
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    ids = set(market_ids) & set(MARKET_IDS)
    if not ids:
        return {}, {}, []
    options = (selectinload(FuturesMarket.sport), selectinload(FuturesMarket.outcomes))
    primary = list(
        (
            await db.execute(
                select(FuturesMarket).options(*options).where(FuturesMarket.id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    primary_ids = {m.id for m in primary}
    registered_twin_ids = sorted(
        {
            entry.polymarket_market_id
            for m in primary
            if (entry := MIDTERMS_TWIN_BY_KALSHI_ID.get(m.id)) is not None
            and entry.polymarket_market_id is not None
            and entry.polymarket_market_id not in primary_ids
        }
    )
    candidates = []
    if registered_twin_ids:
        candidates = list(
            (
                await db.execute(
                    select(FuturesMarket)
                    .options(*options)
                    .where(
                        FuturesMarket.source == "polymarket",
                        FuturesMarket.id.in_(registered_twin_ids),
                    )
                    .order_by(FuturesMarket.id)
                )
            )
            .scalars()
            .all()
        )
    polymarket_pool = [
        m for m in [*primary, *candidates] if getattr(m, "source", None) == "polymarket"
    ]
    by_polymarket_id = {m.id: m for m in polymarket_pool}
    twins, report = {}, []
    for m in primary:
        if m.id == 112905:
            continue
        entry = MIDTERMS_TWIN_BY_KALSHI_ID.get(m.id)
        if entry is None or entry.polymarket_market_id is None:
            twin_state = "no_twin_found"
            matched_ids = []
        else:
            registered = by_polymarket_id.get(entry.polymarket_market_id)
            if registered is not None and is_midterms_twin(m, registered):
                twins[m.id] = [registered.id]
                twin_state = "matched"
                matched_ids = [registered.id]
            else:
                twin_state = "register_mismatch"
                matched_ids = [registered.id] if registered is not None else []
        report.append(
            {
                "market_id": m.id,
                "name": m.name,
                "polymarket_twin_ids": matched_ids,
                "twin_state": twin_state,
            }
        )
    all_markets = {m.id: m for m in primary}
    all_markets.update(
        {c.id: c for c in candidates if any(c.id in v for v in twins.values())}
    )
    withheld = await withheld_price_outcome_ids_for_markets(
        db, list(all_markets.values())
    )
    cards = {}
    for mid, market in all_markets.items():
        try:
            card = _format_futures_for_search(market, withheld.get(mid))
            card["settled_at"] = (
                market.settled_at.isoformat() if market.settled_at else None
            )
            # #11948: search's top-five preview is not the collection's field.
            # Carry every real leg at its own screened venue price. In
            # particular, never normalize a truncated preview to sum to 100%.
            originals = list(clean_outcomes(market.outcomes))
            known = {id(o) for o in originals}
            originals.extend(
                o
                for o in market.outcomes
                if id(o) not in known
                and o.is_winner is True
                and o.resolution_source == "api_settlement"
            )
            preview_order = {
                outcome_key(o["name"]): index
                for index, o in enumerate(card["top_outcomes"])
            }
            originals.sort(
                key=lambda o: preview_order.get(outcome_key(o.name), len(preview_order))
            )
            refused = withheld.get(mid) or set()
            card["top_outcomes"] = [
                {
                    "id": getattr(o, "id", None),
                    "name": o.name,
                    "probability": (
                        float(o.current_probability)
                        if getattr(o, "id", None) not in refused
                        and o.current_probability is not None
                        else None
                    ),
                    "is_winner": o.is_winner,
                    "resolution_source": o.resolution_source,
                }
                for o in originals
            ]
            card["outcome_count"] = max(
                card["outcome_count"], len(card["top_outcomes"])
            )
            cards[mid] = card
        except Exception:
            logger.exception("Midterms market %s could not be rendered", mid)
            cards[mid] = {"_withheld_reason": "unserializable"}
    return cards, twins, sorted(report, key=lambda r: r["market_id"])
