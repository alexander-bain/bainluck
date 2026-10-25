/** @jest-environment jsdom */
/**
 * #9936 — Multi-page collection membership correction and reader return (Back).
 *
 * Exercises the mounted `CollectionHub` component through the full reader loop:
 *   1. Open a multi-page collection at revision 5, load page 2, and open a
 *      page-2 market (`market:104`).
 *   2. Withdraw `market:104` and rebuild at revision 7 (`shown_count: 5`).
 *   3. Return via Back (`CollectionHub` remounts with revision 5 in memory on
 *      frame 1, then settles revision 7 on frame 2):
 *      - frame 2 replaces the hub with page 1 of revision 7 (`[101, 102]`,
 *        `2 of 5 markets`),
 *      - removes the stale `market:104` reading context from `sessionStorage`,
 *      - resets scroll from stale page 2 (`scrollY > 0`) back to `0` so the
 *        reader is not left stranded below a 1-page DOM,
 *      - continues pagination (`Load more`) and `Refresh` coherently at
 *        revision 7 without reviving `market:104`.
 *   4. When a reader returns to a healthy member (`market:102`) whose document
 *      position shifted because an earlier market (`market:101`) above it was
 *      withdrawn at revision 7, frame 2 re-anchors `market:102` at the
 *      remembered viewport offset.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

jest.mock("@/lib/api", () => ({ API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, onClick, ...props }: { href: string; children: React.ReactNode; onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void }) => (
    <a href={href} onClick={(e) => { e.preventDefault(); onClick?.(e); }} {...props}>{children}</a>
  ),
}));
jest.mock("@/components/collections/CollectionMemberCard", () => ({
  CollectionMemberCard: ({ member }: { member: { href: string; key: string } }) => (
    <a href={member.href} onClick={(e) => e.preventDefault()}>{member.key}</a>
  ),
}));

import CollectionHub from "@/components/collections/CollectionHub";
import {
  collectionMemberDomId,
  forgetAcceptedCollections,
  parseCollection,
  settleCollectionRead,
} from "@/lib/collections";

const SLUG = "ai";
const LEFT_AT = 120;
const CARD_STEP = 260;
const FIRST_CARD_DOC_TOP = 420;

const cursor = (rank: number, id: number) =>
  Buffer.from(JSON.stringify([rank, id])).toString("base64url");

function market(id: number, probability = 0.42) {
  return {
    type: "market",
    id,
    event_id: null,
    class: null,
    destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
    card: {
      id,
      name: `AI market ${id}`,
      sport: null,
      sport_name: null,
      llm_sport_category: "ai",
      source: "kalshi",
      source_count: 1,
      market_tier: 2,
      status: "open",
      resolution_date: null,
      outcome_count: 1,
      canonical_market_key: null,
      top_outcomes: [{ id: id * 10, name: "Yes", probability, rank: 1, movement: 0 }],
    },
  };
}

function aiPage(
  revision: number,
  ids: number[],
  opts: { next?: string | null; total?: number; moved?: boolean; prices?: Record<number, number> } = {},
) {
  return {
    state: "published",
    slug: SLUG,
    revision,
    reason: null,
    edition: { kind: "theme_continuing", subject: "ai" },
    container: {
      id: 9301,
      kind: "theme",
      name: "AI",
      slug: SLUG,
      category: "ai",
      status: "active",
      window_start: null,
      window_end: null,
      parent_container_id: null,
    },
    children: [],
    sections: [
      {
        class: "side_question",
        count: ids.length,
        members: ids.map((id) => market(id, opts.prices?.[id])),
      },
    ],
    member_count: ids.length,
    withheld: [],
    withheld_count: 0,
    assembled: true,
    known_classes: ["advancement", "side_question", "title"],
    revision_moved: opts.moved ?? false,
    counts: {
      shown_count: opts.total ?? 6,
      eligible_count: opts.total ?? 6,
      withheld_count: { low_quality: 0, public_source_disagreement: 0, row_missing: 0, suppressed: 0 },
      inventory_complete: true,
    },
    page: { limit: 2, next_cursor: opts.next === undefined ? null : opts.next },
  };
}

const REV5_P1 = () => aiPage(5, [101, 102], { next: cursor(2, 102), total: 6 });
const REV5_P2 = () => aiPage(5, [103, 104], { next: cursor(2, 104), total: 6 });
// Revision 7 after withdrawing market 104: shown_count is 5, page 2 is now [103, 105].
const REV7_P1 = (prices?: Record<number, number>) =>
  aiPage(7, [101, 102], { next: cursor(2, 102), total: 5, prices });
const REV7_P2 = () => aiPage(7, [103, 105], { next: cursor(2, 105), total: 5 });

let root: Root;
let element: HTMLDivElement;
let scrollY: number;
const fetchCalls: string[] = [];

const renderedMembers = () =>
  Array.from(element.querySelectorAll("[data-collection-member]")).map((node) =>
    node.getAttribute("data-collection-member"),
  );

const cardViewportTop = (key: string) =>
  document.getElementById(collectionMemberDomId(key))!.getBoundingClientRect().top;

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  forgetAcceptedCollections();
  sessionStorage.clear();
  fetchCalls.length = 0;
  scrollY = 0;
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY });
  window.scrollTo = jest.fn((options: ScrollToOptions) => {
    scrollY = options.top ?? scrollY;
  }) as unknown as typeof window.scrollTo;
  jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const nodes = Array.from(document.querySelectorAll("[data-collection-member]"));
    const index = nodes.indexOf(this);
    const docTop = index >= 0 ? FIRST_CARD_DOC_TOP + index * CARD_STEP : 0;
    const top = docTop - scrollY;
    return { top, bottom: top + 200 } as DOMRect;
  });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});

afterEach(() => {
  act(() => root.unmount());
  element.remove();
  jest.restoreAllMocks();
  forgetAcceptedCollections();
});

test("multi-page withdrawal + Back return replaces stale page 2, clears withdrawn context, resets scroll, and paginates revision 7 cleanly", async () => {
  // Step 1 & 2: Reader opens /collections/ai at revision 5, loads page 2, and taps market:104.
  const queue: Array<() => unknown> = [() => REV5_P1(), () => REV5_P2()];
  global.fetch = jest.fn(async (url: string) => {
    fetchCalls.push(String(url));
    const body = queue.shift()!();
    return { ok: true, status: 200, json: async () => body };
  }) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  expect(renderedMembers()).toEqual(["market:101", "market:102"]);
  expect(element.textContent).toContain("2 of 6 markets");

  const loadMoreBtn = () =>
    Array.from(element.querySelectorAll("button")).find((b) => b.textContent === "Load more")!;
  await act(async () => {
    loadMoreBtn().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(renderedMembers()).toEqual(["market:101", "market:102", "market:103", "market:104"]);
  expect(element.textContent).toContain("4 of 6 markets");

  // Reader scrolls down to page 2 so market:104 sits at LEFT_AT (120px) in the viewport, then clicks market:104.
  const m104DocTop = FIRST_CARD_DOC_TOP + 3 * CARD_STEP;
  scrollY = m104DocTop - LEFT_AT;
  expect(cardViewportTop("market:104")).toBe(LEFT_AT);

  const m104Link = element.querySelector(
    '[data-collection-member="market:104"] a[href="/futures/104"]',
  )!;
  act(() => {
    m104Link.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(JSON.parse(sessionStorage.getItem("collection-reading:ai") ?? "null")).toEqual({
    slug: SLUG,
    memberKey: "market:104",
    offset: LEFT_AT,
    expanded: [],
  });

  // Unmount to represent navigating to /futures/104 while market:104 is withdrawn & rebuilt at revision 7.
  act(() => root.unmount());
  scrollY = 0;

  // Step 5: Reader returns via Back. Hold the revision-7 network response first to inspect Frame 1 -> Frame 2.
  let resolveRev7!: (value: unknown) => void;
  global.fetch = jest.fn((url: string) => {
    fetchCalls.push(String(url));
    return new Promise((resolve) => {
      resolveRev7 = resolve;
    });
  }) as unknown as typeof fetch;

  root = createRoot(element);
  await act(async () => root.render(<CollectionHub slug={SLUG} />));

  // Frame 1 (before revision 7 resolves): accepted revision-5 hub draws and restores market:104.
  expect(renderedMembers()).toEqual(["market:101", "market:102", "market:103", "market:104"]);
  expect(scrollY).toBe(m104DocTop - LEFT_AT);

  // Frame 2: revision 7 settles with market:104 withdrawn and shown_count = 5.
  await act(async () => {
    resolveRev7({ ok: true, status: 200, json: async () => REV7_P1() });
  });

  expect(renderedMembers()).toEqual(["market:101", "market:102"]);
  expect(element.textContent).toContain("2 of 5 markets");
  expect(element.querySelector('[data-collection-pager="7"]')).not.toBeNull();
  // Scroll is reset to 0 instead of staying at page 2's stale scrollY, and withdrawn market:104 is cleared from storage.
  expect(scrollY).toBe(0);
  expect(sessionStorage.getItem("collection-reading:ai")).toBeNull();

  // Step 6: Reader clicks "Load more" on revision 7 and then "Refresh".
  const postReturnQueue: Array<() => unknown> = [
    () => REV7_P2(),
    () => REV7_P1({ 101: 0.61 }),
  ];
  global.fetch = jest.fn(async (url: string) => {
    fetchCalls.push(String(url));
    const body = postReturnQueue.shift()!();
    return { ok: true, status: 200, json: async () => body };
  }) as unknown as typeof fetch;

  await act(async () => {
    loadMoreBtn().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(fetchCalls[fetchCalls.length - 1]).toContain(
    `revision=7&cursor=${encodeURIComponent(cursor(2, 102))}`,
  );
  expect(renderedMembers()).toEqual(["market:101", "market:102", "market:103", "market:105"]);
  expect(renderedMembers()).not.toContain("market:104");
  expect(element.textContent).toContain("4 of 5 markets");

  const refreshBtn = Array.from(element.querySelectorAll("button")).find(
    (b) => b.textContent === "Refresh",
  )!;
  await act(async () => {
    refreshBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(renderedMembers()).toEqual(["market:101", "market:102", "market:103", "market:105"]);
  expect(renderedMembers()).not.toContain("market:104");
  expect(element.textContent).toContain("4 of 5 markets");
});

test("returning to a healthy member re-anchors its viewport offset when an earlier member above it was withdrawn in revision 7", async () => {
  // Revision 5 has [101, 102] on page 1; reader tapped market:102 (index 1, docTop = 420 + 260 = 680).
  settleCollectionRead(SLUG, { hub: parseCollection(REV5_P1(), SLUG) });
  sessionStorage.setItem(
    `collection-reading:${SLUG}`,
    JSON.stringify({ slug: SLUG, memberKey: "market:102", offset: LEFT_AT, expanded: [] }),
  );

  // In revision 7, market:101 was withdrawn, so page 1 is [102, 103] (market:102 is now index 0, docTop = 420).
  const rev7With101Withdrawn = aiPage(7, [102, 103], { next: cursor(2, 103), total: 5 });
  let resolveRev7!: (value: unknown) => void;
  global.fetch = jest.fn(() => new Promise((resolve) => { resolveRev7 = resolve; })) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  // Frame 1: market:102 is at index 1 (docTop 680), restored to LEFT_AT (scrollY = 560).
  expect(cardViewportTop("market:102")).toBe(LEFT_AT);
  expect(scrollY).toBe(FIRST_CARD_DOC_TOP + CARD_STEP - LEFT_AT);

  // Frame 2: revision 7 removes market:101 above market:102; market:102 shifts to index 0 (docTop 420) and is re-anchored at LEFT_AT (scrollY = 300).
  await act(async () => {
    resolveRev7({ ok: true, status: 200, json: async () => rev7With101Withdrawn });
  });
  expect(renderedMembers()).toEqual(["market:102", "market:103"]);
  expect(cardViewportTop("market:102")).toBe(LEFT_AT);
  expect(scrollY).toBe(FIRST_CARD_DOC_TOP - LEFT_AT);
  expect(JSON.parse(sessionStorage.getItem("collection-reading:ai") ?? "null")).toMatchObject({
    slug: SLUG,
    memberKey: "market:102",
    offset: LEFT_AT,
  });
});

test("a reader who starts scrolling on frame 1 is not yanked when revision 7 arrives on frame 2, while withdrawn storage is still pruned", async () => {
  // Accept 2-page revision 5 in memory and remember page-2 market:104.
  const rev5TwoPages = aiPage(5, [101, 102, 103, 104], { next: cursor(2, 104), total: 6 });
  settleCollectionRead(SLUG, { hub: parseCollection(rev5TwoPages, SLUG) });
  sessionStorage.setItem(
    `collection-reading:${SLUG}`,
    JSON.stringify({ slug: SLUG, memberKey: "market:104", offset: LEFT_AT, expanded: [] }),
  );

  let resolveRev7!: (value: unknown) => void;
  global.fetch = jest.fn(() => new Promise((resolve) => { resolveRev7 = resolve; })) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  // Reader manually scrolls before revision 7 arrives.
  act(() => {
    window.dispatchEvent(new Event("wheel"));
    scrollY = 310;
  });

  await act(async () => {
    resolveRev7({ ok: true, status: 200, json: async () => REV7_P1() });
  });
  expect(renderedMembers()).toEqual(["market:101", "market:102"]);
  expect(sessionStorage.getItem("collection-reading:ai")).toBeNull();
  expect(scrollY).toBe(310);
});

const loadMoreButton = () =>
  Array.from(element.querySelectorAll("button")).find(
    (b) => b.textContent === "Load more" || b.textContent === "Loading…",
  )!;
const refreshButton = () =>
  Array.from(element.querySelectorAll("button")).find((b) => b.textContent === "Refresh")!;

test("settling revision 7 clears a revision-5 pagination error", async () => {
  let refreshed = false;
  global.fetch = jest.fn((url: string) => {
    if (String(url).includes("cursor=")) return Promise.reject(new Error("page 2 failed"));
    const body = refreshed ? REV7_P1() : REV5_P1();
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  }) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  // Load more at revision 5 fails and shows the page error.
  await act(async () => {
    loadMoreButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(element.textContent).toContain("Couldn't load more markets. Please try again.");

  // Refresh settles revision 7 with no Load more in between: the revision-5 error goes with it.
  refreshed = true;
  await act(async () => {
    refreshButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(element.querySelector('[data-collection-pager="7"]')).not.toBeNull();
  expect(element.textContent).not.toContain("Couldn't load more markets. Please try again.");
  expect(element.textContent).toContain("2 of 5 markets");
});

test("settling revision 7 aborts an in-flight revision-5 page read", async () => {
  let refreshed = false;
  let pageSignal: AbortSignal | undefined;
  let resolveSlowPage!: (value: unknown) => void;
  global.fetch = jest.fn((url: string, init?: RequestInit) => {
    if (String(url).includes("cursor=")) {
      pageSignal = init?.signal ?? undefined;
      return new Promise((resolve) => { resolveSlowPage = resolve; });
    }
    const body = refreshed ? REV7_P1() : REV5_P1();
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  }) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  // Load more at revision 5 stays in flight while Refresh settles revision 7.
  act(() => {
    loadMoreButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(loadMoreButton().textContent).toBe("Loading…");
  expect(pageSignal?.aborted).toBe(false);

  refreshed = true;
  await act(async () => {
    refreshButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(element.querySelector('[data-collection-pager="7"]')).not.toBeNull();
  expect(pageSignal?.aborted).toBe(true);
  expect(loadMoreButton().textContent).toBe("Load more");

  // The late revision-5 page answer changes nothing.
  await act(async () => {
    resolveSlowPage({ ok: true, status: 200, json: async () => REV5_P2() });
  });
  expect(renderedMembers()).toEqual(["market:101", "market:102"]);
  expect(element.textContent).toContain("2 of 5 markets");
});

test("a refresh at the same revision leaves an in-flight page read running", async () => {
  let pageSignal: AbortSignal | undefined;
  let resolveSlowPage!: (value: unknown) => void;
  global.fetch = jest.fn((url: string, init?: RequestInit) => {
    if (String(url).includes("cursor=")) {
      pageSignal = init?.signal ?? undefined;
      return new Promise((resolve) => { resolveSlowPage = resolve; });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => REV5_P1() });
  }) as unknown as typeof fetch;

  await act(async () => root.render(<CollectionHub slug={SLUG} />));
  act(() => {
    loadMoreButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await act(async () => {
    refreshButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(pageSignal?.aborted).toBe(false);
  expect(loadMoreButton().textContent).toBe("Loading…");

  await act(async () => {
    resolveSlowPage({ ok: true, status: 200, json: async () => REV5_P2() });
  });
  expect(renderedMembers()).toEqual(["market:101", "market:102", "market:103", "market:104"]);
  expect(element.textContent).toContain("4 of 6 markets");
});
