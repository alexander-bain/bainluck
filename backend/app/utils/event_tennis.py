"""Tennis adapter for the Event Concept framework — slice 2 (#999).

Unlike golf (which delegates to a bespoke aggregation), tennis has no existing
per-event page, so this adapter builds the generic envelope from scratch:
- winner-field: the tournament-winner market ("… Winner"/"Champion", many player
  outcomes) → primary block competitors.
- matchups: individual "X vs Y" match markets sharing the tournament → children.
- props: other same-tournament markets → children.

Data reality (verified live 2026-07-08): tournament-winner fields come from
Polymarket (e.g. "2026 Women's Wimbledon Winner", 52 outcomes, cat=tennis); Kalshi
tennis is per-match (kxatpmatch…). Association is by tournament-name token, since
cross-source event grouping (design §7 `group_type="event"`) is a later slice.

Pure helpers are unit-tested; the adapter's build_event is exercised via the route
test with a seeded winner market.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Tokens stripped when deriving the tournament name from a market title.
_TENNIS_STOPWORDS = {
    "winner", "champion", "champ", "tennis", "atp", "wta", "mens", "men", "s",
    "womens", "women", "singles", "doubles", "the", "2024", "2025", "2026",
    "2027", "2028", "final", "title",
}

_MATCHUP_RE = re.compile(r"\b(vs\.?|v\.?|def\.?|beats?)\b", re.IGNORECASE)
_WINNER_RE = re.compile(r"\b(winner|champion|champ|to win)\b", re.IGNORECASE)


def is_winner_market(name: str | None) -> bool:
    """True for a tournament-winner field (the parent), not a single match."""
    n = name or ""
    return bool(_WINNER_RE.search(n)) and not _MATCHUP_RE.search(n)


def is_matchup_market(name: str | None) -> bool:
    """True for an individual match market ('Player A vs Player B')."""
    return bool(_MATCHUP_RE.search(name or ""))


def tournament_tokens(name: str | None) -> set[str]:
    """Significant tournament-name tokens from a market title.

    "2026 Women's Wimbledon Winner" -> {"wimbledon"};
    "ATP S-Hertogenbosch Winner" -> {"hertogenbosch"} (len>=4 kept).
    Used to associate child markets to the event."""
    raw = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    toks = {t for t in raw.split() if len(t) >= 4 and t not in _TENNIS_STOPWORDS}
    return toks


def shares_tournament(name: str | None, tokens: set[str]) -> bool:
    if not tokens:
        return False
    return bool(tournament_tokens(name) & tokens)


def tennis_status(status: str | None, resolution_date, now) -> str:
    """upcoming / live / settled from status + resolution proximity."""
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            if resolution_date < now:
                return "settled"
            days = (resolution_date - now).total_seconds() / 86400
            if days <= 21:
                return "live"
        except TypeError:
            pass
    return "upcoming"


class TennisEventAdapter:
    domain = "tennis"

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
                FuturesMarket.llm_sport_category == "tennis",
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        # Find the tournament-winner market matching the slug.
        winner = None
        for m in markets:
            if is_winner_market(m.name) and clean_slug(m.name or "") == slug:
                winner = m
                break
        if winner is None:
            # token-subset fallback: slug tokens ⊆ market's tournament tokens
            slug_tokens = {t for t in slug.split("-") if len(t) >= 4 and t not in _TENNIS_STOPWORDS}
            for m in markets:
                if is_winner_market(m.name) and slug_tokens and slug_tokens <= tournament_tokens(m.name):
                    winner = m
                    break
        if winner is None:
            return None

        # Competitors = real players (drop the field-remainder "Other" + placeholders).
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
        # #23: independent candidate binaries can sum >100% (the raw Wimbledon
        # field did: 28.6+26.8+24.6+21.1…). Normalize the displayed field like
        # search/detail do, so the winner-field reads as a coherent distribution.
        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children (L2-62): associate MATCH markets by ENTRANT-SET overlap — both
        # competitors must be in this event's draw (the winner field). This is the
        # concurrent-tournament guard: a Challenger match in the same date-window
        # whose players aren't in the slam draw is excluded. Non-match markets
        # (props) still associate by the tournament-name token (fallback).
        from app.utils.event_matcher import entrant_key_set, market_in_event
        entrant_keys = entrant_key_set([c["name"] for c in competitors])
        tokens = tournament_tokens(winner.name)
        matchup_ids, prop_ids, children = [], [], []
        for m in markets:
            if m.id == winner.id:
                continue
            is_match = market_in_event(m.name, entrant_keys)
            is_prop = (not is_match) and shares_tournament(m.name, tokens)
            if not (is_match or is_prop):
                continue
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            lead = outs[0] if outs else None
            child = {
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit per-source); NOT rendered (D1)
                "probability": (
                    round(float(lead.current_probability), 4)
                    if lead and lead.current_probability is not None else None
                ),
                "outcomes": [
                    {"name": o.name, "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None else None)}
                    for o in outs[:4]
                ],
            }
            children.append(child)
            (matchup_ids if is_match else prop_ids).append(m.id)

        sections = [{"type": "winner", "label": "Winner", "market_ids": [winner.id]}]
        if matchup_ids:
            sections.append({"type": "matchup", "label": "Matchups", "market_ids": matchup_ids})
        if prop_ids:
            sections.append({"type": "prop", "label": "Props", "market_ids": prop_ids})

        return {
            "event": {
                "key": f"event:tennis:{slug}",
                "domain": "tennis",
                "name": winner.name,
                "status": tennis_status(winner.status, winner.resolution_date, now),
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
                "label": "Winner",
                "competitors": competitors,
                "evolution_market_id": winner.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
