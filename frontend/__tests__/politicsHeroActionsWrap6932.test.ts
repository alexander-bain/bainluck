// #6932 — THE CONTROL STACK WRAPS; THE CONTROLS THEMSELVES DO NOT.
//
// What the shopper saw, `/politics` at 390px on production
// (`artifacts/ux-1336/6932-390-BEFORE-politics.png`): the Presidential 2028
// card's `Merged | Kalshi | Polymarket` toggle ran 17px past the card's content
// box. Its grey track crossed the card's rounded corner and `Polymarket` — a
// BUTTON, not a label — sat on the boundary. Measured, not eyeballed:
// `actionsRight=376` against `cardContentRight=359`.
//
// ── WHY #4651's FIX DID NOT ALREADY COVER IT ────────────────────────────────
//
// `.presHeroHead { flex-wrap: wrap }` (#4651) dropped the controls onto their
// own line and stopped the whole PAGE scrolling sideways. But a wrap on the
// parent only decides where the actions block STARTS. It says nothing about how
// wide that block may be, and the block's own `flex-wrap` was still `nowrap`, so
// it stayed at its intrinsic ~335px inside a 318px interior and overflowed by
// the difference. Two rules of the same shape, one level apart, and the second
// is invisible from the first.
//
// ── WHY THIS GUARD IS TWO-SIDED, AND WHERE THE REAL RISK IS ─────────────────
//
// Asserting "the mobile block says `flex-wrap: wrap`" alone would just restate
// the diff. The invariant worth pinning is the SHAPE of the fix, and it has two
// halves that a future edit can break in opposite directions:
//
//   the CONTAINER of the control groups must wrap   (or the spill returns)
//   each control GROUP must not                     (or the fix breaks chrome)
//
// The second half is the one nobody would think to check. `.sourceToggle` and
// `.heroVariantToggle` are single objects whose shared grey track IS the
// affordance; a `Polymarket` that fell to a second line *inside* that pill would
// be a worse defect than the 17px spill, and it would be reached by one more
// `flex-wrap: wrap` applied at the wrong level — the most natural wrong fix for
// exactly this bug. So the leaves are pinned nowrap across the whole stylesheet.
//
// The markup half matters because the container's wrap is only sufficient while
// every child of it is a self-contained control narrower than the card. This
// reads the control groups OUT of `page.tsx` — resolving `<SourceToggle/>`
// through to the class its root renders — rather than hard-coding two names, so
// a third control group added to the row is held to the same rule.
//
// jsdom applies no media query and the CSS Module is swapped for a proxy under
// jest (`__tests__/helpers/cssModuleProxy.js`), so a render test can read none of
// these numbers: a rendered `.presHeroActions` reports no wrap and no width. The
// phone layout exists only in the stylesheet. Same reasoning as #3704's guard,
// which is the precedent this follows.
//
// Every parser asserts what it FOUND before it asserts anything about it — a
// source scan that quietly matches nothing is worse than no guard, so a rename
// or reformat that defeats the parse fails here loudly instead of going green on
// an empty set.
//
// Live measurement of the rule, injected into the production DOM:
// `tools/ux1336-preshero-actions-wrap-6932.mjs` — escape 17px -> 0, head
// self-clip 17px -> 0, block height 28.5 -> 61px (it wrapped rather than
// shrank), and all four numbers unchanged at 1280px.
//
//   npx jest --testPathPatterns=politicsHeroActionsWrap6932

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

/* ═══ 0 · the two halves of the stylesheet ══════════════════════════════ */

const MOBILE_START = CSS.indexOf(MOBILE_BREAKPOINT);
if (MOBILE_START === -1) {
  throw new Error(
    `#6932 guard cannot find "${MOBILE_BREAKPOINT}" in politics.module.css. ` +
      `The phone layout lives only inside it — re-point this guard, do not delete it.`,
  );
}
const DESKTOP_CSS = CSS.slice(0, MOBILE_START);
const MOBILE_CSS = CSS.slice(MOBILE_START);

/** The declaration body of `.<cls>` within `where`, or null if it is not declared there. */
function ruleBody(where: string, cls: string): string | null {
  // Anchored on a selector boundary so `.presHero` cannot match `.presHeroActions`.
  const m = where.match(new RegExp(`(^|[\\s,{}])\\.${cls}\\s*(,[^{]*)?\\{([^}]*)\\}`, "m"));
  return m ? m[3] : null;
}

const declaresWrap = (body: string | null) =>
  body != null && /flex-wrap:\s*wrap/.test(body);

/* ═══ 1 · the control groups the markup actually renders ════════════════ */

/**
 * The text of one JSX element, opening line to its matching close by indent.
 */
function jsxBlock(openMatcher: RegExp, label: string): { lines: string[]; indent: number } {
  const lines = PAGE.split("\n");
  const openIdx = lines.findIndex((l) => openMatcher.test(l));
  if (openIdx === -1) {
    throw new Error(
      `#6932 guard cannot find ${label} (${openMatcher}) in app/politics/page.tsx. ` +
        `If it was renamed or moved, re-point this guard — do not delete it.`,
    );
  }
  const indent = lines[openIdx].search(/\S/);
  const out: string[] = [];
  for (let i = openIdx + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() && line.search(/\S/) <= indent) break; // its own closing tag
    out.push(line);
  }
  return { lines: out, indent };
}

/**
 * The root CSS class a locally-defined component renders, e.g.
 * `SourceToggle` -> `sourceToggle`. Without this the guard would only see
 * `<SourceToggle/>` and could not hold the component to the nowrap rule.
 */
function componentRootClass(name: string): string {
  const at = PAGE.indexOf(`function ${name}(`);
  if (at === -1) {
    throw new Error(
      `#6932 guard found <${name}/> inside the hero actions but no \`function ${name}(\` ` +
        `in app/politics/page.tsx. If the control moved to its own module, re-point this guard.`,
    );
  }
  const body = PAGE.slice(at);
  const m = body.match(/return\s*\(\s*\n\s*<\w+\s+className=\{s\.(\w+)\}/);
  if (!m) {
    throw new Error(
      `#6932 guard cannot read the root className of <${name}/>. A control group whose root ` +
        `class it cannot resolve is a control group it cannot hold to the nowrap rule.`,
    );
  }
  return m[1];
}

/** The root classes of the direct control groups inside `.presHeroActions`. */
const CONTROL_GROUPS: string[] = (() => {
  const { lines } = jsxBlock(
    /<div className=\{s\.presHeroActions\}>/,
    "the hero actions row",
  );

  // The groups sit at the shallowest indent that carries a className or a
  // component tag; everything deeper is a button inside one of them.
  const candidates = lines
    .map((l) => ({ indent: l.search(/\S/), text: l.trim() }))
    .filter((c) => /^<[A-Z]\w*[\s/>]/.test(c.text) || /^<\w+\s+className=\{s\.\w+\}/.test(c.text));

  if (candidates.length === 0) {
    throw new Error(
      `#6932 guard found no control groups inside .presHeroActions. The row is the subject ` +
        `of this guard; an empty parse is a broken parser, not an empty row.`,
    );
  }
  const top = Math.min(...candidates.map((c) => c.indent));

  const names = new Set<string>();
  for (const c of candidates.filter((c) => c.indent === top)) {
    const cls = c.text.match(/^<\w+\s+className=\{s\.(\w+)\}/);
    if (cls) {
      names.add(cls[1]);
      continue;
    }
    const comp = c.text.match(/^<([A-Z]\w*)/);
    if (comp) names.add(componentRootClass(comp[1]));
  }
  return [...names];
})();

describe("#6932 · the markup this guard is reasoning about", () => {
  test("the hero actions row holds the two segmented controls, resolved through the component", () => {
    // Asserted before anything is asserted ABOUT them: if this row is ever
    // emptied or restructured, the nowrap arm below would otherwise pass
    // vacuously over an empty list.
    expect(CONTROL_GROUPS).toEqual(
      expect.arrayContaining(["heroVariantToggle", "sourceToggle"]),
    );
    expect(CONTROL_GROUPS.length).toBeGreaterThanOrEqual(2);
  });

  test("every control group is a real, styled class in this stylesheet", () => {
    for (const g of CONTROL_GROUPS) {
      expect({ group: g, declared: ruleBody(CSS, g) !== null }).toEqual({
        group: g,
        declared: true,
      });
    }
  });
});

/* ═══ 2 · the container wraps at phone width ════════════════════════════ */

describe("#6932 · the control stack is allowed to wrap on a phone", () => {
  test("`.presHeroActions` declares flex-wrap:wrap inside the mobile block", () => {
    // THE REGRESSION ASSERTION. Absent this the block held its intrinsic ~335px
    // against a 318px interior and put an interactive control 17px outside the card.
    expect(declaresWrap(ruleBody(MOBILE_CSS, "presHeroActions"))).toBe(true);
  });

  test("`.presHeroHead` still wraps too — #4651, and half of why this fix works", () => {
    // The two rules are a pair: the head's wrap gives the block the card's full
    // interior, the block's wrap makes it use no more than that. Dropping either
    // brings back a defect, and they are one line apart in the same block.
    expect(declaresWrap(ruleBody(MOBILE_CSS, "presHeroHead"))).toBe(true);
  });

  test("neither wrap escapes to desktop, where the row is a right-aligned single line", () => {
    // The live control arm of the measurement (1280px unchanged) is only true
    // while these live inside the media query. A wrap hoisted to the base rule
    // would be inert *today* at 1280px and would silently change the layout the
    // first time a longer label appeared.
    expect(declaresWrap(ruleBody(DESKTOP_CSS, "presHeroActions"))).toBe(false);
    expect(declaresWrap(ruleBody(DESKTOP_CSS, "presHeroHead"))).toBe(false);
  });
});

/* ═══ 3 · the controls themselves do not ════════════════════════════════ */

describe("#6932 · a segmented control never breaks across lines", () => {
  test("no control group is given flex-wrap:wrap anywhere in the stylesheet", () => {
    // The most natural WRONG fix for this bug: push the wrap one level deeper,
    // where it fits the row by fragmenting a pill. `Polymarket` on a second line
    // inside the grey track is worse than `Polymarket` 15px outside the card.
    const wrapped = CONTROL_GROUPS.filter((g) => declaresWrap(ruleBody(CSS, g)));
    expect(wrapped).toEqual([]);
  });

  test("each control group is still a flex row — it is the flex that makes wrap meaningful", () => {
    // Pins the premise of the arm above. If a group stopped being a flex
    // container, `flex-wrap` would be inert on it and the nowrap assertion would
    // be true for a reason that has nothing to do with the layout it protects.
    for (const g of CONTROL_GROUPS) {
      expect({ group: g, flex: /display:\s*(inline-)?flex/.test(ruleBody(CSS, g) ?? "") }).toEqual({
        group: g,
        flex: true,
      });
    }
  });
});
