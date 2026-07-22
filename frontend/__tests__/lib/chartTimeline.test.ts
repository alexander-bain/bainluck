// Guard for the shared event-chart time skeleton (L2-151). OddsChart and
// ScoreDifferentialChart consume these primitives to keep their categorical
// x-axes pixel-identical; a drift here silently de-aligns the two charts.

import { toMinuteKey, makeEnsurePoint, fillMinuteGaps, MinuteKeyed } from "../../lib/chartTimeline";

describe("toMinuteKey", () => {
  test("floors seconds and milliseconds to the start of the minute", () => {
    expect(toMinuteKey("2026-07-20T18:04:37.512Z")).toBe("2026-07-20T18:04:00.000Z");
  });

  test("is stable across different sub-minute timestamps in the same minute", () => {
    const a = toMinuteKey("2026-07-20T18:04:01Z");
    const b = toMinuteKey("2026-07-20T18:04:59Z");
    expect(a).toBe(b);
  });
});

interface Pt extends MinuteKeyed {
  value: number | null;
}

describe("makeEnsurePoint", () => {
  test("creates a seeded point on first touch and reuses it after", () => {
    const map = new Map<string, Pt>();
    const ensure = makeEnsurePoint<Pt>(map, () => ({ value: null }));

    const first = ensure("2026-07-20T18:04:30Z");
    expect(first.value).toBeNull();
    expect(first.timestamp).toBe("2026-07-20T18:04:00.000Z");
    expect(map.size).toBe(1);

    first.value = 7;
    // Same minute → same object (mutations persist).
    const again = ensure("2026-07-20T18:04:59Z");
    expect(again).toBe(first);
    expect(again.value).toBe(7);
    expect(map.size).toBe(1);
  });

  test("gives each point a fresh seed object (no shared reference)", () => {
    const map = new Map<string, Pt>();
    const ensure = makeEnsurePoint<Pt>(map, () => ({ value: null }));
    const a = ensure("2026-07-20T18:04:00Z");
    const b = ensure("2026-07-20T18:05:00Z");
    a.value = 1;
    expect(b.value).toBeNull();
  });
});

describe("fillMinuteGaps", () => {
  test("seeds every missing minute in (first, last]", () => {
    const map = new Map<string, Pt>();
    const ensure = makeEnsurePoint<Pt>(map, () => ({ value: null }));
    const first = new Date("2026-07-20T18:00:00Z");
    const last = new Date("2026-07-20T18:05:00Z");
    fillMinuteGaps(first, last, ensure);
    // Minutes :01, :02, :03, :04, :05 seeded (first itself excluded).
    expect(map.size).toBe(5);
    expect(map.has("2026-07-20T18:05:00.000Z")).toBe(true);
    expect(map.has("2026-07-20T18:00:00.000Z")).toBe(false);
  });

  test("is a no-op when the range is empty or inverted", () => {
    const map = new Map<string, Pt>();
    const ensure = makeEnsurePoint<Pt>(map, () => ({ value: null }));
    fillMinuteGaps(new Date("2026-07-20T18:00:00Z"), new Date("2026-07-20T18:00:00Z"), ensure);
    expect(map.size).toBe(0);
    fillMinuteGaps(new Date("2026-07-20T18:05:00Z"), new Date("2026-07-20T18:00:00Z"), ensure);
    expect(map.size).toBe(0);
  });
});
