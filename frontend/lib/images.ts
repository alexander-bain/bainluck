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
