// CAL-P067 item 4 (Fable ruling) — the selection-bias rule, presentation half.
//
// The rule: any published cell whose graded share is under 50% renders
// NOT-PROVABLE, with the graded share shown.
//
// What this suite is actually guarding, because the rule is one `if` and the
// mistakes around it are not:
//
//  1. **The share must be SHOWN.** "Not provable" with no number cannot
//     distinguish a 49% cell from an 11% one, and those deserve very different
//     responses. The ruling says shown; the badge label is asserted to contain
//     it.
//  2. **`unknown` must never render as clean.** A cell whose graded share was
//     never measured has not been shown to be unbiased. This is the same
//     discipline as this queue's ruling-075 fix, and the same failure mode:
//     could-not-check sharing a rendering with checked-and-fine.
//  3. **The numbers survive.** The rule changes presentation, never the
//     estimate. A biased number struck through is honest; a number quietly
//     replaced or hidden is not.
//  4. **An unannotated cell renders exactly as before.** The backend states an
//     absent census once, in `provability_census`, instead of badging fifteen
//     public rows — so "no annotation" must be a clean no-op rather than a
//     third badge.

import {
  MIN_GRADED_SHARE,
  anyNotProvable,
  provabilityPresentation,
} from "@/lib/calibrationProvability";

describe("the threshold", () => {
  it("is a half", () => {
    expect(MIN_GRADED_SHARE).toBe(0.5);
  });
});

describe("a cell that is not provable", () => {
  const soccer = {
    provability: "not_provable_selection_biased" as const,
    graded_share: 0.25,
    provability_reason: "only 25.0% of this cell's resolved outcomes are graded",
  };

  it("strikes the confident formatting", () => {
    expect(provabilityPresentation(soccer).strike).toBe(true);
  });

  it("shows the graded share in the badge, not merely in a tooltip", () => {
    const p = provabilityPresentation(soccer);
    expect(p.showNotProvableBadge).toBe(true);
    expect(p.sharePct).toBe("25.0%");
    expect(p.badgeLabel).toBe("Not provable · 25.0% graded");
  });

  it("carries the long reason as the tooltip", () => {
    expect(provabilityPresentation(soccer).title).toContain("25.0%");
  });

  it("still says 'Not provable' when the share itself is missing", () => {
    // Verdict without a share should degrade to the bare claim rather than
    // rendering "Not provable · null graded".
    const p = provabilityPresentation({
      provability: "not_provable_selection_biased",
      graded_share: null,
    });
    expect(p.badgeLabel).toBe("Not provable");
    expect(p.sharePct).toBeNull();
  });

  it("table_tennis, the other cell the ruling names, formats to one decimal", () => {
    expect(
      provabilityPresentation({
        provability: "not_provable_selection_biased",
        graded_share: 0.11,
      }).badgeLabel,
    ).toBe("Not provable · 11.0% graded");
  });
});

describe("a cell whose graded share was never measured", () => {
  it("gets its own badge and is never treated as clean", () => {
    const p = provabilityPresentation({ provability: "unknown" });
    expect(p.showUnknownBadge).toBe(true);
    expect(p.showNotProvableBadge).toBe(false);
    // Crucially NOT struck: we are not asserting it is biased, only that we
    // cannot say. Striking it would be its own overclaim in the other direction.
    expect(p.strike).toBe(false);
    expect(p.badgeLabel).toBe("Graded share unmeasured");
  });
});

describe("a provable cell", () => {
  it("renders with no badge and no strike", () => {
    const p = provabilityPresentation({
      provability: "provable",
      graded_share: 0.92,
    });
    expect(p.strike).toBe(false);
    expect(p.showNotProvableBadge).toBe(false);
    expect(p.showUnknownBadge).toBe(false);
    expect(p.badgeLabel).toBeNull();
  });
});

describe("an unannotated cell (pre-rule payload)", () => {
  it("is a clean no-op in every direction", () => {
    for (const cell of [undefined, null, {}, { graded_share: 0.2 }]) {
      const p = provabilityPresentation(cell);
      expect(p.strike).toBe(false);
      expect(p.showNotProvableBadge).toBe(false);
      expect(p.showUnknownBadge).toBe(false);
      expect(p.badgeLabel).toBeNull();
    }
  });
});

describe("malformed shares", () => {
  it("do not produce a formatted percentage", () => {
    for (const bad of [NaN, Infinity, -Infinity]) {
      expect(
        provabilityPresentation({
          provability: "not_provable_selection_biased",
          graded_share: bad,
        }).sharePct,
      ).toBeNull();
    }
  });
});

describe("the page-level note gate", () => {
  it("fires when any cell is not provable", () => {
    expect(
      anyNotProvable([
        { provability: "provable" },
        { provability: "not_provable_selection_biased" },
      ]),
    ).toBe(true);
  });

  it("does not fire on unknown alone", () => {
    // The note explains selection bias. A page with no biased cell should not
    // display an explanation of a thing it is not showing.
    expect(anyNotProvable([{ provability: "unknown" }])).toBe(false);
  });

  it("does not fire on an unannotated payload", () => {
    expect(anyNotProvable([{}, {}])).toBe(false);
  });

  it("does not fire on an empty page", () => {
    expect(anyNotProvable([])).toBe(false);
  });
});
