"""Positive fixture evidence for unlinked-market alerts (#12637).

A name match is not proof that the matcher missed a link. This only gates the
alert; it never changes the matcher or writes a market/event. Unknown evidence
stays unassessed, with a reason, rather than implying men's play or a game date.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.utils.market_team_sport import (
    market_event_slug,
    market_league_sport_key,
    market_names_womens_play,
)
from app.utils.sport_keys import competition_gender, same_sport_same_gender, sport_family_key
from app.utils.venue_competition import POLYMARKET_LEAGUE_CODES, polymarket_league_code


FIXTURE_RULE = "family_gender_fixture/v1"

# Exact game-slug league tokens, not title guesses. cbb is the men's competition
# in all three accepted #12072 specimens; unknown tokens remain unassessed.
_POLY_GAME_KEYS = {
    "cbb": "basketball_ncaab",
    "nba": "basketball_nba",
    "wnba": "basketball_wnba",
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
}


def _polymarket_scope_key(slug: str | None) -> str | None:
    code = polymarket_league_code(slug)
    if code in _POLY_GAME_KEYS:
        return _POLY_GAME_KEYS[code]
    keys = [key for key, codes in POLYMARKET_LEAGUE_CODES.items() if code in codes]
    scopes = {(sport_family_key(key), competition_gender(key)) for key in keys}
    # Main draw and qualifying can share a code. This check needs their common
    # family/gender, not an invented choice of which competition owns the game.
    return keys[0] if len(scopes) == 1 else None


def _with_explicit_gender(key: str | None, name: str) -> tuple[str | None, bool]:
    """A (W) name can clarify a catch-all, but cannot overrule a men's key."""
    if not market_names_womens_play(name):
        return key, False
    if competition_gender(key) == "men":
        return key, True
    family = sport_family_key(key)
    return (f"{family}_women" if family else key), False


def fixture_refusal(market, event: dict) -> str | None:
    """None only for compatible sport/gender and the same fixture window.

    ``unknown_*`` reasons are unassessed pairs, not a proved contradiction.
    Date-only Kalshi games must share the Eastern calendar day. Timed games
    reuse the matcher's tolerances, including its Polymarket TBD handling.
    """
    from app.tasks.prediction_market_matching import (
        _market_sport_prefix,
        _ticker_date_conflicts_with_event,
        _venue_fixture_disagrees,
        ticker_start_utc,
        venue_game_start,
    )
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    metadata = market.market_metadata
    slug = market_event_slug(metadata)
    key = market_league_sport_key(market.source, market.external_id, slug)
    if market.source == "polymarket":
        key = _polymarket_scope_key(slug) or key
    if key is None:
        family = sport_family_key(_market_sport_prefix(market))
        key = f"{family}_other" if family else None
    event_key = event["sport"]
    if not sport_family_key(key) or not sport_family_key(event_key):
        return "unknown_sport"
    key, market_conflict = _with_explicit_gender(key, market.name or "")
    event_key, event_conflict = _with_explicit_gender(event_key, event["matchup"])
    if market_conflict or event_conflict:
        return "contradictory_gender"
    if not same_sport_same_gender(key, event_key):
        return "sport_or_gender_mismatch"
    if competition_gender(key) is None or competition_gender(event_key) is None:
        return "unknown_gender"

    commence = event["commence_time"]
    if not isinstance(commence, datetime):
        return "unknown_fixture_date"
    if commence.tzinfo is None:
        commence = commence.replace(tzinfo=timezone.utc)
    if market.source == "kalshi":
        day = extract_game_date_from_ticker(market.external_id)
        if day is None:
            return "unknown_fixture_date"
        if ticker_start_utc(day) is None:
            # The ticker is a local game day, not UTC midnight or close time.
            disagrees = day.date() != commence.astimezone(ZoneInfo("America/New_York")).date()
        else:
            disagrees = _ticker_date_conflicts_with_event(
                day, commence, (market.external_id or "").split("-", 1)[0].lower()
            )
    elif market.source == "polymarket":
        if venue_game_start(market) is None:
            return "unknown_fixture_date"
        disagrees = _venue_fixture_disagrees(market, commence)
    else:
        return "unknown_fixture_date"
    return "fixture_date_mismatch" if disagrees else None
