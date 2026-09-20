/**
 * #7423 — `/weather`'s temperature map stops advertising "336 markets" and
 * stops naming a venue it holds nothing from.
 *
 * ═══ WHAT A READER SAW, production 2026-09-20 at 1280 ═══
 *
 *   GLOBAL TEMPERATURE MAP
 *   42 cities. Tomorrow's high, as a probability distribution.
 *   Polymarket & Kalshi · 336 markets
 *
 * `336` was `allCities.length * 8` — a literal typed into the component. One
 * read of `GET /api/weather/cities` the same morning (HTTP 200, 30,102 bytes):
 *
 *   cities                       42
 *   rows carrying a `marketId`   42        distinct `marketId` values   42
 *   bucket rows (`high.dist`)   456        histogram {11: 39, 10: 2, 7: 1}
 *   `srcs` entries               42        every one of them ["polymarket"]
 *
 * No quantity on that endpoint is 336. The tempting repair — `8 → 11` — is the
 * one the issue forbids, and the payload says why: the ladders are 7, 10 and 11
 * buckets long TODAY, so a constant is already wrong before anyone changes one.
 *
 * The second half of the mark was invented the same way. `srcs` is
 * `["polymarket"]` on 42 of 42 cities, so "Polymarket & Kalshi" named a venue
 * backing nothing on the card — with the map's own footer reading
 * `0 cross-source` in the same screenshot.
 *
 * ═══ WHAT THESE ASSERTIONS ARE BUILT TO KILL ═══
 *
 * Every fixture below has ladders of DIFFERING length, because a fixture where
 * every city carries the same bucket count is satisfied by a constant and the
 * guard is vacuous — the exact shape that let `× 8` live. Three mutants are
 * named and each is refuted by construction, not by hope:
 *
 *   `× 8` restored        → 8N ≠ N for every N ≥ 1
 *   the bucket sum        → the sums (7) and (12) differ from the counts (2, 3)
 *   the fixture's own N   → two fixtures of DIFFERENT size assert the same rule
 *
 * The last one is why there are two sizes rather than one bigger fixture.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherMapCountFollowsItsPayload7423
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { CityData, TempBucket } from "@/components/weather/data";
import {
  filterCitiesByName,
  pluralize,
  temperatureMapHeader,
  venuesOf,
} from "@/components/weather/temperatureMapHeader";

/* ── SWR is the only thing between TemperatureMap and its payload ───────── */

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

let swrError: unknown;

// eslint-disable-next-line @typescript-eslint/no-var-requires
const TemperatureMap = require("@/components/weather/TemperatureMap").default;

/** Strip tags so assertions read what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/* ── Specimens, in the shape the route serves ───────────────────────────── */

/**
 * A ladder with a real mode. Flat zeroes would render a histogram whose bars
 * are each `prob / max` of nothing, and React would warn `NaN` is an invalid
 * opacity — a fixture that is not a shape this endpoint serves.
 */
function ladder(n: number): TempBucket[] {
  return Array.from({ length: n }, (_, i) => {
    const probability = (i + 1) / ((n * (n + 1)) / 2);
    return { label: `${60 + i}°F`, prob: Math.round(probability * 100), probability };
  });
}

function city(
  id: string,
  name: string,
  buckets: number,
  srcs: CityData["srcs"] = ["polymarket"],
): CityData {
  return {
    id,
    name,
    preferredX: 18.8,
    preferredY: 45.4,
    x: 18.8,
    y: 45.4,
    region: "Americas",
    srcs,
    marketId: 61500175,
    high: { unit: "F", mode: 78, dist: ladder(buckets) },
  };
}

/**
 * TWO cities, 3 + 4 = 7 buckets. Every number here is distinct from every
 * other, so no assertion can pass by coincidence: 2 ≠ 7 (bucket sum),
 * 2 ≠ 16 (`× 8`), 2 ≠ 3 (the other fixture's size).
 */
const TWO = [city("nyc", "New York", 3), city("la", "Los Angeles", 4)];

/** THREE cities, 3 + 4 + 5 = 12 buckets. 3 ≠ 12 ≠ 24. */
const THREE = [
  city("nyc", "New York", 3),
  city("la", "Los Angeles", 4),
  city("seattle", "Seattle", 5),
];

/* ═══ 1. The count is the list, at two different list sizes ═══════════════ */

describe("#7423 · the market count is read off the payload, never computed", () => {
  test("two cities read two markets, and neither 16 nor 7", () => {
    const { meta } = temperatureMapHeader(TWO, "");
    expect(meta).toBe("Polymarket · 2 markets");
    expect(meta).not.toContain("16"); // the `× 8` mutant
    expect(meta).not.toContain("7 markets"); // the bucket-sum mutant
  });

  test("three cities read three markets — the same rule, a different size", () => {
    const { meta } = temperatureMapHeader(THREE, "");
    expect(meta).toBe("Polymarket · 3 markets");
    expect(meta).not.toContain("24");
    expect(meta).not.toContain("12 markets");
  });

  test("the count and the title's city count are the SAME number, by construction", () => {
    for (const fixture of [TWO, THREE]) {
      const { title, meta } = temperatureMapHeader(fixture, "");
      expect(title.startsWith(`${fixture.length} cit`)).toBe(true);
      expect(meta.endsWith(`${fixture.length} markets`)).toBe(true);
    }
  });

  test("a ladder growing a bucket does NOT move the market count", () => {
    // The mutant this refutes is the plausible one: 8 → 11, or any read of the
    // ladder. `high.dist` is a market's OUTCOMES (weather.py serves one
    // `marketId` per city), so lengthening it must change nothing here.
    const stretched = [city("nyc", "New York", 3), city("la", "Los Angeles", 40)];
    expect(temperatureMapHeader(stretched, "").meta).toBe("Polymarket · 2 markets");
  });
});

/* ═══ 2. The venues are the payload's, not a typed pair ═══════════════════ */

describe("#7423 · the mark names the venues the cities actually carry", () => {
  test("a polymarket-only payload — production's shape today — names ONLY Polymarket", () => {
    expect(venuesOf(TWO)).toBe("Polymarket");
    expect(temperatureMapHeader(TWO, "").meta).not.toContain("Kalshi");
  });

  test("a payload that does carry Kalshi names both, deduped and stable", () => {
    const mixed = [
      city("nyc", "New York", 3, ["polymarket"]),
      city("la", "Los Angeles", 4, ["kalshi"]),
      city("chi", "Chicago", 5, ["kalshi", "polymarket"]),
    ];
    expect(venuesOf(mixed)).toBe("Kalshi & Polymarket");
    expect(temperatureMapHeader(mixed, "").meta).toBe("Kalshi & Polymarket · 3 markets");
  });

  test("the names come from the registry, not from the payload's raw keys", () => {
    // `srcs` arrives lowercase off the wire (`_market_source` lowercases it).
    // A mark printing "polymarket" would be this component inventing a second
    // name for a supplier the registry already names — #2442's rule.
    expect(venuesOf(TWO)).not.toContain("polymarket");
  });

  test("no venue at all leaves a count alone, never a dangling separator", () => {
    const anonymous = [city("nyc", "New York", 3, []), city("la", "Los Angeles", 4, [])];
    expect(temperatureMapHeader(anonymous, "").meta).toBe("2 markets");
  });

  test("a city whose `srcs` is absent entirely contributes no venue and does not throw", () => {
    // PINNED AT THIS LEVEL DELIBERATELY. `MapCanvas` reads `c.srcs.length`
    // unguarded, so this shape takes the card down before it reaches the
    // header — the fail-open is `venuesOf`'s own contract, not the card's, and
    // asserting it through a render would be asserting something untrue.
    const srcless = { ...city("nyc", "New York", 3) } as CityData;
    delete (srcless as Partial<CityData>).srcs;
    expect(venuesOf([srcless, city("la", "Los Angeles", 4)])).toBe("Polymarket");
  });
});

/* ═══ 3. One list: the header describes what the map draws ════════════════ */

describe("#7423 · a search narrows the header with the map", () => {
  test("the returned list IS the filtered list the caller renders", () => {
    const { cities } = temperatureMapHeader(THREE, "seat");
    expect(cities.map(c => c.id)).toEqual(["seattle"]);
    expect(filterCitiesByName(THREE, "seat")).toEqual(cities);
  });

  test("filtering to one city reads '1 city' and '1 market', not '3'", () => {
    const { title, meta, scope } = temperatureMapHeader(THREE, "Seattle");
    expect(title).toBe("1 city. Tomorrow's high, as a probability distribution.");
    expect(meta).toBe("Polymarket · 1 market");
    expect(scope).toBe("1 of 3 cities");
  });

  test("the venue mark narrows too — filtering to a Kalshi city drops Polymarket", () => {
    const mixed = [
      city("nyc", "New York", 3, ["polymarket"]),
      city("la", "Los Angeles", 4, ["kalshi"]),
    ];
    expect(temperatureMapHeader(mixed, "Angeles").meta).toBe("Kalshi · 1 market");
  });

  test("a blank or whitespace query is not a filter and shows no scope chip", () => {
    for (const q of ["", "   ", "\t"]) {
      const { cities, scope } = temperatureMapHeader(THREE, q);
      expect(cities).toHaveLength(3);
      expect(scope).toBeNull();
    }
  });

  test("an unfiltered list is passed through BY REFERENCE, not copied", () => {
    // `toBe`, not `toEqual`, and it is guarding a cost rather than a value.
    // `MapCanvas` memoises a 40-iteration pin-collision solver on `[cities]`
    // and this card re-renders on every `onHover`; a defensive copy here hands
    // that memo a fresh array on every mouse move. A future "tidy-up" that
    // writes `[...allCities]` must fail here.
    expect(filterCitiesByName(THREE, "")).toBe(THREE);
    expect(temperatureMapHeader(THREE, "").cities).toBe(THREE);
  });

  test("a query matching nothing says so rather than falling back to everything", () => {
    const { cities, title, meta, scope } = temperatureMapHeader(THREE, "Reykjavik");
    expect(cities).toEqual([]);
    expect(title).toBe("0 cities. Tomorrow's high, as a probability distribution.");
    expect(meta).toBe("0 markets");
    expect(scope).toBe("0 of 3 cities");
  });

  test("matching is case- and whitespace-insensitive, as the box always was", () => {
    expect(temperatureMapHeader(THREE, "  NEW yORk ").cities.map(c => c.id)).toEqual(["nyc"]);
  });
});

describe("#7423 · pluralize is English, not a template", () => {
  test("one is singular, everything else is not", () => {
    expect(pluralize(1, "city", "cities")).toBe("1 city");
    expect(pluralize(0, "city", "cities")).toBe("0 cities");
    expect(pluralize(2, "market", "markets")).toBe("2 markets");
  });
});

/* ═══ 4. The SHIPPED component, not just the helper ═══════════════════════ */

describe("#7423 · TemperatureMap renders the derived mark", () => {
  afterEach(() => {
    swrPayload = undefined;
    swrError = undefined;
  });

  test("the served payload's own numbers reach the screen", () => {
    swrPayload = THREE;
    const seen = visibleText(renderToStaticMarkup(<TemperatureMap />));

    expect(seen).toContain("3 cities. Tomorrow's high, as a probability distribution.");
    expect(seen).toContain("Polymarket · 3 markets");
    // The three strings the card shipped with, none of which was a reading:
    expect(seen).not.toContain("24 markets");
    expect(seen).not.toContain("336");
    expect(seen).not.toContain("Polymarket & Kalshi");
  });

  test("the header count and the map footer's count agree on one screen", () => {
    swrPayload = TWO;
    const seen = visibleText(renderToStaticMarkup(<TemperatureMap />));
    expect(seen).toContain("2 cities. Tomorrow's high");
    expect(seen).toContain("2 cities shown");
  });

  test("a one-city payload reads as English in BOTH counts on that screen", () => {
    // The card can reach 1 by search as well as by payload, and the footer's
    // "1 cities shown" was already reachable that way before #7423 put a
    // second count above it. This is the shape that pins both.
    swrPayload = [city("nyc", "New York", 3)];
    const seen = visibleText(renderToStaticMarkup(<TemperatureMap />));
    expect(seen).toContain("1 city. Tomorrow's high");
    expect(seen).toContain("Polymarket · 1 market");
    expect(seen).toContain("1 city shown");
    expect(seen).not.toContain("1 cities");
    expect(seen).not.toContain("1 markets");
  });

  test("a card with no payload yet claims no venue and no count", () => {
    // Skeleton, error and empty all used to assert "Polymarket & Kalshi" over
    // nothing at all. A state with no payload has no venues to name.
    for (const [payload, err] of [
      [undefined, undefined],
      [undefined, new Error("boom")],
      [[], undefined],
    ] as const) {
      swrPayload = payload;
      swrError = err;
      const seen = visibleText(renderToStaticMarkup(<TemperatureMap />));
      expect(seen).not.toContain("Kalshi");
      expect(seen).not.toContain("Polymarket");
      // Not a bare "markets" ban: the empty state's own copy legitimately reads
      // "No live temperature markets right now". What may not appear is a
      // COUNT of them, which is the claim these states cannot substantiate.
      expect(seen).not.toMatch(/\d+ markets?\b/);
      expect(seen).toContain("Tomorrow's high, as a probability distribution.");
    }
  });
});
