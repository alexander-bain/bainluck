"""F1 / motorsports adapter for the Event Concept framework — slice 4 (#999, L2-72).

A Grand Prix is a winner-field event (like golf/tennis): the race-winner market
is the primary field; qualifying / sprint / podium / constructor / top-N markets
for the same GP fold in as children. Verified live (2026-07-09): Kalshi carries
"<GP> Winner" (e.g. KXF1RACE-BRIGP26) plus per-GP quali/sprint/podium markets,
category=motorsports; Polymarket adds "<GP>: Driver Winner".

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Tokens stripped when deriving the GP name from a market title.
_F1_STOPWORDS = {
    "grand", "prix", "race", "main", "winner", "session", "the", "driver",
    "sprint", "qualifying", "pole", "position", "podium", "finishers", "top",
    "constructor", "fastest", "lap", "formula", "2024", "2025", "2026", "2027",
    "gp", "f1",
}

# A sub-market (not the main race winner) — used to prefer the real GP winner.
_F1_SUBMARKET_RE = re.compile(
    r"\b(sprint|qualifying|pole|podium|constructor|fastest|top\s*\d|q[123])\b",
    re.IGNORECASE,
)
_F1_WINNER_RE = re.compile(r"\b(winner|to win)\b", re.IGNORECASE)


def is_gp_winner_market(name: str | None) -> bool:
    """True for the main-race GP winner field (not a sprint/quali/pole sub-market)."""
    n = name or ""
    return bool(_F1_WINNER_RE.search(n)) and not _F1_SUBMARKET_RE.search(n)


def gp_tokens(name: str | None) -> set[str]:
    """Distinctive Grand Prix name tokens (drops the generic F1 scaffolding).

    "British Grand Prix Winner" -> {"british"};
    "Austrian Grand Prix Main Race: Podium Finishers" -> {"austrian"}."""
    raw = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return {t for t in raw.split() if len(t) >= 4 and t not in _F1_STOPWORDS}


def shares_gp(name: str | None, tokens: set[str]) -> bool:
    if not tokens:
        return False
    return bool(gp_tokens(name) & tokens)


def f1_status(status: str | None, resolution_date, now) -> str:
    """upcoming / live / settled from status + resolution proximity (race weekend)."""
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            if resolution_date < now:
                return "settled"
            days = (resolution_date - now).total_seconds() / 86400
            if days <= 4:  # race weekend
                return "live"
        except TypeError:
            pass
    return "upcoming"


class F1EventAdapter:
    domain = "f1"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone
        from app.models import FuturesMarket
        from app.utils.name_normalization import clean_slug
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        now = datetime.now(timezone.utc)
        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "motorsports",
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        # Resolve the GP winner market: exact clean_slug OR GP-token subset, richest
        # field wins (mirrors tennis L2-65). Only main-race winners are candidates —
        # sprint/quali/pole are children, never the primary.
        slug_tokens = {t for t in slug.split("-") if len(t) >= 4 and t not in _F1_STOPWORDS}

        def _real_count(m) -> int:
            return sum(
                1 for o in (m.outcomes or [])
                if o.name and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            )

        candidates = []
        for m in markets:
            if not is_gp_winner_market(m.name):
                continue
            exact = clean_slug(m.name or "") == slug
            subset = bool(slug_tokens) and slug_tokens <= gp_tokens(m.name)
            if exact or subset:
                candidates.append(m)
        winner = max(candidates, key=_real_count) if candidates else None
        if winner is None:
            return None

        canonical_slug = clean_slug(winner.name or "") or slug

        competitors = []
        for o in winner.outcomes or []:
            if is_field_outcome(o.name) or is_placeholder_outcome_name(o.name):
                continue
            competitors.append({
                "name": o.name,
                "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None else None
                ),
            })
        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children = other markets for this GP (quali/sprint/podium/constructor/top-N).
        tokens = gp_tokens(winner.name)
        children, section_ids = [], []
        for m in markets:
            if m.id == winner.id or not shares_gp(m.name, tokens):
                continue
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            lead = outs[0] if outs else None
            lead_prob = (
                float(lead.current_probability)
                if lead and lead.current_probability is not None else None
            )
            children.append({
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit); not rendered (D1)
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "outcomes": [
                    {"name": o.name, "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None else None)}
                    for o in outs[:4]
                ],
            })
            section_ids.append(m.id)

        sections = [{"type": "winner", "label": "Race winner", "market_ids": [winner.id]}]
        if section_ids:
            sections.append({"type": "prop", "label": "Weekend markets", "market_ids": section_ids})

        envelope = {
            "event": {
                "key": f"event:f1:{canonical_slug}",
                "domain": "f1",
                "name": winner.name,
                "status": f1_status(winner.status, winner.resolution_date, now),
                "start_date": None,
                "end_date": (
                    winner.resolution_date.isoformat()
                    if winner.resolution_date is not None else None
                ),
                "venue": None,
                "location": None,
                "is_major": False,
            },
            "primary": {
                "kind": "winner_field",
                "label": "Race winner",
                "competitors": competitors,
                "evolution_market_id": winner.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

        # L2-71 shared per-competitor history (one fetch); best-effort.
        try:
            from app.utils.event_concept import attach_competitor_history
            await attach_competitor_history(db, winner.id, competitors)
        except Exception:
            pass

        return envelope
