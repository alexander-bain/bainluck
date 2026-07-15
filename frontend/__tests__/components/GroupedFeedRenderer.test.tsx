// L2-119: the grouped props strip renders the shared Quantity kernel per
// question. formatThresholdTitle enforces the kernel discipline — a ladder
// never renders without its question context (a non-empty title).

import { formatThresholdTitle } from "../../components/GroupedFeedRenderer";

describe("formatThresholdTitle", () => {
  test("sentence-cases the lowercased backend stem", () => {
    expect(formatThresholdTitle("will the fed cut rates")).toBe(
      "Will the fed cut rates",
    );
  });

  test("trims dangling stem artifacts left by the numeric-strip", () => {
    // "Will Bitcoin exceed $90,000?" → stem "will bitcoin exceed $" → title
    expect(formatThresholdTitle("will bitcoin exceed $")).toBe(
      "Will bitcoin exceed",
    );
  });

  test("collapses whitespace", () => {
    expect(formatThresholdTitle("player   points   scored")).toBe(
      "Player points scored",
    );
  });

  test("never returns an empty title (kernel discipline)", () => {
    expect(formatThresholdTitle("")).toBe("Threshold market");
    expect(formatThresholdTitle("  # $ ")).toBe("Threshold market");
  });
});
