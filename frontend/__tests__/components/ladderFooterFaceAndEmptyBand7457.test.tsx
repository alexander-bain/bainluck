/**
 * #7457 — the ladder card's footer, two defects in one block.
 *
 * Seen on production `2629172a` (v4807), Discover at 390px:
 *
 *   1. The footer prints `lastAbove50Label` in the MONO face. That face is
 *      right for the rung labels it was chosen for ("Above 67", "≥ 2.5 goals",
 *      "$90K+") and wrong for the ones that are a phrase. On "Kentucky coal
 *      production in 2027" the footer read
 *
 *          More likely than    Above 22 million short
 *          not:                tons
 *
 *      — mono's wide advance put a 27-character label on two lines and dragged
 *      the caption onto two lines with it. The card's own ladder sets that same
 *      label in `text-[12px] font-semibold` SANS (QuantityGroup, wideLabels),
 *      so the footer was the only place on the card treating it as a figure.
 *
 *   2. With no label to print the row still rendered, gated on
 *      `lastAbove50Label || data.confidence_tier`. A ladder whose every rung is
 *      below 50% is exactly the ladder with no summary, so the `||` could only
 *      ever fire on the empty case, and the reader got a ~60px top-bordered
 *      band holding one small three-bar glyph at the far right and nothing
 *      else — on "Will Trump buy at least part of Greenland?" (4% / 11%),
 *      between the ladder and the action bar, reading as a caption that failed
 *      to load.
 *
 * The fix to (2) can't simply drop the row, because L2-183 deliberately put the
 * confidence glyph on this variant and that would delete it on the whole
 * all-long-shots subset — making a how-well-sourced signal appear or vanish on
 * a property of the market that has nothing to do with sourcing. So the glyph
 * moved to the header's right cluster, where its leaderboard sibling already
 * keeps it, and the footer became only the summary. Both halves are guarded
 * here: the band is gone AND the glyph survives.
 *
 * ⚠️ `jest.config.js` sets `testEnvironment: 'node'` and `renderToStaticMarkup`
 * has no layout engine, so nothing here MEASURES a wrap. These are the two
 * claims that survive that: the face the label is set in (read off the rendered
 * class, which is what decides the advance width), and which elements exist.
 * The wrap itself is the production screenshot in the PR.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import { CONFIDENCE_TOOLTIP } from "@/lib/confidence";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Point = { label: string; probability: number; value: number };

function ladderData(
  points: Point[],
  name: string,
  tier: string | null,
): FeedFuturesData {
  return {
    id: 91,
    name,
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2027-12-31T00:00:00Z",
    top_outcomes: points.map((p, i) => ({
      id: i + 1,
      name: p.label,
      probability: p.probability,
      movement: null,
    })),
    outcome_count: points.length,
    confidence_tier: tier,
    discover_card: { suggested_format: "threshold_heatmap", threshold_points: points },
  } as unknown as FeedFuturesData;
}

function render(
  points: Point[],
  name = "Kentucky coal production in 2027",
  tier: string | null = "moderate",
): string {
  const data = ladderData(points, name, tier);
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/** The card in the coal screenshot: a wide prose rung clears 50%. */
const proseLabelLadder: Point[] = [
  { label: "Above 18 million short tons", probability: 0.81, value: 18 },
  { label: "Above 22 million short tons", probability: 0.57, value: 22 },
  { label: "Above 26 million short tons", probability: 0.22, value: 26 },
];

/** The Greenland card: nothing clears 50%, so there is no summary to print. */
const allLongShotsLadder: Point[] = [
  { label: "Before 2027", probability: 0.04, value: 1 },
  { label: "2027 or later", probability: 0.11, value: 2 },
];

/** The footer's own band, by the class combination only it carries. */
const FOOTER_BAND = "mt-3.5 pt-3 border-t border-surface-border";

/**
 * The span the footer sets `lastAbove50Label` in — its classes and its text.
 * The face is the defect, so the class list IS the evidence.
 *
 * ⚠️ Anchored on the caption, NOT on `text-accent-brand`: the ladder's own
 * highlighted rung carries that token too and renders FIRST, so a bare class
 * match reads `w-10 … font-mono … font-bold tabular-nums text-accent-brand`
 * off a QuantityGroup percentage and grades the wrong element — which passes
 * the mono assertion for the wrong reason the day the footer is fixed.
 */
function footerValue(html: string): { cls: string; text: string } | null {
  const m = html.match(
    /More likely than not:<\/span><span class="([^"]*)">([^<]*)<\/span>/,
  );
  return m ? { cls: m[1], text: m[2] } : null;
}

function footerValueClass(html: string): string | null {
  return footerValue(html)?.cls ?? null;
}

function occurrences(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

describe("#7457 the ladder footer sets a label in the label face", () => {
  test("the rung label is NOT set in the figures face", () => {
    const cls = footerValueClass(render(proseLabelLadder));
    expect(cls).not.toBeNull();
    // The whole defect: mono's advance is what wrapped a 27-character phrase.
    expect(cls).not.toContain("font-mono");
    expect(cls).not.toContain("tabular-nums");
  });

  test("it is set in the same face the card's own ladder uses for it", () => {
    // QuantityGroup wideLabels draws the rung label `text-[12px] font-semibold`
    // sans. The footer echoes that label, so it matches the weight rather than
    // out-shouting the ladder it summarises.
    const cls = footerValueClass(render(proseLabelLadder));
    expect(cls).toContain("font-semibold");
    expect(cls).not.toContain("font-bold");
  });

  test("a wide prose label reaches the reader whole", () => {
    const value = footerValue(render(proseLabelLadder));
    // The furthest rung still over even — every word of it, including the unit
    // that tells this rung from the one above. Read out of the FOOTER's own
    // span: the ladder above prints the same string, so a document-wide
    // `toContain` would pass with the footer deleted.
    expect(value?.text).toBe("Above 22 million short tons");
  });

  test("the caption and the label can size independently", () => {
    // `shrink-0` on the caption + `min-w-0` on the value is what lets a long
    // label wrap UNDER a whole caption instead of breaking both lines. Without
    // the pair the flex row squeezes the caption first, which is the two-line
    // "More likely than / not:" in the screenshot.
    const html = render(proseLabelLadder);
    const caption = html.match(/<span class="([^"]*text-text-secondary[^"]*)">More likely than not:/);
    expect(caption?.[1]).toContain("shrink-0");
    expect(footerValueClass(html)).toContain("min-w-0");
  });
});

describe("#7457 a ladder with no summary draws no band", () => {
  test("no rung over 50% ⇒ the bordered footer band is not rendered at all", () => {
    const html = render(allLongShotsLadder, "Will Trump buy at least part of Greenland?");
    expect(html).not.toContain("More likely than not");
    expect(occurrences(html, FOOTER_BAND)).toBe(0);
  });

  test("CONTROL: a rung over 50% ⇒ the band IS rendered, exactly once", () => {
    // The absence above has to be caused by the missing summary and not by the
    // band having been deleted outright.
    const html = render(proseLabelLadder);
    expect(occurrences(html, FOOTER_BAND)).toBe(1);
  });

  test("the confidence glyph survives the band's removal", () => {
    // L2-183's ship, preserved: the glyph is on this variant whether or not any
    // rung clears 50%. It was the band's only occupant before, so a fix that
    // merely gated the band would have taken it with it.
    const html = render(allLongShotsLadder, "Will Trump buy at least part of Greenland?");
    expect(html).toContain('role="img"');
    expect(html).toContain(CONFIDENCE_TOOLTIP);
    expect(occurrences(html, 'role="img"')).toBe(1);
  });

  test("the glyph sits in the header cluster, above the title", () => {
    // Where it is, not just that it is: the header is the cluster it shares
    // with the resolution date, the way the leaderboard sibling keeps it.
    const html = render(proseLabelLadder);
    const glyph = html.indexOf('role="img"');
    const title = html.indexOf("<h3");
    expect(glyph).toBeGreaterThan(-1);
    expect(title).toBeGreaterThan(-1);
    expect(glyph).toBeLessThan(title);
  });

  test("CONTROL: no tier ⇒ no glyph, and still no separator", () => {
    const html = render(proseLabelLadder, "Kentucky coal production in 2027", null);
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain(CONFIDENCE_TOOLTIP);
    // The header's "·" joins the date to the glyph. With no glyph it would be
    // a bullet beside nothing.
    expect(html).not.toContain(">·<");
  });

  test("a tier the glyph does not recognise prints no orphan separator", () => {
    // `SignalBars` returns null for anything outside high/moderate/low, so a
    // separator gated on the raw payload field would draw a lone "·" next to
    // nothing the first time the backend ships a new tier name.
    const html = render(proseLabelLadder, "Kentucky coal production in 2027", "unknown-tier");
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain(">·<");
  });
});
