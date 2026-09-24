/**
 * #8365 — A DISCOVER HERO CHIP PRINTS ONE MOVE ONE WAY.
 *
 * Production Discover at 390px, 2026-09-24 06:43Z, feed item 21:
 *
 *     Will the 30-year Treasury yield dip below 5.15% before 2027?
 *     Down 27 points today                                  ↓ 27.0 pts
 *
 * Sibling of #8339: that fix moved `MovementBadge` onto the backend sentence's
 * form (`feed_reasons._points`: one decimal, trailing ".0" dropped); the hero
 * chip in `discover/FuturesCard` kept `formatMovementPoints` and so still
 * printed "27.0" beside "27".
 *
 * Both fixtures are feed items exactly as `GET /api/feed?limit=150` served them
 * at 06:43Z, entered through `DiscoverCard` because that is the page-one path:
 * the whole-point card (no image → variant B) and a tenth-point card with a
 * photo (the scrim variant) whose "37.6" must not move.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem } from "@/lib/types";
import fixture from "../fixtures/heroChipMatchesSentence8365.json";

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
  const served = JSON.parse(JSON.stringify(item)) as FeedItem;
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: served }} positionIndex={0} />);
}

/** The hero chip's visible text, e.g. "↓ 27 pts". */
function heroChips(html: string): string[] {
  return Array.from(html.matchAll(/title="(?:Up|Down) [^"]+ points in the last 24h"[^>]*>([^<]*[↑↓][^<]*)</g)).map((m) =>
    m[1].trim(),
  );
}

describe("#8365 — the hero chip says what its sentence says", () => {
  test("the whole-point specimen still carries the sentence this is about", () => {
    // If this fails the fixture no longer shows the defect's shape; the chip
    // arm below would then pass for the wrong reason.
    expect(render(fixture.whole_point)).toContain("Down 27 points today");
  });

  test("the 30-year Treasury chip reads '↓ 27 pts', not '27.0'", () => {
    const html = render(fixture.whole_point);
    expect(heroChips(html)).toEqual(["↓ 27 pts"]);
    expect(html).toContain('title="Down 27 points in the last 24h"');
    expect(html).not.toContain("27.0");
  });

  test("a tenth-point move is unchanged: '↑ 37.6 pts' beside 'Up 37.6 points today'", () => {
    const html = render(fixture.tenth_point);
    expect(html).toContain("Up 37.6 points today");
    expect(heroChips(html)).toEqual(["↑ 37.6 pts"]);
  });
});
