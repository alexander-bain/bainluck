/**
 * #2603 — Alex, 2026-09-01: "The Discover cards reorder themselves on
 * web-desktop while I'm on the screen."
 *
 * #4430's `reconcilePage1` holds the reader's page-one order across the 120 s
 * revalidation. The next stage, local personalization, re-sorted every window
 * of five past the pinned lead by `card.score + categoryAdjustment(profile)`,
 * reading the FRESH copy's score and the LIVE profile — so a score that moved
 * between ticks, or a like that moved the profile, reshuffled cards on screen.
 *
 * These tests pin: (1) the order is decided by the score a card carried when it
 * entered the edition, (2) the page ranks by that frozen score and a profile
 * snapshot, and the live profile listener never touches the snapshot.
 */

export {};

import * as fs from "fs";
import * as path from "path";
import { applyLocalPersonalization, recordEditionScores, runManualRefresh } from "@/lib/discover/editionOrder";
import { reconcilePage1 } from "@/lib/discover/feedPaging";
import type { DiscoverProfile, ProfileBucket } from "@/lib/discoverInteractions";

type Card = { id: string; score: number; category: string };

const bucket = (score: number, likes: number): ProfileBucket => ({
  score,
  impressions: 10,
  clicks: 2,
  likes,
  dismisses: 0,
  shares: 0,
  last_interaction_at: "2026-09-24T16:00:00Z",
});

const profile: DiscoverProfile = {
  categories: { politics: bucket(0, 0) },
  updated_at: "2026-09-24T16:00:00Z",
};

// Three pinned lead cards, then one window of five.
const edition: Card[] = [
  { id: "lead-1", score: 99, category: "politics" },
  { id: "lead-2", score: 98, category: "politics" },
  { id: "lead-3", score: 97, category: "politics" },
  { id: "a", score: 80, category: "baseball" },
  { id: "b", score: 78, category: "baseball" },
  { id: "c", score: 70, category: "politics" },
  { id: "d", score: 50, category: "politics" },
  { id: "e", score: 40, category: "politics" },
];

const ids = (cards: Card[]) => cards.map((c) => c.id);
const liveRank = (c: Card) => ({ score: c.score, category: c.category });

describe("#2603 — a background tick never reorders the edition", () => {
  it("control: ranking by the LIVE score reorders cards when a score moves between ticks", () => {
    const first = applyLocalPersonalization(edition, profile, liveRank);
    expect(ids(first)).toEqual(["lead-1", "lead-2", "lead-3", "a", "b", "c", "d", "e"]);

    // Next tick: game b is now "starting soon" and the server scores it 82.
    const tick = edition.map((c) => (c.id === "b" ? { ...c, score: 82 } : c));
    const second = applyLocalPersonalization(tick, profile, liveRank);
    expect(ids(second)).toEqual(["lead-1", "lead-2", "lead-3", "b", "a", "c", "d", "e"]);
  });

  it("ranking by the EDITION score holds every card in place across the same tick", () => {
    const scores = new Map<string, number>();
    recordEditionScores(scores, edition, (c) => c.id);
    const editionRank = (c: Card) => ({ score: scores.get(c.id) ?? c.score, category: c.category });
    const first = applyLocalPersonalization(edition, profile, editionRank);

    const tick = edition.map((c) => (c.id === "b" ? { ...c, score: 82 } : c));
    recordEditionScores(scores, tick, (c) => c.id);
    const second = applyLocalPersonalization(tick, profile, editionRank);

    expect(ids(second)).toEqual(ids(first));
    // The fresh copy still reaches the render — only its PLACE is frozen.
    expect(second.find((c) => c.id === "b")?.score).toBe(82);
  });

  it("recordEditionScores is first-write-wins and admits cards that arrive later", () => {
    const scores = new Map<string, number>();
    recordEditionScores(scores, [{ id: "x", score: 10 }], (c) => c.id);
    recordEditionScores(scores, [{ id: "x", score: 90 }, { id: "y", score: 5 }], (c) => c.id);
    expect(scores.get("x")).toBe(10);
    expect(scores.get("y")).toBe(5);
  });

  it("a like that moves the profile reorders only when the page ranks by the live profile", () => {
    const liked: DiscoverProfile = {
      categories: { ...profile.categories, politics: bucket(12, 3) },
      updated_at: "2026-09-24T16:05:00Z",
    };
    const before = applyLocalPersonalization(edition, profile, liveRank);
    const afterLike = applyLocalPersonalization(edition, liked, liveRank);
    // Control: the pass is profile-sensitive, which is why the page must hand
    // it a snapshot rather than the live profile.
    expect(ids(afterLike)).not.toEqual(ids(before));
  });

  it("no profile yet leaves the served order untouched", () => {
    expect(ids(applyLocalPersonalization(edition, null, liveRank))).toEqual(ids(edition));
  });
});

describe("#2603 — the Discover page ranks by the edition snapshot, not live inputs", () => {
  const src = fs.readFileSync(path.join(__dirname, "../../app/discover/page.tsx"), "utf8");

  it("passes the ordering snapshot, never the live profile, to the personalization pass", () => {
    const call = src.match(/applyLocalPersonalization\(\s*grouped,\s*(\w+)/);
    expect(call?.[1]).toBe("orderingProfile");
  });

  it("ranks by the edition score map", () => {
    expect(src).toMatch(/recordEditionScores\(editionScores, unique, getItemId\)/);
    expect(src).toMatch(/score: editionScores\.get\(getItemId\(item\)\)/);
  });

  it("the discover-profile-updated listener refreshes the live profile only", () => {
    const listener = src.slice(
      src.indexOf("const refreshProfile = () => {"),
      src.indexOf('window.addEventListener("discover-profile-updated"'),
    );
    expect(listener).toContain("setInteractionProfile(");
    expect(listener).not.toContain("setOrderingProfile(");
  });

  it("the refresh handler opens its edition from runManualRefresh, never through reconcilePage1", () => {
    const start = src.indexOf("const handleRefreshFeed");
    const refresh = src.slice(start, src.indexOf("}, [mutateFeed, user]);", start));
    expect(refresh).toContain("runManualRefresh(");
    expect(refresh).toContain("editionScoresRef.current = outcome.scores");
    expect(refresh).toContain("setPage1Items(outcome.page1)");
    expect(refresh).not.toContain("reconcilePage1");
    // Nothing is torn down before the outcome is known: the keep branch returns
    // ahead of every reset.
    const keep = refresh.indexOf('if (outcome.kind === "keep")');
    for (const reset of ["setAllItems([])", "setPage1Items(", "clearFeedRestore()", "setVisibleCount(PAGE_SIZE)"]) {
      expect(refresh.indexOf(reset)).toBeGreaterThan(keep);
    }
  });
});

describe("#2603 / CERT-3393 — a manual refresh opens a new edition; a failed one keeps the old", () => {
  type Item = { id: string; score: number };
  const getId = (i: Item) => i.id;
  const accept = () => ({ acceptItems: true, hasMore: true, showUnavailable: false });

  // The reader's edition after two background ticks: A, B, C held in place,
  // D appended, C later dropped by the server but still held.
  const oldPage1: Item[] = reconcilePage1(
    reconcilePage1([], [{ id: "A", score: 90 }, { id: "B", score: 80 }, { id: "C", score: 70 }], getId),
    [{ id: "A", score: 60 }, { id: "B", score: 95 }, { id: "D", score: 50 }],
    getId,
  );
  const oldScores = new Map<string, number>();
  recordEditionScores(oldScores, oldPage1, getId);

  // The server's re-ranked page one at refresh time.
  const reranked: Item[] = [{ id: "B", score: 99 }, { id: "E", score: 85 }, { id: "A", score: 40 }];

  it("control: the background path keeps the old ids in the old order and only appends", () => {
    expect(ids2(oldPage1)).toEqual(["A", "B", "C", "D"]);
    expect(ids2(reconcilePage1(oldPage1, reranked, getId))).toEqual(["A", "B", "C", "D", "E"]);
  });

  it("an accepted refresh replaces page one with the re-ranked response and reseeds scores from it alone", async () => {
    const outcome = await runManualRefresh({ fetchPage: async () => ({ items: reranked }), decide: accept, getId });
    expect(outcome.kind).toBe("new-edition");
    if (outcome.kind !== "new-edition") return;
    expect(ids2(outcome.page1)).toEqual(["B", "E", "A"]);
    expect(outcome.scores.get("A")).toBe(40); // not the old edition's 90
    expect(outcome.scores.has("C")).toBe(false);
    expect(outcome.scores.has("D")).toBe(false);
    expect(outcome.hasMore).toBe(true);
  });

  it("a thrown fetch keeps the old edition and raises the retry notice", async () => {
    const outcome = await runManualRefresh<{ items?: Item[] }, Item>({
      fetchPage: async () => { throw new Error("Failed to fetch"); },
      decide: accept,
      getId,
    });
    expect(outcome).toEqual({ kind: "keep", showUnavailable: true });
  });

  it("an unavailable payload keeps the old edition", async () => {
    const outcome = await runManualRefresh({
      fetchPage: async () => ({ items: [] as Item[] }),
      decide: () => ({ acceptItems: false, hasMore: true, showUnavailable: true }),
      getId,
    });
    expect(outcome).toEqual({ kind: "keep", showUnavailable: true });
  });

  it("an accepted but empty page does not blank the reader's edition", async () => {
    const outcome = await runManualRefresh({ fetchPage: async () => ({ items: [] as Item[] }), decide: accept, getId });
    expect(outcome).toEqual({ kind: "keep", showUnavailable: false });
  });
});

function ids2(items: { id: string }[]) {
  return items.map((i) => i.id);
}
