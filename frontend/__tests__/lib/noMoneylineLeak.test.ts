// L2-48: the no-odds thesis is categorical — the product shows probabilities
// ("60% vs 40%"), NEVER American moneyline ("-150/+130"). Alex confirmed a live
// +9900 leak on /futures/411 was a bug. This guard fails if a moneyline formatter
// or an american_odds render is reintroduced on the answer surfaces.

import { readFileSync } from "fs";
import { join } from "path";

const read = (rel: string) =>
  readFileSync(join(__dirname, "../../", rel), "utf8")
    // strip comments so our own "removed …" notes don't trip the assertions
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");

describe("no American-moneyline leak (L2-48)", () => {
  test("api.ts exports no moneyline formatter", () => {
    const api = read("lib/api.ts");
    expect(api).not.toContain("formatAmericanOdds");
    expect(api).not.toContain("formatMoneyline");
  });

  const SURFACES = [
    "app/futures/[id]/page.tsx",
    "components/RelatedFutures.tsx",
  ];

  test("ThresholdGrid (ladder rail) renders no source-provider name (D1)", () => {
    // L2-51: the ladder cells used to print "Polymarket"/"Kalshi" per outcome.
    const src = read("components/ThresholdGrid.tsx");
    expect(src).not.toContain('"Polymarket"');
    expect(src).not.toContain('"Kalshi"');
  });

  for (const rel of SURFACES) {
    test(`${rel} calls no odds formatter`, () => {
      const src = read(rel);
      // The reliable render signal: a call to any American-odds formatter.
      // (Data-passing like `american_odds: o.american_odds` to a child that
      // doesn't render it — e.g. ProgressionTable — is fine and stays.)
      expect(src).not.toMatch(/format(American)?Odds\s*\(/);
      expect(src).not.toMatch(/formatMoneyline\s*\(/);
      // no local inline moneyline formatter (odds > 0 ? "+..." pattern on odds)
      expect(src).not.toMatch(/odds\s*>\s*0\s*\?\s*[`"]\+/);
    });
  }
});
