// lane1-Q479 — the predicate contract for TOP-PRODUCT-DEFECTS item 13.
//
// The page-level proof lives in
// `__tests__/components/futuresDetailIndependentOutcomesQ479.test.tsx`; this file
// pins the rule itself, and in particular the ASYMMETRY that makes it safe:
// `futures_markets.mutually_exclusive` has ORM `default=True`, so `true` is what
// an unwritten row says and `false` is what a source had to write.

import {
  INDEPENDENT_OUTCOMES_NOTE_OPEN,
  INDEPENDENT_OUTCOMES_NOTE_SETTLED,
  MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE,
  independentOutcomesNote,
  outcomesArePricedIndependently,
} from "@/lib/outcomeExclusivity";

describe("only a POSITIVE denial counts as evidence", () => {
  test("false — the source overwrote the default, so we have a fact", () => {
    expect(outcomesArePricedIndependently(false, 8, "kalshi")).toBe(true);
  });

  test("true is NOT evidence — it is the column default", () => {
    // This is the whole reason the predicate is `=== false` and not `!== true`.
    // precompute_calibration.py's Rung 4 (Queue 299) stopped accepting the same
    // flag as proof of a partition for the same reason; nothing here reinstates
    // it in the other direction either.
    expect(outcomesArePricedIndependently(true, 8, "kalshi")).toBe(false);
  });

  test("absent is silence, not the opposite claim", () => {
    expect(outcomesArePricedIndependently(undefined, 8, "kalshi")).toBe(false);
    expect(outcomesArePricedIndependently(null, 8, "kalshi")).toBe(false);
  });

  test("a truthy/falsy near-miss does not slip through", () => {
    // Guards against a future refactor to `!mutuallyExclusive`, which would
    // print the note on every payload that simply omits the field.
    expect(outcomesArePricedIndependently(0 as unknown as boolean, 8, "kalshi")).toBe(false);
    expect(outcomesArePricedIndependently("" as unknown as boolean, 8, "kalshi")).toBe(false);
  });
});

describe("the outcome-count floor", () => {
  test("a two-sided market is a duel whatever the flag says", () => {
    expect(outcomesArePricedIndependently(false, 2, "kalshi")).toBe(false);
    expect(outcomesArePricedIndependently(false, 1, "kalshi")).toBe(false);
    expect(outcomesArePricedIndependently(false, 0, "kalshi")).toBe(false);
  });

  test("the floor is exactly three, inclusive", () => {
    expect(MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE).toBe(3);
    expect(outcomesArePricedIndependently(false, 3, "kalshi")).toBe(true);
  });
});

describe("both renderings are enumerated, because the copy changes with state", () => {
  test("an open bundle speaks in the present", () => {
    expect(independentOutcomesNote(false, 8, false, "kalshi")).toBe(
      INDEPENDENT_OUTCOMES_NOTE_OPEN
    );
    expect(INDEPENDENT_OUTCOMES_NOTE_OPEN).toContain("can happen");
  });

  test("a settled bundle speaks in the past", () => {
    expect(independentOutcomesNote(false, 8, true, "kalshi")).toBe(
      INDEPENDENT_OUTCOMES_NOTE_SETTLED
    );
    expect(INDEPENDENT_OUTCOMES_NOTE_SETTLED).toContain("could happen");
    expect(INDEPENDENT_OUTCOMES_NOTE_SETTLED).not.toContain("is priced");
  });

  test("the two are actually different strings", () => {
    // A settled card claiming the present tense is the HISTORY_CLAIM class this
    // board has blocked on repeatedly; a copy-paste that made these identical
    // would sail past both tests above.
    expect(INDEPENDENT_OUTCOMES_NOTE_OPEN).not.toBe(INDEPENDENT_OUTCOMES_NOTE_SETTLED);
  });

  test("no note is null, never an empty string", () => {
    expect(independentOutcomesNote(true, 8, false, "kalshi")).toBeNull();
    expect(independentOutcomesNote(undefined, 8, false, "kalshi")).toBeNull();
    expect(independentOutcomesNote(false, 2, false, "kalshi")).toBeNull();
  });
});

describe("the note never asserts a number it cannot support", () => {
  for (const note of [
    INDEPENDENT_OUTCOMES_NOTE_OPEN,
    INDEPENDENT_OUTCOMES_NOTE_SETTLED,
  ]) {
    test(`"${note.slice(0, 24)}…" states the shape, not a corrected total`, () => {
      // The fix is emphatically not a renormalisation, so the copy must not
      // imply one ("should add up to", "adjusted", "normalised").
      expect(note).toMatch(/don't add up to 100%/);
      expect(note.toLowerCase()).not.toContain("normal");
      expect(note.toLowerCase()).not.toContain("adjust");
      expect(note.toLowerCase()).not.toContain("should add");
    });
  }
});

// ── CERT-609: `false` is only affirmative if the PARSER makes it so ──────────
//
// The first version of this module asserted that `false` "IS evidence — somebody
// had to overwrite the default to get it". True for Kalshi, false for Polymarket,
// and the cert caught it by probing the real parser rather than the helper.
//
// These tests hold BOTH halves: the behaviour, and the source facts the behaviour
// is deduced from. Pinning only the behaviour would leave the reasoning
// unfalsifiable — the day someone repairs Polymarket's parser, or changes
// Kalshi's default, the gate should move and nothing would say so.

import fs from "fs";
import path from "path";

const BACKEND = path.resolve(__dirname, "..", "..", "..", "backend");

describe("only a source whose parser cannot invent `false` is trusted", () => {
  test("polymarket's false is NOT evidence — its parser invents it from an absent key", () => {
    expect(outcomesArePricedIndependently(false, 8, "polymarket")).toBe(false);
    expect(independentOutcomesNote(false, 8, false, "polymarket")).toBeNull();
    expect(independentOutcomesNote(false, 8, true, "polymarket")).toBeNull();
  });

  test("an unknown or missing source is silence, not trust", () => {
    for (const source of [undefined, null, "", "espn", "the-odds-api"]) {
      expect(outcomesArePricedIndependently(false, 8, source)).toBe(false);
    }
  });

  test("kalshi is still trusted, so the ship survives the gate", () => {
    // 109441 — the named specimen — is a Kalshi market. If this ever goes false,
    // the defect this queue exists for is back on the page.
    expect(outcomesArePricedIndependently(false, 8, "kalshi")).toBe(true);
    expect(independentOutcomesNote(false, 8, false, "KALSHI")).toBe(
      INDEPENDENT_OUTCOMES_NOTE_OPEN
    );
  });
});

describe("the parser facts this gate is deduced from", () => {
  // Read as source text on purpose: these two lines ARE the argument. A test that
  // only asserted the gate's behaviour would still pass on the day one of them
  // changes and the gate became wrong in the other direction.

  test("kalshi defaults an ABSENT flag to true, so its false was written", () => {
    const src = fs.readFileSync(path.join(BACKEND, "app/services/kalshi_api.py"), "utf8");
    expect(src).toContain('mutually_exclusive=event_data.get("mutually_exclusive", True)');
  });

  test("polymarket defaults an ABSENT negRisk to FALSE, and stores it straight through", () => {
    const api = fs.readFileSync(path.join(BACKEND, "app/services/polymarket_api.py"), "utf8");
    const task = fs.readFileSync(path.join(BACKEND, "app/tasks/polymarket.py"), "utf8");
    // The invention…
    expect(api).toContain('neg_risk=event_data.get("negRisk", False)');
    // …and the write that carries it into `mutually_exclusive` unexamined.
    expect(task).toContain("mutually_exclusive=event.neg_risk");
  });

  test("if polymarket's parser is ever repaired, this test fails and the gate should widen", () => {
    // Deliberately phrased as a tripwire rather than a claim about today. When
    // `polymarket_api.py` starts defaulting to None/True, delete this test and add
    // "polymarket" to AFFIRMATIVE_EXCLUSIVITY_SOURCES — ~1,970 open field markets
    // become sayable at that moment.
    const api = fs.readFileSync(path.join(BACKEND, "app/services/polymarket_api.py"), "utf8");
    expect(api).not.toContain('neg_risk=event_data.get("negRisk", None)');
  });
});
