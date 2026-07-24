// L2-175 Item 1: the top Discover cards (TdF concept, UFC) had a DEAD plain click —
// hover highlighted, ctrl-click opened a new tab, but a plain left-click did nothing
// (pointer capture on pointerdown retargeted the click off the inner <Link>, and the
// card hero was never a link at all). These guards assert BOTH directions per gotcha
// #43: a click has a real navigation destination for every card type (feedItemHref),
// AND the whole-card wrapper renders the clickable affordance. Swipe behavior is
// unchanged (useSwipe still returns its touch/pointer handlers; capture is merely
// deferred to the first real drag).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type {
  FeedItem,
  FeedConceptData,
  FeedEventData,
  FeedFuturesData,
  FeedTournamentData,
} from "@/lib/types";

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

import { feedItemHref } from "../../components/discover/utils";
import DiscoverCard from "../../components/DiscoverCard";

function conceptItem(): FeedItem {
  return {
    type: "concept",
    data: {
      key: "event:cycling:tour-de-france-2026",
      name: "Tour de France 2026",
      domain: "cycling",
      status: "live",
    } as FeedConceptData,
  } as FeedItem;
}

describe("feedItemHref — every card type resolves a navigable destination", () => {
  test("concept → /event/<domain>/<slug>", () => {
    expect(feedItemHref(conceptItem())).toBe("/event/cycling/tour-de-france-2026");
  });

  test("event → /events/<id>", () => {
    const item = { type: "event", data: { id: 4242 } as FeedEventData } as FeedItem;
    expect(feedItemHref(item)).toBe("/events/4242");
  });

  test("futures without a concept key → /futures/<id>", () => {
    const item = {
      type: "futures",
      data: { id: 9001, source: "polymarket", external_id: "x" } as FeedFuturesData,
    } as FeedItem;
    expect(feedItemHref(item)).toBe("/futures/9001");
  });

  test("tournament → /event/<domain>/<slug> when a key resolves", () => {
    const item = {
      type: "tournament",
      data: {
        key: "the_open",
        slug: "the-open-2026",
        name: "The Open",
      } as unknown as FeedTournamentData,
    } as FeedItem;
    // tournamentEventKey builds the concept key; a golf slug routes into /event/golf/…
    expect(feedItemHref(item)).toMatch(/^\/event\/golf\//);
  });

  test("bundle/group card types own their internal nav → null", () => {
    expect(feedItemHref({ type: "bundle", data: {} } as unknown as FeedItem)).toBeNull();
  });
});

describe("DiscoverCard — the whole card is clickable (not just the title)", () => {
  test("a navigable concept card renders the cursor-pointer wrapper affordance", () => {
    const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: conceptItem() }} />);
    expect(html).toContain("cursor-pointer");
    // and it still renders the card body (the concept name), not an empty shell
    expect(html).toContain("Tour de France 2026");
  });
});
