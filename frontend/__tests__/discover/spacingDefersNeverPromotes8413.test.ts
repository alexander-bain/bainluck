import * as fs from "fs";
import * as path from "path";
import { SPORT_CATEGORIES, spaceBySport } from "@/lib/discover/spacedOrder";

/**
 * #8413 — the web's first ten were not the ten the feed chose.
 *
 * The fixture is production's served order for the web's exact request
 * (`/api/feed?limit=20&event_pct=0.15`, 2026-09-24 17:26Z), reduced to
 * name + the category `getItemCategory` derives. The old interleave, run over
 * it, reproduced the rendered page card for card: Cardinals, Kings (served
 * #12), China, Mets, NASCAR (#17), Iran, Astros, Korn Ferry (#19), Xi, World
 * Series — with the served #2 White Sox pushed to 13.
 */
type Card = [name: string, category: string];

const SERVED_20260924: Card[] = [
  ["Cardinals@Pirates LIVE", "baseball"],
  ["White Sox@Royals starting soon", "baseball"],
  ["Mets@Rangers", "baseball"],
  ["MLB World Series Winner", "baseball"],
  ["China invade Taiwan", "politics"],
  ["US invade Iran", "politics"],
  ["Xi out before 2027", "geopolitics"],
  ["Brazil Presidential Election", "politics"],
  ["Awards Season", "entertainment"],
  ["US x Iran ceasefire", "geopolitics"],
  ["Astros@Mariners final", "baseball"],
  ["Kings@Ducks final", "icehockey"],
  ["Fed & Rates", "economics"],
  ["IPOs", "economics"],
  ["French Presidential Election", "politics"],
  ["Where will it rain", "weather"],
  ["NASCAR Cup Champion", "motorsports"],
  ["Worlds 2026", "esports"],
  ["Compliance Solutions Championship", "golf"],
  ["FedEx Open de France", "golf"],
];

const cat = (c: Card) => c[1];
const names = (cards: Card[]) => cards.map((c) => c[0]);
const isSport = (c: Card) => SPORT_CATEGORIES.has(c[1]);

/** The page spaces twice (before grouping, and after personalization). */
const asRendered = (cards: Card[]) => spaceBySport(spaceBySport(cards, cat), cat);

describe("#8413 — the first ten on the web are the ten the feed chose", () => {
  it("renders the served ten, spaced, on the 2026-09-24 production payload", () => {
    expect(names(asRendered(SERVED_20260924).slice(0, 10))).toEqual([
      "Cardinals@Pirates LIVE",
      "China invade Taiwan",
      "White Sox@Royals starting soon",
      "US invade Iran",
      "Mets@Rangers",
      "Xi out before 2027",
      "MLB World Series Winner",
      "Brazil Presidential Election",
      "Awards Season",
      "US x Iran ceasefire",
    ]);
  });

  it("keeps the three cards the old pass pulled onto page one below the fold of ten", () => {
    const firstTen = names(asRendered(SERVED_20260924).slice(0, 10));
    for (const pulled of ["Kings@Ducks final", "NASCAR Cup Champion", "Compliance Solutions Championship"]) {
      expect(firstTen).not.toContain(pulled);
    }
  });

  it("still spaces page one: no two same-sport cards side by side, sports runs within the cap", () => {
    // Only the tail (two golf cards with nothing left to separate them) may pair.
    const out = asRendered(SERVED_20260924).slice(0, 10);
    let run = 0;
    for (let i = 0; i < out.length; i++) {
      if (i > 0 && isSport(out[i])) expect(cat(out[i])).not.toBe(cat(out[i - 1]));
      run = isSport(out[i]) ? run + 1 : 0;
      expect(run).toBeLessThanOrEqual(2);
    }
  });
});

describe("#8413 — spacing defers, it never promotes (randomized)", () => {
  const CATS = ["baseball", "baseball", "baseball", "icehockey", "golf", "politics", "economics", "tech"];

  // Deterministic LCG so a failure is reproducible.
  function rng(seed: number) {
    let s = seed;
    return () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296;
  }

  function makeList(seed: number): Card[] {
    const r = rng(seed);
    const n = 3 + Math.floor(r() * 25);
    return Array.from({ length: n }, (_, i) => [`c${i}`, CATS[Math.floor(r() * CATS.length)]] as Card);
  }

  it("every card placed ahead of a higher-ranked one got there only because the rules held that card back", () => {
    for (let seed = 1; seed <= 400; seed++) {
      const input = makeList(seed);
      const out = spaceBySport(input, cat);
      expect(out).toHaveLength(input.length);
      expect(new Set(out)).toEqual(new Set(input));

      const maxRun = input.filter((c) => !isSport(c)).length >= 4 ? 2 : 3;
      const allows = (c: Card, last: string, run: number) =>
        !isSport(c) || (run < maxRun && cat(c) !== last);

      const remaining = [...input];
      let last = "";
      let run = 0;
      for (const placed of out) {
        const idx = remaining.indexOf(placed);
        const passedOver = remaining.slice(0, idx);
        if (allows(placed, last, run)) {
          // Chosen under the rules: everything ranked above it must break them.
          for (const skipped of passedOver) expect(allows(skipped, last, run)).toBe(false);
        } else {
          // Nothing satisfied the rules: nothing above it may be allowed either.
          for (const other of remaining) expect(allows(other, last, run)).toBe(false);
        }
        remaining.splice(idx, 1);
        if (isSport(placed)) {
          last = cat(placed);
          run++;
        } else {
          last = "";
          run = 0;
        }
      }
    }
  });

  it("is idempotent, so the page's second pass cannot move what the first placed", () => {
    for (let seed = 1; seed <= 400; seed++) {
      const once = spaceBySport(makeList(seed), cat);
      expect(spaceBySport(once, cat)).toEqual(once);
    }
  });
});

describe("#8413 — the page uses the shared spacing at both sites", () => {
  const page = fs.readFileSync(path.join(__dirname, "../../app/discover/page.tsx"), "utf8");

  it("defines no interleave of its own", () => {
    expect(page).not.toMatch(/function interleave(Grouped)?\(/);
  });

  it("spaces the raw list and the grouped list through spaceBySport", () => {
    expect(page).toContain("groupRelatedMarkets(spaceBySport(cooldownSafe, getItemCategory))");
    expect(page).toMatch(/return spaceBySport\(\s*applyLocalPersonalization\(/);
    expect(page).toMatch(/\}\),\s*getGroupedCategory,\s*\);/);
  });
});
