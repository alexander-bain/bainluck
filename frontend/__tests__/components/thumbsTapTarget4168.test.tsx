// #4168 — A CARD'S 👍 AND 👎 ARE EACH A TARGET A THUMB CAN HIT.
//
// Production `/sports`, 390×844, 2026-09-25 19:4xZ (ux, `artifacts/ux-4168/taps-BEFORE-prod.json`),
// every live card measured the same pair:
//
//   More like this  x=323 w=20 h=20   ·   Less like this  x=345 w=20 h=20   → 2px apart
//
// Two OPPOSITE personalization signals, each under WCAG 2.5.8's 24px floor, 2px apart. A tap aimed
// at 👍 that lands 3px right sends 👎, and the feed is mistrained for the reader who tapped it.
//
// ## Why this file reads CLASSES
//
// jsdom has no layout engine, so a rendered box cannot be measured here; the bounding-box probe
// against a built page is quoted in the PR. What CI can hold is the arithmetic the probe proved:
// target edge = glyph width + 2 × padding. Tailwind's `p-N` is N × 4px, so `p-1` on the 12px glyph
// is the 20px that was measured, and `p-1.5` is 24.
//
// ThumbButtons is one component shared by the event, futures and bundle cards; the event card is
// rendered here on BOTH of its rows (the footer beside `Opened X/Y`, and the thumbs-only row), so
// a call site that wrapped the buttons in something narrower would show up as a missing button.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

const WCAG_258_MIN_PX = 24;

// The production specimen's shape: Cubs @ Red Sox, Top 9th, 3–4, "Opened 53/47".
function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15318001,
    external_id: "evt-15318001",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Boston Red Sox",
    away_team: "Chicago Cubs",
    commence_time: "2026-09-25T17:10:00.000Z",
    status: "live",
    home_score: 4,
    away_score: 3,
    opening_odds: { away_probability: 0.53, home_probability: 0.47 },
    ...over,
  } as unknown as FeedEventData;
}

function render(data: FeedEventData, reason: string): string {
  const item = { type: "event", score: 50, reason, headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FeedCard item={item} category="baseball" onThumbsUp={() => {}} onThumbsDown={() => {}} />,
  );
}

interface Thumb {
  label: string;
  classes: string[];
  glyphPx: number;
}

/** Every thumb button on the card with its classes and its glyph's drawn width. */
function thumbs(html: string): Thumb[] {
  const out: Thumb[] = [];
  const re = /<button class="([^"]*)" title="[^"]*" aria-label="(More like this|Less like this)"><svg width="(\d+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) out.push({ classes: m[1].split(/\s+/), label: m[2], glyphPx: Number(m[3]) });
  return out;
}

/** Tailwind uniform padding in px (`p-1.5` → 6); 0 when the button carries none. */
function paddingPx(classes: string[]): number {
  const p = classes.map((c) => /^p-(\d+(?:\.5)?)$/.exec(c)).find(Boolean);
  return p ? Number(p[1]) * 4 : 0;
}

/** The flex container that holds the pair, by its `ml-auto flex-shrink-0` signature. */
function pairContainer(html: string): string[] {
  const m = /<div class="([^"]*\bml-auto\b[^"]*\bflex-shrink-0\b[^"]*)"><button/.exec(html);
  return m ? m[1].split(/\s+/) : [];
}

const ROWS: Array<[string, string]> = [
  ["footer row beside Opened X/Y", "Boston Red Sox leading after starting at 47%"],
  ["thumbs-only row (no reason, no opener)", ""],
];

describe("#4168 — each thumb button is at least a 24px target", () => {
  it.each(ROWS)("%s: both buttons render (vacuity control)", (_name, reason) => {
    const data = reason ? makeData() : makeData({ opening_odds: undefined });
    const html = render(data, reason);
    expect(thumbs(html).map((t) => t.label)).toEqual(["More like this", "Less like this"]);
    if (reason) expect(html).toContain('data-testid="feed-card-opened"');
    else expect(html).not.toContain('data-testid="feed-card-opened"');
  });

  it.each(ROWS)("%s: glyph + 2 × padding ≥ 24px on each button", (_name, reason) => {
    const data = reason ? makeData() : makeData({ opening_odds: undefined });
    const found = thumbs(render(data, reason));
    expect(found).toHaveLength(2);
    for (const t of found) {
      expect(t.glyphPx + 2 * paddingPx(t.classes)).toBeGreaterThanOrEqual(WCAG_258_MIN_PX);
    }
  });

  it("the glyph did not grow to buy the target — the icon still draws at 12px", () => {
    // Enlarging the icon would also pass the arithmetic, and would push the row wider than the
    // padding does; the ship is a bigger TARGET, not a bigger picture.
    for (const t of thumbs(render(makeData(), ROWS[0][1]))) expect(t.glyphPx).toBe(12);
  });

  it("the pair is spaced (gap-1 = 4px, was gap-0.5 = 2px) and does not heighten the row", () => {
    const c = pairContainer(render(makeData(), ROWS[0][1]));
    expect(c).toContain("gap-1");
    expect(c).not.toContain("gap-0.5");
    // 24px buttons in a row whose text is ~20px tall would push every card 4px taller; the
    // negative margin lets the extra target overhang into the card's own padding instead.
    expect(c).toContain("-my-0.5");
  });
});
