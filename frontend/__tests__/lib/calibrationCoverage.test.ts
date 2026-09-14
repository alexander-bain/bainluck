// CAL-P1217 — the coverage accounting the accuracy page shows, and the far
// longer list of things it refuses to show.
//
// The selector's whole job is judgement about whether a census may be handed to
// a reader, so the refusals ARE the subject: an accounting that renders when it
// should not is a page telling a reader a partition adds up when it does not.
// Every refusal below is graded by mutating ONE field of a census that renders,
// so a passing assertion can never be "this object was malformed in some way".

import * as fs from "fs";
import * as path from "path";

import {
  readCoverageAccounting,
  RUNG_LABELS,
  PLOTTED_RUNG,
  COVERAGE_BRIDGE_SCHEMA,
} from "@/lib/calibrationCoverage";
import { COMPLETE_CENSUS } from "./calibrationCensusFixture";

/** A deep-enough clone to mutate one field without touching the fixture. */
const clone = (): any => JSON.parse(JSON.stringify(COMPLETE_CENSUS));

const rungIn = (census: any, key: string) =>
  census.coverage_bridge.rungs.find((r: any) => r.key === key);

describe("the accounting the reader gets", () => {
  it("reads the covered population, the plotted count and the difference", () => {
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    expect(a).not.toBeNull();
    expect(a.covered).toBe(734400);
    expect(a.plotted).toBe(412889);
    expect(a.excluded).toBe(734400 - 412889);
  });

  it("adds up: plotted plus every listed exclusion is the covered population", () => {
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    const sum = a.rows.reduce((s, r) => s + r.outcomes, a.plotted);
    expect(sum).toBe(a.covered);
  });

  it("lists the largest exclusion first", () => {
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    const counts = a.rows.map(r => r.outcomes);
    expect(counts).toEqual([...counts].sort((x, y) => y - x));
    expect(a.rows[0].key).toBe("representative_not_selected");
  });

  it("never puts the terminal rung among the exclusions", () => {
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    expect(a.rows.map(r => r.key)).not.toContain(PLOTTED_RUNG);
  });

  it("counts a measured-zero rule rather than listing it as an exclusion", () => {
    // `field_incomplete` is 0 in the fixture: a rule that fired on nobody.
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    expect(a.rows.map(r => r.key)).not.toContain("field_incomplete");
    expect(a.emptyRules).toBe(1);
  });

  it("labels every row from this module, never from the payload", () => {
    const a = readCoverageAccounting(COMPLETE_CENSUS)!;
    const serverRules = new Set(
      (COMPLETE_CENSUS.coverage_bridge.rungs as ReadonlyArray<{ rule: string }>).map(r => r.rule)
    );
    for (const row of a.rows) {
      expect(row.label).toBe(RUNG_LABELS[row.key]);
      expect(serverRules.has(row.label)).toBe(false);
    }
  });

  it("names every rung the server can emit", () => {
    // The closed label map is what lets the selector refuse an unknown rung.
    // If the server's partition grows, this reds here — in the one place that
    // knows what a reader would need to be told — rather than on the page.
    const emitted = (COMPLETE_CENSUS.coverage_bridge.rungs as ReadonlyArray<{ key: string }>).map(
      r => r.key
    );
    expect(emitted.sort()).toEqual(Object.keys(RUNG_LABELS).sort());
  });
});

describe("what it refuses to show", () => {
  it("shows nothing for a census that is not there", () => {
    expect(readCoverageAccounting(undefined)).toBeNull();
    expect(readCoverageAccounting(null)).toBeNull();
  });

  it("shows nothing for the unavailable placeholder the build publishes today", () => {
    // The live payload's actual state: the switch is off, so the builder writes
    // an explicitly-unavailable census with every count null. This is the case
    // that must leave the page exactly as it was.
    const census = clone();
    census.status = "unavailable";
    census.reason = "census_disabled_pending_futures_phase_budget";
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when a rung was not measured", () => {
    const census = clone();
    const rung = rungIn(census, "phantom_liquidity");
    rung.outcomes = null;
    rung.checked = false;
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("distinguishes an unchecked zero from a measured one", () => {
    // `checked` is the entire difference between "this rule excluded nobody"
    // and "nobody counted". Same printed number, opposite meanings.
    const census = clone();
    const rung = rungIn(census, "field_incomplete");
    rung.checked = false;
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing for a rung it cannot put a sentence to", () => {
    // RENAMED, not appended, and it is the ZERO rung that is renamed: the
    // arithmetic still balances and the rung count is still eleven, so the
    // unknown-label refusal is the only guard that can return null here.
    // Appending a rung instead — the obvious way to write this — is caught by
    // the arithmetic and by the rung count, and the test then passes with the
    // label refusal deleted (measured: it did).
    const census = clone();
    rungIn(census, "field_incomplete").key = "some_new_rule_the_client_has_never_heard_of";
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when a rung the partition needs is missing", () => {
    // Again the zero rung, for the same isolation reason: dropping one that
    // excluded outcomes would be caught by the arithmetic. A rule that fired on
    // nobody can go missing without moving a single number, which is exactly
    // why the count of rungs is checked separately.
    const census = clone();
    census.coverage_bridge.rungs = census.coverage_bridge.rungs.filter(
      (r: any) => r.key !== "field_incomplete"
    );
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when the bridge says it does not reconcile", () => {
    const census = clone();
    census.coverage_bridge.reconciles = false;
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when the two independent counts of the curve disagree", () => {
    const census = clone();
    census.invariants.violations = ["PLOTTED_HINGE_DIVERGES"];
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when the rungs do not add up to the stated population", () => {
    // `reconciles: true` is computed by the server from its own rungs. This is
    // the case where the server says the bridge is sound and the arithmetic
    // says otherwise — the two halves came from different walks.
    const census = clone();
    census.units.outcomes_with_calibration_coverage.value = 999_999;
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when the covered population is missing", () => {
    // Graded as BEHAVIOUR, not as an isolated guard: at runtime the arithmetic
    // catches this one too, so deleting `isCount(covered)` leaves this test
    // green. That line survives because it is what narrows `unknown` to
    // `number` for the returned object — the type checker kills the mutant the
    // suite cannot. Same for the `plotted === null` check. Recorded rather than
    // papered over with an assertion written to make a survivor go away.
    const census = clone();
    census.units.outcomes_with_calibration_coverage.value = null;
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing for a schema it does not know", () => {
    const census = clone();
    census.schema_version = "calibration-coverage-bridge/v2";
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("shows nothing when one rung appears twice and another not at all", () => {
    // The one duplicate shape none of the other guards can see: the zero rung
    // re-keyed onto a rung that is already present. Eleven entries, every label
    // known, the arithmetic untouched because the copy carries zero — and one
    // whole exclusion rule silently absent from a list a reader is invited to
    // add up. Pushing a copy instead leaves twelve entries and is caught by the
    // rung count, which is how this test passed for the wrong reason first.
    const census = clone();
    rungIn(census, "field_incomplete").key = "phantom_liquidity";
    expect(readCoverageAccounting(census)).toBeNull();
  });

  it("tolerates shapes that are not objects at all", () => {
    for (const junk of ["", 0, [], [1, 2], true, "a census"]) {
      expect(readCoverageAccounting(junk)).toBeNull();
    }
  });
});

describe("the label map tracks the server's partition", () => {
  // The fixture is a SNAPSHOT of the server's rungs, so a rung added tomorrow
  // would not red any assertion above it — the page would simply stop showing
  // the accounting, safely and silently, and nobody would know why. This reads
  // the partition from the server's own source instead, so the drift reds on
  // the commit that causes it. A monorepo checkout always has both trees; a
  // missing file is a failure here rather than a skip, because a skip is how a
  // cross-tree guard quietly stops guarding.
  const BRIDGE_PATH = path.join(
    __dirname, "..", "..", "..", "backend", "app", "utils", "calibration_coverage_bridge.py"
  );

  function serverRungKeys(): string[] {
    const src = fs.readFileSync(BRIDGE_PATH, "utf8");
    const start = src.indexOf("BRIDGE_RUNGS: tuple[tuple[str, str], ...] = (");
    expect(start).toBeGreaterThan(-1);
    const end = src.indexOf("\n)", start);
    expect(end).toBeGreaterThan(start);
    const block = src.slice(start, end);
    // Each entry opens with its key as a bare string literal on its own line,
    // except the terminal one, which is the PLOTTED_RUNG constant.
    const keys = [...block.matchAll(/^ {8}"([a-z_]+)",$/gm)].map(m => m[1]);
    if (block.includes("        PLOTTED_RUNG,")) keys.push(PLOTTED_RUNG);
    return keys;
  }

  it("finds the partition in the server's source", () => {
    // The control: a regex that matches nothing would make the next test pass
    // against an empty set forever.
    expect(serverRungKeys().length).toBe(Object.keys(RUNG_LABELS).length);
    expect(serverRungKeys()).toContain("phantom_liquidity");
  });

  it("has a reader's sentence for every rung the server defines", () => {
    expect(serverRungKeys().sort()).toEqual(Object.keys(RUNG_LABELS).sort());
  });
});

describe("the fixture is the producer's own shape", () => {
  it("carries the schema the serve path writes", () => {
    expect(COMPLETE_CENSUS.schema_version).toBe(COVERAGE_BRIDGE_SCHEMA);
  });

  it("is INCOMPLETE, and renders anyway — the trap this suite exists to pin", () => {
    // The serve-time attach cannot supply `sportsbook_curve_legs`, so the
    // observation bridge is always UNKNOWN and the census's overall status can never
    // be "complete". Gating the reader on that status would have shipped a
    // component that renders for nobody, ever, and no test over a hand-built
    // "complete" fixture would have caught it.
    expect(COMPLETE_CENSUS.status).toBe("incomplete");
    expect(COMPLETE_CENSUS.invariants.violations).toEqual(["OBSERVATION_BRIDGE_UNKNOWN"]);
    expect(readCoverageAccounting(COMPLETE_CENSUS)).not.toBeNull();
  });
});
