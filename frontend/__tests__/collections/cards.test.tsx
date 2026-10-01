import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => ReactLib.createElement("a", { href, ...props }, children) };
});
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import { CollectionMemberCard, isRelatedMixedListing } from "@/components/collections/CollectionMemberCard";
import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { nflHub, mlbHub } from "./fixtures";

describe("collection readers see the supplied card facts", () => {
  test("ordinary game and question keep their canonical member destinations", () => {
    const hub = parseCollection(nflHub(), "nfl-2026-week-4");
    const scheduled = renderToStaticMarkup(<CollectionMemberCard member={hub.members[0]} />);
    expect(scheduled).toContain('href="/events/7"');
    expect(scheduled).toContain("60%");
    expect(scheduled).toContain("40%");
    const prop = renderToStaticMarkup(<CollectionMemberCard member={hub.related["event:7"][0]} />);
    expect(prop).toContain('href="/futures/70"');
    expect(prop).toContain("Josh Allen");
    expect(prop).toContain("65%");
  });
  test("settled question says Won while missing price never becomes zero", () => {
    const hub = parseCollection(mlbHub(), "mlb-2026-postseason");
    const settled = renderToStaticMarkup(<CollectionMemberCard member={hub.members[1]} />);
    expect(settled).toContain('href="/futures/81"');
    expect(settled).toContain("Dodgers");
    expect(settled).toContain("Won");
    expect(settled).not.toContain("100%");
    const absent = renderToStaticMarkup(<CollectionMemberCard member={hub.members[2]} />);
    expect(absent).toContain("Probability unavailable");
    expect(absent).not.toContain("0%");
  });
  test("final without an authoritative grade remains explicitly unavailable", () => {
    const raw = mlbHub();
    delete ((raw.sections[1].members[0] as ReturnType<typeof import("./fixtures").question>).card.top_outcomes[0] as { is_winner?: boolean }).is_winner;
    const hub = parseCollection(raw, raw.slug);
    const markup = renderToStaticMarkup(<CollectionMemberCard member={hub.members[1]} />);
    expect(markup).toContain("Result unavailable");
    expect(markup).not.toContain(">Won<");
  });
});

// #10089: Polymarket's mixed game listing (totals, spreads and a team-win leg)
// under its own game repeated the game's winner with a different number.
describe("a game's related mixed listing is a link, not a second winner number", () => {
  // Market 70 (related to game 7, Bills 40% / Chiefs 60%) becomes the served
  // shape of 59911155 "Browns vs. Jets": a Polymarket `field` whose third leg
  // is the away team at a number that differs from the game card's.
  const mixedHub = (patch: Record<string, unknown> = {}) => {
    const raw = nflHub();
    const listing = raw.sections[1].members[0] as ReturnType<typeof import("./fixtures").question>;
    Object.assign(listing.card, { name: "Bills vs. Chiefs", source: "polymarket", market_type: "field", outcome_count: 3,
      top_outcomes: [{ id: 1, name: "O/U 47.5", probability: 0.55, rank: 1 }, { id: 2, name: "Spread -2.5", probability: 0.51, rank: 2 }, { id: 3, name: "Buffalo Bills", probability: 0.41, rank: 3 }] }, patch);
    return parseCollection(raw, raw.slug);
  };
  beforeEach(() => forgetAcceptedCollections());

  test("under its game it is a link to the whole listing with no percentages", () => {
    const hub = mixedHub();
    const game = hub.members.find((m) => m.key === "event:7")!;
    const listing = hub.related["event:7"][0];
    expect(isRelatedMixedListing(listing, game)).toBe(true);
    const markup = renderToStaticMarkup(<CollectionMemberCard member={listing} relatedGame={game} />);
    expect(markup).toContain('href="/futures/70"');
    expect(markup).toContain("Bills vs. Chiefs");
    expect(markup).toContain("3 questions on this game");
    expect(markup).not.toMatch(/\d%/);
  });
  test("on the hub the game keeps its one number and the listing stays one tap away", () => {
    const hub = mixedHub();
    settleCollectionRead(hub.slug, { hub });
    const page = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
    const related = page.slice(page.indexOf("Related questions"));
    expect(related).toContain("data-related-listing-link");
    expect(related).toContain('href="/futures/70"');
    expect(page).not.toContain("41%");
    expect(page).toContain("40%");
  });
  test("a settled listing under its game is the same link, not a second result", () => {
    const hub = mixedHub({ status: "resolved" });
    const markup = renderToStaticMarkup(<CollectionMemberCard member={hub.related["event:7"][0]} relatedGame={hub.members.find((m) => m.key === "event:7")} />);
    expect(markup).toContain("data-related-listing-link");
    expect(markup).not.toContain("Won");
  });
  test.each([
    ["standalone (no game context)", {}, null],
    ["related to a different game", {}, "event:8"],
    ["a Kalshi field ladder under its game", { source: "kalshi" }, "event:7"],
    ["a duel under its game", { market_type: "duel" }, "event:7"],
    ["an unshaped market under its game", { market_type: null }, "event:7"],
  ])("control: %s keeps its existing card and percentages", (_name, patch, gameKey) => {
    const hub = mixedHub(patch);
    const listing = hub.related["event:7"][0];
    const game = gameKey ? hub.members.find((m) => m.key === gameKey) : undefined;
    expect(isRelatedMixedListing(listing, game)).toBe(false);
    const markup = renderToStaticMarkup(<CollectionMemberCard member={listing} relatedGame={game} />);
    expect(markup).not.toContain("data-related-listing-link");
    expect(markup).toContain("Bills vs. Chiefs");
    expect(markup).toMatch(/\d%/);
  });
  test("a non-field related question on the hub keeps its card", () => {
    const hub = parseCollection(nflHub(), "nfl-2026-week-4");
    settleCollectionRead(hub.slug, { hub });
    const page = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
    expect(page).not.toContain("data-related-listing-link");
    expect(page).toContain("Josh Allen");
  });
});
