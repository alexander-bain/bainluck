// L2-117: ThresholdGrid + ProgressionLadder carried raw-palette token debt
// (ThresholdGrid deleted by UX-P075 — see gotcha #133; QuantityGroup took its slot)
// (`text-green-400`, `bg-amber-500/15`, …) — a dark-mode artifact that renders
// nearly invisible on the light-mode-only site and violates the CLAUDE.md
// design-system rule. lib/probabilityColors.ts is the single tokenized heat
// scale that replaced them; the #194 Quantity kernel reuses it. This suite
// pins the band mapping AND guards the debt from creeping back into the
// token-critical card components.

import { readFileSync } from "fs";
import { join } from "path";
import { probabilityHeat, probabilityTextClass } from "@/lib/probabilityColors";

describe("probabilityHeat token scale (L2-117)", () => {
  test("favored (>= 0.6) → accent-brand", () => {
    const h = probabilityHeat(0.72);
    expect(h.text).toBe("text-accent-brand");
    expect(h.bg).toBe("bg-accent-brand/15");
    expect(h.bar).toBe("bg-accent-brand");
  });

  test("contested (0.3–0.6) → accent-warning", () => {
    const h = probabilityHeat(0.45);
    expect(h.text).toBe("text-accent-warning");
    expect(h.bar).toBe("bg-accent-warning");
  });

  test("unlikely (< 0.3) → accent-danger", () => {
    const h = probabilityHeat(0.12);
    expect(h.text).toBe("text-accent-danger");
    expect(h.bar).toBe("bg-accent-danger");
  });

  test("boundaries are inclusive-low", () => {
    expect(probabilityTextClass(0.6)).toBe("text-accent-brand");
    expect(probabilityTextClass(0.3)).toBe("text-accent-warning");
    expect(probabilityTextClass(0.2999)).toBe("text-accent-danger");
  });

  // #4660. This test used to read "degrades to unlikely, never throws" and
  // asserted `text-accent-danger`. The property it was protecting is NEVER
  // THROWS — the danger band was the incidental implementation, not a product
  // decision, and it was a bug: it painted an unpriced rung red. The
  // never-throws half is kept verbatim below; the band is now `unknown`.
  test("null / undefined probability is UNKNOWN, not unlikely, and never throws", () => {
    expect(() => probabilityTextClass(null)).not.toThrow();
    expect(() => probabilityTextClass(undefined)).not.toThrow();
    expect(probabilityTextClass(null)).toBe("text-text-muted");
    expect(probabilityTextClass(undefined)).toBe("text-text-muted");
    expect(probabilityHeat(null).known).toBe(false);
  });

  // The assertion that reds on a revert (#4660 acceptance). "We have no price"
  // and "we priced this at zero" are different facts and the scale must be able
  // to tell them apart — collapsing them is the entire bug in one line.
  test("probabilityHeat(null) and probabilityHeat(0) are DIFFERENT", () => {
    const unknown = probabilityHeat(null);
    const zero = probabilityHeat(0);
    expect(unknown).not.toEqual(zero);
    expect(unknown.bar).not.toBe(zero.bar);
    expect(unknown.known).toBe(false);
    expect(zero.known).toBe(true);
    // A measured zero is still a real long shot and keeps the danger band.
    expect(zero.text).toBe("text-accent-danger");
  });

  // NaN is not a probability. Every comparison against it is false, so before
  // #4660 it fell through to the danger band exactly the way `null` did.
  test("NaN is unknown, not unlikely", () => {
    expect(probabilityHeat(Number.NaN).known).toBe(false);
    expect(probabilityTextClass(Number.NaN)).toBe("text-text-muted");
  });

  test("only design-system tokens are ever emitted — including the unknown band", () => {
    const allowed = new Set([
      "accent-brand",
      "accent-warning",
      "accent-danger",
      // The unknown band is deliberately NOT an accent: it is the absence of a
      // claim, and an accent of any colour is a claim.
      "text-muted",
      "surface-elevated",
      "surface-border",
    ]);
    for (const p of [0, 0.1, 0.3, 0.5, 0.6, 0.9, 1, null, undefined, Number.NaN]) {
      const h = probabilityHeat(p);
      for (const cls of [h.text, h.bg, h.bar]) {
        const token = cls.replace(/^(text|bg)-/, "").replace(/\/\d+$/, "");
        expect(allowed.has(token)).toBe(true);
      }
    }
  });
});

// Regression guard: these two components feed the Discover card kernel, so a
// raw Tailwind palette class (light/dark-fragile) reintroduced here is a
// design-system bug. Comments are stripped so our own "removed …" notes don't trip it.
describe("no raw palette in heat components (L2-117)", () => {
  const read = (rel: string) =>
    readFileSync(join(__dirname, "../../", rel), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");

  const COMPONENTS = [
    // `components/ThresholdGrid.tsx` sat here until UX-P075 deleted it (gotcha
    // #133 — no importer since L2-118). Replaced by its live successor, so the
    // token-debt guard keeps covering a ladder a reader can actually reach.
    "components/QuantityGroup.tsx",
    "components/ProgressionLadder.tsx",
    "components/event/FinishPositionLadder.tsx",
  ];

  // Raw Tailwind palette utilities forbidden by the light-mode design system.
  const RAW_PALETTE = /\b(?:text|bg|border|ring|from|to|via)-(?:red|green|blue|amber|orange|yellow|lime|emerald|teal|cyan|sky|indigo|violet|purple|fuchsia|pink|rose|gray|slate|zinc|neutral|stone)-\d{2,3}\b/;

  for (const rel of COMPONENTS) {
    test(`${rel} uses design tokens, not raw palette`, () => {
      const src = read(rel);
      const match = src.match(RAW_PALETTE);
      expect(match).toBeNull();
    });
  }
});
