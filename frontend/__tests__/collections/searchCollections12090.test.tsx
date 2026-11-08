import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import DiscoverCollectionCard from "@/components/discover/DiscoverCollectionCard";
import { admitSearchCollection, typeaheadWithCollections } from "@/lib/discover/collectionFeed";
import { searchAnswerState } from "@/lib/searchAnswerState";

jest.mock("next/link", () => {
  return ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
    React.createElement("a", { href, ...rest }, children);
});

const card = (slug = "nfl-2026-week-10") => ({
  id: 10, slug, name: "NFL 2026 · Week 10 · Nov 12–16", state: "published", revision: 3,
  game_count: 14, question_count: 96,
  destination: { kind: "container", slug, web: `/collections/${slug}` },
});

test.each(["nfl-2026-week-10", "midterms-2026", "roundup-cfp-picture", "ai"])("a published %s search result uses the canonical page", (slug) => {
  const entry = admitSearchCollection(card(slug));
  expect(entry).not.toBeNull();
  const html = renderToStaticMarkup(<DiscoverCollectionCard entry={entry!} />);
  expect(html).toContain(`href="/collections/${slug}"`);
  expect(html).toContain("Nov 12–16");
});

test.each([
  { state: "withdrawn" }, { revision: 0 }, { name: "" },
  { game_count: 0, question_count: 0 }, { slug: "../escape" },
  { destination: { kind: "container", slug: "nfl-2026-week-10", web: "https://elsewhere.example/" } },
])("a malformed or unavailable collection cannot create a search link", (change) => {
  expect(admitSearchCollection({ ...card(), ...change })).toBeNull();
});

test("a collection-only answer renders as present, and a failed lookup stays distinguishable", () => {
  const empty = { hasEvents: false, hasFutures: false, hasTeams: false, hasEventConcepts: false };
  expect(searchAnswerState({ ...empty, hasCollections: true })).toBe("present");
  expect(searchAnswerState({ ...empty, degraded: ["collections"] })).toBe("degraded");
  expect(searchAnswerState(empty)).toBe("empty");
});

test("web typeahead composes collection destinations and removes duplicate links", () => {
  const ordinary = [{ type: "futures" as const, market_id: 1, text: "An ordinary market" }];
  const before = JSON.parse(JSON.stringify(ordinary));
  const combined = typeaheadWithCollections(ordinary, [card()]);
  expect(combined[0]).toEqual({ type: "hub", text: card().name, href: "/collections/nfl-2026-week-10" });
  expect(combined.slice(1)).toEqual(ordinary);
  expect(ordinary).toEqual(before);
  expect(typeaheadWithCollections(combined, [card()])).toEqual(combined);
});
