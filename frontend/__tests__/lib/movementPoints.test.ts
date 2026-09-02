/**
 * UX-P048 (#1695) — the movement unit crosses into "points" in exactly one place.
 *
 * THE DEFECT these guard. `movement` is a wire FRACTION — the backend proves it
 * in the same payload it sends (`movement: -0.07` ships alongside
 * `reason: "The Odyssey moved down 7.0 points today"`). Seven of eight renderers
 * multiplied by 100; the Discover hero did not, and printed the raw fraction
 * under a label reading "points".
 *
 * Measured on production 2026-08-10 (`GET /api/feed?limit=60`, backend
 * a4275e07): of 21 futures cards carrying a leader movement, all 21 route to
 * that hero, and the one that rendered was the feed's biggest mover — a
 * 64.0-point swing to a new favourite — printing `↑ 0.6` above a tooltip
 * asserting "Up 0.6 points in the last 24h".
 */

import fs from "fs";
import path from "path";
import { movementPoints, formatMovementPoints } from "@/lib/probabilityDisplay";

const REPO = path.join(__dirname, "..", "..");

describe("movementPoints — the fraction -> points conversion", () => {
  it("converts the wire fraction to points", () => {
    // The exact production specimen, and the value the backend itself calls
    // "7.0 points" in the same payload.
    expect(movementPoints(-0.07)).toBeCloseTo(-7.0, 10);
    expect(movementPoints(0.64)).toBeCloseTo(64.0, 10);
  });

  it("returns null for every non-value, so a caller cannot leak a bare 0", () => {
    expect(movementPoints(null)).toBeNull();
    expect(movementPoints(undefined)).toBeNull();
    expect(movementPoints(NaN)).toBeNull();
    expect(movementPoints(Infinity)).toBeNull();
  });

  it("keeps a genuine zero as a zero rather than collapsing it into null", () => {
    // The conversion's job is the UNIT, not the threshold. A caller decides
    // whether 0 is worth showing; it must not be pre-decided here.
    expect(movementPoints(0)).toBe(0);
  });
});

describe("formatMovementPoints — the display string", () => {
  it("prints the magnitude in points, one decimal", () => {
    expect(formatMovementPoints(0.64)).toBe("64.0");
    expect(formatMovementPoints(-0.07)).toBe("7.0");
  });

  it("is unsigned — direction is carried by the caller's arrow", () => {
    expect(formatMovementPoints(0.05)).toBe(formatMovementPoints(-0.05));
  });

  it("returns null (never the string '0') for an absent movement", () => {
    expect(formatMovementPoints(null)).toBeNull();
    expect(formatMovementPoints(undefined)).toBeNull();
    expect(formatMovementPoints(NaN)).toBeNull();
  });
});

describe("the production specimen, end to end", () => {
  // Card 55686617, South Carolina Republican Senate special primary winner.
  // Darline Graham, probability 0.6498, movement 0.64 — a new favourite.
  const MOVEMENT = 0.64;
  const HERO_MIN_MOVEMENT_POINTS = 10;

  it("renders the 64-point swing as 64.0, not 0.6", () => {
    const pts = movementPoints(MOVEMENT)!;
    const display = formatMovementPoints(MOVEMENT)!;

    expect(Math.abs(pts) >= HERO_MIN_MOVEMENT_POINTS).toBe(true);
    expect(display).toBe("64.0");
    expect(display).not.toBe("0.6");
    expect(`Up ${display} points in the last 24h`).toBe(
      "Up 64.0 points in the last 24h",
    );
  });
});

describe("threshold behaviour is PRESERVED, not widened (gotcha #43)", () => {
  // UX-P048 fixed the SCALE only. The bars are unchanged in value, so every
  // card that was silent before is still silent and vice versa. If a later
  // change means to move a bar, it must fail here first and say so.
  const HERO_MIN_MOVEMENT_POINTS = 10;
  const BADGE_MIN_MOVEMENT_POINTS = 2;

  const heroFires = (m: number) => {
    const p = movementPoints(m);
    return p != null && Math.abs(p) >= HERO_MIN_MOVEMENT_POINTS;
  };
  const badgeFires = (m: number) => {
    const p = movementPoints(m);
    return p != null && Math.abs(p) >= BADGE_MIN_MOVEMENT_POINTS;
  };

  it("matches the pre-fix hero gate at and around the boundary", () => {
    for (const m of [0.1, -0.1, 0.0999, 0.64, 0.07, 0, 0.5]) {
      expect(heroFires(m)).toBe(Math.abs(m) >= 0.1); // the old expression
    }
  });

  it("matches the pre-fix badge gate at and around the boundary", () => {
    for (const m of [0.02, -0.02, 0.019, 0.021, 0.07, 0.64, 0.5]) {
      // The old expression, minus its truthiness hole.
      expect(badgeFires(m)).toBe(Math.abs(m) >= 0.02);
    }
  });

  it("still renders nothing for a real but sub-threshold move", () => {
    // 7.0 points is real and the card's own caption says so — but the hero bar
    // is 10, and this fix deliberately did not move it. Recorded, not hidden.
    expect(heroFires(0.07)).toBe(false);
    expect(badgeFires(0.07)).toBe(true);
  });

  it("still renders nothing when there is no movement at all", () => {
    for (const m of [null, undefined, NaN]) {
      const p = movementPoints(m as number | null | undefined);
      expect(p != null && Math.abs(p) >= HERO_MIN_MOVEMENT_POINTS).toBe(false);
    }
  });
});

describe("ANTI-DRIFT: the unit is interpreted in exactly one place", () => {
  // This is the deliverable, not the conversion. The hero and the badge read
  // the SAME field and disagreed about its unit for as long as both existed;
  // extracting a helper only helps if a third interpretation cannot appear.
  // Third instance of the #1620 shape on this lane after #1677 and #1688.
  const read = (rel: string) => fs.readFileSync(path.join(REPO, rel), "utf8");

  it("FuturesCard does not multiply a movement by 100 itself", () => {
    const src = read("components/discover/FuturesCard.tsx");
    expect(src).toContain("formatMovementPoints");
    expect(src).toContain("movementPoints");
    expect(src).not.toMatch(/movementVal\s*\*\s*100/);
    expect(src).not.toMatch(/movement\s*\*\s*100/);
  });

  it("MovementBadge delegates the conversion instead of restating it", () => {
    const src = read("components/discover/shared.tsx");
    expect(src).toContain("movementPoints(m)");
    // The old `Math.round(m * 100)` must not come back.
    expect(src).not.toMatch(/Math\.round\(\s*m\s*\*\s*100\s*\)/);
  });

  // UX-P274 (#2672) — the eighth call site, found three weeks after UX-P048
  // shipped. `/golf`'s "Biggest Movers (24h)" strip still ran its own
  // `Math.abs(Math.round(mover.movement_24h * 100))`, so it printed whole
  // points while every other renderer printed one decimal — including
  // `TournamentCard` ~600px below it on the same page. It was also asymmetric:
  // `Math.round` is half-up toward +Infinity, so `Math.round(-0.5)` is `-0`,
  // and the backend admits a mover at exactly `abs(movement_24h) >= 0.005`
  // (`routes/golf.py`). The smallest downward move the producer can admit was
  // therefore the one value guaranteed to render "0%", in red, under a down
  // arrow. Rendered proof: `__tests__/golfMoversPrecisionUxp274.test.tsx`.
  it("the golf movers strip delegates the conversion instead of restating it", () => {
    const src = read("components/golf/MoversStrip.tsx");

    // Scope the scan to the component itself, so neither an unrelated `* 100`
    // nor an unrelated absence of one elsewhere in the file can decide this.
    const start = src.indexOf("export function MoversStrip");
    // A scan that cannot find its subject must RAISE, not pass vacuously —
    // if the component is renamed or moved, this test has stopped guarding
    // anything and must say so rather than going quietly green.
    expect(start).toBeGreaterThan(-1);
    const raw = src.slice(start, src.indexOf("\n}", start));

    // Strip comments before matching. The rule is about what the component
    // COMPUTES, and the note above the fixed line necessarily quotes the
    // arithmetic it replaced — scanning prose as if it were code made this
    // test fail on its own explanation. (The same conflation in the other
    // direction is how a `toContain` guard passes because a docstring
    // mentions the symbol.)
    const body = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
    // The strip cannot remove everything, or the assertions below are vacuous.
    expect(body).toContain("movers.map");

    expect(body).toContain("movementPoints(mover.movement_24h)");
    expect(body).toContain("formatMovementPoints(mover.movement_24h)");
    // The two forms the old line took, neither of which may come back.
    expect(body).not.toMatch(/movement_24h\s*\*\s*100/);
    expect(body).not.toMatch(/Math\.round/);
  });

  it("both surfaces state their threshold in POINTS, not as a bare fraction", () => {
    expect(read("components/discover/FuturesCard.tsx")).toContain(
      "HERO_MIN_MOVEMENT_POINTS",
    );
    expect(read("components/discover/shared.tsx")).toContain(
      "BADGE_MIN_MOVEMENT_POINTS",
    );
  });
});

describe("RelatedFutures no longer leaks a bare 0 into the DOM", () => {
  // `{n && <span/>}` over a NUMBER renders the number when n === 0. Both call
  // sites in this file had it; fixing one would have left the other, which is
  // cycle 44's lesson (a suppression needs every call site or it is decorative).
  it("compares probability_change_24h against null, never for truthiness", () => {
    const src = fs.readFileSync(
      path.join(REPO, "components/RelatedFutures.tsx"),
      "utf8",
    );
    const truthy = src.match(/\{\s*[a-zA-Z0-9_.]*probability_change_24h\s*&&/g);
    expect(truthy).toBeNull();
    expect(
      src.match(/probability_change_24h\s*!=\s*null\s*&&/g)?.length,
    ).toBeGreaterThanOrEqual(2);
  });
});
