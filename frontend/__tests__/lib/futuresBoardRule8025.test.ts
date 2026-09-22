// #8025 — the board rule itself, now that there is one of it.
//
// `lib/discover/futuresBoard.ts` is a faithful extraction of what
// `components/discover/FuturesCard.tsx` computed inline, so the value of this
// file is that each of the bends the extraction carried is asserted separately.
// A bend lost in the move would otherwise only show up as "the Discover card
// changed shape on some market", which is what nobody measures.
//
// The render-level guard is
// `__tests__/components/browseCardDrawsTheSameBoardAsDiscover8025.test.tsx`;
// this one cannot see whether either card calls the module.

import {
  FUTURES_BOARD_ROW_LIMIT,
  futuresBoardRemainderLabel,
  futuresDistributionBoard,
} from "@/lib/discover/futuresBoard";
import type { FeedFuturesData } from "@/lib/types";

type Row = { label: string; probability: number | null; movement?: number | null };

function payload(card: Record<string, unknown> | undefined): FeedFuturesData {
  return { id: 1, name: "market", discover_card: card } as unknown as FeedFuturesData;
}

const rows = (n: number, from = 0.4): Row[] =>
  Array.from({ length: n }, (_, i) => ({
    label: `Row ${i + 1}`,
    probability: Number((from - i * 0.03).toFixed(4)),
  }));

describe("the gate", () => {
  it("is null when the payload carries no discover_card at all", () => {
    expect(futuresDistributionBoard(payload(undefined))).toBeNull();
  });

  it("is null for any other suggested_format", () => {
    expect(
      futuresDistributionBoard(
        payload({
          suggested_format: "threshold_heatmap",
          distribution_outcomes: rows(8),
          remaining_outcome_count: 0,
        }),
      ),
    ).toBeNull();
  });

  it("needs four priced rows", () => {
    const three = payload({
      suggested_format: "outcome_distribution",
      distribution_outcomes: rows(3),
      remaining_outcome_count: 0,
    });
    expect(futuresDistributionBoard(three)).toBeNull();
    const four = payload({
      suggested_format: "outcome_distribution",
      distribution_outcomes: rows(4),
      remaining_outcome_count: 0,
    });
    expect(futuresDistributionBoard(four)?.rows).toHaveLength(4);
  });
});

describe("#1526 — leader-first before slicing", () => {
  it("draws the four highest, not the first four served", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: [
          { label: "also-ran a", probability: 0.05 },
          { label: "also-ran b", probability: 0.04 },
          { label: "also-ran c", probability: 0.03 },
          { label: "also-ran d", probability: 0.02 },
          { label: "the answer", probability: 0.56 },
        ],
        remaining_outcome_count: 0,
      }),
    );
    expect(board?.rows[0].label).toBe("the answer");
    expect(board?.rows).toHaveLength(FUTURES_BOARD_ROW_LIMIT);
  });
});

describe("#6505 — a row we cannot price is not a row", () => {
  it("drops unpriced rows from the board", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: [
          ...rows(4),
          { label: "no book", probability: null },
          { label: "settled zero", probability: 0 },
        ],
        remaining_outcome_count: 0,
      }),
    );
    expect(board?.rows.map((r) => r.label)).not.toContain("no book");
    expect(board?.rows.map((r) => r.label)).not.toContain("settled zero");
  });

  it("bends the four-row bar for a board that HAD four and lost them", () => {
    // Premier Lacrosse: eight rows, two priced. Falling to the hero would delete
    // the only two numbers the card has.
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: [
          { label: "Denver Outlaws", probability: 0.53 },
          { label: "Boston Cannons", probability: 0.47 },
          ...Array.from({ length: 6 }, (_, i) => ({
            label: `unpriced ${i}`,
            probability: null,
          })),
        ],
        remaining_outcome_count: 0,
      }),
    );
    expect(board?.rows.map((r) => r.label)).toEqual(["Denver Outlaws", "Boston Cannons"]);
  });

  it("does NOT bend for a board that never had four rows", () => {
    expect(
      futuresDistributionBoard(
        payload({
          suggested_format: "outcome_distribution",
          distribution_outcomes: rows(2),
          remaining_outcome_count: 0,
        }),
      ),
    ).toBeNull();
  });
});

describe("CERT-2456 / #4610 — a refused ladder is still a field", () => {
  it("draws two rows when the backend refused the ladder treatment", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(3),
        remaining_outcome_count: 0,
        ladder_treatment_refused: true,
      }),
    );
    expect(board?.rows).toHaveLength(3);
  });
});

describe("#6586 — the remainder counts off the unfiltered list", () => {
  it("adds the rows it declined to draw to the served count", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(8),
        remaining_outcome_count: 2,
      }),
    );
    // 2 served + (8 − 4) drawn-but-not-shown = 6.
    expect(board?.remainingCount).toBe(6);
  });

  it("counts an unpriced row as a row the reader is told exists", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: [...rows(4), { label: "no book", probability: null }],
        remaining_outcome_count: 0,
      }),
    );
    // Filtering the total too would make the card claim a smaller field than the
    // market has.
    expect(board?.remainingCount).toBe(1);
  });

  it("says nothing when there is nothing left", () => {
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(4),
        remaining_outcome_count: 0,
      }),
    );
    expect(board?.remainingCount).toBe(0);
    expect(futuresBoardRemainderLabel(board!)).toBeNull();
  });

  it("keeps the payload shape that draws no remainder row today drawing none", () => {
    // The `?? 0`-less addition, kept deliberately (see the module docblock): a
    // payload with no `remaining_outcome_count` yields NaN, and NaN > 0 is false.
    const board = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(8),
      }),
    );
    expect(Number.isNaN(board!.remainingCount)).toBe(true);
    expect(futuresBoardRemainderLabel(board!)).toBeNull();
  });
});

describe("#7844 half two — the exhaustiveness claim", () => {
  const board = (raceFlag: unknown) =>
    futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(8),
        remaining_outcome_count: 2,
        ...(raceFlag === undefined ? {} : { field_is_a_race: raceFlag }),
      }),
    )!;

  it("says 'Field and' on an exclusive board", () => {
    expect(futuresBoardRemainderLabel(board(true))).toBe("Field and 6 more outcomes");
  });

  it("drops it on an explicitly non-exclusive board", () => {
    expect(futuresBoardRemainderLabel(board(false))).toBe("6 more outcomes");
  });

  it("fails to today's rendering when the field is absent", () => {
    expect(board(undefined).fieldIsARace).toBe(true);
    expect(futuresBoardRemainderLabel(board(undefined))).toBe("Field and 6 more outcomes");
  });

  it("singularises a remainder of one", () => {
    const one = futuresDistributionBoard(
      payload({
        suggested_format: "outcome_distribution",
        distribution_outcomes: rows(5),
        remaining_outcome_count: 0,
      }),
    )!;
    expect(futuresBoardRemainderLabel(one)).toBe("Field and 1 more outcome");
  });
});
