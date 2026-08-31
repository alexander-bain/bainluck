/**
 * Image enrichment APIs — ESPN headshots, Wikipedia, Flagpedia.
 *
 * Client-side only — all APIs are free, no auth, CORS-friendly.
 * Images are cached in localStorage with 24h TTL (same pattern as tmdb.ts).
 */

import { lruSetItem } from "./lruCache";

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
  const entry: CacheEntry<T> = { data, ts: Date.now() };
  // LRU-bounded write: evicts oldest img_ entries on quota rather than
  // silently freezing the cache once localStorage fills (#L2-137).
  lruSetItem(CACHE_PREFIX + key, JSON.stringify(entry), CACHE_PREFIX);
}

function cacheDelete(key: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(CACHE_PREFIX + key);
  } catch {
    // Store unavailable (private mode). A stale entry we cannot delete is
    // still ignored by the reader, so this is safe to swallow.
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
export function espnTeamLogoUrl(espnTeamId: string, sport: string = "nba", size: 100 | 500 = 500): string {
  // Use the combiner URL which is more reliable for cross-origin access
  return `https://a.espncdn.com/combiner/i?img=/i/teamlogos/${sport}/${size}/${espnTeamId}.png&w=40&h=40&transparent=true`;
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
  return espnTeamLogoUrl(entry.id, entry.sport, 500);
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

// ---------------------------------------------------------------------------
// UX-P032 (#1600) — bounding the lookup itself
//
// A tennis draw fired ~600 failing requests at Wikipedia's REST API in a single
// page load, and 2,175 console errors five days earlier (browser-audit runs
// 31323268137 and 30864618239). The row-level name guard (`isLikelyPersonName`)
// removes most of them at the call site, but the guard below is what makes the
// STORM structurally impossible, for every caller of this function including
// ones not yet written.
//
// What was measured, so the fix is aimed at the real thing (UX-P032 Item 1):
// `en.wikipedia.org/api/rest_v1/page/summary/<title>` answers `200` for a valid
// title and an honest `404` for a nonsense one, with `access-control-allow-origin: *`
// in both cases. The endpoint shape and CORS were never wrong. So the
// `net::ERR_FAILED` the rail recorded — on `Brandon_Nakashima`, a REAL article —
// is Wikipedia REFUSING us after the burst, which is self-inflicted.
//
// That distinction drives the design: a 404 is the source answering healthily
// ("no article"), and it is already cached, so it costs one request per name
// ever. Only a THROW means we are being refused, and only a throw counts toward
// the circuit below.
// ---------------------------------------------------------------------------

/**
 * Consecutive-failure circuit breaker.
 *
 * Pure and clock-injectable so the policy is unit-testable without timers or a
 * network. Exported for tests; callers should use the shared instance.
 */
export class LookupCircuit {
  private consecutiveFailures = 0;
  private openUntilMs = 0;

  constructor(
    private readonly threshold: number,
    private readonly cooldownMs: number,
    private readonly now: () => number = () => Date.now(),
  ) {}

  /** While open, callers must not issue a request at all. */
  isOpen(): boolean {
    return this.now() < this.openUntilMs;
  }

  /** Any answer from the source — including a 404 — proves it is still talking. */
  recordSuccess(): void {
    this.consecutiveFailures = 0;
    this.openUntilMs = 0;
  }

  /** A throw: refused, offline, or timed out. */
  recordFailure(): void {
    this.consecutiveFailures += 1;
    if (this.consecutiveFailures >= this.threshold) {
      this.openUntilMs = this.now() + this.cooldownMs;
      this.consecutiveFailures = 0;
    }
  }
}

/**
 * Five throws in a row is not a coincidence, and 60s is long enough for a rate
 * limit window to roll over while still self-healing without a reload.
 *
 * Deliberately NOT the alternative of negative-caching a throw for the cache's
 * 24h TTL: that would bound the storm too, but it would also poison a real
 * person's headshot for a day because of one transient blip. The circuit stops
 * the refire without attributing a network failure to a name.
 */
const WIKIPEDIA_CIRCUIT = new LookupCircuit(5, 60_000);

/**
 * Cap on simultaneous lookups. The point is not throughput — it is that a page
 * with hundreds of rows must not open hundreds of sockets in one frame, which is
 * what earns the rate limit that produced the throws in the first place. Four at
 * a time drains a large field in well under a second while looking like a
 * browser rather than a scraper.
 */
const MAX_CONCURRENT_LOOKUPS = 4;
let activeLookups = 0;
const lookupQueue: Array<() => void> = [];

function acquireLookupSlot(): Promise<void> {
  if (activeLookups < MAX_CONCURRENT_LOOKUPS) {
    activeLookups += 1;
    return Promise.resolve();
  }
  return new Promise<void>((resolve) => {
    lookupQueue.push(() => {
      activeLookups += 1;
      resolve();
    });
  });
}

function releaseLookupSlot(): void {
  activeLookups = Math.max(0, activeLookups - 1);
  lookupQueue.shift()?.();
}

/**
 * In-flight requests by cache key. The localStorage cache cannot help a request
 * that has not returned yet, so without this every row sharing a name (and a
 * large field has many) opens its own socket for the same title.
 */
const inFlightLookups = new Map<string, Promise<string | null>>();

/** Test seam — resets the module-level bounding state between cases. */
export function __resetWikipediaLookupState(): void {
  inFlightLookups.clear();
  lookupQueue.length = 0;
  activeLookups = 0;
  WIKIPEDIA_CIRCUIT.recordSuccess();
}

/**
 * UX-P235 (board item 14) — WHY A WIKIPEDIA SUMMARY IMAGE IS SOMETIMES REFUSED.
 *
 * `getWikipediaImage` asks Wikipedia *"what does this NAME look like?"* when the
 * caller means *"what does this BRAND look like?"*, and a bare market-outcome name
 * is often a common noun. Measured live 2026-08-31 on the eight outcomes of market
 * 109441, the market Alex reviewed:
 *
 *   Amazon      disambiguation, no image            -> initials  (honest)
 *   Max         disambiguation, no image            -> initials  (honest)
 *   Netflix     `Netflix_UI_for_Web.png`            -> a SCREENSHOT of the web UI
 *   Disney      `The_Walt_Disney_company_logo.svg`  -> the real logo, 330x171
 *   Hulu        `Hulu_logo_(2018).svg`              -> the real logo
 *   Paramount+  `Paramount_Plus.svg`                -> the real logo
 *   🔴 Peacock  `Peacock_Plumage.jpg`, title "Peafowl", description
 *               "Group of large game birds"         -> A PHOTOGRAPH OF A BIRD
 *   🔴 Apple    `Pink_lady_and_cross_section.jpg`, description
 *               "Edible fruit"                      -> A PHOTOGRAPH OF A FRUIT
 *
 * 🔴 **THE BOARD ITEM SAYS PEACOCK AND APPLE "RESOLVE CORRECTLY". THEY DO NOT** —
 * they resolve to a bird and a fruit, rendered as confident circular brand marks
 * beside a streaming-service probability. Only 2 of the 8 (Hulu, Paramount+) were
 * ever right. Alex's own rule for this item is *a wrong logo is worse than no
 * logo*, and a bird is the most wrong of the eight.
 *
 * So this refuses the answers Wikipedia's OWN metadata marks as not-a-brand, using
 * fields already in the response we fetch — no second request, no new round trip on
 * a page that renders 25 of these. A refusal falls back to the initials chip, which
 * `EntityImage` now paints as an obvious placeholder rather than a brand tile.
 *
 * NOT ATTEMPTED HERE, and named in the report instead: **Wikidata's P154 "logo
 * image"**, which is the *right* question and which I measured working —
 * `Netflix -> Netflix logo.svg`, `Disney -> The Walt Disney Company Logo.svg`,
 * while `Peacock` and `Apple` correctly have none. It would fix the Netflix
 * screenshot too. It needs a SECOND network hop per outcome, and cold-load latency
 * is a named priority today, so it is a deliberate follow-up rather than a thing to
 * slip in unmeasured.
 */

/**
 * Wikipedia's own one-line `description` for pages whose subject is a natural kind
 * — never the subject of a market outcome, and never a brand.
 *
 * Deliberately a SHORT, EXPLICIT list of things we can prove are wrong, not a
 * general "is this a company?" classifier. We cannot prove a page IS a brand; we
 * can prove a page is a bird. Matching is on Wikipedia's curated short description,
 * not on free prose, so it is stable.
 *
 * ⚠️ A racehorse, a hurricane or a boat named after an animal is a legitimate
 * outcome — but its page's description is "racehorse" / "tropical cyclone", not
 * "species of bird", so it is unaffected. The test file pins that.
 */
const NOT_A_BRAND_DESCRIPTIONS: readonly RegExp[] = [
  /\bspecies\b/i,
  /\bgenus\b/i,
  /\bfamily of\b/i,
  /\bgroup of .*(bird|fish|mammal|insect|reptile|animal|plant)/i,
  /\b(bird|fish|mammal|insect|reptile|amphibian)s?\b(?!.*\b(team|club|logo|company|brand)\b)/i,
  /\b(fruit|vegetable|plant|tree|flower|herb)\b(?!.*\b(company|brand|logo|band|film)\b)/i,
  /\bchemical element\b/i,
  /\b(given|family|sur)\s?names?\b/i,
  /\btopics referred to by the same term\b/i,
];

/** True when Wikipedia's own metadata says this page is not a brand or an entity. */
export function wikipediaSummaryIsNotABrand(summary: {
  type?: string | null;
  description?: string | null;
}): boolean {
  // Wikipedia stating outright that the name is ambiguous. Its own word for it.
  if (summary.type === "disambiguation") return true;
  const d = (summary.description || "").trim();
  if (!d) return false;
  return NOT_A_BRAND_DESCRIPTIONS.some((re) => re.test(d));
}

/**
 * UX-P236 (CERT-610) — WHY THE CACHE STORES THE EVIDENCE AND NOT THE VERDICT.
 *
 * UX-P235 put the refusal in the fetch path only, and the fetch path is the one
 * a returning user does not take. `img_wiki_*` has a 24-hour TTL, so every reader
 * who had already loaded `/futures/109441` kept being served the bird straight
 * out of localStorage: the new predicate never ran for them, and the ship — *"a
 * wrong logo is worse than no logo"* — did not land for up to a day. CERT-610
 * blocked on exactly that and was right.
 *
 * The narrow fix is to bump the cache key so old entries miss. It works once,
 * and it re-arms the same trap the next time anyone edits the refusal rules:
 * the policy would again be frozen into whatever it was at WRITE time, and the
 * only thing standing between a reader and a stale verdict is an author
 * remembering to bump a constant.
 *
 * So the entry stores what Wikipedia SAID (`type`, `description`, the thumbnail
 * URL) rather than what we CONCLUDED, and `decideWikipediaImage` re-runs on
 * every read. A change to `NOT_A_BRAND_DESCRIPTIONS` therefore takes effect for
 * already-cached readers on their next paint, with no version to bump and no
 * refetch. `k` marks the SHAPE, not the policy — it changes only if these
 * fields do.
 *
 * The cost is a short description string per entry, in a cache that is already
 * LRU-bounded (#L2-137).
 */
const WIKI_CACHE_SHAPE = "wiki-summary-1";

interface WikipediaCacheEntry {
  /** Shape marker. Entries written before UX-P236 lack it and are discarded. */
  k: typeof WIKI_CACHE_SHAPE;
  url: string | null;
  type?: string | null;
  description?: string | null;
}

function isWikipediaCacheEntry(value: unknown): value is WikipediaCacheEntry {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { k?: unknown }).k === WIKI_CACHE_SHAPE
  );
}

/**
 * The ONE place the refusal decision is made. Called on the fetch path and on
 * every cache read, so the two can never disagree — which is the defect
 * CERT-610 found.
 */
function decideWikipediaImage(entry: WikipediaCacheEntry): string | null {
  // `?? null` because the entry comes back through `JSON.parse` of a store the
  // user's browser owns: a truncated or hand-edited entry can carry the shape
  // marker and no `url`, and `undefined` would escape the declared return type
  // into every caller's `.then`.
  return wikipediaSummaryIsNotABrand(entry) ? null : entry.url ?? null;
}

/**
 * Fetch a thumbnail image URL from Wikipedia for an entity name.
 * Returns null if not found, if the lookup fails, if Wikipedia's own metadata says
 * the page is not a brand (see above), or while the circuit is open.
 */
export async function getWikipediaImage(entityName: string): Promise<string | null> {
  const cacheKey = `wiki_${entityName.toLowerCase().replace(/\s+/g, "_")}`;
  const cached = cacheGet<unknown>(cacheKey);
  if (cached !== undefined) {
    if (isWikipediaCacheEntry(cached)) return decideWikipediaImage(cached);
    // A pre-UX-P236 entry: a bare URL string or null, holding a verdict reached
    // before the refusal existed. It is exactly the poisoned kind, so it is
    // dropped rather than trusted, and the name is looked up again below.
    cacheDelete(cacheKey);
  }

  // Refused recently — do not add to the pile. Falls back to initials, which is
  // what a failed lookup rendered anyway.
  if (WIKIPEDIA_CIRCUIT.isOpen()) return null;

  const existing = inFlightLookups.get(cacheKey);
  if (existing) return existing;

  const pending = (async (): Promise<string | null> => {
    await acquireLookupSlot();
    try {
      const title = entityName.replace(/ /g, "_");
      const res = await fetch(
        `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`,
        { signal: AbortSignal.timeout(5000) }
      );
      // The source answered, so it is healthy — even on a 404.
      WIKIPEDIA_CIRCUIT.recordSuccess();
      if (!res.ok) {
        // No article. There is no metadata to re-judge later, and "no article"
        // is not a verdict that can go stale.
        cacheSet<WikipediaCacheEntry>(cacheKey, { k: WIKI_CACHE_SHAPE, url: null });
        return null;
      }
      const data = await res.json();
      // UX-P235: refuse a confidently-wrong picture before it becomes a brand
      // mark. UX-P236: cache what Wikipedia said, not what we concluded, so the
      // same bird is not fetched 25 times AND the refusal is re-applied to this
      // entry on every later read.
      const entry: WikipediaCacheEntry = {
        k: WIKI_CACHE_SHAPE,
        url: data.thumbnail?.source || null,
        type: data.type ?? null,
        description: data.description ?? null,
      };
      cacheSet(cacheKey, entry);
      return decideWikipediaImage(entry);
    } catch {
      // A throw is the source refusing us (or the network being gone). Not
      // cached against the name — the name is probably fine, we are the problem.
      WIKIPEDIA_CIRCUIT.recordFailure();
      return null;
    } finally {
      releaseLookupSlot();
      inFlightLookups.delete(cacheKey);
    }
  })();

  inFlightLookups.set(cacheKey, pending);
  return pending;
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
// Non-sports category detection
// ============================================================================

const NON_SPORTS_CATEGORIES = new Set([
  "politics", "entertainment", "economics", "tech", "geopolitics",
  "culture", "weather", "other",
]);

/**
 * Check if a category is a non-sports category that could use Wikipedia images.
 */
export function isNonSportsCategory(category: string | null): boolean {
  if (!category) return false;
  return NON_SPORTS_CATEGORIES.has(category.toLowerCase());
}
