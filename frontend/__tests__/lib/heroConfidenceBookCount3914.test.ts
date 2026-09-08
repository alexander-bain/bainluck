import fs from "fs";
import path from "path";
import {
  PROBABILITY_SOURCE_KEYS,
  confidenceFromSources,
  countProbabilitySources,
} from "@/lib/confidence";

// #3914 — THE HERO'S CONFIDENCE BARS COUNT READINGS, NOT KEYS.
//
// The specimen, read off production `/api/events/15306813` (Ben Shelton v
// Carlos Alcaraz, US Open, scheduled) at 2026-09-08 08:23Z:
//
//     betting            = 0.2306
//     polymarket         = 0.2150
//     betting_book_count = 11.0      <- how many sportsbooks, not who wins
//
// `betting_book_count` rides in the same JSONB bag as the readings and is
// serialised onto the wire in the same `{value, display_name, type, color}`
// shape, so a counter that counts KEYS counts it. `SOURCE_SATURATION` is 3, so
// it does not nudge the score — it saturates the sources component and pushes
// the hero across `CONFIDENCE_TIER_HIGH` (0.70): the page printed
// "high / 3 bars" over two opinions.
//
// The fix mirrors the aggregator's own filter (`effective_source_weights`
// skips any key not in `SOURCE_WEIGHTS`), so the blend and the bars count the
// same set. The third test below is the arm that keeps that true: it reads
// `SOURCE_WEIGHTS` out of the Python rather than trusting a comment.

/** The hero's exact inputs: sources + line movement, no volume, no agreement. */
const HERO_MOVEMENT = { hasMovement: true } as const;

const SPECIMEN = {
  betting: { value: 0.2306, display_name: "Betting Odds", type: "market" },
  polymarket: { value: 0.215, display_name: "Polymarket", type: "market" },
  betting_book_count: { value: 11.0, display_name: "betting_book_count", type: "model" },
};

describe("#3914 hero confidence counts probability readings, not bag keys", () => {
  it("counts the two readings on the production specimen and drops the book count", () => {
    expect(countProbabilitySources(SPECIMEN)).toBe(2);
    // The negative control: this is what the page used to pass, and it is the
    // reason the assertion below is worth making at all.
    expect(Object.keys(SPECIMEN).length).toBe(3);
  });

  it("renders the two-source tier, not the saturated one (acceptance 1 + 2)", () => {
    const fixed = confidenceFromSources({
      sourceCount: countProbabilitySources(SPECIMEN),
      ...HERO_MOVEMENT,
    });
    expect(fixed).toEqual({ score: 0.6471, tier: "moderate", bars: 2 });

    // What the same payload produced before the fix — pinned so a revert to
    // key-counting fails here loudly instead of quietly re-inflating a tier.
    const keyCounted = confidenceFromSources({
      sourceCount: Object.keys(SPECIMEN).length,
      ...HERO_MOVEMENT,
    });
    expect(keyCounted).toEqual({ score: 0.8235, tier: "high", bars: 3 });
  });

  it("ignores a known source with no reading, and survives an empty bag", () => {
    // An ingest that wrote the entry before the price landed is not evidence.
    expect(
      countProbabilitySources({
        betting: { value: 0.5 },
        kalshi: { value: null },
        polymarket: undefined,
      })
    ).toBe(1);
    expect(countProbabilitySources({})).toBe(0);
    expect(countProbabilitySources(null)).toBe(0);
    expect(countProbabilitySources(undefined)).toBe(0);
    // A bag of nothing but non-readings publishes no signal at all rather than
    // one bar of imaginary confidence.
    expect(
      confidenceFromSources({
        sourceCount: countProbabilitySources({ betting_book_count: { value: 11.0 } }),
        ...HERO_MOVEMENT,
      })
    ).toBeNull();
  });

  it("holds the allowlist against the backend's SOURCE_WEIGHTS", () => {
    // Read the Python, don't paraphrase it. A source added to the aggregator
    // and not mirrored here is undercounted — the safe direction, but still a
    // drift, and this is where it is caught.
    const aggregation = fs.readFileSync(
      path.join(__dirname, "../../../backend/app/utils/aggregation.py"),
      "utf8"
    );
    const block = aggregation.match(
      /^SOURCE_WEIGHTS: dict\[str, float\] = \{\n([\s\S]*?)^\}/m
    );
    expect(block).not.toBeNull();
    const backendKeys = [...(block as RegExpMatchArray)[1].matchAll(/^\s*"([a-z_]+)":/gm)].map(
      (m) => m[1]
    );
    // Guard the instrument before trusting it: a regex that matched an empty
    // block would make the comparison below say nothing.
    expect(backendKeys.length).toBeGreaterThanOrEqual(6);
    expect(backendKeys).toContain("betting");
    expect(new Set(backendKeys)).toEqual(new Set(PROBABILITY_SOURCE_KEYS));
    // And the thing that started all this is NOT one of them, in either file.
    expect(backendKeys).not.toContain("betting_book_count");
  });
});

describe("#3914 the event hero is wired to the reading counter", () => {
  it("passes countProbabilitySources and no longer counts bag keys", () => {
    const page = fs.readFileSync(
      path.join(__dirname, "../../app/events/[id]/page.tsx"),
      "utf8"
    );
    expect(page).toContain("sourceCount: countProbabilitySources(event.win_probability_sources)");
    expect(page).not.toContain("Object.keys(event.win_probability_sources)");
  });
});
