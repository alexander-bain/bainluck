/**
 * #5342 — a reader can open the exact market already attached to an NFL week.
 *
 * Before: `relate()` folded every attached market under its game and the hub
 * drew only "More on this game" (#10146), which opens the game page. On Week 5
 * (revision 34, saved 2026-10-20 22:02Z, sha256 5791c474…88370c, trimmed of
 * card fields this reader never reads) Polymarket 63294747 "Buccaneers vs.
 * Cowboys: O/U 47.5" carries `destination.web: /futures/63294747`, but the
 * game page serves no row for it, so no page drew a control that reached it.
 * After: a game with a short served list names each attached market as a plain
 * link to its own route, with no number or count; a long list still opens only
 * on the game page, so hundreds of rungs never go inline.
 *
 * Node environment (no jsdom): the hub is read from its first rendered frame,
 * and a link's click handler is captured from the next/link mock.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const clicks = new Map<string, () => void>();
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ href, children, onClick, ...props }: { href: string; children: React.ReactNode; onClick?: () => void }) => {
    if (onClick && (props as Record<string, unknown>)["data-related-market"]) clicks.set(String((props as Record<string, unknown>)["data-related-market"]), onClick);
    return ReactLib.createElement("a", { href, ...props }, children);
  } };
});
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import CollectionHub from "@/components/collections/CollectionHub";
import {
  forgetAcceptedCollections, parseCollection, reconcileCollectionContext, RELATED_LINK_LIMIT, relatedMarketLinks, settleCollectionPage, settleCollectionRead,
} from "@/lib/collections";
import savedWeek5 from "../fixtures/nflWeek5Rev34Container5342.20261020.json";
import { event, nflHub, question } from "./fixtures";

const W5 = "nfl-2026-week-5";
const BUCS = "event:14780554";
const NAMED = "market:63294747";
type Raw = { sections: { class: string; count: number; members: { type: string; id: number; event_id?: number | null; question_ids?: number[]; destination: Record<string, unknown>; card: Record<string, unknown> }[] }[]; member_count: number };
const week5 = (): Raw => JSON.parse(JSON.stringify(savedWeek5));
const draw = (raw: unknown, slug: string) => {
  const hub = parseCollection(raw, slug);
  settleCollectionRead(slug, { hub });
  return { hub, html: renderToStaticMarkup(<CollectionHub slug={slug} />) };
};
const list = (html: string, gameKey: string) => new RegExp(`<ul data-related-markets="${gameKey}"[^>]*>(.*?)</ul>`).exec(html)?.[1] ?? null;
const routes = (segment: string) => segment.match(/href="\/futures\/\d+"/g) ?? [];

beforeEach(() => { forgetAcceptedCollections(); clicks.clear(); });

describe("Week 5 (saved revision 34): the attached O/U 47.5 is one tap from the week", () => {
  test("the named market is a link to its own served route, under its own game", () => {
    const { hub, html } = draw(week5(), W5);
    expect(hub.note).toBeNull();
    const bucs = list(html, BUCS);
    expect(bucs).not.toBeNull();
    expect(bucs).toContain(`<a href="/futures/63294747" data-related-market="${NAMED}"`);
    expect(bucs).toContain("Buccaneers vs. Cowboys: O/U 47.5");
    expect(routes(bucs!)).toHaveLength(9);
  });
  test("the links keep the order the week served them in", () => {
    const raw = week5();
    const served = raw.sections.flatMap((s) => s.members).filter((m) => m.type === "market" && m.event_id === 14780554).map((m) => `market:${m.id}`);
    const { hub, html } = draw(raw, W5);
    const drawn = [...(list(html, BUCS) ?? "").matchAll(/data-related-market="(market:\d+)"/g)].map((m) => m[1]);
    expect(drawn).toHaveLength(9);
    expect(hub.related[BUCS].map((m) => m.key)).toEqual(served);
    expect(drawn).toEqual(served);
    expect(new Set(drawn).size).toBe(9);
  });
  test("every one of the 38 attached markets is drawn once, under the game it was served with", () => {
    const { hub, html } = draw(week5(), W5);
    const drawn = html.match(/data-related-market="market:\d+"/g) ?? [];
    expect(drawn).toHaveLength(38);
    expect(new Set(drawn).size).toBe(38);
    for (const game of hub.members.filter((m) => m.type === "event")) {
      const segment = list(html, game.key) ?? "";
      for (const market of hub.related[game.key]) expect(segment).toContain(`href="${market.href}" data-related-market="${market.key}"`);
    }
  });
  test("grouping is unchanged: 15 game cards, no market card, one section, game links and More on this game kept", () => {
    const { html } = draw(week5(), W5);
    const cards = html.match(/data-collection-member="[^"]+"/g) ?? [];
    expect(cards).toHaveLength(15);
    expect(cards.every((card) => card.startsWith('data-collection-member="event:'))).toBe(true);
    expect(html.match(/<h2 /g)).toHaveLength(1);
    expect(html).toContain("Games and winners");
    expect(html).toContain('href="/events/14780554"');
    expect(html).toMatch(/<a href="\/events\/14780554" data-more-on-game="event:14780554"[^>]*>More on this game/);
    expect(html.match(/data-more-on-game=/g)).toHaveLength(14);
  });
  test("the links print names only: no percentage, result or count, so a resolved or unpriced market claims nothing", () => {
    const { html } = draw(week5(), W5);
    for (const segment of html.match(/<ul data-related-markets="[^"]+"[^>]*>.*?<\/ul>/g) ?? []) {
      expect(segment).not.toMatch(/\d%|Won|Lost|Result|questions/);
    }
  });
  test("control: Bears–Packers has no attached market and draws no list and no More row", () => {
    const { html } = draw(week5(), W5);
    expect(html).toContain('data-collection-member="event:14780556"');
    expect(list(html, "event:14780556")).toBeNull();
    expect(html).not.toContain('data-more-on-game="event:14780556"');
  });
  test("opening a market remembers its game's row, so Back returns to the game it was listed under", () => {
    draw(week5(), W5);
    const stored = new Map<string, string>();
    const g = global as unknown as Record<string, unknown>;
    const saved = { document: g.document, sessionStorage: g.sessionStorage };
    g.document = { getElementById: (id: string) => id === `collection-member-${BUCS}` ? { getBoundingClientRect: () => ({ top: 212 }) } : null };
    g.sessionStorage = { setItem: (key: string, value: string) => stored.set(key, value) };
    try { clicks.get(NAMED)!(); } finally { g.document = saved.document; g.sessionStorage = saved.sessionStorage; }
    expect(JSON.parse(stored.get(`collection-reading:${W5}`)!)).toEqual({ slug: W5, memberKey: BUCS, offset: 212, expanded: [] });
  });
  test("a mid-page game's attached market keeps its non-zero scroll context across a week refresh", () => {
    const midGame = "event:14782156";
    const midMarket = "market:63341312";
    draw(week5(), W5);
    const stored = new Map<string, string>();
    const g = global as unknown as Record<string, unknown>;
    const saved = { document: g.document, sessionStorage: g.sessionStorage };
    g.document = { getElementById: (id: string) => id === `collection-member-${midGame}` ? { getBoundingClientRect: () => ({ top: 148 }) } : null };
    g.sessionStorage = { setItem: (key: string, value: string) => stored.set(key, value) };
    try { clicks.get(midMarket)!(); } finally { g.document = saved.document; g.sessionStorage = saved.sessionStorage; }
    const context = JSON.parse(stored.get(`collection-reading:${W5}`)!);
    expect(context).toEqual({ slug: W5, memberKey: midGame, offset: 148, expanded: [] });
    const refreshed = parseCollection({ ...week5(), revision: 35 }, W5);
    const settled = settleCollectionRead(W5, { hub: refreshed });
    expect(reconcileCollectionContext(context, settled.hub!)).toEqual({ slug: W5, memberKey: midGame, offset: 148, expanded: [] });
  });
});

describe("the inline list is bounded; a long list stays behind the game page (#10146)", () => {
  // Game 7 claims `n` served markets, all attached to it.
  const withRelated = (n: number) => {
    const raw = nflHub();
    const ids = Array.from({ length: n }, (_, index) => 700 + index);
    const game = event(7);
    game.question_ids = ids;
    raw.sections[0].members[0] = game;
    raw.sections[1] = { class: "prop", count: n, members: ids.map((id) => question(id, 7, "open", "americanfootball_nfl")) };
    raw.member_count = 3 + n + 1;
    return raw;
  };
  const pagedThemePage = (
    members: ReturnType<typeof event | typeof question>[],
    nextCursor: string | null,
    totalCount: number,
  ) => ({
    state: "published",
    slug: "ai",
    revision: 12,
    reason: null,
    edition: { kind: "theme_continuing", subject: "ai" },
    container: { id: 9301, kind: "theme", name: "AI", slug: "ai", category: "ai", status: "active", window_start: null, window_end: null, parent_container_id: null },
    children: [],
    sections: [{ class: "side_question", count: members.length, members }],
    member_count: members.length,
    withheld_count: 0,
    withheld: [],
    counts: { eligible_count: totalCount, shown_count: totalCount, withheld_count: 0, inventory_complete: true },
    page: { size: 50, next_cursor: nextCursor },
    revision_moved: false,
  });
  // The bound is the number 12, written as literals: a test that reads the
  // constant follows it to 400 and still passes (lane1 review of 31fe423227).
  test("the limit is 12", () => {
    expect(RELATED_LINK_LIMIT).toBe(12);
  });
  test("exactly 12 attached markets are all linked", () => {
    const { hub, html } = draw(withRelated(12), "nfl-2026-week-4");
    expect(relatedMarketLinks(hub, "event:7")).toHaveLength(12);
    expect(routes(list(html, "event:7") ?? "")).toHaveLength(12);
    expect(html).toContain('data-more-on-game="event:7"');
  });
  test("13 attached markets draw no inline list, only More on this game", () => {
    const { hub, html } = draw(withRelated(13), "nfl-2026-week-4");
    expect(hub.related["event:7"]).toHaveLength(13);
    expect(relatedMarketLinks(hub, "event:7")).toEqual([]);
    expect(html).not.toContain("data-related-market=");
    expect(html).not.toContain('href="/futures/700"');
    expect(html).toContain('data-more-on-game="event:7"');
  });
  test("Load more growing a game from 11 to 12 attached markets folds the new market under the game without a duplicate card", () => {
    const ids = Array.from({ length: 12 }, (_, index) => 700 + index);
    const game = event(7);
    game.question_ids = ids;
    const p1 = parseCollection(
      pagedThemePage([game, ...ids.slice(0, 11).map((id) => question(id, 7))], "WzAsNzEwXQ", 14),
      "ai",
    );
    settleCollectionRead("ai", { hub: p1 });
    const p2 = parseCollection(
      pagedThemePage([question(711, 7), question(801, null)], null, 14),
      "ai",
    );
    const combined = settleCollectionPage("ai", p1, { revision: 12, cursor: "WzAsNzEwXQ" }, p2);
    const html = renderToStaticMarkup(<CollectionHub slug="ai" />);
    expect(combined.related["event:7"].map((m) => m.key)).toEqual(ids.map((id) => `market:${id}`));
    expect(relatedMarketLinks(combined, "event:7")).toHaveLength(12);
    expect(routes(list(html, "event:7") ?? "")).toHaveLength(12);
    expect(html).toContain('data-related-market="market:711"');
    expect(html).not.toContain('data-collection-member="market:711"');
    expect(html).toContain('data-collection-member="market:801"');
  });
  test("Load more growing a game from 12 to 13 attached markets folds all 13 behind More on this game without leaking the 13th as a standalone card", () => {
    const ids = Array.from({ length: 13 }, (_, index) => 700 + index);
    const game = event(7);
    game.question_ids = ids;
    const rawPage1 = pagedThemePage([game, ...ids.slice(0, 12).map((id) => question(id, 7))], "WzAsNzExXQ", 14);
    const p1 = parseCollection(rawPage1, "ai");
    settleCollectionRead("ai", { hub: p1 });
    const beforeHtml = renderToStaticMarkup(<CollectionHub slug="ai" />);
    expect(routes(list(beforeHtml, "event:7") ?? "")).toHaveLength(12);

    const p2 = parseCollection(pagedThemePage([question(712, 7)], null, 14), "ai");
    const combined = settleCollectionPage("ai", p1, { revision: 12, cursor: "WzAsNzExXQ" }, p2);
    const afterHtml = renderToStaticMarkup(<CollectionHub slug="ai" />);
    expect(combined.related["event:7"].map((m) => m.key)).toEqual(ids.map((id) => `market:${id}`));
    expect(relatedMarketLinks(combined, "event:7")).toEqual([]);
    expect(list(afterHtml, "event:7")).toBeNull();
    expect(afterHtml).not.toContain("data-related-market=");
    expect(afterHtml).not.toContain('data-collection-member="market:712"');
    expect(combined.sections.flatMap((s) => s.members).map((m) => m.key)).toEqual(["event:7"]);
    expect(afterHtml).toContain('data-more-on-game="event:7"');

    const refreshed = settleCollectionRead("ai", { hub: parseCollection(rawPage1, "ai") }).hub!;
    expect(refreshed.related["event:7"]).toHaveLength(13);
    expect(refreshed.sections.flatMap((s) => s.members).map((m) => m.key)).toEqual(["event:7"]);
    expect(reconcileCollectionContext({ slug: "ai", memberKey: "event:7", offset: 164, expanded: [] }, refreshed)).toEqual({
      slug: "ai",
      memberKey: "event:7",
      offset: 164,
      expanded: [],
    });
  });
});

describe("destination validation is unchanged: only a served, matching route is linked", () => {
  test.each([
    ["web route for another id", { web: "/futures/99999999" }],
    ["event route on a market", { kind: "event", web: "/events/63294747", api: "/api/events/63294747" }],
    ["api route mismatch", { api: "/api/futures/1" }],
  ])("a member whose destination is a %s is dropped, marked partial and never linked", (_name, patch) => {
    const raw = week5();
    const named = raw.sections.flatMap((s) => s.members).find((m) => m.id === 63294747)!;
    Object.assign(named.destination, patch);
    const { hub, html } = draw(raw, W5);
    expect(hub.note).toBe("Some games or questions aren't available right now.");
    expect(html).not.toContain(NAMED);
    expect(html).not.toContain("63294747");
    expect(routes(list(html, BUCS) ?? "")).toHaveLength(8);
  });
});
