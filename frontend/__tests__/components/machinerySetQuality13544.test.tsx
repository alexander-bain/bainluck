import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
    }) => R.createElement("a", { href, ...rest }, children),
  };
});

describe("#13544 — Row context (196-A) and selection rationale on MachineryDiscoverCard", () => {
  const baseCard: MachineryCardContract = {
    slug: "machinery-everyday-prices",
    form_id: "theme_compact_rows",
    kicker: "ECONOMICS",
    title: "What Everyday Prices Move Next?",
    subtitle: "Four price gauges moving together.",
    footer: "Separate markets grouped together. They do not add up to 100%.",
    selection_note: "Top 4 by trading volume out of 12 open markets in this group",
    scale_ordered: false,
    section_count: 1,
    item_count: 12,
    item_noun: "markets",
    destination_href: "/collections/machinery-everyday-prices",
    rows: [
      {
        outcome_id: 101,
        name: "California gas average above $5.00 in Dec?",
        rendered_percent: 42,
        row_context: {
          text: "Today: $4.68/gal",
          as_of: "2026-11-23",
          source: "AAA",
          kind: "spot_reading",
        },
      },
      {
        outcome_id: 102,
        name: "US egg prices above $4.50/doz?",
        rendered_percent: 31,
        row_context: {
          text: "Missing date should omit",
          as_of: "",
          source: "BLS",
        },
      },
      {
        outcome_id: 103,
        name: "US diesel average above $4.20?",
        rendered_percent: 55,
      },
    ],
  };

  it("renders complete 196-A row_context, hides incomplete/absent context, and shows selection_note above CTA", () => {
    const html = renderToStaticMarkup(<MachineryDiscoverCard card={baseCard} />);
    expect(html).toContain('data-testid="machinery-row-context"');
    expect(html).toContain("Today: $4.68/gal · AAA (2026-11-23)");
    expect(html).not.toContain("Missing date should omit");
    expect(html).toContain('data-testid="machinery-selection-note"');
    expect(html).toContain("Top 4 by trading volume out of 12 open markets in this group");
    expect(html).toContain("See all 12 markets ›");
  });

  it("omits selection_note and row_context markers when absent", () => {
    const minimalCard: MachineryCardContract = {
      ...baseCard,
      selection_note: null,
      rows: [
        {
          outcome_id: 201,
          name: "Single clean row",
          rendered_percent: 60,
        },
      ],
    };
    const html = renderToStaticMarkup(<MachineryDiscoverCard card={minimalCard} />);
    expect(html).not.toContain('data-testid="machinery-selection-note"');
    expect(html).not.toContain('data-testid="machinery-row-context"');
  });
});
