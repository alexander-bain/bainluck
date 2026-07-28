/**
 * L2-205 Item 1 — route analytics `page_type` honesty + drift guard.
 *
 * Two runtime type-contract holes shipped only because `next.config.mjs` sets
 * `typescript.ignoreBuildErrors: true` (gotcha #10):
 *   - `app/discover/scorecard/ScorecardAnalytics.tsx` emitted `page_type:
 *     "scorecard"`, which was NOT a member of the `PageViewParams` union.
 *   - `app/sports/page.tsx` (the multi-sport feed) emitted `page_type: "sports"`,
 *     while the union only had `"sport"` (the single-sport detail page at
 *     `app/sports/[key]/page.tsx`).
 *
 * Both runtime values are canonical (a distinct scorecard page; the `sports`
 * feed surface named in measurement_spec.md's `surface` taxonomy, kept distinct
 * from the `sport` detail page). The fix ADDED those two literals to the union
 * rather than silencing the callers.
 *
 * This guard locks the exact route -> page_type mapping for those routes and
 * rejects future drift in EITHER direction: a caller changing to a non-union
 * value, or the union dropping a value a caller depends on. It parses source
 * text (not TS types) so it is independent of ts-jest/tsconfig diagnostics.
 *
 * SCOPE: this asserts only the routes L2-205 owns (scorecard + the sports
 * feed/detail pair). Other pre-existing off-union `pageType` values elsewhere in
 * the app are pre-existing debt reported to Fable, not touched here.
 */
import * as fs from "fs";
import * as path from "path";

const FRONTEND_DIR = path.resolve(__dirname, "../..");
const TYPES_FILE = path.join(FRONTEND_DIR, "lib/analytics/types.ts");

/**
 * Extract the string-literal members of the `page_type:` union that immediately
 * follows a given `interface <name> {` declaration.
 */
function extractPageTypeUnion(source: string, interfaceName: string): string[] {
  const ifaceIdx = source.indexOf(`interface ${interfaceName} {`);
  if (ifaceIdx === -1) {
    throw new Error(`interface ${interfaceName} not found in types.ts`);
  }
  const fieldIdx = source.indexOf("page_type:", ifaceIdx);
  if (fieldIdx === -1) {
    throw new Error(`page_type field not found in ${interfaceName}`);
  }
  // The union runs from `page_type:` up to its terminating semicolon.
  const semiIdx = source.indexOf(";", fieldIdx);
  const span = source.slice(fieldIdx, semiIdx);
  const literals = span.match(/'([a-z0-9_]+)'/g) || [];
  return literals.map((s) => s.replace(/'/g, ""));
}

/** All `pageType: '<value>'` literals emitted in a caller file. */
function extractCallerPageTypes(absPath: string): string[] {
  const src = fs.readFileSync(absPath, "utf8");
  const matches = src.match(/pageType:\s*['"]([a-z0-9_]+)['"]/g) || [];
  return matches.map((m) => m.replace(/pageType:\s*['"]([a-z0-9_]+)['"]/, "$1"));
}

const UNION_INTERFACES = [
  "PageViewParams",
  "ScrollDepthParams",
  "TimeOnPageParams",
] as const;

describe("analytics page_type union honesty (L2-205)", () => {
  const source = fs.readFileSync(TYPES_FILE, "utf8");
  const unions = Object.fromEntries(
    UNION_INTERFACES.map((name) => [name, extractPageTypeUnion(source, name)]),
  ) as Record<(typeof UNION_INTERFACES)[number], string[]>;

  it("the three page_type unions stay identical (no partial edits)", () => {
    // page_view / scroll_depth / time_on_page share one page_type vocabulary.
    // Editing one union without the others is a drift bug.
    const base = new Set(unions.PageViewParams);
    for (const name of UNION_INTERFACES) {
      expect(new Set(unions[name])).toEqual(base);
    }
  });

  it("includes the canonical scorecard + sports values", () => {
    for (const name of UNION_INTERFACES) {
      expect(unions[name]).toContain("scorecard");
      expect(unions[name]).toContain("sports");
    }
  });

  it("keeps the sports feed distinct from the sport detail page", () => {
    // Regression guard: collapsing the multi-sport feed (`sports`) into the
    // single-sport detail page (`sport`) would conflate two surfaces.
    expect(unions.PageViewParams).toContain("sport");
    expect(unions.PageViewParams).toContain("sports");
  });
});

describe("route -> page_type mapping is truthful (L2-205)", () => {
  const source = fs.readFileSync(TYPES_FILE, "utf8");
  const union = new Set(extractPageTypeUnion(source, "PageViewParams"));

  // The exact routes L2-205 owns, and their canonical single page_type value.
  const ROUTE_MAP: Array<{ file: string; expected: string }> = [
    {
      file: "app/discover/scorecard/ScorecardAnalytics.tsx",
      expected: "scorecard",
    },
    { file: "app/sports/page.tsx", expected: "sports" },
    { file: "app/sports/[key]/page.tsx", expected: "sport" },
  ];

  for (const { file, expected } of ROUTE_MAP) {
    it(`${file} emits only "${expected}" and it is a union member`, () => {
      const emitted = extractCallerPageTypes(path.join(FRONTEND_DIR, file));
      // All three GA4 hooks (page/scroll/time) must agree on the same value.
      expect(emitted.length).toBeGreaterThanOrEqual(1);
      for (const value of emitted) {
        expect(value).toBe(expected);
        expect(union.has(value)).toBe(true);
      }
    });
  }
});
