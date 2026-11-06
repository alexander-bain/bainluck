/**
 * #12102 S4 — the test library prints the scoreboard as recorded.
 *
 * `data/scoreboard-2026-11-03.json` is the unedited output of
 * `python3 -m scripts.evals.scoreboard --json`. These tests hold the page's
 * reading of it to the command's own rules (`backend/scripts/evals/README.md`):
 * a family's case count is the family's own total, never a sum of its members;
 * a missing count makes it a floor; a member with no recorded run is
 * unrecorded, never a pass. And the commit the page links is the record's.
 */

import RAW from "@/lib/evals/data/scoreboard-2026-11-03.json";
import {
  FAMILY_WORDS,
  biteTruth,
  familyView,
  libraryTruth,
  loadScoreboard,
  recordedClock,
  recordedDate,
  scoreboardProblem,
} from "@/lib/evals/scoreboard";
import { sourceLink } from "@/lib/evals/sources";

type Raw = typeof RAW;
const clone = (): Raw => JSON.parse(JSON.stringify(RAW));

describe("the committed scoreboard", () => {
  const board = loadScoreboard();

  it("reads, and its recorded day is the day in its file name", () => {
    expect(scoreboardProblem(RAW)).toBeNull();
    expect(board).not.toBeNull();
    expect(recordedDate(RAW.recorded_at_pt)).toBe("2026-11-03");
    expect(recordedClock(RAW.recorded_at_pt)).toBe("8:48 PM PT");
  });

  it("the Nov 3 record: 40 of 40 planted changes caught, 0 of 40 on the site's own code; golden 666 of 709", () => {
    expect(board?.bite).toEqual({ total: 40, caught: 40, realCode: 0 });
    expect(board?.golden).toEqual({ passing: 666, total: 709, floor: 666, declaredTotal: 709 });
  });

  it("every family has plain words, and every set of words has a family", () => {
    const canonicals = RAW.families.map((f) => f.canonical);
    expect(canonicals.filter((c) => !FAMILY_WORDS[c])).toEqual([]);
    expect(Object.keys(FAMILY_WORDS).filter((c) => !canonicals.includes(c))).toEqual([]);
    for (const f of RAW.families) expect(familyView(f).name).not.toBe(f.canonical);
  });

  it("the number of checks the page prints is the registry's, and it equals the families' members", () => {
    const members = RAW.families.reduce((s, f) => s + f.members.length, 0);
    expect(board?.registry.registered).toBe(members);
  });

  it("the source links pin the record's own commit", () => {
    const short = RAW.recorded_source_sha.slice(0, 10);
    expect(sourceLink("bite-audit").href).toContain(`/blob/${short}/`);
    expect(sourceLink("golden-baseline").href).toContain(`/blob/${short}/`);
    expect(board && biteTruth(board)).toEqual({ kind: "last_run", asOf: "2026-11-03", source: sourceLink("bite-audit") });
    expect(board && libraryTruth(board).asOf).toBe("2026-11-03");
  });
});

describe("a family is read by the command's rules", () => {
  const families = RAW.families.map(familyView);

  it("its case count is the family's own total, never the sum of its members", () => {
    for (const [i, f] of families.entries()) expect(f.cases).toBe(RAW.families[i].cases);
    // The search family shares one gold set across four members; summing them
    // would count it four times.
    const search = RAW.families.find((f) => f.canonical === "search_truth_closure_contract");
    const summed = (search?.members ?? []).reduce((s, m) => s + (m.cases ?? 0), 0);
    expect(summed).toBeGreaterThan(search?.cases ?? 0);
  });

  it("a member with no recorded count makes the family's count a floor", () => {
    for (const [i, f] of families.entries()) {
      expect(f.casesAtLeast).toBe(RAW.families[i].unknown_case_counts.length > 0);
    }
    expect(families.filter((f) => f.casesAtLeast).map((f) => f.canonical)).toEqual([
      "admin_surface_truth_contract",
    ]);
  });

  it("only recorded members count toward the recorded run, and the rest are unrecorded", () => {
    for (const [i, f] of families.entries()) {
      const raw = RAW.families[i];
      const recorded = raw.members.filter((m) => m.last_result !== null);
      expect(f.recorded + f.unrecorded).toBe(raw.members.length);
      expect(f.unrecorded).toBe(raw.members.length - recorded.length);
      expect(f.passed).toBe(recorded.reduce((s, m) => s + (m.last_result?.passed ?? 0), 0));
      expect(f.failed).toBe(recorded.reduce((s, m) => s + (m.last_result?.failed ?? 0), 0));
    }
  });

  it("a family with no plain words keeps its registry name rather than inventing one", () => {
    const stranger = { ...RAW.families[0], canonical: "new_family_contract" };
    expect(familyView(stranger).name).toBe("new_family_contract");
    expect(familyView(stranger).checks).toBe("");
  });
});

describe("a scoreboard that cannot be read is absent, never half-shown", () => {
  it.each<[string, (b: Raw) => void, RegExp]>([
    ["another schema", (b) => void ((b as { schema_version: string }).schema_version = "eval-scoreboard/v2"), /schema/],
    ["an unreadable record time", (b) => void (b.recorded_at_pt = "Nov 3 evening"), /recorded_at_pt/],
    ["a short commit", (b) => void (b.recorded_source_sha = "54470c89fd"), /full commit/],
    ["no families", (b) => void (b.families = []), /no families/],
    ["an unreadable member result", (b) => void ((b.families[0].members[0] as { last_result: unknown }).last_result = { passed: "4" }), /last result/],
    ["golden passing more than it has", (b) => void (b.golden.passing = b.golden.total + 1), /golden/],
    ["more bites than its sample", (b) => void (b.bite_rate.mutation_bites = b.bite_rate.total + 1), /bite_rate/],
    ["no registry", (b) => void delete (b as Partial<Raw>).registry, /registry/],
  ])("%s", (_label, breakIt, why) => {
    const broken = clone();
    breakIt(broken);
    expect(scoreboardProblem(broken)).toMatch(why);
    expect(loadScoreboard(broken)).toBeNull();
  });
});
