/**
 * ux/1070 item 5 — the sports you follow that have no teams.
 *
 * Alex, 2026-09-04: "More PGA. Only 'Golfers to win a PGA Tour major in 2027'
 * shows for a person who follows PGA golf."
 *
 * The server half of the fix admits this week's golf and tennis markets to
 * `/api/feed?my_teams_only=true` on the SPORT follow alone. The page then threw
 * every one of them away, because for as long as My Stuff has existed its first
 * loop has read:
 *
 *     if (item.type === "futures") continue;  // team futures section handles them
 *
 * — true while futures only ever arrived through a TEAM, since those all arrive
 * again, merged and laddered, from `/api/feed/my-team-futures`. A golf market
 * has no team block to arrive in, so the unconditional `continue` would have
 * deleted exactly the markets the server had just gone out of its way to admit:
 * a fix that shipped as no visible change at all.
 *
 * The partition is by sport SHAPE and it is exact rather than heuristic — see
 * `MY_STUFF_TEAM_SPORT_CATEGORIES`.
 */
import {
  MY_STUFF_TEAM_SPORT_CATEGORIES,
  followedSportFutures,
  isFollowedSportFutures,
} from "@/lib/myStuffSections";
import type { FeedItem } from "@/lib/types";

/** A futures item as `/api/feed` serves one; only the read fields matter. */
function futures(over: Record<string, unknown> = {}): FeedItem {
  return {
    type: "futures",
    score: 50,
    data: {
      id: 1,
      name: "Winner",
      llm_sport_category: "golf",
      resolution_date: "2026-09-07T18:00:00Z",
      ...over,
    },
  } as unknown as FeedItem;
}

function gameItem(): FeedItem {
  return {
    type: "event",
    score: 90,
    data: { id: 7, home_team: "Boston Red Sox", away_team: "New York Yankees" },
  } as unknown as FeedItem;
}

/**
 * A non-futures item that DOES carry a sport category.
 *
 * No shape in the `FeedItem` union carries `llm_sport_category` today except
 * `FeedFuturesData`, so the `item.type` check currently costs nothing — which is
 * exactly why it would be deleted as dead code by someone reading only the
 * union. It is not dead: My Stuff serves `tournament` and `concept` items
 * alongside futures, both of which are about a sport and neither of which
 * belongs in this section. The DP World Tour tournament card in particular is
 * already rendered as its own card, and would print twice.
 */
function categorisedNonFutures(type: string): FeedItem {
  return {
    type,
    score: 80,
    data: {
      id: 9,
      name: "Omega European Masters",
      llm_sport_category: "golf",
      resolution_date: "2026-09-07T18:00:00Z",
    },
  } as unknown as FeedItem;
}

describe("isFollowedSportFutures", () => {
  it("keeps this week's golf grid, which has no team block to live in", () => {
    for (const name of [
      "Winner",
      "Top 5 Finish",
      "Top 10 Finish",
      "Top 20 Finish",
      "Make the Cut",
    ]) {
      expect(isFollowedSportFutures(futures({ name }))).toBe(true);
    }
  });

  it("keeps tennis on the same footing", () => {
    expect(isFollowedSportFutures(futures({ llm_sport_category: "tennis" }))).toBe(true);
  });

  it("drops team-sport futures, which the team section renders from its own endpoint", () => {
    // Not a style preference — this is the double-print. "AL Pennant Winner"
    // arrives here AND in the laddered Red Sox block, and only one of the two
    // knows how to merge its sources.
    for (const category of MY_STUFF_TEAM_SPORT_CATEGORIES) {
      expect(isFollowedSportFutures(futures({ llm_sport_category: category }))).toBe(
        false,
      );
    }
  });

  it("mirrors the server's own team-sport set exactly", () => {
    // MY_STUFF_ALLOWED_CATEGORIES in backend/app/routes/feed.py. A category here
    // that the server admits on a follow is dropped by this page; a category
    // missing here prints twice. Both failures are silent, so the set is pinned
    // rather than described.
    expect([...MY_STUFF_TEAM_SPORT_CATEGORIES].sort()).toEqual([
      "baseball",
      "basketball",
      "football",
      "hockey",
      "mma",
      "soccer",
    ]);
  });

  it("is not a filter on everything — only futures items are candidates", () => {
    // The section renders `FeedCard`s of one shape. A game reaching it would be
    // both wrong and a second copy: games are already grouped Live/Upcoming.
    expect(isFollowedSportFutures(gameItem())).toBe(false);
  });

  it("refuses a tournament or concept card even when it names a sport", () => {
    // The `item.type` check, pinned against being read as dead code. Both of
    // these are golf, both are on My Stuff already with their own rendering,
    // and both would print a second time here.
    for (const type of ["tournament", "concept", "bundle", "event"]) {
      expect(isFollowedSportFutures(categorisedNonFutures(type))).toBe(false);
    }
    expect(followedSportFutures([categorisedNonFutures("tournament")])).toEqual([]);
  });

  it("treats an unlabelled market as not-yours", () => {
    // The server admits on a category it could name. A market arriving here
    // without one did not come through the follow path, and guessing that it
    // did is how a page that promises your sports fills with everything else.
    expect(isFollowedSportFutures(futures({ llm_sport_category: null }))).toBe(false);
    expect(isFollowedSportFutures(futures({ llm_sport_category: "" }))).toBe(false);
    expect(isFollowedSportFutures(futures({ llm_sport_category: 7 }))).toBe(false);
  });

  it("does not let casing or padding make baseball a new sport", () => {
    expect(isFollowedSportFutures(futures({ llm_sport_category: "Baseball" }))).toBe(
      false,
    );
    expect(isFollowedSportFutures(futures({ llm_sport_category: " BASEBALL " }))).toBe(
      false,
    );
  });
});

describe("followedSportFutures", () => {
  it("leads with the tournament that finishes first", () => {
    // Resolution order, not score order: the section answers "what is on now".
    // Sunday's final round outranks a market that settles in a fortnight even
    // when the fortnight one scores higher, which is why `score` is inverted
    // against `resolution_date` here.
    const result = followedSportFutures([
      futures({ id: 1, resolution_date: "2026-09-18T12:00:00Z", score: 99 }),
      gameItem(),
      futures({ id: 2, resolution_date: "2026-09-07T18:00:00Z", score: 10 }),
      futures({ id: 3, llm_sport_category: "baseball", resolution_date: "2026-09-05T00:00:00Z" }),
    ]);
    expect(result.map((i) => (i.data as { id: number }).id)).toEqual([2, 1]);
  });

  it("sorts undated markets last, never first", () => {
    // A missing date is not a reason to headline a card. Sorting NaN naively
    // puts it wherever the comparator lands, which on V8 means "first" often
    // enough to be a bug and rarely enough to survive review.
    const result = followedSportFutures([
      futures({ id: 1, resolution_date: null }),
      futures({ id: 2, resolution_date: "2026-09-07T18:00:00Z" }),
      futures({ id: 3, resolution_date: "not a date" }),
    ]);
    expect(result.map((i) => (i.data as { id: number }).id)).toEqual([2, 1, 3]);
  });

  it("returns nothing when the viewer follows only team sports", () => {
    // The empty case is the common one and must render no heading at all —
    // "Your Sports This Week (0)" above white space is worse than absence.
    expect(
      followedSportFutures([
        gameItem(),
        futures({ llm_sport_category: "football" }),
        futures({ llm_sport_category: "hockey" }),
      ]),
    ).toEqual([]);
  });

  it("does not reorder the caller's array in place", () => {
    // `feedData.items` is SWR-cached and shared with the Live/Upcoming grouping
    // above. Sorting it in place would reorder that section as a side effect of
    // rendering this one.
    const items = [
      futures({ id: 1, resolution_date: "2026-09-18T12:00:00Z" }),
      futures({ id: 2, resolution_date: "2026-09-07T18:00:00Z" }),
    ];
    followedSportFutures(items);
    expect(items.map((i) => (i.data as { id: number }).id)).toEqual([1, 2]);
  });
});
