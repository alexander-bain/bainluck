// #7356 — THE LEAD CARD RESERVED 55px IT COULD NOT FILL, AND IT RESERVED IT IN
// THE MIDDLE.
//
// What a reader saw, `/entertainment` at 390px on production, 2026-09-19/20
// (latency/661 measured it twice, 70 minutes apart; ux/1375 reproduced it):
// the first card — "Oscar Winner: Best Picture" — had a finger's width of blank
// card between its title and its first outcome, with nothing in it. The card
// below it had no such gap, so it read as something failing to load rather than
// as spacing. 55px of a 280px card: 20% of the card, empty.
//
// ── THE MECHANISM, MEASURED AT THREE WIDTHS ─────────────────────────────────
//
// `tools/ent-hero-lead-fill-5953.mjs` against production, lead card:
//
//     1280px  card 421px  min-height 280  blank 196px   <- the GRID sets the height
//      800px  card 280px  min-height 280  blank  55px   <- MIN-HEIGHT sets the height
//      390px  card 280px  min-height 280  blank  55px   <- MIN-HEIGHT sets the height
//
// `.heroCardLead { min-height: 280px }` was INERT exactly where it was meant to
// work and was the WHOLE HEIGHT exactly where it hurt. Above 900px `.heroGrid`
// is a `min-height: 420px` two-row grid and the lead spans both rows, so the
// card is 421px and 280 can never bind — the 196px its `flex: 1` spacer holds
// there is the spacer doing its job, filling a row the grid sized. Below 900px
// the grid releases (`min-height: auto`, `auto` rows) and the lead sits alone in
// row 1, so `min-height` is the only thing setting the height and the spacer
// faithfully renders the entire surplus as one blank block.
//
// The fix is the removal of that one declaration. Before/after on byte-identical
// API JSON (`servedFromCache: 2, fetchedUpstream: 0`), same tool:
//
//      390px  280 -> 225px, blank 55 -> 0px
//      800px  280 -> 225px, blank 55 -> 0px
//     1280px  421 -> 421px, blank 196 -> 196px     <- THE CONTROL: desktop unmoved
//
// ── WHY THIS GUARD READS THE STYLESHEET ─────────────────────────────────────
//
// Every pixel of this defect is CSS. jsdom applies no media query and jest swaps
// the CSS Module for a proxy, so a render test sees `min-height` neither present
// nor absent — the defect renders as a pass at every width. The layout exists
// only in the stylesheet, so that is what is read. Precedent and shape:
// `politicsTrendNoteBreakpoint7250.test.ts`.
//
// ── WHAT IS PINNED, AND WHY THE DESKTOP FLOOR IS THE IMPORTANT HALF ─────────
//
// Removing the reservation is free at 1280px for one reason and one only: the
// GRID is still holding the lead card open there. That makes the grid floor
// newly load-bearing in a way it was not before — with `min-height: 280px` gone,
// deleting `.heroGrid { min-height: 420px }`, or its `1fr 1fr` rows, or
// `.heroLead { grid-row: 1 / -1 }`, collapses the desktop lead card to its
// content and quietly retires #5953's spacer. Nothing else in the repo would
// notice. So the floor is pinned here beside the removal it paid for.
//
// ── AMENDED BY #7382 (2026-10-22): THE DESKTOP FLOOR IS GONE ON PURPOSE ────────
//
// The floor pinned above held the lead open at 1280px, and what the lead could
// not fill there printed as one blank band: 98px for a six-rung field, 160 for
// four, 191 for three, 232 for a one-leg contract (local rig, retained
// payloads). #7382 replaces the topology rather than the floor: above 900px the
// grid is three equal columns with content-sized rows, and the lead spans two
// columns of the first row, so its card is as tall as its content (lead band 0px
// in all four, same rig). The CONTROL below now pins THAT shape: no grid height
// is reserved, no row is a fraction, the lead spans columns and not rows. The
// phone half of this file — no reservation on the card or below 900px — is
// unchanged. Design then selected top-aligned, content-height cards above 900px
// (uneven bottoms accepted): a second CONTROL pins `align-items: start` there
// and `stretch` in the narrow block (side bands 53/52/69/43px -> 0px, same rig).
//
// Every parser asserts what it FOUND before it asserts anything about it: a
// source-scanning guard that quietly matches nothing is worse than no guard.
//
//   npx jest --testPathPatterns=entertainmentLeadReservesNothingItCannotFill7356

import fs from "node:fs";
import path from "node:path";

const CSS_PATH = path.join(
  __dirname,
  "..",
  "app",
  "entertainment",
  "entertainment.module.css",
);
const CSS = fs.readFileSync(CSS_PATH, "utf8");

const RELEASE_BREAKPOINT = "@media (max-width: 900px)";

/* ═══ 0 · a rule reader that cannot silently match nothing ═══════════════════
   Comments are stripped FIRST. This fix's own explanation quotes the removed
   declaration (`min-height: 280px`) three times a few lines above the rule, so a
   scanner that read raw text would find `min-height` near `.heroCardLead` and
   pass on the comment that documents its absence. */

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

const BARE = stripComments(CSS);

/** The declaration body of `selector`, brace-matched, searched in `scope`. */
function ruleBody(selector: string, scope: string = BARE): string {
  // `\.heroCard\b` must not match `.heroCardLead`, and a selector may share a
  // rule with others (`.a, .b { }`), so match the selector as a whole token in
  // the prelude of the next `{`.
  const re = new RegExp(
    `(^|[},])\\s*([^{}]*?\\${selector}(?![\\w-])[^{}]*?)\\{`,
    "m",
  );
  const m = re.exec(scope);
  if (!m) {
    throw new Error(
      `#7356 guard: no rule for "${selector}" in entertainment.module.css. ` +
        `If the class was renamed, re-point this guard — do not delete it.`,
    );
  }
  const open = scope.indexOf("{", m.index + m[1].length);
  let depth = 0;
  for (let i = open; i < scope.length; i++) {
    if (scope[i] === "{") depth++;
    else if (scope[i] === "}" && --depth === 0) return scope.slice(open + 1, i);
  }
  throw new Error(`#7356 guard: unbalanced braces reading "${selector}"`);
}

/** The body of the `max-width: 900px` block, where the grid releases. */
function releaseBlock(): string {
  const at = BARE.indexOf(RELEASE_BREAKPOINT);
  if (at === -1) {
    throw new Error(
      `#7356 guard cannot find "${RELEASE_BREAKPOINT}" in entertainment.module.css. ` +
        `If the breakpoint moved, re-point this guard — do not delete it.`,
    );
  }
  const open = BARE.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < BARE.length; i++) {
    if (BARE[i] === "{") depth++;
    else if (BARE[i] === "}" && --depth === 0) return BARE.slice(open + 1, i);
  }
  throw new Error("#7356 guard: unbalanced braces reading the 900px block");
}

/** Every `min-height` value declared in `body`, in source order. */
function minHeights(body: string): string[] {
  return [...body.matchAll(/(?:^|;)\s*min-height\s*:\s*([^;}]+)/g)].map((m) =>
    m[1].trim(),
  );
}

describe("#7356 — the /entertainment lead card reserves nothing it cannot fill", () => {
  it("the reader itself is not vacuous", () => {
    // A brace-matcher that returned the whole file, or a selector regex that
    // matched a prefix, would make every assertion below pass against anything.
    const lead = ruleBody(".heroCardLead");
    const base = ruleBody(".heroCard");

    // `.heroCard` and `.heroCardLead` are DIFFERENT rules — the prefix trap.
    expect(lead).not.toBe(base);
    expect(base).toContain("flex-direction: column");
    expect(lead).toContain("composes: heroCard");

    // Brace matching stops at the rule's own close, not the file's.
    expect(lead).not.toContain("composes: card");
    expect(lead.length).toBeLessThan(200);

    // Comments really are gone: the fix's explanation names the removed
    // declaration, and the raw file therefore still contains the string.
    expect(CSS).toContain("min-height: 280px");
    expect(BARE).not.toContain("min-height: 280px");

    // And the value reader finds values where they exist — the release block's
    // grid declares one — and nothing where there is none.
    expect(minHeights(ruleBody(".heroGrid", releaseBlock()))).toEqual(["auto"]);
    expect(minHeights("gap: 4px; min-height: 7px")).toEqual(["7px"]);
    expect(minHeights("padding: 4px")).toEqual([]);
  });

  it("THE FIX: `.heroCardLead` declares no min-height", () => {
    const lead = ruleBody(".heroCardLead");
    expect(minHeights(lead)).toEqual([]);

    // It still IS the lead: the marks that make it read as one below 900px,
    // where the grid no longer gives it a bigger cell, are its padding and the
    // 72px cover / 18px title the page hands it.
    expect(lead).toContain("padding: 18px");
    expect(ruleBody(".heroCard")).toContain("padding: 14px");
  });

  it("nothing else re-reserves the lead card below 900px", () => {
    // The hole came back if ANY reservation survives where the grid has let go.
    const block = releaseBlock();
    expect(block).toContain(".heroGrid");
    expect(minHeights(ruleBody(".heroGrid", block))).toEqual(["auto"]);

    // `.heroCardLead` is not re-declared inside the release block at all; if a
    // future change adds it there, this reads its min-heights and finds none.
    const hasLeadRule = /(^|[},])\s*[^{}]*\.heroCardLead(?![\w-])[^{}]*\{/m.test(
      block,
    );
    if (hasLeadRule) expect(minHeights(ruleBody(".heroCardLead", block))).toEqual([]);

    // And the base rule it composes carries no floor either.
    expect(minHeights(ruleBody(".heroCard"))).toEqual([]);
    expect(minHeights(ruleBody(".card"))).toEqual([]);
  });

  it("THE CONTROL (#7382): the desktop lead is wide and content-sized, not held open", () => {
    // Above 900px: three equal columns, rows as tall as their content, the lead
    // across two columns of one row. Re-adding any of the old floor — a grid
    // min-height, fraction rows, or a lead spanning rows — brings back the band
    // the lead cannot fill, so each is refused here.
    const grid = ruleBody(".heroGrid");
    expect(grid).toContain("display: grid");
    expect(grid).toContain("grid-template-columns: repeat(3, minmax(0, 1fr))");
    expect(minHeights(grid)).toEqual([]);
    expect(grid).not.toMatch(/(?:^|;)\s*grid-template-rows\s*:/);
    expect(grid).not.toMatch(/(?:^|;)\s*grid-auto-rows\s*:[^;]*fr/);
    expect(grid).not.toMatch(/(?:^|;)\s*height\s*:/);
    // The `grid-template` / `grid` shorthands set rows too (lane1 L7 survivor).
    expect(grid).not.toMatch(/(?:^|;)\s*grid(?:-template)?\s*:/);

    const lead = ruleBody(".heroLead");
    expect(lead).toContain("grid-column: span 2");
    expect(lead).not.toMatch(/grid-row/);

    // The narrow block still owns the phone shape on its own terms.
    const block = releaseBlock();
    expect(ruleBody(".heroLead", block)).toContain("grid-column: span 2");
    expect(ruleBody(".heroLead", block)).toContain("grid-row: auto");
  });

  it("THE CONTROL (#7382, Design on bff73d37d1): desktop cards are top-aligned at their own height", () => {
    // A row is as tall as its tallest card. Stretched, each shorter card was
    // held open to that height and its `flex: 1` spacer printed the difference
    // as a band (53px beside a six-rung lead, 52-69px in a binary card, local
    // rig). Top-aligned, every card is its content and the spacer is 0px.
    const grid = ruleBody(".heroGrid");
    expect(grid).toMatch(/(?:^|;)\s*align-items\s*:\s*start\s*(?:;|$)/);
    expect(grid).not.toMatch(/(?:^|;)\s*place-items\s*:/);

    // No card re-stretches itself against the grid's choice.
    for (const sel of [".heroLead", ".heroCard", ".heroCardLead"]) {
      expect(ruleBody(sel)).not.toMatch(/(?:^|;)\s*(?:align|place)-self\s*:/);
    }

    // At <=900px the cards stretch as they always did, so the two-column
    // tablet rows and the phone column keep their card heights.
    const block = releaseBlock();
    expect(ruleBody(".heroGrid", block)).toMatch(
      /(?:^|;)\s*align-items\s*:\s*stretch\s*(?:;|$)/,
    );
  });
});
