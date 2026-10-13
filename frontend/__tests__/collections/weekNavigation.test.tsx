import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
jest.mock("@/lib/api", () => ({ API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => <a href={href} {...props}>{children}</a> }));
import { fetchCollectionWeekNavigation, parseCollectionWeekNavigation, parseCollection, settleCollectionRead, acceptedCollection, forgetAcceptedCollections } from "@/lib/collections";
import { CollectionWeekLinks } from "@/components/collections/CollectionWeekNavigation";
import { nflHub } from "./fixtures";
const slug = "nfl-2026-week-4";
const link = (week: number, prefix = "", season = 2026) => ({ slug: `nfl-${season}-${prefix}week-${week}`, label: `NFL ${season} · ${prefix}Week ${week}`,
  edition: { kind: "nfl_week", league: "nfl", season, stage: prefix === "preseason-" ? "Pre Season" : prefix === "postseason-" ? "Post Season" : "Regular Season", week },
  destination: { kind: "container", slug: `nfl-${season}-${prefix}week-${week}`, api: `/api/containers/nfl-${season}-${prefix}week-${week}`, web: `/collections/nfl-${season}-${prefix}week-${week}` } });
const payload = () => ({ slug, state: "available", previous: link(3), next: link(6) });
afterEach(() => forgetAcceptedCollections());
test("fresh route metadata becomes accessible canonical controls with an explicit week gap", async () => {
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => payload() })) as unknown as typeof fetch;
  const navigation = await fetchCollectionWeekNavigation(slug);
  expect(global.fetch).toHaveBeenCalledWith(`http://fixture.invalid/api/containers/${slug}/week-navigation`, { cache: "no-store", signal: undefined });
  const html = renderToStaticMarkup(<CollectionWeekLinks navigation={navigation} />);
  expect(html).toContain('href="/collections/nfl-2026-week-6"');
  expect(html).toContain('aria-label="Next available week: NFL 2026 · Week 6"');
  expect(html).toContain("Previous available week"); expect(html).not.toContain("Week 5");
});
test.each([link(4), link(2), link(5, "", 2025), { ...link(5), destination: { ...link(5).destination, web: "/events/1" } }, { ...link(5), edition: { ...link(5).edition, stage: "Unknown" } }])("invalid/self/reversed/other-season destination refuses", (next) => {
  expect(() => parseCollectionWeekNavigation({ ...payload(), next }, slug)).toThrow();
});
test("cross-stage order uses canonical identity", () => {
  const nav = parseCollectionWeekNavigation({ ...payload(), previous: link(4, "preseason-"), next: link(1, "postseason-") }, slug);
  expect(nav.previous?.href).toContain("preseason-week-4"); expect(nav.next?.href).toContain("postseason-week-1");
});
test("failed optional metadata is unknown and cannot clear accepted content", async () => {
  const body = { ...nflHub(), slug, container: { ...nflHub().container, slug }, edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 4 } };
  const hub = parseCollection(body, slug); settleCollectionRead(slug, { hub });
  global.fetch = jest.fn(async () => ({ ok: false })) as unknown as typeof fetch;
  await expect(fetchCollectionWeekNavigation(slug)).rejects.toThrow(); expect(acceptedCollection(slug)).toBe(hub);
  const html = renderToStaticMarkup(<CollectionWeekLinks navigation={{ slug, state: "unavailable", previous: null, next: null }} />);
  expect(html).toContain("available right now"); expect(html).not.toContain("Previous available week");
  expect(renderToStaticMarkup(<CollectionWeekLinks navigation={{ slug, state: "available", previous: null, next: null }} />)).toBe("");
});
