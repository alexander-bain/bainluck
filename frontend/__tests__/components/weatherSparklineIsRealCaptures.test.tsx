// ux/1069 (#2960) — the /weather sparkline draws real captures or nothing.
//
// 🔴 WHAT WAS SHIPPED. `sparkFrom(seed, end)` in `components/weather/data.ts`
// drew a 14-point line in which exactly ONE point — the last — was the real
// price. The other thirteen came from a seeded LCG walking a noise path from a
// random-offset start toward it. The hero seeded it on `idx` (the card's
// position in the 5.5s rotation) and each wild card on `i * 137 + 42` (its
// position in the grid), so the "price history" of a market was a function of
// where the card happened to sit on the page. It rendered in the same ink a
// real history would, and a reader had no way to tell.
//
// 🔴 WHY THE ASSERTIONS ARE PAIRED ARMS, NOT A SNAPSHOT. "There is a path with
// these coordinates" passes on the fabricated line too — the generator ended
// on the real price, so its last point was always right. The only assertions
// that can separate a real line from a manufactured one are relational:
//
//   1. same `prob`, DIFFERENT history  → DIFFERENT path. The old line was a
//      function of (seed, prob) and would be byte-identical across this pair.
//   2. same history, DIFFERENT `prob`  → SAME path. The old line was anchored
//      on `prob` and would differ.
//   3. no history                      → NO path, and no sized empty wrapper.
//   4. two captures                    → NO path. A straight segment reads as
//      a trend it has not earned; `MIN_SPARK_POINTS` is 3.
//
// 🔴 WHY IT GOES THROUGH THE RENDERED COMPONENTS AND BOTH OF THEM. `realSpark`
// returning null proves nothing if a surface still calls the generator, and
// TWO surfaces drew one: `WeatherHero` (the featured card) and `WildCards`
// (the grid). A lib-only test would have passed with either call site
// untouched.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import WeatherHero from "@/components/weather/WeatherHero";
import WildCards from "@/components/weather/WildCards";
import { MIN_SPARK_POINTS, realSpark } from "@/components/weather/data";

// SWR is the only thing between these components and the network. Each test
// installs the payload it wants; the components are otherwise pure at first
// render (their `useEffect` rotation never fires under static rendering).
let swrPayload: unknown = undefined;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

jest.mock("@/lib/weatherApi", () => ({
  fetchWeatherFeatured: () => Promise.resolve([]),
  fetchWildCards: () => Promise.resolve([]),
}));

/** Every `<path d="...">` in the markup, in order. */
function paths(markup: string): string[] {
  return Array.from(markup.matchAll(/<path[^>]*\sd="([^"]+)"/g)).map((m) => m[1]);
}

const HERO_CARD = {
  q: "Where will it rain on Sep 5, 2026?",
  prob: 61,
  src: "polymarket" as const,
  tag: "Daily rain",
  closes: "Sat, Sep 5",
  leader: "Minneapolis",
};

const WILD_CARD = {
  q: "Major volcano eruption in 2026?",
  prob: 61,
  src: "polymarket" as const,
  tag: "Wild card",
  leader: "At least 2",
};

const RISING = [40, 44, 51, 58, 61];
const FALLING = [82, 76, 70, 64, 61];

function renderHero(card: Record<string, unknown>): string {
  swrPayload = [card];
  return renderToStaticMarkup(<WeatherHero />);
}

function renderWild(card: Record<string, unknown>): string {
  swrPayload = [card];
  return renderToStaticMarkup(<WildCards />);
}

describe.each([
  ["WeatherHero", renderHero, HERO_CARD],
  ["WildCards", renderWild, WILD_CARD],
])("%s sparkline (ux/1069, #2960)", (_name, render, base) => {
  test("the line is a function of the captures, not of the printed number", () => {
    const rising = paths(render({ ...base, history: RISING }));
    const falling = paths(render({ ...base, history: FALLING }));

    // Both arms print the same 61% and both drew a line, so the ONLY thing
    // that can have moved the geometry is the capture series.
    expect(rising.length).toBeGreaterThan(0);
    expect(falling.length).toBe(rising.length);
    expect(falling).not.toEqual(rising);
  });

  test("the printed number does not shape the line", () => {
    // A card whose current price differs but whose captures are identical must
    // draw the identical path. The fabricated line anchored its last point on
    // `prob`, so it could not have satisfied this.
    const a = paths(render({ ...base, prob: 61, history: RISING }));
    const b = paths(render({ ...base, prob: 12, history: RISING }));
    expect(a.length).toBeGreaterThan(0);
    expect(b).toEqual(a);
  });

  test("no captures ⇒ no line and no empty chart slot", () => {
    expect(paths(render({ ...base, history: [] }))).toEqual([]);
    // A payload from the Redis cache built before the field existed.
    expect(paths(render({ ...base }))).toEqual([]);
    // The card still renders — this is a missing line, not a missing card.
    expect(render({ ...base })).toContain("61");
    // ...and the sparkline's sized wrapper is gone with it. An empty 112x48
    // box where a chart belongs is a placeholder by another name.
    expect(render({ ...base })).not.toContain("w-28 h-12");
  });

  test("two captures are not a trend", () => {
    expect(MIN_SPARK_POINTS).toBe(3);
    expect(paths(render({ ...base, history: [40, 61] }))).toEqual([]);
    // Survivor: exactly MIN_SPARK_POINTS still draws.
    expect(paths(render({ ...base, history: [40, 50, 61] })).length).toBeGreaterThan(0);
  });
});

describe("realSpark (ux/1069, #2960)", () => {
  test("returns null rather than a short array, so callers must branch", () => {
    expect(realSpark(undefined)).toBeNull();
    expect(realSpark(null)).toBeNull();
    expect(realSpark([])).toBeNull();
    expect(realSpark([61])).toBeNull();
    expect(realSpark([40, 61])).toBeNull();
    expect(realSpark([40, 50, 61])).toEqual([40, 50, 61]);
  });

  test("drops non-finite readings instead of charting them as zero", () => {
    expect(realSpark([40, NaN, 50, 61])).toEqual([40, 50, 61]);
    // Dropping can take a series below the floor, and then there is no line.
    expect(realSpark([40, NaN, Infinity, 61])).toBeNull();
  });
});

describe("nothing on these surfaces manufactures a number (ux/1069, #2960)", () => {
  // 🔴 SCOPE. `components/weather/**` and `components/skeletons/**`, not the
  // whole tree. A tree-wide grep would own every lane's files and go red on
  // someone else's commit, and the three surviving `Math.random` call sites in
  // the app are session ids and idempotency keys, which are supposed to be
  // random. The one deliberate exception — the Higher/Lower game's threshold
  // ("are the odds higher or lower than 42%?") — is a QUIZ LINE, explicitly
  // framed as the game's own question and revealed against the real number,
  // never presented as a market price. It lives outside both directories.
  //
  // The skeletons are in scope because their grey bars are a shape even when
  // they are not a number: the weather temperature skeleton drew an 11-bar
  // sinusoid standing in for a real probability distribution, which is a
  // distribution rendered before the data arrives.
  const DIRS = ["components/weather", "components/skeletons"];

  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const fs = require("fs");
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const path = require("path");

  function filesUnder(dir: string): string[] {
    const root = path.join(__dirname, "../../", dir);
    return fs
      .readdirSync(root, { withFileTypes: true })
      .filter((e: { isFile: () => boolean; name: string }) => e.isFile())
      .map((e: { name: string }) => path.join(root, e.name));
  }

  test.each(DIRS)("%s draws no generated number or shape", (dir) => {
    const offenders = filesUnder(dir).filter((file: string) => {
      const src: string = fs.readFileSync(file, "utf8");
      // The tombstone comment in data.ts names the dead function; only a CALL
      // or a definition counts, and neither survives these patterns.
      return /Math\.(random|sin|cos)\s*\(|mulberry|hashString\s*\(/.test(src);
    });
    expect(offenders.map((f: string) => path.basename(f))).toEqual([]);
  });
});

describe("the generator is gone (ux/1069, #2960)", () => {
  // The point of the fix is that no seeded stream can reach a rendered line on
  // this page again. `realSpark` cannot prove that; only the absence of a
  // generator in the module can, and a stale build would still export one.
  test("components/weather/data.ts exports no random-number generator", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require("@/components/weather/data");
    expect(mod.sparkFrom).toBeUndefined();
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const src = require("fs").readFileSync(
      require("path").join(__dirname, "../../components/weather/data.ts"),
      "utf8",
    );
    // Only the tombstone comment may name it, and nothing may compute a value.
    expect(src).not.toMatch(/Math\.random/);
    expect(src).not.toMatch(/^\s*export function sparkFrom/m);
  });
});
