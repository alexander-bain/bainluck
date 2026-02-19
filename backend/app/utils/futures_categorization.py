"""
Futures market sport categorization.

Uses a hybrid approach:
1. Pattern matching rules (fast, free, deterministic)
2. LLM fallback for edge cases (smart, cached)
"""

import re
import logging
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
