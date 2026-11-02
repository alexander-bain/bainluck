/**
 * #883 — THE CAPTION DESCRIBES THE CHART ON SCREEN, AND SAYS WHEN.
 *
 * The landing-page audit found the undated "up N pts from opening" caption
 * contradicting the drawn line on 7 of 18 pages: it compared the served opening
 * with the served current price, neither of which is a point the chart draws.
 * `rangeMovementCaption` reads the subject's own drawn line over the range the
 * reader picked, in whole points, and dates the start of the move.
 *
 * `jest.config.js` pins TZ=UTC; every call below also passes "UTC" explicitly.
 */
import { rangeMovementCaption } from "@/lib/futuresDetailDisplay";

const RAVENS = { id: 7, name: "Baltimore Ravens", probability: 0.31, opening_probability: 0.5 };

function line(points: [string, number | null][], outcome_id = 7) {
  return {
    outcome_id,
    history: points.map(([timestamp, probability]) => ({ timestamp, probability })),
  };
}

describe("rangeMovementCaption", () => {
  it("THE REPORTED SHAPE: the chart rose, so the caption says up — not the opening's down", () => {
    const drawn = [line([["2026-10-25T12:00:00Z", 0.25], ["2026-10-28T12:00:00Z", 0.28], ["2026-11-01T12:00:00Z", 0.31]])];
    // The old caption on this outcome read "down 19.0 pts from opening".
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens up 6 pts since Oct 25.");
  });

  it("says down, in whole points, for a falling line", () => {
    const drawn = [line([["2026-10-01T00:00:00Z", 0.404], ["2026-10-20T00:00:00Z", 0.31]])];
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens down 9 pts since Oct 1.");
  });

  it("uses the singular for one point", () => {
    const drawn = [line([["2026-10-01T00:00:00Z", 0.30], ["2026-10-02T00:00:00Z", 0.31]])];
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens up 1 pt since Oct 1.");
  });

  it("reads a sub-point move as roughly flat", () => {
    const drawn = [line([["2026-10-01T00:00:00Z", 0.310], ["2026-10-09T00:00:00Z", 0.314]])];
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens roughly flat since Oct 1.");
  });

  it("dates a same-day range by its clock time", () => {
    const drawn = [line([["2026-11-01T09:05:00Z", 0.25], ["2026-11-01T17:40:00Z", 0.31]])];
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens up 6 pts since 9:05 AM.");
  });

  it("reads the line in time order and skips numberless points", () => {
    const drawn = [line([
      ["2026-10-28T12:00:00Z", 0.28],
      ["2026-10-24T12:00:00Z", null],
      ["2026-11-01T12:00:00Z", 0.31],
      ["2026-10-25T12:00:00Z", 0.25],
    ])];
    expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBe("Baltimore Ravens up 6 pts since Oct 25.");
  });

  it("drops a repeated board name the way the hero and rows do", () => {
    const subject = { id: 3, name: "Set 1 O/U 9.5 Over", probability: 0.6 };
    const drawn = [line([["2026-10-01T00:00:00Z", 0.4], ["2026-10-05T00:00:00Z", 0.6]], 3)];
    expect(rangeMovementCaption(subject, drawn, "Set 1 O/U 9.5", "UTC")).toBe("Over up 20 pts since Oct 1.");
  });

  describe("says nothing rather than an undated or invented claim", () => {
    it("no subject", () => {
      expect(rangeMovementCaption(null, [line([["2026-10-01T00:00:00Z", 0.2], ["2026-10-02T00:00:00Z", 0.3]])], null, "UTC")).toBeNull();
    });
    it("the subject is not a drawn line", () => {
      const drawn = [line([["2026-10-01T00:00:00Z", 0.2], ["2026-10-02T00:00:00Z", 0.3]], 99)];
      expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBeNull();
    });
    it("one priced point — no movement to describe, and no opening fallback", () => {
      const drawn = [line([["2026-10-01T00:00:00Z", null], ["2026-10-02T00:00:00Z", 0.3]])];
      expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBeNull();
    });
    it("two points at one instant", () => {
      const drawn = [line([["2026-10-01T00:00:00Z", 0.2], ["2026-10-01T00:00:00Z", 0.3]])];
      expect(rangeMovementCaption(RAVENS, drawn, null, "UTC")).toBeNull();
    });
  });
});
