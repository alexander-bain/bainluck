// L2-235 — the browser-audit rail's Daily / shared-challenge hooks.
//
// `e2e/specs/daily-challenge.spec.ts` binds to `data-testid` anchors rather
// than to copy, for the reason the Discover pack learned the hard way: the old
// smoke spec matched the empty state by the sentence "You're all caught up", so
// an editorial reword would have converted a PROVEN empty state into an
// unproven blank page.
//
// This suite is the tripwire in both directions:
//
//   1. Drop, rename or duplicate a hook in a page and CI fails HERE, in the
//      main frontend suite, rather than as a mystery red in a dispatched
//      browser run nobody is watching.
//   2. Reference a hook from the spec that no page renders and CI fails here
//      too. That is the L2-227 shape — coverage that exists on paper and
//      selects nothing.
//
// ─── WHY THIS IS ASSERTED AT THE SOURCE (measured, UX-P226) ───
//
// This file used to justify the source anchor by saying both pages "are large
// client components behind fetch/localStorage, and rendering them would prove
// less and break more" — the sentence `calibrationAuditHooks.test.tsx` and
// `discoverAuditHooks.test.tsx` also carry, and the one UX-P223 named as the
// origin of three straight cert blocks on movable source anchors. Half of it
// was never measured, and it is wrong:
//
//   - "break more" is FALSE. Both pages render fine on the existing
//     `renderToStaticMarkup` / node rail — 30ms and 7ms, no jsdom, behind the
//     module mocks every component suite here already uses.
//   - "prove less" is TRUE, and understates it: a static render proves NOTHING
//     for this suite. Both pages open on `useState(true)` that only a
//     `useEffect` clears, and effects do not run without a DOM, so the markup
//     is the spinner and nothing else — 262 bytes for Daily, 417 for the
//     challenge, carrying ZERO of the seven hooks below. Better mocks cannot
//     reach past a page-internal state gate, and jsdom is absent from
//     `node_modules` with the npm registry unreachable from the sandbox.
//
// The two directions above are also source questions by nature, not by
// convenience:
//
//   - direction 2 reads a Playwright spec. That is not a component; there is
//     nothing to render, at any point, under any harness.
//   - direction 1 asserts each hook is declared EXACTLY ONCE. That is a
//     deduplication property of the FILE, and a render is the wrong instrument
//     for it in principle: rendering shows you what the branch you took
//     contains, and can never show you the ABSENCE of a second declaration on
//     a branch you did not take.
//
// CERT-575 blocked an earlier draft of this header for adding a third reason
// that was simply false — that "no single render sees more than one" hook. It
// does. Read off the page structure (NOT off a render — see the loading gate
// above, which is why these sets cannot currently be observed):
//
//     Daily      loading   -> {}
//                empty     -> { daily-empty-state }
//                playing   -> { daily-page, daily-guess-higher, daily-guess-lower }
//                completed -> { daily-page, daily-share }
//     Challenge  loading   -> {}
//                error     -> { challenge-error }
//                loaded    -> { challenge-page }
//
// `daily-page` is on the <main> wrapper and `QuestionCard` / `SummaryCard`
// render inside it, so three hooks co-render in the playing state. What is
// true, and all the argument needs, is that no render carries all seven, and
// that the two directions above are not render questions to begin with.
//
// THE GAP THIS LEAVES, STATED: a hook that MIGRATES between branches — moved
// from the empty state into the main return, say — keeps its count of one and
// stays green here. That is the CERT-562 shape. This suite is the cheap
// tripwire for drop / rename / duplicate / orphan-selector; the browser rail
// driving a real page is what catches a hook on the wrong screen.

import * as fs from "fs";
import * as path from "path";

const FRONTEND = path.join(__dirname, "..", "..");

const read = (rel: string): string => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

const DAILY = "app/daily/page.tsx";
const CHALLENGE = "app/challenge/[id]/page.tsx";
const SPEC = "e2e/specs/daily-challenge.spec.ts";

const SOURCES: Record<string, string> = {
  [DAILY]: read(DAILY),
  [CHALLENGE]: read(CHALLENGE),
};

/** How many elements declare `hook` in `source`. */
function hookCount(source: string, hook: string): number {
  return source.split(`data-testid="${hook}"`).length - 1;
}

/** The hooks each page owns, and the attributes the rail reads off them. */
const OWNED: Array<{ file: string; hook: string; attributes?: string[] }> = [
  { file: DAILY, hook: "daily-page", attributes: ["data-daily-complete"] },
  { file: DAILY, hook: "daily-empty-state", attributes: ["data-empty-state-name"] },
  { file: DAILY, hook: "daily-guess-higher" },
  { file: DAILY, hook: "daily-guess-lower" },
  { file: DAILY, hook: "daily-share", attributes: ["data-share-copied"] },
  { file: CHALLENGE, hook: "challenge-page" },
  { file: CHALLENGE, hook: "challenge-error", attributes: ["data-error-state-name"] },
];

// NOT hooked: the challenge Share button. Phase 1 is anonymous-only, so there
// is no real challenge code to load and the button is behind the loaded state —
// an anchor no journey can select is dead instrumentation, and the last
// assertion in this file is what stopped it going in. It belongs with the
// seeded-state journey that can actually click it.

describe.each(OWNED)("$hook", ({ file, hook, attributes }) => {
  it(`is declared exactly once in ${file}`, () => {
    // Exactly once, not at-least-once: `.first()` on a duplicated hook silently
    // grades whichever copy happens to come first in the DOM.
    expect(hookCount(SOURCES[file], hook)).toBe(1);
  });

  it("is not declared in the other page", () => {
    const other = file === DAILY ? CHALLENGE : DAILY;
    expect(hookCount(SOURCES[other], hook)).toBe(0);
  });

  (attributes ?? []).forEach((attribute) => {
    it(`publishes ${attribute}`, () => {
      expect(SOURCES[file]).toContain(attribute);
    });
  });
});

describe("the spec and the pages agree", () => {
  const spec = read(SPEC);
  const declared = new Set(OWNED.map((o) => o.hook));

  it("every hook the spec selects is rendered by a page", () => {
    // Literal selectors only. A selector built from a variable
    // (`[data-testid="${hook}"]`) is covered by the opposite direction below,
    // which searches for the hook NAME rather than the selector.
    const selected = [...spec.matchAll(/data-testid="([^"${}]+)"/g)].map((m) => m[1]);

    expect(selected.length).toBeGreaterThan(0);
    const orphans = selected.filter(
      (hook) => hookCount(SOURCES[DAILY], hook) + hookCount(SOURCES[CHALLENGE], hook) === 0
    );
    expect(orphans).toEqual([]);
  });

  it("every hook this suite guards is actually used by the spec", () => {
    // A guarded hook nobody selects is dead instrumentation; it reads as
    // coverage in the page and buys nothing. Matched as a quoted name so a
    // hook the spec reaches through a variable still counts.
    const unused = [...declared].filter((hook) => !spec.includes(`"${hook}"`));
    expect(unused).toEqual([]);
  });

  it("the challenge loader keeps the aria-label the spec waits on", () => {
    // The loader renders before any page root exists, so its accessible name
    // is the only anchor for "the fetch never resolved".
    expect(SOURCES[CHALLENGE]).toContain('aria-label="Loading challenge"');
    expect(spec).toContain('getByLabel("Loading challenge")');
  });
});
