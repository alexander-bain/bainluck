// L2-161: ambient-history point extraction for the futures Hero C.
import { buildAmbientPoints } from "../../lib/futuresAmbient";
import type { FuturesOutcomeHistory } from "../../lib/types";

function oh(outcome_id: number, probs: (number | null)[]): FuturesOutcomeHistory {
  return {
    outcome_id,
    name: `O${outcome_id}`,
    history: probs.map((probability, i) => ({
      timestamp: `2026-07-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
      probability,
      american_odds: null,
      bookmaker: "blend",
    })),
  };
}

describe("buildAmbientPoints", () => {
  test("returns the hero outcome's probabilities oldest→newest", () => {
    const hist = [oh(1, [0.4, 0.5, 0.68]), oh(2, [0.1, 0.1, 0.1])];
    expect(buildAmbientPoints(hist, 1)).toEqual([0.4, 0.5, 0.68]);
  });

  test("drops null points", () => {
    expect(buildAmbientPoints([oh(1, [0.4, null, 0.6])], 1)).toEqual([0.4, 0.6]);
  });

  test("returns [] for unknown outcome id / empty / nullish", () => {
    expect(buildAmbientPoints([oh(1, [0.4, 0.5])], 99)).toEqual([]);
    expect(buildAmbientPoints([], 1)).toEqual([]);
    expect(buildAmbientPoints(null, 1)).toEqual([]);
    expect(buildAmbientPoints([oh(1, [0.4])], null)).toEqual([]);
  });
});
