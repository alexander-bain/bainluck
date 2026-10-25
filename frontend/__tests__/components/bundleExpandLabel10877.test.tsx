/**
 * #10877 — a bundle's "see the rest" control names what the tap opens.
 *
 * It read "All N questions" on both bundle cards. Alex rejected "question" as
 * the product's umbrella noun (10/11) without choosing a replacement word, so the
 * control now says what its members are. Every member the backend folds into a
 * bundle is one futures market, so a served bundle says "All 6 markets" — N is
 * the member count, never an outcome count. Members that are all games say
 * games; a mix says no noun at all rather than a wrong one.
 *
 * The specimen is the Middle East theme bundle served on production at
 * 2026-10-16 ~22:10Z (six futures members, one of them a three-outcome
 * election market whose outcomes must not be counted), rendered through
 * `DiscoverCard`, the path the page uses.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
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
import { bundleExpandLabel } from "../../components/discover/constants";
import SERVED from "../fixtures/discoverBundleMiddleEast.20261016.json";

const BUNDLE = SERVED as unknown as FeedItem;
const DATA = BUNDLE.data as FeedBundleData;
const MEMBERS = DATA.items;

function render(kind: "theme" | "comparison", items: FeedItem[] = MEMBERS): string {
  const item = { ...BUNDLE, data: { ...DATA, kind, items } } as unknown as FeedItem;
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
}

/** The collapsed card's footer control: the last button before the action bar. */
function footer(html: string): string | null {
  const bar = html.indexOf('data-testid="bundle-action-bar"');
  const buttons = [...html.slice(0, bar < 0 ? html.length : bar).matchAll(/<button[^>]*>([^<]*)<\/button>/g)];
  return buttons.length ? buttons[buttons.length - 1][1] : null;
}

describe("#10877 — the bundle footer names what it expands", () => {
  it("CONTROL: the served specimen is six single-market futures members, one of them multi-outcome", () => {
    expect(MEMBERS).toHaveLength(6);
    expect(MEMBERS.every((m) => m.type === "futures")).toBe(true);
    const outcomes = MEMBERS.map((m) => ((m.data as { top_outcomes?: unknown[] }).top_outcomes ?? []).length);
    expect(outcomes.reduce((a, b) => a + b, 0)).toBeGreaterThan(MEMBERS.length);
  });

  it.each(["theme", "comparison"] as const)("%s: counts members as markets, not outcomes", (kind) => {
    const html = render(kind);
    expect(footer(html)).toBe(`All ${MEMBERS.length} markets`);
    expect(html).not.toMatch(/All \d+ questions/);
  });

  it.each(["theme", "comparison"] as const)("%s: a bundle that seats every member has no count footer", (kind) => {
    const html = render(kind, MEMBERS.slice(0, 4));
    expect(html).not.toContain("All 4 markets");
  });

  it("names games only when every member is a game, and drops the noun for a mix", () => {
    const game = { type: "event", score: 1, reason: "", headline: "Bears @ Packers", data: {} } as unknown as FeedItem;
    expect(bundleExpandLabel([game, game, game, game, game])).toBe("All 5 games");
    const mixed = [...MEMBERS.slice(0, 4), game];
    expect(bundleExpandLabel(mixed)).toBe("See all 5");
    // The mixed theme card renders the noun-free label on the real component.
    expect(footer(render("theme", mixed))).toBe("See all 5");
  });
});
