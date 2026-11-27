"""Deterministic Content Understanding fields from a linked game or market title."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.utils.feed_market_quality import is_us_state_legislative_district
from app.utils.scheduled_start import start_is_from_schedule
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

# Canonical soccer keys name the country in their second component.
_SOCCER_COUNTRIES = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "belgium": "BE",
    "brazil": "BR",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "colombia": "CO",
    "denmark": "DK",
    "england": "GB",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "korea": "KR",
    "mexico": "MX",
    "netherlands": "NL",
    "norway": "NO",
    "paraguay": "PY",
    "poland": "PL",
    "portugal": "PT",
    "russia": "RU",
    "saudi": "SA",
    "scotland": "GB",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "turkey": "TR",
    "usa": "US",
}

_LEAGUE_GEOGRAPHIES = {
    "americanfootball_cfl": "country:CA",
    "americanfootball_ncaaf": "us",
    "americanfootball_nfl": "us",
    "americanfootball_ufl": "us",
    "americanfootball_xfl": "us",
    "baseball_mlb": "us",
    "baseball_ncaa": "us",
    "baseball_npb": "country:JP",
    "basketball_euroleague": "global",
    "basketball_nba": "us",
    "basketball_ncaab": "us",
    "basketball_nbl": "country:AU",
    "basketball_wnba": "us",
    "basketball_wncaab": "us",
    "icehockey_ahl": "us",
    "icehockey_liiga": "country:FI",
    "icehockey_nhl": "us",
    "icehockey_sweden_allsvenskan": "country:SE",
    "icehockey_sweden_hockey_league": "country:SE",
    "soccer_club_friendlies": "global",
    "soccer_efl_champ": "country:GB",
    "soccer_epl": "country:GB",
    "soccer_fa_cup": "country:GB",
    "soccer_league_of_ireland": "country:IE",
    "soccer_spl": "country:GB",
}

# The local calendar used by each league. North American leagues use the
# Eastern game day. International competitions without a reliable common
# calendar leave the day blank.
_LEAGUE_ZONE_BY_GEOGRAPHY = {
    "us": "America/New_York",
    "country:AR": "America/Argentina/Buenos_Aires",
    "country:AT": "Europe/Vienna",
    "country:AU": "Australia/Sydney",
    "country:BE": "Europe/Brussels",
    "country:BR": "America/Sao_Paulo",
    "country:CA": "America/Toronto",
    "country:CH": "Europe/Zurich",
    "country:CL": "America/Santiago",
    "country:CN": "Asia/Shanghai",
    "country:CO": "America/Bogota",
    "country:DE": "Europe/Berlin",
    "country:DK": "Europe/Copenhagen",
    "country:ES": "Europe/Madrid",
    "country:FI": "Europe/Helsinki",
    "country:FR": "Europe/Paris",
    "country:GB": "Europe/London",
    "country:GR": "Europe/Athens",
    "country:IE": "Europe/Dublin",
    "country:IL": "Asia/Jerusalem",
    "country:IT": "Europe/Rome",
    "country:JP": "Asia/Tokyo",
    "country:KR": "Asia/Seoul",
    "country:MX": "America/Mexico_City",
    "country:NL": "Europe/Amsterdam",
    "country:NO": "Europe/Oslo",
    "country:PL": "Europe/Warsaw",
    "country:PT": "Europe/Lisbon",
    "country:PY": "America/Asuncion",
    "country:RU": "Europe/Moscow",
    "country:SA": "Asia/Riyadh",
    "country:SE": "Europe/Stockholm",
    "country:TR": "Europe/Istanbul",
}


_INTERNATIONAL_SOCCER_PREFIXES = (
    "soccer_afc_",
    "soccer_caf_",
    "soccer_concacaf_",
    "soccer_conmebol_",
    "soccer_fifa_",
    "soccer_uefa_",
)


def _league_geography(league: str | None) -> str | None:
    if not league:
        return None
    if league.startswith(_INTERNATIONAL_SOCCER_PREFIXES) or league.endswith("_olympics"):
        return "global"
    if league.startswith("soccer_"):
        country, _, _ = league.removeprefix("soccer_").partition("_")
        country_code = _SOCCER_COUNTRIES.get(country)
        if country_code:
            return "us" if country_code == "US" else f"country:{country_code}"
    return _LEAGUE_GEOGRAPHIES.get(league)


def _league_zone(league: str | None, geography: str | None) -> str | None:
    if league and league.startswith("soccer_uefa_"):
        # UEFA publishes its competition schedule on the Central European calendar.
        return "Europe/Zurich"
    return _LEAGUE_ZONE_BY_GEOGRAPHY.get(geography or "")


def cu_event_facts(
    title: str,
    *,
    linked_game_id: int | None = None,
    linked_start: datetime | None = None,
    start_source: str | None = None,
    linked_league: str | None = None,
) -> dict[str, str | int | None]:
    """Return fields supplied by a linked fixture or an explicit state district."""
    fields: dict[str, str | int | None] = {}
    if linked_game_id is not None:
        # Linked markets take the fixture's scheduling evidence. A prediction
        # market's close/listing stamp cannot supply a day for a linked game.
        fields["event_date"] = None
        geography = _league_geography(linked_league)
        if geography:
            fields["geography"] = geography
        zone = _league_zone(linked_league, geography)
        if zone and linked_start is not None and start_is_from_schedule(start_source):
            start = linked_start
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            fields["event_date"] = start.astimezone(ZoneInfo(zone)).date().isoformat()
    if is_us_state_legislative_district(title):
        fields.update(geography="local", stakes=1, breadth=1)
    return fields


def cu_unlinked_event_date(
    model_date: object, settlement_at: datetime | None, *, category: str, topic: object
) -> str | None:
    """Drop a non-sport date that only repeats the venue's payout day."""
    if not isinstance(model_date, str):
        return None
    non_sport = category in NON_SPORT_LLM_CATEGORIES and (
        category != "other" or topic not in ("sports", "esports")
    )
    if non_sport and settlement_at is not None:
        if settlement_at.tzinfo is None:
            settlement_at = settlement_at.replace(tzinfo=timezone.utc)
        if model_date == settlement_at.astimezone(timezone.utc).date().isoformat():
            return None
    return model_date
