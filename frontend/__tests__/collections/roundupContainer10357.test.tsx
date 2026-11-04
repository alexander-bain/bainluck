import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";

function roundupFixture() {
  const rows = [
    {
      id: 53674,
      name: "NFC East Division Winner",
      outcomes: [
        { name: "Giants", probability: 0.5125 },
        { name: "Cowboys", probability: 0.265 },
        { name: "Commanders", probability: 0.1795 },
        { name: "Eagles", probability: 0.0365 },
      ],
    },
    {
      id: 53675,
      name: "AFC West Division Winner",
      outcomes: [
        { name: "Broncos", probability: 0.455 },
        { name: "Chiefs", probability: 0.345 },
        { name: "Chargers", probability: 0.175 },
        { name: "Raiders", probability: 0.025 },
      ],
    },
    {
      id: 53673,
      name: "NFC North Division Winner",
      outcomes: [
        { name: "Lions", probability: 0.435 },
        { name: "Packers", probability: 0.315 },
        { name: "Vikings", probability: 0.165 },
        { name: "Bears", probability: 0.085 },
      ],
    },
    {
      id: 53672,
      name: "NFC South Division Winner",
      outcomes: [
        { name: "Buccaneers", probability: 0.42 },
        { name: "Falcons", probability: 0.31 },
        { name: "Saints", probability: 0.16 },
        { name: "Panthers", probability: 0.11 },
      ],
    },
  ];
  return {
    state: "published",
    slug: "roundup-nfl-division-front-runners",
    revision: 281094123,
    reason: null,
    edition: null,
    container: {
      id: 10357,
      slug: "roundup-nfl-division-front-runners",
      name: "NFL division front-runners",
      kind: "roundup",
      category: "nfl",
      status: "open",
      window_start: null,
      window_end: null,
      parent_container_id: null,
    },
    subtitle: "Bain Luck blend · the 4 closest of 8 divisions",
    sections: [
      {
        class: "title",
        title: "The 4 closest races",
        layout: "field",
        count: 4,
        members: rows.map((r) => ({
          type: "market",
          id: r.id,
          event_id: null,
          destination: {
            kind: "market",
            id: r.id,
            web: `/futures/${r.id}`,
            api: `/api/futures/${r.id}`,
          },
          card: {
            id: r.id,
            name: r.name,
            sport: "americanfootball_nfl",
            sport_name: "NFL",
            category: "sports",
            llm_sport_category: "nfl",
            market_tier: 4,
            market_type_label: "Division",
            market_type: "field",
            status: "open",
            source: "both",
            sources: ["kalshi", "polymarket"],
            source_count: 2,
            outcome_count: 4,
            top_outcomes: r.outcomes,
            prices_updated_at: "2026-11-02T14:00:33+00:00",
          },
        })),
      },
    ],
    member_count: 4,
    withheld: [],
    withheld_count: 0,
    children: [],
    assembled: true,
  };
}

beforeEach(() => forgetAcceptedCollections());

test("reader honors the served section title for kind: roundup and renders all four division cards in order", () => {
  const raw = roundupFixture();
  const hub = parseCollection(raw, raw.slug);
  expect(hub.title).toBe("NFL division front-runners");
  expect(hub.subtitle).toBe("Bain Luck blend · the 4 closest of 8 divisions");
  expect(hub.sections).toHaveLength(1);
  expect(hub.sections[0].title).toBe("The 4 closest races");
  expect(hub.members.map((m) => m.id)).toEqual([53674, 53675, 53673, 53672]);

  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
  expect(html).toContain("NFL division front-runners");
  expect(html).toContain("Bain Luck blend · the 4 closest of 8 divisions");
  expect(html).toContain("The 4 closest races");
  expect(html.indexOf("NFC East Division Winner")).toBeLessThan(html.indexOf("AFC West Division Winner"));
  expect(html.indexOf("AFC West Division Winner")).toBeLessThan(html.indexOf("NFC North Division Winner"));
  expect(html.indexOf("NFC North Division Winner")).toBeLessThan(html.indexOf("NFC South Division Winner"));
});

test("reader text says market, never question, and names no venue in any sentence on the page", () => {
  const raw = roundupFixture();
  const hub = parseCollection(raw, raw.slug);
  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
  const plain = html.replace(/<[^>]*>/g, " ");
  expect(plain).not.toMatch(/\bquestions?\b/i);
  expect(plain).not.toMatch(/\b(kalshi|polymarket|sportsbooks?)\b/i);

  const partialHub = parseCollection({ ...raw, withheld_count: 1 }, raw.slug);
  expect(partialHub.note).toBe("Some markets aren't available right now.");
  expect(partialHub.note).not.toMatch(/\bquestions?\b/i);
});

test("midterms collection parsing and section titles remain unaffected", () => {
  const midterms = {
    state: "published",
    slug: "midterms-2026",
    revision: 1,
    edition: { kind: "midterms", league: "politics", season: 2026 },
    subtitle: "Who controls Congress, the closest Senate races and the governors' mansions - updated live, settled as results come in.",
    container: { id: 901, name: "Midterms 2026", slug: "midterms-2026" },
    children: [],
    sections: [
      {
        class: "senate_races",
        title: "The closest Senate races",
        layout: "duel",
        count: 1,
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
              source: "both",
              outcome_count: 2,
              top_outcomes: [
                { name: "Susan Collins", probability: 0.585 },
                { name: "Graham Platner", probability: 0.415 },
              ],
            },
          },
        ],
      },
    ],
    member_count: 1,
    withheld: [],
    withheld_count: 0,
  };
  const hub = parseCollection(midterms, "midterms-2026");
  expect(hub.edition).toBe("2026 elections");
  expect(hub.sections[0].title).toBe("The closest Senate races");
  expect(hub.sections[0].layout).toBe("duel");
});

test("same_deadline_board container ('by-december-31') renders all six binary markets in highest-first order with single-venue attribution", () => {
  const dec31Rows = [
    { id: 62162058, name: "Next Claude Opus (5.6+) released by December 31, 2026?", prob: 0.885, cat: "tech" },
    { id: 27594137, name: "Trump meets with Putin by December 31?", prob: 0.83, cat: "politics" },
    { id: 30587891, name: "Will Banksy create a new mural or street artwork by December 31?", prob: 0.47, cat: "entertainment" },
    { id: 8422080, name: "Pete Hegseth out as Secretary of Defense by December 31?", prob: 0.40, cat: "geopolitics" },
    { id: 13791228, name: "SCOTUS accepts sports event contract case by December 31, 2026?", prob: 0.205, cat: "legal" },
    { id: 13794660, name: "Will Samuel Alito announce his retirement by December 31, 2026?", prob: 0.185, cat: "politics" },
  ];
  const raw = {
    state: "published",
    slug: "by-december-31",
    revision: 91238411,
    reason: null,
    edition: null,
    container: {
      id: 2918471,
      slug: "by-december-31",
      name: "By December 31",
      kind: "roundup",
      category: "cross-topic",
      status: "open",
      window_start: null,
      window_end: null,
      parent_container_id: null,
    },
    subtitle: "Separate markets that settle by the same day.",
    sections: [
      {
        class: "title",
        title: "Markets settling by December 31",
        layout: "field",
        count: 6,
        members: dec31Rows.map((r) => ({
          type: "market",
          id: r.id,
          event_id: null,
          destination: { kind: "market", id: r.id, web: `/futures/${r.id}`, api: `/api/futures/${r.id}` },
          card: {
            id: r.id,
            name: r.name,
            category: r.cat,
            llm_sport_category: r.cat,
            market_tier: 2,
            market_type_label: "Yes / No",
            market_type: "yes_no",
            status: "open",
            source: "polymarket",
            sources: ["polymarket"],
            source_count: 1,
            outcome_count: 2,
            top_outcomes: [
              { id: r.id * 10 + 1, name: "Yes", probability: r.prob, rank: 1 },
              { id: r.id * 10 + 2, name: "No", probability: 1 - r.prob, rank: 2 },
            ],
            prices_updated_at: "2026-11-03T22:30:00+00:00",
          },
        })),
      },
    ],
    member_count: 6,
    withheld: [],
    withheld_count: 0,
    children: [],
    assembled: true,
  };
  const hub = parseCollection(raw, "by-december-31");
  expect(hub.title).toBe("By December 31");
  expect(hub.subtitle).toBe("Separate markets that settle by the same day.");
  expect(hub.members.map((m) => m.id)).toEqual(dec31Rows.map((r) => r.id));

  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug="by-december-31" />);
  expect(html).toContain("By December 31");
  expect(html).toContain("Separate markets that settle by the same day.");
  expect(html).toContain("Markets settling by December 31");
  for (const r of dec31Rows) {
    expect(html).toContain(r.name);
  }
  const plain = html.replace(/<[^>]*>/g, " ");
  expect(plain).not.toMatch(/\bquestions?\b/i);
  expect(plain).not.toMatch(/\b(kalshi|polymarket|sportsbooks?|blend)\b/i);
});
