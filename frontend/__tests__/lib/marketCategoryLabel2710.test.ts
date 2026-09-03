// UX-P276 / #2710 — the category chip reads as English, never as the column value.
//
// Alex, mobile /sports 2026-09-02 15:40: "sport line reads 'TENNIS game_prop'
// (raw enum)".
//
// THE VOCABULARY BELOW IS MEASURED, NOT IMAGINED. `SELECT category, count(*)
// FROM futures_markets WHERE status = 'open' GROUP BY category` on 2026-09-03
// returned exactly these 15 values over 45,461 rows, `truncated: false` — so
// the coverage assertion is over the whole population rather than a sample.
//
// The load-bearing test in this file is NOT the two-entry exception map; it is
// `an unknown category still cannot reach the reader raw`. A map alone is
// correct for today's 15 and silently wrong for the 16th, which is exactly how
// `game_prop` reached a chip in the first place.

import { marketCategoryLabel } from "@/lib/marketCategoryLabel";

/** Every open-market category, with its measured row count for provenance. */
const MEASURED_VOCABULARY: ReadonlyArray<readonly [string, number]> = [
  ["championship", 19716],
  ["game_prop", 16208],
  ["politics", 5428],
  ["economics", 1665],
  ["entertainment", 1119],
  ["tech", 453],
  ["weather", 345],
  ["other", 273],
  ["geopolitics", 226],
  ["health", 10],
  ["placement", 9],
  ["crypto", 3],
  ["make_cut", 3],
  ["culture", 2],
  ["legal", 1],
];

/** What a raw column value looks like: snake_case, or bare lowercase. */
function looksRaw(label: string): boolean {
  return label.includes("_") || /^[a-z]/.test(label);
}

describe("marketCategoryLabel — no category reaches the reader raw", () => {
  it.each(MEASURED_VOCABULARY)(
    "%s (%i open markets) renders as English",
    (category) => {
      const label = marketCategoryLabel(category);
      expect(label).not.toBeNull();
      expect(looksRaw(label as string)).toBe(false);
    },
  );

  it("covers the whole measured vocabulary, so the count is exact not a sample", () => {
    expect(MEASURED_VOCABULARY).toHaveLength(15);
    const total = MEASURED_VOCABULARY.reduce((s, [, n]) => s + n, 0);
    expect(total).toBe(45461);
  });

  it("names the two that title-casing leaves as jargon", () => {
    expect(marketCategoryLabel("game_prop")).toBe("Game Props");
    expect(marketCategoryLabel("make_cut")).toBe("Makes the Cut");
  });

  it("an UNKNOWN category still cannot reach the reader raw — the fallback is the ship", () => {
    // Not in the exception map and not in today's vocabulary. This is the 16th
    // value, whenever it arrives.
    for (const invented of ["first_scorer", "series_price", "double_double"]) {
      const label = marketCategoryLabel(invented);
      expect(label).not.toBeNull();
      expect(looksRaw(label as string)).toBe(false);
      expect(label).not.toBe(invented);
    }
  });

  it("preserves acronyms, because it delegates to the caser that owns them", () => {
    // UX-P050 / L2-174 — "nba mvp" must not become "Nba Mvp".
    expect(marketCategoryLabel("nba_mvp")).toBe("NBA MVP");
  });

  it("is case- and whitespace-tolerant on the exception keys", () => {
    expect(marketCategoryLabel("  GAME_PROP  ")).toBe("Game Props");
  });
});

describe("marketCategoryLabel — returns null so the chip can gate on it", () => {
  // The chip renders `{categoryLabel && <span>…}`. A "" here would be falsy and
  // work by accident; a raw-value fallback would render the bug. Both are
  // pinned so a later "simplification" cannot reintroduce either.
  it.each([null, undefined, "", "   "])("%p renders no chip at all", (input) => {
    expect(marketCategoryLabel(input as string | null | undefined)).toBeNull();
  });

  it("never falls back to the raw value to fill a blank", () => {
    // Input the caser cannot turn into words: it must yield null, NOT "___".
    expect(marketCategoryLabel("___")).toBeNull();
  });

  it("CONTROL: a non-string is refused rather than thrown on", () => {
    expect(marketCategoryLabel(42 as unknown as string)).toBeNull();
  });
});
