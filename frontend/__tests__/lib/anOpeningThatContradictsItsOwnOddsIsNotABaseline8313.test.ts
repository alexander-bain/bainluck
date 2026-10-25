/**
 * #8313 — AN OPENING THAT DISAGREES WITH ITSELF IS NOT A BASELINE.
 *
 * Production `/futures/13795456` ("Iran leadership change by December 31?"),
 * shopper pass-0462, 2026-10-17 05:45Z, 390px. The Probability Trend caption read
 *
 *     "No up 57.5 pts from opening."
 *
 * The served No leg (fixture below, the saved `detail.json` byte for byte):
 *
 *     No   probability 0.885   opening_probability 0.31   opening_american_odds -223
 *     Yes  probability 0.115   opening_probability 0.31   opening_american_odds +223
 *
 * −223 is 0.69, the COMPLEMENT of 0.31: the pre-#137 decomposed writer's
 * side-swap (No's opening probability stored from Yes, No's own odds beside it).
 * 0.885 − 0.31 = 57.5 measures from a number this leg never opened at.
 *
 * The odds are NOT always written with the opening (history backfills, empty-book
 * repairs and the pollers' per-column coalesce can leave them stale — lane1b's
 * review R1), so a plain mismatch is not read; only the complement signature is.
 *
 * Three wrong repairs, each asserted absent below:
 *   57.5 — the defect (stored 0.31).
 *   19.5 — 0.885 − 0.69, the odds converted and substituted.
 *    5.0 — 0.885 − 0.835, No's first RETAINED history point (Jul 8, 45 days after
 *          Yes's first). A first retained point is not proof of the opening.
 * None is a verified opening comparison, so the caption makes none.
 *
 * Controls: the Yes leg on the same payload (0.31 / +223, consistent), the
 * same-session `/futures/61318328` (legs opened together, caption "Yes up 5.0
 * pts from opening."), the independent-board production fixtures whose openings
 * do not sum to 1, and stale-odds rows from writers that set the opening alone
 * all still speak.
 */
import {
  movementExplanation,
  pickCaptionSubject,
  type MovementLeader,
} from "@/lib/futuresDetailDisplay";
import SPECIMEN from "../fixtures/futuresDetail13795456-8313.json";
import CONTROL from "../fixtures/futuresDetail61318328-8313.json";
import BOARD_109441 from "../fixtures/uxp230_futures_109441.json";
import BOARD_108559 from "../fixtures/futuresDetail108559Production.json";

interface Leg extends MovementLeader {
  id: number;
}

const legs = (market: { outcomes: unknown[] }) => market.outcomes as Leg[];
const leg = (market: { outcomes: unknown[] }, id: number) => {
  const found = legs(market).find((o) => o.id === id);
  if (!found) throw new Error(`fixture lost outcome ${id}`);
  return found;
};

const NO = 125650217;
const YES = 125650216;

// The reported numbers, in every shape the sentence could take.
const UNSUPPORTED = [/57\.5/, /19\.5/, /\b5\.0\b/, /\bup 5 /];

describe("#8313 the specimen: No's opening is the other side's price", () => {
  test("the fixture is the payload the shopper saved", () => {
    const no = leg(SPECIMEN, NO);
    expect(no.name).toBe("No");
    expect(no.probability).toBe(0.885);
    expect(no.opening_probability).toBe(0.31);
    expect(no.opening_american_odds).toBe(-223);
    expect(no.probability_change_24h).toBeNull();
  });

  test("the page's own subject is No, and its caption says nothing", () => {
    // hist-full.json for this market carries history for both legs (Yes 1,616
    // points from May 24, No 596 from Jul 8), so both are drawn.
    const subject = pickCaptionSubject(legs(SPECIMEN), new Set([YES, NO]));
    expect(subject?.id).toBe(NO);
    expect(movementExplanation(subject, SPECIMEN.name)).toBeNull();
  });

  test("no unsupported opening comparison under any board name", () => {
    for (const name of [SPECIMEN.name, null, undefined]) {
      const s = movementExplanation(leg(SPECIMEN, NO), name) ?? "";
      for (const re of UNSUPPORTED) expect(s).not.toMatch(re);
      expect(s).not.toMatch(/from opening|since opening/);
    }
  });

  test("withheld opening falls through to the existing 24h branch, unchanged", () => {
    const no = { ...leg(SPECIMEN, NO), probability_change_24h: 0.02 };
    expect(movementExplanation(no)).toBe("No up 2.0 pts in the last 24h.");
    // and under 1 point the 24h branch still has nothing to say
    expect(movementExplanation({ ...no, probability_change_24h: 0.004 })).toBeNull();
  });

  test("same leg with its odds removed keeps today's caption (the field is the only signal)", () => {
    const no = leg(SPECIMEN, NO);
    expect(movementExplanation({ ...no, opening_american_odds: null })).toBe(
      "No up 57.5 pts from opening.",
    );
    const { opening_american_odds: _dropped, ...withoutKey } = no;
    expect(movementExplanation(withoutKey)).toBe("No up 57.5 pts from opening.");
  });
});

describe("#8313 controls: a coherent opening still speaks", () => {
  test("the Yes leg of the same payload (0.31 / +223) keeps its caption", () => {
    // Its own move, from its own consistent opening. The two legs' openings sum
    // to 0.62 — not read, and not a reason to withhold.
    expect(movementExplanation(leg(SPECIMEN, YES))).toBe("Yes down 19.5 pts from opening.");
  });

  test("same-session control /futures/61318328 still reads 'Yes up 5.0 pts from opening.'", () => {
    const subject = pickCaptionSubject(legs(CONTROL), new Set(legs(CONTROL).map((o) => o.id)));
    expect(subject?.opening_american_odds).toBe(-270);
    expect(movementExplanation(subject, CONTROL.name)).toBe("Yes up 5.0 pts from opening.");
  });

  test("independent production boards (openings not summing to 1) are untouched", () => {
    const amazon = leg(BOARD_109441, 1597099);
    expect(movementExplanation(amazon)).toBe("Amazon up 13.5 pts from opening.");
    // Every leg of both boards that has an opening keeps exactly the caption the
    // odds-blind version printed.
    for (const board of [BOARD_109441, BOARD_108559]) {
      for (const o of legs(board)) {
        if (o.opening_probability == null) continue;
        expect(movementExplanation(o)).toBe(
          movementExplanation({ ...o, opening_american_odds: null }),
        );
      }
    }
  });
});

describe("#8313 rounding: integer odds are not a contradiction", () => {
  const base = { name: "Field", probability: 0.6 };
  test.each([
    [0.455, 120], // 0.4545
    [0.335, 199], // 0.3344
    [0.545, -120], // 0.5455
    [0.499, 100], // rounds to +100 = 0.5
    [0.5, -100],
    [0.005, 19900],
    [0.995, -19900],
  ])("opening %p with odds %p still speaks", (open, odds) => {
    const s = movementExplanation({ ...base, opening_probability: open, opening_american_odds: odds });
    expect(s).toMatch(/from opening|since opening/);
  });

  test("the tolerance edge: 0.4 pt off the complement is withheld, 0.6 pt off speaks", () => {
    // +150 is exactly 0.40, so the complement edge is an opening near 0.60.
    const leader = { name: "Field", probability: 0.8 };
    expect(
      movementExplanation({ ...leader, opening_probability: 0.596, opening_american_odds: 150 }),
    ).toBeNull();
    expect(
      movementExplanation({ ...leader, opening_probability: 0.594, opening_american_odds: 150 }),
    ).toBe("Field up 20.6 pts from opening.");
  });
});

describe("#8313 stale odds beside an honest opening still speak (lane1b R1)", () => {
  test("case A — an empty-book repair kept the discredited 0.50's odds", () => {
    expect(
      movementExplanation({ name: "Yes", probability: 0.4, opening_probability: 0.12, opening_american_odds: -100 }),
    ).toBe("Yes up 28.0 pts from opening.");
  });

  test("case B — a backfilled opening, odds coalesced later from a 0.45 price", () => {
    expect(
      movementExplanation({ name: "Yes", probability: 0.47, opening_probability: 0.2, opening_american_odds: 122 }),
    ).toBe("Yes up 27.0 pts from opening.");
  });

  test("a mismatch just past rounding that is not the complement speaks", () => {
    // +150 = 0.40; 0.406 is 0.6 pt off it and nowhere near 0.60.
    expect(
      movementExplanation({ name: "Field", probability: 0.6, opening_probability: 0.406, opening_american_odds: 150 }),
    ).toBe("Field up 19.4 pts from opening.");
  });

  test("within 1 pt of 50% the complement is not read (lane1b N1)", () => {
    // -101 = 0.5025: 0.55 pt off 0.497 and 0.05 pt off its complement 0.503.
    expect(
      movementExplanation({ name: "Yes", probability: 0.6, opening_probability: 0.497, opening_american_odds: -101 }),
    ).toBe("Yes up 10.3 pts from opening.");
  });

  test("the specimen's No leg after the #137 flip (0.69 / -223) speaks", () => {
    // The regrade sets the opening to 1 − p and leaves the odds, which then agree.
    expect(
      movementExplanation({ ...leg(SPECIMEN, NO), opening_probability: 0.69 }),
    ).toBe("No up 19.5 pts from opening.");
  });
});

describe("#8313 absent / invalid / zero fields keep today's behaviour", () => {
  const leader = { name: "No", probability: 0.885, opening_probability: 0.31 };
  const today = "No up 57.5 pts from opening.";

  test.each([
    ["undefined", undefined],
    ["null", null],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["zero", 0],
    ["impossible +50", 50],
    ["impossible -99", -99],
  ])("odds %s is not read", (_label, odds) => {
    expect(movementExplanation({ ...leader, opening_american_odds: odds })).toBe(today);
  });

  test("an opening outside (0, 1) is not checked against odds (no writer derives odds there)", () => {
    expect(
      movementExplanation({ name: "No", probability: 0.885, opening_probability: 0, opening_american_odds: -223 }),
    ).toBe("No up 88.5 pts from opening.");
    expect(
      movementExplanation({ name: "No", probability: 0.885, opening_probability: 1, opening_american_odds: -223 }),
    ).toBe("No down 11.5 pts from opening.");
  });

  test("a current price of 0 against a coherent opening still reads as a move", () => {
    expect(
      movementExplanation({ name: "Yes", probability: 0, opening_probability: 0.31, opening_american_odds: 223 }),
    ).toBe("Yes down 31.0 pts from opening.");
  });

  test("missing current price with a contradicted opening: 24h branch only, as before", () => {
    expect(
      movementExplanation({ name: "No", probability: null, opening_probability: 0.31, opening_american_odds: -223 }),
    ).toBeNull();
    expect(
      movementExplanation({
        name: "No",
        probability: null,
        opening_probability: 0.31,
        opening_american_odds: -223,
        probability_change_24h: -0.03,
      }),
    ).toBe("No down 3.0 pts in the last 24h.");
  });
});
