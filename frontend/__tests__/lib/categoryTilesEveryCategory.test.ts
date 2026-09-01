/**
 * D9 (Alex, 2026-08-30): "every category with open markets gets a tile, ordered
 * by size; motorsport naming fixed."
 *
 * The class of bug this guards: the tile list used to be a HARDCODED array
 * (`SPORT_CATEGORIES` filtered by a second hardcoded allowlist in the page), so
 * a category was browsable only if someone had remembered to add it. Measured
 * against production on 2026-08-30, 21 of 48 categories carrying open markets
 * had no tile — 14,873 items, 31.6% of the site, including `table_tennis` at
 * 13,503 open markets, the largest category we have.
 *
 * These assert the two properties that make that unrepeatable — coverage is
 * driven by the DATA, and an unknown key still renders — plus the ordering and
 * the motorsport spelling the same ruling names.
 */
import { buildTiles } from "@/lib/categoryTiles";
import { SPORT_CATEGORIES, getNameForCategory } from "@/lib/sportCategories";

/**
 * The shape measured on production 2026-08-30 (`GET /api/feed/tag-counts`),
 * trimmed to the cases that carry the ruling. `table_tennis`, `cycling`,
 * `handball` and `watchmaking` are all real keys that had NO tile that day.
 */
const PROD_SHAPED_COUNTS = {
  table_tennis: { events: 0, futures: 13503 },
  soccer: { events: 837, futures: 8122 },
  politics: { events: 0, futures: 6579 },
  motorsports: { events: 0, futures: 145 },
  cycling: { events: 0, futures: 17 },
  handball: { events: 0, futures: 16 },
  watchmaking: { events: 0, futures: 2 },
  poker: { events: 0, futures: 0 },
};

describe("D9 — every category with open markets gets a tile", () => {
  it("renders a tile for EVERY category carrying open markets", () => {
    const keys = buildTiles(PROD_SHAPED_COUNTS).map((t) => t.key);
    for (const [key, c] of Object.entries(PROD_SHAPED_COUNTS)) {
      if (c.events + c.futures > 0) {
        expect(keys).toContain(key);
      }
    }
  });

  it("renders keys that are absent from the hardcoded SPORT_CATEGORIES list", () => {
    // The regression that motivated the ruling. `table_tennis` is the largest
    // category on the site and is NOT in SPORT_CATEGORIES; if tile coverage
    // ever goes back to being driven by that array, this fails.
    const known = new Set(SPORT_CATEGORIES.map((c) => c.key));
    expect(known.has("table_tennis")).toBe(false);

    const tile = buildTiles(PROD_SHAPED_COUNTS).find(
      (t) => t.key === "table_tennis",
    );
    expect(tile).toBeDefined();
    // And it degrades gracefully rather than rendering a raw key.
    expect(tile!.name).toBe("Table Tennis");
    expect(tile!.emoji).toBeTruthy();
  });

  it("orders tiles by size, largest first", () => {
    const totals = buildTiles(PROD_SHAPED_COUNTS).map((t) => t.total);
    expect(totals).toEqual([...totals].sort((a, b) => b - a));
    expect(buildTiles(PROD_SHAPED_COUNTS)[0].key).toBe("table_tennis");
  });

  it("drops categories with nothing behind them", () => {
    // `poker` rendered a tile with zero items on production the same day.
    const keys = buildTiles(PROD_SHAPED_COUNTS).map((t) => t.key);
    expect(keys).not.toContain("poker");
  });

  it("is stable for equal sizes rather than inheriting key order", () => {
    const a = buildTiles({ zulu: { events: 0, futures: 5 }, alpha: { events: 0, futures: 5 } });
    const b = buildTiles({ alpha: { events: 0, futures: 5 }, zulu: { events: 0, futures: 5 } });
    expect(a.map((t) => t.key)).toEqual(b.map((t) => t.key));
  });

  it("handles a missing payload without throwing", () => {
    expect(buildTiles(undefined)).toEqual([]);
  });
});

describe("D9 — motorsport naming", () => {
  it("keys the category on the PLURAL llm_sport_category spelling", () => {
    // The tile links to /categories/<key>, which becomes the `sport:<key>` feed
    // tag. Only `sport:motorsports` is ever written, so a singular key is a
    // permanently empty page.
    const keys = SPORT_CATEGORIES.map((c) => c.key);
    expect(keys).toContain("motorsports");
    expect(keys).not.toContain("motorsport");
  });

  it("keeps the SINGULAR spelling for the sport-key prefix", () => {
    // The two spellings are not interchangeable: `motorsport_f1` is a sport
    // key, `motorsports` is a category. Collapsing both would break prefix
    // matching.
    const cat = SPORT_CATEGORIES.find((c) => c.key === "motorsports");
    expect(cat!.prefixes).toContain("motorsport_");
  });

  it("resolves a display name for the plural key", () => {
    expect(getNameForCategory("motorsports")).toBe("Motorsport");
  });

  it("gives the motorsports tile its futures count", () => {
    // Before the fix the payload carried two sibling keys for one sport and the
    // tile read the one that could only ever hold events.
    const tile = buildTiles(PROD_SHAPED_COUNTS).find(
      (t) => t.key === "motorsports",
    );
    expect(tile!.futures).toBe(145);
  });
});
