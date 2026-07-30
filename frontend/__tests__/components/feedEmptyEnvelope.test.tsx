// L2-215 Item 0/Item 1 (#1486) — the render-envelope fixture matrix for the
// fail-closed empty-card guard. Concept + bundle cards shipped with ZERO inline
// outcomes render as bare tiles (colored image + title + Like/Share, nothing to
// predict — Tour de France 2026, Belgian GP Winner). These tests pin the shared
// client eligibility predicate AND the real render routing (DiscoverCard /
// FeedCard) across every envelope shape: usable probability, result-first winner,
// navigational collection with meaningful metadata, empty predictive envelope,
// unknown type, and a partial (mixed) load.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type {
  FeedItem,
  FeedConceptData,
  FeedFuturesData,
  FeedTournamentData,
  FeedBundleData,
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
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import {
  feedItemSuppressionReason,
  feedItemHasRenderableContent,
  collectSuppressedEnvelopes,
} from "../../components/discover/utils";
import DiscoverCard from "../../components/DiscoverCard";
import FeedCard from "../../components/FeedCard";

const NOW = new Date("2026-07-30T00:00:00Z").getTime();

// ---- Fixture factory: one per envelope shape in the matrix ----

/** usable probability — a futures with a real leading outcome. */
function usableFutures(): FeedItem {
  return {
    type: "futures",
    data: {
      id: 1,
      name: "Who wins the title?",
      top_outcomes: [{ id: 1, name: "Leader", probability: 0.62, rank: 1, movement: 0.03 }],
      outcome_count: 4,
      status: "open",
    } as FeedFuturesData,
  } as FeedItem;
}

/** empty predictive envelope — a futures with NO outcomes and no settled context. */
function emptyFutures(): FeedItem {
  return {
    type: "futures",
    data: { id: 2, name: "Bare market", top_outcomes: [], outcome_count: 0, status: "open" } as FeedFuturesData,
  } as FeedItem;
}

/** settled result — a zero-outcome futures that is authoritatively resolved. */
function settledFutures(): FeedItem {
  return {
    type: "futures",
    data: { id: 3, name: "Graded market", top_outcomes: [], status: "resolved", winner: "Someone" } as FeedFuturesData,
  } as FeedItem;
}

/** result-first winner — a settled WHAT-HIT concept. */
function settledConcept(): FeedItem {
  return {
    type: "concept",
    data: {
      key: "event:cycling:tour-de-france-2026",
      name: "Tour de France 2026",
      domain: "cycling",
      status: "completed",
      marquee_whathit: true,
      winner: "Tadej Pogačar",
    } as FeedConceptData,
  } as FeedItem;
}

/** empty predictive envelope — a live/upcoming concept (#1486's exact class). */
function emptyConcept(): FeedItem {
  return {
    type: "concept",
    data: {
      key: "event:f1:belgian-grand-prix-winner",
      name: "Belgian Grand Prix Winner",
      domain: "f1",
      status: "live",
    } as FeedConceptData,
  } as FeedItem;
}

/** empty tournament (no golfers, no marquee result) vs a populated one. */
function emptyTournament(): FeedItem {
  return {
    type: "tournament",
    data: { key: "t1", name: "Some Open", golfers: [] } as unknown as FeedTournamentData,
  } as FeedItem;
}
function usableTournament(): FeedItem {
  return {
    type: "tournament",
    data: {
      key: "t2",
      name: "The Open",
      golfers: [{ name: "G", probability: 22, rank: 1, movement_24h: 1 }],
    } as unknown as FeedTournamentData,
  } as FeedItem;
}

/** navigational collection with meaningful metadata — a bundle with a renderable child. */
function usableBundle(): FeedItem {
  return {
    type: "bundle",
    data: {
      id: "b1",
      title: "Compare",
      kind: "comparison",
      item_count: 1,
      member_ids: [1],
      items: [usableFutures()],
    } as FeedBundleData,
  } as FeedItem;
}

/** empty predictive envelope — a bundle whose members are all empty. */
function emptyBundle(): FeedItem {
  return {
    type: "bundle",
    data: {
      id: "b2",
      title: "Empty",
      kind: "theme",
      item_count: 0,
      member_ids: [],
      items: [emptyConcept()],
    } as FeedBundleData,
  } as FeedItem;
}

function eventItem(): FeedItem {
  return { type: "event", data: { id: 7, home_team: "H", away_team: "A" } } as unknown as FeedItem;
}

function unknownItem(): FeedItem {
  return { type: "mystery", data: {} } as unknown as FeedItem;
}

describe("feedItemSuppressionReason — the envelope matrix", () => {
  test("usable probability (futures with outcomes) → renderable", () => {
    expect(feedItemSuppressionReason(usableFutures(), NOW)).toBeNull();
    expect(feedItemHasRenderableContent(usableFutures(), NOW)).toBe(true);
  });

  test("result-first winner (settled WHAT-HIT concept) → renderable", () => {
    expect(feedItemSuppressionReason(settledConcept(), NOW)).toBeNull();
  });

  test("WHAT-HIT concept without a graded winner still renderable (FINAL/recap, #1219)", () => {
    const item = {
      type: "concept",
      data: { key: "k", name: "Race", domain: "cycling", status: "completed", marquee_whathit: true },
    } as unknown as FeedItem;
    expect(feedItemSuppressionReason(item, NOW)).toBeNull();
  });

  test("navigational collection with a renderable child (bundle) → renderable", () => {
    expect(feedItemSuppressionReason(usableBundle(), NOW)).toBeNull();
  });

  test("settled zero-outcome futures → renderable (result, not empty)", () => {
    expect(feedItemSuppressionReason(settledFutures(), NOW)).toBeNull();
  });

  test("populated tournament → renderable; empty tournament → empty_tournament", () => {
    expect(feedItemSuppressionReason(usableTournament(), NOW)).toBeNull();
    expect(feedItemSuppressionReason(emptyTournament(), NOW)).toBe("empty_tournament");
  });

  test("event → always renderable (real matchup, never a bare tile)", () => {
    expect(feedItemSuppressionReason(eventItem(), NOW)).toBeNull();
  });

  test("empty predictive envelope — live concept → empty_concept", () => {
    expect(feedItemSuppressionReason(emptyConcept(), NOW)).toBe("empty_concept");
    expect(feedItemHasRenderableContent(emptyConcept(), NOW)).toBe(false);
  });

  test("empty predictive envelope — zero-outcome unsettled futures → empty_futures", () => {
    expect(feedItemSuppressionReason(emptyFutures(), NOW)).toBe("empty_futures");
  });

  test("empty predictive envelope — all-empty bundle → empty_bundle", () => {
    expect(feedItemSuppressionReason(emptyBundle(), NOW)).toBe("empty_bundle");
  });

  test("unknown type → unknown_type (fail closed)", () => {
    expect(feedItemSuppressionReason(unknownItem(), NOW)).toBe("unknown_type");
  });
});

describe("collectSuppressedEnvelopes — identity-free, partial-load safe", () => {
  test("a mixed (partial) page keeps renderable, reports only empty envelopes", () => {
    const page = [
      usableFutures(),
      emptyConcept(),
      settledConcept(),
      emptyBundle(),
      eventItem(),
      unknownItem(),
    ];
    const kept = page.filter((i) => feedItemHasRenderableContent(i, NOW));
    expect(kept).toHaveLength(3); // usableFutures + settledConcept + event

    const suppressed = collectSuppressedEnvelopes(page, NOW);
    expect(suppressed).toEqual([
      { type: "concept", reason: "empty_concept" },
      { type: "bundle", reason: "empty_bundle" },
      { type: "mystery", reason: "unknown_type" },
    ]);
    // Identity-free: no id/name/key/session fields leak into telemetry input.
    for (const e of suppressed) {
      expect(Object.keys(e).sort()).toEqual(["reason", "type"]);
    }
  });
});

describe("render routing — the leaf dispatcher fails closed", () => {
  test("DiscoverCard renders NOTHING for an empty live concept", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: emptyConcept() }} />,
    );
    expect(html).toBe("");
    expect(html).not.toContain("Belgian Grand Prix Winner");
  });

  test("DiscoverCard renders a settled WHAT-HIT concept", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: settledConcept() }} />,
    );
    expect(html).toContain("Tadej Pogačar");
  });

  test("FeedCard (Sports dispatcher) returns null for an empty concept", () => {
    const html = renderToStaticMarkup(<FeedCard item={emptyConcept()} />);
    expect(html).toBe("");
  });

  test("FeedCard renders a settled WHAT-HIT concept", () => {
    const html = renderToStaticMarkup(<FeedCard item={settledConcept()} />);
    expect(html).toContain("Tour de France 2026");
  });
});
