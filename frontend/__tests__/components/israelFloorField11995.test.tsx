import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import OutcomeRow from "@/components/futures/OutcomeRow";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type { FuturesOutcome } from "@/lib/types";
import specimen from "../../../contracts/one_winner_floor_field_11995.json";

jest.mock("@/components/EntityImage", () => ({ __esModule: true, default: () => null }));

test("the entire Israel field prints 100 points and seventeen <1% bounds", () => {
  const labels = specimen.outcomes.map(o => formatProbabilityPercent(
    o.probability, { rendered: o.rendered_percent },
  ));
  expect(labels.filter(label => label === "<1%")).toHaveLength(17);
  expect(labels.filter(label => label !== "<1%").reduce((sum, label) => sum + parseInt(label), 0)).toBe(100);
  expect(labels).not.toContain("0%");
});

test("the actual futures row renders the served floor as a bound", () => {
  const row = specimen.outcomes.find(o => o.name === "Naftali Bennett")!;
  const outcome: FuturesOutcome = {
    id: row.id, name: row.name, probability: row.probability,
    rendered_percent: row.rendered_percent, american_odds: null,
    rank: null, rank_change_24h: null, movement: null,
    probability_change_24h: null, opening_probability: null,
    opening_american_odds: null, last_updated: specimen.observed_at,
    is_winner: false, resolution_source: "ungradeable_result",
  };
  const html = renderToStaticMarkup(<OutcomeRow
    outcome={outcome}
    rank={14} isLeader={false} isSelected={false} onToggleSelect={() => {}}
    hasHistory={false} marketCategory="politics" marketName={specimen.market_name}
    rendered={row.rendered_percent} renderedOpening={null}
    showLastMove={false} showEntityImage={false}
  />);
  expect(html).toContain("Naftali Bennett");
  expect(html).toContain("&lt;1%");
  expect(html).not.toContain(">0%</");
});
