/**
 * #4259 — EVERY FIELD SURFACE STEPS THE SAME LADDER.
 *
 * The defect was never in FuturesChart: the component could always take an axis top,
 * and #2451 had already ruled what that top should be. The bug was that the four
 * surfaces which draw a FIELD each rendered `<FuturesChart>` without asking for it,
 * so the golf hub sat on a flat 0–100% axis for four months after the ruling.
 *
 * A component-level test cannot see that class — it passes the prop itself. So this
 * one reads the call sites, and it is the test that fails on the parent commit.
 *
 * It also catches the NEXT one: a new field surface added without the prop fails
 * here rather than shipping flat, and the allowlist forces a stated reason instead
 * of a silent omission.
 */
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const ROOT = join(__dirname, "..", "..");

/**
 * Surfaces that render `<FuturesChart>` and must NOT step the ladder, each with the
 * reason. A file here is a decision on the record, not an exemption.
 */
const NOT_A_FIELD_CHART: Record<string, string> = {
  "components/TeamSeasonJourney.tsx":
    "one team's season line, not a field — it uses the opt-in zoom chip (L2-164) instead",
  "components/event/SettledPathChart.tsx":
    "settled: the winner is at 100%, so the ladder would return 1.0 and the prop would be inert",
  "components/event/TwoSidedTimeline.tsx":
    "co_equal_list — two head-to-head competitors summing to 100%, the case a flat 0–100% axis is RIGHT for",
};

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx$/.test(entry)) out.push(full);
  }
  return out;
}

/** The opening tag of every `<FuturesChart …>` in a file, attributes included. */
function futuresChartTags(src: string): string[] {
  return [...src.matchAll(/<FuturesChart\b[\s\S]*?\/>/g)].map((m) => m[0]);
}

describe("#4259 field-chart call sites", () => {
  const files = [...walk(join(ROOT, "app")), ...walk(join(ROOT, "components"))]
    .map((f) => ({ rel: f.slice(ROOT.length + 1), src: readFileSync(f, "utf8") }))
    // The component's own file defines the prop; it is not a call site.
    .filter((f) => f.rel !== "components/FuturesChart.tsx")
    .map((f) => ({ ...f, tags: futuresChartTags(f.src) }))
    .filter((f) => f.tags.length > 0);

  test("the scan finds the call sites at all (a zero-row census is not a pass)", () => {
    // Without this, deleting the component or renaming the tag makes every
    // assertion below vacuously true.
    expect(files.length).toBeGreaterThanOrEqual(5);
    expect(files.map((f) => f.rel)).toEqual(
      expect.arrayContaining([
        "components/EvolutionView.tsx",
        "components/event/WinnerEvolutionChart.tsx",
        "app/categories/golf/page.tsx",
        "app/futures/[id]/page.tsx",
        "components/event/RaceToTitleChart.tsx",
      ]),
    );
  });

  test("every field surface passes fieldCeiling", () => {
    const missing = files
      .filter((f) => !(f.rel in NOT_A_FIELD_CHART))
      .filter((f) => f.tags.some((t) => !/\bfieldCeiling\b/.test(t)))
      .map((f) => f.rel);
    expect(missing).toEqual([]);
  });

  test("the allowlist is live — every exempted file still renders the chart", () => {
    // A stale allowlist entry is a lie about the codebase; fail rather than carry it.
    const scanned = new Set(files.map((f) => f.rel));
    for (const rel of Object.keys(NOT_A_FIELD_CHART)) {
      expect(scanned.has(rel)).toBe(true);
    }
  });

  test("the exempted surfaces really do stay off the ladder", () => {
    for (const rel of Object.keys(NOT_A_FIELD_CHART)) {
      const f = files.find((x) => x.rel === rel)!;
      for (const tag of f.tags) expect(tag).not.toMatch(/\bfieldCeiling\b/);
    }
  });
});
