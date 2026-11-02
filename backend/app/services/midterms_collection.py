"""Bounded live hydration of the reviewed Midterms markets and venue twins."""

import re
import logging
from typing import Iterable
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesMarket
from app.utils.cross_source_matching import is_same_question, clean_outcomes
from app.utils.midterms_collection import MARKET_IDS, outcome_key

logger = logging.getLogger(__name__)


def is_midterms_twin(a: FuturesMarket, b: FuturesMarket) -> bool:
    if a.source == b.source:
        return False
    if re.search(
        r"margin|turnout|county|first.round|combo|lieutenant|primary", b.name, re.I
    ):
        return False
    if not is_same_question(a.name, b.name):
        return False
    left = {outcome_key(o.name) for o in a.outcomes}
    right = {outcome_key(o.name) for o in b.outcomes}
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
    # The query names only the selected race's office and state, or its existing
    # cross-source group. This is hydration for fourteen cards, never a census.
    predicates = []
    for m in primary:
        if m.group_id:
            predicates.append(FuturesMarket.group_id == m.group_id)
        match = re.match(
            r"^(?:who (?:wins|will win) (?:the )?)?(.+?) (senate|governor)",
            m.name,
            re.I,
        )
        if match:
            name, office = match.groups()
            escaped = name.replace("%", r"\%").replace("_", r"\_")
            predicates.append(
                FuturesMarket.name.ilike(f"%{escaped}%{office}%", escape="\\")
            )
        elif m.id in {108620, 108621}:
            predicates.append(
                FuturesMarket.name.ilike(
                    "%Senate%control%" if m.id == 108620 else "%House%control%"
                )
            )
    candidates = []
    if predicates:
        candidates = list(
            (
                await db.execute(
                    select(FuturesMarket)
                    .options(*options)
                    .where(
                        FuturesMarket.source == "polymarket",
                        or_(*predicates),
                        FuturesMarket.resolution_date
                        >= datetime(2026, 11, 1, tzinfo=timezone.utc),
                        FuturesMarket.resolution_date
                        < datetime(2027, 2, 1, tzinfo=timezone.utc),
                    )
                    .order_by(FuturesMarket.id)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        if len(candidates) == 100:
            raise ValueError(
                "Midterms twin read reached its bound; do not claim an exhaustive twin report"
            )
    twins, report = {}, []
    for m in primary:
        matches = [c for c in candidates if is_midterms_twin(m, c)]
        if m.id == 108619:
            matches = [p for p in primary if p.id == 112905]
        if len(matches) == 1:
            twins[m.id] = [matches[0].id]
        if m.id != 112905:
            report.append(
                {
                    "market_id": m.id,
                    "name": m.name,
                    "polymarket_twin_ids": [c.id for c in matches],
                    "twin_state": (
                        "matched"
                        if len(matches) == 1
                        else "ambiguous" if matches else "no_twin_found"
                    ),
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
            by_name = {outcome_key(o.name): o for o in market.outcomes}
            for outcome in card["top_outcomes"]:
                original = by_name.get(outcome_key(outcome["name"]))
                if original is not None:
                    outcome.update(
                        is_winner=original.is_winner,
                        resolution_source=original.resolution_source,
                    )
            # A settled winner can lack a surviving price. Its official result is
            # still a result; the display never needs to infer it from that price.
            for outcome in market.outcomes:
                if (
                    outcome.is_winner is True
                    and outcome.resolution_source == "api_settlement"
                    and not any(
                        outcome_key(o["name"]) == outcome_key(outcome.name)
                        for o in card["top_outcomes"]
                    )
                ):
                    card["top_outcomes"].append(
                        {
                            "name": outcome.name,
                            "probability": None,
                            "is_winner": True,
                            "resolution_source": outcome.resolution_source,
                        }
                    )
            for original in clean_outcomes(market.outcomes):
                if not any(
                    outcome_key(o["name"]) == outcome_key(original.name)
                    for o in card["top_outcomes"]
                ):
                    card["top_outcomes"].append(
                        {
                            "name": original.name,
                            "probability": None,
                            "is_winner": original.is_winner,
                            "resolution_source": original.resolution_source,
                        }
                    )
            card["outcome_count"] = max(
                card["outcome_count"], len(card["top_outcomes"])
            )
            cards[mid] = card
        except Exception:
            logger.exception("Midterms market %s could not be rendered", mid)
            cards[mid] = {"_withheld_reason": "unserializable"}
    return cards, twins, sorted(report, key=lambda r: r["market_id"])
