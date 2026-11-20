/**
 * #10873 (Nov 9) — "Get Probability" on a game answers for both teams at once,
 * so Siri has nothing more to ask once a game is picked.
 *
 * On Alex's phone (1.0.6 TestFlight) Siri stopped on "Running your shortcut"
 * right where the action used to ask "Which team?". The simulator cannot run
 * Siri by voice, so the second question was removed rather than reproduced:
 * a game now answers with both teams' chances (`gameBothSides`), and only a
 * market with several outcomes still asks which one.
 *
 * What this pins, in CI: the game branch of `GetProbabilityIntent10873` asks
 * nothing and answers both teams; the market branch still asks. The answer's
 * own rules (each figure equals its one-team answer, results, draw-priced
 * matches) are XCTest's (`GetProbabilityBothTeams10873Tests`).
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

const INTENTS = join(__dirname, "../../../ios/Bain Luck/Bain Luck/Intents/BainLuckIntents10873.swift");

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
}

/** The text between `from` and `to`, both searched after `after`. */
function between(source: string, after: string, from: string, to: string): string {
  const anchor = source.indexOf(after);
  const start = anchor < 0 ? -1 : source.indexOf(from, anchor);
  const end = start < 0 ? -1 : source.indexOf(to, start + from.length);
  return start < 0 || end < 0 ? "" : source.slice(start + from.length, end);
}

const d = existsSync(INTENTS) ? describe : describe.skip;

d("Get Probability on a game asks nothing more (#10873)", () => {
  const source = stripComments(readFileSync(INTENTS, "utf8"));
  const game = between(source, "struct GetProbabilityIntent10873", "case .game:", "case .market:");
  const market = between(source, "struct GetProbabilityIntent10873", "case .market:", "private func choose");

  it("finds both branches of the answer", () => {
    expect(game).not.toBe("");
    expect(market).not.toBe("");
  });

  it("answers a game for both teams without a second question", () => {
    for (const asking of ["choose(", "requestDisambiguation", "requestValue", "needsValueError", "Which team"]) {
      expect(game).not.toContain(asking);
    }
    expect(game).toContain("gameBothSides(");
  });

  it("still asks which outcome on a market with several", () => {
    expect(market).toContain('dialog: "Which outcome?"');
  });
});
