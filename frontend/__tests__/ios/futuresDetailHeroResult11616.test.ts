import { readFileSync } from "fs";
import { join } from "path";

// Wiring guards only. Actual Swift result/selection/share cases are in
// FuturesDetailHeroResult11616Tests.swift and require Native runtime execution.
const source = readFileSync(join(process.cwd(), "../ios/Bain Luck/Bain Luck/Views/FuturesDetailView.swift"), "utf8");
const selection = source.split("nonisolated func futuresDetailHeroOutcome")[1].split("/// The share sentence")[0];
const share = source.split("func futuresDetailShareMessage")[1].split("// MARK: - View")[0];
const hero = source.split("private func heroSection")[1].split("private func heroBackground")[0];
const heroValueFn = source.split("nonisolated func futuresDetailHeroValue")[1].split("nonisolated enum FuturesLineOrPropLeg8280")[0];

test("hero selection admits an explicit lead result and a supported winner through the shared row rule", () => {
  // Native 0d239c9d/f35750c9 route every candidate through one `value` closure
  // over the shared row rule instead of calling it inline per candidate.
  expect(selection).toContain(
    "FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source)",
  );
  expect(selection).toContain("let winners = market.outcomes.filter { value($0) == .verdict(.won) }");
  expect(selection).toContain("value(lead) != .none");
  expect(selection).not.toMatch(/\.isWinner == true|heroWearsWinnerBadge/);
  // Open board: lead, then (independent) live leader, then a supported winner.
  expect(selection.indexOf("market.leadOutcomeId")).toBeLessThan(selection.indexOf("return winners.first ??"));
  // R1: a resolved board names a supported winner (side first, #8280), else only
  // a one-row Lost, else nobody — never the price leader of a settled board.
  const resolved = selection.split('if market.status == "resolved" {')[1].split("if let leadId")[0];
  expect(resolved).toContain("FuturesLineOrPropLeg8280.matches($0.name)");
  expect(resolved).toContain("market.outcomes.count == 1");
  expect(resolved).toContain("value(only) == .verdict(.lost)");
  expect(resolved).toContain("return nil");
  expect(resolved).not.toContain("futuresDetailPriceLeader");
});
test("hero value uses the shared decision and only the price branch prints movement", () => {
  // f35750c9: the hero's value is `futuresDetailHeroValue` — the hero row's own
  // decision, else "Result unknown" (no name) only for an all-unknown settled board.
  expect(hero).toContain("let heroValue = futuresDetailHeroValue(market, hero: leader)");
  expect(heroValueFn).toContain("FuturesDetailRowValue.of($0, marketStatus: market.status, marketSource: market.source)");
  expect(heroValueFn).toContain("SettledResultDisplay698.board(market) == .all");
  expect(heroValueFn).toContain(".resultUnknown(lastRecorded: nil)");
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
