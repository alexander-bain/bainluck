"""#2593 — does a market that names one sport belong to a team that plays another?

``futures_outcomes.team_id`` was written by city-name matching across sports, so a
stored link is NOT sport-scoped: Kalshi's "MLS Western Conference Champion —
Dallas" leg carries the Dallas Mavericks' id, "NCAAB Championship Winner —
Cincinnati Bearcats" carries FC Cincinnati's, and the PGA Championship's "Austin
Eckroat" carries Austin FC's. Every reader that joins on the column inherits it.
Measured over open season markets 2026-09-27: ~150 links whose market names one
sport and whose team plays another, and every one sampled is wrong.

This is the one test the team-page readers apply before trusting such a link. It
refuses only when BOTH sides say which sport they are and the two disagree:

* the market side is ``llm_sport_category``; a missing value, ``unknown`` or a
  ``NON_SPORT_LLM_CATEGORIES`` value (``entertainment``, ``other``, …) is the
  absence of a sport claim — the Madden-cover question is ``entertainment`` and
  its player legs rightly carry their NFL clubs;
* the team side is its sport key translated into the vocabulary the column is
  stored in (``americanfootball`` → ``football``, ``motorsport`` → ``motorsports``,
  ``rugbyleague`` → ``rugby``). Comparing the raw prefix would call every F1 or
  NRL link wrong-sport.
"""

from __future__ import annotations

from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES, SPORT_PREFIX_TO_LLM_CATEGORY

# Team sport-key prefixes `SPORT_PREFIX_TO_LLM_CATEGORY` does not carry — the
# same three `routes/events.py` translates for #7355 (rugbyleague 31 teams,
# rugbyunion 6, handball 20). Anything else unmapped keeps its raw prefix.
_TEAM_PREFIX_EXTRA_LLM_CATEGORY = {
    "rugbyleague": "rugby",
    "rugbyunion": "rugby",
    "handball": "handball",
}


def sport_key_llm_category(sport_key: str | None) -> str:
    """A sport key's prefix in ``llm_sport_category``'s vocabulary; "" for none."""
    root = (sport_key or "").split("_")[0].lower()
    return (
        SPORT_PREFIX_TO_LLM_CATEGORY.get(root)
        or _TEAM_PREFIX_EXTRA_LLM_CATEGORY.get(root)
        or root
    )


def claims_a_sport(category: str | None) -> bool:
    """Whether a market's ``llm_sport_category`` says which SPORT it is about."""
    cat = (category or "").strip().lower()
    return bool(cat) and cat != "unknown" and cat not in NON_SPORT_LLM_CATEGORIES


def link_crosses_sport(market_category: str | None, team_category: str | None) -> bool:
    """True when a market claiming one sport is linked to a team of another.

    ``team_category`` is already translated (see :func:`sport_key_llm_category`).
    An unknown team sport never refuses.
    """
    if not claims_a_sport(market_category) or not team_category:
        return False
    return market_category.strip().lower() != team_category
