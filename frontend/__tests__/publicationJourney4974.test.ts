/**
 * #4974 slice 1 (web, #10487) — the pure rules behind a finished game's
 * checkpoint dots and its checkpoint-only scrub. Boundary:
 * `4974-UX-READER-SLICE-1-BOUNDARY.md`, section B, guards (i)–(vi).
 *
 * A recorded checkpoint is a value at an instant and nothing more: `t` is
 * stamped at insert before commit and `rev` counts bag commits only, so no
 * stretch between two checkpoints is vouched for. Every arm below pins one way
 * a reader could be shown a value that was never recorded — a held value
 * between dots, a cursor that does not snap, a clock that is the cursor's, a
 * window cut on array order, or a tie that flips with array order.
 *
 * The x scale here is linear, 1px per 10 s, from a fixed anchor (gotcha #44:
 * no clock reads). TZ is pinned to UTC by jest.config.js — so a Pacific label
 * here is the formatter's zone, never the process's.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { format } from "date-fns";

import {
  CHECKPOINT_HIT_RADIUS_PX,
  chartXToTime,
  checkpointClockLabel,
  eligibleCheckpoints,
  insideRecordedWindow,
  latestCheckpoint,
  publicationReadout,
  publicationReadoutAt,
  recordedWindow,
  rowIndexAt,
  scrubAtPointer,
  spanTouchesRecordedWindow,
  timeToChartX,
  type CheckpointVertex,
} from "@/lib/publicationJourney";
import type { EventPublicationsResponse, PublicationVertex } from "@/lib/types";

const ANCHOR = Date.UTC(2026, 9, 4, 23, 0, 0);
const MIN = 60_000;
const iso = (offsetMs: number) => new Date(ANCHOR + offsetMs).toISOString();
/** 1px per 10 s. */
const xOf = (v: CheckpointVertex) => (v.tMs - ANCHOR) / 10_000;

function body(vertices: PublicationVertex[], over: Partial<EventPublicationsResponse> = {}): EventPublicationsResponse {
  return {
    event_id: 15323826,
    schema_version: 1,
    time_basis: "recorded_at_insert_before_commit",
    truncated: false,
    vertices,
    ...over,
  };
}

function cps(vertices: PublicationVertex[]): CheckpointVertex[] {
  const out = eligibleCheckpoints(body(vertices), { finished: true });
  if (!out) throw new Error("fixture refused — the arm would be vacuous");
  return out;
}

describe("eligibility: only a finished, complete, well-formed response with two or more checkpoints", () => {
  const two = [
    { rev: 1, t: iso(0), p: 0.6 },
    { rev: 2, t: iso(MIN), p: 0.62 },
  ];

  it("accepts the contract and keeps served order and every field as served", () => {
    const out = eligibleCheckpoints(body(two), { finished: true });
    expect(out).toEqual([
      { rev: 1, t: two[0].t, p: 0.6, tMs: ANCHOR },
      { rev: 2, t: two[1].t, p: 0.62, tMs: ANCHOR + MIN },
    ]);
  });

  it.each([
    ["a live game", body(two), { finished: false }],
    ["no response (404, error, refused)", null, { finished: true }],
    ["a truncated response", body([], { truncated: true }), { finished: true }],
    ["truncated even with vertices", body(two, { truncated: true }), { finished: true }],
    ["an unknown schema", body(two, { schema_version: 2 }), { finished: true }],
    ["an empty body (never recorded, or folded)", body([]), { finished: true }],
    ["a single checkpoint", body([two[0]]), { finished: true }],
  ])("refuses %s", (_name, response, opts) => {
    expect(eligibleCheckpoints(response as EventPublicationsResponse | null, opts)).toBeNull();
  });

  it.each([
    ["p null", { rev: 3, t: iso(2 * MIN), p: null }],
    ["p above 1", { rev: 3, t: iso(2 * MIN), p: 1.2 }],
    ["an unparseable t", { rev: 3, t: "not-a-time", p: 0.5 }],
    ["a fractional rev", { rev: 3.5, t: iso(2 * MIN), p: 0.5 }],
  ])("refuses the whole response when one vertex has %s", (_name, bad) => {
    expect(eligibleCheckpoints(body([...two, bad as never]), { finished: true })).toBeNull();
  });
});

describe("(v) the recorded window is [min t, max t], never the first and last rev", () => {
  // rev order with non-monotonic t: rev 2 carries the latest t, rev 3 the earliest.
  const vertices = cps([
    { rev: 1, t: iso(10 * MIN), p: 0.5 },
    { rev: 2, t: iso(40 * MIN), p: 0.55 },
    { rev: 3, t: iso(5 * MIN), p: 0.52 },
    { rev: 4, t: iso(20 * MIN), p: 0.6 },
  ]);

  it("spans 5 min to 40 min", () => {
    expect(recordedWindow(vertices)).toEqual({ startMs: ANCHOR + 5 * MIN, endMs: ANCHOR + 40 * MIN });
  });

  it("would be 10–20 min if cut on array order — the specimen discriminates", () => {
    const first = vertices[0].tMs;
    const last = vertices[vertices.length - 1].tMs;
    expect([first, last]).toEqual([ANCHOR + 10 * MIN, ANCHOR + 20 * MIN]);
  });

  it("includes both ends and nothing outside them", () => {
    const w = recordedWindow(vertices);
    expect(insideRecordedWindow(ANCHOR + 5 * MIN, w)).toBe(true);
    expect(insideRecordedWindow(ANCHOR + 40 * MIN, w)).toBe(true);
    expect(insideRecordedWindow(ANCHOR + 5 * MIN - 1, w)).toBe(false);
    expect(insideRecordedWindow(ANCHOR + 40 * MIN + 1, w)).toBe(false);
    expect(insideRecordedWindow(ANCHOR, null)).toBe(false);
  });
});

describe("(i) between two distant checkpoints there is no reading", () => {
  // 0 min at x=0, 20 min at x=120: 120px apart.
  const vertices = cps([
    { rev: 7, t: iso(0), p: 0.4 },
    { rev: 8, t: iso(20 * MIN), p: 0.7 },
  ]);

  it("midway returns null, not the earlier checkpoint carried forward", () => {
    expect(publicationReadoutAt(vertices, 60, xOf)).toBeNull();
    expect(publicationReadout(vertices, 60, xOf)).toBeNull();
  });

  it("anywhere beyond the radius of both returns null", () => {
    for (let px = CHECKPOINT_HIT_RADIUS_PX + 1; px < 120 - CHECKPOINT_HIT_RADIUS_PX; px++) {
      expect(publicationReadoutAt(vertices, px, xOf)).toBeNull();
    }
  });
});

describe("(ii) an isolated dot answers itself and only within the radius", () => {
  const vertices = cps([
    { rev: 1, t: iso(0), p: 0.4 },
    { rev: 2, t: iso(10 * MIN), p: 0.63 }, // x = 60
    { rev: 3, t: iso(20 * MIN), p: 0.7 },
  ]);
  const dot = vertices[1];

  it("at its exact x", () => {
    expect(publicationReadoutAt(vertices, 60, xOf)).toBe(dot);
  });

  it("at the radius on both sides", () => {
    expect(publicationReadoutAt(vertices, 60 - CHECKPOINT_HIT_RADIUS_PX, xOf)).toBe(dot);
    expect(publicationReadoutAt(vertices, 60 + CHECKPOINT_HIT_RADIUS_PX, xOf)).toBe(dot);
  });

  it("radius + 1px on both sides is nothing", () => {
    expect(CHECKPOINT_HIT_RADIUS_PX).toBe(8);
    expect(publicationReadoutAt(vertices, 60 - CHECKPOINT_HIT_RADIUS_PX - 1, xOf)).toBeNull();
    expect(publicationReadoutAt(vertices, 60 + CHECKPOINT_HIT_RADIUS_PX + 1, xOf)).toBeNull();
  });

  it("a vertex the axis cannot place is not readable", () => {
    expect(publicationReadoutAt(vertices, 60, (v) => (v === dot ? null : xOf(v)))).toBeNull();
  });
});

describe("(iii) a snapped readout carries the checkpoint's own x, value and clock — never the cursor's", () => {
  // Checkpoint at 23:10:00 (x = 60). The cursor 7px right is at 23:11:10.
  const vertices = cps([
    { rev: 1, t: iso(0), p: 0.41 },
    { rev: 2, t: iso(10 * MIN), p: 0.6349 },
  ]);

  it("snaps the cursor to x = 60 and labels 4:10 PM (Pacific) with the vertex value", () => {
    const readout = publicationReadout(vertices, 67, xOf);
    expect(readout).not.toBeNull();
    expect(readout!.vertex).toBe(vertices[1]);
    expect(readout!.x).toBe(60);
    expect(readout!.clock).toBe("4:10 PM");
    expect(readout!.vertex.p).toBe(0.6349);
    expect(readout!.vertex.t).toBe(iso(10 * MIN));
  });

  it("the cursor's own minute would label differently — the specimen discriminates", () => {
    const cursorMs = ANCHOR + 67 * 10_000;
    expect(checkpointClockLabel({ tMs: cursorMs })).toBe("4:11 PM");
  });

  it("the clock is minutes only, no verb", () => {
    expect(checkpointClockLabel(vertices[1])).toMatch(/^\d{1,2}:\d{2} (AM|PM)$/);
  });
});

describe("the checkpoint clock is Pacific, whatever the reader's zone (accepted boundary B; root 0043Z)", () => {
  it("the process zone is UTC, so a reader-local label would differ — the arm discriminates", () => {
    expect(format(new Date(ANCHOR + 10 * MIN), "h:mm a")).toBe("11:10 PM");
    expect(checkpointClockLabel({ tMs: ANCHOR + 10 * MIN })).toBe("4:10 PM");
  });

  it("follows Pacific daylight saving: PST in winter", () => {
    expect(checkpointClockLabel({ tMs: Date.UTC(2026, 11, 1, 23, 10) })).toBe("3:10 PM");
  });

  it("no leading zero on the hour", () => {
    expect(checkpointClockLabel({ tMs: Date.UTC(2026, 9, 5, 16, 5) })).toBe("9:05 AM");
  });
});

describe("a legacy pair is judged by its span, not its endpoints (independent vectors)", () => {
  const S = 1000;
  const T0 = Date.UTC(2026, 9, 4, 20, 15, 0);
  const w = { startMs: T0 + 10 * S, endMs: T0 + 50 * S };

  it("rows 0 s and 60 s around a 10–50 s window: each outside, the span between them touches it", () => {
    expect(insideRecordedWindow(T0, w)).toBe(false);
    expect(insideRecordedWindow(T0 + 60 * S, w)).toBe(false);
    expect(spanTouchesRecordedWindow(T0, T0 + 60 * S, w)).toBe(true);
    expect(spanTouchesRecordedWindow(T0 + 60 * S, T0, w)).toBe(true);
  });

  it("spans strictly before or after are untouched; both ends are closed", () => {
    expect(spanTouchesRecordedWindow(T0 - 60 * S, T0, w)).toBe(false);
    expect(spanTouchesRecordedWindow(T0 + 60 * S, T0 + 120 * S, w)).toBe(false);
    expect(spanTouchesRecordedWindow(T0, T0 + 10 * S, w)).toBe(true);
    expect(spanTouchesRecordedWindow(T0 + 50 * S, T0 + 60 * S, w)).toBe(true);
    expect(spanTouchesRecordedWindow(T0 + 50 * S + 1, T0 + 60 * S, w)).toBe(false);
  });

  it("a single instant is [ms, ms]; no window touches nothing", () => {
    expect(spanTouchesRecordedWindow(T0 + 30 * S, T0 + 30 * S, w)).toBe(true);
    expect(spanTouchesRecordedWindow(T0, T0 + 60 * S, null)).toBe(false);
  });
});

describe("a scrub reads the pointer's own instant (independent vectors: rows 0 s / 60 s at x 0 / 100)", () => {
  const S = 1000;
  const T0 = Date.UTC(2026, 9, 4, 20, 15, 0);
  const rowStartMs = [T0, T0 + 60 * S];
  const rowXs = [0, 100];
  const vertices = cps([
    { rev: 1, t: new Date(T0 + 10 * S).toISOString(), p: 0.45 },
    { rev: 2, t: new Date(T0 + 50 * S).toISOString(), p: 0.55 },
  ]);
  const w = recordedWindow(vertices);
  const x = (v: CheckpointVertex) => timeToChartX(v.tMs, rowStartMs, rowXs);

  it("x 50 is 30 s: inside the window, beyond both 8px radii — no checkpoint, the blend is withheld", () => {
    expect(publicationReadoutAt(vertices, 50, x)).toBeNull();
    const cursorMs = chartXToTime(50, rowStartMs, rowXs)!;
    expect(cursorMs).toBe(T0 + 30 * S);
    expect(insideRecordedWindow(cursorMs, w)).toBe(true);
  });

  it("x 2 is 1.2 s: before the window, so the legacy row keeps its reading", () => {
    const cursorMs = chartXToTime(2, rowStartMs, rowXs)!;
    expect(cursorMs).toBe(T0 + 1.2 * S);
    expect(insideRecordedWindow(cursorMs, w)).toBe(false);
    expect(publicationReadoutAt(vertices, 2, x)).toBeNull();
  });

  it("x 20 snaps to the 10 s checkpoint at x 16.67 with its own value and clock", () => {
    const readout = publicationReadout(vertices, 20, x)!;
    expect(readout.x).toBeCloseTo(100 / 6, 10);
    expect(readout.vertex.p).toBe(0.45);
    expect(readout.vertex.tMs).toBe(T0 + 10 * S);
  });

  it("scrubAtPointer: x 50 withholds the blend, x 2 does not, x 20 snaps and never withholds", () => {
    expect(scrubAtPointer(vertices, w, 50, rowStartMs, rowXs)).toEqual({ readout: null, blendWithheld: true });
    expect(scrubAtPointer(vertices, w, 2, rowStartMs, rowXs)).toEqual({ readout: null, blendWithheld: false });
    const snapped = scrubAtPointer(vertices, w, 20, rowStartMs, rowXs);
    expect(snapped.readout?.vertex.rev).toBe(1);
    expect(snapped.blendWithheld).toBe(false);
    // inside the window by time even with no drawable checkpoint at all
    expect(scrubAtPointer([], w, 50, rowStartMs, rowXs).blendWithheld).toBe(true);
    // and no window, nothing withheld
    expect(scrubAtPointer(vertices, null, 50, rowStartMs, rowXs).blendWithheld).toBe(false);
  });

  it("is timeToChartX read backwards, and refuses before the first row or a minute past the last", () => {
    for (const ms of [T0, T0 + 10 * S, T0 + 59 * S, T0 + 60 * S, T0 + 90 * S]) {
      expect(chartXToTime(timeToChartX(ms, rowStartMs, rowXs)!, rowStartMs, rowXs)).toBeCloseTo(ms, 6);
    }
    expect(chartXToTime(-1, rowStartMs, rowXs)).toBeNull();
    expect(chartXToTime(200, rowStartMs, rowXs)).toBeNull();
    expect(chartXToTime(50, rowStartMs, [0, null])).toBeNull();
    expect(chartXToTime(NaN, rowStartMs, rowXs)).toBeNull();
  });
});

describe("(vi) ties go to the greatest rev, and the chosen vertex is returned unchanged", () => {
  it("equal distance either side of the cursor", () => {
    const vertices = cps([
      { rev: 9, t: iso(0), p: 0.3 }, // x = 0
      { rev: 4, t: iso(MIN), p: 0.8 }, // x = 6
    ]);
    // cursor at 3: both 3px away.
    expect(publicationReadoutAt(vertices, 3, xOf)).toBe(vertices[0]);
    expect(publicationReadoutAt([...vertices].reverse(), 3, xOf)).toBe(vertices[0]);
  });

  it("two checkpoints at the same t", () => {
    const vertices = cps([
      { rev: 11, t: iso(MIN), p: 0.52 },
      { rev: 12, t: iso(MIN), p: 0.57 },
      { rev: 10, t: iso(MIN), p: 0.49 },
    ]);
    for (const order of [vertices, [...vertices].reverse()]) {
      const chosen = publicationReadoutAt(order, 6, xOf);
      expect(chosen).toBe(vertices[1]);
      expect(chosen).toEqual({ rev: 12, t: iso(MIN), p: 0.57, tMs: ANCHOR + MIN });
    }
  });

  it("nearer beats greater rev", () => {
    const vertices = cps([
      { rev: 1, t: iso(0), p: 0.3 }, // x = 0
      { rev: 99, t: iso(MIN), p: 0.8 }, // x = 6
    ]);
    expect(publicationReadoutAt(vertices, 2, xOf)).toBe(vertices[0]);
  });

  it("latestCheckpoint: greatest t, equal t by greatest rev, in any order", () => {
    const vertices = cps([
      { rev: 5, t: iso(3 * MIN), p: 0.6 },
      { rev: 6, t: iso(3 * MIN), p: 0.61 },
      { rev: 7, t: iso(2 * MIN), p: 0.62 },
    ]);
    expect(latestCheckpoint(vertices)).toBe(vertices[1]);
    expect(latestCheckpoint([...vertices].reverse())).toBe(vertices[1]);
    expect(latestCheckpoint([])).toBeNull();
  });
});

describe("timeToChartX: an instant on the minute-category axis", () => {
  const rows = [0, 1, 2, 3].map((m) => ANCHOR + m * MIN);
  const xs = [10, 20, 30, 40];

  it("a minute's start sits on its row; inside a minute it is linear to the next row", () => {
    expect(timeToChartX(ANCHOR + MIN, rows, xs)).toBe(20);
    expect(timeToChartX(ANCHOR + MIN + 30_000, rows, xs)).toBe(25);
  });

  it("inside the last minute it extends at the last spacing; a minute past it, nothing", () => {
    expect(timeToChartX(ANCHOR + 3 * MIN + 30_000, rows, xs)).toBe(45);
    expect(timeToChartX(ANCHOR + 4 * MIN, rows, xs)).toBeNull();
  });

  it("before the first row, or beside an unplaced row, nothing", () => {
    expect(timeToChartX(ANCHOR - 1, rows, xs)).toBeNull();
    expect(timeToChartX(ANCHOR + 30_000, rows, [10, null, 30, 40])).toBeNull();
    expect(timeToChartX(ANCHOR, [], [])).toBeNull();
  });

  it("rowIndexAt is the last row at or before the instant", () => {
    expect(rowIndexAt(ANCHOR + 2 * MIN + 59_999, rows)).toBe(2);
    expect(rowIndexAt(ANCHOR - 1, rows)).toBeNull();
  });
});

describe("OddsChart is wired to the pointer's instant (static markup cannot move a cursor)", () => {
  const source = readFileSync(join(process.cwd(), "components/OddsChart.tsx"), "utf8");

  it("the hover handler asks scrubAtPointer, and a withheld blend hands the hero nothing", () => {
    expect(source).toMatch(/scrubAtPointer\(drawableCheckpoints, checkpointWindow, state\.chartX!, rowStartMs, rowXs\)/);
    expect(source).toMatch(/const delta = blendWithheld \? null : \(pt\[primarySeriesKey\] as number \| null\);/);
    expect(source).toMatch(/setBlendWithheldAtCursor\(blendWithheld\);/);
  });

  it("the tooltip gives the blend no number while it is withheld", () => {
    expect(source).toMatch(/!blendWithheldAtCursor && typeof legacyBlendAtRow === "number"/);
  });
});
