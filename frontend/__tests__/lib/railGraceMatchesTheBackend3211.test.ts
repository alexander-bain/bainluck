/**
 * ONE GRACE PERIOD, TWO LANGUAGES — #3211, lane1/134.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * The repair for #3211 is split across a language boundary and the two halves
 * are only correct together:
 *
 *   backend  `UPCOMING_GRACE` in `app/utils/event_completion.py` is the bound
 *            the two rails SELECT on. Past it, a `scheduled` row moves from the
 *            upcoming rail to the recent one.
 *   frontend `UPCOMING_GRACE_MS` in `lib/eventState.ts` is the bound the card
 *            RENDERS on. Past it, the card stops printing a start time and says
 *            "No result reported".
 *
 * If the backend's were LARGER, a row would reach a surface whose card then
 * advertised a start time for a match that already should have been played —
 * the upcoming-branch fall-through `lib/eventState.ts` opens by naming as the
 * quieter lie, and the exact defect live/048 removed. If it were SMALLER, a
 * card would say no result was reported about a fixture the rail still lists as
 * upcoming, which is the same contradiction told the other way.
 *
 * `lib/eventState.ts` carries a comment asking the two to stay in step. **A
 * comment is not a mechanism.** This reads the Python source and fails on any
 * disagreement, so the drift is caught by CI rather than by a reader.
 *
 * ═══ WHY IT READS THE SOURCE RATHER THAN A COPY ═══
 *
 * The whole point is to compare against what SHIPPED
 * (`r_pinned_numbers_must_come_from_the_shipped_code`). A fixture holding "2"
 * would agree with the TypeScript forever, including on the day someone edits
 * the Python. So the number is parsed out of the file every run, and the parse
 * asserts it found something before comparing — a regex that silently matches
 * nothing would make this test pass for free, which is the failure mode it is
 * most important for a source-scanning guard to avoid.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { UPCOMING_GRACE_MS } from "@/lib/eventState";

const PY_SOURCE = join(
  __dirname,
  "..",
  "..",
  "..",
  "backend",
  "app",
  "utils",
  "event_completion.py",
);

/** `UPCOMING_GRACE = timedelta(hours=2)` → 2. Throws rather than returning a
 *  default: "the constant is gone" and "the constant is 0" must not look alike. */
function backendGraceHours(): number {
  const source = readFileSync(PY_SOURCE, "utf8");
  const m = source.match(/^UPCOMING_GRACE\s*=\s*timedelta\(hours=([\d.]+)\)/m);
  if (!m) {
    throw new Error(
      "could not find `UPCOMING_GRACE = timedelta(hours=N)` in " +
        `${PY_SOURCE}. Either it was renamed or its shape changed — if the ` +
        "backend now expresses the grace some other way, this guard has to " +
        "learn that shape, not be deleted",
    );
  }
  return Number(m[1]);
}

describe("#3211 · the rail grace is one number in two languages", () => {
  test("CONTROL: the parse actually finds a number in the shipped Python", () => {
    // A source scan that matches nothing passes vacuously. Prove it bit.
    const hours = backendGraceHours();
    expect(Number.isFinite(hours)).toBe(true);
    expect(hours).toBeGreaterThan(0);
  });

  test("the frontend's grace is the backend's, to the millisecond", () => {
    expect(UPCOMING_GRACE_MS).toBe(backendGraceHours() * 60 * 60 * 1000);
  });

  test("CONTROL: the comparison would notice a disagreement", () => {
    // The guard's own control — otherwise "they are equal" could be an artefact
    // of comparing a value to itself through two paths that are really one.
    const drifted = backendGraceHours() + 1;
    expect(UPCOMING_GRACE_MS).not.toBe(drifted * 60 * 60 * 1000);
  });
});
