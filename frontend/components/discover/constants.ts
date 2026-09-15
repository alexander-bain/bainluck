import { categoryEmoji } from "@/lib/categoryEmoji";
import { getCategoryForLeague } from "@/lib/sportCategories";

export const CATEGORY_GRADIENTS: Record<string, string> = {
  basketball: "linear-gradient(135deg, #7c2d12, #c2410c)",
  football: "linear-gradient(135deg, #14532d, #15803d)",
  baseball: "linear-gradient(135deg, #7f1d1d, #b91c1c)",
  hockey: "linear-gradient(135deg, #1e3a5f, #2563eb)",
  soccer: "linear-gradient(135deg, #064e3b, #059669)",
  golf: "linear-gradient(135deg, #14532d, #166534)",
  mma: "linear-gradient(135deg, #450a0a, #991b1b)",
  boxing: "linear-gradient(135deg, #450a0a, #991b1b)",
  motorsports: "linear-gradient(135deg, #1c1917, #44403c)",
  economics: "linear-gradient(135deg, #2e1065, #7c3aed)",
  culture: "linear-gradient(135deg, #831843, #db2777)",
  tech: "linear-gradient(135deg, #083344, #0891b2)",
  politics: "linear-gradient(135deg, #1e1b4b, #4338ca)",
  geopolitics: "linear-gradient(135deg, #1e1b4b, #3730a3)",
  olympics: "linear-gradient(135deg, #78350f, #d97706)",
  cricket: "linear-gradient(135deg, #134e4a, #14b8a6)",
  weather: "linear-gradient(135deg, #0c4a6e, #0284c7)",
  entertainment: "linear-gradient(135deg, #701a75, #c026d3)",
  // #4264. The `health` shelf has been a real destination since CAL-P132 but had no
  // entry in either map, so every health market fell to DEFAULT_CAT (grey, 📊) on the
  // web while the app already drew 🏥. Teal, to sit clearly apart from weather's sky
  // blue — the two shelves this ship separates must not read as the same chip.
  health: "linear-gradient(135deg, #134e4a, #0d9488)",
};

const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
  basketball: { bg: "bg-orange-500/15", text: "text-orange-600" },
  football: { bg: "bg-green-700/15", text: "text-green-700" },
  baseball: { bg: "bg-red-500/15", text: "text-red-600" },
  hockey: { bg: "bg-blue-500/15", text: "text-blue-600" },
  soccer: { bg: "bg-emerald-500/15", text: "text-emerald-600" },
  golf: { bg: "bg-lime-600/15", text: "text-lime-700" },
  mma: { bg: "bg-red-700/15", text: "text-red-700" },
  boxing: { bg: "bg-red-600/15", text: "text-red-600" },
  motorsports: { bg: "bg-gray-600/15", text: "text-gray-600" },
  economics: { bg: "bg-violet-500/15", text: "text-violet-600" },
  culture: { bg: "bg-pink-500/15", text: "text-pink-600" },
  tech: { bg: "bg-cyan-500/15", text: "text-cyan-600" },
  politics: { bg: "bg-indigo-500/15", text: "text-indigo-600" },
  geopolitics: { bg: "bg-indigo-500/15", text: "text-indigo-600" },
  olympics: { bg: "bg-amber-500/15", text: "text-amber-600" },
  cricket: { bg: "bg-teal-500/15", text: "text-teal-600" },
  weather: { bg: "bg-sky-500/15", text: "text-sky-600" },
  entertainment: { bg: "bg-fuchsia-500/15", text: "text-fuchsia-600" },
  health: { bg: "bg-teal-500/15", text: "text-teal-600" },
};

const DEFAULT_COLORS = { bg: "bg-gray-500/15", text: "text-gray-600" };
const DEFAULT_EMOJI = "📊";

/** Chip colours + icon for a shelf.
 *
 * #4326. The icon comes from `lib/categoryEmoji.ts`, the one map every web
 * surface reads, so a card cannot wear one glyph here and another on Browse.
 *
 * Colours and icons fall back INDEPENDENTLY, and that is the point. A shelf
 * with a named icon but no colour entry now draws its real icon on a neutral
 * chip instead of the grey 📊 — measured 2026-09-09, 10 of 113 served Discover
 * cards were falling through to 📊 (esports, cycling, lacrosse, legal), and
 * `tennis` had 7,463 open markets and no entry at all. Colours are a design
 * call per shelf; an icon is not, and withholding the icon until someone picks
 * a colour is how `health` came to wear a weather chip (#4264).
 */
export function getCat(cat: string | null | undefined) {
  const key = chipCategory(cat);
  if (!key) return { ...DEFAULT_COLORS, emoji: DEFAULT_EMOJI };
  return {
    ...(CATEGORY_COLORS[key] ?? DEFAULT_COLORS),
    emoji: categoryEmoji(key) ?? DEFAULT_EMOJI,
  };
}

/**
 * The shelf a card's chip belongs to, from either a shelf name or a SPORT KEY.
 *
 * #6247. Every one of these maps is keyed on a shelf name — `football`,
 * `hockey`, `motorsports` — and `components/discover/EventCard` was handing
 * them `data.sport.split("_")[0]`, which is a sport-key segment:
 * `americanfootball`, `icehockey`, `rugbyleague`. No match, so every NFL and
 * NHL card on the landing page drew the grey fallback 📊 and lost its
 * gradient. Measured over a 10-day window: 892 of 8,806 events —
 * americanfootball 659, icehockey 198, rugbyleague 30, motorsport 5.
 *
 * #4326 repaired four fallers by ADDING shelf names to the maps, which could
 * never reach these: `americanfootball` is not a shelf name and never will be.
 * The mapping from sport key to shelf already exists and is used by the rest
 * of the site — `getCategoryForLeague` in `lib/sportCategories.ts` — so this
 * reads it rather than minting a second answer here.
 *
 * ⚠️ IT MUST BE GIVEN THE WHOLE KEY. Those prefixes carry the underscore
 * (`americanfootball_`), so the truncated segment the card used to pass
 * matches nothing and this function would be inert — the assertion in
 * `discoverCardChipKnowsItsSport6247.test.tsx` is on the card's own render for
 * exactly that reason.
 *
 * A shelf name comes back untouched — every prefix carries a trailing
 * underscore, so `politics`, `weather` and `health` match none of them — which
 * is why `llm_sport_category` callers need no fast path around this and do not
 * have one: an early return for "I already know this name" was measured
 * equivalent for every value any caller passes, and an untested branch that
 * changes nothing is worse than no branch. An unknown key is likewise returned
 * as-is, to fall through to the default the way it always has.
 */
export function chipCategory(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const key = raw.toLowerCase();
  return getCategoryForLeague(key)?.key ?? key;
}
