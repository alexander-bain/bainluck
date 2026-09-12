/**
 * #5652 — a market that did not move must never print a COLOURED zero.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sport/baseball/mlb/team/boston-red-sox`, production 2026-09-12 15:52Z:
 * the "MLB World Series Winner" row printed a green **`+0.0%`** — a "went up"
 * badge on a market that did not move. The row behind it:
 *
 *     Boston Red Sox | MLB World Series Winner | probability_change_24h = 0.000034
 *
 * 0.000034 is a 0.0034-POINT move. The gate was `!== 0`, an exact test on the raw
 * fraction, so any value that is nonzero but rounds to `0.0` at one decimal got
 * through — and the COLOUR was then decided by the sign of a rounding residue.
 *
 * Measured reach over all `futures_outcomes` with a nonzero 24h change (19,553):
 * **145 render as a coloured zero — 44 green `+0.0%` and 101 red `-0.0%`.** The
 * red ones are the worse half: an alarm, and a direction, from nothing.
 *
 * ═══ WHY THIS TEST IS SHAPED THIS WAY ═══
 *
 * `isRenderedMove` already existed (UX-P275, `lib/probabilityDisplay.ts`) and its
 * construction is the whole point: the predicate is derived from
 * `formatMovementPoints`, THE SAME function that prints the magnitude, so gate
 * and render cannot drift apart at any `decimals`. It had been adopted on three
 * surfaces (FeedCard, QuantityGroup, futures/OutcomeRow) and MISSED on four:
 *
 *   app/sport/[sport]/[league]/team/[team]/page.tsx  :299  headline movement
 *   app/sport/[sport]/[league]/team/[team]/page.tsx  :450  futures rows (specimen)
 *   components/TeamChampionshipPath.tsx              :50   championship path
 *   components/CategoryBrowser.tsx                   :263  category leader arrow
 *
 * So this file guards the CLASS, not the specimen. Part 1 renders the one surface
 * that renders cleanly under SSR, in BOTH directions (gotcha #43: a guard that
 * only proves the badge disappears would pass on a component that never draws a
 * badge at all). Part 2 is a source scan, which is the only thing that can reach
 * the two page-level surfaces AND the surfaces nobody has written yet — the raw
 * `!== 0` movement gate is a source-level pattern, and a fifth copy of it is the
 * regression this issue is actually about.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { TeamChampionshipPath } from "../../components/TeamChampionshipPath";
import { isRenderedMove } from "../../lib/probabilityDisplay";
import type { ChampionshipPathEntry } from "../../lib/api";

function pathEntry(overrides: Partial<ChampionshipPathEntry>): ChampionshipPathEntry {
  return {
    tier: 1,
    label: "Championship",
    market_name: "World Series",
    market_id: 1,
    probability: 0.04,
    rank: null,
    movement: null,
    ...overrides,
  };
}

const render = (movement: number | null) =>
  renderToStaticMarkup(
    <TeamChampionshipPath color="#BD3039" entries={[pathEntry({ movement })]} />,
  );

/** The two colour classes the movement badge can carry, and nothing else. */
const UP = "text-accent-live";
const DOWN = "text-accent-danger";

describe("#5652 part 1 — the rendered badge, both directions", () => {
  it("draws NO badge for a move that rounds to nothing, up or down", () => {
    // The production specimen, and its mirror. Both are nonzero, so the old
    // `!== 0` gate admitted both and coloured them by sign.
    for (const tiny of [0.000034, -0.000034, 0.0004, -0.0004]) {
      const html = render(tiny);
      expect(html).not.toContain(UP);
      expect(html).not.toContain(DOWN);
      // and never the string itself, whatever markup carries it
      expect(html).not.toContain("0.0");
    }
  });

  it("STILL draws the badge for a move that does render — the guard did not just delete the feature", () => {
    const up = render(0.062);
    expect(up).toContain(UP);
    expect(up).toContain("6.2");
    expect(up).not.toContain(DOWN);

    const down = render(-0.062);
    expect(down).toContain(DOWN);
    expect(down).toContain("6.2");
    expect(down).not.toContain(UP);
  });

  it("draws no badge for the honest zero and for absent movement", () => {
    for (const none of [0, null]) {
      const html = render(none);
      expect(html).not.toContain(UP);
      expect(html).not.toContain(DOWN);
    }
  });

  it("renders the sign, so a fall is not printed as a rise", () => {
    // `formatMovementPoints` returns the ABSOLUTE magnitude, so a caller that
    // forgets the prefix silently turns every drop into a gain. Assert the
    // positive form rather than the absence of a minus.
    expect(render(-0.062)).toContain("-6.2");
    expect(render(0.062)).toContain("+6.2");
  });

  it("agrees with the helper at the boundary, so the gate cannot drift from the print", () => {
    // 0.0005 -> "0.1" at one decimal (rounds up), 0.00049 -> "0.0".
    expect(isRenderedMove(0.0005)).toBe(true);
    expect(isRenderedMove(0.00049)).toBe(false);
    expect(render(0.0005)).toContain(UP);
    expect(render(0.00049)).not.toContain(UP);
  });
});

describe("#5652 part 2 — the class: no surface gates a movement badge on the raw number", () => {
  const ROOT = path.join(__dirname, "..", "..");
  const DIRS = ["app", "components"];

  /**
   * The defect's source signature: a PRICE-MOVEMENT value compared to zero with
   * `!==`/`!=`, which is what `isRenderedMove` exists to replace. Deliberately
   * not a scan for the word "movement" alone — the specimen was named
   * `probability_change_24h`, and the next one will be named something else.
   *
   * `delta` is deliberately NOT in this list. The first draft included it and
   * the scan reported three hits in `app/admin/discover-quality/page.tsx`
   * (`score_delta`, `category_affinity_delta`) — personalization RANKING scores,
   * not probability movements, and nothing renders them as a coloured
   * percentage. A guard that cries wolf on a sibling concept gets deleted by the
   * next person who trips over it, so the pattern names the thing it is about.
   */
  const RAW_GATE =
    /\b[\w.?![\]]*(?:movement|change_24h|price_change)\b[\w.?![\]]*\s*!==?\s*0\b/i;

  function walk(dir: string, out: string[] = []): string[] {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (e.name === "node_modules" || e.name === ".next") continue;
        walk(p, out);
      } else if (/\.tsx?$/.test(e.name)) out.push(p);
    }
    return out;
  }

  const files = DIRS.flatMap((d) => walk(path.join(ROOT, d)));

  it("scans a real population, so this guard cannot pass by finding nothing", () => {
    // Without this, a broken walk() makes every assertion below vacuous.
    expect(files.length).toBeGreaterThan(200);
    expect(files.some((f) => f.endsWith("CategoryBrowser.tsx"))).toBe(true);
    expect(files.some((f) => f.includes("team") && f.endsWith("page.tsx"))).toBe(true);
  });

  it("finds no raw zero-comparison gate on a movement badge anywhere", () => {
    const offenders: string[] = [];
    for (const f of files) {
      fs.readFileSync(f, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (RAW_GATE.test(line)) offenders.push(`${path.relative(ROOT, f)}:${i + 1}  ${line.trim()}`);
        });
    }
    expect(offenders).toEqual([]);
  });

  it("the four repaired surfaces import the helper they were missing", () => {
    const repaired = [
      "app/sport/[sport]/[league]/team/[team]/page.tsx",
      "components/TeamChampionshipPath.tsx",
      "components/CategoryBrowser.tsx",
    ];
    for (const rel of repaired) {
      const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
      expect(src).toContain("isRenderedMove");
      expect(src).toContain("@/lib/probabilityDisplay");
    }
  });
});
