// UX-P042 (#1640) — a lone untraded Polymarket midpoint is not a probability.
//
// Every fixture below is a REAL production payload read on 2026-08-09 ~21:15 PT.
// The both-direction guards (gotcha #43) are the point of this file: suppression is
// the sharp edge on this lane, and the rule must NEVER eat a real price. Two of these
// cases (0.495 and 0.505) are traded Polymarket markets sitting either side of the
// placeholder, and one is a genuine 0.500 pick'em from the betting source.

import {
  UNTRADED_MIDPOINT,
  isUntradedPlaceholder,
  readSourceValue,
  readSourceValues,
  shouldWithholdProbability,
} from "../../lib/probabilityEvidence";

/** Event 15187583, Red Sox @ Blue Jays — the defect. Decorated wire shape. */
const LONE_POLY_PLACEHOLDER = {
  status: "scheduled",
  win_probability_sources: {
    polymarket: {
      value: 0.5,
      display_name: "Polymarket",
      type: "market",
      color: "#3b82f6",
    },
  },
};

/** Event 15187584, Mets @ Braves — a REAL traded price that must survive. */
const LONE_POLY_TRADED_LOW = {
  status: "scheduled",
  win_probability_sources: { polymarket: { value: 0.495 } },
};

/** Event 15187849, Astros @ Giants — also real, on the other side of 0.5. */
const LONE_POLY_TRADED_HIGH = {
  status: "scheduled",
  win_probability_sources: { polymarket: { value: 0.505 } },
};

/** A genuine pick'em: betting quotes exactly 0.500. 3 of 243 on the live slate. */
const BETTING_GENUINE_HALF = {
  status: "scheduled",
  win_probability_sources: { betting: 0.5 },
};

/** /api/feed's BARE-NUMBER shape, which the decorated reader would miss. */
const FEED_SHAPE_PLACEHOLDER = {
  status: "scheduled",
  win_probability_sources: { polymarket: 0.5 },
};

describe("readSourceValue — both live wire shapes", () => {
  it("reads the bare-number shape /api/feed sends", () => {
    expect(readSourceValue(0.629)).toBe(0.629);
  });

  it("reads the decorated shape /api/events and /search send", () => {
    expect(readSourceValue({ value: 0.5 })).toBe(0.5);
  });

  it("returns null for a missing or non-numeric value", () => {
    expect(readSourceValue(null)).toBeNull();
    expect(readSourceValue(undefined)).toBeNull();
    expect(readSourceValue({})).toBeNull();
    expect(readSourceValue({ value: null })).toBeNull();
    expect(readSourceValue(Number.NaN)).toBeNull();
  });

  it("collects every usable source regardless of shape", () => {
    expect(
      readSourceValues({ mlb: 0.629, polymarket: { value: 0.5 }, broken: null }),
    ).toEqual([
      ["mlb", 0.629],
      ["polymarket", 0.5],
    ]);
  });
});

describe("isUntradedPlaceholder", () => {
  it("catches the lone Polymarket midpoint (the 31-of-311 cohort)", () => {
    expect(
      isUntradedPlaceholder(LONE_POLY_PLACEHOLDER.win_probability_sources),
    ).toBe(true);
  });

  it("catches it in the feed's bare-number shape too", () => {
    expect(
      isUntradedPlaceholder(FEED_SHAPE_PLACEHOLDER.win_probability_sources),
    ).toBe(true);
  });

  it("treats two agreeing sources as evidence even at exactly 0.500", () => {
    expect(
      isUntradedPlaceholder({ polymarket: 0.5, betting: 0.5 }),
    ).toBe(false);
  });

  it("is not fooled by an empty or absent source map", () => {
    expect(isUntradedPlaceholder({})).toBe(false);
    expect(isUntradedPlaceholder(null)).toBe(false);
    expect(isUntradedPlaceholder(undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// BOTH-DIRECTION GUARDS (gotcha #43). A rule that only ever hides things is
// half-tested; these assert the rule does NOT fire on real data.
// ---------------------------------------------------------------------------
describe("shouldWithholdProbability — withholds ONLY the fabricated case", () => {
  it("withholds the lone untraded Polymarket midpoint", () => {
    expect(shouldWithholdProbability(LONE_POLY_PLACEHOLDER)).toBe(true);
  });

  it("KEEPS a traded lone-Polymarket price just below the midpoint (0.495)", () => {
    expect(shouldWithholdProbability(LONE_POLY_TRADED_LOW)).toBe(false);
  });

  it("KEEPS a traded lone-Polymarket price just above the midpoint (0.505)", () => {
    expect(shouldWithholdProbability(LONE_POLY_TRADED_HIGH)).toBe(false);
  });

  it("KEEPS a genuine pick'em quoted at exactly 0.500 by the betting source", () => {
    expect(shouldWithholdProbability(BETTING_GENUINE_HALF)).toBe(false);
  });

  it("KEEPS a multi-source event that averages to exactly 0.500", () => {
    expect(
      shouldWithholdProbability({
        status: "scheduled",
        win_probability_sources: { polymarket: 0.5, espn: 0.5, betting: 0.5 },
      }),
    ).toBe(false);
  });

  it("KEEPS a well-sourced ordinary game untouched", () => {
    expect(
      shouldWithholdProbability({
        status: "scheduled",
        win_probability_sources: { betting: 0.4023 },
      }),
    ).toBe(false);
  });

  // Scope guard: the measured cohort is scheduled-only, and widening a suppression
  // rule past its measurement is how real data gets eaten.
  it.each(["live", "completed", "closed"])(
    "leaves a %s game alone even with the placeholder signature",
    (status) => {
      expect(
        shouldWithholdProbability({
          ...LONE_POLY_PLACEHOLDER,
          status,
        }),
      ).toBe(false);
    },
  );

  it("is safe on a null/absent event", () => {
    expect(shouldWithholdProbability(null)).toBe(false);
    expect(shouldWithholdProbability(undefined)).toBe(false);
    expect(shouldWithholdProbability({ status: "scheduled" })).toBe(false);
  });
});

describe("UNTRADED_MIDPOINT", () => {
  it("is exactly representable, so === cannot drift", () => {
    expect(UNTRADED_MIDPOINT).toBe(0.5);
    expect(JSON.parse("0.5")).toBe(UNTRADED_MIDPOINT);
  });
});
