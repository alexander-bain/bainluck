// L2-135: golf round-boundary chart markers (R1..R5, UTC-midnight day steps).

import { golfRoundMarkers } from "../../lib/golfRounds";

describe("golfRoundMarkers", () => {
  // The Open 2026: Thu Jul 16 → Sun Jul 19. "now" fixed to Sunday so all four
  // rounds are reached.
  const start = "2026-07-16T00:00:00+00:00";
  const end = "2026-07-19T00:00:00+00:00";
  const now = Date.parse("2026-07-19T18:00:00+00:00");

  test("emits one R-marker per tournament day", () => {
    const markers = golfRoundMarkers(start, end, now);
    expect(markers.map((m) => m.label)).toEqual(["R1", "R2", "R3", "R4"]);
  });

  test("markers land on UTC midnight of each day", () => {
    const markers = golfRoundMarkers(start, end, now);
    const r1 = new Date(markers[0].time);
    expect(r1.getUTCHours()).toBe(0);
    expect(r1.getUTCDate()).toBe(16);
    // Consecutive markers are exactly one day apart.
    expect(markers[1].time - markers[0].time).toBe(86_400_000);
  });

  test("never runs past 'now' — a live R1 shows only rounds reached", () => {
    const midR1 = Date.parse("2026-07-16T14:00:00+00:00");
    const markers = golfRoundMarkers(start, end, midR1);
    expect(markers.map((m) => m.label)).toEqual(["R1"]);
  });

  test("caps at R5 for a long (Monday-finish) event", () => {
    const longEnd = "2026-07-27T00:00:00+00:00";
    const laterNow = Date.parse("2026-07-27T00:00:00+00:00");
    const markers = golfRoundMarkers(start, longEnd, laterNow);
    expect(markers.length).toBeLessThanOrEqual(5);
    expect(markers[markers.length - 1].label).toBe("R5");
  });

  test("honest-empty on missing or invalid start date", () => {
    expect(golfRoundMarkers(null, end, now)).toEqual([]);
    expect(golfRoundMarkers(undefined, end, now)).toEqual([]);
    expect(golfRoundMarkers("not-a-date", end, now)).toEqual([]);
  });
});
