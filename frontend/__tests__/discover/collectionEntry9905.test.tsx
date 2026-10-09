/**
 * #9905 — WEB DISCOVER OPENS THE PUBLISHED NFL-WEEK / MLB-POSTSEASON HUBS.
 *
 * The feed places a `type: "collection"` card directly before the strongest of
 * its members (`backend/app/utils/feed_collections.py`, envelope under `data`
 * exactly as `container_discovery.collection_card` writes it). Before this, the
 * web's renderability filter called every such card `unknown_type` and dropped
 * it. This suite pins, both directions:
 *
 * - ADMISSION: a published NFL week / MLB postseason whose slug round-trips its
 *   edition and whose destination is the canonical `/collections/{slug}` renders.
 *   Master's producer still writes `destination.web = null` until #9892 lands;
 *   that card is refused, as is anything malformed — and refusing one never
 *   drops an ordinary card beside it.
 * - PLACEMENT: the page spaces cards by sport. Left in that pass, an NFL hub in
 *   front of an NFL game would be pushed away from it. The collection keeps the
 *   spot the server gave it.
 * - TAP / RETURN: the card is a plain link to the hub, and the feed snapshot the
 *   page restores on Back brings it back to the same spot.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem } from "@/lib/types";
import {
  admitCollection,
  isCollectionItem,
  placeCollections,
  splitCollections,
  type AnchoredCollection,
} from "@/lib/discover/collectionFeed";
import { spaceBySport } from "@/lib/discover/spacedOrder";
import { parseFeedSnapshot, serializeFeedSnapshot } from "@/lib/discover/feedRestore";
import DiscoverCollectionCard from "@/components/discover/DiscoverCollectionCard";

jest.mock("next/link", () => {
  return ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
    React.createElement("a", { href, ...rest }, children);
});

// ── fixtures: the producer's envelope, verbatim shape ─────────────────────────

function collection(overrides: Record<string, unknown> = {}, slug = "nfl-2026-week-5"): FeedItem {
  const nfl = slug.startsWith("nfl-");
  const data = {
    type: "collection",
    text: nfl ? "NFL 2026 · Week 5" : "MLB 2026 · Postseason",
    id: nfl ? 901 : 902,
    slug,
    name: nfl ? "NFL 2026 · Week 5" : "MLB 2026 · Postseason",
    state: "published",
    revision: 1,
    edition: nfl
      ? { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 5 }
      : { kind: "mlb_postseason", league: "mlb", season: 2026 },
    status: "active",
    window_start: "2026-10-01T00:00:00+00:00",
    window_end: "2026-10-07T00:00:00+00:00",
    game_count: nfl ? 16 : 4,
    question_count: nfl ? 40 : 1,
    matched_event_ids: [7],
    destination: { kind: "container", slug, web: `/collections/${slug}`, api: `/api/containers/${slug}` },
    ...overrides,
  };
  return { type: "collection", score: 80, reason: data.name as string, headline: null, data } as unknown as FeedItem;
}

function game(id: number, sport = "americanfootball_nfl"): FeedItem {
  return {
    type: "event",
    score: 80 - id,
    reason: "",
    headline: null,
    data: { id, sport, home_team: `Home ${id}`, away_team: `Away ${id}` },
  } as unknown as FeedItem;
}

function futures(id: number): FeedItem {
  return {
    type: "futures",
    score: 70 - id,
    reason: "",
    headline: null,
    data: { id, name: `Question ${id}`, llm_sport_category: "politics", top_outcomes: [{ name: "Yes", probability: 0.4 }] },
  } as unknown as FeedItem;
}

// The page's id rule for the kinds used here (`getItemId`).
function idOf(item: FeedItem): string {
  const data = item.data as { id?: number; slug?: string };
  if (item.type === "collection") return `collection-${data?.slug}`;
  return `${item.type}-${data.id}`;
}

function categoryOf(item: FeedItem): string {
  if (item.type === "event") return (item.data as { sport: string }).sport.split("_")[0];
  return "politics";
}

type Single = { type: "single"; item: FeedItem };

/** The page's composition with the real spacing pass (`processedItems`). */
function compose(served: FeedItem[], drop: Set<string> = new Set()): string[] {
  const { ordinary, anchored } = splitCollections(served, idOf);
  const kept = ordinary.filter((item) => !drop.has(idOf(item)));
  const spaced: Single[] = spaceBySport(kept, categoryOf).map((item) => ({ type: "single", item }));
  return placeCollections<Single>(spaced, anchored, (g) => [idOf(g.item)], (item) => ({ type: "single", item })).map((g) =>
    idOf(g.item),
  );
}

// ── admission ─────────────────────────────────────────────────────────────────

describe("#9905 admission", () => {
  it("admits a published NFL week onto its canonical hub", () => {
    expect(admitCollection(collection())).toEqual({
      slug: "nfl-2026-week-5",
      name: "NFL 2026 · Week 5",
      href: "/collections/nfl-2026-week-5",
      subtitle: "16 games · 40 questions",
    });
  });

  it("admits the MLB postseason and the preseason / postseason NFL weeks", () => {
    expect(admitCollection(collection({}, "mlb-2026-postseason"))?.href).toBe("/collections/mlb-2026-postseason");
    expect(admitCollection(collection({}, "mlb-2026-postseason"))?.subtitle).toBe("4 games · 1 question");
    for (const [stage, slug] of [
      ["Pre Season", "nfl-2026-preseason-week-2"],
      ["Post Season", "nfl-2026-postseason-week-1"],
    ]) {
      const week = Number(slug.slice(-1));
      const item = collection({ edition: { kind: "nfl_week", league: "nfl", season: 2026, stage, week } }, slug);
      expect(admitCollection(item)?.href).toBe(`/collections/${slug}`);
    }
  });

  it("leaves out an empty half of the subtitle", () => {
    expect(admitCollection(collection({ question_count: 0 }))?.subtitle).toBe("16 games");
    expect(admitCollection(collection({ game_count: 0, question_count: 1 }))?.subtitle).toBe("1 question");
  });

  const refusals: [string, Record<string, unknown>][] = [
    ["master's producer today: no web destination yet (#9892)", { destination: { kind: "container", slug: "nfl-2026-week-5", web: null, api: "/api/containers/nfl-2026-week-5" } }],
    ["destination missing", { destination: undefined }],
    ["destination null", { destination: null }],
    ["destination to another page", { destination: { kind: "container", slug: "nfl-2026-week-5", web: "/sport/football/nfl", api: "x" } }],
    ["destination for another slug", { destination: { kind: "container", slug: "nfl-2026-week-6", web: "/collections/nfl-2026-week-5", api: "x" } }],
    ["destination of another kind", { destination: { kind: "event", slug: "nfl-2026-week-5", web: "/collections/nfl-2026-week-5", api: "x" } }],
    ["unpublished", { state: "draft" }],
    ["publication state absent", { state: undefined }],
    ["no name", { name: "   " }],
    ["no id", { id: undefined }],
    ["no revision", { revision: null }],
    ["slug disagrees with its edition", { edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 6 } }],
    ["zero-padded week slug", { slug: "nfl-2026-week-05" }],
    ["unknown stage", { edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Wild Card", week: 5 } }],
    ["an edition this ship does not offer", { edition: { kind: "nfl_season", league: "nfl", season: 2026 } }],
    ["no edition", { edition: null }],
    ["nothing in it", { game_count: 0, question_count: 0 }],
    ["a count that is not a count", { game_count: "16" }],
    ["negative count", { game_count: -1 }],
  ];
  it.each(refusals)("refuses: %s", (_label, overrides) => {
    expect(admitCollection(collection(overrides))).toBeNull();
  });

  it("refuses a broken envelope without throwing", () => {
    for (const data of [null, undefined, [], "nfl-2026-week-5", 5]) {
      const item = { type: "collection", score: 1, reason: "", headline: null, data } as unknown as FeedItem;
      expect(() => admitCollection(item)).not.toThrow();
      expect(admitCollection(item)).toBeNull();
    }
    expect(admitCollection(null)).toBeNull();
    expect(admitCollection(game(1))).toBeNull();
  });

  it("an MLB edition on an NFL slug is refused", () => {
    expect(admitCollection(collection({ edition: { kind: "mlb_postseason", league: "mlb", season: 2026 } }))).toBeNull();
  });
});

// ── placement ─────────────────────────────────────────────────────────────────

describe("#9905 placement keeps the server's spot", () => {
  it("control: without the split, sport spacing moves the NFL hub away from its NFL game", () => {
    // What would happen if the hub rode the spacing pass as an NFL card.
    const served = [game(1), collection(), game(7), futures(2), futures(3)];
    const naive = spaceBySport(served, (item) => (item.type === "collection" ? "americanfootball" : categoryOf(item)));
    const ids = naive.map(idOf);
    expect(ids.indexOf("collection-nfl-2026-week-5") + 1).not.toBe(ids.indexOf("event-7"));
  });

  it("the hub stays directly in front of the game it was served before", () => {
    const served = [game(1), collection(), game(7), futures(2), futures(3)];
    const ids = compose(served);
    expect(ids.indexOf("collection-nfl-2026-week-5") + 1).toBe(ids.indexOf("event-7"));
    // Every ordinary card still renders, once.
    expect(ids.filter((id) => id !== "collection-nfl-2026-week-5").sort()).toEqual(
      ["event-1", "event-7", "futures-2", "futures-3"].sort(),
    );
  });

  it("an MLB and an NFL hub each keep their own anchor, and ranking is not the client's", () => {
    const served = [
      futures(1),
      collection({}, "mlb-2026-postseason"),
      game(20, "baseball_mlb"),
      collection(),
      game(7),
      futures(2),
    ];
    const ids = compose(served);
    expect(ids.indexOf("collection-mlb-2026-postseason") + 1).toBe(ids.indexOf("event-20"));
    expect(ids.indexOf("collection-nfl-2026-week-5") + 1).toBe(ids.indexOf("event-7"));
  });

  it("if the anchor is gone (dismissed / stale) the hub sits before the next served card", () => {
    const served = [futures(1), collection(), game(7), futures(2), futures(3)];
    const ids = compose(served, new Set(["event-7"]));
    expect(ids.indexOf("collection-nfl-2026-week-5") + 1).toBe(ids.indexOf("futures-2"));
  });

  it("with nothing after it left, the hub goes last rather than vanishing", () => {
    const served = [futures(1), futures(2), collection(), game(7)];
    const ids = compose(served, new Set(["event-7"]));
    expect(ids[ids.length - 1]).toBe("collection-nfl-2026-week-5");
  });

  it("two hubs in front of one card keep their served order", () => {
    const g: Single[] = [{ type: "single", item: game(7) }];
    const anchored: AnchoredCollection[] = [
      { item: collection({}, "mlb-2026-postseason"), followers: ["event-7"] },
      { item: collection(), followers: ["event-7"] },
    ];
    const ids = placeCollections<Single>(g, anchored, (x) => [idOf(x.item)], (item) => ({ type: "single", item })).map((x) =>
      idOf(x.item),
    );
    expect(ids).toEqual(["collection-mlb-2026-postseason", "collection-nfl-2026-week-5", "event-7"]);
  });

  it("a hub in front of a GROUP lands before the group that holds its anchor", () => {
    type G = { ids: string[] };
    const grouped: G[] = [{ ids: ["futures-1"] }, { ids: ["futures-2", "event-7"] }];
    const out = placeCollections<G>(grouped, [{ item: collection(), followers: ["event-7"] }], (x) => x.ids, (item) => ({ ids: [idOf(item)] }));
    expect(out.map((x) => x.ids[0])).toEqual(["futures-1", "collection-nfl-2026-week-5", "futures-2"]);
  });

  it("a refused collection is dropped alone; every ordinary card survives", () => {
    const served = [game(1), collection({ destination: { kind: "container", slug: "nfl-2026-week-5", web: null, api: "x" } }), game(7), futures(2)];
    const { ordinary, anchored } = splitCollections(served, idOf);
    expect(anchored).toEqual([]);
    expect(ordinary.map(idOf)).toEqual(["event-1", "event-7", "futures-2"]);
    expect(compose(served).sort()).toEqual(["event-1", "event-7", "futures-2"].sort());
  });

  it("a feed with no collections is returned unchanged (same array)", () => {
    const grouped: Single[] = [game(1), futures(2)].map((item) => ({ type: "single", item }));
    expect(placeCollections<Single>(grouped, [], (x) => [idOf(x.item)], (item) => ({ type: "single", item }))).toBe(grouped);
  });
});

// ── render + tap/return ───────────────────────────────────────────────────────

describe("#9905 the card", () => {
  const html = renderToStaticMarkup(<DiscoverCollectionCard entry={admitCollection(collection())!} />);

  it("is one link to the canonical hub, naming it and what it holds", () => {
    expect(html.match(/<a /g)).toHaveLength(1);
    expect(html).toContain('href="/collections/nfl-2026-week-5"');
    expect(html).toContain("NFL 2026 · Week 5");
    expect(html).toContain("16 games · 40 questions");
    expect(html).toContain('data-testid="discover-collection-card"');
  });

  it("carries no price, no like/dismiss control and no house jargon", () => {
    expect(html).not.toMatch(/\d%/);
    expect(html).not.toMatch(/<button/);
    // The reader-visible text nodes only (attributes carry the slug for probes).
    const text = [...html.matchAll(/>([^<]+)</g)].map((m) => m[1]).join(" | ");
    expect(text).toBe("Collection | NFL 2026 · Week 5 | 16 games · 40 questions");
    expect(text).not.toMatch(/like this|matched|slug|published|revision/i);
  });

  it("comes back in the same spot after Back: the restored snapshot composes identically", () => {
    const page1 = [game(1), collection(), game(7), futures(2), collection({}, "mlb-2026-postseason"), game(20, "baseball_mlb")];
    const before = compose(page1);
    const raw = serializeFeedSnapshot({ page1, rest: [], visibleCount: 20, hasMore: true });
    const restored = parseFeedSnapshot<FeedItem>(raw)!;
    expect(compose(restored.page1)).toEqual(before);
    expect(admitCollection(restored.page1[1])?.href).toBe("/collections/nfl-2026-week-5");
  });
});

// ── the page wiring ───────────────────────────────────────────────────────────

describe("#9905 page wiring", () => {
  const PAGE = fs.readFileSync(path.join(process.cwd(), "app/discover/page.tsx"), "utf8");
  const memo = PAGE.slice(PAGE.indexOf("const processedItems = useMemo"), PAGE.indexOf("const suppressedEnvelopes"));

  it("collections leave the pipeline before the renderability filter and return after spacing", () => {
    const split = memo.indexOf("splitCollections(deduped, getItemId)");
    expect(split).toBeGreaterThan(-1);
    expect(split).toBeLessThan(memo.indexOf("feedItemHasRenderableContent"));
    expect(memo.lastIndexOf("placeCollections")).toBeGreaterThan(memo.lastIndexOf("spaceBySport"));
  });

  it("a collection is not counted as a suppressed (unknown) card", () => {
    expect(PAGE).toMatch(/collectSuppressedEnvelopes\([^;]*!isCollectionItem\(item\)/);
  });

  it("the render branch draws the collection card, outside the learning shell", () => {
    // #5105 — the card renderer is shared by the flat list and both sections.
    const loop = PAGE.slice(PAGE.indexOf("const renderFeedCard = (gi: DiscoverGroupedItem, idx: number)"));
    const branch = loop.slice(0, loop.indexOf("const isGuessSlot"));
    expect(branch).toContain("admitCollection(gi.item)");
    expect(branch).toContain("<DiscoverCollectionCard entry={collection} />");
    expect(branch).not.toContain("FeedItemShell");
  });

  it("isCollectionItem only answers for the collection type", () => {
    expect(isCollectionItem(collection())).toBe(true);
    expect(isCollectionItem(game(1))).toBe(false);
    expect(isCollectionItem(undefined)).toBe(false);
  });
});
