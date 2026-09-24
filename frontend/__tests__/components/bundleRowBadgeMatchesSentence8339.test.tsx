/**
 * #8339 — A BUNDLE ROW PRINTS ONE MOVE ONE WAY.
 *
 * Production Discover at 390px, 2026-09-24 ~03:40Z, the RUSSIA–UKRAINE bundle:
 *
 *     Will Russia enter Mykolaivka by October 31, 2026?
 *     Down 28.5 points today — now 37% chance        ▼ 29 pts   37%
 *
 * The sentence comes from the backend's house formatter (`feed_reasons._points`:
 * one decimal, trailing ".0" dropped). The chip rounded to a whole point. Same
 * class as #5842: a card and its own sentence printing one value two ways.
 *
 * The fixture is that bundle exactly as `GET /api/feed?limit=100` served it at
 * 04:11Z (the Yes leg carries `movement: -0.28500000000000003`), entered
 * through `DiscoverCard` because that is the path page one renders.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem } from "@/lib/types";
import { formatMovementPointsLikeSentence } from "@/lib/probabilityDisplay";
import { MovementBadge } from "@/components/discover/shared";
import fixture from "../fixtures/bundleRowBadgeMatchesSentence8339.json";

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

function servedBundle(): FeedItem {
  return JSON.parse(JSON.stringify(fixture.bundle)) as FeedItem;
}

/** Every movement chip's visible text, e.g. "28.5 pts". */
function chipTexts(html: string): string[] {
  return Array.from(html.matchAll(/aria-label="(?:Up|Down) [^"]+ in the last 24h"[^>]*>.*?<\/svg>([^<]*)<\/span>/g)).map(
    (m) => m[1].trim(),
  );
}

describe("#8339 — the bundle row's chip says what its sentence says", () => {
  const html = renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item: servedBundle() }} positionIndex={0} />,
  );

  test("the served specimen still carries the sentence this is about", () => {
    // If this fails the fixture no longer shows the defect's shape; the chip
    // arm below would then pass for the wrong reason.
    expect(html).toContain("Down 28.5 points today");
  });

  test("the Mykolaivka chip reads 28.5, not 29", () => {
    expect(chipTexts(html)).toEqual(["28.5 pts"]);
    expect(html).toContain('aria-label="Down 28.5 points in the last 24h"');
    expect(html).not.toContain("29 pts");
  });
});

describe("#8339 — the chip's number is the backend sentence's number", () => {
  // `feed_reasons._points`: round(abs(v) * 100, 1), trailing ".0" dropped.
  test.each([
    [-0.28500000000000003, "28.5"],
    [0.07, "7"],
    [0.1, "10"],
    [-0.105, "10.5"],
    [0.02, "2"],
  ])("movement %p prints %p", (movement, expected) => {
    expect(formatMovementPointsLikeSentence(movement)).toBe(expected);
  });

  test("a whole-point move keeps its old width: '7 pts', never '7.0 pts'", () => {
    const html = renderToStaticMarkup(<MovementBadge m={0.07} prob={0.4} />);
    expect(html).toContain("</svg>7 pts</span>");
    expect(html).toContain('aria-label="Up 7 points in the last 24h"');
  });

  test("null stays null", () => {
    expect(formatMovementPointsLikeSentence(null)).toBeNull();
    expect(formatMovementPointsLikeSentence(Number.NaN)).toBeNull();
  });
});
