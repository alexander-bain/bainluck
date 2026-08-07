import { leaderFirst, leaderFirstSlice } from "@/lib/discover/leaderOrder";

/**
 * UX-P007 / #1526. Behaviour of the leader-first truncation helper.
 *
 * NOTE: jest is not a CI gate in this repo — the deploy-blocking wiring guard
 * lives in `frontend/e2e/contract/leaderFirst.contract.test.js`. This file
 * covers the ordering semantics that file reads as text.
 */
describe("leaderFirstSlice (#1526)", () => {
  // The production specimen: market 20570794, "Fed Decision in September?".
  // The backend array is NOT leader-first, and slice(0, 4) dropped the answer.
  const FED_SEPTEMBER = [
    { label: "25 bps increase", probability: 0.385 },
    { label: "25 bps decrease", probability: 0.06 },
    { label: "50+ bps decrease", probability: 0.01 },
    { label: "50+ bps increase", probability: 0.01 },
    { label: "No change", probability: 0.56 },
  ];

  it("keeps the leader that the old unsorted slice dropped", () => {
    const shown = leaderFirstSlice(FED_SEPTEMBER, 4);
    expect(shown[0].label).toBe("No change");
    expect(shown.map((r) => r.label)).toContain("No change");
  });

  it("no longer renders a card that sums to 47%", () => {
    const before = FED_SEPTEMBER.slice(0, 4);
    const after = leaderFirstSlice(FED_SEPTEMBER, 4);
    const sum = (rows: typeof FED_SEPTEMBER) =>
      rows.reduce((t, r) => t + (r.probability ?? 0), 0);
    expect(Math.round(sum(before) * 100)).toBe(47); // the bug, as rendered
    expect(Math.round(sum(after) * 100)).toBe(102); // leader restored
  });

  it("still truncates the tail (gotcha #43: assert BOTH directions)", () => {
    expect(leaderFirstSlice(FED_SEPTEMBER, 4)).toHaveLength(4);
    const shown = leaderFirstSlice(FED_SEPTEMBER, 4).map((r) => r.label);
    expect(shown).not.toContain("50+ bps increase");
  });

  it("always contains the maximum-probability row", () => {
    for (let count = 1; count <= FED_SEPTEMBER.length; count++) {
      const shown = leaderFirstSlice(FED_SEPTEMBER, count);
      expect(shown[0].probability).toBe(0.56);
    }
  });

  it("is stable — equal probabilities keep the backend's order", () => {
    const tied = [
      { label: "b", probability: 0.5 },
      { label: "a", probability: 0.5 },
      { label: "c", probability: 0.9 },
    ];
    expect(leaderFirst(tied).map((r) => r.label)).toEqual(["c", "b", "a"]);
  });

  it("sorts unpriced rows last, never as the leader", () => {
    const rows = [
      { label: "unpriced", probability: null },
      { label: "zero", probability: 0 },
      { label: "real", probability: 0.2 },
    ];
    expect(leaderFirst(rows).map((r) => r.label)).toEqual(["real", "zero", "unpriced"]);
  });

  it("does not mutate its input", () => {
    const rows = [{ label: "a", probability: 0.1 }, { label: "b", probability: 0.9 }];
    const snapshot = rows.map((r) => r.label);
    leaderFirstSlice(rows, 2);
    expect(rows.map((r) => r.label)).toEqual(snapshot);
  });

  it("handles empty and short lists", () => {
    expect(leaderFirstSlice([], 4)).toEqual([]);
    expect(leaderFirstSlice([{ probability: 0.3 }], 4)).toHaveLength(1);
  });
});
