/**
 * #4326 — ONE emoji per shelf, for every web surface.
 *
 * A reader tapping from Discover into Browse used to watch the icon change
 * under a card that had not. Four independent maps carried their own answers:
 *
 *   - `components/discover/constants.ts`  `CATEGORY_COLORS`  (Discover cards)
 *   - `components/CategoryBrowser.tsx`    `CATEGORY_EMOJI`   (Browse, on /search)
 *   - `lib/sportCategories.ts`            `SPORT_CATEGORIES` (/categories)
 *   - iOS `DiscoverFuturesCard.swift` + `FuturesDetailView.swift`
 *
 * The issue named two disagreements (`health`, `weather`). A census of all four
 * on 2026-09-09 found **ten**:
 *
 *   aussierules  🏉 / 🏈
 *   economics    📈 / 📊 / 📊 / 📈        <- 2nd biggest shelf on Browse
 *   health       🏥 / 💊 / 🏥 / 🏥
 *   mma          🥊 / 🥋 / 🥋
 *   motorsports  🏎 / 🏎️ / 🏎️            <- VS16 only
 *   olympics     🏅 / 🥇 / 🏅
 *   other        📋 / 🏆
 *   politics     🏛 / 🏛️ / 🗳️ / 🏛        <- a building vs a ballot box
 *   tech         💻 / 💻 / 🔬 / 💻
 *   weather      🌤 / 🌦️ / 🌤️ / 🌤
 *
 * Two of those are VARIATION-SELECTOR differences, not glyph differences:
 * `🌤` and `🌤️` differ only by U+FE0F, which forces emoji presentation and can
 * paint differently. A naive equality test passes them straight through and a
 * grep for one does not find the other, which is exactly how they survived.
 * Everything here is stored WITHOUT VS16 and the drift test normalises before
 * comparing (`stripVariationSelectors`).
 *
 * ## How each winner was chosen, so the next shelf does not need a debate
 *
 *   1. If iOS draws it, iOS wins. It is the app, it is Alex's primary surface,
 *      and #4264 already set that precedent for `health`.
 *   2. Otherwise the Discover map wins — Discover is the default landing page.
 *   3. EXCEPT where 1 or 2 would make two different shelves share one glyph.
 *      `mma` keeps 🥋 rather than taking Discover's 🥊, which `boxing` already
 *      owns; `aussierules` keeps 🏉 rather than `football`'s 🏈.
 *
 * Adding a shelf: add it HERE. `CATEGORY_COLORS` still owns the chip colours,
 * and a shelf with no colour entry draws the neutral chip with its real icon
 * rather than the grey 📊 fallback — which is how `health` came to wear a
 * weather chip until #4264, and how `tennis` (7,463 open markets) still wore
 * 📊 when this file was written.
 */

/** Strip U+FE0F so `🌤` and `🌤️` compare equal. */
export function stripVariationSelectors(emoji: string): string {
  return emoji.replace(/[︎️]/g, "");
}

export const CATEGORY_EMOJI: Record<string, string> = {
  // ── league sub-shelves (only `/categories` groups this finely) ──
  //
  // They deliberately REPEAT their parent's icon: on a page that already prints
  // "NFL" and "College Football" as names, two different balls would read as two
  // different sports. Listed here rather than left to a local fallback so the
  // drift test can hold every rendered icon, not just the ones that disagreed.
  college_basketball: "🏀",
  college_football: "🏈",
  golf_dp_world: "⛳",
  golf_liv: "⛳",
  golf_lpga: "⛳",
  golf_pga: "⛳",
  nba: "🏀",
  nfl: "🏈",

  // ── sports ──
  adventure: "🧗",
  aussierules: "🏉", // rule 3: 🏈 is football's
  baseball: "⚾",
  basketball: "🏀",
  boxing: "🥊",
  chess: "♟",
  cricket: "🏏",
  cycling: "🚴",
  darts: "🎯",
  dodgeball: "🤾",
  esports: "🎮",
  football: "🏈",
  golf: "⛳",
  handball: "🤾",
  hockey: "🏒",
  horse_racing: "🏇",
  lacrosse: "🥍",
  mma: "🥋", // rule 3: 🥊 is boxing's
  motorsports: "🏎",
  olympics: "🏅",
  pickleball: "🏓",
  poker: "🃏",
  rugby: "🏉",
  sailing: "⛵",
  soccer: "⚽",
  softball: "🥎",
  squash: "🎾",
  surfing: "🏄",
  table_tennis: "🏓",
  tennis: "🎾",

  // ── non-sports ──
  auto: "🚗",
  auto_industry: "🚗",
  business: "💼",
  combat_archery: "🏹",
  commodities: "🛢",
  crypto: "🪙",
  culture: "🎭",
  economics: "📈", // rule 1: iOS draws 📈; Browse's 📊 loses
  energy: "⚡",
  entertainment: "🎬",
  geopolitics: "🌍",
  health: "🏥", // rule 1 (#4264)
  legal: "⚖",
  politics: "🏛", // rule 1: iOS draws the building, not 🗳
  space: "🚀",
  tech: "💻", // rule 1: iOS draws 💻; /categories' 🔬 loses
  watchmaking: "⌚",
  weather: "🌤", // rule 1, and WITHOUT VS16
  other: "📋",
};

/** The icon for a shelf, or `null` when we have never named one. */
export function categoryEmoji(category: string | null | undefined): string | null {
  if (!category) return null;
  return CATEGORY_EMOJI[category.toLowerCase()] ?? null;
}
