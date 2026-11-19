/** 227-A point 6: /grade/screens helpers. */
import {
  SCREEN_GRADES,
  SCREEN_GRADE_LABELS,
  nextScreen,
  screensPath,
  weekFromSearch,
} from "@/lib/ranking/screenSession";

describe("screenSession (227-A point 6)", () => {
  it("offers exactly fun, fine and wall of numbers", () => {
    expect([...SCREEN_GRADES]).toEqual(["fun", "fine", "wall"]);
    expect(SCREEN_GRADES.map((g) => SCREEN_GRADE_LABELS[g])).toEqual(["Fun", "Fine", "Wall of numbers"]);
  });

  it("reads a well-formed week and ignores anything else", () => {
    expect(weekFromSearch("?week=2026-w47")).toBe("2026-w47");
    expect(weekFromSearch("?week=47")).toBeNull();
    expect(weekFromSearch("")).toBeNull();
  });

  it("asks for the named week, or the newest when none is named", () => {
    expect(screensPath("2026-w47")).toBe("/api/admin/ranking/screens?week=2026-w47");
    expect(screensPath(null)).toBe("/api/admin/ranking/screens");
  });

  it("moves to the next unanswered screen, wrapping round, and stops when all are done", () => {
    expect(nextScreen(10, new Set([1]), 1)).toBe(2);
    expect(nextScreen(10, new Set([1, 2, 3]), 3)).toBe(4);
    expect(nextScreen(3, new Set([2, 3]), 3)).toBe(1);
    expect(nextScreen(3, new Set([1, 2, 3]), 2)).toBeNull();
  });
});
