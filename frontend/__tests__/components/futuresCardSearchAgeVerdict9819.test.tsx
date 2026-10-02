/**
 * #9819 — A SEARCH CARD'S AGE DESCRIBES THE PRICES IT ACTUALLY PRINTS.
 *
 * The backend half (`_served_prices_as_of` + `_search_row_prints_a_verdict`)
 * drops a row's stamp from `prices_updated_at` exactly when this card draws the
 * row as `Won`/`Lost`. This file mounts the real FuturesCard on the wire that
 * backend serves and reads the rows and the footer TOGETHER, because the claim
 * is about the pair: every printed price is covered by the footer, and no
 * printed result is.
 *
 * `fixtures/searchAge9819.json` is the search formatter's own output for three
 * boards. `backend/tests/test_search_settled_leg_does_not_age_card_9819.py`
 * asserts the file equals what the formatter serves today, so this test cannot
 * drift onto a wire the backend no longer sends.
 *
 * The clock is frozen at 2026-10-02 12:00Z, so every relative string is fixed.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket } from "../../lib/types";
import wire from "../fixtures/searchAge9819.json";

const NOW = new Date("2026-10-02T12:00:00.000Z");

type Board = (typeof wire)[keyof typeof wire];

function card(board: Board): FuturesMarket {
  return {
    description: null,
    source: "polymarket",
    category: "championship",
    sport: null,
    sport_name: null,
    llm_sport_category: "baseball",
    external_id: null,
    mutually_exclusive: false,
    commence_time: null,
    resolution_date: null,
    outcome_count: board.top_outcomes.length,
    created_at: null,
    updated_at: "2026-10-02T11:59:00+00:00",
    ...board,
    top_outcomes: board.top_outcomes.map((o) => ({
      american_odds: null,
      rank: null,
      movement: null,
      ...o,
    })),
  } as unknown as FuturesMarket;
}

function html(board: Board): string {
  return renderToStaticMarkup(<FuturesCard market={card(board)} />);
}

/** The card's footer pip, or null when it renders nothing. */
function pip(board: Board): string | null {
  const spans = [
    ...html(board).matchAll(/class="text-micro text-text-muted"[^>]*>([^<]*)</g),
  ];
  if (spans.length === 0) return null;
  return spans[spans.length - 1][1].trim();
}

/** The text that follows a leg's name, up to the next leg (tags stripped). */
function rowText(board: Board, name: string): string {
  const text = html(board).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const at = text.indexOf(name);
  if (at < 0) throw new Error(`${name} is not on the card`);
  return text.slice(at + name.length, at + name.length + 24);
}

beforeAll(() => {
  jest.useFakeTimers().setSystemTime(NOW);
});

afterAll(() => {
  jest.useRealTimers();
});

describe("#9819 the footer covers the printed prices and no printed result", () => {
  it("NLDS (open): the authoritative winners print Won and the footer is the live rows' age", () => {
    expect(rowText(wire.nlds, "Los Angeles Dodgers")).toMatch(/^[^A-Za-z0-9%]*Won/);
    expect(rowText(wire.nlds, "Milwaukee Brewers")).toMatch(/^[^A-Za-z0-9%]*Won/);
    expect(rowText(wire.nlds, "San Diego Padres")).toMatch(/^\s*79%/);
    // Padres/Braves/Cubs were written 2026-09-30 11:48Z; the Won rows on 09-29.
    expect(wire.nlds.prices_updated_at).toBe("2026-09-30T11:48:14+00:00");
    expect(pip(wire.nlds)).toBe("2d ago");
  });

  it("ALCS (open): Toronto prints a numeric 0%, so its Sep 23 age stays on the card", () => {
    expect(rowText(wire.alcs, "Toronto Blue Jays")).toMatch(/^\s*0%/);
    expect(rowText(wire.alcs, "Toronto Blue Jays")).not.toMatch(/Won|Lost/);
    expect(pip(wire.alcs)).toBe("Sep 23");
  });

  it("a resolved board of results prints Won/Lost and no age at all", () => {
    expect(rowText(wire.resolved, "Seattle Mariners")).toMatch(/^[^A-Za-z0-9%]*Won/);
    expect(rowText(wire.resolved, "Houston Astros")).toMatch(/^[^A-Za-z0-9%]*Lost/);
    expect(wire.resolved.prices_updated_at).toBeNull();
    // The footer span is still drawn, empty: a null age renders nothing.
    expect(pip(wire.resolved) ?? "").toBe("");
  });
});
