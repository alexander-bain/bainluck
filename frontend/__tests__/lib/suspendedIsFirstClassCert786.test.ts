// A STATE NOBODY CAN REACH IS NOT A BETTER LIE — live/048, CERT-786 (pure half).
//
// live/048 taught the backend to write `suspended` instead of a false Final, and
// then every grid surface filed it under Upcoming by falling through its own
// inline `=== "closed"` chain. CERT-786's finding on the pinned My Stuff path is
// the sharpest version: the card was reachable — pinned events are fetched by id,
// so they never depended on the list SQL — arrived with an unrecognised status,
// and was listed among games that have not started. A match that had already been
// played, filed under "Upcoming".
//
// This file guards the PURE vocabulary: the summary string every card prints, the
// three-way section ladder, and the section title. `suspendedCardsCert786.test.tsx`
// guards that the cards actually RENDER them, and neither substitutes for the
// other — #2060's lesson, restated: a contract test proves the function is right,
// only a render test proves the card shows it.

import {
  SUSPENDED_LABEL,
  eventSectionKey,
  isFinishedStatus,
  isSuspendedStatus,
  liveSectionTitle,
  suspendedSummary,
} from "@/lib/eventState";
import { groupFeedIntoSections } from "@/lib/feedSections";
import type { FeedEventData, FeedItem } from "@/lib/types";

// ---------------------------------------------------------------------------
// The summary — one string, four surfaces
// ---------------------------------------------------------------------------

describe("suspendedSummary is the one thing every surface says", () => {
  it("carries the last score when both sides are known", () => {
    // The CERT-752 specimen: De Jong v Passaro, 1-2 in sets, on a surface that
    // paints the away side first.
    expect(suspendedSummary(1, 2, "away-home")).toBe(
      "No result reported · last score 1-2",
    );
  });

  it("prints the SAME scores in the surface's own order (#2786)", () => {
    // One string, two orders — because the four callers do not agree about
    // which side they paint first, and standardising the string while ignoring
    // the surface around it is what shipped an inverted score. Same two
    // numbers, same sentence, flipped to match the card.
    expect(suspendedSummary(1, 2, "home-away")).toBe(
      "No result reported · last score 2-1",
    );
  });

  it("prints the badge alone when there is no score at all", () => {
    expect(suspendedSummary(null, null, "away-home")).toBe(SUSPENDED_LABEL);
    expect(suspendedSummary(undefined, undefined, "home-away")).toBe(SUSPENDED_LABEL);
  });

  it("refuses to print HALF a score", () => {
    // A partial line under a "last score" label is the same trap that graded the
    // CERT-752 specimen 1.0/0.0 off a 1-2 — told smaller, and therefore more
    // likely to survive review. Neither order rescues half a score.
    expect(suspendedSummary(1, null, "away-home")).toBe(SUSPENDED_LABEL);
    expect(suspendedSummary(null, 2, "away-home")).toBe(SUSPENDED_LABEL);
    expect(suspendedSummary(1, null, "home-away")).toBe(SUSPENDED_LABEL);
    expect(suspendedSummary(null, 2, "home-away")).toBe(SUSPENDED_LABEL);
  });

  it("prints a 0-0 score rather than treating it as absent", () => {
    // `!score` would swallow this. Nil-coalescing is the difference between "no
    // score was reported" and "the score reported was nil-all", and a suspended
    // match at 0-0 is a real and common shape (a rain delay before the first
    // point). Two different facts must not print the same sentence.
    expect(suspendedSummary(0, 0, "away-home")).toBe(
      "No result reported · last score 0-0",
    );
  });

  it("says nothing about the future", () => {
    // The shipped-copy ban: no "we will update it if a source confirms". A
    // promise about a later update is not a description of the state, and
    // describing exactly what is and is not known right now is this state's
    // entire job.
    const summary = suspendedSummary(1, 2, "home-away").toLowerCase();
    for (const banned of ["will", "soon", "shortly", "pending", "check back"]) {
      expect(summary).not.toContain(banned);
    }
  });

  it("never claims a result", () => {
    const summary = suspendedSummary(1, 2, "home-away").toLowerCase();
    for (const banned of ["final", "won", "winner", "beat"]) {
      expect(summary).not.toContain(banned);
    }
  });
});

// ---------------------------------------------------------------------------
// The ladder
// ---------------------------------------------------------------------------

describe("the section ladder", () => {
  it("does not file a suspended match under upcoming", () => {
    // THE defect. Every surface reached this by falling through, and the
    // upcoming branch renders a START TIME.
    expect(eventSectionKey("suspended")).not.toBe("upcoming");
    expect(eventSectionKey("suspended")).toBe("live");
  });

  it("does not file it under finished either", () => {
    expect(eventSectionKey("suspended")).not.toBe("finished");
    expect(isFinishedStatus("suspended")).toBe(false);
  });

  it.each([
    ["live", "live"],
    ["completed", "finished"],
    ["closed", "finished"],
    ["scheduled", "upcoming"],
  ])("still files %s under %s", (status, section) => {
    expect(eventSectionKey(status)).toBe(section);
  });

  it("files an unknown status under upcoming, as it always did", () => {
    // The next state added to the vocabulary lands here, and that is the
    // fallback this whole cert is about — so it is asserted rather than
    // inherited, and the assertion is a place to notice it.
    expect(eventSectionKey("postponed")).toBe("upcoming");
    expect(eventSectionKey(null)).toBe("upcoming");
    expect(eventSectionKey(undefined)).toBe("upcoming");
  });

  it("recognises only the exact word", () => {
    expect(isSuspendedStatus("Suspended")).toBe(false);
    expect(isSuspendedStatus("suspend")).toBe(false);
    expect(isSuspendedStatus("suspended")).toBe(true);
  });
});

describe("the live section names what is in it", () => {
  it("says Live & Paused when a suspended match is in the bucket", () => {
    expect(liveSectionTitle(true)).toBe("Live & Paused");
  });

  it("says Live Now when it is only live games", () => {
    expect(liveSectionTitle(false)).toBe("Live Now");
  });
});

// ---------------------------------------------------------------------------
// The shared sectioner — /sports, the category grids, My Stuff's twin
// ---------------------------------------------------------------------------

function eventItem(over: Partial<FeedEventData>): FeedItem {
  return {
    type: "event",
    score: 50,
    data: {
      id: 1,
      home_team: "Passaro",
      away_team: "De Jong",
      commence_time: "2026-09-02T04:00:00.000Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      ...over,
    },
  } as unknown as FeedItem;
}

const SPECIMEN = eventItem({
  id: 15295047,
  status: "suspended",
  away_score: 1,
  home_score: 2,
});
const LIVE = eventItem({ id: 2, status: "live" });
const FINISHED = eventItem({ id: 3, status: "completed" });
const SCHEDULED = eventItem({
  id: 4,
  status: "scheduled",
  commence_time: "2030-01-01T00:00:00.000Z",
});

function section(items: FeedItem[], key: string) {
  return groupFeedIntoSections(items).find((s) => s.key === key);
}

describe("groupFeedIntoSections admits suspended to the live section", () => {
  it("puts the specimen in the live section, not upcoming", () => {
    const sections = groupFeedIntoSections([SPECIMEN, LIVE, FINISHED, SCHEDULED]);
    const ids = (key: string) =>
      (sections.find((s) => s.key === key)?.items ?? []).map(
        (i) => (i.data as FeedEventData).id
      );
    expect(ids("live")).toContain(15295047);
    expect(ids("upcoming")).not.toContain(15295047);
    expect(ids("finished")).not.toContain(15295047);
  });

  it("retitles the section when one is present", () => {
    expect(section([SPECIMEN, LIVE], "live")?.title).toBe("Live & Paused");
  });

  it("leaves the title alone when it is only live games", () => {
    // Both directions (gotcha #43): the header must change when it should AND
    // must not change when it should not, or the retitle is just noise.
    expect(section([LIVE], "live")?.title).toBe("Live Now");
  });

  it("does not disturb the other sections", () => {
    const sections = groupFeedIntoSections([SPECIMEN, LIVE, FINISHED, SCHEDULED]);
    expect(section([SPECIMEN, FINISHED], "finished")?.title).toBe("Just Happened");
    expect(sections.find((s) => s.key === "upcoming")?.items).toHaveLength(1);
    expect(sections.find((s) => s.key === "finished")?.items).toHaveLength(1);
  });

  it("counts the suspended card in the live section badge", () => {
    // The badge is a promise about what is below it.
    expect(section([SPECIMEN, LIVE], "live")?.count).toBe(2);
  });
});
