/**
 * UX-P276 / #2789 — the rank badge on a `/sports` prop card must be earned.
 *
 * `FuturesCard` renders `rank={index + 1}` and `isLeader={index === 0}` over
 * `outcomes.slice(0, 5)`. Nothing sorted that array, so the badge was a claim
 * the data never made. The backend half (`routes/futures.py`) fixes WHICH five
 * rows ship; this half fixes the order the card renders whatever it is handed,
 * which is the rule `lib/discover/leaderOrder.ts` already states for UX-P007:
 *
 *   "Sorting is done HERE, at the truncation site, rather than trusted from the
 *    payload ... a renderer that silently depends on upstream order has no way
 *    to fail loudly when that order changes."
 *
 * Both halves are load-bearing and they serve different populations. Measured
 * on the live `/sports` payload: five-outcome cards need the BACKEND (0 of 5
 * led correctly, and the true leader was not among the shipped five at all),
 * while two-outcome cards are fixed by THIS half alone (8 of 15 led with the
 * long shot, worst `Yes 2.4%` badged #1 above `No 97.6%`).
 *
 * Every claim is read off the rendered markup, and the label claims are read
 * off the `data-outcome-label` span (#2662) rather than a Tailwind class — the
 * attribute predates this diff, so an absence check can see it on the parent
 * too (ux/1022's lesson #5).
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

function outcome(
  id: number,
  name: string,
  probability: number | null,
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

function market(name: string, outcomes: FuturesOutcome[]): FuturesMarket {
  return {
    id: 59863411,
    name,
    description: null,
    source: "datagolf",
    category: null,
    sport: "golf",
    sport_name: null,
    llm_sport_category: "golf",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: outcomes.length,
    created_at: null,
    updated_at: null,
    status: "open",
    outcomes,
  } as unknown as FuturesMarket;
}

/** The rendered outcome labels, in the order the card put them on screen. */
function renderedLabels(html: string): string[] {
  const found = [...html.matchAll(/data-outcome-label[^>]*>([^<]*)</g)].map(
    (m) => m[1],
  );
  if (found.length === 0) {
    throw new Error(
      "no data-outcome-label spans rendered — the extractor is blind, not the card empty",
    );
  }
  return found;
}

/**
 * The rendered (label, percentage) PAIRS, read off the one element that binds
 * them — the mini bar carries `aria-label={`${displayName} probability`}` and
 * `aria-valuenow={Math.round(prob * 100)}` together.
 *
 * Reading labels and numbers from two separate extractors cannot tell "the rows
 * are in the wrong order" apart from "the rows are in the right order wearing
 * each other's names", and the second is the failure mode a positional
 * `outcomeLabels` lookup actually produces. Bind per row (ux/1032's lesson #1).
 */
function renderedPairs(html: string): [string, number][] {
  const found = [
    ...html.matchAll(
      /role="progressbar"[^>]*aria-valuenow="(\d+)"[^>]*aria-label="([^"]*) probability"/g,
    ),
  ].map(([, value, label]) => [label, Number(value)] as [string, number]);
  if (found.length === 0) {
    throw new Error(
      "no progressbar rows rendered — the pair extractor is blind, not the card empty",
    );
  }
  return found;
}

function render(m: FuturesMarket): string {
  return renderToStaticMarkup(<FuturesCard market={m} />);
}

// The five rows production shipped for the reported card, in production order.
const WINNER_ROWS = [
  outcome(1, "Yannik Paul", 0.000863),
  outcome(2, "Felix Mory", 0.000496),
  outcome(3, "Marco Penge", 0.007235),
  outcome(4, "Todd Clements", 0.038777),
  outcome(5, "Richard Sterne", 0.000174),
];

describe("#2789 — the card ranks the favourite first", () => {
  it("puts the highest-probability outcome in row 1", () => {
    // RED ON MASTER: row 1 is "Yannik Paul" at 0.09%.
    const labels = renderedLabels(
      render(market("Omega European Masters - Winner", WINNER_ROWS)),
    );
    expect(labels[0]).toBe("Todd Clements");
  });

  it("renders every row in descending probability order", () => {
    const labels = renderedLabels(
      render(market("Omega European Masters - Winner", WINNER_ROWS)),
    );
    expect(labels).toEqual([
      "Todd Clements",
      "Marco Penge",
      "Yannik Paul",
      "Felix Mory",
      "Richard Sterne",
    ]);
  });

  it("does not lead a two-outcome card with the long shot", () => {
    // RED ON MASTER, and the commonest shape on /sports: 8 of 15 live tennis
    // cards led with the unlikely side. The leader is deliberately SECOND in
    // the fixture — #2789 warns that a two-outcome guard can be green on the
    // bug, which is true only when the leader happens to arrive first (see the
    // labelled control below).
    const labels = renderedLabels(
      render(
        market("Will Jasmine Paolini advance to the Semifinals?", [
          outcome(10, "Yes", 0.024),
          outcome(11, "No", 0.976),
        ]),
      ),
    );
    expect(labels).toEqual(["No", "Yes"]);
  });

  it("keeps a truncated card's leader when more than five outcomes arrive", () => {
    const labels = renderedLabels(
      render(
        market("Omega European Masters - Winner", [
          ...WINNER_ROWS,
          outcome(6, "Harry Hall", 0.117902),
        ]),
      ),
    );
    expect(labels).toHaveLength(5);
    expect(labels[0]).toBe("Harry Hall");
    expect(labels).not.toContain("Richard Sterne");
  });

  it("never makes an unpriced row the leader", () => {
    const labels = renderedLabels(
      render(
        market("Omega European Masters - Make the Cut", [
          outcome(20, "Oliver Lindell", null),
          outcome(21, "Marco Penge", 0.53008),
        ]),
      ),
    );
    expect(labels).toEqual(["Marco Penge", "Oliver Lindell"]);
  });
});

describe("#2789 — the #2662 label travels with its own outcome", () => {
  // The trap the issue names: `outcomeLabels` is positional over the UNSORTED
  // array, so sorting the rows without re-pairing hands row i's stripped label
  // to a different entrant — a silent misattribution that looks perfectly fine
  // on screen, which is worse than the bug being fixed.
  const PREFIXED = market(
    "US Open WTA: Zeynep Sonmez vs Coco Gauff",
    [
      outcome(30, "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 2 Winner", 0.14),
      outcome(31, "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 O/U 8.5", 0.52),
      outcome(32, "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 Winner", 0.15),
    ],
  );

  it("shows each stripped suffix beside the probability it belongs to", () => {
    // The 52% row must read "Set 1 O/U 8.5". If the labels were still indexed
    // positionally it would read "Set 2 Winner" — the label of whatever used to
    // sit at index 0 — while the number beside it stayed correct.
    expect(renderedLabels(render(PREFIXED))).toEqual([
      "Set 1 O/U 8.5",
      "Set 1 Winner",
      "Set 2 Winner",
    ]);
  });

  it("keeps each label attached to its own probability", () => {
    // The pairing, not the order. This is the arm that separates a genuine fix
    // from the near-miss a reader writes by pointing `leaderFirstSlice` at
    // `outcomes` and leaving `outcomeLabels` indexed over the unsorted array:
    // that mutation renders the rows in the RIGHT order under the WRONG names,
    // so every label-order assertion above is satisfied by the same wrong output
    // the bug produces, and only this one can see the difference.
    expect(renderedPairs(render(PREFIXED))).toEqual([
      ["Set 1 O/U 8.5", 52],
      ["Set 1 Winner", 15],
      ["Set 2 Winner", 14],
    ]);
  });

  it("CONTROL (green on main too): the prefix is still stripped at all", () => {
    // #2662's all-or-nothing predicate must still see the WHOLE shipped set.
    // If reordering had moved the predicate's input, every row would fall back
    // to its full title and this fix would have quietly undone UX-P269.
    const html = render(PREFIXED);
    for (const label of renderedLabels(html)) {
      expect(label).not.toContain("Zeynep Sonmez vs Coco Gauff");
    }
  });
});

describe("#2789 — controls, each verified GREEN on the parent commit", () => {
  it("CONTROL (green on main too): an already-ordered card is unchanged", () => {
    // Three of FuturesCard's four callers already pass a sorted list. The sort
    // is idempotent, so this must be a no-op for them.
    const labels = renderedLabels(
      render(
        market("An already ordered market", [
          outcome(40, "Alpha", 0.6),
          outcome(41, "Bravo", 0.3),
          outcome(42, "Charlie", 0.1),
        ]),
      ),
    );
    expect(labels).toEqual(["Alpha", "Bravo", "Charlie"]);
  });

  it("CONTROL (green on main too): a two-outcome card already led correctly", () => {
    // 7 of 15 live two-outcome cards were right by luck. Kept as a labelled
    // control so the coincidence-correct half is visibly NOT counted as
    // evidence for the fix.
    const labels = renderedLabels(
      render(
        market("Will Ann Li advance to the Quarterfinals?", [
          outcome(50, "No", 0.9695),
          outcome(51, "Yes", 0.0305),
        ]),
      ),
    );
    expect(labels).toEqual(["No", "Yes"]);
  });

  it("CONTROL (green on main too): the card still renders at most five rows", () => {
    const labels = renderedLabels(
      render(
        market(
          "Omega European Masters - Winner",
          Array.from({ length: 12 }, (_, i) =>
            outcome(60 + i, `Golfer ${i}`, i / 100),
          ),
        ),
      ),
    );
    expect(labels).toHaveLength(5);
  });
});
