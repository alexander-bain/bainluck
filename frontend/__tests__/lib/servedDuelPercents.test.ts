/**
 * #2279 — the web arm of "both served or neither", in values and in shape.
 *
 * The native arm lives in `__tests__/ios/duelPercentServedPair.test.ts` and has to
 * read Swift as text because jest cannot execute it. Web has no such excuse: the
 * decision is a real function here, so it is EXECUTED, and the source scan below
 * exists only to stop a surface routing around it again.
 *
 * The two web surfaces that adopted UX-P114's served pair — `FeedCard` and
 * `discover/EventCard` — both coalesced per side:
 *
 *     const awayPct = data.current_odds?.away_rendered_percent ?? fallbackAwayPct;
 *     const homePct = data.current_odds?.home_rendered_percent ?? fallbackHomePct;
 *
 * which prints a served value beside a locally derived one whenever a payload
 * carries one field and not the other, and that is the 101 UX-P114 shipped to
 * close arriving from the other side.
 */

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

import { renderedDuelPercents } from "@/lib/renderedPercent";
import { servedDuelPercents } from "@/lib/servedDuelPercents";

const FRONTEND = join(__dirname, "../..");

// 0.505 / 0.495 is the row the issue names: served home 51 beside a naively
// derived away 50 is 101.
const AWAY = 0.495;
const HOME = 0.505;

describe("#2279 — servedDuelPercents takes the pair or neither of it", () => {
  it("the local rule answers 49/51 for this pair", () => {
    expect(renderedDuelPercents(AWAY, HOME)).toEqual([49, 51]);
  });

  it("both served — used verbatim", () => {
    // 30/70 is deliberately NOT the local answer, so an implementation that
    // ignored the payload would return 49/51 and be caught. (LAT-P119's M7
    // survived because its served values happened to equal the local ones.)
    expect(servedDuelPercents(AWAY, HOME, 30, 70)).toEqual([30, 70]);
  });

  it("one side served — the pair falls back WHOLE", () => {
    expect(servedDuelPercents(AWAY, HOME, null, 70)).toEqual([49, 51]);
    expect(servedDuelPercents(AWAY, HOME, 30, null)).toEqual([49, 51]);
    // Never a mixture, from either direction.
    expect(servedDuelPercents(AWAY, HOME, null, 70)).not.toEqual([49, 70]);
    expect(servedDuelPercents(AWAY, HOME, 30, null)).not.toEqual([30, 51]);
  });

  it("undefined is treated as absent, not as a value", () => {
    // The payload types are optional, so a missing key arrives as `undefined`
    // rather than `null`. A `=== null` test would take `undefined` as served.
    expect(servedDuelPercents(AWAY, HOME, undefined, 70)).toEqual([49, 51]);
    expect(servedDuelPercents(AWAY, HOME, 30, undefined)).toEqual([49, 51]);
    expect(servedDuelPercents(AWAY, HOME, undefined, undefined)).toEqual([49, 51]);
  });

  it("a served ZERO is a value, not an absence", () => {
    // `??` was right about this and `||` would not be: a 0% side is a real
    // reading. The rewrite must not lose it.
    expect(servedDuelPercents(AWAY, HOME, 0, 100)).toEqual([0, 100]);
  });

  it("neither served — the contract rule answers", () => {
    expect(servedDuelPercents(AWAY, HOME, null, null)).toEqual([49, 51]);
  });

  it("no partial payload can make a half-percent card sum to anything but 100", () => {
    for (let n = 1; n < 100; n += 1) {
      const home = (n + 0.5) / 100;
      const away = 1 - home;
      const [localAway, localHome] = renderedDuelPercents(away, home);
      const partials: Array<[number | null, number | null]> = [
        [null, localHome],
        [localAway, null],
        [undefined as unknown as null, localHome],
        [null, null],
      ];
      for (const [sa, sh] of partials) {
        const [a, h] = servedDuelPercents(away, home, sa, sh);
        expect((a as number) + (h as number)).toBe(100);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// The shape. A correct helper nobody calls is worth nothing.
// ---------------------------------------------------------------------------

function tsFilesUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry === "e2e") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...tsFilesUnder(full));
    else if (/\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

/**
 * Comments and string bodies removed — the fix documents the defect by quoting
 * it, so a scanner that reads prose as code reports the cure as the disease.
 * (The native arm of this guard failed exactly that way on its first run.)
 */
function code(src: string): string {
  let out = "";
  let i = 0;
  let inString = false;
  let quote = "";
  let inLine = false;
  let inBlock = false;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (inLine) {
      if (c === "\n") {
        inLine = false;
        out += c;
      }
      i += 1;
    } else if (inBlock) {
      if (c === "*" && next === "/") {
        inBlock = false;
        i += 2;
      } else {
        if (c === "\n") out += c;
        i += 1;
      }
    } else if (inString) {
      if (c === "\\") i += 2;
      else {
        if (c === quote) inString = false;
        i += 1;
      }
    } else if (c === "/" && next === "/") {
      inLine = true;
      i += 2;
    } else if (c === "/" && next === "*") {
      inBlock = true;
      i += 2;
    } else if (c === '"' || c === "'" || c === "`") {
      inString = true;
      quote = c;
      out += c;
      i += 1;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

describe("#2279 — no web surface coalesces the served pair per side", () => {
  const files = tsFilesUnder(FRONTEND).filter((f) => !f.includes("__tests__"));

  it("scans a real corpus, not an empty one", () => {
    // A narrowed scan prints the same clean line as a full one, so the
    // denominator is asserted (gotcha #53's discipline).
    expect(files.length).toBeGreaterThan(200);
    expect(files.some((f) => f.endsWith("components/FeedCard.tsx"))).toBe(true);
    expect(files.some((f) => f.endsWith("components/discover/EventCard.tsx"))).toBe(true);
  });

  it.each(files.map((f) => [f.slice(FRONTEND.length + 1), f]))(
    "%s does not fall back per side",
    (_label, path) => {
      const src = code(readFileSync(path, "utf8"));
      expect(src.match(/(away|home)_rendered_percent\s*\?\?/g) ?? []).toHaveLength(0);
    },
  );

  it.each([
    "components/FeedCard.tsx",
    "components/discover/EventCard.tsx",
  ])("%s routes the choice through servedDuelPercents", (rel) => {
    const src = code(readFileSync(join(FRONTEND, rel), "utf8"));
    expect(src).toContain("servedDuelPercents(");
    // Side-specific: a transpose still sums to 100 and nothing else here sees it.
    expect(src).toMatch(/\[awayPct, homePct\] = servedDuelPercents\(/);
  });
});
