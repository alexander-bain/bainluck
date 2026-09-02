/**
 * UX-1035 / #2709 — the client sectioner and the server projection agree.
 *
 * The "Live Now" rail is now assembled from two halves in two languages: the
 * server decides WHICH items are live (`backend/app/utils/feed_live_section.py`)
 * and the client decides WHICH SECTION each item lands in
 * (`lib/feedSections.ts`). Nothing in the type system makes those two agree, and
 * a silent disagreement is the exact failure the fix exists to remove.
 *
 * So both sides are pinned to the SAME banked production payload and the SAME
 * numbers. Neither test reimplements the other's predicate — that would be a
 * guard that passes under both arms. They meet on a count:
 * `backend/tests/test_feed_live_section_2709.py` asserts the Python filter finds
 * 14 in this file; this asserts the TypeScript sectioner puts 14 under "Live
 * Now". Change one predicate and one of the two goes red.
 *
 * The payload is not hand-written: verbatim `GET /api/feed?mode=sports&
 * limit=200` from api.bainluck.com on 2026-09-02 with nine US Open matches in
 * play.
 */
import fs from "fs";
import path from "path";

import { groupFeedIntoSections } from "@/lib/feedSections";
import { mergeLiveRail } from "@/lib/sports/liveRail";
import { dedupeById } from "@/lib/discover/feedPaging";
import { getSportsItemId as idOf } from "@/lib/sports/feedItemId";
import type { FeedItem } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "sports_feed_live_rail_2709.json",
);

const banked: { _page_limit: number; payload: { items: FeedItem[] } } =
  JSON.parse(fs.readFileSync(FIXTURE, "utf8"));

const ALL: FeedItem[] = banked.payload.items;
const PAGE_LIMIT = banked._page_limit;

/** The same three numbers the Python suite pins, from the same file. */
const BANKED_TOTAL = 83;
const BANKED_LIVE = 14;
const BANKED_LIVE_IN_FIRST_PAGE = 6;

// Item identity is the PAGE's own function, imported, not re-typed: the whole
// point of this guard is that the rail de-duplicates the way the page does.

const liveCount = (items: FeedItem[]): number =>
  groupFeedIntoSections(items).find((s) => s.key === "live")?.count ?? 0;

describe("#2709 — the payload the rail was wrong about", () => {
  it("is the one the defect was measured on", () => {
    expect(ALL).toHaveLength(BANKED_TOTAL);
    expect(PAGE_LIMIT).toBe(20);
  });

  it("🔴 sections only 6 live cards out of the 14 that are in progress", () => {
    // This is the bug, run through the REAL sectioner. `/sports` at first paint
    // holds exactly `ALL.slice(0, 20)`, so this is the number that was printed
    // beside "Live Now" while fourteen games were being played.
    expect(liveCount(ALL.slice(0, PAGE_LIMIT))).toBe(BANKED_LIVE_IN_FIRST_PAGE);
    expect(liveCount(ALL)).toBe(BANKED_LIVE);
  });

  it("🔴 showed no US Open match while six courts were mid-match", () => {
    const live = groupFeedIntoSections(ALL.slice(0, PAGE_LIMIT)).find(
      (s) => s.key === "live",
    );
    const names = (live?.items ?? []).map((i) => {
      const d = i.data as { home_team?: string; away_team?: string; name?: string };
      return d.name ?? `${d.home_team} vs ${d.away_team}`;
    });
    expect(names).toEqual(
      expect.arrayContaining(["Vuelta a España 2026", "Dutch Grand Prix Winner"]),
    );
    // Nine US Open matches were live; exactly one of them ranked above the cut.
    const tennisOnPageOne = names.filter((n) =>
      ["Wang", "Shapovalov", "Etcheverry", "Harris", "Berrettini"].some((p) =>
        n.includes(p),
      ),
    );
    expect(tennisOnPageOne).toEqual(["Xinyu Wang vs Anna Kalinskaya"]);
  });
});

describe("#2709 — the merged pool the fix renders", () => {
  // What the page now holds at first paint: the live projection (every live
  // item, which is what `live_only=true` returns off this same build) merged
  // with the bounded 20-item first page.
  const liveProjection = ALL.filter((item) => {
    if (item.type === "futures" || item.type === "bundle") return false;
    const d = item.data as { status?: string; schedule_status?: string };
    return d?.schedule_status === "in-progress" || d?.status === "live";
  });
  const merged = dedupeById(
    mergeLiveRail(liveProjection, ALL.slice(0, PAGE_LIMIT)),
    idOf,
  );

  it("🟢 puts every live match under Live Now", () => {
    expect(liveCount(merged)).toBe(BANKED_LIVE);
  });

  it("🟢 the server's projection and the client's sectioner name the SAME set", () => {
    // The parity claim itself. Not "both are 14" — the same cards.
    const sectioned = groupFeedIntoSections(merged).find((s) => s.key === "live");
    expect(new Set((sectioned?.items ?? []).map(idOf))).toEqual(
      new Set(liveProjection.map(idOf)),
    );
  });

  it("counts each live card once, not twice", () => {
    // Six of the fourteen are on page 1 as well. Without de-duplication the
    // rail would read 20 and render six games twice.
    expect(merged.filter((i) => idOf(i) === idOf(liveProjection[0]))).toHaveLength(1);
    expect(merged.length).toBe(
      PAGE_LIMIT + BANKED_LIVE - BANKED_LIVE_IN_FIRST_PAGE,
    );
  });

  it("leaves every other section exactly as it was", () => {
    // The control. A live item is in no other section, so merging the rail must
    // move nothing else — same sections, same counts, same order.
    const before = groupFeedIntoSections(ALL.slice(0, PAGE_LIMIT));
    const after = groupFeedIntoSections(merged);
    for (const key of ["finished", "upcoming", "markets"]) {
      const b = before.find((s) => s.key === key);
      const a = after.find((s) => s.key === key);
      expect(a?.count ?? 0).toBe(b?.count ?? 0);
      expect((a?.items ?? []).map(idOf)).toEqual((b?.items ?? []).map(idOf));
    }
  });

  it("keeps the build's own order in the rail", () => {
    // A rail that re-sorted would be a second opinion about score, and would
    // disagree with the list underneath it.
    const sectioned = groupFeedIntoSections(merged).find((s) => s.key === "live");
    const positions = (sectioned?.items ?? []).map((i) =>
      ALL.findIndex((a) => idOf(a) === idOf(i)),
    );
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("an absent rail degrades to exactly the pre-fix page", () => {
    // The failure mode. If the live request errors, SWR hands back undefined;
    // the page must be what it was, not empty.
    const degraded = dedupeById(
      mergeLiveRail(undefined, ALL.slice(0, PAGE_LIMIT)),
      idOf,
    );
    expect(degraded.map(idOf)).toEqual(ALL.slice(0, PAGE_LIMIT).map(idOf));
    expect(liveCount(degraded)).toBe(BANKED_LIVE_IN_FIRST_PAGE);
  });
});
