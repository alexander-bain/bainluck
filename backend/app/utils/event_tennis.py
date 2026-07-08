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


def tennis_gender(text: str | None) -> str:
    """men / women / "" inferred from a market name or slug.

    Women is checked first so the "men" substring inside "women" never misfires.
    Used by canonical resolution (L2-65 Item 2) so a gendered slug
    ("…-men-s-…") can never resolve to the opposite-gender field even though the
    gender tokens are stripped from `tournament_tokens`.
    """
    t = (text or "").lower()
    if "women" in t or "wta" in t or "ladies" in t or "female" in t:
        return "women"
    if "men" in t or "atp" in t or "male" in t:
        return "men"
    return ""


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

        # Canonical resolution (L2-65 Item 2): collect ALL winner markets whose
        # slug matches (exact clean_slug OR token-subset), then pick the RICHEST
        # field. A bare/ambiguous slug ("wimbledon") — or a specific one whose name
        # differs across sources — thus lands on the fullest market (e.g. the
        # Polymarket 51-player field) instead of the first, sparse Kalshi one, so
        # shared links converge. A gendered slug never crosses genders (the gender
        # tokens are stopwords, so guard explicitly). The non-winner siblings fold
        # in as children below via the existing entrant/token association.
        slug_gender = tennis_gender(slug)
        slug_tokens = {t for t in slug.split("-") if len(t) >= 4 and t not in _TENNIS_STOPWORDS}

        def _real_outcome_count(m) -> int:
            return sum(
                1 for o in (m.outcomes or [])
                if o.name and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            )

        candidates = []
        for m in markets:
            if not is_winner_market(m.name):
                continue
            exact = clean_slug(m.name or "") == slug
            subset = bool(slug_tokens) and slug_tokens <= tournament_tokens(m.name)
            if not (exact or subset):
                continue
            if slug_gender:
                mg = tennis_gender(m.name)
                if mg and mg != slug_gender:
                    continue
            candidates.append(m)

        # Richest wins: most real competitors, then higher 24h volume, then an
        # exact-slug match, then lowest id (stable / deterministic).
        def _rank(m):
            vol = float(getattr(m, "volume_24h", None) or getattr(m, "volume", None) or 0.0)
            return (_real_outcome_count(m), vol, clean_slug(m.name or "") == slug, -(m.id or 0))

        winner = max(candidates, key=_rank) if candidates else None
        if winner is None:
            return None

        # Canonical key from the WINNER's name so every alias slug (bare or
        # differently-named-per-source) reports the same event key.
        canonical_slug = clean_slug(winner.name or "") or slug

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

        # L2-63 association hierarchy (no auto-associate on weak signals — L2-61
        # precedent: mislabeling > missing):
        #   entrant  — both competitors in the draw (confident matchups)
        #   container— shares a source-native container (group_id) with a CONFIDENT
        #             sibling (winner or entrant matchup) → inherits (catches no-
        #             entrant tournament props when a source groups them)
        #   token    — name shares the tournament token (props naming the event)
        # Collect confident containers first (winner + entrant matchups).
        matched_containers = {winner.group_id} if winner.group_id else set()
        for m in markets:
            if m.id != winner.id and m.group_id and market_in_event(m.name, entrant_keys):
                matched_containers.add(m.group_id)

        matchup_ids, prop_ids, children = [], [], []
        for m in markets:
            if m.id == winner.id:
                continue
            if market_in_event(m.name, entrant_keys):
                method = "entrant"
            elif m.group_id and m.group_id in matched_containers:
                method = "container"
            elif shares_tournament(m.name, tokens):
                method = "token"
            else:
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
            # L2-63 Item 2: a match whose leader is at a dead extreme is DECIDED —
            # mark it settled so the page groups/de-emphasizes it instead of showing
            # a stale 99% as if live (mirrors the L2-53 settled ruling). Kalshi
            # settled markets stay status='open' (gotcha #33), so use the price.
            settled = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
            child = {
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit per-source); NOT rendered (D1)
                "method": method,    # data-only (audit per-method)
                "settled": settled,
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "outcomes": [
                    {"name": o.name, "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None else None)}
                    for o in outs[:4]
                ],
            }
            children.append(child)
            (matchup_ids if method == "entrant" else prop_ids).append(m.id)

        sections = [{"type": "winner", "label": "Winner", "market_ids": [winner.id]}]
        if matchup_ids:
            sections.append({"type": "matchup", "label": "Matchups", "market_ids": matchup_ids})
        if prop_ids:
            sections.append({"type": "prop", "label": "Props", "market_ids": prop_ids})

        return {
            "event": {
                "key": f"event:tennis:{canonical_slug}",
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
