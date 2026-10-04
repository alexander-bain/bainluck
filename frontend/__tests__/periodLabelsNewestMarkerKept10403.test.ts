/**
 * #10403 — a baseball chart deleted its NEWEST inning marker.
 *
 * `anchorPeriodLabels` flips the marker nearest the plot's right rule so its
 * caption grows leftward. When neither row had two inks of room behind it, the
 * flipped marker itself was dropped — and the flipped marker is by
 * construction the newest one: the half-inning being played on a live page,
 * the last one on a final. Both specimens below are the served
 * `period_markers` of two production pages at 390px:
 *
 *   ALDS G1 (/events/15322539, final, Rays 1–0), chart 22:38Z–01:10Z:
 *     drew `… B7 B8`, `T9` deleted.
 *   NLDS (/events/15322620, live in the Bottom 6th), chart 00:38Z–02:48Z:
 *     drew `… T5 B5`, both `T6` and `B6` deleted.
 *
 * The repair: the LATER marker wins, and the older labels in its way give way,
 * on whichever row loses the fewest captions. The number of captions lost does
 * not change on either specimen; which ones are lost does.
 */
import {
  anchorPeriodLabels,
  PERIOD_LABEL_INK_FRACTION,
  collapseDuplicateTransitions,
  derivePeriodBoundaries,
  placePeriodLabels,
} from "@/lib/periodMarkers";

type Row = [string, string];

// Served `period_markers`, verbatim (timestamp, period), source `win_prob`.
const ALDS: Row[] = [
  ["2026-10-03T22:40:45.403162+00:00", "Top 1st"],
  ["2026-10-03T22:43:31.105519+00:00", "Middle 1st"],
  ["2026-10-03T22:46:32.780003+00:00", "Bottom 1st"],
  ["2026-10-03T22:56:57.422856+00:00", "End 1st"],
  ["2026-10-03T23:00:59.222893+00:00", "Top 2nd"],
  ["2026-10-03T23:08:59.038107+00:00", "Middle 2nd"],
  ["2026-10-03T23:11:58.608645+00:00", "Bottom 2nd"],
  ["2026-10-03T23:18:58.089704+00:00", "End 2nd"],
  ["2026-10-03T23:21:57.604525+00:00", "Top 3rd"],
  ["2026-10-03T23:28:58.193695+00:00", "Middle 3rd"],
  ["2026-10-03T23:30:58.349315+00:00", "Bottom 3rd"],
  ["2026-10-03T23:38:59.371696+00:00", "End 3rd"],
  ["2026-10-03T23:40:58.484259+00:00", "Top 4th"],
  ["2026-10-03T23:44:59.344184+00:00", "Middle 4th"],
  ["2026-10-03T23:46:58.417468+00:00", "Bottom 4th"],
  ["2026-10-03T23:52:57.414092+00:00", "End 4th"],
  ["2026-10-03T23:55:58.710615+00:00", "Top 5th"],
  ["2026-10-03T23:58:58.202967+00:00", "Middle 5th"],
  ["2026-10-04T00:01:58.553218+00:00", "Bottom 5th"],
  ["2026-10-04T00:10:00.868674+00:00", "End 5th"],
  ["2026-10-04T00:12:58.721529+00:00", "Top 6th"],
  ["2026-10-04T00:17:58.020011+00:00", "Bottom 6th"],
  ["2026-10-04T00:23:58.777019+00:00", "End 6th"],
  ["2026-10-04T00:25:57.819006+00:00", "Top 7th"],
  ["2026-10-04T00:30:58.213588+00:00", "Bottom 7th"],
  ["2026-10-04T00:38:59.409190+00:00", "End 7th"],
  ["2026-10-04T00:41:58.848686+00:00", "Top 8th"],
  ["2026-10-04T00:45:59.601213+00:00", "Middle 8th"],
  ["2026-10-04T00:47:58.528086+00:00", "Bottom 8th"],
  ["2026-10-04T01:01:59.181967+00:00", "End 8th"],
  ["2026-10-04T01:02:58.613649+00:00", "Top 9th"],
];

const NLDS: Row[] = [
  ["2026-10-04T00:38:59.409190+00:00", "Top 1st"],
  ["2026-10-04T00:49:00.110849+00:00", "Middle 1st"],
  ["2026-10-04T00:51:58.281907+00:00", "Bottom 1st"],
  ["2026-10-04T00:55:57.753713+00:00", "End 1st"],
  ["2026-10-04T00:57:58.116774+00:00", "Top 2nd"],
  ["2026-10-04T01:12:57.718102+00:00", "Middle 2nd"],
  ["2026-10-04T01:15:58.583226+00:00", "Bottom 2nd"],
  ["2026-10-04T01:23:58.439366+00:00", "End 2nd"],
  ["2026-10-04T01:26:00.524636+00:00", "Top 3rd"],
  ["2026-10-04T01:29:58.334310+00:00", "Middle 3rd"],
  ["2026-10-04T01:31:57.789699+00:00", "Bottom 3rd"],
  ["2026-10-04T01:47:58.524649+00:00", "End 3rd"],
  ["2026-10-04T01:50:57.606149+00:00", "Top 4th"],
  ["2026-10-04T02:00:57.025715+00:00", "Middle 4th"],
  ["2026-10-04T02:03:57.621021+00:00", "Bottom 4th"],
  ["2026-10-04T02:11:58.766982+00:00", "End 4th"],
  ["2026-10-04T02:13:56.887496+00:00", "Top 5th"],
  ["2026-10-04T02:24:56.591558+00:00", "Middle 5th"],
  ["2026-10-04T02:26:56.448327+00:00", "Bottom 5th"],
  ["2026-10-04T02:34:58.875759+00:00", "End 5th"],
  ["2026-10-04T02:37:58.059942+00:00", "Top 6th"],
  ["2026-10-04T02:42:57.392610+00:00", "Middle 6th"],
  ["2026-10-04T02:44:57.749125+00:00", "Bottom 6th"],
];

function chart(rows: Row[], startIso: string, endIso: string) {
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  const markers = rows
    .map(([timestamp, period]) => ({ timestamp, period, source: "win_prob" }))
    .filter((m) => new Date(m.timestamp).getTime() <= end);
  const boundaries = [
    ...derivePeriodBoundaries(undefined, undefined, undefined, markers, "baseball_mlb"),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const placed = placePeriodLabels(collapseDuplicateTransitions(boundaries), end - start);
  const anchored = anchorPeriodLabels(placed, end - start, end);
  return { placed, anchored };
}

const labels = (xs: Array<{ label?: string }>) => xs.map((x) => x.label);

describe("#10403 — the newest inning marker survives the right-edge anchor pass", () => {
  it("ALDS final: T9 is drawn, flipped at the right rule; B8 gives way", () => {
    const { placed, anchored } = chart(ALDS, "2026-10-03T22:38:00Z", "2026-10-04T01:10:00Z");
    // The fixture really is the defect's shape: placement keeps T9 last.
    expect(labels(placed).slice(-3)).toEqual(["B7", "B8", "T9"]);
    expect(labels(anchored)).toEqual(["T1", "B1", "T2", "B2", "B3", "B4", "B5", "B6", "B7", "T9"]);
    expect(anchored[anchored.length - 1].labelPosition).toBe("insideTopRight");
    // Same number of captions lost as before the repair (one).
    expect(placed.length - anchored.length).toBe(1);
  });

  it("NLDS live: B6 — the half-inning being played — is drawn; B5 and T6 give way", () => {
    const { placed, anchored } = chart(NLDS, "2026-10-04T00:38:00Z", "2026-10-04T02:48:00Z");
    expect(labels(placed).slice(-3)).toEqual(["B5", "T6", "B6"]);
    expect(labels(anchored)).toEqual(["T1", "B1", "T2", "B2", "B3", "T4", "B4", "T5", "B6"]);
    expect(anchored[anchored.length - 1].labelPosition).toBe("insideTopRight");
    expect(placed.length - anchored.length).toBe(2);
  });

  it("still never smears: every flipped caption has two inks of room on its row", () => {
    for (const [rows, s, e] of [
      [ALDS, "2026-10-03T22:38:00Z", "2026-10-04T01:10:00Z"],
      [NLDS, "2026-10-04T00:38:00Z", "2026-10-04T02:48:00Z"],
    ] as const) {
      const { anchored } = chart(rows as Row[], s, e);
      const span = new Date(e).getTime() - new Date(s).getTime();
      const ink = span * PERIOD_LABEL_INK_FRACTION;
      anchored.forEach((m, i) => {
        if (m.labelPosition !== "insideTopRight") return;
        const t = new Date(m.timestamp).getTime();
        const prior = anchored.slice(0, i).filter((p) => p.labelRow === m.labelRow);
        if (prior.length === 0) return;
        expect(t - new Date(prior[prior.length - 1].timestamp).getTime()).toBeGreaterThanOrEqual(2 * ink);
      });
    }
  });
});
