import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MidtermsMarketCard from "@/components/collections/MidtermsMarketCard";
import type { FeedFuturesData } from "@/lib/types";

jest.mock("@/components/EntityImage", () => ({ __esModule: true, default: () => null }));

test("the field card prints the full field's served allocation", () => {
  const market = {
    id: 108629, name: "Closest Governor race", source: "kalshi", outcome_count: 6,
    top_outcomes: [
      { id: 1, name: "Alaska", probability: 0.225, rendered_percent: 23 },
      { id: 2, name: "Kansas", probability: 0.225, rendered_percent: 22 },
      { id: 3, name: "Nebraska", probability: 0.2, rendered_percent: 20 },
      { id: 4, name: "Florida", probability: 0.15, rendered_percent: 15 },
      { id: 5, name: "Ohio", probability: 0.1, rendered_percent: 10 },
      { id: 6, name: "Texas", probability: 0.1, rendered_percent: 10 },
    ],
  } as FeedFuturesData;
  const html = renderToStaticMarkup(<MidtermsMarketCard market={market} presentation="field" />);
  expect(html).toContain("23%");
  expect(html).toContain("22%");
  expect(html).toContain("+1 more");
  expect(html).not.toContain("Texas");
});
