/**
 * #1933 — `contracts/rendered_percent.json` drives web, and this suite is also
 * the only CROSS-runtime check that runs in CI.
 *
 * The server fingerprints a graded card at this resolution so that a refused
 * judgment is always explicable as "the number on screen changed". Three
 * runtimes print that number and no import spans them, so the shared unit is the
 * table (ruling 021).
 *
 * ## What this file is responsible for that no other file can be
 *
 * The Swift arm executes under `scripts/ios_native_gate.sh test`, which is a
 * local gate — xcodebuild does not run in CI. So the Swift TEST's inlined case
 * table is compared against the contract HERE, where CI will see it. Without
 * this, native could quietly stop being the same rule and the only thing that
 * would notice is whoever next ran the native gate by hand.
 *
 * UX-P110's near-miss is the reason the bar is set here: it shipped the Python
 * arm using banker's rounding, under a comment stating the JavaScript answer,
 * with a test that asserted the Python one. Everything was green and two
 * runtimes disagreed at every .5.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

import { renderedPercent } from "../../lib/renderedPercent";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const CONTRACT_PATH = join(REPO_ROOT, "contracts/rendered_percent.json");

interface Case {
  probability: number | null;
  percent: number | null;
  discriminates?: boolean;
}
interface Contract {
  version: number;
  rule: string;
  implementations: { runtime: string; path: string; symbol: string; driven_by: string }[];
  cases: Case[];
}

const CONTRACT: Contract = JSON.parse(readFileSync(CONTRACT_PATH, "utf8"));

describe("web prints what the contract says", () => {
  it.each(CONTRACT.cases.map((c) => [String(c.probability), c] as const))(
    "%s",
    (_label, c) => {
      expect(renderedPercent(c.probability)).toBe(c.percent);
    }
  );

  it("undefined behaves like null — a missing field is not a zero", () => {
    expect(renderedPercent(undefined)).toBeNull();
  });

  it("a non-finite number is not a percent", () => {
    expect(renderedPercent(NaN)).toBeNull();
    expect(renderedPercent(Infinity)).toBeNull();
  });
});

describe("the contract still discriminates", () => {
  // Same guard as the Python suite: a table can be defanged by deleting rows
  // while every remaining assertion stays green.
  it("keeps at least five rows where banker's rounding would differ", () => {
    const discriminating = CONTRACT.cases.filter((c) => c.discriminates);
    expect(discriminating.length).toBeGreaterThanOrEqual(5);
  });

  it("every flagged row really does disagree with banker's rounding", () => {
    // Banker's rounding, implemented here so the flag is checked against
    // arithmetic rather than trusted.
    const bankers = (x: number) => {
      const floor = Math.floor(x);
      const frac = x - floor;
      if (frac > 0.5) return floor + 1;
      if (frac < 0.5) return floor;
      return floor % 2 === 0 ? floor : floor + 1;
    };
    for (const c of CONTRACT.cases) {
      if (c.probability === null) continue;
      const differs = bankers(c.probability * 100) !== c.percent;
      expect([c.probability, differs]).toEqual([c.probability, Boolean(c.discriminates)]);
    }
  });
});

// ── THE SWIFT ARM. This is the CI half of a runtime check CI cannot run. ─────

const SWIFT_IMPL = join(
  REPO_ROOT,
  "ios/Bain Luck/Bain Luck/Utilities/RenderedPercent.swift"
);
const SWIFT_TEST = join(
  REPO_ROOT,
  "ios/Bain Luck/BainLuckTests/RenderedPercentContractTests.swift"
);
const iosPresent = existsSync(SWIFT_IMPL);
const d = iosPresent ? describe : describe.skip;

d("native encodes the SAME rule", () => {
  const impl = readFileSync(SWIFT_IMPL, "utf8");
  const code = impl
    .split("\n")
    .filter((l) => !l.trim().startsWith("///") && !l.trim().startsWith("//"))
    .join("\n");

  it("multiplies before rounding, in Double", () => {
    expect(code).toMatch(/\(probability \* 100\)\.rounded\(\)/);
  });

  it("does not name a rounding rule other than the default half-away-from-zero", () => {
    // `.rounded(.down)`, `.rounded(.toNearestOrEven)` — either would leave the
    // contract while still looking deliberate.
    expect(code).not.toMatch(/\.rounded\(\s*\./);
  });

  it("returns nil for nil and for non-finite, like the other two arms", () => {
    expect(code).toContain("probability.isFinite");
    expect(code).toContain("return nil");
  });
});

d("the Swift test table has not drifted from the contract", () => {
  const src = readFileSync(SWIFT_TEST, "utf8");
  const start = src.indexOf("CONTRACT ROWS BEGIN");
  const end = src.indexOf("CONTRACT ROWS END");

  it("has the delimited block the drift check reads", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  it("contains exactly the contract's rows, in order", () => {
    const block = src.slice(start, end);
    const rows = [...block.matchAll(/\(\s*(nil|-?[0-9.]+)\s*,\s*(nil|-?\d+)\s*\)/g)].map(
      (m) => ({
        probability: m[1] === "nil" ? null : Number(m[1]),
        percent: m[2] === "nil" ? null : Number(m[2]),
      })
    );
    expect(rows).toEqual(
      CONTRACT.cases.map((c) => ({ probability: c.probability, percent: c.percent }))
    );
  });

  it("is non-vacuous — the parse finds rows at all", () => {
    // Without this, a regex that silently matched nothing would make the
    // comparison above `[] === []` on an empty contract and pass forever.
    const block = src.slice(start, end);
    const rows = [...block.matchAll(/\(\s*(nil|-?[0-9.]+)\s*,\s*(nil|-?\d+)\s*\)/g)];
    expect(rows.length).toBe(CONTRACT.cases.length);
    expect(rows.length).toBeGreaterThan(10);
  });
});

d("the labeling card renders through the shared function, not a second copy", () => {
  const view = readFileSync(
    join(REPO_ROOT, "ios/Bain Luck/Bain Luck/Views/DiscoverLabelingView.swift"),
    "utf8"
  );
  const page = readFileSync(
    join(REPO_ROOT, "frontend/app/admin/label-pass/page.tsx"),
    "utf8"
  );

  it("native calls renderedPercent", () => {
    expect(view).toContain("renderedPercent(value)");
    expect(view).not.toMatch(/Int\(\(value \* 100\)\.rounded\(\)\)/);
  });

  it("web calls renderedPercent", () => {
    expect(page).toContain("renderedPercent(features.probability)");
    expect(page).not.toMatch(/Math\.round\(features\.probability \* 100\)/);
  });
});

describe("the contract's own registry is honest", () => {
  it("every declared implementation and driver exists and names its symbol", () => {
    for (const impl of CONTRACT.implementations) {
      const p = join(REPO_ROOT, impl.path);
      expect(existsSync(p)).toBe(true);
      expect(readFileSync(p, "utf8")).toContain(impl.symbol);
      expect(existsSync(join(REPO_ROOT, impl.driven_by))).toBe(true);
    }
  });

  it("declares all three runtimes", () => {
    expect(CONTRACT.implementations.map((i) => i.runtime).sort()).toEqual([
      "python",
      "swift",
      "typescript",
    ]);
  });
});
