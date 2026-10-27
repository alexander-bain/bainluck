import { readFileSync } from "fs";
import { join } from "path";

// Wiring guards only. Actual Swift result/selection/share cases are in
// FuturesDetailHeroResult11616Tests.swift and require Native runtime execution.
const source = readFileSync(join(process.cwd(), "../ios/Bain Luck/Bain Luck/Views/FuturesDetailView.swift"), "utf8");
const selection = source.split("nonisolated func futuresDetailHeroOutcome")[1].split("/// The share sentence")[0];
const share = source.split("func futuresDetailShareMessage")[1].split("// MARK: - View")[0];
const hero = source.split("private func heroSection")[1].split("private func heroBackground")[0];

test("hero selection admits an explicit lead result and a supported winner through the shared row rule", () => {
  // Native 0d239c9d (N1/N2) routes every candidate through one `value` closure
  // over the shared row rule instead of calling it inline per candidate.
  expect(selection).toContain(
    "FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source)",
  );
  expect(selection).toContain("value(lead) != .none");
  expect(selection).toContain("value($0) == .verdict(.won)");
  expect(selection).not.toMatch(/\.isWinner == true|heroWearsWinnerBadge/);
  expect(selection.indexOf("market.leadOutcomeId")).toBeLessThan(selection.indexOf("let winner"));
  // N2: a resolved board with no supported winner never heads with a loser.
  expect(selection).toContain("value($0) != .verdict(.lost)");
});
test("hero value uses the shared decision and only the price branch prints movement", () => {
  expect(hero).toContain("FuturesDetailRowValue.of($0,");
  expect(hero).toContain("switch heroValue");
  expect(hero).toContain("case .verdict(let verdict):");
  expect(hero).toContain("Text(verdict.label)");
  expect(hero).not.toContain("heroWearsWinnerBadge");
  const price = hero.split("case .price(let prob):")[1]?.split("case .none:")[0];
  expect(price).toContain("detailMovementBadge(leader.probabilityChange24h)");
  expect(hero.match(/detailMovementBadge\(/g)).toHaveLength(1);
});
test("sharing preserves verified-mode omission and switches on the shared result before quoting a probability", () => {
  expect(share).toContain("VerifiedTitlePresentation.shareOmitsQuote(market)");
  expect(share).toContain("switch FuturesDetailRowValue.of(leader,");
  expect(share).toContain("case .verdict(let verdict):");
  expect(share).toContain("\\(verdict.label)");
  expect(share).toContain("case .resultUnknown, .none:");
  expect(share).not.toContain("let prob = leader.probability");
});
