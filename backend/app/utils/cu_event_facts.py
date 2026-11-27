"""Deterministic Content Understanding fields from a linked game or market title."""

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.utils.feed_market_quality import (
    is_us_state_legislative_district,
    names_us_election_office,
)
from app.utils.prediction_market_matching import (
    extract_matchup,
    matchup_for_link_search,
)
from app.utils.scheduled_start import start_is_from_schedule

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

# Reviewed whole club names for fixtures whose team rows lack a domestic league.
# These are club countries and apply to each club across competitions.
_SOCCER_CLUB_COUNTRIES = {
    "almere city fc": "NL",
    "amiens sc": "FR",
    "bayern munich": "DE",
    "fc bayern münchen": "DE",
    "lille osc": "FR",
    "sas épinal": "FR",
    "sportivo ameliano": "PY",
    "sportivo san lorenzo": "PY",
    "vv sint bavo": "NL",
}

_ELECTION_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_ELECTION_RACE_RE = re.compile(r"\b(?:election|winner|wins?|race)\b", re.IGNORECASE)
_NON_GENERAL_ELECTION_RE = re.compile(
    r"\b(?:primary|primaries|nominat\w*|nominees?|run[- ]?offs?|"
    r"special|by[- ]?elections?|recall|caucus|convention|inaugurat\w*|"
    r"poll(?:s|ing)?|appointed?|acting)\b",
    re.IGNORECASE,
)
_ELECTION_DATE_WINDOW_RE = re.compile(
    r"\b(?:before|after|by|until|through)\s+(?:the\s+)?(?:end of\s+)?(?:19|20)\d{2}\b",
    re.IGNORECASE,
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


def _club_geography(
    name: str | None, league: str | None, *, soccer: bool
) -> str | None:
    if soccer and name:
        country = _SOCCER_CLUB_COUNTRIES.get(name.strip().casefold())
        if country:
            return f"country:{country}"
    geography = _league_geography(league)
    return geography if geography != "global" else None


def _fixture_geography(
    title: str,
    league: str | None,
    home_team: tuple[str | None, str | None],
    away_team: tuple[str | None, str | None],
) -> str | None:
    geography = _league_geography(league)
    if geography == "global":
        return geography
    soccer = bool(league and league.startswith("soccer_"))
    if soccer and not home_team[0] and not away_team[0]:
        # An older fixture or frozen replay can lack participant records.
        # Accept only whole club names after removing the market's prop suffix.
        matchup = matchup_for_link_search(extract_matchup(title), title)
        if matchup:
            home_team = (matchup.team_a, home_team[1])
            away_team = (matchup.team_b, away_team[1])
    home_geography = _club_geography(*home_team, soccer=soccer)
    away_geography = _club_geography(*away_team, soccer=soccer)
    if home_geography and away_geography:
        if home_geography != away_geography:
            return "global"
        return geography or home_geography
    return geography


def _election_date_facts(title: str) -> dict[str, str | None]:
    years = set(_ELECTION_YEAR_RE.findall(title))
    if (
        not years
        or not _ELECTION_RACE_RE.search(title)
        or _NON_GENERAL_ELECTION_RE.search(title)
        or not names_us_election_office(title)
    ):
        return {}
    if len(years) != 1 or _ELECTION_DATE_WINDOW_RE.search(title):
        return {"event_date": None}
    year = int(next(iter(years)))
    if year % 2 and not re.search(r"\bgeneral election\b", title, re.IGNORECASE):
        return {"event_date": None}
    november_start = date(year, 11, 1)
    days_to_monday = -november_start.weekday() % 7
    election_day = november_start + timedelta(days=days_to_monday + 1)
    return {"event_date": election_day.isoformat()}


def cu_event_facts(
    title: str,
    *,
    linked_game_id: int | None = None,
    linked_start: datetime | None = None,
    start_source: str | None = None,
    linked_league: str | None = None,
    home_team: tuple[str | None, str | None] = (None, None),
    away_team: tuple[str | None, str | None] = (None, None),
) -> dict[str, str | int | None]:
    """Return fields supplied by a linked fixture or a U.S. election title."""
    fields: dict[str, str | int | None] = {}
    if linked_game_id is not None:
        # Linked markets take the fixture's scheduling evidence. A prediction
        # market's close/listing stamp cannot supply a day for a linked game.
        fields["event_date"] = None
        geography = _fixture_geography(title, linked_league, home_team, away_team)
        fields["geography"] = geography
        zone = _league_zone(
            linked_league, _league_geography(linked_league) or geography
        )
        if zone and linked_start is not None and start_is_from_schedule(start_source):
            start = linked_start
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            fields["event_date"] = start.astimezone(ZoneInfo(zone)).date().isoformat()
    else:
        fields.update(_election_date_facts(title))
    if is_us_state_legislative_district(title):
        fields.update(geography="local", stakes=1, breadth=1)
    return fields


def cu_unlinked_event_date(
    model_date: object, settlement_at: datetime | None
) -> str | None:
    """Drop a model date that only repeats the venue's UTC settlement day."""
    if not isinstance(model_date, str):
        return None
    if settlement_at is not None:
        if settlement_at.tzinfo is None:
            settlement_at = settlement_at.replace(tzinfo=timezone.utc)
        if model_date == settlement_at.astimezone(timezone.utc).date().isoformat():
            return None
    return model_date
