/**
 * #9956 — a team card stops printing two different awards under the one word "MVP".
 *
 * Production, CWS @ HOU `/events/15321836`, 390px, 2026-09-30 23:08Z, Astros card →
 * PLAYER AWARDS:
 *
 *     Yordan Álvarez   MVP Finalist 98% · MVP 96% · MVP 2%
 *     Jose Altuve      MVP 2% · Championship MVP 1% · MVP 1%
 *
 * The 96% is market 216 "AL MVP Winner?" (clean_label `AL MVP`); the 2% is market
 * 62952891 "ALCS MVP Winner" (clean_label `ALCS MVP`), which matched none of
 * `shortAwardLabel`'s specific arms and fell through to the generic `\bmvp\b`.
 * Same class as #6973 (the finalist arm), a different missing arm.
 *
 * The fixture is the served `/related-futures` payload banked at 23:04Z, trimmed to
 * the award rows; only `last_updated` is re-stamped so the 90-day award-price gate
 * cannot age the specimen out of the render and make this file vacuous.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

import banked from "./fixtures/relatedFutures.15321836.series-mvp-9956.json";

const FRESH = new Date(Date.now() - 2 * 86_400_000).toISOString();
const restamp = (rows: RelatedFuture[]) => rows.map((f) => ({ ...f, last_updated: FRESH }));

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(): string {
  const b = banked as unknown as RelatedFuturesResponse;
  swrPayload = {
    ...b,
    home_team_futures: restamp(b.home_team_futures),
    away_team_futures: restamp(b.away_team_futures),
  };
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: b.event_id,
      homeTeam: b.home_team,
      awayTeam: b.away_team,
      homeTeamColor: "#eb6e1f",
      awayTeamColor: "#27251f",
    }),
  );
}

/** Element-boundary runs; a chip is `<span>LABEL <span>NN%</span></span>` (see #6973's parser). */
function runs(html: string): string[] {
  return html
    .split(/<[^>]+>/)
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

/** The chips drawn on the row that starts at `player`, up to the next player row. */
function rowChips(html: string, player: string, allPlayers: string[]): { label: string; pct: number }[] {
  const r = runs(html);
  const start = r.indexOf(player);
  expect(start).toBeGreaterThanOrEqual(0);
  let end = r.length;
  for (let i = start + 1; i < r.length; i++) {
    if (allPlayers.includes(r[i])) {
      end = i;
      break;
    }
  }
  const out: { label: string; pct: number }[] = [];
  for (let i = start + 1; i < end; i++) {
    const pct = r[i].match(/^(\d+)%$/);
    if (pct) out.push({ label: r[i - 1], pct: Number(pct[1]) });
  }
  return out;
}

const HOME_CARD = (html: string) => {
  const h = html.indexOf('data-testid="home-team-card"');
  const a = html.indexOf('data-testid="away-team-card"');
  expect(h).toBeGreaterThanOrEqual(0);
  return a > h ? html.slice(h, a) : html.slice(h);
};

const ASTROS = ["Yordan Álvarez", "Isaac Paredes", "Christian Walker", "Jose Altuve", "Yainer Diaz", "Carlos Correa"];

describe("#9956 · the parser reads the specimen at all", () => {
  it("finds Álvarez's row and more than one chip on it", () => {
    expect(rowChips(HOME_CARD(render()), "Yordan Álvarez", ASTROS).length).toBeGreaterThan(1);
  });
});

describe("#9956 · no player row prints one award label twice", () => {
  it("THE REPORTED ROW: Álvarez's 2% is the ALCS MVP, and his 96% is still the MVP", () => {
    const chips = rowChips(HOME_CARD(render()), "Yordan Álvarez", ASTROS);
    // Before the fix: [MVP Finalist 98, MVP 96, MVP 2].
    expect(chips).toContainEqual({ label: "ALCS MVP", pct: 2 });
    expect(chips).toContainEqual({ label: "MVP", pct: 96 });
    expect(chips.filter((c) => c.label === "MVP")).toHaveLength(1);
  });

  it("across every Astros row, each label appears at most once", () => {
    const html = HOME_CARD(render());
    for (const p of ASTROS) {
      const labels = rowChips(html, p, ASTROS).map((c) => c.label);
      expect({ player: p, dupes: labels.filter((l, i) => labels.indexOf(l) !== i) }).toEqual({ player: p, dupes: [] });
    }
  });

  it("CONTROL — the finalist and championship arms keep their own labels", () => {
    const chips = rowChips(HOME_CARD(render()), "Yordan Álvarez", ASTROS);
    expect(chips).toContainEqual({ label: "MVP Finalist", pct: 98 });
    expect(chips.map((c) => c.label)).toContain("Championship MVP");
  });
});

describe("#9956 · the spelled-out series name reads the same, not 'Championship MVP'", () => {
  it("'American League Championship Series MVP' is labelled ALCS MVP", () => {
    const b = banked as unknown as RelatedFuturesResponse;
    const spelled = b.home_team_futures.map((f) =>
      f.market_id === 62952891
        ? { ...f, market_name: "American League Championship Series MVP", clean_label: "American League Championship Series MVP" }
        : f,
    );
    swrPayload = { ...b, home_team_futures: restamp(spelled), away_team_futures: restamp(b.away_team_futures) };
    const html = renderToStaticMarkup(
      React.createElement(RelatedFutures, {
        eventId: b.event_id,
        homeTeam: b.home_team,
        awayTeam: b.away_team,
        homeTeamColor: "#eb6e1f",
        awayTeamColor: "#27251f",
      }),
    );
    const chips = rowChips(HOME_CARD(html), "Yordan Álvarez", ASTROS);
    expect(chips).toContainEqual({ label: "ALCS MVP", pct: 2 });
  });
});
