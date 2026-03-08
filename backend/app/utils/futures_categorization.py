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
from datetime import datetime, timezone
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

    # Motorsport / Automotive
    (re.compile(r"\b(formula.1|f1|nascar|indycar|motogp|wrc)\b", re.I), "motorsports"),
    (re.compile(r"\b(daytona.500|indy.500|le.mans|monaco.grand.prix)\b", re.I), "motorsports"),
    (re.compile(r"\b(racing|motorsport)\b", re.I), "motorsports"),
    (re.compile(r"\b(bmw|tesla|ford|gm|toyota|honda|mercedes|audi|porsche|ferrari|lamborghini|rivian|lucid)\b.*\b(release|electric|ev|model|vehicle|car)\b", re.I), "motorsports"),

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

    # Darts
    (re.compile(r"\b(darts?|pdc|bdo|premier.league.darts|world.darts|lakeside|ally.pally|world.matchplay|grand.prix.darts|world.grand.prix.darts)\b", re.I), "darts"),
    (re.compile(r"\b(nine.dart|180s|checkout|bullseye|dartboard)\b", re.I), "darts"),

    # Generic sports awards (catch-all for awards not already matched above)
    # These come after specific sport patterns so "NFL Coach" matches football first
    (re.compile(r"\bnba\s+(coach|executive|clutch|all[\s-]?star)\b", re.I), "basketball"),
    (re.compile(r"\bnfl\s+(coach|executive|comeback|walter.payton|man.of.the.year)\b", re.I), "football"),
    (re.compile(r"\bmlb\s+(manager|coach|executive|comeback)\b", re.I), "baseball"),
    (re.compile(r"\bnhl\s+(coach|jack.adams|general.manager)\b", re.I), "hockey"),
    (re.compile(r"\bmls\s+(coach|mvp|defender|goalkeeper|newcomer)\b", re.I), "soccer"),
    # "Coach of the year" / "Manager of the year" with sport context
    (re.compile(r"\b(head\s+)?coach.of.the.year\b", re.I), "football"),  # Most common in NFL context
    (re.compile(r"\bmanager.of.the.year\b", re.I), "baseball"),  # Most common in MLB context

    # Additional sports patterns commonly missed
    (re.compile(r"\b(most\s+)?wins?\s+(total|over|under)\b", re.I), "football"),  # NFL regular season wins
    (re.compile(r"\bplayoff\s+(berth|spot|appearance|contender)\b", re.I), "football"),  # Generic but usually NFL
    (re.compile(r"\bdraft\s+(pick|order|lottery|#?\d+\s+overall)\b", re.I), "football"),  # NFL/NBA draft
    (re.compile(r"\b(rushing|passing|receiving|touchdown|sack|interception)\s+(yards?|leader|record|title|king|crown)\b", re.I), "football"),
    (re.compile(r"\b(home\s+run|batting\s+average|strikeout|rbi|era\s+leader|no[\s-]?hitter|perfect\s+game)\b", re.I), "baseball"),
    (re.compile(r"\b(triple[\s-]?double|assist|rebound|block|steal)\s+(leader|record|king|title)\b", re.I), "basketball"),
    (re.compile(r"\b(shutout|hat\s+trick|gordie\s+howe|assist)\b", re.I), "hockey"),
    (re.compile(r"\b(transfer\s+window|transfer\s+fee|sign|loan)\b.*\b(epl|premier|la\s+liga|bundesliga|serie\s+a)\b", re.I), "soccer"),

    # Swimming / Track & Field / Athletics (often Olympic context)
    (re.compile(r"\b(swimming|swimmer|butterfly|backstroke|breaststroke|freestyle\s+\d+m)\b", re.I), "olympics"),
    (re.compile(r"\b(track.and.field|athletics|100m|200m|400m|800m|1500m|marathon|hurdle|javelin|shot.put|discus|pole.vault|high.jump|long.jump|decathlon|heptathlon)\b", re.I), "olympics"),

    # Crypto / Digital Assets (include common misspellings)
    (re.compile(r"\b(bitcoin|btc|ethereum|etherium|eth|solana|crypto|blockchain|defi|nft|dogecoin|doge.coin|cardano|xrp|ripple|altcoin|litecoin|polkadot|avalanche|chainlink)\b", re.I), "crypto"),
    (re.compile(r"\bprice\s+of\s+(bitcoin|btc|ethereum|etherium|eth|solana|doge|dogecoin|cardano|xrp|litecoin)\b", re.I), "crypto"),

    # Economics / Finance / Business
    (re.compile(r"\b(fed\s+rate|interest\s+rate|inflation|gdp|recession|cpi|jobs?\s+report|unemployment|treasury|tariff|federal\s+reserve|fomc|rate\s+cut|rate\s+hike|stock\s+market|s&p\s*500|nasdaq|dow\s+jones)\b", re.I), "economics"),
    (re.compile(r"\b(gas\s+price|oil\s+price|commodity|bond\s+yield|ipo|earnings)\b", re.I), "economics"),
    (re.compile(r"\b(ceo|cfo|take\s*over|acquisition|merger|board\s+of\s+directors)\b", re.I), "economics"),

    # Tech / Science / AI / Space
    (re.compile(r"\b(artificial\s+intelligence|chatgpt|openai|anthropic|deepmind|gemini\s+ai|gpt[\s-]?\d)\b", re.I), "tech"),
    (re.compile(r"\b(spacex|starship|nasa|mars\s+mission|moon\s+landing|rocket\s+launch|blue\s+origin)\b", re.I), "tech"),
    (re.compile(r"\b(self[\s-]?driving|autonomous\s+vehicle|quantum\s+computing)\b", re.I), "tech"),
    (re.compile(r"\b(satellite|space\s+station|astronaut|orbit|lunar)\b", re.I), "tech"),

    # Weather / Climate
    (re.compile(r"\b(hurricane|tornado|earthquake|wildfire|heat\s+wave|cold\s+snap|blizzard|flood)\b", re.I), "weather"),
    (re.compile(r"\b(temperature|weather|climate|el\s+ni[nñ]o|la\s+ni[nñ]a)\b", re.I), "weather"),

    # Health / Science
    (re.compile(r"\b(pandemic|covid|vaccine|fda\s+approval|bird\s+flu|mpox|virus|outbreak|drug\s+approval)\b", re.I), "health"),
    (re.compile(r"\b(cdc|who\s+declares|health\s+emergency|clinical\s+trial)\b", re.I), "health"),

    # Geopolitics / International
    (re.compile(r"\b(ukraine|russia|china|taiwan|nato|ceasefire|peace\s+deal|war|sanctions|nuclear|missile)\b", re.I), "geopolitics"),
    (re.compile(r"\b(un\s+security|united\s+nations|diplomatic|geopoliti)\b", re.I), "geopolitics"),
    (re.compile(r"\b(middle\s+east|israel|gaza|iran|north\s+korea|syria)\b", re.I), "geopolitics"),
    (re.compile(r"\b(brexit|european\s+union|eu\s+election)\b", re.I), "geopolitics"),

    # Legal / Regulatory
    (re.compile(r"\b(supreme\s+court|scotus|indictment|verdict|trial|conviction|lawsuit|regulation|antitrust)\b", re.I), "legal"),
    (re.compile(r"\b(sec\s+charges|doj|department\s+of\s+justice|impeach|pardon)\b", re.I), "legal"),

    # Social Media / Culture
    (re.compile(r"\b(twitter|x\.com|tiktok\s+ban|social\s+media|meta\s+stock|elon\s+musk)\b", re.I), "culture"),
    (re.compile(r"\b(nobel\s+prize|pulitzer|time\s+person)\b", re.I), "culture"),

    # NASCAR numbered races (e.g., "Autotrader 400 Winner?", "Bennett 250 Winner?")
    (re.compile(r"\b(250|300|350|400|500)\s+winner\b", re.I), "motorsports"),
    (re.compile(r"\b(xfinity|craftsman|cup\s+series|talladega|bristol\s+motor|charlotte\s+motor|pocono|martinsville|sonoma|watkins\s+glen|richmond|dover|phoenix\s+raceway)\b", re.I), "motorsports"),

    # TV shows / Reality TV
    (re.compile(r"\b(love\s+is\s+blind|survivor|big\s+brother|amazing\s+race|dancing\s+with\s+the\s+stars|american\s+idol|the\s+voice|masked\s+singer|jeopardy|wheel\s+of\s+fortune|90\s+day\s+fianc|below\s+deck|real\s+housewives|the\s+traitors|squid\s+game|love\s+island|married\s+at\s+first)\b", re.I), "entertainment"),

    # Additional NFL Draft patterns
    (re.compile(r"\b(overall\s+pick|#\d+\s+pick|1st\s+pick|first\s+pick|draft\s+class)\b", re.I), "football"),

    # Economics - Powell / Fed chair
    (re.compile(r"\bpowell\b", re.I), "economics"),

    # Crypto tickers with price context
    (re.compile(r"\b(sol|ada|dot|link|avax|matic|atom|bnb|luna)\s+(price|above|below|over|under|at)\b", re.I), "crypto"),
    (re.compile(r"\bprice\s+of\s+(sol|ada|dot|link|avax|matic|atom|bnb)\b", re.I), "crypto"),

    # Engaged / relationship markets (reality TV context)
    (re.compile(r"\b(get\s+engaged|propose|engaged\s+on|wedding|married|couple)\b.*\b(show|season|episode|finale|bachelor|love)\b", re.I), "entertainment"),
    (re.compile(r"\b(show|season|episode|finale|bachelor|love)\b.*\b(get\s+engaged|propose|engaged\s+on|wedding|married|couple)\b", re.I), "entertainment"),

    # Known athletes for ambiguous markets (e.g., "US Open" disambiguation)
    # Top golfers
    (re.compile(r"\b(bryson.dechambeau|scottie.scheffler|rory.mcilroy|jon.rahm|xander.schauffele|collin.morikawa|viktor.hovland|jordan.spieth|brooks.koepka|tiger.woods|phil.mickelson|dustin.johnson|cameron.smith|hideki.matsuyama|patrick.cantlay|justin.thomas|tony.finau|max.homa|wyndham.clark|ludvig.aberg)\b", re.I), "golf"),
    # Top tennis players
    (re.compile(r"\b(novak.djokovic|carlos.alcaraz|jannik.sinner|daniil.medvedev|alexander.zverev|stefanos.tsitsipas|holger.rune|taylor.fritz|coco.gauff|iga.swiatek|aryna.sabalenka|emma.raducanu|naomi.osaka|rafael.nadal|roger.federer|serena.williams)\b", re.I), "tennis"),
]


# =============================================================================
# Game prop detection
# =============================================================================

# Pattern: "Team at/vs Team: Stat" (Kalshi game prop format)
_GAME_PROP_RE = re.compile(
    r'^(.+?)\s+(?:at|vs\.?|@)\s+(.+?):\s+(.+)$', re.IGNORECASE,
)

# Stats that uniquely identify a sport
_STAT_TO_SPORT: dict[str, str] = {
    # Basketball
    "rebounds": "basketball",
    "assists": "basketball",
    "3-pointers": "basketball",
    "three-pointers": "basketball",
    "threes": "basketball",
    "blocks": "basketball",
    "steals": "basketball",
    "turnovers": "basketball",
    "free throws": "basketball",
    "points": "basketball",
    "double-double": "basketball",
    "triple-double": "basketball",
    "dunks": "basketball",
    # Football
    "passing yards": "football",
    "rushing yards": "football",
    "receiving yards": "football",
    "touchdowns": "football",
    "interceptions": "football",
    "sacks": "football",
    "completions": "football",
    "carries": "football",
    "pass attempts": "football",
    "passing touchdowns": "football",
    "rushing touchdowns": "football",
    # Hockey
    "saves": "hockey",
    "shots on goal": "hockey",
    "power play": "hockey",
    "penalty minutes": "hockey",
    # Baseball
    "home runs": "baseball",
    "strikeouts": "baseball",
    "rbis": "baseball",
    "earned runs": "baseball",
    "walks": "baseball",
    "at-bats": "baseball",
    "innings": "baseball",
    # Soccer
    "corners": "soccer",
    "shots on target": "soccer",
    "cards": "soccer",
    "fouls": "soccer",
}


def _seasonal_sport_for_college_matchup() -> Optional[str]:
    """
    Infer the most likely sport for a college matchup based on current month.

    College teams play multiple sports (football, basketball, baseball, etc.).
    When the market name is just "Team at Team" with an ambiguous stat like
    "Spread" or "Total Points", the current date disambiguates:
    - Feb–Apr: basketball (football ended in Jan, March Madness in Mar/Apr)
    - May–Jul: baseball/softball (both football and basketball off-season)
    - Aug–Oct: football (basketball hasn't started yet)
    - Nov–Jan: ambiguous (both football and basketball in-season) → None
    """
    month = datetime.now(timezone.utc).month
    if month in (2, 3, 4):
        return "basketball"
    elif month in (5, 6, 7):
        return "baseball"
    elif month in (8, 9, 10):
        return "football"
    # Nov–Jan: both football and basketball are in-season
    return None


# Ambiguous stats that exist across multiple sports
_AMBIGUOUS_STATS = {
    "spread", "total points", "total", "moneyline", "money line",
    "winner", "field goals", "over/under", "spreads", "totals",
}

# Team name indicators that strongly suggest professional soccer
# (EPL, La Liga, Bundesliga, Serie A, Ligue 1, etc.)
_SOCCER_TEAM_INDICATORS = re.compile(
    r'\b('
    # Common suffixes for soccer clubs worldwide
    r'united|city|fc|rovers|wanderers|hotspur|athletic|albion|villa|palace|forest'
    r'|wolves|rangers|celtic|dynamo|sporting|olimpico'
    # EPL / EFL team names (single-word city names recognizable as soccer)
    r'|arsenal|chelsea|liverpool|everton|fulham|brentford|bournemouth'
    r'|wolverhampton|tottenham|sunderland|burnley|nottingham|brighton'
    r'|newcastle|leicester|southampton|luton|sheffield|ipswich|coventry'
    r'|middlesbrough|swansea|watford|norwich|stoke|aston|blackburn'
    # La Liga
    r'|barcelona|atletico|atlético|betis|celta|getafe|osasuna|sevilla|villarreal'
    r'|sociedad|valladolid|mallorca|girona|deportivo|vallecano|leganes|espanyol'
    # Bundesliga
    r'|bayern|dortmund|leverkusen|gladbach|frankfurt|freiburg|augsburg|mainz'
    r'|hoffenheim|wolfsburg|werder|bochum|heidenheim|darmstadt|köln|stuttgart'
    # Serie A
    r'|juventus|napoli|lazio|fiorentina|genoa|torino|empoli|sassuolo|udinese'
    r'|bologna|cagliari|verona|salernitana|frosinone|lecce|monza'
    # Ligue 1
    r'|marseille|lyon|monaco|lille|rennes|nantes|strasbourg|montpellier|brest'
    r'|reims|toulouse|lorient|clermont|metz|havre'
    # Liga MX / South America / Other
    r'|santos|palmeiras|flamengo|corinthians|boca|river|america|guadalajara|tigres'
    r')\b', re.IGNORECASE,
)


def _is_soccer_matchup(team_a: str, team_b: str) -> bool:
    """Check if team names suggest a professional soccer matchup."""
    return bool(
        _SOCCER_TEAM_INDICATORS.search(team_a)
        or _SOCCER_TEAM_INDICATORS.search(team_b)
    )


def detect_game_prop_sport(market_name: str) -> Optional[str]:
    """
    Detect sport from game prop market names like 'Boston at Golden State: Rebounds'.

    Returns the sport category if a game prop pattern is detected with a
    sport-specific stat, or None if not a game prop or stat is ambiguous.

    For ambiguous stats (spread, total points, moneyline):
    - First checks if team names indicate a soccer matchup (EPL, La Liga, etc.)
    - Then falls back to seasonal inference for college team matchups
    """
    match = _GAME_PROP_RE.match(market_name)
    if not match:
        return None

    team_a = match.group(1).strip()
    team_b = match.group(2).strip()
    stat = match.group(3).strip().lower()

    # Check stat against sport mapping (deterministic, sport-specific)
    for stat_keyword, sport in _STAT_TO_SPORT.items():
        if stat_keyword in stat:
            return sport

    # For ambiguous stats, check soccer teams first, then seasonal inference
    for ambiguous in _AMBIGUOUS_STATS:
        if ambiguous in stat:
            if _is_soccer_matchup(team_a, team_b):
                return "soccer"
            return _seasonal_sport_for_college_matchup()

    return None


def is_game_prop(market_name: str) -> bool:
    """Check if a market name looks like a game prop (Team at Team: Stat)."""
    return _GAME_PROP_RE.match(market_name) is not None


# Pattern: "Team at/vs Team" (bare matchup without stat, typical Kalshi format)
# Team names are typically 1-5 words, start with uppercase, and don't contain
# question marks, sentence-like structures, or common non-matchup words.
_BARE_MATCHUP_RE = re.compile(
    r'^([A-Z][\w\s.\'()]+?)\s+(?:at|vs\.?|@)\s+([A-Z][\w\s.\'()]+?)$',
)


def detect_bare_matchup_sport(market_name: str) -> Optional[str]:
    """
    Detect sport from bare matchup names like 'Iowa at Purdue'.

    Only applies seasonal inference — we can't determine the sport from
    the market name alone. Returns None during ambiguous months (Nov-Jan)
    when both football and basketball are in-season.

    Excludes sentence-like markets ("What will X say at Y?") by requiring
    the match to look like team names (starting with uppercase, no question
    marks, short enough to be team names).
    """
    # Quick filters: skip sentences, questions, and game props
    if '?' in market_name or ':' in market_name:
        return None
    if _GAME_PROP_RE.match(market_name):
        return None
    match = _BARE_MATCHUP_RE.match(market_name.strip())
    if not match:
        return None
    # Both sides should look like team names (1-5 words, under 40 chars each)
    team_a, team_b = match.group(1).strip(), match.group(2).strip()
    if len(team_a) > 40 or len(team_b) > 40:
        return None
    if len(team_a.split()) > 6 or len(team_b.split()) > 6:
        return None
    # Check if team names suggest soccer before falling back to seasonal inference
    if _is_soccer_matchup(team_a, team_b):
        return "soccer"
    return _seasonal_sport_for_college_matchup()


# =============================================================================
# Category tag generation
# =============================================================================

# Entity/topic keywords to extract as tags from market names
_TAG_KEYWORDS: list[tuple[re.Pattern, str]] = [
    # ── Politicians / public figures ──
    (re.compile(r"\btrump\b", re.I), "trump"),
    (re.compile(r"\bbiden\b", re.I), "biden"),
    (re.compile(r"\bharris\b", re.I), "harris"),
    (re.compile(r"\belon\s*musk\b", re.I), "elon_musk"),
    (re.compile(r"\bdesantis\b", re.I), "desantis"),
    (re.compile(r"\bnewsom\b", re.I), "newsom"),
    (re.compile(r"\bpowell\b", re.I), "powell"),
    (re.compile(r"\bvance\b", re.I), "vance"),
    (re.compile(r"\bobama\b", re.I), "obama"),
    (re.compile(r"\bpence\b", re.I), "pence"),
    (re.compile(r"\brfk\b|robert\s+f\.?\s+kennedy", re.I), "rfk"),
    (re.compile(r"\bhaley\b", re.I), "haley"),
    (re.compile(r"\bramaswamy\b", re.I), "ramaswamy"),
    (re.compile(r"\bbuttigieg\b", re.I), "buttigieg"),
    (re.compile(r"\bpelosi\b", re.I), "pelosi"),
    (re.compile(r"\bmcconnell\b", re.I), "mcconnell"),
    (re.compile(r"\baoc\b|ocasio.cortez\b", re.I), "aoc"),
    (re.compile(r"\bputin\b", re.I), "putin"),
    (re.compile(r"\bzelensky\b", re.I), "zelensky"),
    (re.compile(r"\bxi\s+jinping\b", re.I), "xi_jinping"),
    (re.compile(r"\bstarmer\b", re.I), "starmer"),
    (re.compile(r"\bmacron\b", re.I), "macron"),
    (re.compile(r"\btrudeau\b", re.I), "trudeau"),
    (re.compile(r"\bmodi\b", re.I), "modi"),
    # ── Political topics & institutions ──
    (re.compile(r"\belection\b", re.I), "elections"),
    (re.compile(r"\bprimary\b|primaries\b", re.I), "elections"),
    (re.compile(r"\bmidterm\b", re.I), "elections"),
    (re.compile(r"\bgovernor\b", re.I), "governors"),
    (re.compile(r"\bsupreme\s+court\b|\bscotus\b", re.I), "scotus"),
    (re.compile(r"\bcongress\b", re.I), "congress"),
    (re.compile(r"\bsenate\b", re.I), "senate"),
    (re.compile(r"\bhouse\s+of\s+rep", re.I), "house"),
    (re.compile(r"\bcabinet\b", re.I), "cabinet"),
    (re.compile(r"\bimpeach\b", re.I), "impeachment"),
    (re.compile(r"\bexecutive\s+order\b", re.I), "executive_orders"),
    (re.compile(r"\bapproval\s+rat", re.I), "approval_rating"),
    (re.compile(r"\bpardon\b", re.I), "pardons"),
    (re.compile(r"\bshutdown\b", re.I), "government_shutdown"),
    # ── Geopolitics / international ──
    (re.compile(r"\bnato\b", re.I), "nato"),
    (re.compile(r"\bukrain(?:e|ian)?\b", re.I), "ukraine"),
    (re.compile(r"\brussia\b", re.I), "russia"),
    (re.compile(r"\bchina\b", re.I), "china"),
    (re.compile(r"\btaiwan\b", re.I), "taiwan"),
    (re.compile(r"\bisrael\b", re.I), "israel"),
    (re.compile(r"\bgaza\b|palestin", re.I), "gaza"),
    (re.compile(r"\bnorth\s+korea\b", re.I), "north_korea"),
    (re.compile(r"\biran\b", re.I), "iran"),
    # ── Crypto assets ──
    (re.compile(r"\b(bitcoin|btc)\b", re.I), "bitcoin"),
    (re.compile(r"\b(ethereum|etherium|eth)\b", re.I), "ethereum"),
    (re.compile(r"\b(solana|sol\s+price)\b", re.I), "solana"),
    (re.compile(r"\b(dogecoin|doge)\b", re.I), "dogecoin"),
    (re.compile(r"\bxrp\b|ripple\b", re.I), "xrp"),
    (re.compile(r"\bcardano\b|\bada\s+price\b", re.I), "cardano"),
    (re.compile(r"\blitecoin\b|\bltc\b", re.I), "litecoin"),
    (re.compile(r"\bpolkadot\b|\bdot\s+price\b", re.I), "polkadot"),
    (re.compile(r"\bchainlink\b|\blink\s+price\b", re.I), "chainlink"),
    (re.compile(r"\bavalanche\b|\bavax\b", re.I), "avalanche"),
    (re.compile(r"\bpolygon\b|\bmatic\b", re.I), "polygon"),
    (re.compile(r"\buniswap\b|\buni\s+price\b", re.I), "uniswap"),
    (re.compile(r"\bcosmos\b|\batom\s+price\b", re.I), "cosmos"),
    (re.compile(r"\bbnb\b|binance\s+coin", re.I), "bnb"),
    (re.compile(r"\btron\b|\btrx\b", re.I), "tron"),
    (re.compile(r"\bshiba\s*inu\b|\bshib\b", re.I), "shiba_inu"),
    (re.compile(r"\btoncoin\b|\b(?:the\s+)?ton\s+price\b", re.I), "toncoin"),
    (re.compile(r"\bsui\s+price\b|\bsui\s+token\b|\bsui\s+crypto\b", re.I), "sui"),
    (re.compile(r"\baptos\b|\bapt\s+price\b", re.I), "aptos"),
    (re.compile(r"\bpepe\s+(coin|price|token|crypto)\b|\bpepe\b(?=.*\b(price|token|crypto|market)\b)", re.I), "pepe"),
    (re.compile(r"\bnear\s+protocol\b|\bnear\s+price\b", re.I), "near"),
    (re.compile(r"\barbitrum\b|\barb\s+price\b", re.I), "arbitrum"),
    (re.compile(r"\boptimism\b|\bop\s+price\b", re.I), "optimism"),
    (re.compile(r"\bcelestia\b|\btia\s+price\b", re.I), "celestia"),
    (re.compile(r"\bjupiter\b|\bjup\s+price\b", re.I), "jupiter"),
    (re.compile(r"\brender\b|\brndr\b", re.I), "render"),
    (re.compile(r"\bstacks\b|\bstx\b", re.I), "stacks"),
    (re.compile(r"\bworldcoin\b|\bwld\b", re.I), "worldcoin"),
    # ── Crypto topics ──
    (re.compile(r"\bcrypto\s+etf\b|\bbitcoin\s+etf\b|\bethereum\s+etf\b|\betf\b(?=.*\bcrypto\b)", re.I), "crypto_etf"),
    (re.compile(r"\bdefi\b", re.I), "defi"),
    (re.compile(r"\bnft\b", re.I), "nft"),
    (re.compile(r"\bstablecoin\b", re.I), "stablecoin"),
    (re.compile(r"\bmeme\s*coin\b", re.I), "meme_coin"),
    (re.compile(r"\bhalving\b", re.I), "halving"),
    (re.compile(r"\bcrypto\s+market\s+cap\b|\btotal\s+crypto\b", re.I), "crypto_market_cap"),
    # ── Economics / finance ──
    (re.compile(r"\bfed\s+(rate|fund|cut|hike|meeting|decision)\b|\bfederal\s+reserve\b|\bfomc\b", re.I), "fed"),
    (re.compile(r"\binflation\b|\bcpi\b", re.I), "inflation"),
    (re.compile(r"\bgdp\b", re.I), "gdp"),
    (re.compile(r"\brecession\b", re.I), "recession"),
    (re.compile(r"\bunemployment\b|\bjobs?\s+report\b|\bnonfarm\b", re.I), "unemployment"),
    (re.compile(r"\btariff\b", re.I), "tariffs"),
    (re.compile(r"\bdebt\s+ceiling\b", re.I), "debt_ceiling"),
    (re.compile(r"\bs&p\s*500\b|\bsp500\b|\bspx\b", re.I), "sp500"),
    (re.compile(r"\bnasdaq\b", re.I), "nasdaq"),
    (re.compile(r"\bdow\s+jones\b|\bdjia\b", re.I), "dow"),
    (re.compile(r"\btreasury\b|\byield\b", re.I), "treasury"),
    (re.compile(r"\boil\s+price\b|\bcrude\s+oil\b|\bwti\b|\bbrent\b", re.I), "oil"),
    (re.compile(r"\bgold\s+price\b", re.I), "gold"),
    # ── Weather / climate ──
    (re.compile(r"\bhurricane\b|\btropical\s+storm\b", re.I), "hurricanes"),
    (re.compile(r"\btornado\b", re.I), "tornadoes"),
    (re.compile(r"\bwildfire\b", re.I), "wildfires"),
    (re.compile(r"\bearthquake\b", re.I), "earthquakes"),
    (re.compile(r"\btemperature\b|\bdegrees?\b.*\b(high|record|above|below)\b", re.I), "temperature"),
    (re.compile(r"\bsnowfall\b|\bblizzard\b", re.I), "snowfall"),
    (re.compile(r"\brainfall\b|\bflooding\b", re.I), "rainfall"),
    # ── Entertainment / culture ──
    (re.compile(r"\blove\s+is\s+blind\b", re.I), "love_is_blind"),
    (re.compile(r"\boscar\b", re.I), "oscars"),
    (re.compile(r"\bgrammy\b", re.I), "grammys"),
    (re.compile(r"\bemmy\b", re.I), "emmys"),
    (re.compile(r"\btony\s+award\b", re.I), "tonys"),
    (re.compile(r"\bgolden\s+globe\b", re.I), "golden_globes"),
    (re.compile(r"\bnobel\b", re.I), "nobel"),
    (re.compile(r"\bbillboard\b", re.I), "billboard"),
    (re.compile(r"\bbox\s+office\b", re.I), "box_office"),
    (re.compile(r"\bsurvivor\b", re.I), "survivor"),
    (re.compile(r"\bbachelor\b", re.I), "bachelor"),
    (re.compile(r"\breal\s+housewives\b", re.I), "real_housewives"),
    (re.compile(r"\bsnl\b|saturday\s+night\s+live", re.I), "snl"),
    (re.compile(r"\bjeopardy\b", re.I), "jeopardy"),
    (re.compile(r"\bwheel\s+of\s+fortune\b", re.I), "wheel_of_fortune"),
    # ── Companies / tech ──
    (re.compile(r"\btesla\b", re.I), "tesla"),
    (re.compile(r"\bspacex\b", re.I), "spacex"),
    (re.compile(r"\bopenai\b", re.I), "openai"),
    (re.compile(r"\bgoogle\b|\balphabet\b", re.I), "google"),
    (re.compile(r"\bapple\b(?=.*\b(stock|price|market|cap|revenue|iphone)\b)", re.I), "apple"),
    (re.compile(r"\bmeta\b(?=.*\b(stock|price|market|zuckerberg)\b)", re.I), "meta"),
    (re.compile(r"\bnvidia\b|\bnvda\b", re.I), "nvidia"),
    (re.compile(r"\bmicrosoft\b|\bmsft\b", re.I), "microsoft"),
    (re.compile(r"\bamazon\b|\bamzn\b", re.I), "amazon"),
    (re.compile(r"\btiktok\b", re.I), "tiktok"),
    # ── AI / technology topics ──
    (re.compile(r"\bai\s+model\b|\bllm\b|\bchatgpt\b|\bgpt[- ]?\d\b", re.I), "ai"),
    (re.compile(r"\bagi\b", re.I), "agi"),
    (re.compile(r"\bartificial\s+general\s+intelligence\b", re.I), "agi"),
    (re.compile(r"\bself[- ]driving\b|\bautonomous\s+vehicle\b", re.I), "self_driving"),
    # ── Major sports events ──
    (re.compile(r"\bsuper\s+bowl\b", re.I), "super_bowl"),
    (re.compile(r"\bworld\s+series\b", re.I), "world_series"),
    (re.compile(r"\bmarch\s+madness\b", re.I), "march_madness"),
    (re.compile(r"\bstanley\s+cup\b", re.I), "stanley_cup"),
    (re.compile(r"\bnba\s+finals\b", re.I), "nba_finals"),
    (re.compile(r"\bolympic\b", re.I), "olympics"),
    # ── Market types ──
    (re.compile(r"\bmvp\b", re.I), "mvp"),
    (re.compile(r"\brookie\s+of\s+the\s+year\b", re.I), "rookie_of_year"),
    (re.compile(r"\bcoach\s+of\s+the\s+year\b", re.I), "coach_of_year"),
]

# Non-sport categories for cross-referencing
_CROSS_CATEGORY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(bitcoin|btc|ethereum|etherium|crypto|blockchain|solana|dogecoin|cardano|litecoin|polkadot|chainlink|avalanche|polygon|defi|nft|stablecoin)\b", re.I), "crypto"),
    (re.compile(r"\b(trump|biden|harris|election|congress|senate|president|governor|scotus|supreme\s+court|impeach|vance|pelosi|desantis|newsom)\b", re.I), "politics"),
    (re.compile(r"\b(fed\s+rate|inflation|gdp|recession|tariff|interest\s+rate)\b", re.I), "economics"),
    (re.compile(r"\b(ai|artificial\s+intelligence|chatgpt|openai|spacex)\b", re.I), "tech"),
]


def generate_category_tags(
    market_name: str,
    llm_sport_category: Optional[str] = None,
    llm_league: Optional[str] = None,
    category: Optional[str] = None,
) -> list[str]:
    """
    Generate tags for multi-category support.

    Tags enable markets to appear in multiple categories (e.g., a market
    about Trump's Bitcoin policy gets tags for both "politics" and "crypto").

    Args:
        market_name: The market name
        llm_sport_category: Primary category
        llm_league: League abbreviation
        category: Market type (championship, mvp, etc.)

    Returns:
        Sorted list of unique tags
    """
    tags: set[str] = set()

    # Add primary category
    if llm_sport_category and llm_sport_category != "other":
        tags.add(llm_sport_category)

    # Add league as tag
    if llm_league:
        tags.add(llm_league.lower())

    # Add market type
    if category and category not in ("other", "championship"):
        tags.add(category)

    # Extract entity/topic tags from market name
    for pattern, tag in _TAG_KEYWORDS:
        if pattern.search(market_name):
            tags.add(tag)

    # Detect cross-category relevance
    # (e.g., a sports market mentioning crypto should also get "crypto" tag)
    for pattern, cross_cat in _CROSS_CATEGORY_KEYWORDS:
        if pattern.search(market_name):
            tags.add(cross_cat)

    # Mark game props
    if is_game_prop(market_name):
        tags.add("game_prop")

    return sorted(tags)


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

    # Try game prop detection (Team at Team: Stat)
    game_prop_sport = detect_game_prop_sport(market_name)
    if game_prop_sport:
        return game_prop_sport

    # Try bare matchup detection with seasonal inference (Team at Team)
    bare_matchup_sport = detect_bare_matchup_sport(market_name)
    if bare_matchup_sport:
        return bare_matchup_sport

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
# Olympic discipline extraction
# =============================================================================

# Regex for specific Olympic disciplines/events in market names.
# Used to make canonical keys more specific (e.g., "curling" instead of "championship").
_OLYMPIC_DISCIPLINE_RE = re.compile(
    r"\b("
    # Winter sports
    r"curling|figure\s*skating|speed\s*skating|short\s*track|"
    r"alpine\s*skiing|cross[\s-]?country(?:\s*skiing)?|biathlon|"
    r"bobsled|bobsleigh|luge|skeleton|freestyle(?:\s*skiing)?|snowboard(?:ing)?|"
    r"ski\s*jumping|nordic\s*combined|ski\s*mountaineering|"
    r"ice\s*hockey|"
    # Summer sports
    r"swimming|diving|water\s*polo|artistic\s*swimming|"
    r"track\s*(?:and|&)\s*field|athletics|gymnastics|"
    r"basketball|soccer|football|volleyball|beach\s*volleyball|"
    r"tennis|table\s*tennis|badminton|"
    r"boxing|wrestling|judo|taekwondo|karate|fencing|"
    r"archery|shooting|cycling|rowing|canoeing|sailing|surfing|"
    r"skateboarding|climbing|"
    r"weightlifting|equestrian|triathlon|"
    r"rugby\s*sevens|handball|field\s*hockey|"
    r"golf"
    r")\b",
    re.I,
)


def extract_olympic_discipline(market_name: str) -> Optional[str]:
    """
    Extract the specific Olympic discipline from a market name.

    Used to make canonical keys more specific for Olympic events.
    Without this, all Olympic events would share the same canonical key.

    Args:
        market_name: The name of the futures market

    Returns:
        Normalized discipline string (e.g., "curling", "figure_skating"),
        or None if no specific discipline is found.
    """
    match = _OLYMPIC_DISCIPLINE_RE.search(market_name)
    if not match:
        return None

    discipline = match.group(1).lower().strip()
    # Normalize: replace spaces/hyphens with underscores
    discipline = re.sub(r"[\s-]+", "_", discipline)
    # Skip overly generic terms
    if discipline in ("mens", "men_s", "womens", "women_s"):
        return None
    return discipline


# =============================================================================
# League → Sport Category inference
# =============================================================================

# Maps league abbreviations to sport categories. Used to upgrade markets
# stuck as "other" when league detection succeeds but sport detection didn't.
LEAGUE_TO_SPORT_CATEGORY: dict[str, str] = {
    # Basketball
    "NBA": "basketball",
    "WNBA": "basketball",
    "NCAAB": "basketball",
    "WNCAAB": "basketball",
    "EUROLEAGUE": "basketball",
    # Football
    "NFL": "football",
    "NCAAF": "football",
    "CFL": "football",
    "XFL": "football",
    # Baseball
    "MLB": "baseball",
    "NCAA_BASEBALL": "baseball",
    # Hockey
    "NHL": "hockey",
    # Soccer
    "EPL": "soccer",
    "UCL": "soccer",
    "EUROPA": "soccer",
    "LA_LIGA": "soccer",
    "BUNDESLIGA": "soccer",
    "SERIE_A": "soccer",
    "LIGUE_1": "soccer",
    "MLS": "soccer",
    "NWSL": "soccer",
    "LIGA_MX": "soccer",
    "BRASILEIRAO": "soccer",
    "FIFA_WC": "soccer",
    "COPA_AMERICA": "soccer",
    # Golf
    "PGA": "golf",
    "LPGA": "golf",
    "LIV": "golf",
    # Tennis
    "ATP": "tennis",
    "WTA": "tennis",
    # MMA / Boxing
    "UFC": "mma",
    "MMA": "mma",
    "BOXING": "boxing",
    # Motorsports
    "F1": "motorsports",
    "NASCAR": "motorsports",
    "INDYCAR": "motorsports",
    # Cricket
    "IPL": "cricket",
    "ICC": "cricket",
    # Rugby
    "NRL": "rugby",
    "SIX_NATIONS": "rugby",
    "RUGBY": "rugby",
    # Aussie Rules
    "AFL": "aussierules",
    # Horse Racing
    "HORSE_RACING": "horse_racing",
    # Olympics
    "OLYMPICS": "olympics",
    # Esports
    "LOL": "esports",
    "CSGO": "esports",
    "DOTA": "esports",
    "VALORANT": "esports",
    # Non-sports (league-level keys for canonical key)
    "US": "politics",
    "AWARDS": "entertainment",
}


def infer_sport_from_league(league: Optional[str]) -> Optional[str]:
    """
    Infer the sport category from a detected league abbreviation.

    This allows markets categorized as 'other' to be re-categorized when
    league detection succeeds (e.g., market mentions 'Stanley Cup' → NHL → hockey).

    Args:
        league: League abbreviation (e.g., "NBA", "NFL", "EPL")

    Returns:
        Sport category string, or None if league is unknown.
    """
    if not league:
        return None
    return LEAGUE_TO_SPORT_CATEGORY.get(league.upper().strip())


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
# Market type detection (for canonical key specificity)
# =============================================================================

# Ordered by specificity — more specific patterns first
_MARKET_TYPE_PATTERNS: list[tuple["re.Pattern[str]", str]] = [
    # League-specific awards
    (re.compile(r"\b(?:al|american\s+league)\s+cy\s+young\b", re.I), "al_cy_young"),
    (re.compile(r"\b(?:nl|national\s+league)\s+cy\s+young\b", re.I), "nl_cy_young"),
    (re.compile(r"\bcy\s+young\b", re.I), "cy_young"),
    (re.compile(r"\b(?:al|american\s+league)\s+mvp\b", re.I), "al_mvp"),
    (re.compile(r"\b(?:nl|national\s+league)\s+mvp\b", re.I), "nl_mvp"),
    (re.compile(r"\b(?:al|american\s+league)\s+rookie\b", re.I), "al_roy"),
    (re.compile(r"\b(?:nl|national\s+league)\s+rookie\b", re.I), "nl_roy"),
    # Sport-specific awards
    (re.compile(r"\bheisman\b", re.I), "heisman"),
    (re.compile(r"\bhart\s+trophy\b", re.I), "hart_trophy"),
    (re.compile(r"\bnorris\s+trophy\b", re.I), "norris_trophy"),
    (re.compile(r"\bvezina\b", re.I), "vezina"),
    (re.compile(r"\bcalder\s+trophy\b", re.I), "calder_trophy"),
    (re.compile(r"\bconn\s+smythe\b", re.I), "conn_smythe"),
    (re.compile(r"\bballon\s+d.or\b", re.I), "ballon_dor"),
    (re.compile(r"\bgolden\s+boot\b", re.I), "golden_boot"),
    (re.compile(r"\bgolden\s+glove\b", re.I), "golden_glove"),
    # Generic awards (must come after specific ones)
    (re.compile(r"\bmvp\b", re.I), "mvp"),
    (re.compile(r"\brookie\s+of\s+the\s+year\b", re.I), "roy"),
    (re.compile(r"\bdefensive\s+player\b", re.I), "dpoy"),
    (re.compile(r"\bsixth\s+man\b", re.I), "sixth_man"),
    (re.compile(r"\bmost\s+improved\b", re.I), "mip"),
    (re.compile(r"\bcoach\s+of\s+the\s+year\b", re.I), "coy"),
    (re.compile(r"\bclutch\s+player\b", re.I), "clutch_player"),
    # Market types
    (re.compile(r"\bwin\s+total|over.?under\s+wins\b", re.I), "win_totals"),
    (re.compile(r"\bmake\s+playoffs\b", re.I), "make_playoffs"),
    (re.compile(r"\bdivision\s+winner\b", re.I), "division_winner"),
    (re.compile(r"\bconference\s+winner\b", re.I), "conference_winner"),
    # Championship (fallback for sports markets)
    (re.compile(
        r"\bchampion|finals?\s+winner|super\s+bowl|world\s+series|stanley\s+cup"
        r"|pennant|nba\s+finals|nfc|afc\s+champion",
        re.I,
    ), "championship"),
]


def detect_market_type(name: str) -> str:
    """
    Detect a normalized market type from the market name.

    Returns a specific type string for use in canonical market keys.
    More specific than the generic "championship" that was previously used
    for all sports markets.

    Returns:
        Normalized type string (e.g., "al_cy_young", "mvp", "championship")
    """
    for pattern, market_type in _MARKET_TYPE_PATTERNS:
        if pattern.search(name):
            return market_type
    return "championship"


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
