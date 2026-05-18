"""
League classification for personalization and highlights.

Centralizes league metadata: pro vs college, Power 4 conference membership,
and league class (pro_major, pro_minor, college, international, other).
"""

import re

# League class: how we categorize each sport_key for scoring purposes.
# "pro_major"    — NFL, NBA, MLB, NHL, WNBA, top international soccer
# "pro_minor"    — XFL, CFL, UFL, AHL, etc.
# "college"      — NCAAF, NCAAB, WNCAAB (further refined by team for Power 4)
# "international"— EPL, La Liga, etc. (non-US pro leagues)
# "other"        — anything not explicitly listed
LEAGUE_CLASS: dict[str, str] = {
    # US Pro Major
    "americanfootball_nfl": "pro_major",
    "basketball_nba": "pro_major",
    "baseball_mlb": "pro_major",
    "icehockey_nhl": "pro_major",
    "basketball_wnba": "pro_major",
    # US College
    "americanfootball_ncaaf": "college",
    "basketball_ncaab": "college",
    "basketball_wncaab": "college",
    # US Pro Minor
    "americanfootball_cfl": "pro_minor",
    "americanfootball_xfl": "pro_minor",
    "americanfootball_ufl": "pro_minor",
    "icehockey_ahl": "pro_minor",
    "basketball_nbl": "pro_minor",
    "basketball_euroleague": "pro_minor",
    # International (top soccer leagues)
    "soccer_epl": "international",
    "soccer_spain_la_liga": "international",
    "soccer_uefa_champs_league": "international",
    "soccer_germany_bundesliga": "international",
    "soccer_italy_serie_a": "international",
    "soccer_france_ligue_one": "international",
    "soccer_usa_mls": "international",
    "soccer_uefa_europa_league": "international",
    "soccer_mexico_ligamx": "international",
    "soccer_brazil_serie_a": "international",
    # MMA/Boxing
    "mma_mixed_martial_arts": "pro_major",
    "boxing_boxing": "pro_major",
    # International soccer (additional)
    "soccer_fifa_world_cup": "international",
    "soccer_brazil_campeonato": "international",
    "soccer_conmebol_copa_libertadores": "international",
    "soccer_netherlands_eredivisie": "international",
    "soccer_portugal_primeira_liga": "international",
    "soccer_efl_champ": "international",
    "soccer_fa_cup": "international",
    "soccer_uefa_europa_conference_league": "international",
    "soccer_england_league1": "pro_minor",
    "soccer_england_league2": "pro_minor",
    # Olympics
    "icehockey_olympics": "international",
    "basketball_olympics": "international",
    "soccer_olympics": "international",
    "fieldhockey_olympics": "international",
    "curling_olympics": "international",
    # Rugby
    "rugby_nrl": "international",
    "rugbyleague_nrl": "international",
    "rugbyunion_six_nations": "international",
    # Aussie Rules
    "aussierules_afl": "international",
    # Cricket
    "cricket_t20_world_cup": "international",
    "cricket_icc_world_cup": "international",
    "cricket_international_t20": "international",
    "cricket_test_match": "international",
    # Tennis Grand Slams
    "tennis_us_open": "pro_major",
    "tennis_french_open": "pro_major",
    "tennis_wimbledon": "pro_major",
    "tennis_australian_open": "pro_major",
    "tennis_atp_aus_open_singles": "pro_major",
    "tennis_wta_aus_open_singles": "pro_major",
    # Golf Majors
    "golf_masters_tournament_winner": "pro_major",
    "golf_pga_championship_winner": "pro_major",
    "golf_us_open_winner": "pro_major",
    "golf_the_open_championship_winner": "pro_major",
    "golf_pga": "pro_major",
    # Lower-tier hockey
    "icehockey_liiga": "pro_minor",
    "icehockey_sweden_hockey_league": "pro_minor",
    "icehockey_sweden_allsvenskan": "pro_minor",
}

# Power 4 conferences (SEC, Big Ten, Big 12, ACC) — ~67 schools.
# Used to distinguish Power 4 vs mid-major college teams in highlights scoring.
POWER_4_TEAMS: set[str] = {
    # SEC (16)
    "Alabama", "Arkansas", "Auburn", "Florida", "Georgia",
    "Kentucky", "LSU", "Mississippi State", "Missouri", "Oklahoma",
    "Ole Miss", "South Carolina", "Tennessee", "Texas",
    "Texas A&M", "Vanderbilt",
    # Big Ten (18)
    "Illinois", "Indiana", "Iowa", "Maryland", "Michigan",
    "Michigan State", "Minnesota", "Nebraska", "Northwestern",
    "Ohio State", "Oregon", "Penn State", "Purdue", "Rutgers",
    "UCLA", "USC", "Washington", "Wisconsin",
    # Big 12 (16)
    "Arizona", "Arizona State", "Baylor", "BYU", "UCF",
    "Cincinnati", "Colorado", "Houston", "Iowa State", "Kansas",
    "Kansas State", "Oklahoma State", "TCU", "Texas Tech",
    "Utah", "West Virginia",
    # ACC (17)
    "Boston College", "Cal", "Clemson", "Duke", "Florida State",
    "Georgia Tech", "Louisville", "Miami", "NC State",
    "North Carolina", "Notre Dame", "Pitt", "SMU", "Stanford",
    "Syracuse", "Virginia", "Virginia Tech", "Wake Forest",
}

# Lowercased set for fast fuzzy matching
_POWER_4_LOWER: set[str] = {name.lower() for name in POWER_4_TEAMS}

_POWER_4_ALIASES: dict[str, str] = {
    "california": "cal",
}

_AMBIGUOUS_NON_POWER_4_RE = re.compile(
    r"\b(?:northwestern state|miami\s+(?:oh|ohio)|california baptist|southern california college)\b"
)


def get_league_class(sport_key: str) -> str:
    """Get league classification for a sport key.

    Returns one of: "pro_major", "pro_minor", "college", "international", "other".
    """
    return LEAGUE_CLASS.get(sport_key, "other")


def is_power_4_team(team_name: str) -> bool:
    """Check if a team name matches a Power 4 school.

    Uses case-insensitive token-boundary matching to handle team name variations
    like "Alabama Crimson Tide" matching "Alabama", or "Ohio State Buckeyes"
    matching "Ohio State", while avoiding ambiguous non-Power 4 names.
    """
    if not team_name:
        return False
    name_lower = team_name.lower()
    if _AMBIGUOUS_NON_POWER_4_RE.search(name_lower):
        return False
    for p4_name in _POWER_4_LOWER:
        # Token-boundary matching handles "Alabama Crimson Tide" without
        # letting short names like "Cal" match unrelated words.
        if re.search(rf"(?<![a-z0-9]){re.escape(p4_name)}(?![a-z0-9])", name_lower):
            return True
    for alias in _POWER_4_ALIASES:
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", name_lower):
            return True
    return False
