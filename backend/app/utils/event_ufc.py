"""UFC adapter for the Event Concept framework — slice 3, the co-equal variant
(#999, L2-72). This is the first `primary.kind == "co_equal_list"` domain the
L2-64 components (TwoSidedTimeline + MatchupsRail) were built for.

A UFC card has no single winner — it's a set of two-sided fights. Verified live
(2026-07-09): Kalshi carries per-fight markets with tickers
`KXUFCFIGHT-<DATE><FIGHTERS>` (e.g. KXUFCFIGHT-26JUN20KAPHOR), each with exactly 2
outcomes (fighter A / fighter B), category=mma. Fights sharing the DATE token are
one card. Model: the card's headline fight (latest commence_time) is `primary`
(rendered head-to-head via TwoSidedTimeline); every fight is a child (matchup rail).

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Kalshi UFC fight ticker: KXUFCFIGHT-<YYMONDD><FIGHTERS>. The <YYMONDD> date
# token identifies the card (all fights that day share it).
_UFC_TICKER_RE = re.compile(r"KXUFCFIGHT-(\d{2}[A-Z]{3}\d{2})", re.IGNORECASE)


def ufc_card_token(external_id: str | None) -> str | None:
    """Extract the lowercased card date-token from a Kalshi UFC fight ticker, or
    None if it isn't a fight market. e.g. "kalshi:KXUFCFIGHT-26JUN20KAPHOR" ->
    "26jun20". This is the reliable card-grouping key (no card-level market exists)."""
    if not external_id:
        return None
    m = _UFC_TICKER_RE.search(external_id)
    return m.group(1).lower() if m else None


def ufc_status(latest_commence, now) -> str:
    """upcoming / live / settled for a card from its latest fight's commence time
    (fight night spans a few hours). Conservative: no time → upcoming."""
    if latest_commence is None:
        return "upcoming"
    try:
        hours = (latest_commence - now).total_seconds() / 3600
    except TypeError:
        return "upcoming"
    if hours < -6:      # card finished (> ~6h after the main event started)
        return "settled"
    if hours <= 8:      # fight night window
        return "live"
    return "upcoming"


class UFCEventAdapter:
    domain = "ufc"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone
        from app.models import FuturesMarket

        now = datetime.now(timezone.utc)
        target = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
        if not target:
            return None

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "mma",
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        # Collect this card's FIGHTS: ticker date-token == slug AND two-sided.
        fights = []
        for m in markets:
            if ufc_card_token(m.external_id) != target:
                continue
            if len(m.outcomes or []) != 2:  # a real fight is two-sided
                continue
            fights.append(m)
        if not fights:
            return None

        # Headline fight = latest commence_time (the main event caps the night).
        def _ct(m):
            return m.commence_time or datetime.min.replace(tzinfo=timezone.utc)
        fights.sort(key=_ct)
        main_event = fights[-1]
        latest_commence = main_event.commence_time

        def _fight_outcomes(m):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            return [
                {"name": o.name, "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None else None)}
                for o in outs
            ]

        # primary = the main-event fighters (co-equal, head-to-head).
        competitors = _fight_outcomes(main_event)

        # children = every fight on the card (matchup rail). Settled when decided.
        children = []
        for m in fights:
            outs = _fight_outcomes(m)
            lead_prob = outs[0]["probability"] if outs else None
            settled = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
            children.append({
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit); not rendered (D1)
                "settled": settled,
                "probability": lead_prob,
                "outcomes": outs,
            })

        sections = [{
            "type": "matchup",
            "label": "Fights",
            "market_ids": [m.id for m in fights],
        }]

        return {
            "event": {
                "key": f"event:ufc:{target}",
                "domain": "ufc",
                "name": main_event.name,  # headline fight names the card
                "status": ufc_status(latest_commence, now),
                "start_date": (
                    latest_commence.isoformat() if latest_commence is not None else None
                ),
                "end_date": None,
                "venue": None,
                "location": None,
                "is_major": bool(re.match(r"^UFC\s*\d", main_event.name or "")),
            },
            "primary": {
                "kind": "co_equal_list",
                "label": "Main event",
                "competitors": competitors,
                "evolution_market_id": main_event.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
