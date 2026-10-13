/**
 * #10985 — a hub served as ONE unclassified list prints no "More" heading.
 *
 * Every provider-event hub is served as a single `unclassified` section, which
 * the reader titles "More". Printed under the page title, "More" follows
 * nothing. The lone list is named by the page title instead; a hub with real
 * sections still prints "More" after them.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/lib/api", () => ({ ...jest.requireActual("@/lib/api"), API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => ReactLib.createElement("a", { href, ...props }, children) };
});
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { event, nflHub, question } from "./fixtures";

const SLUG = "nfl-2026-week-4";
const frame = (hub: ReturnType<typeof nflHub>) => {
  settleCollectionRead(SLUG, { hub: parseCollection(hub, SLUG) });
  return renderToStaticMarkup(<CollectionHub slug={SLUG} />);
};
const headings = (html: string) => [...html.matchAll(/<h2[^>]*>([^<]*)<\/h2>/g)].map((m) => m[1]);
const cards = (html: string) => html.match(/data-collection-member="[^"]+"/g) ?? [];

beforeEach(() => forgetAcceptedCollections());

test("a hub that is one unclassified list prints no section heading, and the page title names the list", () => {
  const hub = { ...nflHub(), sections: [{ class: "unclassified", count: 2, members: [event(8), event(9)] }], member_count: 2 } as ReturnType<typeof nflHub>;
  const html = frame(hub);
  expect(cards(html)).toHaveLength(2);
  expect(headings(html)).toEqual([]);
  expect(html).not.toMatch(/>More</);
  expect(html).toContain('<h1 id="collection-title"');
  expect(html).toMatch(/<section [^>]*aria-labelledby="collection-title"/);
});

test("control: unclassified after real sections still prints \"More\"", () => {
  const hub = nflHub();
  hub.sections.push({ class: "unclassified", count: 1, members: [question(73, null, "open", "americanfootball_nfl")] });
  hub.member_count = 7;
  const html = frame(hub);
  expect(headings(html)).toEqual(["Games and winners", "Player and game questions", "Championship", "More"]);
  expect(html).not.toMatch(/<section [^>]*aria-labelledby="collection-title"/);
});

test("control: a lone section that is not unclassified keeps its heading", () => {
  const hub = { ...nflHub(), sections: [{ class: "match_winner", count: 2, members: [event(8), event(9)] }], member_count: 2 } as ReturnType<typeof nflHub>;
  expect(headings(frame(hub))).toEqual(["Games and winners"]);
});
