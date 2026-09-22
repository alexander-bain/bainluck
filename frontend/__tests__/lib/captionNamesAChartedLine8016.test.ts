/**
 * #8016 — A FUTURES CHART CAPTION MAY ONLY NAME A LINE THE CHART DREW.
 *
 * Production `/futures/109257` ("Who will Donald Trump meet in 2026?") drew three
 * lines and named a fourth leg underneath them:
 *
 *     legend:  Andy Burnham · Vladimir Putin · Mohammed bin Salman
 *     caption: "Lionel Messi up 81.0 pts from opening."
 *
 * Messi is `is_winner: true` at 1.00 from 0.19, so +81.0 pts is arithmetically
 * correct. The number was right and the sentence was attached to a chart that
 * could not show it: the caption's subject came from `market.outcomes` (every
 * leg) while the lines came from the chart's seed rule, which drops graded rows
 * from a live non-mutually-exclusive board (#7439).
 *
 * 🔴 THE BUG IS NOT "IT PICKS THE BIGGEST MOVER", though this board cannot show
 * you that. The caption's subject has always been the highest-PROBABILITY row;
 * on 109257 Messi is both the probability leader (1.00) and the largest mover
 * (+81.0), so the specimen is blind to the difference and the issue's own
 * wording ("the largest opening→current move across all legs") reads as correct
 * against it. The discriminator lives inside the drawn set, and is asserted
 * below: Putin moves most of the three lines (−19.5) while Burnham leads them
 * (0.95), and the caption names Burnham. A "biggest mover" fix would print
 * Putin. The fix narrows the EXISTING rule to the charted set, nothing else.
 *
 * The fixture is the real served payload (35 legs, 10 of them with history),
 * banked from production so the arms below are measured against the board that
 * produced the screenshot rather than a hand-built shape.
 */
import {
  CHART_LINES_WHEN_NONE_SELECTED,
  movementExplanation,
  pickCaptionSubject,
  pickChartSeedOutcomes,
  visibleChartOutcomes,
} from "@/lib/futuresDetailDisplay";
import FIXTURE from "../fixtures/futures109257-8016.json";

interface Leg {
  id: number;
  name: string | null;
  probability: number | null;
  opening_probability: number | null;
  probability_change_24h: number | null;
  is_winner: boolean | null;
}

const LEGS = FIXTURE.outcomes as Leg[];
const HISTORY = (FIXTURE.history_outcome_ids as number[]).map((id) => ({
  outcome_id: id,
}));
const BOARD = FIXTURE.name as string;

const MESSI = 206769569;
const BURNHAM = 210874634;
const BIN_SALMAN = 1596003;
const PUTIN = 1596002;
const NEWSOM = 1595999;

/** What the page composes on first paint: seed the chart, keep the ids that have history. */
function seededSelection(): Set<number> {
  const seeds = pickChartSeedOutcomes(
    LEGS,
    FIXTURE.status === "resolved",
    FIXTURE.mutually_exclusive as boolean | null,
  );
  const historyIds = new Set(HISTORY.map((h) => h.outcome_id));
  const withHistory = seeds.map((s) => s.id).filter((id) => historyIds.has(id));
  return new Set(withHistory.length > 0 ? withHistory : seeds.map((s) => s.id));
}

/** The caption the page renders, composed exactly as `page.tsx` composes it. */
function captionFor(selected: Set<number>): string | null {
  const drawn = new Set(
    visibleChartOutcomes(HISTORY, selected).map((o) => o.outcome_id),
  );
  return movementExplanation(pickCaptionSubject(LEGS, drawn), BOARD);
}

/** The rule as it stood before #8016: highest probability across every leg. */
function legacySubject(): Leg | null {
  if (LEGS.length === 0) return null;
  return [...LEGS].sort(
    (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
  )[0];
}

describe("#8016 — the specimen that produced the screenshot", () => {
  it("draws exactly the three legs the production legend named", () => {
    const drawn = visibleChartOutcomes(HISTORY, seededSelection()).map(
      (o) => o.outcome_id,
    );
    expect(new Set(drawn)).toEqual(new Set([BURNHAM, BIN_SALMAN, PUTIN]));
  });

  it("captions the leading DRAWN line, not the settled winner", () => {
    expect(captionFor(seededSelection())).toBe(
      "Andy Burnham up 5.0 pts from opening.",
    );
  });

  it("never names Lionel Messi, who has no line on this chart", () => {
    const caption = captionFor(seededSelection());
    expect(caption).not.toContain("Messi");
  });

  it("the subject is the probability LEADER of the drawn lines, not their biggest mover", () => {
    // The specimen cannot separate the two readings at field level — Messi is
    // both the probability leader and the largest mover. Inside the drawn set
    // they come apart cleanly, and that is what pins the rule.
    const drawnLegs = [BURNHAM, BIN_SALMAN, PUTIN].map(
      (id) => LEGS.find((l) => l.id === id)!,
    );
    const biggestMover = [...drawnLegs].sort(
      (a, b) =>
        Math.abs((b.probability ?? 0) - (b.opening_probability ?? 0)) -
        Math.abs((a.probability ?? 0) - (a.opening_probability ?? 0)),
    )[0];
    const leaderOfDrawn = [...drawnLegs].sort(
      (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
    )[0];

    expect(biggestMover.name).toBe("Vladimir Putin");
    expect(leaderOfDrawn.name).toBe("Andy Burnham");
    expect(captionFor(seededSelection())).toContain("Andy Burnham");
    expect(captionFor(seededSelection())).not.toContain("Putin");
  });

  it("at field level the two readings agree, so neither the issue nor this board can tell them apart", () => {
    // Recorded so a later session does not "correct" the rule on the strength of
    // the issue's wording: the largest mover across ALL legs is Messi too.
    const biggestMover = [...LEGS]
      .filter((o) => o.probability != null && o.opening_probability != null)
      .sort(
        (a, b) =>
          Math.abs((b.probability ?? 0) - (b.opening_probability ?? 0)) -
          Math.abs((a.probability ?? 0) - (a.opening_probability ?? 0)),
      )[0];
    expect(biggestMover.id).toBe(MESSI);
    expect(legacySubject()!.id).toBe(MESSI);
    // Newsom is the largest DECLINE, and is equally undrawn.
    expect(captionFor(seededSelection())).not.toContain("Newsom");
    expect(LEGS.find((l) => l.id === NEWSOM)!.name).toBe("Gavin Newsom");
  });
});

describe("#8016 — the general property, over the real 35-leg field", () => {
  const selections: Array<[string, Set<number>]> = [
    ["seeded (first paint)", seededSelection()],
    ["reader selected the settled winner alone", new Set([MESSI])],
    ["reader selected winner + an open leg", new Set([MESSI, PUTIN])],
    ["reader selected one open leg", new Set([PUTIN])],
    ["reader selected every leg with history", new Set(HISTORY.map((h) => h.outcome_id))],
  ];

  it.each(selections)(
    "%s — the caption's subject is a leg the chart drew",
    (_label, selected) => {
      const drawn = visibleChartOutcomes(HISTORY, selected).map(
        (o) => o.outcome_id,
      );
      const subject = pickCaptionSubject(LEGS, new Set(drawn));
      expect(subject).not.toBeNull();
      expect(drawn).toContain(subject!.id);
    },
  );

  it.each(selections)(
    "%s — every name the caption prints belongs to a drawn leg",
    (_label, selected) => {
      const caption = captionFor(selected);
      if (caption === null) return;
      const drawnNames = new Set(
        visibleChartOutcomes(HISTORY, selected)
          .map((o) => LEGS.find((l) => l.id === o.outcome_id)?.name)
          .filter((n): n is string => typeof n === "string"),
      );
      // Exactly one drawn name is a prefix of the sentence, and it is the subject.
      const named = [...drawnNames].filter((n) => caption.startsWith(n));
      expect(named).toHaveLength(1);
    },
  );

  it("SELECTING THE SETTLED WINNER MAKES THE SENTENCE LEGAL — the rule is about the chart, not about settlement", () => {
    // Messi is drawable; he was simply not drawn. Once the reader puts that line
    // on the chart the +81.0 sentence is honest, and the fix must not suppress
    // it. This is the arm that stops "drop every graded leg" passing as the fix.
    expect(captionFor(new Set([MESSI]))).toBe(
      "Lionel Messi up 81.0 pts from opening.",
    );
  });

  it("a chart drawing nothing gets no sentence rather than one from off-chart", () => {
    expect(pickCaptionSubject(LEGS, new Set<number>())).toBeNull();
    expect(movementExplanation(pickCaptionSubject(LEGS, new Set()), BOARD)).toBeNull();
    // An id with no matching leg is the same emptiness, not a crash.
    expect(pickCaptionSubject(LEGS, new Set([-1]))).toBeNull();
  });

  it("picks by probability, not by list order", () => {
    const drawn = new Set([PUTIN, BURNHAM, BIN_SALMAN]);
    const shuffled = [...LEGS].sort((a, b) => a.id - b.id);
    expect(pickCaptionSubject(shuffled, drawn)?.id).toBe(BURNHAM);
    expect(pickCaptionSubject([...shuffled].reverse(), drawn)?.id).toBe(BURNHAM);
  });
});

describe("#8016 — visibleChartOutcomes is the chart's own rule, unchanged", () => {
  it("an empty selection draws the first N, not the whole field", () => {
    expect(visibleChartOutcomes(HISTORY, new Set())).toHaveLength(
      Math.min(CHART_LINES_WHEN_NONE_SELECTED, HISTORY.length),
    );
    expect(visibleChartOutcomes(HISTORY, null)).toEqual(
      HISTORY.slice(0, CHART_LINES_WHEN_NONE_SELECTED),
    );
    expect(visibleChartOutcomes(HISTORY, undefined)).toEqual(
      HISTORY.slice(0, CHART_LINES_WHEN_NONE_SELECTED),
    );
  });

  it("a non-empty selection filters, and ignores ids with no history row", () => {
    expect(
      visibleChartOutcomes(HISTORY, new Set([PUTIN, 999999])).map(
        (o) => o.outcome_id,
      ),
    ).toEqual([PUTIN]);
  });
});

describe("#8016 — REACH: the ordinary board is untouched", () => {
  it("when the field leader is drawn, the caption is the one the old rule gave", () => {
    // Burnham leads the drawn set AND would lead a field with the graded rows
    // removed — the ordinary case. Same sentence before and after.
    const openLegs = LEGS.filter((o) => o.is_winner !== true);
    const openLeader = [...openLegs].sort(
      (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
    )[0];
    expect(openLeader.id).toBe(BURNHAM);
    expect(movementExplanation(openLeader, BOARD)).toBe(captionFor(seededSelection()));
  });
});

/**
 * 🔴 THE CONTROL. Everything above is a property suite over a snapshot, and a
 * property suite over a snapshot is worth very little on its own: if the
 * population drifts to contain no settled-and-undrawn leg, every arm stays green
 * while protecting nothing.
 *
 * So this arm asserts the DEFECT is still reachable in the fixture — the rejected
 * rule must still produce the wrong sentence on it. If this goes green, the
 * specimen has gone inert and the suite above is decoration; re-bank a board that
 * reproduces it rather than deleting this.
 */
describe("#8016 — control: the rejected rule still fails on this population", () => {
  it("the pre-#8016 subject is a leg the chart does not draw", () => {
    const drawn = new Set(
      visibleChartOutcomes(HISTORY, seededSelection()).map((o) => o.outcome_id),
    );
    const legacy = legacySubject();
    expect(legacy).not.toBeNull();
    expect(drawn.has(legacy!.id)).toBe(false);
  });

  it("the pre-#8016 caption is the sentence Alex would have seen", () => {
    expect(movementExplanation(legacySubject(), BOARD)).toBe(
      "Lionel Messi up 81.0 pts from opening.",
    );
  });
});
