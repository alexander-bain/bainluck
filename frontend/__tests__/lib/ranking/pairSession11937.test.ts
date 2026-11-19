/**
 * #11937 (171-A): /grade/pair reads only a slate and an opaque pair name from the
 * link, and asks the server for two unlabelled sides.
 */
import {
  MORNING_NOT_READY_MESSAGE,
  PAIR_CHOICES,
  PAIR_CHOICE_LABELS,
  formatCaptureDayPt,
  gradeDeckHref,
  isCapturedTodayPt,
  normalizeMorningError,
  pairFromSearch,
  pairPath,
  pairTargetFromSearch,
} from "@/lib/ranking/pairSession";

describe("pairFromSearch", () => {
  it("needs both a slate and a pair, each a safe reference", () => {
    expect(pairFromSearch("?slate=59da9307253a78dc&pair=p1")).toEqual({ slate: "59da9307253a78dc", pair: "p1" });
    expect(pairFromSearch("?slate=59da9307253a78dc")).toBeNull();
    expect(pairFromSearch("?pair=p1")).toBeNull();
    expect(pairFromSearch("?slate=x&pair=../p")).toBeNull();
  });
});

describe("pairTargetFromSearch", () => {
  it("defaults bare /grade/pair to today's morning slate and pair, and validates explicit params", () => {
    expect(pairTargetFromSearch("")).toEqual({ slate: null, pair: null });
    expect(pairTargetFromSearch("?slate=59da9307253a78dc&pair=p1")).toEqual({
      slate: "59da9307253a78dc",
      pair: "p1",
    });
    expect(pairTargetFromSearch("?slate=59da9307253a78dc")).toBeNull();
    expect(pairTargetFromSearch("?slate=x&pair=../p")).toBeNull();
  });
});

describe("pairPath", () => {
  it("names only the slate and the pair, or uses the default morning endpoint when omitted", () => {
    expect(pairPath("59da9307253a78dc", "p1")).toBe("/api/admin/ranking/pair?slate=59da9307253a78dc&pair=p1");
    expect(pairPath(null, null)).toBe("/api/admin/ranking/pair");
  });
});

describe("the three answers", () => {
  it("are left, right and no difference, and none names a side's origin", () => {
    expect(PAIR_CHOICES).toEqual(["left", "right", "none"]);
    for (const label of Object.values(PAIR_CHOICE_LABELS)) {
      expect(label).not.toMatch(/served|candidate|today|new|current/i);
    }
  });
});

describe("gradeDeckHref", () => {
  it("goes on to the same slate's deck after the pick", () => {
    expect(gradeDeckHref("59da9307253a78dc")).toBe("/grade?slate=59da9307253a78dc");
  });
});

describe("capture day and before-7:15 AM morning guard", () => {
  it("formats the capture day in Pacific time and distinguishes yesterday from today", () => {
    const wedCapture = "2026-11-18T15:15:00+00:00"; // Wed Nov 18, 7:15 AM PT
    const thuEarly = new Date("2026-11-19T14:50:00Z"); // Thu Nov 19, 6:50 AM PT
    const wedLater = new Date("2026-11-18T16:00:00Z"); // Wed Nov 18, 8:00 AM PT
    expect(formatCaptureDayPt(wedCapture)).toMatch(/Nov 18/);
    expect(isCapturedTodayPt(wedCapture, thuEarly)).toBe(false);
    expect(isCapturedTodayPt(wedCapture, wedLater)).toBe(true);
    expect(normalizeMorningError(`HTTP 409: ${MORNING_NOT_READY_MESSAGE}`)).toBe(MORNING_NOT_READY_MESSAGE);
  });
});
