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
import { applyLocalPersonalization, recordEditionScores } from "@/lib/discover/editionOrder";
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

  it("a manual refresh opens a new edition", () => {
    const refresh = src.slice(src.indexOf("const handleRefreshFeed"), src.indexOf("mutateFeed();\n  }, [mutateFeed]);", src.indexOf("const handleRefreshFeed")));
    expect(refresh).toContain("editionScoresRef.current = new Map()");
    expect(refresh).toContain("setOrderingProfile(readDiscoverInteractionProfile())");
  });
});
