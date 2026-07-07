// #993 L2-44: D1 compliance guard — the plain search/market cards must NEVER
// render a source-provider name ("Kalshi"/"Polymarket"/"Sportsbooks"). D1 is
// blend-only: users see one clean number, source plumbing hidden. This is a
// source-inspection guard (like the backend _format_market_detail guard) rather
// than an RTL render — FuturesCard's deps (Link/framer-motion) make render tests
// brittle, and the invariant we care about is "the provider-name code path is
// gone", which the source proves directly and cheaply.

import { readFileSync } from "fs";
import { join } from "path";

const src = readFileSync(
  join(__dirname, "../../components/FuturesCard.tsx"),
  "utf8",
);

// Strip line/block comments so our own explanatory comment (which names Kalshi)
// doesn't trip the assertion — we only care about rendered/executed code.
const code = src
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

describe("FuturesCard D1 (blend-only, no source names)", () => {
  test("has no formatSourceName helper", () => {
    expect(code).not.toContain("formatSourceName");
  });

  test("does not render the provider-name field market.source", () => {
    // The blend COUNT (market.source_count) is source-agnostic and allowed;
    // the bare provider string (market.source) must not be rendered.
    expect(code).not.toMatch(/market\.source(?!_count)/);
  });

  test("does not hardcode a provider name in rendered code", () => {
    for (const name of ["Kalshi", "Polymarket", "Sportsbooks"]) {
      expect(code).not.toContain(name);
    }
  });

  test("still shows the source-agnostic blend count", () => {
    // We remove the NAME, not the blend signal — "N sources" stays.
    expect(code).toContain("source_count");
    expect(code).toContain("sources");
  });
});
