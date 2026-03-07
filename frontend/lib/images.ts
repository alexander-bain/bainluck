/**
 * Image enrichment APIs — ESPN headshots, Wikipedia, Flagpedia, CoinGecko.
 *
 * Client-side only — all APIs are free, no auth, CORS-friendly.
 * Images are cached in localStorage with 24h TTL (same pattern as tmdb.ts).
 */

const CACHE_PREFIX = "img_";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

// ============================================================================
// Cache helpers (same pattern as tmdb.ts)
// ============================================================================

interface CacheEntry<T> {
  data: T;
  ts: number;
}

function cacheGet<T>(key: string): T | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return undefined;
    const entry: CacheEntry<T> = JSON.parse(raw);
    if (Date.now() - entry.ts > CACHE_TTL_MS) {
      localStorage.removeItem(CACHE_PREFIX + key);
      return undefined;
    }
    return entry.data;
  } catch {
    return undefined;
  }
}

function cacheSet<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry<T> = { data, ts: Date.now() };
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(entry));
  } catch {
    // localStorage full or unavailable — silently fail
  }
}

// ============================================================================
// 1. ESPN Player Headshots
// ============================================================================

/**
 * Construct ESPN headshot URL from an ESPN player ID.
 * No API call needed — URL pattern is deterministic.
 */
export function espnHeadshotUrl(espnId: string, sport?: string): string {
  const s = sport || "nba";
  return `https://a.espncdn.com/i/headshots/${s}/players/full/${espnId}.png`;
}

/**
 * Construct ESPN team logo URL from a team ID.
 * No API call needed — URL pattern is deterministic.
 * Size: 500 (full), 100 (small)
 */
export function espnTeamLogoUrl(espnTeamId: string, sport: string = "nba", size: 100 | 500 = 100): string {
  return `https://a.espncdn.com/i/teamlogos/${sport}/${size}/${espnTeamId}.png`;
}

/**
 * Known ESPN team IDs for major North American teams.
 * Key format: "Team Name" (lowercased).
 */
const ESPN_TEAM_IDS: Record<string, { id: string; sport: string }> = {
  // NBA
  "atlanta hawks": { id: "1", sport: "nba" },
  "boston celtics": { id: "2", sport: "nba" },
  "brooklyn nets": { id: "17", sport: "nba" },
  "charlotte hornets": { id: "30", sport: "nba" },
  "chicago bulls": { id: "4", sport: "nba" },
  "cleveland cavaliers": { id: "5", sport: "nba" },
  "dallas mavericks": { id: "6", sport: "nba" },
  "denver nuggets": { id: "7", sport: "nba" },
  "detroit pistons": { id: "8", sport: "nba" },
  "golden state warriors": { id: "9", sport: "nba" },
  "houston rockets": { id: "10", sport: "nba" },
  "indiana pacers": { id: "11", sport: "nba" },
  "los angeles clippers": { id: "12", sport: "nba" },
  "los angeles lakers": { id: "13", sport: "nba" },
  "memphis grizzlies": { id: "29", sport: "nba" },
  "miami heat": { id: "14", sport: "nba" },
  "milwaukee bucks": { id: "15", sport: "nba" },
  "minnesota timberwolves": { id: "16", sport: "nba" },
  "new orleans pelicans": { id: "3", sport: "nba" },
  "new york knicks": { id: "18", sport: "nba" },
  "oklahoma city thunder": { id: "25", sport: "nba" },
  "orlando magic": { id: "19", sport: "nba" },
  "philadelphia 76ers": { id: "20", sport: "nba" },
  "phoenix suns": { id: "21", sport: "nba" },
  "portland trail blazers": { id: "22", sport: "nba" },
  "sacramento kings": { id: "23", sport: "nba" },
  "san antonio spurs": { id: "24", sport: "nba" },
  "toronto raptors": { id: "28", sport: "nba" },
  "utah jazz": { id: "26", sport: "nba" },
  "washington wizards": { id: "27", sport: "nba" },
  // NFL
  "arizona cardinals": { id: "22", sport: "nfl" },
  "atlanta falcons": { id: "1", sport: "nfl" },
  "baltimore ravens": { id: "33", sport: "nfl" },
  "buffalo bills": { id: "2", sport: "nfl" },
  "carolina panthers": { id: "29", sport: "nfl" },
  "chicago bears": { id: "3", sport: "nfl" },
  "cincinnati bengals": { id: "4", sport: "nfl" },
  "cleveland browns": { id: "5", sport: "nfl" },
  "dallas cowboys": { id: "6", sport: "nfl" },
  "denver broncos": { id: "7", sport: "nfl" },
  "detroit lions": { id: "8", sport: "nfl" },
  "green bay packers": { id: "9", sport: "nfl" },
  "houston texans": { id: "34", sport: "nfl" },
  "indianapolis colts": { id: "11", sport: "nfl" },
  "jacksonville jaguars": { id: "30", sport: "nfl" },
  "kansas city chiefs": { id: "12", sport: "nfl" },
  "las vegas raiders": { id: "13", sport: "nfl" },
  "los angeles chargers": { id: "24", sport: "nfl" },
  "los angeles rams": { id: "14", sport: "nfl" },
  "miami dolphins": { id: "15", sport: "nfl" },
  "minnesota vikings": { id: "16", sport: "nfl" },
  "new england patriots": { id: "17", sport: "nfl" },
  "new orleans saints": { id: "18", sport: "nfl" },
  "new york giants": { id: "19", sport: "nfl" },
  "new york jets": { id: "20", sport: "nfl" },
  "philadelphia eagles": { id: "21", sport: "nfl" },
  "pittsburgh steelers": { id: "23", sport: "nfl" },
  "san francisco 49ers": { id: "25", sport: "nfl" },
  "seattle seahawks": { id: "26", sport: "nfl" },
  "tampa bay buccaneers": { id: "27", sport: "nfl" },
  "tennessee titans": { id: "10", sport: "nfl" },
  "washington commanders": { id: "28", sport: "nfl" },
  // MLB
  "arizona diamondbacks": { id: "29", sport: "mlb" },
  "atlanta braves": { id: "15", sport: "mlb" },
  "baltimore orioles": { id: "1", sport: "mlb" },
  "boston red sox": { id: "2", sport: "mlb" },
  "chicago cubs": { id: "16", sport: "mlb" },
  "chicago white sox": { id: "4", sport: "mlb" },
  "cincinnati reds": { id: "17", sport: "mlb" },
  "cleveland guardians": { id: "5", sport: "mlb" },
  "colorado rockies": { id: "27", sport: "mlb" },
  "detroit tigers": { id: "6", sport: "mlb" },
  "houston astros": { id: "18", sport: "mlb" },
  "kansas city royals": { id: "7", sport: "mlb" },
  "los angeles angels": { id: "3", sport: "mlb" },
  "los angeles dodgers": { id: "19", sport: "mlb" },
  "miami marlins": { id: "28", sport: "mlb" },
  "milwaukee brewers": { id: "21", sport: "mlb" },
  "minnesota twins": { id: "9", sport: "mlb" },
  "new york mets": { id: "21", sport: "mlb" },
  "new york yankees": { id: "10", sport: "mlb" },
  "oakland athletics": { id: "11", sport: "mlb" },
  "philadelphia phillies": { id: "22", sport: "mlb" },
  "pittsburgh pirates": { id: "23", sport: "mlb" },
  "san diego padres": { id: "25", sport: "mlb" },
  "san francisco giants": { id: "26", sport: "mlb" },
  "seattle mariners": { id: "12", sport: "mlb" },
  "st. louis cardinals": { id: "24", sport: "mlb" },
  "tampa bay rays": { id: "30", sport: "mlb" },
  "texas rangers": { id: "13", sport: "mlb" },
  "toronto blue jays": { id: "14", sport: "mlb" },
  "washington nationals": { id: "20", sport: "mlb" },
  // NHL
  "anaheim ducks": { id: "25", sport: "nhl" },
  "boston bruins": { id: "1", sport: "nhl" },
  "buffalo sabres": { id: "2", sport: "nhl" },
  "calgary flames": { id: "20", sport: "nhl" },
  "carolina hurricanes": { id: "12", sport: "nhl" },
  "chicago blackhawks": { id: "4", sport: "nhl" },
  "colorado avalanche": { id: "17", sport: "nhl" },
  "columbus blue jackets": { id: "29", sport: "nhl" },
  "dallas stars": { id: "9", sport: "nhl" },
  "detroit red wings": { id: "5", sport: "nhl" },
  "edmonton oilers": { id: "22", sport: "nhl" },
  "florida panthers": { id: "13", sport: "nhl" },
  "los angeles kings": { id: "26", sport: "nhl" },
  "minnesota wild": { id: "30", sport: "nhl" },
  "montreal canadiens": { id: "8", sport: "nhl" },
  "nashville predators": { id: "18", sport: "nhl" },
  "new jersey devils": { id: "1", sport: "nhl" },
  "new york islanders": { id: "2", sport: "nhl" },
  "new york rangers": { id: "3", sport: "nhl" },
  "ottawa senators": { id: "9", sport: "nhl" },
  "philadelphia flyers": { id: "4", sport: "nhl" },
  "pittsburgh penguins": { id: "5", sport: "nhl" },
  "san jose sharks": { id: "28", sport: "nhl" },
  "seattle kraken": { id: "55", sport: "nhl" },
  "st. louis blues": { id: "19", sport: "nhl" },
  "tampa bay lightning": { id: "14", sport: "nhl" },
  "toronto maple leafs": { id: "10", sport: "nhl" },
  "utah hockey club": { id: "56", sport: "nhl" },
  "vancouver canucks": { id: "23", sport: "nhl" },
  "vegas golden knights": { id: "54", sport: "nhl" },
  "washington capitals": { id: "15", sport: "nhl" },
  "winnipeg jets": { id: "52", sport: "nhl" },
};

/**
 * Get an ESPN team logo URL by team name (no API call needed).
 * Returns null if team is not in the lookup table.
 */
export function espnTeamLogoByName(teamName: string, sportKey?: string | null): string | null {
  const key = teamName.toLowerCase().trim();
  const entry = ESPN_TEAM_IDS[key];
  if (!entry) return null;
  // Use the sport from the lookup unless overridden
  const sport = entry.sport;
  return espnTeamLogoUrl(entry.id, sport, 100);
}

/**
 * Map our sport_key to ESPN headshot sport path.
 */
export function sportKeyToEspnHeadshotSport(sportKey: string | null): string {
  if (!sportKey) return "nba";
  const key = sportKey.toLowerCase();
  if (key.includes("nba") || key.includes("wnba") || key.includes("ncaab") || key.includes("wncaab")) return "nba";
  if (key.includes("nfl") || key.includes("ncaaf")) return "nfl";
  if (key.includes("nhl")) return "nhl";
  if (key.includes("mlb")) return "mlb";
  if (key.includes("mls") || key.includes("soccer") || key.includes("epl")) return "soccer";
  return "nba";
}

// ============================================================================
// 2. Wikipedia / MediaWiki API
// ============================================================================

/**
 * Fetch a thumbnail image URL from Wikipedia for an entity name.
 * Returns null if not found or on error.
 */
export async function getWikipediaImage(entityName: string): Promise<string | null> {
  const cacheKey = `wiki_${entityName.toLowerCase().replace(/\s+/g, "_")}`;
  const cached = cacheGet<string | null>(cacheKey);
  if (cached !== undefined) return cached;

  try {
    const title = entityName.replace(/ /g, "_");
    const res = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) {
      cacheSet(cacheKey, null);
      return null;
    }
    const data = await res.json();
    const url: string | null = data.thumbnail?.source || null;
    cacheSet(cacheKey, url);
    return url;
  } catch {
    return null;
  }
}

// ============================================================================
// 3. Flagpedia / flagcdn.com
// ============================================================================

/**
 * Country/region name → ISO 3166-1 alpha-2 code mapping.
 * Covers ~60 most common in sports and prediction markets.
 */
const COUNTRY_CODES: Record<string, string> = {
  // Americas
  "united states": "us", usa: "us", america: "us",
  canada: "ca", mexico: "mx", brazil: "br", argentina: "ar",
  colombia: "co", chile: "cl", uruguay: "uy", paraguay: "py",
  peru: "pe", ecuador: "ec", venezuela: "ve", "costa rica": "cr",
  jamaica: "jm", "trinidad and tobago": "tt", panama: "pa",
  honduras: "hn",

  // Europe
  england: "gb-eng", "united kingdom": "gb", scotland: "gb-sct",
  wales: "gb-wls", france: "fr", germany: "de", spain: "es",
  italy: "it", netherlands: "nl", holland: "nl", belgium: "be",
  portugal: "pt", switzerland: "ch", austria: "at", sweden: "se",
  norway: "no", denmark: "dk", finland: "fi", poland: "pl",
  "czech republic": "cz", czechia: "cz", croatia: "hr", serbia: "rs",
  greece: "gr", turkey: "tr", ukraine: "ua", romania: "ro",
  hungary: "hu", ireland: "ie", iceland: "is",

  // Asia & Oceania
  japan: "jp", "south korea": "kr", korea: "kr", china: "cn",
  india: "in", australia: "au", "new zealand": "nz",
  "saudi arabia": "sa", iran: "ir", qatar: "qa", "united arab emirates": "ae",
  uae: "ae", thailand: "th", vietnam: "vn", indonesia: "id",
  philippines: "ph",

  // Africa
  nigeria: "ng", "south africa": "za", egypt: "eg", ghana: "gh",
  senegal: "sn", cameroon: "cm", "ivory coast": "ci",
  morocco: "ma", tunisia: "tn", algeria: "dz",

  // Common abbreviations
  gbr: "gb", fra: "fr", ger: "de", esp: "es", ita: "it",
  ned: "nl", sui: "ch", aus: "au", nzl: "nz", jpn: "jp",
  kor: "kr", bra: "br", arg: "ar", mex: "mx", col: "co",
  por: "pt",
};

/**
 * Get a flag image URL from flagcdn.com.
 * Returns null if country code is not found.
 */
export function flagUrl(countryOrTeamName: string, width: number = 80): string | null {
  const code = COUNTRY_CODES[countryOrTeamName.toLowerCase().trim()];
  if (!code) return null;
  return `https://flagcdn.com/w${width}/${code}.png`;
}

/**
 * Check if a sport key represents an international competition.
 */
export function isInternationalSport(sportKey: string | null): boolean {
  if (!sportKey) return false;
  return /world_cup|olympics|euros|nations_league|copa_america|asian_cup|africa_cup|international/i.test(sportKey);
}

// ============================================================================
// 4. CoinGecko API
// ============================================================================

/**
 * Common coin names → CoinGecko IDs.
 * Covers the most common coins in prediction markets.
 */
const COIN_IDS: Record<string, string> = {
  bitcoin: "bitcoin", btc: "bitcoin",
  ethereum: "ethereum", eth: "ethereum",
  solana: "solana", sol: "solana",
  dogecoin: "dogecoin", doge: "dogecoin",
  xrp: "ripple", ripple: "ripple",
  cardano: "cardano", ada: "cardano",
  polkadot: "polkadot", dot: "polkadot",
  avalanche: "avalanche-2", avax: "avalanche-2",
  chainlink: "chainlink", link: "chainlink",
  litecoin: "litecoin", ltc: "litecoin",
  polygon: "matic-network", matic: "matic-network",
  uniswap: "uniswap", uni: "uniswap",
  cosmos: "cosmos", atom: "cosmos",
  stellar: "stellar", xlm: "stellar",
  algorand: "algorand", algo: "algorand",
  tron: "tron", trx: "tron",
  toncoin: "the-open-network", ton: "the-open-network",
  sui: "sui",
  aptos: "aptos", apt: "aptos",
  near: "near",
  arbitrum: "arbitrum", arb: "arbitrum",
  optimism: "optimism", op: "optimism",
  pepe: "pepe",
  shiba: "shiba-inu", "shiba inu": "shiba-inu",
  bonk: "bonk",
  worldcoin: "worldcoin-wld", wld: "worldcoin-wld",
};

/**
 * Fetch a coin logo URL from CoinGecko.
 * Returns null if not found or on error.
 */
export async function getCoinImage(coinName: string): Promise<string | null> {
  const normalized = coinName.toLowerCase().trim();
  const id = COIN_IDS[normalized];
  if (!id) return null;

  const cacheKey = `coin_${id}`;
  const cached = cacheGet<string | null>(cacheKey);
  if (cached !== undefined) return cached;

  try {
    const res = await fetch(
      `https://api.coingecko.com/api/v3/coins/${id}?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) {
      cacheSet(cacheKey, null);
      return null;
    }
    const data = await res.json();
    const url: string | null = data.image?.small || null;
    cacheSet(cacheKey, url);
    return url;
  } catch {
    return null;
  }
}

/**
 * Extract a coin name from a market name string.
 * e.g., "Will Bitcoin hit $100k?" → "bitcoin"
 * e.g., "ETH price above $5000" → "eth"
 */
export function extractCoinName(marketName: string): string | null {
  const lower = marketName.toLowerCase();
  // Check each known coin name against the market name
  for (const name of Object.keys(COIN_IDS)) {
    // Use word boundary matching to avoid partial matches
    const regex = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (regex.test(lower)) {
      return name;
    }
  }
  return null;
}

// ============================================================================
// Non-sports category detection
// ============================================================================

const NON_SPORTS_CATEGORIES = new Set([
  "politics", "entertainment", "economics", "tech", "geopolitics",
  "culture", "crypto", "weather", "other",
]);

/**
 * Check if a category is a non-sports category that could use Wikipedia images.
 */
export function isNonSportsCategory(category: string | null): boolean {
  if (!category) return false;
  return NON_SPORTS_CATEGORIES.has(category.toLowerCase());
}

/**
 * Check if a category is crypto.
 */
export function isCryptoCategory(category: string | null): boolean {
  if (!category) return false;
  return category.toLowerCase() === "crypto";
}
