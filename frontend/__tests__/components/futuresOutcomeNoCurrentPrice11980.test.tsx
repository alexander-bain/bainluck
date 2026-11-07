import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import OutcomeRow from "@/components/futures/OutcomeRow";
import type { FuturesOutcome } from "@/lib/types";

function row(
  overrides: Partial<FuturesOutcome> = {},
  isResolved = false,
  rendered: number | null = null,
): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={{
        id: 152597195,
        name: "2",
        probability: null,
        opening_probability: 0.17,
        probability_change_24h: null,
        is_winner: null,
        resolution_source: null,
        ...overrides,
      } as FuturesOutcome}
      rank={3}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory="politics"
      marketName="Alaska Senate rounds"
      isResolved={isResolved}
      rendered={rendered}
      renderedOpening={17}
      showLastMove={false}
      showEntityImage={false}
    />,
  );
}

it("names the missing current price while retaining the labelled historical opening", () => {
  const html = row({}, false, 17);
  expect(html).toContain("No current price");
  expect(html).toContain('data-testid="outcome-open"');
  expect(html).not.toContain('data-testid="outcome-price"');
  expect(html).not.toContain("Latest");
  expect(html).not.toContain("Settled");
});

it.each([0, 0.17])("keeps a genuine %s price numeric", (probability) => {
  const html = row({ probability });
  expect(html).toContain('data-testid="outcome-price"');
  expect(html).toContain("Latest");
  expect(html).not.toContain("No current price");
});

it("keeps a venue winner on an open market as a settled result even without a price", () => {
  const html = row({ is_winner: true, resolution_source: "api_settlement" });
  expect(html).toContain("100%");
  expect(html).toContain("Settled");
  expect(html).not.toContain("No current price");
});

it("keeps a settled loss without a price", () => {
  const html = row({ is_winner: false, resolution_source: "api_settlement" }, true);
  expect(html).toContain("0%");
  expect(html).toContain("Settled");
  expect(html).not.toContain("No current price");
});

it("preserves the existing result-unknown treatment for a resolved market", () => {
  const html = row({ settlement_display: { verdict: "unknown" } as FuturesOutcome["settlement_display"] }, true);
  expect(html).toContain("Result unknown");
  expect(html).not.toContain("No current price");
  expect(html).not.toContain('data-testid="outcome-price"');
});
