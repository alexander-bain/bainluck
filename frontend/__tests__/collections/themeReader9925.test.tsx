/**
 * #9925 — the AI and Oscars collection reader.
 *
 * Before: `parseCollection` knew only NFL/MLB edition shapes, so the theme
 * route's `{"kind": "theme_continuing", "subject": "ai"}` and
 * `{"kind": "theme_edition", "subject": "oscars", "edition": 2027}` both threw
 * "This collection isn't available right now.", and the reader only ever read
 * the first response — a 132-question collection could never show question 51.
 *
 * After: both theme identities parse (only for the slug the registry builds),
 * `counts.shown_count` is the collection's size, and "Load more" sends the
 * opaque `next_cursor` WITH its revision. Same revision appends; a
 * `revision_moved` answer replaces membership with the new first page; a page
 * that answers a hub that has since moved on is dropped. Refresh keeps the
 * pages already loaded at the same revision, so Back finds a later-page member.
 * A slow refresh answering an EARLIER revision than the one Load more already
 * admitted is refused (refresh and Load more run on separate controllers).
 *
 * Fixtures are shaped like PR #10439's `_serve_theme_page` response at
 * 397f34e381 (the producer is a pinned read-only interface here).
 *
 * `node` environment, no DOM: the component is read through its first rendered
 * frame; every read outcome goes through the real `fetchCollection` and the
 * real settle functions the component calls.
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
import {
  acceptedCollection, fetchCollection, forgetAcceptedCollections, parseCollection, reconcileCollectionContext,
  settleCollectionPage, settleCollectionRead, type CollectionHub as Hub,
} from "@/lib/collections";
import { mlbHub, nflHub } from "./fixtures";

// ── route-shaped fixtures ────────────────────────────────────────────────────
const NAMES: Record<number, string> = {
  101: "OpenAI releases GPT-6 before 2027?", 102: "Will an AI model top the Chatbot Arena leaderboard in December?", 103: "Anthropic valued above $500B?",
  104: "AI-generated song reaches Billboard Hot 100?", 105: "EU AI Act enforcement delayed?", 106: "Nvidia market cap above $6T?",
  201: "Oscars 2027: Best Picture winner?", 202: "Oscars 2027: Best Actress winner?", 203: "Oscars 2027: Most nominations?", 204: "Oscars 2027: Host announced by November?",
};
function market(id: number, probability = 0.42) {
  return { type: "market", id, event_id: null, class: null,
    destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
    card: { id, name: NAMES[id] ?? `Question ${id}?`, sport: null, sport_name: null, llm_sport_category: id < 200 ? "ai" : "awards", source: "kalshi", source_count: 1,
      market_tier: 2, status: "open", resolution_date: null, outcome_count: 1, canonical_market_key: null,
      top_outcomes: [{ id: id * 10, name: "Yes", probability, rank: 1, movement: 0 }] } };
}
const cursor = (rank: number, id: number) => Buffer.from(JSON.stringify([rank, id])).toString("base64url");
type Section = { class: string; ids: number[] };
function themePage(slug: "ai" | "oscars-2027", revision: number, sections: Section[], opts: { next?: string | null; total?: number; complete?: boolean; moved?: boolean; prices?: Record<number, number>; withheld?: number[] } = {}) {
  const ai = slug === "ai";
  const built = sections.map((s) => ({ class: s.class, count: s.ids.length, members: s.ids.map((id) => market(id, opts.prices?.[id])) }));
  const withheld = (opts.withheld ?? []).map((id) => ({ type: "market", id, reason: "row_missing" }));
  return {
    state: "published", slug, revision, reason: null,
    edition: ai ? { kind: "theme_continuing", subject: "ai" } : { kind: "theme_edition", subject: "oscars", edition: 2027 },
    container: { id: ai ? 9301 : 9302, kind: ai ? "theme" : "award_show", name: ai ? "AI" : "Oscars 2027", slug, category: ai ? "ai" : "awards", status: "active", window_start: null, window_end: null, parent_container_id: null },
    children: [], sections: built, member_count: built.reduce((n, s) => n + s.count, 0), withheld, withheld_count: withheld.length,
    assembled: true, known_classes: ["advancement", "side_question", "title"], revision_moved: opts.moved ?? false,
    counts: { shown_count: opts.total ?? 6, eligible_count: (opts.total ?? 6) + 2, withheld_count: { low_quality: 2, public_source_disagreement: 0, row_missing: 0, suppressed: 0 }, inventory_complete: opts.complete ?? true },
    page: { limit: 2, next_cursor: opts.next === undefined ? null : opts.next },
  };
}
// AI: six questions, three pages of two, all `side_question` (rank 2).
const AI_P1 = (rev = 5, o = {}) => themePage("ai", rev, [{ class: "side_question", ids: [101, 102] }], { next: cursor(2, 102), ...o });
const AI_P2 = (rev = 5, o = {}) => themePage("ai", rev, [{ class: "side_question", ids: [103, 104] }], { next: cursor(2, 104), ...o });
const AI_P3 = (rev = 5, o = {}) => themePage("ai", rev, [{ class: "side_question", ids: [105, 106] }], { next: null, ...o });
// Oscars: a page boundary that falls inside a class, and one that crosses into the next.
const OSC_P1 = () => themePage("oscars-2027", 3, [{ class: "title", ids: [201, 202] }], { next: cursor(0, 202), total: 4 });
const OSC_P2 = () => themePage("oscars-2027", 3, [{ class: "advancement", ids: [203] }, { class: "side_question", ids: [204] }], { next: null, total: 4 });

// ── harness ──────────────────────────────────────────────────────────────────
const urls: string[] = [];
const respond = (...bodies: Array<[number, unknown]>) => {
  global.fetch = jest.fn(async (url: string) => {
    urls.push(url);
    const [status, body] = bodies.length > 1 ? bodies.shift()! : bodies[0];
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  }) as unknown as typeof fetch;
};
const refresh = async (slug: string) => {
  try { return settleCollectionRead(slug, { hub: await fetchCollection(slug) }); } catch { return settleCollectionRead(slug, { failed: true }); }
};
// Exactly the component's loadMore: request from the hub's own revision + cursor.
const loadMore = async (slug: string, current: Hub) => {
  const requested = { revision: current.revision!, cursor: current.theme!.nextCursor! };
  return settleCollectionPage(slug, current, requested, await fetchCollection(slug, undefined, requested));
};
const ids = (hub: Hub | null) => hub?.members.map((m) => m.id) ?? [];
const frame = (slug: string) => renderToStaticMarkup(<CollectionHub slug={slug} />);
const cards = (html: string) => (html.match(/data-collection-member="[^"]+"/g) ?? []).map((m) => m.slice('data-collection-member="'.length, -1));

beforeEach(() => { forgetAcceptedCollections(); urls.length = 0; });

// ── identity ─────────────────────────────────────────────────────────────────
describe("both theme edition shapes are accepted for their own slug", () => {
  test("AI: continuing identity, the collection's size from counts, the page's cards as one section", () => {
    const hub = parseCollection(AI_P1(), "ai");
    expect(hub).toMatchObject({ state: "published", title: "AI", edition: "AI · Ongoing", revision: 5, note: null,
      theme: { totalCount: 6, nextCursor: cursor(2, 102), inventoryComplete: true, revisionMoved: false } });
    expect(ids(hub)).toEqual([101, 102]);
    expect(hub.sections.map((s) => s.title)).toEqual(["Questions"]);
  });
  test("Oscars: edition identity, award sections — never the sports 'Championship'/'Advancement' titles", () => {
    const hub = parseCollection(OSC_P2(), "oscars-2027");
    expect(hub.edition).toBe("Oscars · 2027");
    expect(hub.sections.map((s) => s.title)).toEqual(["Nominations", "More questions"]);
    expect(parseCollection(OSC_P1(), "oscars-2027").sections.map((s) => s.title)).toEqual(["Award winners"]);
  });
  test("`member_count` is the page, not the collection: two cards of six is not a partial collection", () => {
    expect(parseCollection(AI_P1(), "ai").note).toBeNull();
  });
  test.each([
    ["a continuing subject with a year", "ai-2026", { kind: "theme_continuing", subject: "ai" }],
    ["an edition whose year is not the slug's", "oscars-2027", { kind: "theme_edition", subject: "oscars", edition: 2028 }],
    ["a subject this reader does not know", "grammys-2027", { kind: "theme_edition", subject: "grammys", edition: 2027 }],
    ["AI wearing the edition shape", "ai", { kind: "theme_edition", subject: "ai", edition: 2026 }],
  ])("refused: %s", (_name, slug, edition) => {
    const body = { ...AI_P1(), slug, edition, container: { ...AI_P1().container, slug } };
    expect(() => parseCollection(body, slug)).toThrow("This collection isn't available right now.");
  });
  test.each([
    ["counts absent", (b: ReturnType<typeof AI_P1>) => ({ ...b, counts: undefined })],
    ["shown_count not a count", (b: ReturnType<typeof AI_P1>) => ({ ...b, counts: { ...b.counts, shown_count: "6" } })],
    ["inventory_complete absent", (b: ReturnType<typeof AI_P1>) => ({ ...b, counts: { ...b.counts, inventory_complete: undefined } })],
    ["page absent", (b: ReturnType<typeof AI_P1>) => ({ ...b, page: undefined })],
    ["cursor not opaque url-safe text", (b: ReturnType<typeof AI_P1>) => ({ ...b, page: { limit: 2, next_cursor: "a&revision=9" } })],
  ])("a theme page without a trustworthy pager is refused, not drawn as complete: %s", (_name, mutate) => {
    expect(() => parseCollection(mutate(AI_P1()), "ai")).toThrow();
  });
});

// ── Load more ────────────────────────────────────────────────────────────────
describe("Load more sends the cursor with its revision and appends only the same revision", () => {
  test("three AI pages read in order, each request carrying the previous page's cursor and revision 5", async () => {
    respond([200, AI_P1()]);
    let hub = (await refresh("ai")).hub!;
    respond([200, AI_P2()]);
    hub = await loadMore("ai", hub);
    respond([200, AI_P3()]);
    hub = await loadMore("ai", hub);
    expect(urls).toEqual([
      "http://fixture.invalid/api/containers/ai",
      `http://fixture.invalid/api/containers/ai?revision=5&cursor=${cursor(2, 102)}`,
      `http://fixture.invalid/api/containers/ai?revision=5&cursor=${cursor(2, 104)}`,
    ]);
    expect(ids(hub)).toEqual([101, 102, 103, 104, 105, 106]);
    expect(hub.sections).toHaveLength(1);
    expect(hub.theme).toMatchObject({ totalCount: 6, nextCursor: null });
    expect(ids(acceptedCollection("ai"))).toEqual([101, 102, 103, 104, 105, 106]);
  });
  test("Oscars: a page continuing a class joins its section; a new class opens the next section in order", async () => {
    respond([200, OSC_P1()]);
    let hub = (await refresh("oscars-2027")).hub!;
    respond([200, OSC_P2()]);
    hub = await loadMore("oscars-2027", hub);
    expect(hub.sections.map((s) => [s.title, s.members.map((m) => m.id)])).toEqual([["Award winners", [201, 202]], ["Nominations", [203]], ["More questions", [204]]]);
    expect(new Set(hub.sections.map((s) => s.key)).size).toBe(3);
  });
  test("revision moved during Load more: the new first page REPLACES — no revision-5 card survives beside revision 6", async () => {
    respond([200, AI_P1()]);
    let hub = (await refresh("ai")).hub!;
    respond([200, AI_P2()]);
    hub = await loadMore("ai", hub);
    // The producer answers a stale revision with page 1 of the live one.
    respond([200, themePage("ai", 6, [{ class: "side_question", ids: [102, 107] }], { next: cursor(2, 107), total: 5, moved: true })]);
    hub = await loadMore("ai", hub);
    expect(hub.revision).toBe(6);
    expect(ids(hub)).toEqual([102, 107]);
    expect(hub.theme).toMatchObject({ totalCount: 5, nextCursor: cursor(2, 107) });
    expect(ids(acceptedCollection("ai"))).toEqual([102, 107]);
  });
  test("control: a page whose revision differs is replaced even if the moved flag were missing", async () => {
    respond([200, AI_P1()]);
    const hub = (await refresh("ai")).hub!;
    respond([200, AI_P2(6)]);
    expect(ids(await loadMore("ai", hub))).toEqual([103, 104]);
  });
  test("a duplicate member across pages is drawn once", async () => {
    respond([200, AI_P1()]);
    const hub = (await refresh("ai")).hub!;
    respond([200, themePage("ai", 5, [{ class: "side_question", ids: [102, 103] }], { next: null })]);
    expect(ids(await loadMore("ai", hub))).toEqual([101, 102, 103]);
  });
});

describe("a page that answers a hub which has moved on is dropped", () => {
  test("a refresh moved the revision while Load more was in flight: the late revision-5 page is not appended to revision 6", async () => {
    respond([200, AI_P1()]);
    const asked = (await refresh("ai")).hub!;
    const requested = { revision: 5, cursor: asked.theme!.nextCursor! };
    respond([200, AI_P1(6, { next: cursor(2, 102) })]);
    const now = (await refresh("ai")).hub!;
    respond([200, AI_P2()]);
    const late = await fetchCollection("ai", undefined, requested);
    expect(settleCollectionPage("ai", now, requested, late)).toBe(now);
    expect(ids(acceptedCollection("ai"))).toEqual([101, 102]);
    expect(acceptedCollection("ai")?.revision).toBe(6);
  });
  // The component runs refresh and Load more on SEPARATE controllers, so each
  // is "current" in its own lane. Inverse of the test above: the OLD answer is
  // the refresh, and it arrives after the page lane admitted a newer revision.
  describe("a late refresh never rolls back a revision the page lane already admitted", () => {
    // Both reads are in flight at once; each answers only when the test says.
    const inFlight = () => {
      const pending: Array<{ url: string; answer: (body: unknown) => void }> = [];
      global.fetch = jest.fn((url: string) => new Promise((resolve) => {
        urls.push(url);
        pending.push({ url, answer: (body) => resolve({ status: 200, ok: true, json: async () => body }) });
      })) as unknown as typeof fetch;
      return pending;
    };
    const race = async (lateRefresh: unknown) => {
      respond([200, AI_P1()]);
      const held = (await refresh("ai")).hub!;
      const pending = inFlight();
      // (1) page-1 refresh leaves while revision 5 is held …
      const refreshing = fetchCollection("ai").then((hub) => settleCollectionRead("ai", { hub }));
      // (2) … then Load more leaves from the same revision-5 hub.
      const requested = { revision: 5, cursor: held.theme!.nextCursor! };
      const paging = fetchCollection("ai", undefined, requested).then((page) => settleCollectionPage("ai", held, requested, page));
      expect(pending.map((p) => p.url)).toEqual(["http://fixture.invalid/api/containers/ai", `http://fixture.invalid/api/containers/ai?revision=5&cursor=${cursor(2, 102)}`]);
      // The page lane answers first: revision moved to 6, membership replaced.
      pending[1].answer(themePage("ai", 6, [{ class: "side_question", ids: [102, 107] }], { next: cursor(2, 107), total: 5, moved: true }));
      const afterPage = await paging;
      expect(afterPage.revision).toBe(6);
      // (3) the slower refresh finally answers.
      pending[0].answer(lateRefresh);
      return { afterPage, late: await refreshing };
    };
    test("held 5 → Load more admits 6 → the refresh's revision-5 answer is refused: list and cursor stay at 6", async () => {
      const { afterPage, late } = await race(AI_P1(5, { prices: { 101: 0.91 } }));
      expect(late.hub).toBe(afterPage);
      expect(late.error).toBeNull();
      expect(late.hub?.revision).toBe(6);
      expect(ids(late.hub)).toEqual([102, 107]);
      expect(late.hub?.theme).toMatchObject({ totalCount: 5, nextCursor: cursor(2, 107) });
      expect(acceptedCollection("ai")).toBe(afterPage);
      expect(cards(frame("ai"))).toEqual(["market:102", "market:107"]);
    });
    test("control: the same late refresh answering a LATER revision (7) is admitted", async () => {
      const { late } = await race(AI_P1(7, { next: cursor(2, 102) }));
      expect(late.hub?.revision).toBe(7);
      expect(ids(late.hub)).toEqual([101, 102]);
      expect(acceptedCollection("ai")?.revision).toBe(7);
    });
    test("control: the same late refresh answering WITHDRAWN still clears the collection", async () => {
      const { late } = await race({ state: "withdrawn", slug: "ai", revision: 5, edition: { kind: "theme_continuing", subject: "ai" }, container: null, sections: [] });
      expect(late.hub?.state).toBe("withdrawn");
      expect(late.hub?.members).toEqual([]);
      expect(acceptedCollection("ai")).toBeNull();
    });
  });
  test("the same page answered twice (double tap) appends once", async () => {
    respond([200, AI_P1()]);
    const asked = (await refresh("ai")).hub!;
    const requested = { revision: 5, cursor: asked.theme!.nextCursor! };
    const page = parseCollection(AI_P2(), "ai");
    const once = settleCollectionPage("ai", asked, requested, page);
    expect(settleCollectionPage("ai", once, requested, page)).toBe(once);
    expect(ids(once)).toEqual([101, 102, 103, 104]);
  });
  test("slug switch: an AI page never lands on the Oscars hub, and the Oscars hub never draws under AI", async () => {
    respond([200, OSC_P1()]);
    const oscars = (await refresh("oscars-2027")).hub!;
    const page = parseCollection(AI_P2(), "ai");
    expect(settleCollectionPage("oscars-2027", oscars, { revision: 3, cursor: oscars.theme!.nextCursor! }, page)).toBe(oscars);
    expect(cards(frame("ai"))).toEqual([]);
    expect(frame("ai")).not.toContain("Oscars 2027");
  });
});

// ── authoritative vs transient ───────────────────────────────────────────────
describe("disappearance replaces; a transient failure keeps the honest last-good collection", () => {
  const twoPages = async () => {
    respond([200, AI_P1()]);
    const hub = (await refresh("ai")).hub!;
    respond([200, AI_P2()]);
    return loadMore("ai", hub);
  };
  test.each([
    ["withdrawn", [200, { state: "withdrawn", slug: "ai", revision: 7, edition: { kind: "theme_continuing", subject: "ai" }, container: null, sections: [] }], "This collection is no longer available."],
    ["unpublished", [200, { state: "unpublished", slug: "ai", revision: null, edition: { kind: "theme_continuing", subject: "ai" }, container: null, sections: [] }], "This collection isn't available yet."],
    ["404", [404, { detail: "Not found" }], "This collection isn't available right now."],
  ] as Array<[string, [number, unknown], string]>)("%s on refresh clears every loaded page", async (_name, answer, note) => {
    await twoPages();
    respond(answer);
    const next = await refresh("ai");
    expect(next.hub?.members).toEqual([]);
    expect(next.hub?.note).toBe(note);
    expect(acceptedCollection("ai")).toBeNull();
  });
  test("withdrawn answering a Load more clears too — the cursor does not outlive the collection", async () => {
    const hub = await twoPages();
    respond([200, { state: "withdrawn", slug: "ai", revision: 7, edition: { kind: "theme_continuing", subject: "ai" }, container: null, sections: [] }]);
    const next = await loadMore("ai", hub);
    expect(next.state).toBe("withdrawn");
    expect(next.members).toEqual([]);
    expect(acceptedCollection("ai")).toBeNull();
  });
  test.each([
    ["503 building", () => respond([503, { detail: { state: "building" } }])],
    ["network failure", () => { global.fetch = jest.fn(async () => { throw new TypeError("network"); }) as unknown as typeof fetch; }],
    ["malformed theme page", () => respond([200, { ...AI_P1(), counts: null }])],
  ])("%s on refresh keeps both loaded pages with an honest error", async (_name, stub) => {
    await twoPages();
    stub();
    const next = await refresh("ai");
    expect(ids(next.hub)).toEqual([101, 102, 103, 104]);
    expect(next.error).toBe("Couldn't refresh this collection. Showing the last update.");
  });
  test("a failed Load more throws to the component and changes nothing accepted", async () => {
    const hub = await twoPages();
    respond([503, { detail: { state: "building" } }]);
    await expect(loadMore("ai", hub)).rejects.toThrow();
    expect(ids(acceptedCollection("ai"))).toEqual([101, 102, 103, 104]);
  });
});

// ── refresh + Back ───────────────────────────────────────────────────────────
describe("member to Back keeps a later-page position", () => {
  const twoPages = async () => {
    respond([200, AI_P1()]);
    const hub = (await refresh("ai")).hub!;
    respond([200, AI_P2()]);
    return loadMore("ai", hub);
  };
  test("Back's first frame draws page 2's card with its member id, and the saved position still resolves", async () => {
    await twoPages();
    const html = frame("ai");
    expect(cards(html)).toEqual(["market:101", "market:102", "market:103", "market:104"]);
    expect(html).toContain('id="collection-member-market:104"');
    const context = reconcileCollectionContext({ slug: "ai", memberKey: "market:104", offset: 120, expanded: [] }, acceptedCollection("ai")!);
    expect(context?.memberKey).toBe("market:104");
  });
  test("the mount's page-1 refresh at the same revision keeps page 2, refreshes page 1's prices, keeps the cursor", async () => {
    await twoPages();
    respond([200, AI_P1(5, { prices: { 101: 0.77 } })]);
    const next = (await refresh("ai")).hub!;
    expect(ids(next)).toEqual([101, 102, 103, 104]);
    const top = (next.members[0].item.data as { top_outcomes: Array<{ probability: number }> }).top_outcomes[0].probability;
    expect(top).toBe(0.77);
    expect(next.theme?.nextCursor).toBe(cursor(2, 104));
    expect(reconcileCollectionContext({ slug: "ai", memberKey: "market:104", offset: 120, expanded: [] }, next)?.memberKey).toBe("market:104");
  });
  test("control: a refresh at a NEW revision replaces, and the page-2 position honestly falls away", async () => {
    await twoPages();
    respond([200, AI_P1(6)]);
    const next = (await refresh("ai")).hub!;
    expect(ids(next)).toEqual([101, 102]);
    expect(reconcileCollectionContext({ slug: "ai", memberKey: "market:104", offset: 120, expanded: [] }, next)?.memberKey).toBeNull();
  });
  test("control: a same-revision refresh naming a member the loaded pages never placed replaces rather than mixes", async () => {
    await twoPages();
    respond([200, themePage("ai", 5, [{ class: "side_question", ids: [101, 199] }], { next: cursor(2, 199) })]);
    expect(ids((await refresh("ai")).hub)).toEqual([101, 199]);
  });
});

// ── what the reader sees ─────────────────────────────────────────────────────
describe("the rendered pager", () => {
  test("count of the whole collection and a Load more control while there is a next page", async () => {
    respond([200, AI_P1()]);
    await refresh("ai");
    const html = frame("ai");
    expect(html).toContain("2 of 6 questions");
    expect(html).toContain("Load more");
    expect(html).toContain("AI · Ongoing");
    expect(html).not.toContain("may not include every question");
  });
  test("no Load more once the last page is in", async () => {
    respond([200, OSC_P1()]);
    const hub = (await refresh("oscars-2027")).hub!;
    respond([200, OSC_P2()]);
    await loadMore("oscars-2027", hub);
    const html = frame("oscars-2027");
    expect(html).toContain("4 of 4 questions");
    expect(html).not.toContain("Load more");
  });
  test("incomplete inventory is said plainly, without a source or health claim", async () => {
    respond([200, AI_P1(5, { complete: false })]);
    await refresh("ai");
    const html = frame("ai");
    expect(html).toContain("This list may not include every question yet.");
    expect(html).not.toMatch(/provider|source|outage|health/i);
  });
  test("no aggregate number for unrelated questions: every percentage on the page belongs to a card", async () => {
    respond([200, AI_P1()]);
    await refresh("ai");
    const html = frame("ai");
    const outside = html.replace(/<div id="collection-member-[^"]+"[\s\S]*?(?=<div id="collection-member-|<div class="flex flex-col items-center)/g, "");
    expect(outside).not.toMatch(/\d+%/);
  });
});

// ── sports unchanged ─────────────────────────────────────────────────────────
describe("NFL and MLB readers are untouched", () => {
  test.each([["nfl-2026-week-4", nflHub], ["mlb-2026-postseason", mlbHub]] as const)("%s parses with no pager and no theme state", (slug, hub) => {
    const parsed = parseCollection(hub(), slug);
    expect(parsed.theme).toBeNull();
    expect(parsed.sections.map((s) => s.title)).toEqual(slug.startsWith("nfl") ? ["Games and winners", "Player and game questions", "Championship"] : ["Games and winners", "Championship"]);
    settleCollectionRead(slug, { hub: parsed });
    const html = frame(slug);
    expect(html).not.toContain("Load more");
    expect(html).not.toContain("data-collection-pager");
  });
  test("a sports refresh still replaces wholesale (no theme merge)", () => {
    settleCollectionRead("nfl-2026-week-4", { hub: parseCollection(nflHub(), "nfl-2026-week-4") });
    const fewer = { ...nflHub(), sections: [nflHub().sections[0]], member_count: 3 };
    expect(settleCollectionRead("nfl-2026-week-4", { hub: parseCollection(fewer, "nfl-2026-week-4") }).hub?.members).toHaveLength(3);
  });
});
