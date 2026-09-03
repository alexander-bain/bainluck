// UX-P275 (#2585) — A MARKET THAT DID NOT MOVE SAYS NOTHING.
//
// What the shopper saw, `/futures/1` -> "All Outcomes" -> the LAST MOVE column:
// rows whose price did not move rendered `-0.0%` inside the red "went down"
// pill. A no-change read as an alarm.
//
// ── THE MECHANISM, AND IT IS ONE LINE ───────────────────────────────────────
//
// Every one of these renderers decided "did it move?" by testing the WIRE
// FRACTION for exact zero, and then printed the value rounded to one decimal:
//
//     {change !== null && change !== 0 && (            <- asks the NUMBER
//       <span className={change > 0 ? UP : DOWN}>      <- colour on the raw sign
//         {change > 0 ? "+" : ""}{(change * 100).toFixed(1)}%   <- prints 1dp
//
// Those are two different questions and they disagree on the whole open band
// that is nonzero yet rounds to nothing. `-0.00029` passes `!== 0`, so it earns
// a coloured pill, and then prints `-0.0`. Which colour a no-move got was
// decided purely by the sign of a rounding residue.
//
// ── THE SIZE, MEASURED ON PRODUCTION 2026-09-02 (not taken from the issue) ──
//
// `GET /api/futures/1`: of 22 outcomes carrying a change, **16 printed a
// coloured zero** — 13 green `+0.0%` and 3 red `-0.0%`. Only 6 rows in that
// column said anything true. Read off the live DOM as well as the payload, and
// the two agree exactly. `GET /api/feed?limit=50` carries 81 `movement` values,
// 41 of which render as a zero and 27 of which are EXACTLY zero.
//
// ⚠️ The issue says `+0.0%` renders "plain, un-pilled". It does not — that was
// a mis-read. Reading each span's OWN className off production shows `+0.0%` in
// `bg-emerald-500/15 text-emerald-400`, a green pill, and `-0.0%` in
// `bg-red-500/15 text-red-400`. BOTH signs are coloured, which is why the fix
// gates on magnitude rather than on the negative case.
//
// ── WHY THE FIX IS A PREDICATE AND NOT A THRESHOLD ──────────────────────────
//
// `isRenderedMove` is derived from `formatMovementPoints` — the very function
// that produces the printed magnitude — so the gate and the rendering cannot
// drift apart at any `decimals`. A constant would have to be kept in sync with
// each caller's precision by hand, which is the drift UX-P048 exists to stop.
// It is the same construction UX-P046 already uses in the same module, where
// the bands come from the rounding RESULT "so the two ends cannot disagree".
//
// The site-wide convention agrees: every renderer that CANNOT print a zero is
// the one whose floor is >= its own display precision — `TournamentCard`'s
// `Math.abs(m) > 0.001` against one decimal is exactly "at least a tenth of a
// point". The vulnerable ones are the ones that gate on `!== 0` instead.
//
// ── WHAT THIS HARNESS CAN AND CANNOT SEE ────────────────────────────────────
//
// `CombinedFeedCard` and `FeedCard` are real exported components, so every
// claim about them below is read off RENDERED MARKUP.
//
// The third surface, `/futures/1`'s `OutcomeRow`, lives inside
// `app/futures/[id]/page.tsx` and is NOT exported — and it must not become
// exported, because a named export from a Next.js `page.tsx` is a typecheck
// error against the page contract (UX-P274 paid for that one). So its claim is
// a SOURCE SCAN, which is strictly weaker, and it is labelled as such rather
// than dressed up as a render. The behaviour it would assert is covered
// behaviourally by the predicate tests and by the two components that share the
// identical shape.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "fs";
import path from "path";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import type { GroupedMarket } from "@/lib/feedSections";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import CombinedFeedCard from "../components/CombinedFeedCard";
import { isRenderedMove, formatMovementPoints } from "@/lib/probabilityDisplay";

const REPO = path.join(__dirname, "..");

// ── The production population, captured 2026-09-02 from GET /api/futures/1 ──
// Every non-null `probability_change_24h` on the reported market, in payload
// order. 16 of these 22 printed a coloured zero before this ship.
const PRODUCTION_CHANGES: ReadonlyArray<readonly [string, number]> = [
  ["Los Angeles Dodgers", 0.00149],
  ["Milwaukee Brewers", 7.3e-5],
  ["New York Yankees", 6.6e-5],
  ["Tampa Bay Rays", -0.001251],
  ["Atlanta Braves", 0.000758],
  ["Philadelphia Phillies", -0.000777],
  ["Boston Red Sox", 4e-5],
  ["Chicago Cubs", 3.9e-5],
  ["Chicago White Sox", -0.000685],
  ["Houston Astros", 0.00089],
  ["Cleveland Guardians", 2e-5],
  ["San Diego Padres", -0.00029],
  ["Texas Rangers", 1.3e-5],
  ["Toronto Blue Jays", -0.000414],
  ["Seattle Mariners", 7e-6],
  ["Baltimore Orioles", 0.000428],
  ["Arizona Diamondbacks", -0.000414],
  ["Minnesota Twins", 3e-6],
  ["Detroit Tigers", 1e-6],
  ["Miami Marlins", 1e-6],
  ["Pittsburgh Pirates", 1e-6],
  ["St. Louis Cardinals", 1e-6],
];

// ── Fixtures, shaped like the payload `/api/feed` serves ────────────────────

function feedOutcome(name: string, movement: number | null, probability = 0.4) {
  return {
    id: Math.abs(Math.round(probability * 1e6)) + name.length,
    rank: 1,
    name,
    probability,
    rendered_percent: Math.round(probability * 100),
    movement,
  };
}

function combinedGroup(
  movers: ReadonlyArray<readonly [string, number | null]>,
): GroupedMarket {
  const item = {
    type: "futures",
    score: 71,
    reason: null,
    headline: null,
    data: {
      id: 114160,
      name: "MLB World Series Winner",
      llm_sport_category: "baseball",
      source: "kalshi",
      source_count: 1,
      status: "open",
      top_outcomes: movers.map(([n, m], i) => feedOutcome(n, m, 0.4 - i * 0.01)),
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
  return { items: [item] } as unknown as GroupedMarket;
}

/**
 * Every movement badge the combined card rendered, keyed by outcome name.
 *
 * A POSITIVE extraction: it states the shape it expects and throws on anything
 * else, rather than peeling characters off with `.replace()`. A subtractive
 * parse silently mangles what it cannot handle, which is the last thing you
 * want in a guard whose whole job is to read exact output (UX-P274 paid a
 * CodeQL HIGH for the subtractive version of this helper).
 */
function badges(markup: string): string[] {
  const re =
    /<span[^>]*data-testid="combined-outcome-movement"[^>]*>([^<]*)<\/span>/g;
  const found: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) found.push(decode(m[1]).trim());
  // If a badge ever grows a child element, `[^<]*` skips it entirely and this
  // under-reports. Cross-check the yield against the raw attribute count so it
  // fails loudly instead of quietly returning fewer rows.
  const count = (markup.match(/data-testid="combined-outcome-movement"/g) ?? [])
    .length;
  expect(found).toHaveLength(count);
  return found;
}

function decode(s: string): string {
  const named: Record<string, string> = {
    amp: "&",
    lt: "<",
    gt: ">",
    quot: '"',
    "#x27": "'",
    "#39": "'",
  };
  return s.replace(/&(#x?[0-9a-fA-F]+|[a-z]+);/g, (whole, body: string) => {
    if (body in named) return named[body];
    if (body[0] === "#") {
      const n =
        body[1] === "x" || body[1] === "X"
          ? Number.parseInt(body.slice(2), 16)
          : Number.parseInt(body.slice(1), 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : whole;
    }
    return whole;
  });
}

const renderCombined = (
  movers: ReadonlyArray<readonly [string, number | null]>,
) => renderToStaticMarkup(<CombinedFeedCard group={combinedGroup(movers)} />);

// ────────────────────────────────────────────────────────────────────────────

describe("isRenderedMove — the gate is the printed string, not the raw value", () => {
  it("refuses a move too small to print at the precision it will be printed", () => {
    // 0.00004 * 100 = 0.004 -> "0.0". Nonzero, but it prints as nothing.
    expect(isRenderedMove(0.00004)).toBe(false);
    expect(isRenderedMove(-0.00004)).toBe(false);
  });

  it("admits the smallest move that does print, in BOTH directions", () => {
    // 0.0005 * 100 = 0.05 -> "0.1" (toFixed rounds half away from zero here).
    expect(isRenderedMove(0.0005)).toBe(true);
    expect(isRenderedMove(-0.0005)).toBe(true);
    expect(formatMovementPoints(0.0005)).toBe("0.1");
    expect(formatMovementPoints(-0.0005)).toBe("0.1");
  });

  it("is SYMMETRIC — the sign never decides whether a move counts", () => {
    for (const v of [1e-6, 4e-5, 0.00029, 0.0005, 0.00149, 0.07, 0.64]) {
      expect(isRenderedMove(v)).toBe(isRenderedMove(-v));
    }
  });

  it("moves with the precision, so a caller choosing 2dp is not silently wrong", () => {
    // 0.00004 prints as "0.00" at 2dp too, but 0.0004 prints "0.04".
    expect(isRenderedMove(0.0004, 2)).toBe(true);
    expect(isRenderedMove(0.0004, 1)).toBe(false);
    expect(isRenderedMove(0.00004, 2)).toBe(false);
  });

  it("treats an exact zero as no move, which is what it always was", () => {
    expect(isRenderedMove(0)).toBe(false);
    expect(isRenderedMove(-0)).toBe(false);
  });

  it("refuses anything unusable rather than coercing it", () => {
    expect(isRenderedMove(null)).toBe(false);
    expect(isRenderedMove(undefined)).toBe(false);
    expect(isRenderedMove(NaN)).toBe(false);
    expect(isRenderedMove(Infinity)).toBe(false);
    expect(isRenderedMove(-Infinity)).toBe(false);
  });

  it("agrees with formatMovementPoints on the whole production population", () => {
    // The invariant that makes the fix true BY CONSTRUCTION: a value is admitted
    // if and only if the magnitude it would print is not zero. No third source
    // of truth, so there is nothing to keep in sync.
    for (const [, v] of PRODUCTION_CHANGES) {
      const printed = formatMovementPoints(v);
      expect(isRenderedMove(v)).toBe(Number.parseFloat(printed!) !== 0);
    }
  });
});

describe("the reported population no longer prints a coloured zero", () => {
  it("admits exactly the 6 of 22 production rows that have something to say", () => {
    const admitted = PRODUCTION_CHANGES.filter(([, v]) => isRenderedMove(v));
    expect(admitted).toHaveLength(6);
    expect(admitted.map(([n]) => n)).toEqual([
      "Los Angeles Dodgers",
      "Tampa Bay Rays",
      "Atlanta Braves",
      "Philadelphia Phillies",
      "Chicago White Sox",
      "Houston Astros",
    ]);
  });

  it("names the 16 rows that used to carry a coloured zero", () => {
    const suppressed = PRODUCTION_CHANGES.filter(([, v]) => !isRenderedMove(v));
    expect(suppressed).toHaveLength(16);
    // Every one of them WOULD have printed a zero magnitude, i.e. none is being
    // hidden for any reason other than having nothing to print.
    for (const [, v] of suppressed) {
      expect(Number.parseFloat(formatMovementPoints(v)!)).toBe(0);
    }
    // And three of them are the negative ones the shopper photographed in red.
    expect(suppressed.filter(([, v]) => v < 0)).toHaveLength(3);
  });

  it("no admitted production value can render a zero magnitude", () => {
    for (const [name, v] of PRODUCTION_CHANGES) {
      if (!isRenderedMove(v)) continue;
      expect(`${name}:${formatMovementPoints(v)}`).not.toMatch(/:0\.0$/);
    }
  });
});

describe("CombinedFeedCard (/sports Top Markets, grouped) — rendered markup", () => {
  // ⚠️ THESE TWO ASSERT ON RENDERED TEXT, NOT ON `badges()`, AND THAT IS
  // DELIBERATE. `badges()` selects on the `data-testid` this diff ADDED, so on
  // the parent it finds nothing and "no badge" would read true for entirely the
  // wrong reason — absence of the marker and absence of the thing are the same
  // observation. Anchor a PRESENCE check on your new attribute; anchor an
  // ABSENCE check on something older than your diff.
  it("renders NO zero badge for a move that would print as zero", () => {
    // -0.00029 is San Diego's real production value: the exact shape that
    // produced `-0.0%` in the shopper's screenshot.
    const html = renderCombined([["San Diego Padres", -0.00029]]);
    expect(html).not.toContain("0.0%");
    expect(badges(html)).toEqual([]);
  });

  it("renders no zero badge for the positive twin either — BOTH signs were wrong", () => {
    const html = renderCombined([["Milwaukee Brewers", 7.3e-5]]);
    expect(html).not.toContain("0.0%");
    expect(badges(html)).toEqual([]);
  });

  it("never emits a signed zero, over the whole production population", () => {
    const html = renderCombined(PRODUCTION_CHANGES.map(([n, v]) => [n, v]));
    expect(html).not.toContain("-0.0%");
    expect(html).not.toContain("+0.0%");
    for (const b of badges(html)) {
      expect(b).not.toMatch(/[+-]0\.0%/);
    }
  });

  it("CONTROL — a real move is untouched, with its sign and its magnitude", () => {
    // The whole change is a NARROWING: nothing that printed a nonzero magnitude
    // before may print differently now.
    expect(badges(renderCombined([["Los Angeles Dodgers", 0.00149]]))).toEqual([
      "+0.1%",
    ]);
    expect(badges(renderCombined([["Tampa Bay Rays", -0.001251]]))).toEqual([
      "-0.1%",
    ]);
    expect(badges(renderCombined([["The Odyssey", -0.07]]))).toEqual(["-7.0%"]);
    expect(badges(renderCombined([["Big Mover", 0.64]]))).toEqual(["+64.0%"]);
  });

  it("CONTROL (green on master too) — a null movement was always silent", () => {
    expect(badges(renderCombined([["No Data", null]]))).toEqual([]);
  });

  it("CONTROL (green on master too) — an exact zero was always silent", () => {
    expect(badges(renderCombined([["Flat", 0]]))).toEqual([]);
  });

  it("keeps the direction colour keyed to the sign for real moves", () => {
    const up = renderCombined([["Riser", 0.02]]);
    const down = renderCombined([["Faller", -0.02]]);
    expect(up).toContain("text-accent-live");
    expect(up).not.toContain("text-accent-danger");
    expect(down).toContain("text-accent-danger");
    expect(down).not.toContain("text-accent-live");
  });

  it("the card still renders its other content when every move is suppressed", () => {
    // Fail-open: suppressing badges must not blank the card.
    const html = renderCombined(
      PRODUCTION_CHANGES.filter(([, v]) => !isRenderedMove(v)).map(
        ([n, v]) => [n, v] as const,
      ),
    );
    expect(badges(html)).toEqual([]);
    expect(html).toContain("MLB World Series Winner");
    expect(html).toContain("Milwaukee Brewers");
  });
});

describe("ANTI-DRIFT (SOURCE SCAN, not a render) — the three reported call sites", () => {
  // Labelled honestly: these read the file, not the DOM. `OutcomeRow` cannot be
  // rendered here (see the header), and for the two that CAN be rendered the
  // behavioural claims above are the load-bearing ones — this suite exists so a
  // future edit cannot quietly reintroduce the raw arithmetic.
  const read = (rel: string) => {
    const p = path.join(REPO, rel);
    // A scan that cannot find its subject must RAISE, not silently pass.
    if (!fs.existsSync(p)) throw new Error(`ANTI-DRIFT subject missing: ${rel}`);
    return fs.readFileSync(p, "utf8");
  };

  const SUBJECTS = [
    "app/futures/[id]/page.tsx",
    "components/CombinedFeedCard.tsx",
    "components/FeedCard.tsx",
  ];

  it.each(SUBJECTS)("%s gates on isRenderedMove", (rel) => {
    expect(read(rel)).toContain("isRenderedMove(");
  });

  it.each(SUBJECTS)("%s delegates the magnitude instead of restating it", (rel) => {
    expect(read(rel)).toContain("formatMovementPoints(");
  });

  it("the futures LAST MOVE column no longer multiplies by 100 itself", () => {
    const src = read("app/futures/[id]/page.tsx");
    expect(src).not.toMatch(/\(\s*change\s*\*\s*100\s*\)\.toFixed/);
    expect(src).not.toMatch(/change\s*!==\s*null\s*&&\s*change\s*!==\s*0/);
  });

  it("CombinedFeedCard no longer multiplies by 100 itself", () => {
    const src = read("components/CombinedFeedCard.tsx");
    expect(src).not.toMatch(/bestMovement\s*\*\s*100/);
    expect(src).not.toMatch(/bestMovement\s*!==\s*0/);
  });

  it("FeedCard's leader movement no longer multiplies by 100 itself", () => {
    const src = read("components/FeedCard.tsx");
    expect(src).not.toMatch(/leader\.movement\s*\*\s*100/);
    expect(src).not.toMatch(/leader\.movement\s*!==\s*0/);
  });
});
