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
 * Human label for a `FuturesMarket.category`, or `null` when there is nothing
 * to show.
 *
 * Returns `null` — not `""` — for absent/blank input so a caller can use it as
 * a truthiness gate and render no chip at all, which is what the card already
 * does for a null category.
 */
export function marketCategoryLabel(
  category: string | null | undefined,
): string | null {
  if (typeof category !== "string") return null;
  const key = category.trim();
  if (!key) return null;
  const exception = CATEGORY_LABEL_EXCEPTIONS[key.toLowerCase()];
  if (exception) return exception;
  const cased = toTitleCaseAcronymSafe(key);
  // `toTitleCaseAcronymSafe` returns "" for input it cannot case; never let a
  // blank chip render, and never fall back to the raw value to fill it.
  return cased || null;
}
