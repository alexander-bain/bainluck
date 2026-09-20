/**
 * THE GLOBAL TEMPERATURE MAP'S HEADER, DERIVED FROM THE PAYLOAD IT HEADS
 * (#7423).
 *
 * ═══ WHAT A READER SAW, production 2026-09-20 at 1280 ═══
 *
 *   GLOBAL TEMPERATURE MAP
 *   42 cities. Tomorrow's high, as a probability distribution.
 *   Polymarket & Kalshi · 336 markets
 *
 * Neither half of that mark was a reading of anything.
 *
 * **336** was `allCities.length * 8`, a literal `8` typed into the component.
 * `GET /api/weather/cities`, measured the same morning: 42 cities, 42 rows
 * carrying a `marketId`, 42 distinct `marketId` values. There is no quantity on
 * that endpoint equal to 336. The near-miss reading — "8 is the bucket count" —
 * does not survive the payload either: the ladders run 7, 10 and 11 buckets
 * (Buenos Aires 7, Austin 10, Seattle 10, the other 39 at 11), totalling 456.
 * So the repair is not `8 → 11`; a constant is the wrong SHAPE here, and the
 * next ladder change would re-break whichever constant were chosen.
 *
 * **"Polymarket & Kalshi"** was typed too. The payload's own `srcs` read
 * `["polymarket"]` on 42 of 42 cities — no Kalshi market backed a single city
 * on the card. The map's own footer already said `0 cross-source` four hundred
 * pixels below the mark that named two venues.
 *
 * ═══ THE UNIT, AND WHY IT IS CITIES AND NOT BUCKETS ═══
 *
 * `backend/app/routes/weather.py` picks ONE `FuturesMarket` per city — it
 * serves `"marketId": chosen.id` — and `high.dist` is that market's OUTCOMES.
 * A bucket is therefore an outcome of a market, not a market. Printing 456
 * would swap one over-claim for another; the honest count of markets behind
 * this card is the number of cities on it.
 *
 * That makes the count agree with the title by construction rather than by
 * coincidence, which is the point: both now come from the same list, so they
 * cannot drift apart the way a hardcoded factor did.
 *
 * ═══ WHY THE FILTER LIVES HERE TOO ═══
 *
 * The card holds three counts — this mark, the "N of 42 cities" chip beside the
 * search box, and `MapCanvas`'s "N cities shown" footer. The last two followed
 * the search box and this one did not, so typing a city name left a 28px
 * headline reading "42 cities" over a map with one dot on it.
 *
 * Filtering here, and handing the caller back the very list it renders, is what
 * stops that returning: the component is left with ONE city list and no second
 * one to head the card with by mistake. A change that fed this function the
 * unfiltered list would empty the search box's effect on the map as well, which
 * is a visible break rather than a silent disagreement.
 */

import { sourceLabel } from "@/lib/sourceColors";
import type { CityData } from "./data";

export type TemperatureMapHeader = {
  /** The cities the card should RENDER — the same list the header describes. */
  cities: CityData[];
  /** The `<h2>`: the count, then the card's standing sentence. */
  title: string;
  /** The small mark under it: the venues actually present, then the count. */
  meta: string;
  /** "N of M cities" while a search narrows the list, else `null`. */
  scope: string | null;
};

/** English, not a template: `1 city` is a reader-visible detail (#7423). */
export function pluralize(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * The card's city search, by name, case- and whitespace-insensitive.
 *
 * An empty or blank query is NOT a filter: it returns THE LIST ITSELF, not a
 * copy, and that identity is load-bearing. `MapCanvas` memoises its pin-collision
 * solver on `[cities]` — 40 iterations over every pair, ~70k steps at the 42
 * cities production serves — and this card re-renders on every `onHover`. A
 * defensive `[...allCities]` here would hand that memo a new array on each
 * mouse move and run the solver again every time. The pre-#7423 code passed
 * `allCities` straight through for exactly this reason; keep it that way.
 *
 * Nothing downstream mutates the array (`MapCanvas` copies via
 * `cities.map(c => ({ ...c }))` before touching a pin), so sharing it is safe.
 */
export function filterCitiesByName(
  allCities: CityData[],
  query: string,
): CityData[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return allCities;
  return allCities.filter(c => c.name.toLowerCase().includes(needle));
}

/**
 * The venues a list of cities is actually priced by, named by the registry.
 *
 * A list with no venues at all yields an empty string, so the caller prints a
 * count alone instead of a dangling separator. A source the registry does not
 * know still reaches the reader under its own key (`sourceLabel`'s fallback),
 * because a nameless supplier is worse than an unpolished name.
 *
 * The `?? []` is THIS FUNCTION'S contract and not a promise about the card:
 * `MapCanvas` reads `c.srcs.length` unguarded, so a payload with a city missing
 * `srcs` takes the map down whatever happens here. It is pinned at unit level
 * because that is the only level at which it is reachable — claiming the card
 * fails open on that shape would be false.
 */
export function venuesOf(cities: readonly CityData[]): string {
  const labels = new Set<string>();
  for (const c of cities) {
    for (const s of c.srcs ?? []) {
      if (s) labels.add(sourceLabel(s, s));
    }
  }
  return [...labels].sort().join(" & ");
}

export function temperatureMapHeader(
  allCities: CityData[],
  query: string,
): TemperatureMapHeader {
  const cities = filterCitiesByName(allCities, query);
  const venues = venuesOf(cities);
  const markets = pluralize(cities.length, "market", "markets");

  return {
    cities,
    title: `${pluralize(cities.length, "city", "cities")}. Tomorrow's high, as a probability distribution.`,
    meta: venues ? `${venues} · ${markets}` : markets,
    scope: query.trim()
      ? `${cities.length} of ${allCities.length} cities`
      : null,
  };
}
