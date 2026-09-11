/**
 * #4959 — iOS player props printed no verdict on a finished game.
 *
 * `bainluck://events/15308638`, Rangers 3 – Mariners 4, four minutes after the game
 * went final: every prop rung read a forward-looking "chance of hitting" with no ✓,
 * no –, and no value — directly below a totals ladder that graded itself correctly
 * and above an "Additional Markets" card that said "settled".
 *
 * The endpoint had already answered. `_grade_settled_prop` (`backend/app/routes/
 * events.py`) joins the ESPN box score at serve time and ships `actual`/`hit` on
 * every player prop of a finished event. `GameMarketPlayerProp` did not declare
 * either field, so both were dropped at decode, and the card re-derived the grade
 * from `box_score_data` keyed on the FULL market name ("Cole Young: Total Bases
 * O/U 2.5") against an alias table of five basketball stats — which no baseball
 * stat can ever hit.
 *
 * MEASURED on the served payload of 14 finished MLB games, 2026-09-10:
 *
 *     app renders 928 rungs · server had graded 481 (52%) · app drew 0
 *
 * ═══ WHY THIS FILE EXISTS AND NOT ONLY THE XCTESTS ═══
 *
 * CI COMPILES NO SWIFT. `PlayerPropVerdictTests` proves `rungVerdict` resolves the
 * grade correctly and runs on a laptop. It structurally cannot prove the VIEW asks
 * it, or that the MODEL still decodes the pair it needs — and deleting either
 * `let actual`/`let hit` from the struct leaves every Swift test in the repo green
 * while restoring the exact bug, because the pure function still passes and nothing
 * reaches it with real data. Same trap as `eventStatusSingleSource.test.ts` and
 * `propsCardDealsAStableOrder4857.test.ts`, on a third surface.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That every rung now grades. The server grades what the box score can answer: on
 * the specimen above, 31 of the 57 rungs the app renders. The rest draw no mark,
 * which is the correct fail-closed outcome, not a regression.
 *
 * It also does not assert anything about `GameMarketOutcome`. The issue suggested
 * adding the pair there too; measurement refuted it — `hit`/`actual` are absent
 * keys on all 118 `totals`/`team_totals`/`spreads`/`period_markets`/`other` rows of
 * the specimen, because all four `_grade_settled_prop` call sites feed
 * `player_props` alone. Declaring them there would decode a field that never
 * travels. If the server ever grades those sections, that is a new ship.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CARD = join(IOS_ROOT, "Components/PlayerPropsCardView.swift");
const MODELS = join(IOS_ROOT, "Models/FuturesModels.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass — the failure mode a source
// scan is most prone to, and the reason these are constants and not an inline join.
const present = [CARD, MODELS].every(existsSync);
const d = present ? describe : describe.skip;

d("#4959 — a finished game's props print the verdict the server computed", () => {
  const card = () => stripComments(readFileSync(CARD, "utf8"));
  const models = () => stripComments(readFileSync(MODELS, "utf8"));

  describe("the model decodes the grade — where it was actually lost", () => {
    const playerProp = () => {
      const m = models().match(/struct GameMarketPlayerProp[\s\S]*?\n\}/);
      expect(m).not.toBeNull();
      return m![0];
    };

    it("GameMarketPlayerProp declares both served fields", () => {
      expect(playerProp()).toMatch(/let actual: Double\?/);
      expect(playerProp()).toMatch(/let hit: Bool\?/);
    });

    it("both are optional, because live payloads carry neither key", () => {
      // Non-optional would throw on every live and scheduled game — the server
      // returns `{}` from `_grade_settled_prop` for an unfinished event, so the
      // keys are ABSENT rather than null.
      expect(playerProp()).not.toMatch(/let actual: Double(?!\?)/);
      expect(playerProp()).not.toMatch(/let hit: Bool(?!\?)/);
    });
  });

  describe("THE MUTANTS: the view must carry the grade, ask for it, and draw it", () => {
    it("the rung carries the served pair off the prop", () => {
      // Dropping either line compiles once the struct member is removed, and the
      // card silently returns to grading nothing.
      expect(card()).toMatch(/actual: prop\.actual/);
      expect(card()).toMatch(/hit: prop\.hit/);
    });

    it("the row asks rungVerdict, passing the served values", () => {
      expect(card()).toMatch(
        /Self\.rungVerdict\(\s*servedActual: rung\.actual,\s*servedHit: rung\.hit,/,
      );
    });

    it("the ✓/– is keyed on the resolved verdict, not on the box-score lookup", () => {
      // THE ORIGINAL BUG IN ONE LINE. `if isDone, actualValue != nil` gated the
      // mark on the local re-derivation, so a rung the server graded drew nothing
      // whenever the alias table could not reach the stat.
      expect(card()).toMatch(/if isDone, verdict\.hit != nil \{/);
      expect(card()).not.toMatch(/if isDone, actualValue != nil/);
    });

    it("the box-score lookup is a FALLBACK argument, not the grade itself", () => {
      // It must still be called — it is the only source during a LIVE game — but
      // only as `boxActual:`, never as the thing the row branches on.
      expect(card()).toMatch(/boxActual: lookupActualValue\(player: card\.name, stat: statType\)/);
    });
  });

  describe("fail closed: an actual never manufactures a hit", () => {
    it("rungVerdict does not compare the SERVED actual to the threshold", () => {
      // A rung whose orientation we did not receive could be an Under, where the
      // server grades `total < threshold`. Deriving `servedActual >= threshold`
      // would print a confident wrong verdict on every one of them.
      const source = card();
      expect(source).not.toMatch(/servedActual\s*>=\s*threshold/);
      expect(source).not.toMatch(/servedActual\s*<\s*threshold/);
    });

    it("the served hit is returned as-is, not recomputed", () => {
      expect(card()).toMatch(/if let servedHit \{\s*return RungVerdict\(actual: actual, hit: servedHit\)/);
    });
  });

  describe("the caption is left exactly where it was", () => {
    it("the card still asks EventState for it", () => {
      // #4959 is fixed by making the control test's PREMISE true — the card now
      // draws the actual and a ✓/– — not by widening `propsChanceCaption`, whose
      // `completed → "chance of hitting"` case `SuspendedProjectionTests` pins on
      // purpose. A bespoke caption string appearing here would be that same
      // shortcut taken locally.
      expect(card()).toMatch(/EventState\.propsChanceCaption\(/);
      expect(card()).not.toMatch(/"chance of hitting"/);
      expect(card()).not.toMatch(/"final"|"settled"/i);
    });
  });

  describe("the final value is stated once per group, like the totals ladder", () => {
    it("the group derives it from its rungs rather than the row repeating it", () => {
      expect(card()).toMatch(/var finalValue: Double\? \{ rungs\.compactMap\(\\\.actual\)\.first \}/);
    });

    it("it is drawn only on a finished game, and only when known", () => {
      expect(card()).toMatch(/if isDone, let final = group\.finalValue \{/);
    });
  });
});
