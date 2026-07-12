"""B7 up-link resolver — L2-91.

The ONE shared, server-side resolver that maps a futures MARKET to (a) its
event-concept key (`event:<domain>:<slug>`, richer per-event page) and (b) its
competition hub slug (`/hub/<slug>`). The futures-detail response attaches both so
every market/futures page can link UP to its concept + hub "where a mapping exists"
(and NO link where none does — honest).

This is deliberately a thin DISPATCHER over the domains' existing canonical
derivations — the same functions the registered event-concept adapters and the hub
use — so a link is guaranteed to resolve (no client-side slug guessing that can
dead-link). Mirrors the dispatch-by-domain pattern in `routes/hub.py`.

Coverage:
  * awards ceremonies (Oscars/Emmys/Tonys/Grammys) — ticker/name stem
  * UFC + boxing fights — card date-token from the fight ticker
  * tennis + F1 winner fields — name-slug (the adapters resolve token-tolerantly)
  * golf MAJORS — canonical tournament slug via `_normalize_tournament` (exact match;
    only the four majors are guaranteed to resolve, so non-majors get the hub link,
    never a dead concept link)

All imports are function-level: these util/route modules pull large dependency
graphs, and keeping them lazy holds this module circular-import safe + cheap.
"""

from __future__ import annotations

import re

# Golf major -> a phrase that must appear in the market name for the concept link to
# fire. `_normalize_tournament` is tuned for markets already KNOWN to be golf, so its
# "masters" pattern is loose (matches "Masters of the Universe Opening Weekend Box
# Office" when the LLM miscategorizes an entertainment market as golf). These guards
# require a golf-tournament-plausible phrase so a miscategorized market gets no wrong
# breadcrumb (honest). "masters of …" is excluded to kill that exact box-office case.
_GOLF_MAJOR_NAME_GUARDS: dict[str, re.Pattern] = {
    "masters": re.compile(r"\bmasters\b(?!\s+of\b)", re.I),
    "the_open": re.compile(r"open championship|the open\b", re.I),
    "pga_championship": re.compile(r"pga championship", re.I),
    "us_open": re.compile(r"u\.?\s?s\.? open|\bus open\b", re.I),
}

# category (FuturesMarket.llm_sport_category) -> competition hub slug (routes/hub.py
# HUB_CONFIGS). Only competitions with a real /hub/<slug> page appear here; anything
# else resolves to no hub (honest).
_CATEGORY_HUB: dict[str, str] = {
    "mma": "mma",
    "boxing": "boxing",
    "golf": "golf",
    "tennis": "tennis",
}


def derive_market_hub_slug(llm_sport_category: str | None) -> str | None:
    """Competition hub slug for a market's category, or None if no hub exists."""
    return _CATEGORY_HUB.get((llm_sport_category or "").lower())


def _golf_major_concept_key(name: str | None) -> str | None:
    """`event:golf:<slug>` for a golf MAJOR winner/prop market, else None.

    Uses the SAME normalization the golf route resolves by (`_normalize_tournament`
    -> `TOURNAMENT_DISPLAY_NAMES` -> `clean_slug`, mirroring `_build_completed_tournament`
    in golf.py), so the emitted slug is exactly what `get_golf_tournament` matches.
    Restricted to the four majors — they have hardcoded patterns + display names that
    guarantee resolution; other tour events fall back to the golf hub rather than risk
    a dead concept link (golf slug matching is EXACT, not token-tolerant)."""
    if not name:
        return None
    try:
        from app.routes.golf import (
            MAJOR_TOURNAMENTS,
            TOURNAMENT_DISPLAY_NAMES,
            _normalize_tournament,
        )
        from app.utils.name_normalization import clean_slug
    except Exception:
        return None
    key = _normalize_tournament(name)
    if key not in MAJOR_TOURNAMENTS:
        return None
    # Defensive: require a golf-plausible phrase so an upstream category error
    # (e.g. a box-office market tagged "golf") can't emit a wrong major breadcrumb.
    guard = _GOLF_MAJOR_NAME_GUARDS.get(key)
    if guard is not None and not guard.search(name):
        return None
    display = TOURNAMENT_DISPLAY_NAMES.get(key, key.replace("_", " ").title())
    slug = clean_slug(display)
    return f"event:golf:{slug}" if slug else None


def derive_market_concept_key(
    external_id: str | None,
    name: str | None,
    llm_sport_category: str | None = None,
    n_outcomes: int | None = None,
) -> str | None:
    """Resolve a market to its event-concept key (`event:<domain>:<slug>`) or None.

    Tries each domain's canonical derivation in precedence order; the first hit wins.
    Ticker-based derivations (awards / combat) are authoritative regardless of
    category; the winner-field domains gate on category + a winner-market name."""
    cat = (llm_sport_category or "").lower()

    # 1. Awards ceremonies — ticker stem (unambiguous) then name keyword.
    try:
        from app.utils.event_awards import derive_awards_concept

        aw = derive_awards_concept(external_id, name)
        if aw and aw.get("key"):
            return aw["key"]
    except Exception:
        pass

    # 2. Combat fights — the card date-token off a fight ticker (KXUFCFIGHT / KXBOXING).
    #    Prop tickers (KXUFCMOV / KXBOXINGMOV …) don't match the fight regex -> None,
    #    so props fall through to the hub link.
    try:
        from app.utils.event_ufc import derive_ufc_concept

        u = derive_ufc_concept(external_id, name, n_outcomes)
        if u and u.get("key"):
            return u["key"]
    except Exception:
        pass
    try:
        from app.utils.event_boxing import derive_boxing_concept

        b = derive_boxing_concept(external_id, name, n_outcomes)
        if b and b.get("key"):
            return b["key"]
    except Exception:
        pass

    # 3. Winner-field domains — name-slug (adapters resolve token-tolerantly).
    if cat == "tennis":
        try:
            from app.utils.event_tennis import is_winner_market
            from app.utils.name_normalization import clean_slug

            if is_winner_market(name):
                slug = clean_slug(name or "")
                return f"event:tennis:{slug}" if slug else None
        except Exception:
            return None
        return None

    if cat == "motorsports":
        try:
            from app.utils.event_f1 import is_gp_winner_market
            from app.utils.name_normalization import clean_slug

            # Require "grand prix" in the name to stay F1-scoped — guards against
            # non-race markets miscategorized as motorsports (e.g. the World Cup
            # KXWCGROUPPTS "Any Group Winner" market) leaking a nonsense concept.
            if is_gp_winner_market(name) and "grand prix" in (name or "").lower():
                slug = clean_slug(name or "")
                return f"event:f1:{slug}" if slug else None
        except Exception:
            return None
        return None

    if cat == "golf":
        return _golf_major_concept_key(name)

    return None
