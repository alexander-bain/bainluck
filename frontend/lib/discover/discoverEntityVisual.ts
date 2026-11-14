/**
 * Discover image truth policy & deterministic monogram fallback (#12659).
 *
 * Mirrors `backend/app/utils/discover_image_policy.py`:
 *  1. A person, team, film, or song (and named public companies / tickers)
 *     NEVER renders a stock photo (`images.pexels.com`).
 *  2. Music / song / album / chart markets NEVER render TMDB film backdrops
 *     (`image.tmdb.org`).
 *  3. Known wrong, misleading, clip-art, or duplicate Pexels photo IDs from
 *     the 60-seat Discover audit are refused on every market kind.
 *  4. Consumes `image_presentation` (`"photo" | "portrait" | "logo" | "cover"`)
 *     and `image_monogram` (`{ initials, label, kind, bg_hex, accent_hex }`)
 *     from `/api/feed` when present, and computes a deterministic client-side
 *     fallback when absent or when `<img onError>` fires.
 */

export type DiscoverImagePresentation = "photo" | "portrait" | "logo" | "cover";
export type DiscoverVisualKind =
  | "person"
  | "team"
  | "film"
  | "song"
  | "organization"
  | "topic";

export interface DiscoverMonogram {
  initials: string;
  label: string;
  kind: DiscoverVisualKind;
  bgHex: string;
  accentHex: string;
}

export interface ResolvedDiscoverVisual {
  imageUrl: string | null;
  presentation: DiscoverImagePresentation | null;
  kind: DiscoverVisualKind;
  monogram: DiscoverMonogram;
}

export const BLOCKED_PEXELS_PHOTO_IDS: ReadonlySet<string> = new Set([
  "8919548",  // Bitcoin "2021 TO INVEST OR TO SELL?" on Fed & Rates
  "6289047",  // Toy red rocket on "PROFIT" flashcard (Kimi IPO)
  "6289061",  // Plastic toy bomb on $100 bill + "STOCKS" flashcard (Bloomberg IPO)
  "31825810", // Shirtless rugby players holding sports cup (French election)
  "3970331",  // Johns Hopkins COVID-19 Global Cases dashboard (U.S. confirm aliens)
  "9321371",  // Brazilian Portuguese impeachment banner (U.S. House impeach Trump)
  "8728168",  // Sci-fi lab coat hologram (Jensen Huang divorce)
  "11460276", // Taipei street rally (Jensen Huang Congress testimony)
  "12786869", // "LOST CAT WOLF" utility-pole flyer (Most Searched People)
  "6326317",  // Unrelated man with megaphone (Jensen Huang Congress testimony)
  "32417524", // Wooden blocks "2026" generic flatlay
  "8850837",  // Duplicate "POLITICS" newspaper flatlay
  "8850633",  // Duplicate "POLITICS" newspaper flatlay
  "8044086",  // Stock vocal microphone on Song of the Year
  "18326060", // Stock tuxedo silhouette on Next James Bond actor
]);

const MONOGRAM_PALETTE: ReadonlyArray<readonly [string, string]> = [
  ["#1e3a8a", "#2563eb"], // Royal cobalt
  ["#312e81", "#4f46e5"], // Civic indigo
  ["#0f766e", "#14b8a6"], // Editorial teal
  ["#7c2d12", "#ea580c"], // Burnt sienna
  ["#581c87", "#9333ea"], // Deep plum
  ["#831843", "#db2777"], // Crimson rose
  ["#14532d", "#16a34a"], // Forest emerald
  ["#7f1d1d", "#dc2626"], // Arena crimson
  ["#1e293b", "#475569"], // Cinema slate
  ["#78350f", "#d97706"], // Warm amber
];

const INITIALS_NOISE = new Set([
  "the", "of", "and", "or", "in", "on", "at", "to", "for", "from", "with",
  "will", "who", "what", "when", "where", "which", "how", "high", "low",
  "be", "is", "are", "does", "do", "a", "an", "by", "before", "after",
  "end", "during", "through", "next", "new", "announced", "announce",
  "win", "wins", "winner", "champion", "championship", "election",
  "ipo", "closing", "market", "cap", "quarterly", "earnings", "beat",
  "close", "above", "below", "go", "reach", "hit",
  "rotten", "tomatoes", "score", "opening", "weekend", "domestic", "box", "office",
  "inc", "corp", "corporation", "ltd", "llc", "plc", "holdings", "group",
]);

const MUSIC_TITLE_RE =
  /\b(grammys?|grammy\s+awards?|latin\s+grammys?|song\s+of\s+the\s+year|record\s+of\s+the\s+year|album\s+of\s+the\s+year|best\s+[a-z\s]{0,30}\s+(?:album|song|music\s+performance|rap\s+performance|pop\s+solo\s+performance|vocal\s+album)|billboard\s+(?:hot\s+100|200)|spotify|apple\s+music|gta\s+vi:\s+the\s+album|featured\s+on\s+.*album|eurovision|halftime\s+show\s+headliner)\b/i;

const FILM_TITLE_RE =
  /\b(oscars?|academy\s+awards?|golden\s+globes?|emmys?|bafta|cannes|best\s+(?:picture|director|actor|actress|casting|animated\s+feature|screenplay)|rotten\s+tomatoes|box\s+office|opening\s+weekend|james\s+bond|next\s+007|marvel|star\s+wars|dc\s+studios)\b/i;

const TEAM_SPORT_CATS = new Set([
  "basketball",
  "football",
  "baseball",
  "hockey",
  "soccer",
  "rugby",
  "cricket",
]);

const TEAM_TITLE_RE =
  /\b(super\s+bowl\s+(?:winner|champion|matchup)|stanley\s+cup|world\s+series|nba\s+finals|nba\s+champion|world\s+cup\s+(?:winner|champion)|champions\s+league|playoffs?|division\s+(?:winner|front-runners)|relegated|relegation|college\s+football\s+playoff)\b/i;

const TICKER_RE = /\(([A-Z]{2,5})\)/;
const ORG_TITLE_RE =
  /\b(ipo|quarterly\s+earnings|beat\s+earnings|market\s+cap|kimi|moonshot\s+ai|bloomberg|openai|anthropic|spacex|stripe|databricks)\b/i;

const PARTY_OR_BUCKET_OUTCOME_RE =
  /^(yes|no|not\s+.+|none|no\s+change|no\s+head\s+of\s+state|before\s+.+|after\s+.+|by\s+.+|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}.*|above\s+.+|below\s+.+|top\s+\d+|[\$<>≤≥\-+\d.% \t]+(?:\s+bps.*)?|.*\([A-Z]{2,5}\))$/i;

const PERSON_HEADLINE_PATTERNS: ReadonlyArray<RegExp> = [
  /^Will\s+([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s+(?:de|le|la|van|von|di|del|da|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.\-']*)){1,3}?)\s+(?:join|attend|testify|publicly\s+testify|resign|step\s+down|win|beat|divorce|leave|endorse|pardon|visit|meet)\b/,
  /^([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s+(?:de|le|la|van|von|di|del|da|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.\-']*)){1,3}?)\s+(?:out\s+as|divorce|impeached|pardoned|arrested|confirmed\s+as)\b/,
  /\bimpeach\s+(Trump|Biden|Macron|Lula|Yoon)\b/i,
  /\bWill\s+(Trump|Putin|Netanyahu|Zelenskyy?|Xi\s+Jinping|Modi)\s+be\b/i,
];

const PERSON_ELECTION_OR_ROLE_RE =
  /\b(presidential\s+election|governor\s+election|mayor\s+election|prime\s+minister|minister\s+of\s+finance|leader\s+end\s+of|next\s+ceo\s+of|most\s+searched\s+people|ufc\s+.*champion|mvp\s+winner)\b/i;

function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

export function isPexelsStockUrl(url: string | null | undefined): boolean {
  const host = hostOf(url);
  return host === "images.pexels.com" || host.endsWith(".pexels.com");
}

export function isBlockedPexelsPhoto(url: string | null | undefined): boolean {
  if (!url || !isPexelsStockUrl(url)) return false;
  const m = /\/photos\/(\d+)\//.exec(url);
  return !!m && BLOCKED_PEXELS_PHOTO_IDS.has(m[1]);
}

function isTmdbUrl(url: string | null | undefined): boolean {
  const host = hostOf(url);
  return host === "image.tmdb.org" || host.endsWith(".tmdb.org");
}

function hashPalette(label: string, kind: DiscoverVisualKind): readonly [string, string] {
  if (kind === "film") return ["#1e293b", "#475569"];
  if (kind === "song") return ["#581c87", "#9333ea"];
  const norm = (label || kind).toLowerCase().trim();
  let h = 2166136261;
  for (let i = 0; i < norm.length; i++) {
    h ^= norm.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return MONOGRAM_PALETTE[Math.abs(h) % MONOGRAM_PALETTE.length];
}

export function computeDiscoverInitials(label: string | null | undefined, tickerOk = true): string {
  let raw = (label ?? "").trim();
  if (!raw) return "BL";
  if (tickerOk) {
    const tm = TICKER_RE.exec(raw);
    if (tm) return tm[1].slice(0, 5).toUpperCase();
  }
  if (/\bkimi\b.*\bmoonshot\b/i.test(raw)) return "KM";
  if (raw.includes(" - ")) raw = raw.split(" - ", 1)[0].trim();
  if (raw.includes(": ") && /^(afc|nfc|al|nl)\s+/i.test(raw)) {
    raw = raw.split(": ", 2)[1].trim();
  }
  const noParens = raw.replace(/\([^)]*\)/g, " ").trim() || raw;
  const rawTokens = noParens
    .split(/\s+/)
    .map((w) => w.replace(/[^A-Za-z0-9À-ÖØ-öø-ÿ]/g, ""))
    .filter(Boolean);
  const filtered = rawTokens.filter(
    (w) =>
      !INITIALS_NOISE.has(w.toLowerCase()) &&
      !/^(?:\d+|q[1-4]|\d+(?:st|nd|rd|th))$/i.test(w),
  );
  const words =
    filtered.length > 0
      ? filtered
      : rawTokens.filter((w) => !/^\d+$/.test(w)).length > 0
      ? rawTokens.filter((w) => !/^\d+$/.test(w))
      : rawTokens;
  if (words.length === 0) return "BL";
  if (words.length === 1) {
    const word = words[0].toUpperCase();
    return word.length <= 3 && /^[A-ZÀ-ÖØ-Þ]+$/.test(word) ? word.slice(0, 3) : word.slice(0, 2);
  }
  const secondIdx = words.length <= 3 ? words.length - 1 : 1;
  return (words[0][0] + words[secondIdx][0]).toUpperCase();
}

function looksLikePersonName(text: string | null | undefined): boolean {
  if (!text) return false;
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  if (tokens.length < 2 || tokens.length > 4) return false;
  const bad = new Set([
    "party", "congress", "united", "states", "republic", "city", "county",
    "team", "club", "hurricanes", "dodgers", "49ers", "yankees", "brewers",
    "celtics", "wild", "oilers", "devils", "avalanche", "apple", "nvidia",
    "alphabet", "microsoft", "amazon", "tesla", "google", "meta", "above",
    "below", "before", "after", "top", "no", "yes",
  ]);
  for (const t of tokens) {
    const clean = t.toLowerCase().replace(/[^a-z]/g, "");
    if (bad.has(clean)) return false;
    if (/^[a-zA-Z]/.test(t) && t[0] !== t[0].toUpperCase()) return false;
  }
  return true;
}

function firstMeaningfulOutcome(
  topOutcomes: ReadonlyArray<{ name?: string; label?: string }> | null | undefined,
): string | null {
  for (const o of topOutcomes ?? []) {
    const n = (o?.name ?? o?.label ?? "").trim();
    if (!n) continue;
    if (PARTY_OR_BUCKET_OUTCOME_RE.test(n)) continue;
    return n;
  }
  return null;
}

export function classifyDiscoverSubject(
  name: string | null | undefined,
  category: string | null | undefined,
  topOutcomes?: ReadonlyArray<{ name?: string; label?: string }> | null,
): { kind: DiscoverVisualKind; label: string; tickerOk: boolean } {
  const title = (name ?? "").trim();
  const cat = (category ?? "").trim().toLowerCase();
  const lead = firstMeaningfulOutcome(topOutcomes);

  if (MUSIC_TITLE_RE.test(title)) {
    return { kind: "song", label: lead || title, tickerOk: false };
  }
  for (const pat of PERSON_HEADLINE_PATTERNS) {
    const m = pat.exec(title);
    if (m) {
      let person = m[1].trim();
      if (person.toLowerCase() === "trump") person = "Donald Trump";
      else if (person.toLowerCase() === "putin") person = "Vladimir Putin";
      return { kind: "person", label: person, tickerOk: false };
    }
  }
  if (FILM_TITLE_RE.test(title) || (cat === "entertainment" && title.includes('"'))) {
    if (lead && looksLikePersonName(lead) && title.toLowerCase().includes("actor")) {
      return { kind: "person", label: lead, tickerOk: false };
    }
    const quoted = /["“]([^"”]{2,80})["”]/.exec(title);
    return { kind: "film", label: quoted ? quoted[1].trim() : lead || title, tickerOk: false };
  }
  if (cat === "mma" || title.toLowerCase().includes("ufc")) {
    return { kind: "person", label: lead || title, tickerOk: false };
  }
  if (TEAM_SPORT_CATS.has(cat) || TEAM_TITLE_RE.test(title)) {
    let subj = lead || title;
    if (/\s+vs\.?\s+/i.test(subj)) subj = subj.split(/\s+vs\.?\s+/i)[0].trim();
    return { kind: "team", label: subj, tickerOk: false };
  }
  if (PERSON_ELECTION_OR_ROLE_RE.test(title) && lead && looksLikePersonName(lead)) {
    return { kind: "person", label: lead, tickerOk: false };
  }
  if (TICKER_RE.test(title) || ORG_TITLE_RE.test(title)) {
    return { kind: "organization", label: title, tickerOk: true };
  }
  return { kind: "topic", label: title || "Discover", tickerOk: false };
}

function inferPresentation(
  url: string,
  kind: DiscoverVisualKind,
  wirePresentation?: unknown,
): DiscoverImagePresentation {
  if (
    wirePresentation === "logo" ||
    wirePresentation === "portrait" ||
    wirePresentation === "cover" ||
    wirePresentation === "photo"
  ) {
    return wirePresentation;
  }
  const host = hostOf(url);
  if ((host.includes("espncdn.com") && url.includes("/teamlogos/")) || host.includes("flagcdn.com")) {
    return "logo";
  }
  if (host.includes("espncdn.com") && url.includes("/headshots/")) {
    return "portrait";
  }
  if (host.includes("archive.org") || host.includes("coverartarchive.org")) {
    return "cover";
  }
  if (kind === "person" && host.includes("wikimedia.org")) {
    return "portrait";
  }
  return "photo";
}

function parseWireMonogram(raw: unknown): DiscoverMonogram | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.initials !== "string" || !r.initials.trim()) return null;
  const kind = (typeof r.kind === "string" ? r.kind : "topic") as DiscoverVisualKind;
  return {
    initials: r.initials.trim(),
    label: typeof r.label === "string" ? r.label : "",
    kind,
    bgHex: typeof r.bg_hex === "string" ? r.bg_hex : "#1e293b",
    accentHex: typeof r.accent_hex === "string" ? r.accent_hex : "#475569",
  };
}

export function resolveDiscoverFuturesVisual(data: {
  name?: string | null;
  llm_sport_category?: string | null;
  top_outcomes?: ReadonlyArray<{ name?: string; label?: string }> | null;
  image_url?: string | null;
}): ResolvedDiscoverVisual {
  const wire = data as Record<string, unknown>;
  const classified = classifyDiscoverSubject(
    data.name,
    data.llm_sport_category,
    data.top_outcomes,
  );
  const wireMono = parseWireMonogram(wire.image_monogram);
  const [bgHex, accentHex] = hashPalette(classified.label, classified.kind);
  const monogram: DiscoverMonogram = wireMono ?? {
    initials: computeDiscoverInitials(classified.label, classified.tickerOk),
    label: classified.label,
    kind: classified.kind,
    bgHex,
    accentHex,
  };

  let url = typeof data.image_url === "string" ? data.image_url.trim() : "";
  if (url) {
    if (isBlockedPexelsPhoto(url)) {
      url = "";
    } else if (classified.kind === "song" && isTmdbUrl(url)) {
      url = "";
    } else if (classified.kind !== "topic" && isPexelsStockUrl(url)) {
      url = "";
    }
  }

  if (!url) {
    return {
      imageUrl: null,
      presentation: null,
      kind: monogram.kind,
      monogram,
    };
  }

  return {
    imageUrl: url,
    presentation: inferPresentation(url, classified.kind, wire.image_presentation),
    kind: classified.kind,
    monogram,
  };
}

export function resolveDiscoverAuxiliaryVisual(
  data: Record<string, unknown>,
  fallbackLabel: string,
  fallbackKind: DiscoverVisualKind,
): ResolvedDiscoverVisual {
  const wireMono = parseWireMonogram(data.image_monogram);
  const [bgHex, accentHex] = hashPalette(fallbackLabel, fallbackKind);
  const monogram: DiscoverMonogram = wireMono ?? {
    initials: computeDiscoverInitials(fallbackLabel, false),
    label: fallbackLabel,
    kind: fallbackKind,
    bgHex,
    accentHex,
  };
  let url = typeof data.image_url === "string" ? data.image_url.trim() : "";
  if (url && (isBlockedPexelsPhoto(url) || (fallbackKind !== "topic" && isPexelsStockUrl(url)))) {
    url = "";
  }
  return {
    imageUrl: url || null,
    presentation: url ? inferPresentation(url, fallbackKind, data.image_presentation) : null,
    kind: fallbackKind,
    monogram,
  };
}
