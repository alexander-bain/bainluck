import { readFileSync } from "fs";
import { join } from "path";
import { swiftCode } from "../helpers/swiftSource";

const root = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const read = (path: string) => swiftCode(readFileSync(join(root, path), "utf8"));

test("derived source sizing and both row layouts opt into complement display, bookmakers do not", () => {
  const detail = read("Views/EventDetailView.swift");
  const sources = detail.split("private func sourceContent(")[1].split("private func legendItem(")[0];
  expect(sources.match(/complementaryAway: true/g)).toHaveLength(2);
  const rows = detail.split("private func sourceProbabilityRow(")[1].split("private func sourceContent(")[0];
  expect(rows).toContain("complementaryAway: Bool = false");
  expect(rows.match(/complementaryAway: complementaryAway/g)).toHaveLength(3);
  const books = detail.split("private func bookmakerContent(")[1];
  expect(books).toBeDefined();
  expect(books).not.toContain("complementaryAway: true");
});

test("chart, hero, and activity receipt share the bounded display fallback", () => {
  for (const path of ["Components/GamePlayCardView.swift", "Views/EventDetailView.swift", "Utilities/LivePriceActivity.swift"]) {
    expect(read(path)).toContain("complementDisplayPercents(");
  }
  const helper = read("Utilities/ComplementProbabilityDisplay.swift");
  expect(helper).toContain("if let servedAway, let servedHome { return [servedAway, servedHome] }");
  expect(helper).toContain("away == 1 - home");
  const formatter = read("Utilities/FormattingUtilities.swift");
  expect(formatter).toContain("complementaryAway: Bool = false");
  expect(formatter).toMatch(/complementaryAway\s*\? complementDisplayPercents[\s\S]*?: renderedDuelPercents/);
});
