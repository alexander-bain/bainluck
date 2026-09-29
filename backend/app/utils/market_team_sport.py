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

import re

from app.utils.sport_keys import (
    NON_SPORT_LLM_CATEGORIES,
    SPORT_LEAGUE_MAP,
    SPORT_PREFIX_TO_LLM_CATEGORY,
    competition_gender,
    get_sport_key_from_ticker,
    league_family_identity,
    sport_family_key,
)

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


# Sports where a team row plays in exactly ONE league, so a market of another
# league cannot be the team's own title question. Soccer is left out on purpose:
# a club's own path can hold a cup or a continental competition beside its
# league (measured 2026-09-27: 0 of the soccer links below disagree today, so
# leaving it out costs nothing and keeps a Champions League row from being
# refused the day one is linked). Tennis, golf and motorsport players are not
# league-scoped the same way either.
_ONE_LEAGUE_TEAM_CATEGORIES = frozenset({"basketball", "football", "baseball", "hockey"})


# Kalshi series the ticker maps do not carry, each a single league, that sit in
# team championship paths. Read-side only: adding them to
# `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` would also reclassify these markets at
# ingest, which is a different change with a different review. Without them the
# check UNMASKS wrong rows: a path tier that was being withheld because a mapped
# wrong-league candidate disagreed with an unmapped one clears, and the unmapped
# one prints — measured on the 2026-09-27 replay, "Pro Football Teams to go
# Undefeated in their Division" on the Houston and Buffalo college football
# pages, "United Athletic Conference Men's Tournament Champion" on Tarleton
# State's women's page, "Men's Championship Game Qualifiers" on Baylor's.
_SERIES_LEAGUE_SUPPLEMENT: dict[str, str] = {
    "kxnflseed": "americanfootball_nfl",
    "kxnfl1seed": "americanfootball_nfl",
    "kxnfldivundefeated": "americanfootball_nfl",
    "kxnflroundqual": "americanfootball_nfl",
    "kxsbhost": "americanfootball_nfl",
    "kxmarmad": "basketball_ncaab",
    "kxmarmadround": "basketball_ncaab",
    "kxwmarmad": "basketball_wncaab",
    "kxwmarmadround": "basketball_wncaab",
    "kxncaambuac": "basketball_ncaab",
}


def _series_league_supplement(external_id: str | None) -> str | None:
    """A sport key for a series only :data:`_SERIES_LEAGUE_SUPPLEMENT` declares.

    Matched on the SERIES (the ticker up to its first ``-``) exactly, never as a
    loose prefix: ``KXMARMAD`` and ``KXMARMADROUND`` are each listed, because
    a bare ``startswith("kxnfl")`` would also claim a series that merely shares
    the stem (Netflix trades as ``NFLX``).
    """
    series = (external_id or "").split("-", 1)[0].lower()
    return _SERIES_LEAGUE_SUPPLEMENT.get(series)


# The Odds API names an outright by its league's sport key plus the question:
# ``basketball_ncaab_championship_winner``, ``americanfootball_nfl_super_bowl_winner``.
_ODDS_API_OUTRIGHT_SUFFIXES = ("_championship_winner", "_super_bowl_winner")


def _odds_api_outright_league(external_id: str | None) -> str | None:
    """The league sport key an Odds API outright id carries, when it is a known league."""
    ext = (external_id or "").lower()
    for suffix in _ODDS_API_OUTRIGHT_SUFFIXES:
        if ext.endswith(suffix):
            base = ext[: -len(suffix)]
            return base if base in SPORT_LEAGUE_MAP else None
    return None


def _market_league_sport_key(source: str | None, external_id: str | None) -> str | None:
    """The sport key of the league a market's own venue id names; None when it names none."""
    venue = (source or "").lower()
    if venue == "kalshi":
        return get_sport_key_from_ticker(external_id or "") or _series_league_supplement(
            external_id
        )
    if venue == "odds_api":
        return _odds_api_outright_league(external_id)
    return None


def link_crosses_league(
    market_source: str | None,
    market_external_id: str | None,
    team_sport_key: str | None,
) -> bool:
    """True when a market's own venue id names a different league than the team's.

    :func:`link_crosses_sport` cannot see a wrong LEAGUE inside one sport: both
    sides of "West Coast Conference Men's Tournament Champion — Seattle" (Seattle
    U) linked to the Seattle Storm say ``basketball``, so the WNBA team's page
    printed "Win Conference 20%". The same city-name linking put the College
    Football National Championship's "Washington" leg on the Commanders, the
    NFC Championship's "Carolina" leg on the North Carolina Tar Heels and the
    NEC men's tournament's "Central Connecticut St." on the Connecticut Sun —
    102 open tier-1/2/4 Kalshi links on 2026-09-27, every one sampled wrong.

    The market's league is read off its venue's own id (D55: an explicit key,
    never a name) — a Kalshi SERIES through the ticker → sport-key maps, an Odds
    API outright through the sport key it is named with — the team's off its
    sport key, and both are compared as :func:`league_family_identity` (season
    variants and tour tournaments collapse onto their league). Refuses only when:

    * the venue id names a league — an unmapped Kalshi series (``KXNFLPOTM``), a
      Polymarket numeric id or an unknown Odds API key is no claim;
    * the team plays a one-league sport (:data:`_ONE_LEAGUE_TEAM_CATEGORIES`);
    * both leagues are known and differ.
    """
    if not team_sport_key:
        return False
    if sport_key_llm_category(team_sport_key) not in _ONE_LEAGUE_TEAM_CATEGORIES:
        return False
    market_sport_key = _market_league_sport_key(market_source, market_external_id)
    if not market_sport_key:
        return False
    return league_family_identity(market_sport_key) != league_family_identity(team_sport_key)


# A market name that says it is women's play. Word-bounded, so "Men's" never
# reads as "Women's" and "WTA" never fires inside another word. The league
# abbreviations are the women's competitions whose names carry no "women":
# WNBA, the women's college game (WNCAA…), NWSL, the WSL, UWCL, AFLW, NRLW, WTA,
# LPGA, and Kalshi's "(W)" suffix ("College Basketball (W): …").
_WOMENS_MARKET_NAME = re.compile(
    r"\bwomen\b|\bwomen'?s\b|\bwnba\b|\bwncaa\w*|\bnwsl\b|\bwsl\b|\buwcl\b"
    r"|\baflw\b|\bnrlw\b|\bwta\b|\blpga\b|\(w\)",
    re.IGNORECASE,
)

# Families where one market can hold both sides ("Who will win a Grand Slam in
# 2027?" lists Sabalenka beside Sinner), so an unmarked name is no claim.
_MIXED_FIELD_FAMILIES = frozenset({"tennis", "golf"})


def market_names_womens_play(
    market_name: str | None,
    market_sport_key: str | None = None,
    market_source: str | None = None,
    market_external_id: str | None = None,
) -> bool:
    """Whether a market says it is a women's competition.

    By its name, its sport key, or the league its venue id names. The venue id
    matters for Kalshi's "Caitlin Clark's Next Team" (``KXWNBANEXTTEAM``), whose
    name carries no marker.
    """
    if _WOMENS_MARKET_NAME.search(market_name or ""):
        return True
    if competition_gender(market_sport_key) == "women":
        return True
    venue_key = _market_league_sport_key(market_source, market_external_id)
    return competition_gender(venue_key) == "women"


def link_crosses_gender(
    market_name: str | None,
    team_sport_key: str | None,
    market_sport_key: str | None = None,
    market_source: str | None = None,
    market_external_id: str | None = None,
) -> bool:
    """True when a market of one side is linked to a team of the other (#9593).

    :func:`link_crosses_sport` cannot see it: Arsenal and Arsenal Women are both
    ``soccer``, so every soccer "Arsenal" leg reached both pages. The women's
    page printed "Championship 59%", which was Kalshi's men's English Premier
    League Champion. The men's page listed the UEFA Women's Champions League
    Winner. The WNCAAB rows carry "Men's Round of 16 Qualifiers" and "NCAAB
    Championship Winner" by stored link.

    * A men's team refuses a market that names women's play.
    * A women's team refuses a market that does NOT. In a team sport a
      competition is gendered, and the unmarked name is the men's one
      (English Premier League Champion, NCAAB Championship Winner, Final KenPom
      Ratings; every unmarked market stored on a WNCAAB row on 2026-09-29 was
      a men's one). Tennis and golf are exempt (:data:`_MIXED_FIELD_FAMILIES`),
      because an unmarked market there can be a mixed field.
    * A team whose key cannot say its side (a catch-all, or no key) never refuses.
    """
    team_gender = competition_gender(team_sport_key)
    if team_gender is None:
        return False
    womens_market = market_names_womens_play(
        market_name, market_sport_key, market_source, market_external_id
    )
    if team_gender == "men":
        return womens_market
    if womens_market:
        return False
    return sport_family_key(team_sport_key) not in _MIXED_FIELD_FAMILIES
