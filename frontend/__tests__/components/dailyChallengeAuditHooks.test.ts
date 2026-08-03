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
// Asserted at the source, like `calibrationAuditHooks.test.tsx` and
// `discoverAuditHooks.test.tsx`: both pages are large client components behind
// fetch/localStorage, and rendering them would prove less and break more.

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
