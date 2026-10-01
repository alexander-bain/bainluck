/**
 * #10059 — A QUESTION'S TITLE IS NEVER CLIPPED ON A DISCOVER CARD OR GROUP ROW.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Discover at 390px, 2026-10-01 ~11:30Z, the "What happens next in AI?" group:
 *
 *     Which company has #1 AI model end of November?…   +36 pts  46%
 *       New favorite: Google (46%)
 *     Which company has the best AI model end of November?        48%
 *       New favorite: Google (48%)
 *
 * The first title is "… end of November? (Style Control On)", a separate
 * Polymarket market. `line-clamp-2` cut it down to the first half, which reads
 * as the second row's question. The reader then sees one question with two
 * prices. The leaderboard card clamped the same way ("… Number 1 (Men's)").
 *
 * ── THE SPECIMEN IS THE SERVED OBJECT ───────────────────────────────────────
 *
 * `__tests__/fixtures/titleNeverClipped10059.json` holds the bundle and the
 * PPA leaderboard card exactly as `GET /api/feed?limit=40` served them. Both
 * enter through `DiscoverCard`, the path page one actually uses.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. the collapsed group row prints the whole title in an element with no
 *     clamp, so "(Style Control On)" is visible;
 *  2. the leaderboard card's <h3> carries no clamp either;
 *  3. CONTROL — the row's caption keeps its two-line clamp. The fix removed the
 *     limit on the question only, not on every line of the row.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem } from "@/lib/types";
import fixture from "../fixtures/titleNeverClipped10059.json";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";

function render(item: unknown): string {
  const copy = JSON.parse(JSON.stringify(item)) as FeedItem;
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: copy }} positionIndex={0} />);
}

/** The opening tag of the element whose text content is exactly `text`. */
function tagAround(html: string, text: string): string {
  const at = html.indexOf(`>${text}<`);
  expect(at).toBeGreaterThan(-1);
  return html.slice(html.lastIndexOf("<", at), at + 1);
}

const STYLE_ON = "Which company has #1 AI model end of November? (Style Control On)";
const MENS = "PPA 2026-27 End of Year Rankings: Player to be Number 1 (Men&#x27;s)";

describe("#10059 a question's title is never clipped", () => {
  it("the specimen is the served bundle, and the clipped sibling sits beside it", () => {
    const html = render(fixture.bundle);
    expect(html).toContain(STYLE_ON);
    expect(html).toContain(">Which company has the best AI model end of November?<");
  });

  it("the collapsed group row prints the whole title with no clamp", () => {
    const tag = tagAround(render(fixture.bundle), STYLE_ON);
    expect(tag).toContain('data-testid="compact-row-title"');
    expect(tag).not.toMatch(/line-clamp|\btruncate\b/);
    expect(tag).toContain("break-words");
  });

  it("the leaderboard card's heading prints the whole title with no clamp", () => {
    const html = render(fixture.leaderboard);
    expect(html).toContain('data-card-format="leaderboard"');
    const tag = tagAround(html, MENS);
    expect(tag.startsWith("<h3")).toBe(true);
    expect(tag).not.toMatch(/line-clamp|\btruncate\b/);
  });

  it("CONTROL: the row's caption keeps its two-line clamp", () => {
    const html = render(fixture.bundle);
    const captions = html.match(/<div[^>]*data-testid="compact-row-caption"[^>]*>/g) ?? [];
    expect(captions.length).toBeGreaterThan(0);
    for (const c of captions) expect(c).toContain("line-clamp-2");
  });
});
