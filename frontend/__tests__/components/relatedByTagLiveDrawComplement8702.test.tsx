/**
 * #8702 — THE RAIL'S LIVE SOCCER CARD STOPS PRINTING "DOES NOT LOSE" AS A WIN PRICE.
 *
 * Production, 390px, 2026-09-25 ~20:30Z: `/events/15290673` → MORE SOCCER, live
 * Belgium @ Italy 1–0, read "Belgium 98% · Italy 2%". /sports drew the same row as
 * "Belgium —". Soccer prices a draw; a served `current_odds` pair summing to 1 carries
 * the away side as `1 − home` (draw folded in). `FeedCard` withholds it via
 * `awayIsTheComplement` (#6238); the rail's live branch never asked.
 *
 * Specimen: the banked production feed bytes from #5558 (`ux1493_related_soccer_live_5558`),
 * the same row at 0.5644 / 0.4356. Controls exercise the gate's other branch twice: a
 * two-way sport with a summing pair keeps both numbers, and a soccer pair that does NOT
 * sum to 1 (a real de-vigged away price) keeps its away number.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SOCCER from "../fixtures/ux1493_related_soccer_live_5558.20260925.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

const RelatedByTag = require("@/components/RelatedByTag").default;

type Item = { type: string; data: Record<string, unknown> };
type Payload = { items: Item[] };

const soccer = SOCCER as unknown as Payload;
const belgiumRow = soccer.items.find(
  (item) => item.type === "event" && item.data.status === "live",
)!.data;

function card(data: Record<string, unknown>): string {
  swrPayload = { items: [{ type: "event", data }] };
  const html = renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, { tags: ["sport:x"], limit: 4, title: "More" } as never),
  );
  const start = html.search(new RegExp(`<a [^>]*href="/events/${data.id}"`));
  if (start < 0) throw new Error(`no card for ${data.id}`);
  return html.slice(start, html.indexOf("</a>", start) + 4);
}

/** Visible text of the field rows, with sr-only spans dropped. */
function visibleField(html: string): string {
  const start = html.indexOf('data-testid="related-card-field"');
  if (start < 0) return "";
  const ol = html.slice(start, html.indexOf("</ol>", start));
  return ol
    .replace(/<span class="sr-only">[^<]*<\/span>/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/^[^>]*>/, "")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#8702 the specimen is what the fixture says it is", () => {
  it("Belgium @ Italy is live soccer with a served pair summing to exactly 1", () => {
    expect(belgiumRow.status).toBe("live");
    expect(belgiumRow.sport).toBe("soccer_uefa_nations_league");
    const co = belgiumRow.current_odds as { away_probability: number; home_probability: number };
    expect([co.away_probability, co.home_probability]).toEqual([0.5644, 0.4356]);
    expect(co.away_probability + co.home_probability).toBeCloseTo(1, 10);
  });
});

describe("#8702 the live draw-priced away side is withheld", () => {
  const html = card(belgiumRow);

  it("prints no away percentage — the slot reads '—'", () => {
    expect(visibleField(html)).toBe("Belgium — Italy 44%");
    expect(html).not.toMatch(/56%/);
    expect(html).toContain('data-testid="related-card-away-withheld"');
  });

  it("says why to a screen reader, and keeps the home number on its own line", () => {
    expect(html).toContain("No separate win probability for Belgium.");
    expect(html).toMatch(/Italy<\/span><span class="[^"]*">44%/);
  });
});

describe("#8702 controls — the other branch of the gate", () => {
  it("a two-way sport with a summing pair keeps BOTH numbers", () => {
    const html = card({
      ...belgiumRow,
      id: 15318002,
      sport: "baseball_mlb",
      away_team: "Chicago Cubs",
      home_team: "Boston Red Sox",
    });
    expect(visibleField(html)).toBe("Chicago Cubs 56% Boston Red Sox 44%");
    expect(html).not.toContain("related-card-away-withheld");
  });

  it("a soccer pair that does NOT sum to 1 keeps its real away price", () => {
    const html = card({
      ...belgiumRow,
      id: 15318003,
      current_odds: { away_probability: 0.2885, home_probability: 0.4419 },
    });
    expect(visibleField(html)).toBe("Belgium 29% Italy 44%");
    expect(html).not.toContain("related-card-away-withheld");
  });
});
