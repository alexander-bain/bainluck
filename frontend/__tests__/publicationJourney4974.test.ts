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
 * no clock reads). TZ is pinned to UTC by jest.config.js.
 */

import {
  CHECKPOINT_HIT_RADIUS_PX,
  checkpointClockLabel,
  eligibleCheckpoints,
  insideRecordedWindow,
  latestCheckpoint,
  publicationReadout,
  publicationReadoutAt,
  recordedWindow,
  rowIndexAt,
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

  it("snaps the cursor to x = 60 and labels 11:10 PM with the vertex value", () => {
    const readout = publicationReadout(vertices, 67, xOf);
    expect(readout).not.toBeNull();
    expect(readout!.vertex).toBe(vertices[1]);
    expect(readout!.x).toBe(60);
    expect(readout!.clock).toBe("11:10 PM");
    expect(readout!.vertex.p).toBe(0.6349);
    expect(readout!.vertex.t).toBe(iso(10 * MIN));
  });

  it("the cursor's own minute would label differently — the specimen discriminates", () => {
    const cursorMs = ANCHOR + 67 * 10_000;
    expect(checkpointClockLabel({ tMs: cursorMs })).toBe("11:11 PM");
  });

  it("the clock is minutes only, no verb", () => {
    expect(checkpointClockLabel(vertices[1])).toMatch(/^\d{1,2}:\d{2} (AM|PM)$/);
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
