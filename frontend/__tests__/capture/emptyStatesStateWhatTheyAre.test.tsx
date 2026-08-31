/**
 * UX-P220 — THE LAST OF RULING 142'S DEBT: EIGHT EMPTY STATES STOP PROMISING.
 *
 * ═══ WHAT THIS IS ═══
 *
 * Ruling 142: *a section states what it IS, not what it WILL be.* UX-P219 paid
 * `app/weather`'s share and, in the process, found why the rest had survived two
 * sweeps — a green capture was asserting a banned sentence VERBATIM, so the debt
 * list said "we owe a fix" while a test said "keep it exactly as it is".
 *
 * A census of the built bundle put the remainder at ten (surface, rule) hits
 * across six surfaces — but only EIGHT sentences, because three of them ship
 * into more than one chunk and one carries two rules at once:
 *
 *   EndOfFeedCard  "…so check back soon."            → app/search AND shared
 *   OddsChart      "…will update live once the       → shared, as BOTH
 *                   game starts"                        once-the AND will-populate
 *
 * That is why the OWED map made the debt look wider than it was, and why this
 * file is keyed on SITES rather than on surfaces.
 *
 * ═══ WHY THIS FILE EXISTS ON TOP OF THE BUNDLE SCAN ═══
 *
 * `shippedCopyBans.test.ts` now carries no ruling-142 entry at all, so any
 * promise on any surface is an unlisted (surface, rule) pair and fails against
 * the built artifact. That is the stronger half of the gate and it needs no
 * help here.
 *
 * What it cannot do is tell a REWRITE from a DELETION: silence violates no copy
 * rule, so ripping an empty state out entirely would turn the scan green and
 * leave a reader staring at a blank panel. This file is the presence half — one
 * anchor per site, never an aggregate over a whole page, because with eight
 * sites seven can regress while the eighth keeps a page-wide assertion green
 * (UX-P218's finding, generalised from CERT-550).
 *
 * ═══ WHY TWO KINDS OF ANCHOR, AND WHICH SITES GET WHICH ═══
 *
 * `EndOfFeedCard` and `OddsChart` are components and are RENDERED here, so the
 * assertion reads what a person reads.
 *
 * The six page sites are large client components behind SWR, auth and the
 * router. They are asserted against `renderableText` — the JSX CHILD text of the
 * file, with every attribute subtree, dead expression and comment excluded.
 *
 * 🔴 TWO CERTS BLOCKED THIS FILE'S ANCHORS, AND BOTH WERE RIGHT.
 *
 *   CERT-558  the anchor was `read(file).toContain(sentence)`, a raw substring
 *             scan. A mutation removed the visible `app/my-stuff` line and kept
 *             the string alive in a `data-cert-copy` ATTRIBUTE. Green.
 *   CERT-562  the anchor became whole-file `renderableText`. A mutation MOVED the
 *             sentence out of the authenticated no-content branch and into the
 *             SIGNED-OUT branch. Right file, wrong screen. Green.
 *
 * So the anchor is now `emptyStateText(file, name)`: the JSX child text of the ONE
 * element carrying `data-empty-state-name="<name>"`. That handle is not invented
 * here — it is the browser-audit rail's existing hook on `EndOfFeedCard`,
 * `app/daily` and `app/hub`; the other five sites now carry one too.
 *
 * Both attacks are replayed in the non-vacuity block below AND in
 * `artifacts-ux-p221/battery_ux159_repair.py` against the REAL page files, along
 * with `title`/`aria-label`/`alt`/`placeholder`, a dead `{false && "…"}`, a JSX
 * comment, a sibling-branch move, and dropping a site's scope altogether.
 *
 * This is still a source anchor, not a render: it reads what the file WOULD
 * render, not what a browser did. That is this repo's established treatment for
 * exactly this shape — see the header of
 * `__tests__/components/dailyChallengeAuditHooks.test.ts`: *"both pages are
 * large client components behind fetch/localStorage, and rendering them would
 * prove less and break more."* TWO of the six are ALSO rendered EMPTY, in the
 * captures that already own them, and those captures were repointed at the new
 * copy in this same change rather than left spelling the retired sentence:
 *
 *   app/categories  → categoryTagFilterCapture.test.tsx   (`SERVED_BEFORE`, total 0)
 *   app/playoffs    → playoffsEmptyGridCapture.test.tsx   (`SERVED_BEFORE`, teams 0)
 *                     playoffsWncaabCapture.test.tsx      (`columns: [] teams: 0`)
 *                     playoffsDegradedCapture.test.tsx    (asserts its ABSENCE)
 *
 * `app/hub`, `app/my-stuff` and the `ChallengeModal` in `app/discover` have
 * source anchors only, and are named here rather than left to be discovered.
 * `hubVocabularyCapture.test.tsx` does render the hub page, but only its
 * populated arms — there is no empty-hub fixture, so it is NOT a second anchor
 * for this site and is not counted as one.
 *
 * ═══ THE SOURCE SWEEP STRIPS COMMENTS FIRST, AND THAT IS NOT HOUSEKEEPING ═══
 *
 * Every one of these fixes carries a comment naming the retired sentence, and
 * two of those comments QUOTE the banned words — `"will appear"` in the
 * playoffs page, `"will update … once the game starts"` in `OddsChart`. Scanned
 * raw, this file would fail on its own rationale and the obvious repair would be
 * to delete the rationale. Strip first, then scan; and prove the stripper works,
 * because an absence assertion over a stripper that eats too much is free.
 *
 *   TZ=UTC npx jest --testPathPatterns=emptyStatesStateWhatTheyAre
 */

import fs from "node:fs";
import path from "node:path";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as ts from "typescript";

import { findBannedCopy, FUTURE_PROMISE_BANS } from "@/lib/copyBans";

const FRONTEND = path.join(__dirname, "..", "..");
const read = (rel: string): string => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

/**
 * The text a `.tsx` file actually RENDERS: JSX text children plus the values of
 * string/template literals that sit in child position, in source order.
 *
 * ═══ WHY THIS IS NOT `read(file).includes(sentence)` ═══
 *
 * CERT-558 blocked the first version of this file. Its presence anchors were raw
 * substring scans over the source, and an exact-head mutation removed the visible
 * `app/my-stuff` sentence, kept it alive in a `data-cert-copy` ATTRIBUTE, rebuilt,
 * and every guard here plus the built-bundle scan stayed green. A substring of a
 * source file is not a thing a reader can see.
 *
 * So this walks the TS/JSX AST and collects only what reaches the screen:
 *
 *   - attribute subtrees are skipped ENTIRELY — the exact mutation that blocked
 *     CERT-558, and any of its variants (`title=`, `aria-label=`, `alt=`);
 *   - a child expression contributes NOTHING unless it is a literal, so
 *     `{false && "…"}` and `{/* … *\/}` cannot satisfy a presence anchor either;
 *   - `{league.label}` therefore elides, which is why the two interpolated
 *     anchors below read as the reader reads them with the dynamic word removed.
 *
 * It is deliberately NOT a renderer. The six page sites are large client
 * components behind SWR, auth and the router (see this file's header); this is a
 * strictly stronger source anchor, not a substitute for rendering them.
 */
function renderableText(source: string): string {
  const sf = ts.createSourceFile(
    "site.tsx",
    source,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
  const parts: string[] = [];

  const literalValue = (node: ts.Node): string | null => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
    if (ts.isTemplateExpression(node)) {
      // Only the literal chunks render as fixed copy; the `${…}` holes are data.
      return [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join(" ");
    }
    return null;
  };

  const walk = (node: ts.Node): void => {
    if (ts.isJsxAttribute(node) || ts.isJsxAttributes(node)) return;
    if (ts.isJsxText(node)) {
      parts.push(node.text);
      return;
    }
    if (ts.isJsxExpression(node)) {
      const expr = node.expression;
      if (expr) {
        const direct = literalValue(expr);
        if (direct !== null) parts.push(direct);
        else if (ts.isConditionalExpression(expr)) {
          for (const branch of [expr.whenTrue, expr.whenFalse]) {
            const v = literalValue(branch);
            if (v !== null) parts.push(v);
          }
        }
        // Anything else contributes no COPY; recurse only for nested JSX.
        expr.forEachChild(walk);
      }
      return;
    }
    node.forEachChild(walk);
  };

  sf.forEachChild(walk);
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

/**
 * `renderableText`, but scoped to the ONE element tagged
 * `data-empty-state-name="<name>"` — its opening tag and its subtree, nothing else.
 *
 * ═══ WHY SCOPING, ON TOP OF `renderableText` ═══
 *
 * CERT-562 blocked the previous round. `renderableText` closed the attribute and
 * dead-expression attacks, but it still read the WHOLE FILE: a mutation deleted the
 * `app/my-stuff` sentence from the authenticated no-content branch and moved it into
 * the SIGNED-OUT branch, and the guard stayed green. Right file, wrong screen.
 *
 * `data-empty-state-name` is not invented for this — it is the browser-audit rail's
 * existing handle on `EndOfFeedCard`, `app/daily` and `app/hub`. The other five sites
 * now carry one too, so each anchor names the exact element whose emptiness it is
 * about, and moving copy to a sibling branch fails.
 *
 * Throws rather than returning "" when the name is absent: a scope that silently
 * matches nothing turns every presence assertion below into a free pass.
 */
function emptyStateText(source: string, name: string): string {
  const sf = ts.createSourceFile(
    "site.tsx",
    source,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );

  const tagged = (attrs: ts.JsxAttributes): boolean =>
    attrs.properties.some(
      (a) =>
        ts.isJsxAttribute(a) &&
        a.name.getText(sf) === "data-empty-state-name" &&
        a.initializer !== undefined &&
        ts.isStringLiteral(a.initializer) &&
        a.initializer.text === name,
    );

  let found: ts.Node | undefined;
  const search = (node: ts.Node): void => {
    if (found) return;
    if (ts.isJsxElement(node) && tagged(node.openingElement.attributes)) found = node;
    else if (ts.isJsxSelfClosingElement(node) && tagged(node.attributes)) found = node;
    else node.forEachChild(search);
  };
  sf.forEachChild(search);

  if (!found) {
    throw new Error(
      `no element carries data-empty-state-name="${name}" — the scope matched nothing, ` +
        `which would make every presence assertion for this site vacuous`,
    );
  }
  return renderableText(found.getText(sf));
}

/* ─────────────────────────── the eight sites ─────────────────────────────── */

/**
 * `states` is the sentence that must be present; `retired` is the sentence that
 * shipped until this change and must be gone. Both are required per row: the
 * absence alone is satisfied by deleting the empty state, and the presence alone
 * is satisfied by adding a second line under the promise.
 */
type Site = {
  site: string;
  file: string;
  /**
   * The `data-empty-state-name` on the element this row is about (CERT-562).
   * REQUIRED for the six page sites. Omitted for the two COMPONENT sites, which are
   * rendered outright further down — `OddsChart`'s pre-game arm is a fragment with no
   * taggable element, and adding a wrapper div to satisfy a test would change layout.
   */
  emptyState?: string;
  states: string;
  retired: string;
};

const SITES: Site[] = [
  {
    site: "app/categories · no items for this category",
    file: "app/categories/[slug]/page.tsx",
    emptyState: "category-no-items",
    // Anchors read as `renderableText` yields them: `{categoryName.toLowerCase()}`
    // is data, not copy, so it elides. The reader sees "…open football questions."
    states: "This page lists open questions.",
    retired: "Check back soon or browse other categories",
  },
  {
    site: "app/hub · no open markets for this competition",
    file: "app/hub/[competition]/page.tsx",
    emptyState: "entity-competition-present",
    states: "This page collects every open market for this competition.",
    retired: "No open markets right now. Check back when the next card is announced.",
  },
  {
    site: "app/my-stuff · nothing on for your teams",
    file: "app/my-stuff/page.tsx",
    emptyState: "my-stuff-no-teams",
    states: "This page follows the teams you have saved.",
    retired: "Check back when your teams are playing",
  },
  {
    site: "app/sports/[key] · no upcoming events",
    file: "app/sports/[key]/page.tsx",
    emptyState: "league-no-upcoming-events",
    states: "This page lists scheduled games for this league.",
    retired: "Check back later for more games",
  },
  {
    site: "app/playoffs · no championship odds",
    file: "app/playoffs/[sport]/page.tsx",
    emptyState: "playoffs-no-championship-odds",
    states: "This grid covers championship markets from sportsbooks and prediction markets.",
    retired: "Odds will appear when sportsbooks and prediction markets publish",
  },
  {
    site: "app/discover · ChallengeModal has no cards",
    file: "app/discover/page.tsx",
    emptyState: "challenge-no-cards",
    states: "The daily challenge draws its questions from the live feed.",
    retired: "Check back after the feed refreshes.",
  },
  {
    site: "components/discover/EndOfFeedCard · end of the Discover feed",
    file: "components/discover/EndOfFeedCard.tsx",
    // Case-stable across both arms: the count=0 arm now opens with a capital
    // (CERT-558's P3), so the shared anchor starts after the sentence opener.
    states: "every market in your feed right now.",
    retired: "new markets open throughout the day, so check back soon.",
  },
  {
    site: "components/OddsChart · pre-game, no history",
    file: "components/OddsChart.tsx",
    states: "This chart plots win probability minute by minute.",
    retired: "Win probability will update live once the game starts",
  },
];

/* ═══════════════════ the BEFORE really was a ruling-142 breach ══════════════ */

describe("UX-P220 · the retired copy is copy the rules actually reject", () => {
  // A ruling-142 sweep that has never seen a ruling-142 violation is a sweep
  // whose regexes are wrong. Each retired sentence must be rejected, and
  // rejected BY the promise family, so no unrelated rule can carry this file.
  it.each(SITES.map((s) => [s.site, s.retired] as const))(
    "%s — the sentence that shipped until now is rejected",
    (_site, retired) => {
      const hits = findBannedCopy(retired);
      expect(hits.length).toBeGreaterThan(0);
      const promiseIds = new Set(FUTURE_PROMISE_BANS.map((b) => b.id));
      expect(hits.some((h) => promiseIds.has(h.ban.id))).toBe(true);
    },
  );

  it("the replacements are clean against EVERY rule, not just ruling 142's", () => {
    // Ruling 138's `price` family and ruling 141's venue names are live on these
    // surfaces too. A fix that trades one banned sentence for another is not a
    // fix, and `app/categories`/`app/sports` carry no `price-family` exemption.
    const dirty = SITES.map((s) => ({ site: s.site, hits: findBannedCopy(s.states) })).filter(
      (r) => r.hits.length > 0,
    );
    expect(dirty.map((r) => `${r.site}: ${r.hits.map((h) => h.ban.id).join(",")}`)).toEqual([]);
  });
});

/* ════════════ the extractor, proven against CERT-558's own mutation ════════ */

describe("renderableText — non-vacuity, both directions", () => {
  const SENTENCE = "This page follows the teams you have saved.";

  it("captures a sentence that is a JSX text child", () => {
    expect(renderableText(`const A = () => <p>${SENTENCE}</p>;`)).toContain(SENTENCE);
  });

  it("CERT-558's mutation: a sentence kept only in an attribute does NOT count", () => {
    // This is the exact shape that blocked the first version of this file — the
    // visible line removed, the string preserved in `data-cert-copy`.
    const mutated = `const A = () => <p data-cert-copy="${SENTENCE}"></p>;`;
    expect(mutated).toContain(SENTENCE); // the raw scan is still satisfied …
    expect(renderableText(mutated)).not.toContain(SENTENCE); // … this one is not.
  });

  it("the same, for the attributes a mutation would reach for next", () => {
    for (const attr of ["title", "aria-label", "alt", "placeholder"]) {
      const mutated = `const A = () => <p ${attr}="${SENTENCE}">x</p>;`;
      expect(renderableText(mutated)).not.toContain(SENTENCE);
    }
  });

  it("a sentence in a dead expression does NOT count", () => {
    const dead = `const A = () => <p>{false && "${SENTENCE}"}</p>;`;
    expect(renderableText(dead)).not.toContain(SENTENCE);
  });

  it("a sentence in a JSX comment does NOT count", () => {
    const commented = `const A = () => <p>{/* ${SENTENCE} */}</p>;`;
    expect(renderableText(commented)).not.toContain(SENTENCE);
  });

  it("a literal child DOES count — it is copy that renders", () => {
    expect(renderableText(`const A = () => <p>{"${SENTENCE}"}</p>;`)).toContain(SENTENCE);
  });

  it("both arms of a conditional child count", () => {
    const both = `const A = ({n}) => <p>{n > 0 ? "left copy" : "right copy"}</p>;`;
    const text = renderableText(both);
    expect(text).toContain("left copy");
    expect(text).toContain("right copy");
  });

  it("JSX nested inside an expression is still reached", () => {
    const nested = `const A = ({xs}) => <ul>{xs.map((x) => <li key={x}>${SENTENCE}</li>)}</ul>;`;
    expect(renderableText(nested)).toContain(SENTENCE);
  });

  it("CERT-562's mutation: the sentence moved to a SIBLING branch does NOT count", () => {
    // The exact shape that blocked round 2 — right file, wrong screen.
    const moved = `const A = ({signedIn}) => signedIn
      ? <div data-empty-state-name="s"><p>nothing here yet</p></div>
      : <div><p>${SENTENCE}</p></div>;`;
    expect(renderableText(moved)).toContain(SENTENCE); // whole-file scan: satisfied
    expect(emptyStateText(moved, "s")).not.toContain(SENTENCE); // scoped: not.
  });

  it("the scoped extractor DOES see copy inside its own element", () => {
    const inside = `const A = () => <div data-empty-state-name="s"><p>${SENTENCE}</p></div>;`;
    expect(emptyStateText(inside, "s")).toContain(SENTENCE);
  });

  it("a scope that matches nothing THROWS rather than passing vacuously", () => {
    const none = `const A = () => <div><p>${SENTENCE}</p></div>;`;
    expect(() => emptyStateText(none, "s")).toThrow(/matched nothing/);
  });

  it("the scope does not leak into a sibling that shares the parent", () => {
    const siblings = `const A = () => <section>
      <div data-empty-state-name="s"><p>mine</p></div>
      <div><p>${SENTENCE}</p></div>
    </section>;`;
    const text = emptyStateText(siblings, "s");
    expect(text).toContain("mine");
    expect(text).not.toContain(SENTENCE);
  });

  it("does not swallow the file — sibling copy survives beside a skipped attribute", () => {
    // A stripper that eats too much makes every absence assertion above free.
    const mixed = `const A = () => <p title="hidden words">visible words</p>;`;
    const text = renderableText(mixed);
    expect(text).toContain("visible words");
    expect(text).not.toContain("hidden words");
  });
});

/* ═══════════════════════ every site, one at a time ═════════════════════════ */

describe.each(SITES.map((s) => [s.site, s] as const))("UX-P220 · %s", (_site, site) => {
  it("states what it is, inside ITS OWN empty state — not merely in the file", () => {
    // CERT-558: `read(file).toContain(states)` was satisfied by a `data-cert-copy`
    // attribute.  CERT-562: whole-file `renderableText` was satisfied by moving the
    // sentence into a sibling JSX branch.  The scope is now the element itself.
    const text = site.emptyState
      ? emptyStateText(read(site.file), site.emptyState)
      : renderableText(read(site.file));
    expect(text).toContain(site.states);
  });

  it("no longer promises what it will be — anywhere in the file", () => {
    // Absence stays on the RAW source deliberately: a retired promise left in an
    // attribute or a comment is still a promise someone will re-render later.
    expect(read(site.file)).not.toContain(site.retired);
  });
});

describe("every PAGE site is scoped — the escape hatch is closed", () => {
  // `emptyState` is optional only so the two rendered COMPONENT sites can opt out.
  // Without this row, dropping a page's `emptyState` would silently downgrade it to
  // the whole-file scan CERT-562 blocked — the cheapest way to make a failure go away.
  const PAGE_SITES = SITES.filter((s) => s.file.startsWith("app/"));

  it("all six page sites are present and carry a scope", () => {
    expect(PAGE_SITES).toHaveLength(6);
    expect(PAGE_SITES.filter((s) => !s.emptyState).map((s) => s.site)).toEqual([]);
  });

  it("only the two rendered component sites may opt out", () => {
    expect(SITES.filter((s) => !s.emptyState).map((s) => s.file)).toEqual([
      "components/discover/EndOfFeedCard.tsx",
      "components/OddsChart.tsx",
    ]);
  });
});

/* ══════════════════ the two component sites, actually rendered ═════════════ */

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    // Normalised as CHARACTERS, not as `&ldquo;` entities: `renderToStaticMarkup`
    // resolves a JSX entity before it ever reaches a string, so an entity-keyed
    // replacement is a no-op that leaves a smart quote in the compared text
    // (UX-P219's finding).
    .replace(/[“”]/g, '"')
    .replace(/[’]/g, "'")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

jest.mock("@/lib/analytics", () => ({ trackEvent: jest.fn() }));

/* eslint-disable @typescript-eslint/no-var-requires */
const EndOfFeedCard = require("@/components/discover/EndOfFeedCard").default;
/* eslint-enable @typescript-eslint/no-var-requires */

describe("UX-P220 · EndOfFeedCard, rendered", () => {
  const site = SITES.find((s) => s.file.endsWith("EndOfFeedCard.tsx")) as Site;

  const rendered = (count: number): string =>
    visibleText(
      renderToStaticMarkup(React.createElement(EndOfFeedCard, { count, onRefresh: () => {} })),
    );

  // Both counts: the "end of feed" and "no markets at all" arms are separate
  // sentences, and only one of them carries the count prefix.
  it.each([137, 0])("count=%i — the reader is told what the feed holds", (count) => {
    const text = rendered(count);
    expect(text).toContain("You're all caught up");
    expect(text).toContain(site.states);
    expect(findBannedCopy(text, FUTURE_PROMISE_BANS).map((h) => h.matched)).toEqual([]);
  });

  it("count>0 keeps the count prefix", () => {
    expect(rendered(137)).toContain("137 markets explored — that is every market");
  });

  it("count=0 opens the sentence with a capital (CERT-558 P3)", () => {
    const text = rendered(0);
    expect(text).toContain("That is every market in your feed right now.");
    expect(text).not.toContain("up that is every market");
  });

  it("the refresh affordance the promise stood in for is still there", () => {
    // "check back soon" was doing the work of "there is a way to get more".
    // Removing the sentence is only honest while the button remains.
    const markup = renderToStaticMarkup(
      React.createElement(EndOfFeedCard, { count: 5, onRefresh: () => {} }),
    );
    expect(visibleText(markup)).toContain("Refresh feed");
    expect(markup).toContain('data-empty-state-name="end-of-feed"');
  });
});

/* ══════════════ the source sweep — comments stripped, then scanned ═════════ */

/**
 * Remove `//` lines, `/* *\/` blocks and JSX `{/* *\/}` comments.
 *
 * Deliberately not a parser. It runs over eight files this repo controls, and
 * the row below proves on a fixture that it removes a comment and keeps the JSX
 * text beside it — which is the only property the sweep depends on.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^[ \t]*\/\/.*$/gm, " ");
}

describe("UX-P220 · no promise survives anywhere in these eight files", () => {
  it.each(SITES.map((s) => [s.site, s.file] as const))(
    "%s — the file's own text makes no ruling-142 promise",
    (_site, file) => {
      // The per-site rows above name ONE retired sentence each. This is the
      // class check: a second promise elsewhere in the same file, or one added
      // later, fails here without anybody having to list it.
      const hits = findBannedCopy(stripComments(read(file)), FUTURE_PROMISE_BANS);
      expect(hits.map((h) => `${h.ban.id}: ${h.matched}`)).toEqual([]);
    },
  );
});

/* ═══════════ the harness cannot quietly pass by looking at nothing ═════════ */

describe("UX-P220 · the harness is not vacuous", () => {
  it("stripComments removes a comment and keeps the JSX text beside it", () => {
    // Both directions. If it kept comments, the two rationale comments in this
    // change would redden the sweep; if it ate JSX text, the sweep would pass
    // over a real promise. The fixture carries one of each.
    const fixture = [
      "// Ruling 142: this said it will appear once the game starts.",
      "{/* and so did this: markets will populate here */}",
      "<p>Check back soon</p>",
    ].join("\n");
    const stripped = stripComments(fixture);

    expect(stripped).not.toContain("will appear");
    expect(stripped).not.toContain("will populate");
    expect(stripped).toContain("Check back soon");
    expect(findBannedCopy(stripped, FUTURE_PROMISE_BANS).length).toBe(1);
  });

  it("the sweep really is reading the shipped files", () => {
    // `read` throwing would fail every row above for the right reason, but a
    // path typo that resolved to an EMPTY file would pass them all silently.
    for (const s of SITES) expect(read(s.file).length).toBeGreaterThan(500);
  });

  it("every row is a distinct site, so none is covering for another", () => {
    expect(new Set(SITES.map((s) => s.site)).size).toBe(SITES.length);
    expect(new Set(SITES.map((s) => s.states)).size).toBe(SITES.length);
    expect(new Set(SITES.map((s) => s.retired)).size).toBe(SITES.length);
  });
});
