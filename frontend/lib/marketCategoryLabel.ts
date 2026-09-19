/**
 * UX-P276 / #2710 — a market's category chip reads as English, never as the
 * column value.
 *
 * `/sports` "Player Props & Progressions" printed `FuturesMarket.category`
 * straight into a chip beside the sport name, so the reader got the enum:
 * Alex, on mobile /sports 2026-09-02 15:40, "sport line reads 'TENNIS
 * game_prop' (raw enum)". Measured on the live strip 2026-09-03 (the DOM, not
 * the payload — `limit: 20`, which is what `app/sports/page.tsx` requests):
 * 16 of the 20 rendered cards carried a raw chip, and it was never only
 * `game_prop` — `championship` x12, `placement` x3, `make_cut` x1.
 *
 * THE FALLBACK IS THE SHIP, NOT THE MAP. The whole open-market vocabulary is
 * 15 values (measured, exact, `GROUP BY category` over 45,461 open rows on
 * 2026-09-03) and THIRTEEN of them are already correct English once title-cased
 * — `politics`, `weather`, `geopolitics`, `championship`, `placement` and so
 * on. Only two read as jargon after casing. So this maps the two exceptions and
 * sends everything else through `toTitleCaseAcronymSafe`, which means a
 * category value that does not exist yet STILL cannot reach the reader as
 * `snake_case`. A map alone would have been correct for today's 15 and silently
 * wrong for the 16th.
 *
 * NOT `SUBCATEGORY_DISPLAY_NAMES` (`lib/sportCategories.ts`). That map happens
 * to contain a `game_prop` key, which makes it look like the home for this, but
 * it is a *tag* vocabulary — its other keys are `tesla`, `taylor_swift`,
 * `wheel_of_fortune`. `FuturesMarket.category` is a different, closed column.
 * Merging the two would let a tag rename silently change a market chip.
 */
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";

/**
 * The only two values that title-casing leaves as jargon.
 *
 * `game_prop` -> "Game Prop" is grammatical but reads as a schema name; the
 * card is showing several of them. `make_cut` -> "Make Cut" is not English.
 * Everything else in the measured vocabulary is deliberately absent: adding
 * `politics: "Politics"` here would be a second place to keep in sync with no
 * behaviour of its own.
 */
const CATEGORY_LABEL_EXCEPTIONS: Record<string, string> = {
  game_prop: "Game Props",
  make_cut: "Makes the Cut",
};

/**
 * #5516 (the half #2710 could not see) — CATEGORIES THAT NAME A RUNG, AND THE
 * RUNG THEY NAME.
 *
 * `category` is not one vocabulary, it is two wearing one column. Polymarket's
 * poller returns the single value `championship` from EVERY arm of its cascade
 * that lands on a sport (`tasks/polymarket.py` `_tags_to_category` ->
 * `("championship", None)`, `resolve_event_category` -> `category =
 * "championship"`), so the column there means "this is sport", spelled with the
 * wrong word. #2710 then title-cases it faithfully onto the card, and the reader
 * gets **Championship** in the same purple pill as "MLB World Series Champion
 * 2026".
 *
 * MEASURED on production 2026-09-19: 12,724 open rows carry
 * `category='championship'` with `market_tier = 5` (11,025 Polymarket, 1,698
 * Kalshi, 1 Odds API). Specimen from a 390px LOOK at `/search?q=chiefs`: "What
 * will the announcers say during the Colts vs Chiefs game?" — a novelty prop,
 * badged Championship, `market_tier: 5`, `market_type_label: "Prop"`.
 *
 * THE BACKEND ALREADY DISAGREES WITH ITSELF IN THE SAME PAYLOAD, which is what
 * makes this decidable without inventing a word. `market_tier` is computed from
 * the market NAME by `compute_market_tier`, whose own comment says name patterns
 * are more reliable "(Polymarket uses 'championship' for everything)". So when
 * the category claims a specific rung and the row landed in the catch-all rung,
 * the claim is unsupported by the row's own classifier.
 *
 * SUPPRESS, DO NOT SUBSTITUTE. The honest replacement is not available: the 5
 * affected rows on that one card are a moneyline, three season-series markets
 * and a novelty question, and no single word covers them. `market_type_label`
 * would read "Prop" beside a sibling reading "Game Props" — a new inconsistency
 * for an old one. Rendering no chip is already the designed null state (the
 * function returns `null` so the card can gate on it), so the card loses a false
 * claim and gains nothing wrong.
 *
 * ONLY THE MAXIMAL CONTRADICTION. Tiers 2-4 are adjacent rungs of the same
 * hierarchy (conference / award / division) where "Championship" is at worst
 * imprecise; ~750 open rows sit there and are deliberately LEFT, so this ships
 * the population the LOOK actually found rather than a sweep nobody measured.
 */
const CATEGORY_CLAIMS_TIER: Record<string, number> = {
  championship: 1,
};

/** `compute_market_tier`'s catch-all: "props / other", and its unclassified default. */
const UNCLASSIFIED_TIER = 5;

/**
 * Human label for a `FuturesMarket.category`, or `null` when there is nothing
 * to show.
 *
 * Returns `null` — not `""` — for absent/blank input so a caller can use it as
 * a truthiness gate and render no chip at all, which is what the card already
 * does for a null category.
 */
export function marketCategoryLabel(
  category: string | null | undefined,
  marketTier?: number | null,
): string | null {
  if (typeof category !== "string") return null;
  const key = category.trim();
  if (!key) return null;
  // #5516 — the row's own tier contradicts what the category claims, so there is
  // nothing true to print. Gated on an EXPLICIT 5: `market_tier` is optional on
  // the payload and absent during a Vercel-ahead-of-Heroku window, and a missing
  // tier must leave the chip exactly as it is today rather than blank every card.
  if (
    CATEGORY_CLAIMS_TIER[key.toLowerCase()] !== undefined &&
    marketTier === UNCLASSIFIED_TIER
  ) {
    return null;
  }
  const exception = CATEGORY_LABEL_EXCEPTIONS[key.toLowerCase()];
  if (exception) return exception;
  const cased = toTitleCaseAcronymSafe(key);
  // `toTitleCaseAcronymSafe` returns "" for input it cannot case; never let a
  // blank chip render, and never fall back to the raw value to fill it.
  return cased || null;
}
