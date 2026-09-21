// #7738 — THE ONLY NAV LINK TO THE ACCURACY PAGE IS LABELLED IN READER WORDS.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// The footer is the ONLY navigation entry point to the accuracy page: the
// bottom nav is Discover · Sports · Browse · My Stuff and the top nav has none.
// In the footer's Explore column it read:
//
//     Discover · Sports · Calibration · My Stuff
//
// Every sibling is a plain word; "Calibration" is a statistics term on a
// casual fan's screen — the class notice 34 / D102 bars. Worse, the page it
// opens never says the word back: its `<h1>` is "Do Prediction Markets Predict
// Anything?", so a reader who clicked it landed somewhere that did not confirm
// they had arrived. Alex's own vocabulary for the surface is "the accuracy
// page" (D137, notice 45), and `/about` already links to it in plain words.
//
// ── WHAT THIS SUITE FIXES IN PLACE ───────────────────────────────────────────
//
// Two things, and the pairing is the point:
//
//   1. the LABEL is a reader word, and
//   2. the ROUTE is untouched.
//
// The cheapest way to make a label stop saying "Calibration" is to move the
// page, and that is the change this ship explicitly did NOT make — `/calibration`
// is in `sitemap.ts` at priority 0.7 with a matching `canonical`, and renaming a
// live URL is a different, larger question. A guard that asserted only (1) would
// be satisfied by the one edit the issue rules out.
//
// ── WHY A RENDER AND NOT A SOURCE SLICE ──────────────────────────────────────
//
// The claim is about what a reader reads, and `FOOTER_LINKS` is a data table
// that a later refactor could legitimately build from anywhere. Rendering asks
// the question in the reader's terms — "which words sit on the anchor that goes
// to this href" — and survives that refactor. It is also cheap here: `Footer`
// is a small client component with two hooks and no data fetching, unlike the
// 2,000-line page behind SWR that `calibrationNotice34.test.ts` deliberately
// does not render.
//
// ── THE TRAP THIS SUITE IS WRITTEN AROUND ────────────────────────────────────
//
// `calibrationNotice34.test.ts`'s header states it: a guard that bans a phrase
// from a FILE red-lights honest work — a comment explaining why the word left,
// which this fix has in both files it touches. So nothing here greps a source
// file. The ban below is on the accessible name of ONE anchor, parsed out of
// rendered markup, which a comment cannot trip.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/",
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => undefined }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const Footer = require("@/components/Footer").default;

const HTML = renderToStaticMarkup(React.createElement(Footer));

/**
 * Every `<a href=…>text</a>` in the rendered footer whose content is PURE TEXT,
 * in document order.
 *
 * Two things this deliberately does not do, both of them CodeQL findings the
 * first draft earned:
 *
 *   - it does not strip tags out of the content (`/<[^>]*>/g` is
 *     `js/incomplete-multi-character-sanitization` — an incomplete tag strip,
 *     and CodeQL is right that a regex is not an HTML parser), and
 *   - it does not decode entities (#7716's `js/double-escaping`).
 *
 * Instead the content pattern is `[^<]*`, so an anchor wrapping markup does not
 * match AT ALL rather than being mangled into a label. That is only safe
 * because nothing may hide in the gap, which is what `the only anchor with
 * nested markup is the brand` asserts below. No label in this footer contains
 * an HTML entity either, so an undecoded `&amp;` would surface as a loud
 * failure rather than a silent pass.
 */
function textLinks(): Array<{ href: string; label: string }> {
  const found: Array<{ href: string; label: string }> = [];
  const anchor = /<a\b[^>]*\bhref="([^"]*)"[^>]*>([^<]*)<\/a>/g;
  for (;;) {
    const match = anchor.exec(HTML);
    if (match === null) break;
    found.push({ href: match[1], label: match[2].trim() });
  }
  return found;
}

const LINKS = textLinks();

describe("#7738 — the footer names the accuracy page in reader words", () => {
  // ═══ THE SHIP ═══

  test("the link to the accuracy page is labelled 'Accuracy'", () => {
    const toAccuracy = LINKS.filter((link) => link.href === "/calibration");
    // Exactly one, not at-least-one: two footer entries to the same page would
    // let a stale jargon label survive beside a new plain one and still pass.
    expect(toAccuracy).toHaveLength(1);
    expect(toAccuracy[0].label).toBe("Accuracy");
  });

  test("and the route it points at did NOT move", () => {
    // (2) above. The label is the whole change; `/calibration` keeps its
    // sitemap entry and its canonical.
    expect(LINKS.map((link) => link.href)).toContain("/calibration");
  });

  test("no footer link is labelled with the statistics term", () => {
    // Scoped to accessible names, and whole-label rather than substring: a
    // future "How accurate our numbers are" must not red, and neither must the
    // comments in `Footer.tsx` and `app/calibration/layout.tsx` that record why
    // the word left.
    const jargon = LINKS.filter(
      (link) => link.label.toLowerCase() === "calibration",
    );
    expect(jargon).toEqual([]);
  });

  // ═══ CONTROLS ON THE PARSER ═══
  //
  // Every assertion above passes vacuously if `footerLinks` returns nothing, or
  // returns hrefs with empty labels — and both are exactly what a render that
  // half-failed would produce. These two fail on that and cannot be satisfied
  // by the ship being correct.

  test("the parser found the footer's links at all", () => {
    // The footer ships three columns plus the brand and the "What is Bain Luck?"
    // line. A floor well under that catches an empty or truncated render
    // without pinning the count, which is editorial.
    expect(LINKS.length).toBeGreaterThanOrEqual(8);
  });

  test("the only anchor with nested markup is the brand", () => {
    // This is what makes `[^<]*` safe. A text-only pattern skips an anchor
    // whose label is wrapped in a span — so a future `<span>Calibration</span>`
    // would vanish from `LINKS` and every ban above would pass on a footer that
    // still says it. Counting the anchors the pattern did NOT reach closes that
    // hole: the brand lockup (a 🍀 span and a wordmark span) is the one, and a
    // second one is a red that sends the reader back here.
    const everyAnchor = HTML.match(/<a\b/g) ?? [];
    expect(everyAnchor).toHaveLength(LINKS.length + 1);
    expect(HTML).toContain(">Bain Luck</span>");
  });

  test("the parser reads LABELS, not just hrefs", () => {
    // If `label` were coming back empty, "no link says Calibration" would be
    // true of a blank footer. The siblings prove the extraction works on the
    // very column under test.
    const explore = new Map(LINKS.map((link) => [link.href, link.label]));
    expect(explore.get("/discover")).toBe("Discover");
    expect(explore.get("/sports")).toBe("Sports");
    expect(explore.get("/my-stuff")).toBe("My Stuff");
  });
});

describe("#7738 — the tab and share titles moved with the label", () => {
  // The other, and only other, place the word reached a reader. Asserted on the
  // exported `metadata` object rather than on the file's text, for the same
  // reason the footer is rendered: this is what Next serves.
  //
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { metadata } = require("@/app/calibration/layout");

  test("the browser tab says Accuracy", () => {
    expect(metadata.title).toBe("Accuracy");
  });

  test("the share card says Accuracy", () => {
    expect(metadata.openGraph.title).toBe("Accuracy — Bain Luck");
  });

  test("but the canonical url is unchanged", () => {
    // The pairing again: a title change must not be delivered by moving the
    // page. `sitemap.ts` points here.
    expect(metadata.alternates.canonical).toBe("/calibration");
    expect(metadata.openGraph.url).toBe("/calibration");
  });
});
