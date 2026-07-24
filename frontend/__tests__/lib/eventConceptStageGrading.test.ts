// L2-175 Item 2b: pure grading + labelling helpers for Tour de France stage cards.
// A settled stage must render GRADED (winner + "Won"), never two riders at 90%+
// stale independent-binary prices; an upcoming stage gets an honest label, not an
// empty card. These guard both the authoritative path (#249's graded_winner / won
// emit) AND the impossible-live fallback that fires before that pass ships.

import { stageGradedWinner, stagePendingLabel } from "@/lib/eventConceptDisplay";
import type { EventConceptChild } from "@/lib/types";

const child = (over: Partial<EventConceptChild>): EventConceptChild =>
  ({ market_name: "Tour de France: Stage 6 Winner", kind: "prop", prop_type: "stage", ...over }) as EventConceptChild;

describe("stageGradedWinner", () => {
  test("authoritative graded_winner wins", () => {
    expect(
      stageGradedWinner(child({ graded_winner: "Tadej Pogacar", outcomes: [{ name: "x", probability: 0.5 }] })),
    ).toEqual({ name: "Tadej Pogacar" });
  });

  test("a settled outcome flagged won wins", () => {
    expect(
      stageGradedWinner(
        child({
          settled: true,
          outcomes: [
            { name: "Ben Healy", probability: 0.3, won: true },
            { name: "Tadej Pogacar", probability: 0.6 },
          ],
        }),
      ),
    ).toEqual({ name: "Ben Healy" });
  });

  test("settled child with no won flag → the top outcome", () => {
    expect(
      stageGradedWinner(
        child({ settled: true, outcomes: [{ name: "Mads Pedersen", probability: 0.99 }, { name: "Sean Quinn", probability: 0.2 }] }),
      ),
    ).toEqual({ name: "Mads Pedersen" });
  });

  test("impossible-live tell: TWO riders at 90%+ → stale/settled, top is the winner", () => {
    // The exact production shape: a finished stage whose runner-up was never marked
    // down (Kalshi settled markets stay status=open, gotcha #33).
    expect(
      stageGradedWinner(
        child({ outcomes: [{ name: "Jonas Vingegaard", probability: 0.99 }, { name: "Kevin Vauquelin", probability: 0.94 }] }),
      ),
    ).toEqual({ name: "Jonas Vingegaard" });
  });

  test("a genuine live favorite is NOT crowned (one leader, no second extreme)", () => {
    expect(
      stageGradedWinner(
        child({ outcomes: [{ name: "Tadej Pogacar", probability: 0.627 }, { name: "Ben O Connor", probability: 0.12 }] }),
      ),
    ).toBeNull();
  });

  test("a lone near-certain leader without a settled flag stays undecided (no false crown)", () => {
    expect(
      stageGradedWinner(
        child({ outcomes: [{ name: "Olav Kooij", probability: 0.99 }, { name: "Tim Merlier", probability: 0.16 }] }),
      ),
    ).toBeNull();
  });

  test("no outcomes → null (upcoming)", () => {
    expect(stageGradedWinner(child({ outcomes: [] }))).toBeNull();
  });
});

describe("stagePendingLabel", () => {
  test("stage number + weekday when commence_time is present", () => {
    const iso = "2026-08-15T11:00:00+00:00";
    const weekday = new Date(Date.parse(iso)).toLocaleDateString("en-US", { weekday: "long" });
    expect(
      stagePendingLabel(child({ market_name: "Tour de France: Stage 20 Winner", commence_time: iso })),
    ).toBe(`Stage 20 · ${weekday}`);
  });

  test("bare stage label when no commence_time", () => {
    expect(
      stagePendingLabel(child({ market_name: "Tour de France: Stage 20 Winner", commence_time: null })),
    ).toBe("Stage 20");
  });

  test("falls back to the market name when no stage token", () => {
    expect(
      stagePendingLabel(child({ market_name: "Tour de France: Green Jersey Winner", commence_time: null })),
    ).toBe("Tour de France: Green Jersey Winner");
  });
});
