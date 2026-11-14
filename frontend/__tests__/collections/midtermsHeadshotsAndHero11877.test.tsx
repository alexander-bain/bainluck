/** @jest-environment jsdom */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import CollectionHub from "@/components/collections/CollectionHub";
import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";
import { MidtermsAtlasMemberCard } from "@/components/collections/MidtermsAtlasSection";
import EntityImage from "@/components/EntityImage";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { cleanPersonOutcomeName, isPersonOutcomeName } from "@/lib/eventConceptDisplay";
import * as images from "@/lib/images";
import * as api from "@/lib/api";

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

let mockSwrData: unknown = undefined;
let mockSwrError: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown, fetcher?: () => unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false, mutate: () => {} };
    if (fetcher) void fetcher();
    return { data: mockSwrData, error: mockSwrError, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/components/FuturesChart", () => ({
  FuturesChart: ({
    historyData,
    height,
    historyWithheld,
  }: {
    historyData: unknown[];
    height?: number;
    historyWithheld?: boolean;
  }) => (
    <div
      data-testid="mock-futures-chart"
      data-outcome-count={historyData.length}
      data-height={height}
      data-withheld={historyWithheld ? "true" : "false"}
    />
  ),
}));

const ids = [
  [108620, 108621],
  [108619],
  [109085, 109095],
  [108645, 109918, 108629],
];
const titles = [
  "Congress control",
  "Balance of power",
  "The closest Senate races",
  "Governors",
];

function midtermsFixture() {
  return {
    state: "published",
    slug: "midterms-2026",
    revision: 1,
    edition: { kind: "midterms", league: "politics", season: 2026 },
    subtitle:
      "Who controls Congress, the closest Senate races and the governors' mansions - updated live, settled as results come in.",
    container: { id: 901, name: "Midterms 2026", slug: "midterms-2026" },
    children: [],
    sections: [
      {
        class: "congress_control",
        title: titles[0],
        layout: "party",
        count: 2,
        members: ids[0].map((id) => ({
          type: "market",
          id,
          event_id: null,
          destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
          card: {
            id,
            name: id === 108620 ? "Which party will win the U.S. Senate?" : "Which party will win the U.S. House?",
            status: "open",
            source: "kalshi",
            outcome_count: 2,
            top_outcomes: [
              { name: "Republican", probability: 0.585 },
              { name: "Democratic", probability: 0.415 },
            ],
          },
        })),
      },
      {
        class: "balance_of_power",
        title: titles[1],
        layout: "field",
        count: 1,
        members: [
          {
            type: "market",
            id: 108619,
            event_id: null,
            destination: { kind: "market", id: 108619, web: "/futures/108619", api: "/api/futures/108619" },
            card: {
              id: 108619,
              name: "2026 Midterms: Congress Balance of Power?",
              status: "open",
              source: "kalshi",
              outcome_count: 4,
              top_outcomes: [
                { name: "Democrats sweep", probability: 0.48 },
                { name: "R Senate, D House", probability: 0.34 },
                { name: "Republicans sweep", probability: 0.16 },
                { name: "D Senate, R House", probability: 0.01 },
              ],
            },
          },
        ],
      },
      {
        class: "senate_races",
        title: titles[2],
        layout: "duel",
        count: 2,
        members: [
          {
            type: "market",
            id: 109085,
            event_id: null,
            destination: { kind: "market", id: 109085, web: "/futures/109085", api: "/api/futures/109085" },
            card: {
              id: 109085,
              name: "Maine Senate winner?",
              status: "open",
              source: "kalshi",
              outcome_count: 2,
              top_outcomes: [
                { name: "Susan Collins", probability: 0.54 },
                { name: "Graham Platner", probability: 0.46 },
              ],
            },
          },
          {
            type: "market",
            id: 109095,
            event_id: null,
            destination: { kind: "market", id: 109095, web: "/futures/109095", api: "/api/futures/109095" },
            card: {
              id: 109095,
              name: "Alaska Senate winner?",
              status: "open",
              source: "kalshi",
              outcome_count: 2,
              top_outcomes: [
                { name: "Democratic party", probability: 0.56 },
                { name: "Republican party", probability: 0.43 },
              ],
            },
          },
        ],
      },
      {
        class: "governors",
        title: titles[3],
        layout: "auto",
        count: 3,
        members: [
          {
            type: "market",
            id: 108645,
            event_id: null,
            destination: { kind: "market", id: 108645, web: "/futures/108645", api: "/api/futures/108645" },
            card: {
              id: 108645,
              name: "Georgia Governor winner?",
              status: "open",
              source: "kalshi",
              outcome_count: 5,
              top_outcomes: [
                { name: "Keisha Lance Bottoms", probability: 0.55 },
                { name: "Burt Jones", probability: 0.16 },
                { name: "Rick Jackson", probability: 0.14 },
              ],
            },
          },
          {
            type: "market",
            id: 109918,
            event_id: null,
            destination: { kind: "market", id: 109918, web: "/futures/109918", api: "/api/futures/109918" },
            card: {
              id: 109918,
              name: "Republican wins California Governor race?",
              status: "open",
              source: "kalshi",
              outcome_count: 1,
              top_outcomes: [{ name: "Yes", probability: 0.24 }],
            },
          },
          {
            type: "market",
            id: 108629,
            event_id: null,
            destination: { kind: "market", id: 108629, web: "/futures/108629", api: "/api/futures/108629" },
            card: {
              id: 108629,
              name: "Closest Governor race in 2026?",
              status: "open",
              source: "kalshi",
              outcome_count: 8,
              top_outcomes: [
                { name: "New Hampshire", probability: 0.21 },
                { name: "Georgia", probability: 0.21 },
                { name: "Wisconsin", probability: 0.16 },
              ],
            },
          },
        ],
      },
    ],
    member_count: 8,
    withheld: [],
    withheld_count: 0,
  };
}

describe("Midterms 2026 candidate headshots & hero history chart (#11877)", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    forgetAcceptedCollections();
    mockSwrData = undefined;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    jest.restoreAllMocks();
  });

  test.each(["open", "settled", "atlas-open", "atlas-settled"])(
    "the %s card requests the registered identity and keeps the person's displayed name", async (state) => {
      const wikiSpy = jest.spyOn(images, "getWikipediaImage").mockImplementation(async (name) =>
        name === "Mike Rogers (Michigan politician)" ? "https://upload.wikimedia.org/wikipedia/commons/roger-michigan.jpg" : null);
      const raw = midtermsFixture();
      const row = raw.sections[2].members[0];
      Object.assign(row.card, { name: "Michigan Senate winner?", top_outcomes: [
        { name: "Mike Rogers", probability: .7, image_title: "Mike Rogers (Michigan politician)" },
        { name: "Abdul El-Sayed", probability: .3, image_title: "Abdul El-Sayed" },
      ] });
      if (state.endsWith("settled")) Object.assign(row.card, { status: "resolved", settled_winner: "Mike Rogers" });
      const member = parseCollection(raw, raw.slug).sections[2].members[0];
      await act(async () => {
        root.render(state.startsWith("atlas")
          ? <MidtermsAtlasMemberCard member={member} />
          : <CollectionMemberCard member={member} presentation="duel" />);
        await Promise.resolve();
      });
      expect(wikiSpy).toHaveBeenCalledWith("Mike Rogers (Michigan politician)");
      expect(wikiSpy).not.toHaveBeenCalledWith("Mike Rogers");
      expect(container.querySelector('img[alt="Mike Rogers"]')?.getAttribute("src")).toContain("roger-michigan.jpg");
      expect(container.textContent).not.toContain("Michigan politician");
    },
  );

  test("a changed article identity with the same label starts a fresh lookup", async () => {
    const lookup = jest.spyOn(images, "getWikipediaImage").mockResolvedValue(null);
    await act(async () => {
      root.render(<EntityImage type="wikipedia" name="Mike Rogers" showFallback={false} />);
    });
    await act(async () => {
      root.render(<EntityImage type="wikipedia" name="Mike Rogers" imageTitle="Mike Rogers (Michigan politician)" showFallback={false} />);
    });
    expect(lookup.mock.calls.map(call => call[0])).toEqual(["Mike Rogers", "Mike Rogers (Michigan politician)"]);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('[data-testid="entity-image-placeholder"]')).toBeNull();
  });

  test("isPersonOutcomeName identifies candidate names and excludes parties, states, teams, and binary labels", () => {
    expect(isPersonOutcomeName("Susan Collins")).toBe(true);
    expect(isPersonOutcomeName("Graham Platner")).toBe(true);
    expect(isPersonOutcomeName("Sherrod Brown")).toBe(true);
    expect(isPersonOutcomeName("Keisha Lance Bottoms")).toBe(true);
    expect(isPersonOutcomeName("Abdul El-Sayed")).toBe(true);
    expect(isPersonOutcomeName("Cory Booker (D)")).toBe(true);
    expect(cleanPersonOutcomeName("Cory Booker (D)")).toBe("Cory Booker");

    expect(isPersonOutcomeName("Democratic party")).toBe(false);
    expect(isPersonOutcomeName("Republican party")).toBe(false);
    expect(isPersonOutcomeName("Democrats sweep")).toBe(false);
    expect(isPersonOutcomeName("R Senate, D House")).toBe(false);
    expect(isPersonOutcomeName("New Hampshire")).toBe(false);
    expect(isPersonOutcomeName("South Carolina")).toBe(false);
    expect(isPersonOutcomeName("Georgia")).toBe(false);
    expect(isPersonOutcomeName("Yes")).toBe(false);
    expect(isPersonOutcomeName("No")).toBe(false);
    expect(isPersonOutcomeName("Buffalo Bills")).toBe(false);
  });

  test("person-outcome cards render Wikipedia headshots for leaders and omit the tile completely when Wikipedia has no article", async () => {
    const wikiSpy = jest.spyOn(images, "getWikipediaImage").mockImplementation(async (name: string) => {
      if (name === "Susan Collins") return "https://upload.wikimedia.org/wikipedia/commons/susan_collins.jpg";
      // Keisha Lance Bottoms simulates a missing Wikipedia article -> must render NO tile at all
      return null;
    });

    const raw = midtermsFixture();
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => raw,
    })) as unknown as typeof fetch;
    const hub = parseCollection(raw, raw.slug);
    settleCollectionRead(hub.slug, { hub });

    await act(async () => {
      root.render(<CollectionHub slug={hub.slug} />);
    });
    await act(async () => {
      await Promise.resolve();
    });

    // Only the two person-leader cards (Susan Collins on 109085, Keisha Lance Bottoms on 108645)
    // should query Wikipedia; Alaska (Democratic party), CA Governor (Yes), Closest Governor (New Hampshire),
    // and Balance of Power (Democrats sweep) must not.
    const queriedNames = wikiSpy.mock.calls.map((c) => c[0]);
    expect(queriedNames).toContain("Susan Collins");
    expect(queriedNames).toContain("Keisha Lance Bottoms");
    expect(queriedNames).not.toContain("Democratic party");
    expect(queriedNames).not.toContain("New Hampshire");
    expect(queriedNames).not.toContain("Democrats sweep");
    expect(queriedNames).not.toContain("Yes");

    // Susan Collins renders her Wikipedia headshot <img>
    const imgs = Array.from(container.querySelectorAll("img")) as HTMLImageElement[];
    expect(imgs.map((img) => img.getAttribute("alt"))).toEqual(["Susan Collins"]);
    expect(imgs[0].getAttribute("src")).toContain("susan_collins.jpg");

    // Keisha Lance Bottoms (where Wikipedia returned null) renders NO placeholder/initials tile at all
    expect(container.querySelectorAll('[data-testid="entity-image-placeholder"]')).toHaveLength(0);
    expect(container.querySelectorAll('[data-testid="entity-image-initials"]')).toHaveLength(0);
  });

  test("settled person-outcome card and FeedCard fallback honour the Wikipedia headshot and no-fallback rule", async () => {
    jest.spyOn(images, "getWikipediaImage").mockImplementation(async (name: string) => {
      if (name === "Graham Platner") return null;
      if (name === "Sherrod Brown") return "https://upload.wikimedia.org/wikipedia/commons/sherrod_brown.jpg";
      return null;
    });

    const raw = midtermsFixture();
    // Settled race with Graham Platner (missing Wikipedia image -> no placeholder tile)
    const settledMember = raw.sections[2].members[0];
    Object.assign(settledMember.card, { status: "resolved", settled_winner: "Graham Platner" });
    settledMember.card.top_outcomes.forEach((o) => Object.assign(o, { probability: null }));

    // Unpresented futures member (FeedCard fallback) with Sherrod Brown (has Wikipedia image)
    const feedMember = raw.sections[2].members[1];
    feedMember.card.top_outcomes = [
      { name: "Sherrod Brown", probability: 0.52 },
      { name: "Jon Husted", probability: 0.48 },
    ];

    const hub = parseCollection(raw, raw.slug);

    await act(async () => {
      root.render(
        <div>
          <CollectionMemberCard member={hub.sections[2].members[0]} presentation="duel" />
          <CollectionMemberCard member={hub.sections[2].members[1]} />
        </div>,
      );
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(container.textContent).toContain("Settled - Graham Platner");
    const imgs = Array.from(container.querySelectorAll("img")) as HTMLImageElement[];
    expect(imgs.map((img) => img.getAttribute("alt"))).toEqual(["Sherrod Brown"]);
    expect(container.querySelectorAll('[data-testid="entity-image-placeholder"]')).toHaveLength(0);
  });

  test("Midterms collection hero embeds TwoSidedHistoryTimeline with 'All' (8760h) as default and keeps 24h / 7d toggles working", async () => {
    const historyCalls: Array<{ marketId: number; hours: number; range?: string }> = [];
    mockSwrData = {
      market_id: 108620,
      market_name: "Senate control",
      outcomes: [
        {
          outcome_id: 1,
          outcome_name: "Democratic",
          current_probability: 0.585,
          history: [
            { timestamp: "2026-03-01T00:00:00Z", probability: 0.52 },
            { timestamp: "2026-11-01T00:00:00Z", probability: 0.585 },
          ],
        },
        {
          outcome_id: 2,
          outcome_name: "Republican",
          current_probability: 0.415,
          history: [
            { timestamp: "2026-03-01T00:00:00Z", probability: 0.48 },
            { timestamp: "2026-11-01T00:00:00Z", probability: 0.415 },
          ],
        },
      ],
    };
    jest.spyOn(api, "fetchFuturesHistory").mockImplementation(async (marketId, hours, _s, _t, _i, opts) => {
      historyCalls.push({ marketId, hours: hours ?? 0, range: opts?.range });
      return mockSwrData as Awaited<ReturnType<typeof api.fetchFuturesHistory>>;
    });
    jest.spyOn(images, "getWikipediaImage").mockResolvedValue(null);

    const raw = midtermsFixture();
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => raw,
    })) as unknown as typeof fetch;
    const hub = parseCollection(raw, raw.slug);
    settleCollectionRead(hub.slug, { hub });

    await act(async () => {
      root.render(<CollectionHub slug={hub.slug} />);
      await new Promise((r) => setTimeout(r, 20));
    });

    const timelines = Array.from(
      container.querySelectorAll('[data-testid="two-sided-history-timeline"]'),
    ) as HTMLElement[];
    expect(timelines).toHaveLength(2);
    expect(timelines[0].getAttribute("data-hours")).toBe("8760");
    expect(timelines[1].getAttribute("data-hours")).toBe("8760");

    // Verify "All" button is active by default and 24h / 7d toggles are present
    const senateTimeline = timelines[0];
    const buttons = Array.from(senateTimeline.querySelectorAll("button"));
    expect(buttons.map((b) => b.textContent)).toEqual(["24h", "7d", "All"]);
    expect(buttons[0].getAttribute("aria-pressed")).toBe("false");
    expect(buttons[1].getAttribute("aria-pressed")).toBe("false");
    expect(buttons[2].getAttribute("aria-pressed")).toBe("true");

    // Initial history fetch used hours=8760 and range="full" for both 108620 and 108621
    expect(historyCalls).toEqual(
      expect.arrayContaining([
        { marketId: 108620, hours: 8760, range: "full" },
        { marketId: 108621, hours: 8760, range: "full" },
      ]),
    );

    // Clicking "7d" switches the Senate timeline to 168h
    await act(async () => {
      buttons[1].click();
    });
    expect(senateTimeline.getAttribute("data-hours")).toBe("168");
    expect(buttons[1].getAttribute("aria-pressed")).toBe("true");
    expect(buttons[2].getAttribute("aria-pressed")).toBe("false");

    // Clicking "24h" switches the Senate timeline to 24h
    await act(async () => {
      buttons[0].click();
    });
    expect(senateTimeline.getAttribute("data-hours")).toBe("24");
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
  });

  test("Midterms collection hero keeps timeline visible on settled chambers and shows explicit error state on history fetch failure (#12093)", async () => {
    mockSwrData = {
      market_id: 108620,
      market_name: "Senate control",
      outcomes: [
        {
          outcome_id: 1,
          outcome_name: "Democratic",
          current_probability: 1.0,
          history: [
            { timestamp: "2026-03-01T00:00:00Z", probability: 0.52 },
            { timestamp: "2026-11-01T00:00:00Z", probability: 0.585 },
          ],
        },
      ],
    };
    mockSwrError = null;
    jest.spyOn(api, "fetchFuturesHistory").mockResolvedValue(
      mockSwrData as Awaited<ReturnType<typeof api.fetchFuturesHistory>>,
    );
    jest.spyOn(images, "getWikipediaImage").mockResolvedValue(null);

    const raw = midtermsFixture();
    (raw.sections[0].members[0].card as Record<string, unknown>).status = "resolved";
    (raw.sections[0].members[0].card as Record<string, unknown>).settled_winner = "Democratic Party";
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => raw,
    })) as unknown as typeof fetch;
    const hub = parseCollection(raw, raw.slug);
    settleCollectionRead(hub.slug, { hub });

    await act(async () => {
      root.render(<CollectionHub slug={hub.slug} />);
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(container.textContent).toContain("Settled - Democratic Party");
    expect(
      container.querySelectorAll('[data-testid="two-sided-history-timeline"]'),
    ).toHaveLength(2);

    // When fetchFuturesHistory fails with no data, explicit error notice renders instead of null
    mockSwrData = undefined;
    mockSwrError = new Error("History fetch failed");
    await act(async () => {
      root.render(<CollectionHub slug={hub.slug} />);
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(
      container.querySelectorAll('[data-testid="two-sided-history-timeline-error"]'),
    ).toHaveLength(2);
    expect(container.textContent).toContain("Update interrupted");
    mockSwrError = null;
  });
});
