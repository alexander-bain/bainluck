// L2-163 Item 2c — the "T9 rendered left of T1" inning-ordering bug.
//
// Root cause (confirmed on the live-MLB exhibit 15165210): an event's
// period_markers stream carried a PRIOR day's innings ("Top 5th" @ 07-21)
// alongside the current game ("Top 4th" @ 07-22). The old first-seen-per-label
// collapse anchored each inning to its earliest (stale) timestamp; in a wide
// "All" window the 12-hour "h:mm a" categorical axis then collided and rendered
// a late inning to the LEFT of an earlier one. keepLatestSession() cuts the
// stale segment so the current game's innings stay monotonic.

import { derivePeriodBoundaries, normalizePeriodLabel } from "../../lib/periodMarkers";

describe("derivePeriodBoundaries — stale prior-game contamination (L2-163)", () => {
  test("discards a prior day's inning markers, keeping the current game monotonic", () => {
    // Yesterday's game (07-21): reached the 5th. Today's live game (07-22/23):
    // Top 1st → Top 4th. Both wrongly share one event's period_markers.
    const periodMarkers = [
      // --- stale 07-21 segment ---
      { timestamp: "2026-07-21T00:22:00Z", period: "Top 4th" },
      { timestamp: "2026-07-21T00:31:00Z", period: "Top 5th" },
      { timestamp: "2026-07-21T00:45:00Z", period: "Bottom 5th" },
      // --- current 07-22/23 game (≥6h later) ---
      { timestamp: "2026-07-22T23:00:00Z", period: "Top 1st" },
      { timestamp: "2026-07-22T23:20:00Z", period: "Top 2nd" },
      { timestamp: "2026-07-22T23:40:00Z", period: "Top 3rd" },
      { timestamp: "2026-07-23T00:00:00Z", period: "Top 4th" },
    ];

    const boundaries = derivePeriodBoundaries(undefined, undefined, undefined, undefined, periodMarkers);

    // Only the current game survives — the 5th (which only existed yesterday) is gone.
    const labels = boundaries.map((b) => b.label);
    expect(labels).toEqual(["T1", "T2", "T3", "T4"]);

    // And every boundary is on the current day, strictly increasing in time.
    for (let i = 1; i < boundaries.length; i++) {
      const prev = new Date(boundaries[i - 1].timestamp).getTime();
      const cur = new Date(boundaries[i].timestamp).getTime();
      expect(cur).toBeGreaterThan(prev);
    }
    // T4 (the current game's 4th) resolves to 07-23, NOT the stale 07-21 "Top 4th".
    const t4 = boundaries.find((b) => b.label === "T4")!;
    expect(t4.timestamp.startsWith("2026-07-23")).toBe(true);
  });

  test("a clean single-game stream (no large gaps) passes through unchanged", () => {
    const periodMarkers = [
      { timestamp: "2026-07-23T00:00:00Z", period: "Top 1st" },
      { timestamp: "2026-07-23T00:20:00Z", period: "Top 2nd" },
      { timestamp: "2026-07-23T00:40:00Z", period: "Top 3rd" },
    ];
    const boundaries = derivePeriodBoundaries(undefined, undefined, undefined, undefined, periodMarkers);
    expect(boundaries.map((b) => b.label)).toEqual(["T1", "T2", "T3"]);
  });

  test("first inning snaps to commence_time (T1/B1 recognized)", () => {
    const periodMarkers = [
      // First marker arrives a few min late (data lag).
      { timestamp: "2026-07-23T00:05:00Z", period: "Top 1st" },
      { timestamp: "2026-07-23T00:25:00Z", period: "Top 2nd" },
    ];
    const commence = "2026-07-23T00:00:00Z";
    const boundaries = derivePeriodBoundaries(undefined, undefined, undefined, commence, periodMarkers);
    const t1 = boundaries.find((b) => b.label === "T1")!;
    expect(t1.timestamp).toBe(commence);
  });
});

describe("normalizePeriodLabel — baseball innings", () => {
  test("Top/Bottom map to T/B + inning number", () => {
    expect(normalizePeriodLabel("Top 3rd")).toBe("T3");
    expect(normalizePeriodLabel("Bottom 5th")).toBe("B5");
    expect(normalizePeriodLabel("Top 9th")).toBe("T9");
  });
  test("Middle innings are dropped (chart clutter)", () => {
    expect(normalizePeriodLabel("Middle 4th")).toBe("");
  });
});
