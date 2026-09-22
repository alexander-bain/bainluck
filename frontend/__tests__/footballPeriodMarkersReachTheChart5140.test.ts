/**
 * #5140 — the corrected football markers survive the web's own marker pipeline.
 *
 * The backend half of this ship (PR #6699) changes what `period_markers` CONTAINS
 * and, for the first time on football, what its `period` strings LOOK like: the
 * first-score tiers served bare digits (`"2"`, `"3"`, `"4"` — the very payload
 * #4888 was written about), and the observed-transition tier serves ESPN's own
 * vocabulary (`"2nd Quarter"`, `"Halftime"`).
 *
 * "Web needs no change" was read off the code. This executes it instead, because
 * a served label is also a lookup key: `derivePeriodBoundaries` is what both
 * `OddsChart` and `ScoreDifferentialChart` draw from, and a string it cannot
 * normalise becomes a rule labelled with raw ESPN text — or, in the one case
 * worth fearing, a Q2 dragged back to kickoff by `applyCommenceTime`.
 *
 * #7901 REMOVED `applyCommenceTime` ENTIRELY, so the case this suite feared is
 * now structurally impossible rather than guarded — and the case it did NOT
 * fear, a Q1 dragged back to kickoff, turned out to be the live defect. Both
 * assertions below are kept: they now pin the absence of a rule rather than the
 * correctness of its exception, which is the stronger of the two.
 *
 * The payloads below are the BEFORE and AFTER of the two specimens on the issue,
 * as production serves them and as the fixed route serves them.
 */

import { derivePeriodBoundaries } from "@/lib/periodMarkers";

const NFL = "americanfootball_nfl";

/** 14638896 Chiefs–Broncos, kickoff 2026-09-15T00:15:00Z. */
const CHIEFS_BRONCOS_COMMENCE = "2026-09-15T00:15:00+00:00";
const CHIEFS_BRONCOS_AFTER = [
  { timestamp: "2026-09-15T00:17:12+00:00", period: "1st Quarter" },
  { timestamp: "2026-09-15T00:54:43+00:00", period: "2nd Quarter" },
  { timestamp: "2026-09-15T01:41:44+00:00", period: "Halftime" },
  { timestamp: "2026-09-15T01:56:23+00:00", period: "3rd Quarter" },
  { timestamp: "2026-09-15T02:36:23+00:00", period: "4th Quarter" },
];

/** 14780138 Patriots–Seahawks. Nobody saw Q1 start, so the fix serves no Q1. */
const PATRIOTS_SEAHAWKS_COMMENCE = "2026-09-10T00:20:00+00:00";
const PATRIOTS_SEAHAWKS_BEFORE = [
  { timestamp: "2026-09-10T00:24:28.214933+00:00", period: "2" },
  { timestamp: "2026-09-10T00:24:28.214933+00:00", period: "3" },
  { timestamp: "2026-09-10T02:44:55.073599+00:00", period: "4" },
];
const PATRIOTS_SEAHAWKS_AFTER = [
  { timestamp: "2026-09-10T00:57:30+00:00", period: "2nd Quarter" },
  { timestamp: "2026-09-10T01:39:03+00:00", period: "Halftime" },
  { timestamp: "2026-09-10T01:53:41+00:00", period: "3rd Quarter" },
  { timestamp: "2026-09-10T02:36:55+00:00", period: "4th Quarter" },
];

const draw = (markers: Array<{ timestamp: string; period: string }>) =>
  derivePeriodBoundaries(undefined, undefined, undefined, markers, NFL);

describe("#5140 — corrected football markers reach the chart", () => {
  it("draws Q1 HT Q3 Q4 from ESPN's vocabulary, at the corrected times", () => {
    const drawn = draw(CHIEFS_BRONCOS_AFTER);

    expect(drawn.map((b) => b.label)).toEqual(["Q1", "Q2", "HT", "Q3", "Q4"]);
    // #7901: Q1 stands where it was SEEN (00:17:12), not at kickoff (00:15:00).
    // 2m12s is the ordinary, invisible end of the correction this suite's own
    // specimen happens to sit at — the same rule moved MLB 15316297 by 47.6 min.
    expect(drawn.find((b) => b.label === "Q1")!.timestamp).toBe(
      "2026-09-15T00:17:12+00:00",
    );
    expect(drawn.find((b) => b.label === "Q1")!.timestamp).not.toBe(
      CHIEFS_BRONCOS_COMMENCE,
    );
    // The defect, in the one number a reader could see: Q2 was drawn at
    // 01:33:43Z — the quarter's only touchdown, 39 minutes after it began.
    expect(drawn.find((b) => b.label === "Q2")!.timestamp).toBe(
      "2026-09-15T00:54:43+00:00",
    );
    // Halftime is a rule of its own and is not folded into Q3.
    expect(drawn.find((b) => b.label === "HT")!.timestamp).toBe(
      "2026-09-15T01:41:44+00:00",
    );
  });

  it("does not drag a leading Q2 back to kickoff when Q1 is absent", () => {
    // The one live risk in serving fewer markers than before USED to be
    // `applyCommenceTime` rewriting the FIRST boundary to `commence_time`,
    // held off only by its first-period label test. #7901 removed the rewrite,
    // so nothing can drag any leading marker to kickoff — this now pins that.
    const drawn = draw(PATRIOTS_SEAHAWKS_AFTER);

    expect(drawn.map((b) => b.label)).toEqual(["Q2", "HT", "Q3", "Q4"]);
    expect(drawn[0].timestamp).toBe("2026-09-10T00:57:30+00:00");
    expect(drawn[0].timestamp).not.toBe(PATRIOTS_SEAHAWKS_COMMENCE);
  });

  it("is a change the reader can see: the served payload stacks two quarters", () => {
    // Control on the BEFORE, so the assertions above are known to be measuring
    // the fix rather than agreeing with what was already drawn.
    const drawn = draw(PATRIOTS_SEAHAWKS_BEFORE);

    expect(drawn.map((b) => b.label)).toEqual(["Q2", "Q3", "Q4"]);
    expect(drawn[0].timestamp).toBe(drawn[1].timestamp); // Q2 and Q3, one instant
    expect(drawn.some((b) => b.label === "HT")).toBe(false);
  });

  it("keeps the additive keys off the drawn boundary", () => {
    // `precision` and `not_before` are new keys on each marker. The chart takes
    // `{timestamp, label}` and nothing else, so an old client reads exactly what
    // it read before — asserted rather than assumed, since this is the claim
    // that let the backend half ship without a client change.
    const withKeys = CHIEFS_BRONCOS_AFTER.map((m) => ({
      ...m,
      precision: "boundary_observed",
      not_before: "2026-09-15T00:53:43+00:00",
      source: "win_prob",
    }));

    expect(draw(withKeys)).toEqual(
      draw(CHIEFS_BRONCOS_AFTER),
    );
  });
});
