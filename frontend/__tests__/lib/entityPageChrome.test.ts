// UX-P061 (#1742, epic #1741) — the §4 chrome-earning grammar, and the guard
// that keeps it ONE rule rather than two.
//
// The parity block at the bottom is the load-bearing part. Every count threshold
// here also exists in `backend/app/utils/entity_page_tiers.py`, and a constant
// that exists in two languages is two constants the moment one is tuned. This
// lane has filed that shape (#1620 — two graders, one input) eleven times, so the
// copy is mechanically pinned to its source rather than trusted to stay in sync.

import fs from "fs";
import path from "path";

import {
  CHROME_ANCHOR_NAV_MIN_SECTIONS,
  CHROME_GRID_MIN_ITEMS,
  CHROME_MORE_LINK_MIN_HIDDEN,
  CHROME_MOVERS_MIN,
  CHROME_RAIL_MIN_ITEMS,
  CHROME_SECTION_HEADER_MIN_ITEMS,
  CHROME_SECTION_HEADER_MIN_SECTIONS,
  applyCountedCap,
  earnsAnchorNav,
  earnsCountChip,
  earnsGrid,
  earnsMoreLink,
  earnsMoversStrip,
  earnsRail,
  earnsSectionHeader,
  probabilityBarWidth,
} from "@/lib/entityPageChrome";

describe("section header — register E1, the broken shelf itself", () => {
  it("does NOT earn a header over a single card", () => {
    // The named violation: `hub/[competition]` renders a header + count chip over
    // one market.
    expect(earnsSectionHeader(1, 5)).toBe(false);
  });

  it("does not earn a header when it is the only section", () => {
    // A header needs something to distinguish it FROM. One section is the page.
    expect(earnsSectionHeader(9, 1)).toBe(false);
  });

  it("earns a header at two items across two sections", () => {
    expect(earnsSectionHeader(2, 2)).toBe(true);
  });
});

describe("rail / grid — a two-card carousel is a broken carousel", () => {
  it.each([
    [4, true],
    [3, false],
    [1, false],
  ])("rail at %i items → %s", (n, expected) => {
    expect(earnsRail(n)).toBe(expected);
  });

  it.each([
    [3, true],
    [2, false],
  ])("grid at %i items → %s", (n, expected) => {
    expect(earnsGrid(n)).toBe(expected);
  });
});

describe("+N more — register E1's second half", () => {
  it("does NOT render '+1 more'", () => {
    // It costs the same row as the item it hides.
    expect(earnsMoreLink(1)).toBe(false);
  });

  it("renders '+2 more'", () => {
    expect(earnsMoreLink(2)).toBe(true);
  });
});

describe("counted caps — an uncounted cap is concealment (ruling 025 clause 3)", () => {
  it("shows everything below the cap", () => {
    expect(applyCountedCap(3, 12)).toEqual({ shown: 3, hidden: 0, showMoreLink: false });
  });

  it("caps and COUNTS the remainder", () => {
    expect(applyCountedCap(112, 12)).toEqual({ shown: 12, hidden: 100, showMoreLink: true });
  });

  it("absorbs a single leftover rather than announcing it", () => {
    // 13 items with a cap of 12 renders 13, not 12 + "+1 more".
    expect(applyCountedCap(13, 12)).toEqual({ shown: 13, hidden: 0, showMoreLink: false });
  });

  it("never hides an item without saying so", () => {
    // The invariant, over the whole range: if anything is hidden, the link shows.
    for (let total = 0; total <= 60; total += 1) {
      const { shown, hidden, showMoreLink } = applyCountedCap(total, 12);
      expect(shown + hidden).toBe(total);
      if (hidden > 0) expect(showMoreLink).toBe(true);
    }
  });
});

describe("count chip — keyed off the DECLARED tier, not a local count", () => {
  it("is absent at T1 and T0", () => {
    // Spec §3: at two answers the count is visible; "2 markets" is an apology.
    expect(earnsCountChip("answer")).toBe(false);
    expect(earnsCountChip("present")).toBe(false);
  });

  it("is present at T2 and T3", () => {
    expect(earnsCountChip("standard")).toBe(true);
    expect(earnsCountChip("full")).toBe(true);
  });

  it("is absent when the backend declared no tier", () => {
    // Fail closed: a missing tier must not manufacture chrome.
    expect(earnsCountChip(null)).toBe(false);
    expect(earnsCountChip(undefined)).toBe(false);
  });
});

describe("anchor nav / movers", () => {
  it.each([
    [3, true],
    [2, false],
  ])("anchor nav at %i sections → %s", (n, expected) => {
    expect(earnsAnchorNav(n)).toBe(expected);
  });

  it.each([
    [3, true],
    [2, false],
  ])("movers strip at %i movers → %s", (n, expected) => {
    expect(earnsMoversStrip(n)).toBe(expected);
  });
});

describe("probability bar — register E2, null drawn as a claim", () => {
  it("returns null for a null probability", () => {
    // `width: ${pct ?? 0}%` said "we measured this and it is zero" about something
    // we did not measure. Doctrine A3: honest or absent.
    expect(probabilityBarWidth(null)).toBeNull();
    expect(probabilityBarWidth(undefined)).toBeNull();
    expect(probabilityBarWidth(Number.NaN)).toBeNull();
  });

  it("returns a real width for a real probability", () => {
    expect(probabilityBarWidth(0.62)).toBe(62);
    expect(probabilityBarWidth(0)).toBe(0);
    expect(probabilityBarWidth(1)).toBe(100);
  });

  it("distinguishes a MEASURED zero from an absent probability", () => {
    // The whole point: these two must not render identically.
    expect(probabilityBarWidth(0)).toBe(0);
    expect(probabilityBarWidth(null)).toBeNull();
  });

  it("clamps rather than overflowing its track", () => {
    expect(probabilityBarWidth(1.4)).toBe(100);
    expect(probabilityBarWidth(-0.2)).toBe(0);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// PARITY WITH THE BACKEND — the guard that makes this one rule, not two
// ───────────────────────────────────────────────────────────────────────────

describe("parity: every threshold matches backend/app/utils/entity_page_tiers.py", () => {
  const pySource = fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "backend", "app", "utils", "entity_page_tiers.py"),
    "utf8",
  );

  /** Read `NAME = 12` out of the Python module. Fails loudly if absent. */
  function pyConst(name: string): number {
    const m = new RegExp(`^${name}\\s*=\\s*([0-9.]+)`, "m").exec(pySource);
    if (!m) throw new Error(`${name} not found in entity_page_tiers.py`);
    return Number(m[1]);
  }

  it.each([
    ["CHROME_SECTION_HEADER_MIN_ITEMS", CHROME_SECTION_HEADER_MIN_ITEMS],
    ["CHROME_SECTION_HEADER_MIN_SECTIONS", CHROME_SECTION_HEADER_MIN_SECTIONS],
    ["CHROME_RAIL_MIN_ITEMS", CHROME_RAIL_MIN_ITEMS],
    ["CHROME_GRID_MIN_ITEMS", CHROME_GRID_MIN_ITEMS],
    ["CHROME_MORE_LINK_MIN_HIDDEN", CHROME_MORE_LINK_MIN_HIDDEN],
    ["CHROME_ANCHOR_NAV_MIN_SECTIONS", CHROME_ANCHOR_NAV_MIN_SECTIONS],
    ["CHROME_MOVERS_MIN", CHROME_MOVERS_MIN],
  ])("%s agrees with Python", (name, tsValue) => {
    expect(tsValue).toBe(pyConst(name as string));
  });

  it("the count-chip rule reads the same tiers on both sides", () => {
    // Python: `earns_count_chip` returns True for TIER_FULL / TIER_STANDARD.
    expect(pySource).toContain("return tier in (TIER_FULL, TIER_STANDARD)");
    expect(earnsCountChip("full")).toBe(true);
    expect(earnsCountChip("standard")).toBe(true);
    expect(earnsCountChip("answer")).toBe(false);
  });

  it("the parity reader is non-vacuous", () => {
    // If the regex silently matched nothing, every assertion above would compare
    // a number to NaN and fail — but a future refactor could make it return a
    // default. Prove the reader actually reads.
    expect(pyConst("T3_MIN_ANSWERS")).toBe(12);
    expect(() => pyConst("NO_SUCH_CONSTANT")).toThrow();
  });
});
