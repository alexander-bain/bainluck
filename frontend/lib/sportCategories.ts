import type { FuturesMarket } from "./types";

/**
 * Sport categories for grouping leagues under parent sports.
 *
 * BLACKLIST APPROACH: The backend excludes soccer, cricket, rugby, and AFL.
 * (soccer_*, cricket_*, rugbyleague_*, rugbyunion_*, aussierules_*)
 * Everything else from The Odds API is included and should be categorized here.
 *
 * This file maps sport keys to categories and display names dynamically.
 * Unknown sports fall into an "Other" category rather than being hidden.
 *
 * Last updated: 2025-01-27
 */

export interface SportCategory {
  key: string;
  name: string;
  emoji: string;
  prefixes: string[]; // Sport key prefixes that belong to this category
  tier: 1 | 2 | 3; // 1 = primary (Football, Basketball, Baseball), 2 = secondary, 3 = tertiary
}

/**
 * Sport categories with their key prefixes.
 * A sport key is matched to the first category whose prefix it starts with.
 */
export const SPORT_CATEGORIES: SportCategory[] = [
  // Tier 1: Primary sports (most users care about these)
  {
    key: "football",
    name: "Football",
    emoji: "🏈",
    prefixes: ["americanfootball_"],
    tier: 1,
  },
  {
    key: "basketball",
    name: "Basketball",
    emoji: "🏀",
    prefixes: ["basketball_"],
    tier: 1,
  },
  {
    key: "baseball",
    name: "Baseball",
    emoji: "⚾",
    prefixes: ["baseball_"],
    tier: 1,
  },
  // Tier 2: Secondary sports (popular but niche)
  {
    key: "hockey",
    name: "Hockey",
    emoji: "🏒",
    prefixes: ["icehockey_"],
    tier: 2,
  },
  {
    key: "mma",
    name: "MMA",
    emoji: "🥋",
    prefixes: ["mma_"],
    tier: 2,
  },
  {
    key: "boxing",
    name: "Boxing",
    emoji: "🥊",
    prefixes: ["boxing_"],
    tier: 2,
  },
  {
    key: "golf",
    name: "Golf",
    emoji: "⛳",
    prefixes: ["golf_"],
    tier: 2,
  },
  {
    key: "tennis",
    name: "Tennis",
    emoji: "🎾",
    prefixes: ["tennis_"],
    tier: 2,
  },
  // Tier 2: International sports
  {
    key: "soccer",
    name: "Soccer",
    emoji: "⚽",
    prefixes: ["soccer_"],
    tier: 2,
  },
  {
    key: "cricket",
    name: "Cricket",
    emoji: "🏏",
    prefixes: ["cricket_"],
    tier: 2,
  },
  {
    key: "rugby",
    name: "Rugby",
    emoji: "🏉",
    prefixes: ["rugbyleague_", "rugbyunion_"],
    tier: 2,
  },
  {
    key: "aussierules",
    name: "AFL",
    emoji: "🏈",
    prefixes: ["aussierules_"],
    tier: 2,
  },
  // Tier 2: Beyond Sports (high-volume prediction market categories)
  {
    key: "politics",
    name: "Politics",
    emoji: "🗳️",
    prefixes: ["politics_"],
    tier: 2,
  },
  {
    key: "entertainment",
    name: "Entertainment",
    emoji: "🎬",
    prefixes: ["entertainment_"],
    tier: 2,
  },
  {
    key: "crypto",
    name: "Crypto",
    emoji: "₿",
    prefixes: ["crypto_"],
    tier: 2,
  },
  // Tier 3: Tertiary sports (niche audience)
  {
    key: "esports",
    name: "Esports",
    emoji: "🎮",
    prefixes: ["esports_"],
    tier: 3,
  },
  {
    key: "lacrosse",
    name: "Lacrosse",
    emoji: "🥍",
    prefixes: ["lacrosse_"],
    tier: 3,
  },
  {
    key: "motorsport",
    name: "Motorsport",
    emoji: "🏎️",
    prefixes: ["motorsport_", "racing_"],
    tier: 3,
  },
  {
    key: "horse_racing",
    name: "Horse Racing",
    emoji: "🏇",
    prefixes: ["horseracing_"],
    tier: 3,
  },
  {
    key: "olympics",
    name: "Olympics",
    emoji: "🏅",
    prefixes: ["olympics_"],
    tier: 3,
  },
  {
    key: "chess",
    name: "Chess",
    emoji: "♟️",
    prefixes: ["chess_"],
    tier: 3,
  },
  {
    key: "poker",
    name: "Poker",
    emoji: "🃏",
    prefixes: ["poker_"],
    tier: 3,
  },
  {
    key: "darts",
    name: "Darts",
    emoji: "🎯",
    prefixes: ["darts_"],
    tier: 3,
  },
  // Non-sports categories (from prediction markets)
  {
    key: "economics",
    name: "Economics",
    emoji: "📊",
    prefixes: ["economics_"],
    tier: 3,
  },
  {
    key: "tech",
    name: "Tech & Science",
    emoji: "🔬",
    prefixes: ["tech_"],
    tier: 3,
  },
  {
    key: "weather",
    name: "Weather",
    emoji: "🌤️",
    prefixes: ["weather_"],
    tier: 3,
  },
  {
    key: "health",
    name: "Health",
    emoji: "🏥",
    prefixes: ["health_"],
    tier: 3,
  },
  {
    key: "geopolitics",
    name: "Geopolitics",
    emoji: "🌍",
    prefixes: ["geopolitics_"],
    tier: 3,
  },
  {
    key: "legal",
    name: "Legal",
    emoji: "⚖️",
    prefixes: ["legal_"],
    tier: 3,
  },
  {
    key: "culture",
    name: "Culture",
    emoji: "🎭",
    prefixes: ["culture_"],
    tier: 3,
  },
  // Other category is a catch-all (handled in code, not here)
];

/**
 * League tiers for prioritizing major leagues.
 * 1 = Major pro league (NFL, NBA, MLB, NHL)
 * 2 = Major college or secondary pro (NCAAF, NCAAB, WNBA)
 * 3 = Minor leagues and international
 */
export const LEAGUE_TIERS: Record<string, 1 | 2 | 3> = {
  // Football
  americanfootball_nfl: 1,
  americanfootball_ncaaf: 2,
  americanfootball_cfl: 3,
  americanfootball_xfl: 3,
  americanfootball_ufl: 3,
  // Basketball
  basketball_nba: 1,
  basketball_ncaab: 2,
  basketball_wnba: 2,
  basketball_wncaab: 3,
  basketball_euroleague: 3,
  basketball_nbl: 3,
  // Baseball
  baseball_mlb: 1,
  baseball_ncaa: 3,
  baseball_npb: 3,
  baseball_kbo: 3,
  // Hockey
  icehockey_nhl: 1,
  icehockey_ahl: 3,
  icehockey_khl: 3,
  icehockey_shl: 3,
  // MMA/Boxing
  mma_ufc: 2,
  mma_mixed_martial_arts: 2,
  boxing_boxing: 2,
  // Golf
  golf_pga_tour: 2,
  golf_masters_tournament: 2,
  golf_pga_championship: 2,
  golf_us_open: 2,
  golf_the_open: 2,
  // Tennis
  tennis_atp_aus_open: 2,
  tennis_atp_wimbledon: 2,
  tennis_atp_us_open: 2,
  tennis_atp_french_open: 2,
};

/**
 * Get league tier (default to 3 for unknown leagues)
 */
export function getLeagueTier(leagueKey: string): 1 | 2 | 3 {
  return LEAGUE_TIERS[leagueKey] ?? 3;
}

/**
 * Known league display names.
 * If a league isn't here, we generate a display name from the key.
 */
export const LEAGUE_DISPLAY: Record<string, string> = {
  // Football
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAAF",
  americanfootball_cfl: "CFL",
  americanfootball_xfl: "XFL",
  americanfootball_ufl: "UFL",
  // Basketball
  basketball_nba: "NBA",
  basketball_ncaab: "NCAAB",
  basketball_wnba: "WNBA",
  basketball_wncaab: "WNCAAB",
  basketball_euroleague: "EuroLeague",
  basketball_nbl: "NBL",
  basketball_nba_championship_winner: "NBA Finals",
  basketball_ncaab_championship_winner: "March Madness",
  // Baseball
  baseball_mlb: "MLB",
  baseball_ncaa: "NCAA Baseball",
  baseball_npb: "NPB",
  baseball_kbo: "KBO",
  baseball_mlb_world_series_winner: "World Series",
  // Hockey
  icehockey_nhl: "NHL",
  icehockey_ahl: "AHL",
  icehockey_khl: "KHL",
  icehockey_shl: "SHL",
  icehockey_liiga: "Liiga",
  icehockey_mestis: "Mestis",
  icehockey_sweden_hockey_league: "SHL",
  icehockey_sweden_allsvenskan: "Allsvenskan",
  icehockey_nhl_championship_winner: "Stanley Cup",
  // MMA
  mma_mixed_martial_arts: "MMA",
  mma_ufc: "UFC",
  // Boxing
  boxing_boxing: "Boxing",
  // Golf
  golf_pga_championship: "PGA Championship",
  golf_pga_championship_winner: "PGA Championship",
  golf_masters_tournament: "Masters",
  golf_masters_tournament_winner: "Masters",
  golf_us_open: "US Open",
  golf_us_open_winner: "US Open",
  golf_the_open: "The Open",
  golf_the_open_championship_winner: "The Open",
  golf_pga_tour: "PGA Tour",
  // Tennis
  tennis_atp_aus_open: "Australian Open",
  tennis_atp_aus_open_singles: "Australian Open (ATP)",
  tennis_wta_aus_open_singles: "Australian Open (WTA)",
  tennis_atp_us_open: "US Open",
  tennis_atp_us_open_singles: "US Open (ATP)",
  tennis_wta_us_open_singles: "US Open (WTA)",
  tennis_atp_wimbledon: "Wimbledon",
  tennis_atp_wimbledon_singles: "Wimbledon (ATP)",
  tennis_wta_wimbledon_singles: "Wimbledon (WTA)",
  tennis_atp_french_open: "French Open",
  tennis_atp_french_open_singles: "French Open (ATP)",
  tennis_wta_french_open_singles: "French Open (WTA)",
  // Rugby
  rugbyleague_nrl: "NRL",
  rugbyleague_nrl_state_of_origin: "State of Origin",
  rugbyunion_six_nations: "Six Nations",
  rugbyunion_rugby_world_cup: "Rugby World Cup",
  // AFL
  aussierules_afl: "AFL",
  // Cricket
  cricket_international_t20: "International T20",
  cricket_ipl: "IPL",
  cricket_big_bash: "Big Bash",
  // Lacrosse
  lacrosse_ncaa: "NCAA Lacrosse",
  lacrosse_pll: "PLL",
  // Politics
  politics_us_presidential_election_winner: "US Election",
  politics_us_presidential_election: "US Election",
  // Esports
  esports_lol: "League of Legends",
  esports_csgo: "CS:GO",
  esports_dota2: "Dota 2",
  esports_valorant: "Valorant",
};

/**
 * Get category for a league key based on prefix matching.
 */
export function getCategoryForLeague(leagueKey: string): SportCategory | undefined {
  return SPORT_CATEGORIES.find((cat) =>
    cat.prefixes.some((prefix) => leagueKey.startsWith(prefix))
  );
}

/**
 * Pattern-based sport detection.
 * Uses regex patterns for more robust matching that doesn't require exact keyword lists.
 * Order matters - more specific patterns should come first.
 */
const SPORT_PATTERNS: Array<{ pattern: RegExp; category: string }> = [
  // Baseball - Match AL/NL awards, MVP, Cy Young, etc.
  { pattern: /\b(mlb|world.series)\b/i, category: "baseball" },
  { pattern: /\b(al|nl)\s+(mvp|cy.young|rookie|reliever|hank.aaron|manager|comeback|batting|home.run|era)\b/i, category: "baseball" },
  { pattern: /\bcy.young\s+(award|winner)\b/i, category: "baseball" },
  { pattern: /\bamerican.league\b/i, category: "baseball" },
  { pattern: /\bnational.league\b/i, category: "baseball" },
  { pattern: /\bpro.baseball\b/i, category: "baseball" },
  { pattern: /\bhome.run.derby\b/i, category: "baseball" },
  { pattern: /\bbaseball\b/i, category: "baseball" },

  // Football - Match college football, NFL, Super Bowl, Heisman, etc.
  { pattern: /\b(nfl|super.bowl)\b/i, category: "football" },
  { pattern: /\bcollege.football\b/i, category: "football" },
  { pattern: /\bncaaf\b/i, category: "football" },
  { pattern: /\bheisman\b/i, category: "football" },
  { pattern: /\b(afc|nfc)\s+(championship|winner|east|west|north|south)\b/i, category: "football" },
  { pattern: /\bpro.football\b/i, category: "football" },
  // College conferences
  { pattern: /\b(acc|sec|big.ten|big.12|big.east|pac.12|pac.10|mountain.west|sun.belt|mac|aac|c.usa)\s+(championship|football|winner)\b/i, category: "football" },
  // College bowl games
  { pattern: /\b(rose|sugar|orange|cotton|peach|fiesta|citrus|alamo|holiday|liberty|independence|armed.forces|sun|gator|outback|music.city).bowl\b/i, category: "football" },
  // College Football Playoff
  { pattern: /\bcfp\b/i, category: "football" },
  { pattern: /\bpro.bowl\b/i, category: "football" },
  // NFL awards
  { pattern: /\b(offensive|defensive).player.of.the.year\b/i, category: "football" },
  { pattern: /\bnfl.mvp\b/i, category: "football" },

  // Basketball - Must come after football patterns to avoid false matches
  { pattern: /\b(nba|ncaab|wnba)\b/i, category: "basketball" },
  { pattern: /\bmarch.madness\b/i, category: "basketball" },
  { pattern: /\b(eastern|western).conference\b/i, category: "basketball" },
  { pattern: /\bpro.basketball\b/i, category: "basketball" },
  { pattern: /\b(final.four|sweet.sixteen|sweet.16|elite.eight|elite.8)\b/i, category: "basketball" },
  { pattern: /\bncaa.tournament\b/i, category: "basketball" },
  // NBA awards
  { pattern: /\b(nba.mvp|finals.mvp|nba.finals)\b/i, category: "basketball" },
  { pattern: /\b(defensive.player|sixth.man|most.improved|rookie.of.the.year)\b/i, category: "basketball" },
  { pattern: /\b(slam.dunk|dunk.contest|three.point.contest)\b/i, category: "basketball" },
  // College basketball conferences
  { pattern: /\b(big.east|big.12|acc|sec|big.ten|pac.12).basketball\b/i, category: "basketball" },
  { pattern: /\bbasketball\b/i, category: "basketball" },

  // Hockey - NHL and awards
  { pattern: /\b(nhl|stanley.cup)\b/i, category: "hockey" },
  { pattern: /\b(hart.trophy|vezina|calder|conn.smythe|norris.trophy|selke|lady.byng|rocket.richard)\b/i, category: "hockey" },
  { pattern: /\bhockey\b/i, category: "hockey" },

  // Golf - Major championships and tours
  { pattern: /\b(pga|masters|british.open|the.open|ryder.cup)\b/i, category: "golf" },
  { pattern: /\b(lpga|liv.golf|dp.world)\b/i, category: "golf" },
  { pattern: /\bus.women.?s?.open\b/i, category: "golf" },  // US Women's Open (golf)
  { pattern: /\bgolf\b/i, category: "golf" },

  // Tennis - Majors and tournaments
  { pattern: /\b(wimbledon|french.open|australian.open|atp|wta)\b/i, category: "tennis" },
  { pattern: /\b(davis.cup|billie.jean.king.cup|fed.cup|laver.cup)\b/i, category: "tennis" },
  { pattern: /\btennis\b/i, category: "tennis" },

  // Soccer - Match Ballon d'Or, PFA, Premier League, etc.
  { pattern: /\b(ballon.d.or|pfa.player|epl|premier.league|champions.league|mls|la.liga|bundesliga|serie.a|nwsl)\b/i, category: "soccer" },
  { pattern: /\b(major.league.soccer|europa.league|fa.cup|carabao.cup|league.cup|community.shield)\b/i, category: "soccer" },
  { pattern: /\b(golden.boot|golden.ball|golden.glove)\b/i, category: "soccer" },  // Soccer awards
  { pattern: /\bworld.cup\b(?!.*college)/i, category: "soccer" }, // World Cup but not "College Football"
  { pattern: /\bworld.cup.qualifier\b/i, category: "soccer" },
  { pattern: /\b(copa.america|euro.20\d\d|euros|uefa.euro|concacaf|nations.league)\b/i, category: "soccer" },
  { pattern: /\bsoccer\b/i, category: "soccer" },

  // Cricket
  { pattern: /\b(ipl|cricket|t20|test.match|ashes|bbl|big.bash)\b/i, category: "cricket" },

  // Rugby
  { pattern: /\b(rugby|six.nations|tri.nations|super.rugby|nrl)\b/i, category: "rugby" },

  // Australian Rules
  { pattern: /\b(afl|australian.football|aussie.rules)\b/i, category: "aussierules" },

  // Horse Racing - Must be before motorsport to avoid "racing" false match
  { pattern: /\b(kentucky.derby|preakness|belmont.stakes|breeders.cup|triple.crown)\b/i, category: "horse_racing" },
  { pattern: /\b(horse.racing|thoroughbred|jockey)\b/i, category: "horse_racing" },

  // MMA
  { pattern: /\b(ufc|mma|bellator|pfl|one.championship)\b/i, category: "mma" },

  // Boxing
  { pattern: /\bboxing\b/i, category: "boxing" },

  // Motorsport
  { pattern: /\b(formula.1|f1|nascar|indycar|motogp|wrc)\b/i, category: "motorsport" },
  { pattern: /\b(daytona.500|indy.500|le.mans|monaco.grand.prix)\b/i, category: "motorsport" },
  { pattern: /\b(racing|motorsport)\b/i, category: "motorsport" },

  // Politics
  { pattern: /\b(election|president|congress|senate|governor|presidential|democrat|republican|trump|biden)\b/i, category: "politics" },
  { pattern: /\bhouse.race\b/i, category: "politics" },
  { pattern: /\bwhich.party.will.win\b/i, category: "politics" },
  { pattern: /\b(gubernatorial|midterm|primary.election|electoral.college|ballot.measure)\b/i, category: "politics" },

  // Esports
  { pattern: /\b(lol|league.of.legends|csgo|cs2|cs.go|dota|valorant|esports|overwatch.league)\b/i, category: "esports" },

  // Entertainment
  { pattern: /\b(oscar|emmy|grammy|golden.globe|academy.award|entertainer|box.office|movie|film|music|spotify|album)\b/i, category: "entertainment" },
  { pattern: /\b(tv.show|television|reality|bachelor|bachelorette|portnoy|youtube|tiktok|influencer)\b/i, category: "entertainment" },

  // Olympics - explicit keyword + uniquely-Olympic winter sports
  { pattern: /\b(olympic|olympics|paralympic)\b/i, category: "olympics" },
  { pattern: /\bcurling\b/i, category: "olympics" },
  { pattern: /\bfigure.skating\b/i, category: "olympics" },
  { pattern: /\bspeed.skating\b/i, category: "olympics" },
  { pattern: /\bshort.track\b/i, category: "olympics" },
  { pattern: /\bfreestyle.skiing\b/i, category: "olympics" },
  { pattern: /\balpine.skiing\b/i, category: "olympics" },
  { pattern: /\bcross.country.skiing\b/i, category: "olympics" },
  { pattern: /\bski.jumping\b/i, category: "olympics" },
  { pattern: /\bski.mountaineering\b/i, category: "olympics" },
  { pattern: /\bnordic.combined\b/i, category: "olympics" },
  { pattern: /\bbiathlon\b/i, category: "olympics" },
  { pattern: /\b(bobsled|bobsleigh)\b/i, category: "olympics" },
  { pattern: /\b(luge|skeleton)\b/i, category: "olympics" },
  { pattern: /\bgold.medal\b/i, category: "olympics" },

  // Lacrosse
  { pattern: /\b(lacrosse|tewaaraton|pll|premier.lacrosse)\b/i, category: "lacrosse" },

  // Chess
  { pattern: /\bchess\b/i, category: "chess" },

  // Poker
  { pattern: /\b(wsop|poker|world.series.of.poker)\b/i, category: "poker" },

  // Darts
  { pattern: /\b(darts?|pdc|bdo|premier.league.darts|world.darts|world.matchplay)\b/i, category: "darts" },
];

/**
 * Legacy keyword map for backwards compatibility.
 * Note: SPORT_PATTERNS above is now the primary matching mechanism.
 */
const FUTURES_KEYWORD_MAP: Record<string, string> = {
  // Basketball
  nba: "basketball",
  ncaab: "basketball",
  wnba: "basketball",
  march_madness: "basketball",
  // Football
  nfl: "football",
  ncaaf: "football",
  super_bowl: "football",
  // Baseball
  mlb: "baseball",
  world_series: "baseball",
  // Hockey
  nhl: "hockey",
  stanley_cup: "hockey",
  // Golf (us_open is ambiguous, handled separately)
  pga: "golf",
  masters: "golf",
  the_open: "golf",
  british_open: "golf",
  ryder_cup: "golf",
  // Tennis (us_open is ambiguous, handled separately)
  wimbledon: "tennis",
  french_open: "tennis",
  australian_open: "tennis",
  atp: "tennis",
  wta: "tennis",
  // MMA
  ufc: "mma",
  // Motorsport
  f1: "motorsport",
  formula_1: "motorsport",
  nascar: "motorsport",
  indycar: "motorsport",
  // Soccer
  epl: "soccer",
  premier_league: "soccer",
  champions_league: "soccer",
  world_cup: "soccer",
  mls: "soccer",
  la_liga: "soccer",
  bundesliga: "soccer",
  serie_a: "soccer",
  // Politics
  election: "politics",
  president: "politics",
  // Esports
  lol: "esports",
  csgo: "esports",
  dota: "esports",
  valorant: "esports",
};

/**
 * Known athletes by sport for disambiguation.
 * When a market name is ambiguous (e.g., "US Open"), we check outcomes
 * for known athlete names to determine the sport.
 */
const KNOWN_GOLFERS = new Set([
  // Top current male golfers
  "scottie scheffler", "rory mcilroy", "bryson dechambeau", "jon rahm",
  "xander schauffele", "collin morikawa", "viktor hovland", "patrick cantlay",
  "jordan spieth", "justin thomas", "brooks koepka", "dustin johnson",
  "tiger woods", "phil mickelson", "hideki matsuyama", "cameron smith",
  "tony finau", "max homa", "wyndham clark", "brian harman", "matt fitzpatrick",
  "tommy fleetwood", "shane lowry", "adam scott", "rickie fowler", "sahith theegala",
  "ludvig aberg", "tom kim", "sungjae im", "cameron young", "keegan bradley",
  "russell henley", "sam burns", "corey conners", "tyrrell hatton", "min woo lee",
  // LIV golfers
  "dustin johnson", "cameron smith", "brooks koepka", "phil mickelson",
  "sergio garcia", "patrick reed", "talor gooch", "joaquin niemann",
  // Top female golfers (LPGA)
  "nelly korda", "lydia ko", "jin young ko", "minjee lee", "lexi thompson",
  "danielle kang", "brooke henderson", "atthaya thitikul", "rose zhang",
  "charley hull", "lilia vu", "hannah green", "celine boutier",
]);

const KNOWN_TENNIS_PLAYERS = new Set([
  // Top ATP players
  "novak djokovic", "carlos alcaraz", "jannik sinner", "daniil medvedev",
  "alexander zverev", "andrey rublev", "stefanos tsitsipas", "holger rune",
  "taylor fritz", "tommy paul", "hubert hurkacz", "casper ruud", "grigor dimitrov",
  "felix auger-aliassime", "ben shelton", "alex de minaur", "frances tiafoe",
  "ugo humbert", "karen khachanov", "sebastian korda", "arthur fils",
  "lorenzo musetti", "matteo berrettini", "denis shapovalov", "nick kyrgios",
  // Top WTA players
  "iga swiatek", "aryna sabalenka", "coco gauff", "jessica pegula", "elena rybakina",
  "ons jabeur", "maria sakkari", "qinwen zheng", "emma raducanu", "naomi osaka",
  "caroline garcia", "madison keys", "daria kasatkina", "petra kvitova",
  "jelena ostapenko", "veronika kudermetova", "donna vekic", "liudmila samsonova",
  "beatriz haddad maia", "danielle collins", "marketa vondrousova",
  // Legends (still relevant for markets)
  "rafael nadal", "roger federer", "serena williams", "venus williams",
  "andy murray",
]);

/**
 * Get category for a futures market based on sport key and market name.
 * Uses a multi-stage approach:
 * 1. Backend LLM category (if available, already computed)
 * 2. Standard prefix matching on sport key
 * 3. Regex pattern matching on market name (handles "College Football", "AL MVP", etc.)
 * 4. Legacy keyword matching as fallback
 * 5. Athlete name detection for ambiguous cases (e.g., "US Open")
 */
export function getCategoryForFutures(
  sportKey: string | null,
  marketName?: string | null,
  outcomeNames?: string[],
  llmSportCategory?: string | null
): SportCategory | undefined {
  // First check if backend already categorized via LLM
  if (llmSportCategory) {
    const llmCategory = SPORT_CATEGORIES.find((cat) => cat.key === llmSportCategory);
    if (llmCategory) return llmCategory;
  }
  // First try standard prefix matching on sport key
  if (sportKey) {
    const category = getCategoryForLeague(sportKey);
    if (category) return category;
  }

  // Build searchable text from sport key and market name
  const searchText = [sportKey, marketName].filter(Boolean).join(" ");

  // Try regex pattern matching (most reliable for complex names)
  for (const { pattern, category: categoryKey } of SPORT_PATTERNS) {
    if (pattern.test(searchText)) {
      return SPORT_CATEGORIES.find((cat) => cat.key === categoryKey);
    }
  }

  // Legacy keyword matching as fallback
  const normalizedText = searchText.toLowerCase().replace(/[^a-z0-9]/g, "_");
  for (const [keyword, categoryKey] of Object.entries(FUTURES_KEYWORD_MAP)) {
    if (normalizedText.includes(keyword)) {
      return SPORT_CATEGORIES.find((cat) => cat.key === categoryKey);
    }
  }

  // Handle ambiguous cases like "US Open" by checking outcome names
  if (normalizedText.includes("us_open") || normalizedText.includes("open")) {
    if (outcomeNames && outcomeNames.length > 0) {
      const normalizedOutcomes = outcomeNames.map((n) => n.toLowerCase());
      const golfersList = Array.from(KNOWN_GOLFERS);
      const tennisPlayersList = Array.from(KNOWN_TENNIS_PLAYERS);

      // Check for golfers (by full name or last name)
      for (const outcome of normalizedOutcomes) {
        if (KNOWN_GOLFERS.has(outcome)) {
          return SPORT_CATEGORIES.find((cat) => cat.key === "golf");
        }
        // Also check last names
        for (const golfer of golfersList) {
          const lastName = golfer.split(" ").pop();
          if (lastName && outcome.includes(lastName)) {
            return SPORT_CATEGORIES.find((cat) => cat.key === "golf");
          }
        }
      }

      // Check for tennis players
      for (const outcome of normalizedOutcomes) {
        if (KNOWN_TENNIS_PLAYERS.has(outcome)) {
          return SPORT_CATEGORIES.find((cat) => cat.key === "tennis");
        }
        for (const player of tennisPlayersList) {
          const lastName = player.split(" ").pop();
          if (lastName && outcome.includes(lastName)) {
            return SPORT_CATEGORIES.find((cat) => cat.key === "tennis");
          }
        }
      }
    }
  }

  return undefined;
}

/**
 * Get display name for a league.
 * Falls back to generating a readable name from the key.
 */
export function getLeagueDisplay(leagueKey: string): string {
  if (LEAGUE_DISPLAY[leagueKey]) {
    return LEAGUE_DISPLAY[leagueKey];
  }

  // Generate a display name from the key
  // e.g., "basketball_nba" -> "NBA", "tennis_atp_aus_open" -> "ATP Aus Open"
  const parts = leagueKey.split("_");
  if (parts.length > 1) {
    // Remove the first part (category) and capitalize the rest
    const displayParts = parts.slice(1).map((part) =>
      part.toUpperCase()
    );
    return displayParts.join(" ");
  }
  return leagueKey.toUpperCase();
}

/**
 * Get full display with emoji for a league.
 */
export function getLeagueDisplayWithEmoji(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  const leagueName = getLeagueDisplay(leagueKey);
  return category ? `${category.emoji} ${leagueName}` : `🏆 ${leagueName}`;
}

/**
 * Get emoji for a sport category or default trophy for unknown.
 */
export function getEmojiForLeague(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  return category?.emoji || "🏆";
}

/**
 * Get category name for a league, or "Other" for unknown.
 */
export function getCategoryName(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  return category?.name || "Other";
}

// Build a fast lookup map from category key to SportCategory
const _CATEGORY_BY_KEY = new Map<string, SportCategory>(
  SPORT_CATEGORIES.map((c) => [c.key, c]),
);

/**
 * Look up a SportCategory by its key (e.g., "darts", "basketball").
 * Returns undefined for unknown keys.
 */
export function getCategoryByKey(key: string): SportCategory | undefined {
  return _CATEGORY_BY_KEY.get(key.toLowerCase());
}

/**
 * Get emoji for a category key (e.g., "darts" → "🎯").
 * Falls back to "🏆" for unknown categories.
 */
export function getEmojiForCategory(categoryKey: string): string {
  return _CATEGORY_BY_KEY.get(categoryKey.toLowerCase())?.emoji || "🏆";
}

/**
 * Get display name for a category key (e.g., "horse_racing" → "Horse Racing").
 * Falls back to capitalized key for unknown categories.
 */
export function getNameForCategory(categoryKey: string): string {
  const cat = _CATEGORY_BY_KEY.get(categoryKey.toLowerCase());
  if (cat) return cat.name;
  return categoryKey.charAt(0).toUpperCase() + categoryKey.slice(1).replace(/_/g, " ");
}

/**
 * Group an array of league keys by their category.
 * Returns a map of categoryKey -> leagueKeys[]
 */
export function groupLeaguesByCategory(leagueKeys: string[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();

  for (const leagueKey of leagueKeys) {
    const category = getCategoryForLeague(leagueKey);
    const categoryKey = category?.key || "other";

    if (!groups.has(categoryKey)) {
      groups.set(categoryKey, []);
    }
    groups.get(categoryKey)!.push(leagueKey);
  }

  return groups;
}

/**
 * Get all unique categories present in a list of league keys.
 * Includes "other" category if there are uncategorized leagues.
 */
export function getActiveCategoriesFromLeagues(leagueKeys: string[]): SportCategory[] {
  const categorySet = new Set<string>();
  let hasOther = false;

  for (const leagueKey of leagueKeys) {
    const category = getCategoryForLeague(leagueKey);
    if (category) {
      categorySet.add(category.key);
    } else {
      hasOther = true;
    }
  }

  const activeCategories = SPORT_CATEGORIES.filter((cat) => categorySet.has(cat.key));

  if (hasOther) {
    activeCategories.push({
      key: "other",
      name: "Other",
      emoji: "🏆",
      prefixes: [],
      tier: 3,
    });
  }

  return activeCategories;
}
// =============================================================================
// Subcategory grouping for large futures categories
// =============================================================================

/**
 * Display names for subcategory tags.
 * Tags not listed here get auto-formatted (e.g., "fed_rate" → "Fed Rate").
 */
const SUBCATEGORY_DISPLAY_NAMES: Record<string, string> = {
  // ── Crypto assets ──
  bitcoin: "Bitcoin",
  ethereum: "Ethereum",
  solana: "Solana",
  dogecoin: "Dogecoin",
  xrp: "XRP",
  cardano: "Cardano",
  litecoin: "Litecoin",
  polkadot: "Polkadot",
  chainlink: "Chainlink",
  avalanche: "Avalanche",
  polygon: "Polygon",
  uniswap: "Uniswap",
  cosmos: "Cosmos",
  bnb: "BNB",
  tron: "Tron",
  shiba_inu: "Shiba Inu",
  toncoin: "Toncoin",
  sui: "Sui",
  aptos: "Aptos",
  pepe: "Pepe",
  near: "NEAR",
  arbitrum: "Arbitrum",
  optimism: "Optimism",
  celestia: "Celestia",
  jupiter: "Jupiter",
  render: "Render",
  stacks: "Stacks",
  worldcoin: "Worldcoin",
  // ── Crypto topics ──
  crypto_etf: "Crypto ETFs",
  defi: "DeFi",
  nft: "NFTs",
  stablecoin: "Stablecoins",
  meme_coin: "Meme Coins",
  halving: "Halving",
  crypto_market_cap: "Market Cap",
  // ── Politicians / public figures ──
  trump: "Trump",
  biden: "Biden",
  harris: "Harris",
  desantis: "DeSantis",
  newsom: "Newsom",
  powell: "Powell",
  elon_musk: "Elon Musk",
  vance: "Vance",
  obama: "Obama",
  pence: "Pence",
  rfk: "RFK Jr.",
  haley: "Haley",
  ramaswamy: "Ramaswamy",
  buttigieg: "Buttigieg",
  pelosi: "Pelosi",
  mcconnell: "McConnell",
  aoc: "AOC",
  putin: "Putin",
  zelensky: "Zelensky",
  xi_jinping: "Xi Jinping",
  starmer: "Starmer",
  macron: "Macron",
  trudeau: "Trudeau",
  modi: "Modi",
  // ── Political topics ──
  elections: "Elections",
  governors: "Governors",
  scotus: "Supreme Court",
  congress: "Congress",
  senate: "Senate",
  house: "House",
  cabinet: "Cabinet",
  impeachment: "Impeachment",
  executive_orders: "Executive Orders",
  approval_rating: "Approval Ratings",
  pardons: "Pardons",
  government_shutdown: "Gov't Shutdown",
  // ── Geopolitics ──
  nato: "NATO",
  ukraine: "Ukraine",
  russia: "Russia",
  china: "China",
  taiwan: "Taiwan",
  israel: "Israel",
  gaza: "Gaza",
  north_korea: "North Korea",
  iran: "Iran",
  // ── Economics / finance ──
  fed: "Federal Reserve",
  inflation: "Inflation",
  gdp: "GDP",
  recession: "Recession",
  unemployment: "Unemployment",
  tariffs: "Tariffs",
  debt_ceiling: "Debt Ceiling",
  sp500: "S&P 500",
  nasdaq: "NASDAQ",
  dow: "Dow Jones",
  treasury: "Treasury",
  oil: "Oil",
  gold: "Gold",
  // ── Weather ──
  hurricanes: "Hurricanes",
  tornadoes: "Tornadoes",
  wildfires: "Wildfires",
  earthquakes: "Earthquakes",
  temperature: "Temperature",
  snowfall: "Snowfall",
  rainfall: "Rainfall",
  // ── Entertainment ──
  oscars: "Oscars",
  grammys: "Grammys",
  emmys: "Emmys",
  tonys: "Tonys",
  golden_globes: "Golden Globes",
  nobel: "Nobel Prize",
  billboard: "Billboard",
  box_office: "Box Office",
  survivor: "Survivor",
  bachelor: "Bachelor",
  real_housewives: "Real Housewives",
  snl: "SNL",
  jeopardy: "Jeopardy!",
  wheel_of_fortune: "Wheel of Fortune",
  love_is_blind: "Love Is Blind",
  // ── Sports events ──
  super_bowl: "Super Bowl",
  world_series: "World Series",
  march_madness: "March Madness",
  stanley_cup: "Stanley Cup",
  nba_finals: "NBA Finals",
  olympics: "Olympics",
  // ── Market types ──
  mvp: "MVP",
  rookie_of_year: "Rookie of the Year",
  coach_of_year: "Coach of the Year",
  championship: "Championship",
  game_prop: "Game Props",
  // ── Companies / tech ──
  tesla: "Tesla",
  spacex: "SpaceX",
  openai: "OpenAI",
  google: "Google",
  apple: "Apple",
  meta: "Meta",
  nvidia: "NVIDIA",
  microsoft: "Microsoft",
  amazon: "Amazon",
  tiktok: "TikTok",
  // ── AI / tech topics ──
  ai: "AI",
  agi: "AGI",
  self_driving: "Self-Driving",
};

/**
 * Tags that should be excluded from subcategory grouping.
 * These are too generic or are the parent category itself.
 */
const EXCLUDED_SUBCATEGORY_TAGS = new Set([
  "crypto", "politics", "economics", "tech", "entertainment",
  "football", "basketball", "baseball", "hockey", "golf", "tennis",
  "soccer", "mma", "boxing", "motorsports", "esports", "rugby",
  "cricket", "aussierules", "horse_racing", "olympics", "lacrosse",
  "chess", "poker", "darts", "other", "weather", "health",
  "geopolitics", "legal", "culture",
]);

/**
 * Get the best subcategory for a futures market from its category_tags.
 * Returns the most specific tag that isn't the parent category itself.
 */
export function getSubcategory(
  categoryTags: string[] | undefined,
  parentCategory: string,
): string | null {
  if (!categoryTags || categoryTags.length === 0) return null;

  // Find the first tag that's specific (not a parent category)
  for (const tag of categoryTags) {
    const lower = tag.toLowerCase();
    if (lower === parentCategory.toLowerCase()) continue;
    if (EXCLUDED_SUBCATEGORY_TAGS.has(lower)) continue;
    return lower;
  }
  return null;
}

/**
 * Get display name for a subcategory tag.
 */
export function getSubcategoryDisplayName(tag: string): string {
  const display = SUBCATEGORY_DISPLAY_NAMES[tag];
  if (display) return display;
  // Auto-format: "fed_rate" → "Fed Rate"
  return tag
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Minimum number of futures in a category before subcategory grouping kicks in.
 */
export const SUBCATEGORY_THRESHOLD = 10;

export interface SubcategoryGroup {
  key: string;
  displayName: string;
  markets: FuturesMarket[];
}

/**
 * Group futures markets by subcategory within a parent category.
 * Returns subcategory groups sorted by market count (descending),
 * with an "Other" group for markets without a specific subcategory.
 */
export function groupBySubcategory(
  markets: FuturesMarket[],
  parentCategory: string,
): SubcategoryGroup[] {
  const groups = new Map<string, FuturesMarket[]>();

  for (const market of markets) {
    const sub = getSubcategory(market.category_tags, parentCategory);
    const key = sub ?? "_other";

    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(market);
  }

  // Convert to array and sort by count
  const result: SubcategoryGroup[] = [];
  groups.forEach((mktList, key) => {
    result.push({
      key,
      displayName: key === "_other" ? "Other" : getSubcategoryDisplayName(key),
      markets: mktList,
    });
  });

  // Sort: named groups by count desc, "_other" always last
  result.sort((a, b) => {
    if (a.key === "_other") return 1;
    if (b.key === "_other") return -1;
    return b.markets.length - a.markets.length;
  });

  return result;
}

/**
 * Calculate an excitement score for an event.
 * Higher scores = more exciting/important games that should surface first.
 *
 * Factors:
 * - Live games get high priority
 * - Close matchups (within 10% of 50/50) are exciting
 * - Starting soon (within 1 hour) gets boost
 * - Higher tier leagues get slight boost
 *
 * Returns a score from 0-100
 */
export function calculateExcitementScore(
  event: {
    status: "scheduled" | "live" | "completed" | "closed";
    commence_time: string;
    sport: string | null;
    current_odds?: {
      home_probability: number | null;
    };
  }
): number {
  let score = 0;

  // Live games: +50 points
  if (event.status === "live") {
    score += 50;
  }

  // Close games (within 10% of 50/50): +30 points max
  const homeProb = event.current_odds?.home_probability ?? 0.5;
  const closeness = 1 - Math.abs(homeProb - 0.5) * 2; // 1.0 = perfectly even, 0.0 = one-sided
  if (closeness > 0.8) {
    // Within 10% of 50/50
    score += 30 * closeness;
  }

  // Starting soon (within 1 hour): +15 points
  const now = new Date();
  const gameTime = new Date(event.commence_time);
  const hoursUntil = (gameTime.getTime() - now.getTime()) / (1000 * 60 * 60);
  if (hoursUntil > 0 && hoursUntil <= 1) {
    score += 15;
  } else if (hoursUntil > 1 && hoursUntil <= 3) {
    score += 5;
  }

  // League tier boost: Tier 1 = +5, Tier 2 = +2, Tier 3 = 0
  if (event.sport) {
    const tier = getLeagueTier(event.sport);
    if (tier === 1) score += 5;
    else if (tier === 2) score += 2;
  }

  return Math.min(100, score);
}

// Staleness thresholds for featured events
const STALE_ODDS_MINUTES = 30; // Odds not updated in 30 minutes = stale
const MAX_LIVE_HOURS = 4; // If "live" for more than 4 hours, needs review

/**
 * Check if a live event has stale data.
 * Returns true if data is stale or event needs review.
 */
function isEventStaleOrNeedsReview(
  event: {
    status: "scheduled" | "live" | "completed" | "closed";
    commence_time: string;
    current_odds?: {
      home_probability: number | null;
      captured_at?: string;
    };
  }
): boolean {
  if (event.status !== "live") return false;

  const now = new Date();
  const commenceTime = new Date(event.commence_time);
  const hoursSinceStart = (now.getTime() - commenceTime.getTime()) / (1000 * 60 * 60);

  // Check if event has been "live" for too long (>4 hours without completion)
  if (hoursSinceStart > MAX_LIVE_HOURS) {
    return true;
  }

  // Check if odds data is stale (not updated in 30+ minutes)
  if (event.current_odds?.captured_at) {
    const lastUpdate = new Date(event.current_odds.captured_at);
    const minutesSinceUpdate = (now.getTime() - lastUpdate.getTime()) / (1000 * 60);
    if (minutesSinceUpdate > STALE_ODDS_MINUTES) {
      return true;
    }
  }

  return false;
}

/**
 * Feature reason explains why an event appears in the featured section
 */
export type FeatureReason = "live" | "starting_soon" | "close_game" | null;

/**
 * Get the reason an event is featured, or null if not featured.
 * Returns: "live" | "starting_soon" | "close_game" | null
 */
export function getFeatureReason(
  event: {
    status: "scheduled" | "live" | "completed" | "closed";
    commence_time: string;
    current_odds?: {
      home_probability: number | null;
      captured_at?: string;
    };
  }
): FeatureReason {
  // Live games are featured ONLY if not stale/needs review
  if (event.status === "live") {
    return !isEventStaleOrNeedsReview(event) ? "live" : null;
  }

  const now = new Date();
  const gameTime = new Date(event.commence_time);
  const hoursUntil = (gameTime.getTime() - now.getTime()) / (1000 * 60 * 60);

  // Close games starting soon are featured
  const homeProb = event.current_odds?.home_probability ?? 0.5;
  const isClose = Math.abs(homeProb - 0.5) <= 0.1; // Within 10% of 50/50
  const startingSoon = hoursUntil > 0 && hoursUntil <= 3;

  if (isClose && startingSoon) {
    return "close_game";
  }

  // Games starting very soon (within 1 hour) are also featured
  if (hoursUntil > 0 && hoursUntil <= 1) {
    return "starting_soon";
  }

  return null;
}

/**
 * Determine if an event is "featured" (exciting enough to highlight)
 * Featured = Live (and not stale) OR (close game AND starting within 3 hours) OR starting within 1 hour
 */
export function isFeaturedEvent(
  event: {
    status: "scheduled" | "live" | "completed" | "closed";
    commence_time: string;
    current_odds?: {
      home_probability: number | null;
      captured_at?: string;
    };
  }
): boolean {
  return getFeatureReason(event) !== null;
}

/**
 * Format time until event starts in a human-friendly way
 */
export function formatTimeUntil(commenceTime: string): string {
  const now = new Date();
  const gameTime = new Date(commenceTime);
  const minutesUntil = (gameTime.getTime() - now.getTime()) / (1000 * 60);

  if (minutesUntil <= 0) return "Started";
  if (minutesUntil < 60) return `${Math.round(minutesUntil)}m`;
  if (minutesUntil < 180) {
    const hours = Math.floor(minutesUntil / 60);
    const mins = Math.round(minutesUntil % 60);
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${Math.round(minutesUntil / 60)}h`;
}

// Force rebuild Wed Jan 28 2026 - tiered polling update
