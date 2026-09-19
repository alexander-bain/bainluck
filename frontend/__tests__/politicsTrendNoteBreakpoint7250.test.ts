// #7250 — A CAPTION IS GATED ON WHETHER ITS SUBJECT IS ON THE SCREEN, NOT ON
// WHETHER ITS SUBJECT EXISTS.
//
// What the shopper saw, `/politics` at 390px on production, 2026-09-19 16:2xZ
// (`artifacts/ux-1361/BEFORE-prod-390-caption.png`): under the fourteen rows of
// "2028 Democratic presidential nominee", in grey,
//
//     Dimmed trend lines have stretches we have no numbers for —
//     the longest is 9 days.
//
// There are no trend lines on that screen. At phone width the table is
// candidate · probability · now; the spark column and the Δ 7d chip are
// `display: none`. The reader was handed the definition of a visual convention
// absent from their page, with a precise-sounding "9 days" attached to nothing.
//
// ── THE MECHANISM, AND IT IS TWO GATES WHERE THERE SHOULD BE ONE ────────────
//
// `trendNote` (page.tsx:313) is correctly gated on whether any row IS dimmed —
// #2961's acceptance is that a complete series is not marked. It was never
// gated on whether the dimming can be SEEN. The column it defines is gated on
// the breakpoint (346, 377); the caption was not (390). One subject, two gates,
// and only one of them a breakpoint.
//
// ── WHY THIS TEST READS TWO FILES, AND WHY IT READS THE CSS IN ORDER ────────
//
// jsdom applies no media query and the CSS Module is swapped for a proxy under
// jest, so a render test cannot see a single width-dependent thing here — a
// rendered caption reports itself present at every width, which is the defect
// rendering as a pass. The phone layout exists only in the stylesheet.
//
// And there is a second invariant, new with this fix and invisible in both
// files read alone. Every previous holder of `.hideOnMobile` carries it as its
// ONLY class, so `display: none` had nothing to beat. The caption carries
// `.sourceLegend .hideOnMobile`, and `.sourceLegend` declares `display: flex`.
// Both selectors are one class — (0,1,0) — and `@media` adds no specificity.
// So the caption disappears on a phone for exactly one reason: `.hideOnMobile`
// is LATER IN THE FILE. That is a fact about source order, it is load-bearing,
// and nothing else in the repo would notice it breaking. It is pinned below.
//
// Every parser asserts what it found before it asserts anything about it: a
// source-scanning guard that quietly matches nothing is worse than no guard.
//
//   npx jest --testPathPatterns=politicsTrendNoteBreakpoint7250

import fs from "node:fs";
import path from "node:path";

const PAGE = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "page.tsx"),
  "utf8",
);
const CSS = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "politics.module.css"),
  "utf8",
);

const MOBILE_BREAKPOINT = "@media (max-width: 720px)";

/* ═══ 0 · the stylesheet, split at the breakpoint ════════════════════════ */

/** `[desktopHalf, mobileBlockBody]`, by brace-matching the media query. */
function splitAtBreakpoint(): [string, string] {
  const at = CSS.indexOf(MOBILE_BREAKPOINT);
  if (at === -1) {
    throw new Error(
      `#7250 guard cannot find "${MOBILE_BREAKPOINT}" in politics.module.css. ` +
        `If the breakpoint moved, re-point this guard — do not delete it.`,
    );
  }
  const open = CSS.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < CSS.length; i++) {
    if (CSS[i] === "{") depth++;
    else if (CSS[i] === "}" && --depth === 0) {
      return [CSS.slice(0, at), CSS.slice(open + 1, i)];
    }
  }
  throw new Error("#7250 guard: the mobile media query is never closed.");
}

const [DESKTOP_CSS, MOBILE_CSS] = splitAtBreakpoint();

type Rule = { selector: string; body: string; index: number };

/** Every `selector { body }` in `css`, with its offset. Flat sheets only. */
function rules(css: string, offset: number): Rule[] {
  const out: Rule[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css))) {
    out.push({
      selector: m[1].replace(/\/\*[\s\S]*?\*\//g, "").trim(),
      body: m[2],
      index: offset + m.index,
    });
  }
  return out;
}

/** Rules whose selector LIST contains `.name` as a whole class. */
const selecting = (rs: Rule[], name: string) =>
  rs.filter((r) =>
    r.selector
      .split(",")
      .some((s) => new RegExp(`(^|[^-\\w])\\.${name}(?![-\\w])`).test(s)),
  );

const declares = (r: Rule, prop: string) =>
  new RegExp(`(^|[;{\\s])${prop}\\s*:`).test(r.body);

const DESKTOP_RULES = rules(DESKTOP_CSS, 0);
const MOBILE_RULES = rules(MOBILE_CSS, CSS.indexOf(MOBILE_BREAKPOINT));
const ALL_RULES = [...DESKTOP_RULES, ...MOBILE_RULES];

/** Class names the phone stylesheet removes from flow. */
const HIDDEN_ON_PHONE = new Set(
  MOBILE_RULES.filter((r) => /display\s*:\s*none/.test(r.body)).flatMap((r) =>
    [...r.selector.matchAll(/\.([-\w]+)/g)].map((m) => m[1]),
  ),
);

/* ═══ 1 · the markup: caption and column share one gate ═════════════════ */

/**
 * The `s.foo` classes on the element whose first line matches `matcher`.
 *
 * The anchor is the line a reader would search for — the testid, the child
 * component, the label expression. That is not always the line carrying the
 * className: the trend heading puts its label on the next line down. So a
 * matched line with no `className=` walks BACK to the element's opening tag,
 * and gives up loudly rather than returning an empty set, which would read in
 * every assertion below exactly like "this element carries no gate".
 */
function classesOn(matcher: RegExp, what: string): string[] {
  const lines = PAGE.split("\n");
  const at = lines.findIndex((l) => matcher.test(l));
  if (at === -1) {
    throw new Error(
      `#7250 guard cannot find ${what} (${matcher}) in app/politics/page.tsx. ` +
        `If it was renamed or reflowed, re-point this guard — do not delete it.`,
    );
  }
  let i = at;
  while (i >= 0 && at - i <= 3 && !lines[i].includes("className=")) i--;
  if (i < 0 || !lines[i].includes("className=")) {
    throw new Error(
      `#7250 guard found ${what} at line ${at + 1} but no className= within three ` +
        `lines above it. Re-point this guard — an empty class set here would pass.`,
    );
  }
  const className = lines[i].match(/className=\{([^}]*(?:\}[^}]*)*?)\}\s*(?:[a-zA-Z-]+=|\/?>)/);
  const scope = className ? className[1] : lines[i];
  return [...scope.matchAll(/\bs\.([-\w]+)/g)].map((m) => m[1]);
}

const CAPTION_CLASSES = classesOn(
  /data-testid="politics-trend-note"/,
  "the trend-note caption",
);
const SPARK_CLASSES = classesOn(
  /<CandidateSpark /,
  "the spark cell (the caption's referent)",
);
const HEADING_CLASSES = classesOn(
  /\{trendWindow \? `\$\{trendWindow\} trend` : "Trend"\}/,
  "the trend column heading",
);

/**
 * The gate is DERIVED, never spelled: the classes on the spark cell that the
 * phone stylesheet actually hides. Spelling `hideOnMobile` here would make this
 * file assert the string it was written from; deriving it means the guard still
 * holds if the gate is ever renamed, and — the part that matters — it cannot go
 * quietly green by the column ceasing to be hidden.
 */
const GATE = SPARK_CLASSES.filter((c) => HIDDEN_ON_PHONE.has(c));

describe("#7250 · the markup the parser is reasoning about", () => {
  test("the spark cell is hidden on a phone by at least one class", () => {
    // If this ever reads empty, the column is visible on a phone and the rest
    // of this file would be asserting a subset of nothing. Loud, not vacuous.
    expect(SPARK_CLASSES.length).toBeGreaterThan(0);
    expect(GATE.length).toBeGreaterThan(0);
  });

  test("the caption is still conditional on a row BEING dimmed (#2961)", () => {
    // The breakpoint is an ADDITIONAL gate. If this fix ever gets "simplified"
    // into replacing `trendNote &&`, a complete series starts being marked and
    // #2961's acceptance is gone with no test of its own to say so.
    expect(PAGE).toMatch(
      /\{trendNote && \(\s*\n\s*<div className=[^\n]*data-testid="politics-trend-note"/,
    );
  });
});

describe("#7250 · the caption carries the gate of the column it defines", () => {
  test("every class that hides the spark cell also sits on the caption", () => {
    // THE REGRESSION ASSERTION. Before the fix the caption's classes were
    // [sourceLegend] and the gate was [hideOnMobile]: this read false.
    for (const g of GATE) expect(CAPTION_CLASSES).toContain(g);
  });

  test("the heading over that column is gated the same way", () => {
    // The caption and the heading describe the same column from opposite ends.
    // Leaving one of the three behind is how this bug was made.
    for (const g of GATE) expect(HEADING_CLASSES).toContain(g);
  });

  test("the caption keeps its own look — the gate is added, not swapped in", () => {
    expect(CAPTION_CLASSES.length).toBeGreaterThan(GATE.length);
    expect(CAPTION_CLASSES).toContain("sourceLegend");
  });
});

/* ═══ 2 · the cascade that makes the gate bite ══════════════════════════ */

describe("#7250 · `display: none` actually wins on the caption", () => {
  test("the gate is declared ONLY inside the mobile block", () => {
    // If a copy appeared at desktop scope the caption would vanish at every
    // width and the reader would lose a caption that is correct and useful
    // there. That is the over-reach arm, and nothing else would catch it.
    for (const g of GATE) {
      expect(selecting(MOBILE_RULES, g).length).toBeGreaterThan(0);
      expect(selecting(DESKTOP_RULES, g)).toHaveLength(0);
    }
  });

  test("the gate removes the caption from FLOW, not just from view", () => {
    for (const g of GATE) {
      const bodies = selecting(MOBILE_RULES, g).map((r) => r.body).join("");
      expect(bodies).toMatch(/display:\s*none/);
      // `visibility: hidden` / `opacity: 0` would leave a 10px-margined empty
      // grey band between the last candidate and the Kalshi legend.
      expect(bodies).not.toMatch(/visibility:\s*hidden|opacity:\s*0/);
    }
  });

  test("the gate is LATER IN THE FILE than every competing `display`", () => {
    // The whole fix rests on source order. `.sourceLegend` is `display: flex`
    // and `.hideOnMobile` is `display: none`; both are (0,1,0), and a media
    // query adds no specificity, so the later rule wins and nothing else
    // decides it. Move the mobile block above `.sourceLegend`, or re-declare
    // `display` for `.sourceLegend` inside it, and the caption comes back on
    // every phone — with no other test in the repo reading differently.
    const gateAt = Math.min(
      ...GATE.flatMap((g) => selecting(MOBILE_RULES, g).map((r) => r.index)),
    );
    const competing = ALL_RULES.filter(
      (r) =>
        CAPTION_CLASSES.includes("sourceLegend") &&
        selecting([r], "sourceLegend").length > 0 &&
        declares(r, "display"),
    );

    // Non-vacuity: there IS a competing declaration. If `.sourceLegend` ever
    // stops declaring `display`, this test stops being about anything and says
    // so here rather than passing on an empty loop.
    expect(competing.length).toBeGreaterThan(0);
    for (const r of competing) expect(r.index).toBeLessThan(gateAt);
  });
});
