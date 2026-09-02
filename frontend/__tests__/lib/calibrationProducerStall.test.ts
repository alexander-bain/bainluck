/**
 * #2649 — the banner may not promise a rebuild that is not happening.
 *
 * ## The production state this pins
 *
 * On 2026-09-02 `GET /api/calibration` served, in ONE object:
 *
 *   cache:    { status: "stale", reason: "main_key_absent", age_s: 184401 }
 *   producer: { stalled: true, beats_missed: 51 }
 *
 * and the page rendered "… and are not being refreshed right now. **The curve
 * rebuilds hourly.**" — telling a reader to come back in an hour for the 51st
 * consecutive hour. It could not self-resolve: under `q268` the publish gate
 * refused every rebuild and binned the work (`checkpoint_action: invalidate`).
 *
 * ## Why this file exists and `calibrationBannerCopy.test.tsx` did not catch it
 *
 * That suite bans forward-looking copy in this banner and EXEMPTS the schedule
 * sentence, on reasoning that is actually correct: it is present tense about a
 * cadence that is "externally true (the beat fires at :15 every hour)" and is
 * checkable rather than promissory. The exemption's premise — *the beat fires*
 * — is the thing that failed. A copy linter cannot see that; only the payload
 * can. So this suite tests the DECISION, not the prose, and the two are
 * complementary: keep both.
 *
 * The assertions below are therefore about `stalenessScheduleClause` returning
 * the right THING for a given server state, not about any particular wording.
 */
import {
  decideCalibrationStaleness,
  stalenessScheduleClause,
  type CalibrationStalenessInput,
} from "@/lib/calibrationStaleness";

/** The exact production shape from the incident, minus what this decision reads. */
const PRODUCTION_2026_09_02: CalibrationStalenessInput = {
  availability: "stale",
  cache: {
    status: "stale",
    reason: "main_key_absent",
    generated_at: "2026-08-31T04:37:36.703361+00:00",
    age_s: 184401,
  },
  producer: { stalled: true, beats_missed: 51 },
};

function clauseFor(input: CalibrationStalenessInput): string | null {
  const notice = decideCalibrationStaleness(input);
  if (notice === null) throw new Error("expected a staleness notice for this fixture");
  return stalenessScheduleClause(notice);
}

describe("the schedule clause reads the producer, not the calendar", () => {
  // --- The regression arm. This is the one that was red before the fix. ---
  it("says nothing about hourly rebuilds when the producer is stalled", () => {
    const clause = clauseFor(PRODUCTION_2026_09_02);
    expect(clause).not.toBeNull();
    // The defect, stated as the thing that must not happen. Substring, not
    // equality: any rewording that still promises the cadence fails here.
    expect(clause).not.toMatch(/rebuilds hourly/i);
  });

  it("reports the measured miss count instead", () => {
    expect(clauseFor(PRODUCTION_2026_09_02)).toContain("51");
  });

  // --- The control arm. Deleting the sentence is NOT a fix for it being
  //     wrong: when the beat really is landing, the cadence is useful and
  //     true, and a suite that passed on an always-empty clause would be
  //     satisfied by ripping the copy out. ---
  it("still states the cadence when the producer says the beat is landing", () => {
    const clause = clauseFor({
      ...PRODUCTION_2026_09_02,
      producer: { stalled: false, beats_missed: 0 },
    });
    expect(clause).toMatch(/rebuilds hourly/i);
  });

  // --- gotcha #53: absence is not health. ---
  it("says nothing at all when the payload carries no producer block", () => {
    const { producer: _omitted, ...withoutProducer } = PRODUCTION_2026_09_02;
    expect(clauseFor(withoutProducer)).toBeNull();
  });

  it("says nothing when `stalled` is present but not a boolean", () => {
    // An older or partial payload. `"true"` is not `true`, and guessing which
    // way a non-boolean leans is how the reassuring default creeps back in.
    expect(clauseFor({ ...PRODUCTION_2026_09_02, producer: { stalled: "true" } })).toBeNull();
  });

  // --- The count is evidence, so an unread count may not be invented. ---
  it("describes the stall without a number when beats_missed is unreadable", () => {
    const clause = clauseFor({
      ...PRODUCTION_2026_09_02,
      producer: { stalled: true, beats_missed: null },
    });
    expect(clause).not.toBeNull();
    expect(clause).not.toMatch(/rebuilds hourly/i);
    expect(clause).not.toMatch(/\d/);
  });

  it("does not print '0 hourly rebuilds have come and gone'", () => {
    // `stalled: true` with `beats_missed: 0` is reachable: the server sets
    // `stalled` on an UNKNOWN age while `beats_missed` floors at 0. A literal
    // read would emit a sentence that says nothing happened.
    const clause = clauseFor({
      ...PRODUCTION_2026_09_02,
      producer: { stalled: true, beats_missed: 0 },
    });
    expect(clause).not.toMatch(/^0 /);
    expect(clause).not.toMatch(/rebuilds hourly/i);
  });

  it("uses a singular verb for exactly one missed beat", () => {
    const clause = clauseFor({
      ...PRODUCTION_2026_09_02,
      producer: { stalled: true, beats_missed: 1 },
    });
    expect(clause).toContain("1 hourly rebuild has");
  });
});

describe("the notice carries the producer verdict as data", () => {
  it("distinguishes not-stated from false", () => {
    const stated = decideCalibrationStaleness({
      ...PRODUCTION_2026_09_02,
      producer: { stalled: false, beats_missed: 0 },
    });
    const { producer: _omitted, ...withoutProducer } = PRODUCTION_2026_09_02;
    const unstated = decideCalibrationStaleness(withoutProducer);
    expect(stated?.producerStalled).toBe(false);
    expect(unstated?.producerStalled).toBeNull();
  });

  it("carries the miss count through unchanged", () => {
    expect(decideCalibrationStaleness(PRODUCTION_2026_09_02)?.beatsMissed).toBe(51);
  });
});
