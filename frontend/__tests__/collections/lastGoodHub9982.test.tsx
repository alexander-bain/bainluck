/**
 * #9982 — Back from a game keeps the accepted hub on screen.
 *
 * Before: CollectionHub started every mount with no hub, so Back from a game
 * (a remount under the Next router) drew "Loading collection…" for the whole
 * re-read — 5–8 s on NFL Week 4 — and any failed refresh (503, timeout,
 * malformed body) erased six good cards. After: the last accepted hub per slug
 * is drawn on the first frame and survives a failed refresh with an honest
 * error; an authoritative 404 / withdrawn / unpublished / empty answer still
 * clears it, and one slug's hub never appears under another.
 *
 * This suite runs in the `node` environment (no jsdom), so the component is
 * exercised through its first rendered frame — exactly the frame a reader sees
 * on Back while the refresh is still pending — and the read outcomes through
 * the real `fetchCollection` against a stubbed `fetch`.
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
import { acceptedCollection, fetchCollection, forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { nflHub } from "./fixtures";

const W4 = "nfl-2026-week-4";
const weekHub = (week: number) => ({ ...nflHub(), slug: `nfl-2026-week-${week}`,
  edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week },
  container: { id: 900 + week, name: `NFL Week ${week}`, slug: `nfl-2026-week-${week}` } });
const cards = (html: string) => html.match(/data-collection-member="[^"]+"/g) ?? [];
const frame = (slug: string) => renderToStaticMarkup(<CollectionHub slug={slug} />);
const accept = (week = 4) => settleCollectionRead(`nfl-2026-week-${week}`, { hub: parseCollection(weekHub(week), `nfl-2026-week-${week}`) });
const respond = (status: number, body: unknown = null) => {
  global.fetch = jest.fn(async () => ({ status, ok: status >= 200 && status < 300, json: async () => body })) as unknown as typeof fetch;
};
// The component's own catch → settle path for a read that throws.
const read = async (slug: string) => {
  try { return settleCollectionRead(slug, { hub: await fetchCollection(slug) }); } catch { return settleCollectionRead(slug, { failed: true }); }
};

beforeEach(() => forgetAcceptedCollections());

describe("Back from a game while the refresh is pending", () => {
  test("the six accepted cards draw on the first frame, with the refresh shown as in progress", () => {
    accept();
    const html = frame(W4);
    expect(cards(html)).toHaveLength(6);
    expect(html).toContain("NFL Week 4");
    expect(html).toContain("Updating…");
    expect(html).not.toContain("Loading collection…");
  });
  test("control: with nothing accepted yet the first frame is the loading state, not invented cards", () => {
    const html = frame(W4);
    expect(cards(html)).toHaveLength(0);
    expect(html).toContain("Loading collection…");
  });
  test("each card keeps its member id, so the saved reading position can find it again", () => {
    accept();
    expect(frame(W4)).toContain('id="collection-member-event:8"');
  });
});

describe("a failed refresh keeps the accepted hub with an honest error", () => {
  test.each([
    ["503", () => respond(503)],
    ["network failure", () => { global.fetch = jest.fn(async () => { throw new TypeError("network"); }) as unknown as typeof fetch; }],
    ["malformed published body", () => respond(200, { ...nflHub(), revision: null })],
  ])("%s", async (_name, stub) => {
    accept();
    stub();
    const next = await read(W4);
    expect(next.hub?.members).toHaveLength(6);
    expect(next.error).toBe("Couldn't refresh this collection. Showing the last update.");
    expect(cards(frame(W4))).toHaveLength(6);
  });
  test("control: a failed first read with nothing accepted shows the error and no cards", async () => {
    respond(503);
    const next = await read(W4);
    expect(next).toEqual({ hub: null, error: "Couldn't load this collection. Please try again." });
  });
  test("a later good read replaces the retained hub and clears the error", async () => {
    accept();
    const raw = nflHub(); raw.sections = raw.sections.slice(0, 1); raw.sections[0].members = raw.sections[0].members.slice(0, 2); raw.sections[0].count = 2; raw.member_count = 2;
    respond(200, raw);
    const next = await read(W4);
    expect(next.error).toBeNull();
    expect(next.hub?.members).toHaveLength(2);
    expect(cards(frame(W4))).toHaveLength(2);
  });
});

describe("an authoritative answer that the hub is gone clears it", () => {
  test.each([
    ["404", 404, null],
    ["200 withdrawn", 200, { ...nflHub(), state: "withdrawn" }],
    ["200 unpublished", 200, { ...nflHub(), state: "unpublished" }],
    ["200 empty", 200, { ...nflHub(), state: "empty" }],
  ])("%s", async (_name, status, body) => {
    accept();
    respond(status, body);
    const next = await read(W4);
    expect(next.error).toBeNull();
    expect(next.hub?.members).toEqual([]);
    expect(next.hub?.note).toBeTruthy();
    expect(acceptedCollection(W4)).toBeNull();
    const html = frame(W4);
    expect(cards(html)).toHaveLength(0);
    expect(html).toContain("Loading collection…");
  });
});

describe("slug isolation", () => {
  test("Week 4's accepted hub never draws under Week 5", () => {
    accept(4);
    const html = frame("nfl-2026-week-5");
    expect(cards(html)).toHaveLength(0);
    expect(html).not.toContain("NFL Week 4");
    expect(html).toContain("Loading collection…");
  });
  test("a failure on Week 5 does not borrow Week 4's hub", async () => {
    accept(4);
    respond(503);
    expect((await read("nfl-2026-week-5")).hub).toBeNull();
  });
  test("a body for another slug is never stored under the requested one", () => {
    settleCollectionRead("nfl-2026-week-5", { hub: parseCollection(weekHub(4), W4) });
    expect(acceptedCollection("nfl-2026-week-5")).toBeNull();
  });
  test("memory stays bounded: the oldest hub is dropped after four", () => {
    for (const week of [1, 2, 3, 4, 5]) accept(week);
    expect(acceptedCollection("nfl-2026-week-1")).toBeNull();
    for (const week of [2, 3, 4, 5]) expect(acceptedCollection(`nfl-2026-week-${week}`)?.slug).toBe(`nfl-2026-week-${week}`);
  });
});
