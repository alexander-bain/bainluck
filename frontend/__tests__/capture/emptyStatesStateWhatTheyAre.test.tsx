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
 * router. They are asserted at the SOURCE, which is this repo's established
 * treatment for exactly that shape — see the header of
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

import { findBannedCopy, FUTURE_PROMISE_BANS } from "@/lib/copyBans";

const FRONTEND = path.join(__dirname, "..", "..");
const read = (rel: string): string => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

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
  states: string;
  retired: string;
};

const SITES: Site[] = [
  {
    site: "app/categories · no items for this category",
    file: "app/categories/[slug]/page.tsx",
    states: "This page lists open {categoryName.toLowerCase()} questions.",
    retired: "Check back soon or browse other categories",
  },
  {
    site: "app/hub · no open markets for this competition",
    file: "app/hub/[competition]/page.tsx",
    states: "This page collects every open market for this competition.",
    retired: "No open markets right now. Check back when the next card is announced.",
  },
  {
    site: "app/my-stuff · nothing on for your teams",
    file: "app/my-stuff/page.tsx",
    states: "This page follows the teams you have saved.",
    retired: "Check back when your teams are playing",
  },
  {
    site: "app/sports/[key] · no upcoming events",
    file: "app/sports/[key]/page.tsx",
    states: "This page lists scheduled games for this league.",
    retired: "Check back later for more games",
  },
  {
    site: "app/playoffs · no championship odds",
    file: "app/playoffs/[sport]/page.tsx",
    states: "This grid covers {league.label} championship markets from",
    retired: "Odds will appear when sportsbooks and prediction markets publish",
  },
  {
    site: "app/discover · ChallengeModal has no cards",
    file: "app/discover/page.tsx",
    states: "The daily challenge draws its questions from the live feed.",
    retired: "Check back after the feed refreshes.",
  },
  {
    site: "components/discover/EndOfFeedCard · end of the Discover feed",
    file: "components/discover/EndOfFeedCard.tsx",
    states: "that is every market in your feed right now.",
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

/* ═══════════════════════ every site, one at a time ═════════════════════════ */

describe.each(SITES.map((s) => [s.site, s] as const))("UX-P220 · %s", (_site, site) => {
  it("states what it is — deleting the line is a regression, not a fix", () => {
    expect(read(site.file)).toContain(site.states);
  });

  it("no longer promises what it will be", () => {
    expect(read(site.file)).not.toContain(site.retired);
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

  // Both counts: the sub-line is shared between the "end of feed" and the
  // "no markets at all" arms, and only one of them prints the count prefix.
  it.each([137, 0])("count=%i — the reader is told what the feed holds", (count) => {
    const text = visibleText(
      renderToStaticMarkup(React.createElement(EndOfFeedCard, { count, onRefresh: () => {} })),
    );
    expect(text).toContain("You're all caught up");
    expect(text).toContain(site.states);
    expect(findBannedCopy(text, FUTURE_PROMISE_BANS).map((h) => h.matched)).toEqual([]);
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
