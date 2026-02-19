"""
Futures market sport categorization and cross-source matching.

Uses a hybrid approach:
1. Pattern matching rules (fast, free, deterministic)
2. LLM fallback for edge cases (smart, cached)

Also provides:
- League detection (detect_league)
- Season detection (detect_season)
- Canonical market key computation (compute_canonical_market_key)
"""

import re
import logging
from datetime import datetime
from typing import Optional

from app.services import llm

logger = logging.getLogger(__name__)


# Sport categories with their regex patterns
# Order matters - more specific patterns should come first
SPORT_PATTERNS = [
    # Baseball - Match AL/NL awards, MVP, Cy Young, etc.
    (re.compile(r"\b(mlb|world.series)\b", re.I), "baseball"),
    (re.compile(r"\b(al|nl)\s+(mvp|cy.young|rookie|reliever|hank.aaron|manager|comeback|batting|home.run|era)\b", re.I), "baseball"),
    (re.compile(r"\bcy.young\s+(award|winner)\b", re.I), "baseball"),
    (re.compile(r"\bamerican.league\b", re.I), "baseball"),
    (re.compile(r"\bnational.league\b", re.I), "baseball"),
    (re.compile(r"\bpro.baseball\b", re.I), "baseball"),
    (re.compile(r"\bhome.run.derby\b", re.I), "baseball"),
    (re.compile(r"\bbaseball\b", re.I), "baseball"),

    # Football - Match college football, NFL, Super Bowl, Heisman, etc.
    (re.compile(r"\b(nfl|super.bowl)\b", re.I), "football"),
    (re.compile(r"\bcollege.football\b", re.I), "football"),
    (re.compile(r"\bncaaf\b", re.I), "football"),
    (re.compile(r"\bheisman\b", re.I), "football"),
    (re.compile(r"\b(afc|nfc)\s+(championship|winner|east|west|north|south)\b", re.I), "football"),
    (re.compile(r"\bpro.football\b", re.I), "football"),
    # College conferences
    (re.compile(r"\b(acc|sec|big.ten|big.12|big.east|pac.12|pac.10|mountain.west|sun.belt|mac|aac|c.usa)\s+(championship|football|winner)\b", re.I), "football"),
    # College bowl games
    (re.compile(r"\b(rose|sugar|orange|cotton|peach|fiesta|citrus|alamo|holiday|liberty|independence|armed.forces|sun|gator|outback|music.city).bowl\b", re.I), "football"),
    # College Football Playoff
    (re.compile(r"\bcfp\b", re.I), "football"),
    (re.compile(r"\bpro.bowl\b", re.I), "football"),
    # NFL awards
    (re.compile(r"\b(offensive|defensive).player.of.the.year\b", re.I), "football"),
    (re.compile(r"\bnfl.mvp\b", re.I), "football"),

    # Basketball - Must come after football patterns to avoid false matches
    (re.compile(r"\b(nba|ncaab|wnba)\b", re.I), "basketball"),
    (re.compile(r"\bmarch.madness\b", re.I), "basketball"),
    (re.compile(r"\b(eastern|western).conference\b", re.I), "basketball"),
    (re.compile(r"\bpro.basketball\b", re.I), "basketball"),
    (re.compile(r"\b(final.four|sweet.sixteen|sweet.16|elite.eight|elite.8)\b", re.I), "basketball"),
    (re.compile(r"\bncaa.tournament\b", re.I), "basketball"),
    # NBA awards
    (re.compile(r"\b(nba.mvp|finals.mvp|nba.finals)\b", re.I), "basketball"),
    (re.compile(r"\b(defensive.player|sixth.man|most.improved|rookie.of.the.year)\b", re.I), "basketball"),
    (re.compile(r"\b(slam.dunk|dunk.contest|three.point.contest)\b", re.I), "basketball"),
    # College basketball conferences
    (re.compile(r"\b(big.east|big.12|acc|sec|big.ten|pac.12).basketball\b", re.I), "basketball"),
    (re.compile(r"\bbasketball\b", re.I), "basketball"),

    # Hockey - NHL and awards
    (re.compile(r"\b(nhl|stanley.cup)\b", re.I), "hockey"),
    (re.compile(r"\b(hart.trophy|vezina|calder|conn.smythe|norris.trophy|selke|lady.byng|rocket.richard)\b", re.I), "hockey"),
    (re.compile(r"\bhockey\b", re.I), "hockey"),

    # Golf - Major championships and tours
    (re.compile(r"\b(pga|masters|british.open|the.open|ryder.cup)\b", re.I), "golf"),
    (re.compile(r"\b(lpga|liv.golf|dp.world)\b", re.I), "golf"),
    (re.compile(r"\bus.women.?s?.open\b", re.I), "golf"),  # US Women's Open (golf)
    (re.compile(r"\bgolf\b", re.I), "golf"),

    # Tennis - Majors and tournaments
    (re.compile(r"\b(wimbledon|french.open|australian.open|atp|wta)\b", re.I), "tennis"),
    (re.compile(r"\b(davis.cup|billie.jean.king.cup|fed.cup|laver.cup)\b", re.I), "tennis"),
    (re.compile(r"\btennis\b", re.I), "tennis"),

    # Soccer - Match Ballon d'Or, PFA, Premier League, etc.
    (re.compile(r"\b(ballon.d.or|pfa.player|epl|premier.league|champions.league|mls|la.liga|bundesliga|serie.a|nwsl)\b", re.I), "soccer"),
    (re.compile(r"\b(major.league.soccer|europa.league|fa.cup|carabao.cup|league.cup|community.shield)\b", re.I), "soccer"),
    (re.compile(r"\b(golden.boot|golden.ball|golden.glove)\b", re.I), "soccer"),  # Soccer awards
    (re.compile(r"\bworld.cup\b(?!.*college)", re.I), "soccer"),
    (re.compile(r"\bworld.cup.qualifier\b", re.I), "soccer"),
    (re.compile(r"\b(copa.america|euro.20\d\d|euros|uefa.euro|concacaf|nations.league)\b", re.I), "soccer"),
    (re.compile(r"\bbarcelona\b", re.I), "soccer"),
    (re.compile(r"\bsoccer\b", re.I), "soccer"),

    # Horse Racing - Must be before motorsport to avoid "racing" false match
    (re.compile(r"\b(kentucky.derby|preakness|belmont.stakes|breeders.cup|triple.crown)\b", re.I), "horse_racing"),
    (re.compile(r"\b(horse.racing|thoroughbred|jockey)\b", re.I), "horse_racing"),

    # MMA
    (re.compile(r"\b(ufc|mma|bellator|pfl|one.championship)\b", re.I), "mma"),

    # Boxing
    (re.compile(r"\bboxing\b", re.I), "boxing"),

    # Motorsport
    (re.compile(r"\b(formula.1|f1|nascar|indycar|motogp|wrc)\b", re.I), "motorsports"),
    (re.compile(r"\b(daytona.500|indy.500|le.mans|monaco.grand.prix)\b", re.I), "motorsports"),
    (re.compile(r"\b(racing|motorsport)\b", re.I), "motorsports"),

    # Cricket
    (re.compile(r"\b(ipl|cricket|t20|test.match|ashes|bbl|big.bash)\b", re.I), "cricket"),

    # Rugby
    (re.compile(r"\b(rugby|six.nations|tri.nations|super.rugby|nrl)\b", re.I), "rugby"),

    # Australian Rules
    (re.compile(r"\b(afl|australian.football|aussie.rules)\b", re.I), "aussierules"),

    # Politics
    (re.compile(r"\b(election|president|congress|senate|governor|presidential|democrat|republican|trump|biden)\b", re.I), "politics"),
    (re.compile(r"\bhouse.race\b", re.I), "politics"),
    (re.compile(r"\bwhich.party.will.win\b", re.I), "politics"),
    (re.compile(r"\b(gubernatorial|midterm|primary.election|electoral.college|ballot.measure)\b", re.I), "politics"),

    # Esports
    (re.compile(r"\b(lol|league.of.legends|csgo|cs2|cs.go|dota|valorant|esports|overwatch.league)\b", re.I), "esports"),

    # Entertainment
    (re.compile(r"\b(oscar|emmy|grammy|golden.globe|academy.award|entertainer|box.office|movie|film|music|spotify|album)\b", re.I), "entertainment"),
    (re.compile(r"\b(tv.show|television|reality|bachelor|bachelorette|portnoy|youtube|tiktok|influencer)\b", re.I), "entertainment"),

    # Olympics - explicit keyword + uniquely-Olympic winter sports
    (re.compile(r"\b(olympic|olympics|paralympic)\b", re.I), "olympics"),
    # Winter sports that only appear in prediction markets during Olympics
    (re.compile(r"\bcurling\b", re.I), "olympics"),
    (re.compile(r"\bfigure.skating\b", re.I), "olympics"),
    (re.compile(r"\bspeed.skating\b", re.I), "olympics"),
    (re.compile(r"\bshort.track\b", re.I), "olympics"),
    (re.compile(r"\bfreestyle.skiing\b", re.I), "olympics"),
    (re.compile(r"\balpine.skiing\b", re.I), "olympics"),
    (re.compile(r"\bcross.country.skiing\b", re.I), "olympics"),
    (re.compile(r"\bski.jumping\b", re.I), "olympics"),
    (re.compile(r"\bski.mountaineering\b", re.I), "olympics"),
    (re.compile(r"\bnordic.combined\b", re.I), "olympics"),
    (re.compile(r"\bbiathlon\b", re.I), "olympics"),
    (re.compile(r"\bbobsled|bobsleigh\b", re.I), "olympics"),
    (re.compile(r"\b(luge|skeleton)\b", re.I), "olympics"),
    (re.compile(r"\bgold.medal\b", re.I), "olympics"),

    # Lacrosse
    (re.compile(r"\b(lacrosse|tewaaraton|pll|premier.lacrosse)\b", re.I), "lacrosse"),

    # Chess
    (re.compile(r"\bchess\b", re.I), "chess"),

    # Poker
    (re.compile(r"\b(wsop|poker|world.series.of.poker)\b", re.I), "poker"),

    # Known athletes for ambiguous markets (e.g., "US Open" disambiguation)
    # Top golfers
    (re.compile(r"\b(bryson.dechambeau|scottie.scheffler|rory.mcilroy|jon.rahm|xander.schauffele|collin.morikawa|viktor.hovland|jordan.spieth|brooks.koepka|tiger.woods|phil.mickelson|dustin.johnson|cameron.smith|hideki.matsuyama|patrick.cantlay|justin.thomas|tony.finau|max.homa|wyndham.clark|ludvig.aberg)\b", re.I), "golf"),
    # Top tennis players
    (re.compile(r"\b(novak.djokovic|carlos.alcaraz|jannik.sinner|daniil.medvedev|alexander.zverev|stefanos.tsitsipas|holger.rune|taylor.fritz|coco.gauff|iga.swiatek|aryna.sabalenka|emma.raducanu|naomi.osaka|rafael.nadal|roger.federer|serena.williams)\b", re.I), "tennis"),
]


def categorize_by_rules(market_name: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Try to categorize a market using regex pattern matching.

    Args:
        market_name: The name of the futures market
        sport_key: Optional sport key from the source (e.g., "basketball_nba_championship")

    Returns:
        Sport category string, or None if no pattern matches
    """
    # Build searchable text from sport key and market name
    search_text = " ".join(filter(None, [sport_key, market_name]))

    # Try prefix matching on sport_key first
    if sport_key:
        prefixes = {
            "americanfootball_": "football",
            "basketball_": "basketball",
            "baseball_": "baseball",
            "icehockey_": "hockey",
            "mma_": "mma",
            "boxing_": "boxing",
            "golf_": "golf",
            "tennis_": "tennis",
            "soccer_": "soccer",
            "politics_": "politics",
            "esports_": "esports",
            "motorsport_": "motorsports",
            "lacrosse_": "lacrosse",
            "cricket_": "cricket",
            "rugbyleague_": "rugby",
            "rugbyunion_": "rugby",
            "aussierules_": "aussierules",
            "horseracing_": "horse_racing",
        }
        for prefix, category in prefixes.items():
            if sport_key.startswith(prefix):
                return category

    # Try regex pattern matching
    for pattern, category in SPORT_PATTERNS:
        if pattern.search(search_text):
            return category

    return None


def categorize_market(
    market_name: str,
    sport_key: Optional[str] = None,
    use_llm: bool = True,
) -> str:
    """
    Categorize a futures market into a sport category.

    Uses hybrid approach:
    1. Try pattern matching rules (fast, free)
    2. Fall back to LLM if rules don't match (smart, cached)
    3. Return "other" if all else fails

    Args:
        market_name: The name of the futures market
        sport_key: Optional sport key from the source
        use_llm: Whether to use LLM as fallback (default True)

    Returns:
        Sport category string (never None - defaults to "other")
    """
    # Try rules first
    category = categorize_by_rules(market_name, sport_key)
    if category:
        logger.debug(f"Categorized '{market_name}' as '{category}' via rules")
        return category

    # Fall back to LLM if enabled
    if use_llm and llm.is_available():
        category = llm.classify_futures_market(market_name)
        if category and category != "other":
            logger.info(f"Categorized '{market_name}' as '{category}' via LLM")
            return category
        elif category == "other":
            logger.debug(f"LLM categorized '{market_name}' as 'other'")
            return "other"

    logger.debug(f"Could not categorize '{market_name}', defaulting to 'other'")
    return "other"


# =============================================================================
# League detection
# =============================================================================

# Maps sport_key prefixes from The Odds API to standardized league abbreviations.
# Order: more specific keys first to avoid partial matches.
_SPORT_KEY_TO_LEAGUE: list[tuple[str, str]] = [
    # Basketball
    ("basketball_nba", "NBA"),
    ("basketball_wnba", "WNBA"),
    ("basketball_ncaab", "NCAAB"),
    ("basketball_wncaab", "WNCAAB"),
    ("basketball_euroleague", "EUROLEAGUE"),
    # Football
    ("americanfootball_nfl", "NFL"),
    ("americanfootball_ncaaf", "NCAAF"),
    ("americanfootball_cfl", "CFL"),
    ("americanfootball_xfl", "XFL"),
    # Baseball
    ("baseball_mlb", "MLB"),
    ("baseball_ncaa", "NCAA_BASEBALL"),
    # Hockey
    ("icehockey_nhl", "NHL"),
    # Soccer
    ("soccer_epl", "EPL"),
    ("soccer_usa_mls", "MLS"),
    ("soccer_spain_la_liga", "LA_LIGA"),
    ("soccer_germany_bundesliga", "BUNDESLIGA"),
    ("soccer_italy_serie_a", "SERIE_A"),
    ("soccer_france_ligue_one", "LIGUE_1"),
    ("soccer_uefa_champs_league", "UCL"),
    ("soccer_uefa_europa_league", "EUROPA"),
    ("soccer_mexico_ligamx", "LIGA_MX"),
    ("soccer_brazil_campeonato", "BRASILEIRAO"),
    ("soccer_fifa_world_cup", "FIFA_WC"),
    # Golf
    ("golf_pga", "PGA"),
    ("golf_masters", "PGA"),
    ("golf_lpga", "LPGA"),
    # Tennis
    ("tennis_atp", "ATP"),
    ("tennis_wta", "WTA"),
    # MMA
    ("mma_mixed_martial_arts", "UFC"),
    # Motorsports
    ("motorsport_f1", "F1"),
    ("motorsport_nascar", "NASCAR"),
    ("motorsport_indycar", "INDYCAR"),
    # Cricket
    ("cricket_ipl", "IPL"),
    ("cricket_test", "ICC"),
    # Rugby
    ("rugbyleague_nrl", "NRL"),
    ("rugbyunion_six_nations", "SIX_NATIONS"),
    # Aussie Rules
    ("aussierules_afl", "AFL"),
    # Horse Racing
    ("horseracing_", "HORSE_RACING"),
]

# Regex patterns for detecting league from market name.
# Order: more specific patterns first. Each returns a standardized abbreviation.
LEAGUE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Basketball
    (re.compile(r"\b(nba|nba\s+finals|nba\s+championship)\b", re.I), "NBA"),
    (re.compile(r"\bwnba\b", re.I), "WNBA"),
    (re.compile(r"\b(ncaab|march\s*madness|ncaa\s+tournament|final\s+four|sweet\s+sixteen|elite\s+eight)\b", re.I), "NCAAB"),
    (re.compile(r"\b(wncaab|women.?s?\s+ncaa)\b", re.I), "WNCAAB"),
    (re.compile(r"\b(eastern|western)\s+conference\b", re.I), "NBA"),  # Ambiguous but usually NBA
    # Football
    (re.compile(r"\b(nfl|super\s*bowl|nfl\s+mvp)\b", re.I), "NFL"),
    (re.compile(r"\b(afc|nfc)\s+(championship|winner|east|west|north|south)\b", re.I), "NFL"),
    (re.compile(r"\b(ncaaf|college\s+football|heisman|cfp)\b", re.I), "NCAAF"),
    (re.compile(r"\b(rose|sugar|orange|cotton|peach|fiesta)\s+bowl\b", re.I), "NCAAF"),
    # Baseball
    (re.compile(r"\b(mlb|world\s+series|american\s+league|national\s+league)\b", re.I), "MLB"),
    (re.compile(r"\b(al|nl)\s+(mvp|cy\s*young|rookie|reliever)\b", re.I), "MLB"),
    # Hockey
    (re.compile(r"\b(nhl|stanley\s+cup)\b", re.I), "NHL"),
    (re.compile(r"\b(hart\s+trophy|vezina|calder|conn\s+smythe|norris\s+trophy|selke|rocket\s+richard)\b", re.I), "NHL"),
    # Soccer
    (re.compile(r"\b(epl|premier\s+league|english\s+premier)\b", re.I), "EPL"),
    (re.compile(r"\b(champions\s+league|ucl)\b", re.I), "UCL"),
    (re.compile(r"\b(europa\s+league)\b", re.I), "EUROPA"),
    (re.compile(r"\b(la\s+liga|spanish\s+league)\b", re.I), "LA_LIGA"),
    (re.compile(r"\bbundesliga\b", re.I), "BUNDESLIGA"),
    (re.compile(r"\bserie\s+a\b", re.I), "SERIE_A"),
    (re.compile(r"\bligue\s+1\b", re.I), "LIGUE_1"),
    (re.compile(r"\b(mls|major\s+league\s+soccer)\b", re.I), "MLS"),
    (re.compile(r"\bnwsl\b", re.I), "NWSL"),
    (re.compile(r"\bliga\s+mx\b", re.I), "LIGA_MX"),
    (re.compile(r"\bworld\s+cup\b(?!.*college)", re.I), "FIFA_WC"),
    (re.compile(r"\b(copa\s+america)\b", re.I), "COPA_AMERICA"),
    (re.compile(r"\b(ballon\s+d.or|pfa\s+player)\b", re.I), "EPL"),  # Typically EPL context
    # Golf
    (re.compile(r"\b(pga|pga\s+tour|pga\s+championship)\b", re.I), "PGA"),
    (re.compile(r"\b(masters|the\s+masters)\b", re.I), "PGA"),
    (re.compile(r"\blpga\b", re.I), "LPGA"),
    (re.compile(r"\b(liv\s+golf)\b", re.I), "LIV"),
    # Tennis
    (re.compile(r"\b(atp|atp\s+finals)\b", re.I), "ATP"),
    (re.compile(r"\bwta\b", re.I), "WTA"),
    (re.compile(r"\bwimbledon\b", re.I), "ATP"),
    (re.compile(r"\b(french\s+open|roland\s+garros)\b", re.I), "ATP"),
    (re.compile(r"\baustralian\s+open\b", re.I), "ATP"),
    (re.compile(r"\bdavis\s+cup\b", re.I), "ATP"),
    # MMA / Boxing
    (re.compile(r"\bufc\b", re.I), "UFC"),
    (re.compile(r"\b(bellator|pfl)\b", re.I), "MMA"),
    (re.compile(r"\bboxing\b", re.I), "BOXING"),
    # Motorsports
    (re.compile(r"\b(formula\s*1|f1)\b", re.I), "F1"),
    (re.compile(r"\bnascar\b", re.I), "NASCAR"),
    (re.compile(r"\bindycar\b", re.I), "INDYCAR"),
    (re.compile(r"\b(daytona\s+500)\b", re.I), "NASCAR"),
    (re.compile(r"\b(indy\s+500)\b", re.I), "INDYCAR"),
    # Cricket
    (re.compile(r"\bipl\b", re.I), "IPL"),
    (re.compile(r"\b(cricket|t20|ashes|big\s+bash)\b", re.I), "ICC"),
    # Rugby
    (re.compile(r"\bnrl\b", re.I), "NRL"),
    (re.compile(r"\bsix\s+nations\b", re.I), "SIX_NATIONS"),
    (re.compile(r"\brugby\b", re.I), "RUGBY"),
    # Aussie Rules
    (re.compile(r"\bafl\b", re.I), "AFL"),
    # Horse Racing
    (re.compile(r"\b(kentucky\s+derby|preakness|belmont\s+stakes|breeders.cup|triple\s+crown)\b", re.I), "HORSE_RACING"),
    # Olympics
    (re.compile(r"\b(olympic|olympics)\b", re.I), "OLYMPICS"),
    # Esports
    (re.compile(r"\b(lol|league\s+of\s+legends)\b", re.I), "LOL"),
    (re.compile(r"\b(csgo|cs2)\b", re.I), "CSGO"),
    (re.compile(r"\b(dota)\b", re.I), "DOTA"),
    (re.compile(r"\bvalorant\b", re.I), "VALORANT"),
    # Politics / non-sports
    (re.compile(r"\b(election|president|congress|senate|governor)\b", re.I), "US"),
    # Entertainment / economics / tech / crypto — use category-level
    (re.compile(r"\b(oscar|emmy|grammy|golden\s+globe)\b", re.I), "AWARDS"),
]


def detect_league(
    market_name: str,
    sport_key: Optional[str] = None,
) -> Optional[str]:
    """
    Detect the league/competition for a futures market.

    For Odds API markets, trivially derives from sport_key.
    For Kalshi/Polymarket, parses from market name using regex patterns.

    Args:
        market_name: The name of the futures market
        sport_key: Optional sport key from The Odds API

    Returns:
        Standardized league abbreviation (e.g., "NBA", "NFL", "EPL"),
        or None if no league can be determined.
    """
    # Phase 1: Try sport_key prefix mapping (Odds API markets)
    if sport_key:
        for prefix, league in _SPORT_KEY_TO_LEAGUE:
            if sport_key.startswith(prefix):
                return league

    # Phase 2: Try regex pattern matching on market name
    search_text = " ".join(filter(None, [sport_key, market_name]))
    for pattern, league in LEAGUE_PATTERNS:
        if pattern.search(search_text):
            return league

    return None


# =============================================================================
# Season detection
# =============================================================================

# Leagues that use split-year seasons (e.g., 2025-26 for Oct-Jun)
_SPLIT_YEAR_LEAGUES = {
    "NBA", "WNBA", "NCAAB", "WNCAAB", "NHL", "EPL", "UCL", "EUROPA",
    "LA_LIGA", "BUNDESLIGA", "SERIE_A", "LIGUE_1", "MLS", "NWSL",
    "EUROLEAGUE", "LIGA_MX", "NRL", "AFL",
}

# Leagues that use single-year seasons (e.g., 2025 for Jan-Dec or Feb-Feb)
_SINGLE_YEAR_LEAGUES = {
    "NFL", "NCAAF", "MLB", "PGA", "LPGA", "LIV", "ATP", "WTA",
    "UFC", "MMA", "BOXING", "F1", "NASCAR", "INDYCAR", "IPL", "ICC",
    "HORSE_RACING", "OLYMPICS", "COPA_AMERICA", "FIFA_WC",
    "SIX_NATIONS", "RUGBY", "LOL", "CSGO", "DOTA", "VALORANT",
}

# Regex to find explicit year references in market names
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
_SPLIT_YEAR_PATTERN = re.compile(r"\b(20\d{2})[-/](20)?(\d{2})\b")


def detect_season(
    market_name: str,
    league: Optional[str] = None,
    resolution_date: Optional[datetime] = None,
) -> Optional[str]:
    """
    Detect the season for a futures market.

    Returns standardized season strings:
    - Split-year leagues: "2025-26" (NBA, NHL, EPL, etc.)
    - Single-year leagues: "2025" (NFL, MLB, PGA, etc.)
    - Non-sports: calendar year "2026"

    Args:
        market_name: The name of the futures market
        league: Detected league abbreviation
        resolution_date: When the market resolves

    Returns:
        Season string, or None if cannot determine.
    """
    # Try to find explicit split-year in market name (e.g., "2025-26", "2025/26")
    split_match = _SPLIT_YEAR_PATTERN.search(market_name)
    if split_match:
        start_year = int(split_match.group(1))
        end_suffix = split_match.group(3)
        return f"{start_year}-{end_suffix}"

    # Try to find explicit single year in market name
    year_matches = _YEAR_PATTERN.findall(market_name)

    if year_matches:
        # Use the first year found
        year = int(year_matches[0])

        # If league uses split-year format, convert
        if league and league in _SPLIT_YEAR_LEAGUES:
            # A market named "NBA Championship 2026" means the 2025-26 season
            # The year in the name is typically when the season ends
            return f"{year - 1}-{str(year)[2:]}"

        return str(year)

    # No explicit year — infer from resolution_date
    if resolution_date:
        year = resolution_date.year
        month = resolution_date.month

        if league and league in _SPLIT_YEAR_LEAGUES:
            # If resolves in Jan-Aug, it's the season that started the previous year
            if month <= 8:
                return f"{year - 1}-{str(year)[2:]}"
            else:
                return f"{year}-{str(year + 1)[2:]}"

        return str(year)

    return None


# =============================================================================
# Canonical market key computation
# =============================================================================


def compute_canonical_market_key(
    llm_sport_category: Optional[str],
    llm_league: Optional[str],
    category: Optional[str],
    season: Optional[str],
) -> Optional[str]:
    """
    Compute a canonical market key for cross-source matching.

    Format: {sport_category}:{league}:{category}:{season}

    Only returns a key when we have enough axes to make a meaningful match.
    Missing sport_category or category will prevent key generation.

    Args:
        llm_sport_category: Sport/topic category (e.g., "basketball", "politics")
        llm_league: League abbreviation (e.g., "NBA", "NFL")
        category: Market type (e.g., "championship", "mvp")
        season: Season string (e.g., "2025-26", "2025")

    Returns:
        Canonical key string, or None if insufficient data.
    """
    sport = (llm_sport_category or "").lower().strip()
    league = (llm_league or "").upper().strip()
    cat = (category or "").lower().strip()
    szn = (season or "").strip()

    # Must have at least sport + category to form a meaningful key
    if not sport or not cat:
        return None

    # Build key: use empty string for missing optional parts
    return f"{sport}:{league}:{cat}:{szn}"
