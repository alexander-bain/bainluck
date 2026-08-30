/**
 * UX-P194 — THE CROSS-SOURCE CARD REACHES THE OTHER TWO CATEGORY PAGES.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/politics` ends on "⇄ Cross-source spotlight · Markets where sources
 * disagree". `/economics` and `/entertainment` build the IDENTICAL payload,
 * off the IDENTICAL shared `find_cross_source_markets`, with their own
 * `_cross_source_row_fn` — and then throw it away. Read live 2026-08-30:
 *
 *     /api/politics        cross_source: 8 rows   → rendered
 *     /api/economics       cross_source: 8 rows   → nothing renders it
 *     /api/entertainment   cross_source: 8 rows   → nothing renders it
 *     /api/weather/cross-source: []               → genuinely empty, not hidden
 *
 * The mechanism was not forgetfulness at the render site. `EconData` and
 * `EntertainmentData` never DECLARED `cross_source`, so the field could not
 * reach a page even in principle: the server sent it and TypeScript dropped it
 * on the floor. Two server-side computations per precompute, discarded.
 *
 * ═══ WHY IT IS WORTH RENDERING NOW AND WAS NOT BEFORE ═══
 *
 * Before UX-P187 this payload was mostly false. Re-running that queue's real
 * `align_on_shared_outcome` over all 24 served rows (banked fixture):
 *
 *              served   survive alignment
 *   politics        8                   1
 *   economics       8                   2
 *   entertainment   8                   2
 *              ────────────────────────────
 *              24                   5
 *
 * 21 of 24 were two sources pricing DIFFERENT outcomes — "Top US Netflix Show
 * this week?" as Kalshi 96.5% against Polymarket 22.5% is two different shows,
 * not a 74-point disagreement. Wiring the card before UX-P187 would have
 * shipped that to two more surfaces. Wiring it after ships the 2-and-2 that
 * are real — including "Top US Netflix Show this week?" resurfacing honestly
 * as *Beauty in Black: Season 3*, 2.5% against 22.5%, a genuine gap the broken
 * ranking had buried under its own artifact.
 *
 * ═══ WHAT THESE TESTS DO ═══
 *
 * Every render arm drives the SHIPPED `CrossSourceSpotlight` and reads the
 * text a PERSON sees. The two source-level arms are narrow positive assertions
 * on the call site, because a component guard stays green when someone deletes
 * the CALL — they are a companion to the render arms, never a substitute.
 *
 *   npx jest --testPathPatterns=categoryCrossSourceWiring
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { CrossSourceMatch } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-var-requires */
const {
  CrossSourceSpotlight,
  CROSS_SOURCE_BORDER_COLOR,
} = require("@/components/crossSource/CrossSourceSpotlight");
/* eslint-enable @typescript-eslint/no-var-requires */

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");

const banked = JSON.parse(
  fs.readFileSync(
    path.join(
      REPO,
      "backend",
      "tests",
      "fixtures",
      "uxp194_category_cross_source.json",
    ),
    "utf8",
  ),
);

type BankedRow = CrossSourceMatch & {
  _aligned: { outcome: string; kalshi: number; poly: number; delta: number } | null;
};
type BankedPage = {
  served: number;
  aligned: number;
  rows: BankedRow[];
  declared_in_frontend_type: boolean;
  rendered_by_page: boolean;
};

const PAGES = banked.pages as Record<string, BankedPage>;

/** The rows that survive UX-P187's alignment, rebuilt into what the route now
 *  serves: the aligned outcome, and the two numbers that price THAT outcome. */
function alignedMatches(page: string): CrossSourceMatch[] {
  return PAGES[page].rows
    .filter((r) => r._aligned)
    .map((r) => ({
      ...r,
      outcome: r._aligned!.outcome,
      kalshi: r._aligned!.kalshi,
      poly: r._aligned!.poly,
      delta: r._aligned!.delta,
    }));
}

function render(matches: CrossSourceMatch[]): string {
  return renderToStaticMarkup(
    React.createElement(CrossSourceSpotlight, { matches }),
  );
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(m: string): string {
  return m
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

/* ═══ 1 · the fixture really is the gap ════════════════════════════════ */

describe("UX-P194 · the payload was served and discarded", () => {
  test("all three routes serve a full eight rows", () => {
    for (const page of ["politics", "economics", "entertainment"]) {
      expect(PAGES[page].served).toBe(8);
    }
  });

  test("only /politics had ever declared the field, let alone rendered it", () => {
    expect(PAGES.politics.declared_in_frontend_type).toBe(true);
    expect(PAGES.economics.declared_in_frontend_type).toBe(false);
    expect(PAGES.entertainment.declared_in_frontend_type).toBe(false);
  });

  test("the banked alignment counts are the ones the docstring quotes", () => {
    expect(PAGES.politics.aligned).toBe(1);
    expect(PAGES.economics.aligned).toBe(2);
    expect(PAGES.entertainment.aligned).toBe(2);
    const served = Object.values(PAGES).reduce((n, p) => n + p.served, 0);
    const aligned = Object.values(PAGES).reduce((n, p) => n + p.aligned, 0);
    expect([served, aligned]).toEqual([24, 5]);
  });

  test("the two new pages are non-empty after alignment — the ship is not a no-op", () => {
    // If alignment had emptied them, wiring the card would render a header
    // over nothing on both pages. It does not: this is the floor, and the
    // real section can only be larger (pairs below the old top-8 cut surface
    // once the artifacts stop occupying it).
    expect(alignedMatches("economics").length).toBeGreaterThan(0);
    expect(alignedMatches("entertainment").length).toBeGreaterThan(0);
  });
});

/* ═══ 2 · what a reader on the two new pages actually sees ═════════════ */

describe.each([
  ["economics", "Goldman Sachs", "Which bank will lead Anthropic's IPO?"],
  ["entertainment", "Beauty in Black: Season 3", "Top US Netflix Show this week?"],
])("UX-P194 · /%s renders the card", (page, outcome, question) => {
  const matches = alignedMatches(page);
  const text = visibleText(render(matches));

  test("the section header is there", () => {
    expect(text).toContain("Cross-source spotlight");
    expect(text).toContain("Markets where sources disagree");
  });

  test("the question a reader recognises is on the page", () => {
    expect(text).toContain(question);
  });

  test("...and so is the ONE outcome both numbers price", () => {
    // The load-bearing word on a comparison surface (UX-P187). Without it
    // "Kalshi 2.5% / Polymarket 22.5%" does not say what either side is
    // 2.5% ABOUT.
    expect(text).toContain(outcome);
  });

  test("both sources are named beside their numbers", () => {
    expect(text).toContain("Kalshi");
    expect(text).toContain("Polymarket");
    const row = matches.find((m) => m.q === question)!;
    // Printed through the site's single home for percentages (UX-P191), so
    // whole numbers print whole — not `2.5%` becoming `2.50%`, not `49%`
    // becoming `49.0%`.
    expect(text).toContain(`${Math.round(row.kalshi)}%`);
  });

  test("the spread is reported", () => {
    expect(text).toMatch(/Disagree by \d+pp|Merged: \d+%/);
  });
});

/* ═══ 3 · the palette actually covers the new vocabularies ═════════════ */

describe("UX-P194 · the accent is not silently grey on the new pages", () => {
  const GREY = "#9CA3AF";

  test("every category the two new pages actually served has its own accent", () => {
    const seen = new Set<string>();
    for (const page of ["economics", "entertainment"]) {
      for (const r of PAGES[page].rows) seen.add(r.category);
    }
    // `other` is a real category and legitimately draws the grey.
    const named = [...seen].filter((c) => c && c !== "other");
    expect(named.length).toBeGreaterThan(0);
    for (const c of named) {
      expect(CROSS_SOURCE_BORDER_COLOR[c]).toBeDefined();
      expect(CROSS_SOURCE_BORDER_COLOR[c]).not.toBe(GREY);
    }
  });

  test("politics' own accents are unchanged by the move", () => {
    // The map absorbed `components/politics/atoms.tsx`'s BORDER_COLOR. If a
    // key drifted, /politics would silently recolour.
    expect(CROSS_SOURCE_BORDER_COLOR).toMatchObject({
      presidential: "#3B82F6",
      congressional: "#8B5CF6",
      gubernatorial: "#10B981",
      policy: "#F59E0B",
      scotus: "#EF4444",
      international: "#0EA5E9",
      other: "#9CA3AF",
    });
  });

  test("an unknown category degrades to a plain card, never to an absent one", () => {
    const rogue: CrossSourceMatch = {
      ...alignedMatches("economics")[0],
      category: "a-theme-invented-next-quarter",
    };
    const text = visibleText(render([rogue]));
    expect(text).toContain("Cross-source spotlight");
    expect(text).toContain(rogue.q);
  });
});

/* ═══ 4 · vacuity — no header over no cards ════════════════════════════ */

describe("UX-P194 · the section self-gates", () => {
  test("an empty list renders NOTHING, not an empty section", () => {
    // Both new call sites pass `data.cross_source ?? []`. A precompute served
    // before this deploy has no such key, and /weather's equivalent is
    // genuinely `[]` — measured, not assumed. Neither may draw a header.
    expect(render([])).toBe("");
  });

  test("the assertions above would notice an empty render", () => {
    // Vacuity companion: prove `toContain` on the real payload is not passing
    // against a component that renders nothing at all.
    expect(render(alignedMatches("economics"))).not.toBe("");
    expect(render(alignedMatches("entertainment"))).not.toBe("");
  });
});

/* ═══ 5 · the call sites exist ═════════════════════════════════════════ */

describe.each([
  ["economics", "app/economics/page.tsx"],
  ["entertainment", "app/entertainment/page.tsx"],
])("UX-P194 · /%s mounts it", (_page, rel) => {
  const src = fs.readFileSync(path.join(FRONTEND, rel), "utf8");

  test("the page imports the shared component", () => {
    expect(src).toContain(
      'from "@/components/crossSource/CrossSourceSpotlight"',
    );
  });

  test("...and mounts it against the payload's cross_source", () => {
    expect(src).toMatch(
      /<CrossSourceSpotlight\s+matches=\{data\.cross_source \?\? \[\]\}\s*\/>/,
    );
  });
});
