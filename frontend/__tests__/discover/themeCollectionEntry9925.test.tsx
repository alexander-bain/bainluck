/**
 * #9925 — A DISCOVER THEME CARD OPENS ITS FULL COLLECTION, AND BACK RETURNS TO IT.
 *
 * SHIP: tap "View collection" on a genuinely eligible Discover theme, browse its
 * complete, automatically maintained page, open a member, and come back to the
 * same place in the feed. Pillars DISCOVER / TRUTH / FORMATTING.
 *
 * The server sends `data.collection_ref = {slug, name, revision,
 * collection_count}` only when it has proved the whole preview sits on that
 * collection's published, complete page (`backend/app/utils/theme_collection_ref.py`).
 * This suite pins the web half:
 *
 * - ADMISSION: a well-formed ref draws one link to the canonical
 *   `/collections/{slug}`, named for the collection (never the card header) and
 *   counting the page's markets (never the preview's). Anything malformed draws
 *   nothing, and a card with no ref is exactly the card it was.
 * - INLINE KEPT: the peek rows, "All N markets" and expand all still work
 *   beside the link, in both states.
 * - DISCOVERCARD PASSES IT: the served bundle's ref and id reach the card.
 * - BACK: a reader who opened the collection from an EXPANDED card finds it
 *   expanded on Back (mounted with effects running — static markup runs none),
 *   so the page's restored scroll offset lands on the same card. Read once,
 *   for that card only, and not after a long gap.
 *
 * Members are the verbatim production payload of 2026-09-09
 * (`__tests__/fixtures/discoverBundles.20260909.json`). The ref on them is
 * SYNTHETIC: no theme collection is published in production yet.
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import type { FeedItem, FeedThemeCollectionRef } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));
const tracked: Array<[string, Record<string, unknown>]> = [];
jest.mock("@/lib/analytics", () => ({
  __esModule: true,
  trackEvent: (name: string, params: Record<string, unknown>) => tracked.push([name, params]),
}));

import { ThemeBundleCard } from "@/components/discover/ThemeBundleCard";
import DiscoverCard from "@/components/DiscoverCard";
import {
  THEME_RETURN_MAX_AGE_MS,
  admitCollectionRef,
  consumeThemeCollectionReturn,
  rememberThemeCollectionReturn,
} from "@/components/discover/shared";
import BUNDLES from "../fixtures/discoverBundles.20260909.json";

const ELECTION = (BUNDLES as { election2028: { data: Record<string, unknown> } }).election2028.data;
const MEMBERS = ELECTION.items as unknown as FeedItem[];
const TITLE = ELECTION.title as string;
const QUESTION = ELECTION.shared_question as string;
const BUNDLE_ID = ELECTION.id as string;

// SYNTHETIC ref (labelled above): the shape the producer writes.
const REF: FeedThemeCollectionRef = { slug: "oscars-2027", name: "Oscars 2027", revision: 7, collection_count: 86 };

// ── sessionStorage double (minimalDom has none) ───────────────────────────────

const store = new Map<string, string>();
beforeAll(() => {
  (globalThis as unknown as { sessionStorage: Storage }).sessionStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    get length() { return store.size; },
  } as Storage;
});
beforeEach(() => {
  store.clear();
  tracked.length = 0;
});

function card(props: Partial<React.ComponentProps<typeof ThemeBundleCard>> = {}): string {
  return renderToStaticMarkup(
    <ThemeBundleCard items={MEMBERS} title={TITLE} sharedQuestion={QUESTION} storyKey="story:election_2028" bundleId={BUNDLE_ID} {...props} />,
  );
}

function collectionLinks(html: string): string[] {
  return Array.from(html.matchAll(/<a [^>]*href="(\/collections\/[^"]*)"/g)).map((m) => m[1]);
}

// ── admission ─────────────────────────────────────────────────────────────────

describe("#9925 admission — one canonical link, or none", () => {
  it("draws the collection's own name and the page's count, to /collections/{slug}", () => {
    const html = card({ collectionRef: REF });
    expect(collectionLinks(html)).toEqual(["/collections/oscars-2027"]);
    expect(html).toContain("View the Oscars 2027 collection");
    expect(html).toContain("86 markets");
    expect(html).not.toContain("86 questions");
    // The header is the card's; the link names the collection, not the header.
    expect(html).not.toContain(`View the ${TITLE} collection`);
  });

  it("says one market, not one markets", () => {
    expect(card({ collectionRef: { ...REF, collection_count: 1 } })).toMatch(/>1 market<|1 market</);
    expect(card({ collectionRef: { ...REF, collection_count: 1 } })).not.toContain("1 markets");
  });

  it("a card with no ref is exactly the card it was", () => {
    expect(card({ collectionRef: undefined })).toBe(card({ collectionRef: null }));
    expect(collectionLinks(card())).toEqual([]);
    expect(card()).not.toContain("View the");
  });

  it.each([
    ["an unsafe slug", { slug: "../admin" }],
    ["a capitalised slug", { slug: "Oscars-2027" }],
    ["an empty name", { name: "  " }],
    ["a zero revision", { revision: 0 }],
    ["a fractional count", { collection_count: 2.5 }],
    ["a zero count", { collection_count: 0 }],
    ["a string count", { collection_count: "86" as unknown as number }],
  ])("refuses %s and draws nothing", (_label, patch) => {
    const bad = { ...REF, ...patch } as FeedThemeCollectionRef;
    expect(admitCollectionRef(bad)).toBeNull();
    expect(collectionLinks(card({ collectionRef: bad }))).toEqual([]);
  });

  it("admits the AI collection too", () => {
    expect(admitCollectionRef({ slug: "ai", name: "AI", revision: 18, collection_count: 579 })).toEqual({
      href: "/collections/ai", name: "AI", count: 579,
    });
  });
});

// ── inline navigation kept ────────────────────────────────────────────────────

describe("#9925 the card keeps its inline peek, expand and member navigation", () => {
  it("keeps every peek row and the expand control beside the link", () => {
    const withRef = card({ collectionRef: REF });
    const without = card();
    // Two members both fit the peek, so the footer reads "Expand" (a bigger
    // bundle reads "All N markets"; the same button either way).
    expect(withRef).toMatch(/>(Expand|All \d+ markets)<\/button>/);
    for (const member of MEMBERS) expect(withRef).toContain(`href="/futures/${(member.data as { id: number }).id}"`);
    // The link is ADDED: removing it leaves the original card byte for byte.
    const link = withRef.match(/<a [^>]*href="\/collections\/oscars-2027"[^>]*>.*?<\/a>/)![0];
    expect(withRef.replace(link, "")).toBe(without);
  });
});

// ── DiscoverCard passes the served ref and id ────────────────────────────────

describe("#9925 DiscoverCard hands the served bundle's ref to the theme card", () => {
  const item = (ref?: FeedThemeCollectionRef) =>
    ({ type: "bundle", score: 50, reason: QUESTION, headline: TITLE, data: { ...ELECTION, kind: "theme", collection_ref: ref } }) as unknown as FeedItem;

  it("links when the bundle carries a ref, and not otherwise", () => {
    const linked = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: item(REF) } as never} />);
    expect(collectionLinks(linked)).toEqual(["/collections/oscars-2027"]);
    const plain = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: item() } as never} />);
    expect(collectionLinks(plain)).toEqual([]);
  });
});

// ── Back: the card comes back as it was left ─────────────────────────────────

describe("#9925 the return mark", () => {
  it("is read once, by the card it names", () => {
    rememberThemeCollectionReturn("a", true, 1_000);
    expect(consumeThemeCollectionReturn("b", 1_001)).toBe(false); // not mine: left alone
    expect(consumeThemeCollectionReturn("a", 1_002)).toBe(true);
    expect(consumeThemeCollectionReturn("a", 1_003)).toBe(false); // forgotten
  });

  it("reopens only a card that was open, and not after a long gap", () => {
    rememberThemeCollectionReturn("a", false, 1_000);
    expect(consumeThemeCollectionReturn("a", 1_001)).toBe(false);
    rememberThemeCollectionReturn("a", true, 1_000);
    expect(consumeThemeCollectionReturn("a", 1_000 + THEME_RETURN_MAX_AGE_MS + 1)).toBe(false);
    store.set("discover-theme-collection-return", "{not json");
    expect(consumeThemeCollectionReturn("a")).toBe(false);
  });
});

type El = HTMLElement & { [k: string]: unknown };
function descendants(node: El): El[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as El))];
}
function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return node[key] as Record<string, (arg?: unknown) => void>;
}

describe("#9925 mounted: open, leave from the expanded card, come Back", () => {
  let host: El;
  let root: ReturnType<typeof createRoot>;
  beforeEach(() => {
    host = document.createElement("div") as unknown as El;
    document.body.appendChild(host);
    root = createRoot(host);
  });
  afterEach(() => {
    act(() => root.unmount());
    document.body.removeChild(host);
  });

  const mount = () =>
    act(() =>
      root.render(
        <ThemeBundleCard items={MEMBERS} title={TITLE} sharedQuestion={QUESTION} storyKey="story:election_2028" bundleId={BUNDLE_ID} collectionRef={REF} />,
      ),
    );
  const text = () => host.textContent ?? "";
  const link = () => descendants(host).find((n) => n.tagName === "A" && n["href"] === "/collections/oscars-2027");
  // The collapsed footer control ("Expand", or "All N markets" on a bigger
  // bundle). It exists only while the card is collapsed.
  const expandButton = () =>
    descendants(host).find((n) => n.tagName === "BUTTON" && /^(Expand|All \d+ markets)$/.test(n.textContent ?? ""));

  it("an expanded card the reader left from comes back expanded, then forgets", () => {
    mount();
    expect(expandButton()).toBeDefined(); // collapsed on arrival
    act(() => reactProps(expandButton()!).onClick());
    expect(expandButton()).toBeUndefined(); // expanded
    expect(link()).toBeDefined(); // the link survives expanding

    act(() => reactProps(link()!).onClick());

    // The page unmounts on navigation and remounts on Back.
    act(() => root.unmount());
    root = createRoot(host);
    mount();
    expect(expandButton()).toBeUndefined(); // reopened before the scroll lands
    expect(text()).toContain("View the Oscars 2027 collection");

    // A later visit is a fresh card.
    act(() => root.unmount());
    root = createRoot(host);
    mount();
    expect(expandButton()).toBeDefined();
  });

  it("a collapsed card the reader left from comes back collapsed", () => {
    mount();
    act(() => reactProps(link()!).onClick());
    act(() => root.unmount());
    root = createRoot(host);
    mount();
    expect(expandButton()).toBeDefined();
  });
});
