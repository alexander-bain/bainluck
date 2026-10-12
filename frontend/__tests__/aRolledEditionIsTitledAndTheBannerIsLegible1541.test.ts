// #1541 — two reader repairs on the futures detail page.
//
// (1) `/futures/7` read "US Open Winner" while every quote was for the 2027 US
// Open (provider commence 2027-06-17); the backend now serves `edition_year`
// from the provider's own verified event and the hero titles the board with it.
// (2) The withdrawn sentence rendered `text-amber-400` on a 10% amber tint —
// ~1.43:1 at 390px on production. It is the whole message, so it reads in
// primary text.

import { readFileSync } from "fs";
import { join } from "path";

import { editionTitle } from "@/lib/futuresDetailDisplay";

const PAGE = join(__dirname, "..", "app", "futures", "[id]", "page.tsx");

describe("#1541 editionTitle", () => {
  it("titles a bare rolled board with its provider edition", () => {
    expect(editionTitle("US Open Winner", "2027")).toBe("2027 US Open Winner");
  });

  it("leaves the name untouched when no edition is served", () => {
    expect(editionTitle("US Open Winner", null)).toBe("US Open Winner");
    expect(editionTitle("US Open Winner", undefined)).toBe("US Open Winner");
    expect(editionTitle("US Open Winner", "")).toBe("US Open Winner");
  });

  it("never gives a name that states a year a second one", () => {
    expect(editionTitle("2027 The Masters Champion", "2027")).toBe("2027 The Masters Champion");
    expect(editionTitle("NBA Finals 2027 Winner", "2027")).toBe("NBA Finals 2027 Winner");
  });

  it("refuses a year that is not a year", () => {
    expect(editionTitle("US Open Winner", "27")).toBe("US Open Winner");
    expect(editionTitle("US Open Winner", "next")).toBe("US Open Winner");
  });
});

describe("#1541 the page wires both repairs", () => {
  const source = readFileSync(PAGE, "utf8");

  it("titles the hero through editionTitle with the served year", () => {
    expect(source).toContain("name={editionTitle(market.name, market.edition_year)}");
  });

  it("renders the settlement banner in primary text on the warning token", () => {
    const at = source.indexOf("{settlementBanner}");
    expect(at).toBeGreaterThan(0);
    const div = source.slice(source.lastIndexOf("<div", at), at);
    expect(div).toContain("text-text-primary");
    expect(div).toContain("bg-accent-warning/10");
    expect(div).not.toMatch(/text-amber-\d+/);
  });
});
