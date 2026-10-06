/**
 * #10598 — a finished game in iPhone Search suggestions says who won.
 *
 * Native fix check for #10581, 2026-10-06 07:23Z: typing `brewers` showed
 * "San Diego Padres at Milwaukee Brewers · FINAL · Oct 4, 1:00 PM" with no
 * score, while the web dropdown (`finalScoreText` in
 * `lib/searchSuggestionDisplay.ts`, #9226) and the phone's own submitted
 * results both said 3 - 4. The server already sent `home_score`/`away_score`;
 * `TypeaheadSuggestion` dropped them.
 *
 * WHY THIS FILE, AND NOT ONLY A SWIFT TEST. The rule itself (finished only,
 * both sides, away first; finished rows print the day) lives on the model and
 * is tested by `BainLuckTests/SearchSuggestionFinalScore10598Tests.swift`. But
 * whether the suggestion row DRAWS it is an arm inside a `some View` body:
 * XCTest stays green with that arm deleted, and CI compiles no Swift (#4302).
 * This scan is what kills the dropped-arm mutant on every push.
 */

import { readFileSync } from "fs";
import { join } from "path";
import { swiftCode, swiftCodeKeepingStrings } from "../helpers/swiftSource";

const IOS = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const SEARCH_VIEW = join(IOS, "Views/SearchView.swift");
const SEARCH_MODELS = join(IOS, "Models/SearchModels.swift");

/** The suggestion list's body: from its declaration to the icon builder after it. */
function suggestionList(source: string): string {
  const start = source.indexOf("private var suggestionList: some View");
  const end = source.indexOf("private func suggestionIcon(", start);
  if (start === -1 || end === -1) {
    throw new Error(
      "SearchView.swift no longer has `suggestionList` followed by `suggestionIcon(`. " +
        "Re-aim this file at the suggestion row — do not delete the assertions.",
    );
  }
  return source.slice(start, end);
}

/** One computed property's body on `TypeaheadSuggestion`, brace-matched. */
function property(source: string, name: string): string {
  const struct = source.indexOf("struct TypeaheadSuggestion");
  const start = source.indexOf(`var ${name}:`, struct);
  if (struct === -1 || start === -1) {
    throw new Error(`TypeaheadSuggestion no longer declares \`var ${name}:\`.`);
  }
  const open = source.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unbalanced braces after \`var ${name}:\``);
}

describe("#10598 — iPhone Search suggestions print a finished game's score and day", () => {
  const view = suggestionList(swiftCode(readFileSync(SEARCH_VIEW, "utf8")));
  const models = readFileSync(SEARCH_MODELS, "utf8");

  it("the suggestion row draws the model's final score", () => {
    expect(view).toMatch(/if let score = suggestion\.finalScoreText \{\s*Text\(score\)/);
  });

  it("the suggestion row's time takes the model's style (day only once finished)", () => {
    expect(view).toMatch(/RelativeTimeText\(\s*dateString: commenceTime,\s*style: suggestion\.timeStyle/);
    // The old call, with no style, printed "Oct 4, 1:00 PM" on a final.
    expect(view).not.toMatch(/RelativeTimeText\(dateString: commenceTime\)/);
  });

  it("the model decodes both score keys", () => {
    const code = swiftCode(models);
    expect(code).toMatch(/var homeScore: Int\? = nil/);
    expect(code).toMatch(/var awayScore: Int\? = nil/);
  });

  it("the score is finished-only, both sides, away first", () => {
    const body = property(swiftCodeKeepingStrings(models), "finalScoreText");
    expect(body).toContain("EventState.isFinished(status)");
    expect(body).toMatch(/let away = awayScore, let home = homeScore/);
    expect(body).toContain('"\\(away) - \\(home)"');
  });

  it("a finished row prints the day; every other row keeps the full form", () => {
    const body = property(swiftCode(models), "timeStyle");
    expect(body).toMatch(/EventState\.isFinished\(status\) \? \.dayOnly : \.full/);
  });
});
