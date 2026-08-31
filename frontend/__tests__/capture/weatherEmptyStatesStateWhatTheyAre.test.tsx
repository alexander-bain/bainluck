/**
 * UX-P219 — THE WEATHER PAGE'S EMPTY SECTIONS STOP PROMISING AND START STATING.
 *
 * ═══ WHAT THIS IS ═══
 *
 * Ruling 142: *a section states what it IS, not what it WILL be.* Four shipped
 * empty states on `/weather` broke it in the same words, and they had broken it
 * long enough to be written down as debt:
 *
 *   frontend/__tests__/components/shippedCopyBans.test.ts
 *     const OWED = { …, "app/weather": ["appear-here"], … }
 *
 *   RainForecast    (daily)   "Daily “will it rain?” questions appear here when they reopen."
 *   RainForecast    (monthly) "Monthly city markets appear here when they reopen."
 *   ClimateDashboard          "Long-horizon climate markets appear here when they reopen."
 *   TemperatureMap            "Daily city markets appear here when they reopen."
 *
 * Each promises the reader a refill nobody has committed to. All 147 NYC daily
 * rain markets resolved on 2026-07-22 and have not reopened since; "when they
 * reopen" has been a thirteen-month-old IOU on 100% of loads.
 *
 * The fix says what the card is FOR instead — a fact that is true whether or not
 * anything ever reopens — and the debt entry is deleted, which is what turns the
 * bundle scan in `shippedCopyBans.test.ts` into a live gate for this surface: an
 * unlisted (surface, rule) pair with any hit fails from now on.
 *
 * ═══ WHY THIS FILE EXISTS ON TOP OF THAT ═══
 *
 * The bundle scan is an absence assertion over a whole route chunk. It cannot
 * fail when a sub-line is DELETED rather than rewritten — silence violates no
 * copy rule. So the class needs a per-SITE anchor as well, and this is it: each
 * of the four empty states is rendered from the shipped component and must emit
 * BOTH lines, with the description checked against the real rules rather than
 * against a literal somebody typed twice.
 *
 * Anchoring per site is deliberate. Asserting a phrase against the whole render
 * is an aggregate check: with four cards, three of them can regress while the
 * fourth keeps the assertion green (UX-P218's finding, generalised from
 * CERT-550). Every expectation below names one card.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherEmptyStatesStateWhatTheyAre
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { findBannedCopy, FUTURE_PROMISE_BANS } from "@/lib/copyBans";

/* ── SWR is the only thing between these components and their payloads ──── */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

/* eslint-disable @typescript-eslint/no-var-requires */
const RainForecast = require("@/components/weather/RainForecast").default;
const ClimateDashboard = require("@/components/weather/ClimateDashboard").default;
const TemperatureMap = require("@/components/weather/TemperatureMap").default;
/* eslint-enable @typescript-eslint/no-var-requires */

function render(Component: React.ComponentType, payload: unknown): string {
  swrPayload = payload;
  swrError = undefined;
  return renderToStaticMarkup(React.createElement(Component));
}

/**
 * Strip tags so assertions read what a PERSON reads, not what React emitted.
 *
 * The curly quotes are normalised as CHARACTERS, not as `&ldquo;` entities:
 * `renderToStaticMarkup` resolves a JSX `&ldquo;` to `“` before it ever reaches
 * a string, so an entity-keyed replacement is a no-op that silently leaves a
 * smart quote in the text an assertion is comparing against.
 */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const SKELETON = "animate-pulse";

/**
 * One row per empty state. `headline` proves the render reached THAT arm —
 * without it a component that silently fell through to a skeleton would satisfy
 * every copy assertion by rendering no copy at all.
 */
const SITES: {
  card: string;
  Component: React.ComponentType;
  payload: unknown;
  headline: string;
  description: string;
  retired: string;
}[] = [
  {
    card: "RainForecast · daily",
    Component: RainForecast,
    payload: { daily: [], monthly: [] },
    headline: "No live rain markets right now",
    description: 'This card tracks daily "will it rain?" questions.',
    retired: 'Daily "will it rain?" questions appear here when they reopen.',
  },
  {
    card: "RainForecast · monthly",
    Component: RainForecast,
    payload: { daily: [], monthly: [] },
    headline: "No live rainfall markets right now",
    description: "This card tracks monthly city rainfall markets.",
    retired: "Monthly city markets appear here when they reopen.",
  },
  {
    card: "ClimateDashboard",
    Component: ClimateDashboard,
    payload: [],
    headline: "No live climate markets right now",
    description: "This card tracks long-horizon climate markets.",
    retired: "Long-horizon climate markets appear here when they reopen.",
  },
  {
    card: "TemperatureMap",
    Component: TemperatureMap,
    payload: [],
    headline: "No live temperature markets right now",
    description: "This card tracks daily city temperature markets.",
    retired: "Daily city markets appear here when they reopen.",
  },
];

/* ═══════════════════════ the BEFORE was really broken ═══════════════════ */

describe("UX-P219 · the retired copy is copy the rules actually reject", () => {
  // A ruling-142 test that has never seen a ruling-142 violation is a test whose
  // regexes are wrong. Each retired sentence must be rejected, and rejected BY
  // the promise family — so a stray unrelated rule cannot carry this file.
  it.each(SITES.map((s) => [s.card, s.retired] as const))(
    "%s — the shipped-until-now sentence is rejected",
    (_card, retired) => {
      const hits = findBannedCopy(retired);
      expect(hits.length).toBeGreaterThan(0);
      const promiseIds = new Set(FUTURE_PROMISE_BANS.map((b) => b.id));
      expect(hits.some((h) => promiseIds.has(h.ban.id))).toBe(true);
    },
  );
});

/* ═══════════════════════ every site, one at a time ══════════════════════ */

describe.each(SITES.map((s) => [s.card, s] as const))(
  "UX-P219 · %s states what it is",
  (_card, site) => {
    it("reaches the loaded-and-empty arm rather than a skeleton", () => {
      const markup = render(site.Component, site.payload);
      // Both halves matter: the headline proves WHICH arm rendered, and the
      // absence of a pulse proves it is not still pretending to load (UX-P170).
      expect(visibleText(markup)).toContain(site.headline);
      expect(markup).not.toContain(SKELETON);
    });

    it("renders its description — deleting the line is a regression, not a fix", () => {
      const text = visibleText(render(site.Component, site.payload));
      expect(text).toContain(site.description);
    });

    it("no longer says what the section WILL hold", () => {
      const text = visibleText(render(site.Component, site.payload));
      expect(text).not.toContain("appear here");
    });

    it("its whole empty state makes no promise about the future", () => {
      // Ruling 142's family, applied to the text a reader sees — not to a
      // literal that could drift from the component. This is what makes the
      // file a class guard rather than a spelling of today's four sentences.
      //
      // Scoped to FUTURE_PROMISE_BANS on purpose. The full rule set also fires
      // on `meta="Polymarket & Kalshi"` in the section header and on the
      // `SourceBadge`, which ruling 141 AS AMENDED permits as attribution —
      // `shippedCopyBans.test.ts` classifies both through `isSourceAttribution`
      // rather than treating them as debt. Re-litigating a settled carve-out
      // here would make this file fail for a reason that is not its subject.
      const text = visibleText(render(site.Component, site.payload));
      const hits = findBannedCopy(text, FUTURE_PROMISE_BANS);
      expect(hits.map((h) => `${h.ban.id}: ${h.matched}`)).toEqual([]);
    });

    it("its description breaks no copy rule at all, not just ruling 142's", () => {
      // Legitimate to rule on the literal rather than the render: the test
      // above pins this exact string to what the component emits, so the two
      // cannot drift apart without that test failing first.
      const hits = findBannedCopy(site.description);
      expect(hits.map((h) => `${h.ban.id}: ${h.matched}`)).toEqual([]);
    });
  },
);

/* ═══════════════ the harness cannot quietly pass by rendering nothing ═══ */

describe("UX-P219 · the harness is not vacuous", () => {
  it("visibleText would surface a promise if one were rendered", () => {
    // The guard above is an absence assertion, and an absence assertion over a
    // stripper that eats too much is free. Prove the stripper preserves the
    // exact class of string it is being asked to rule out — including through
    // the smart quotes these cards actually render.
    const markup = '<p class="x">Daily &ldquo;city&rdquo; markets appear here when they reopen.</p>';
    expect(visibleText(markup)).toBe('Daily "city" markets appear here when they reopen.');
    expect(findBannedCopy(visibleText(markup), FUTURE_PROMISE_BANS).length).toBeGreaterThan(0);
  });

  it("every site is a distinct card, so no row is covering for another", () => {
    expect(new Set(SITES.map((s) => s.card)).size).toBe(SITES.length);
    expect(new Set(SITES.map((s) => s.description)).size).toBe(SITES.length);
    expect(new Set(SITES.map((s) => s.headline)).size).toBe(SITES.length);
  });
});
