/**
 * #8640 — the search ANSWERS card printed a graded leader as a live price.
 *
 * ═══ WHAT WAS ON THE SCREEN ═══
 *
 * Production 2026-09-25 17:50Z, `/search?q=Fed chair` at 390px, the ANSWERS
 * card's headline: **`Who will be confirmed as Fed chair — Kevin Warsh >99%`**.
 * The served leg (market 2558995, still `status: "open"`) carries
 * `is_winner: true, resolution_source: "api_settlement"` — the venue has called
 * it. `>99%` tells a reader the question is still being priced; it is settled.
 *
 * latency's #8648 (backend half) moved graded rungs of an open multi-winner
 * ladder below the live ones and put `is_winner` + `resolution_source` on each
 * `top_outcomes` item so the client can say which is which. On a one-winner
 * board the graded winner still leads, so the card has to read the grade.
 *
 * ═══ THE RULE IS NOT NEW ═══
 *
 * `outcomeRowVerdict` is the rule the futures card and page already use. Each
 * arm below is one of its clauses, pinned on the search surface with a
 * production-shaped row, so a second private copy of the rule here (the defect
 * class #6082 records) would have to agree with it on every case to pass.
 */

import { renderToStaticMarkup } from "react-dom/server";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import type { FuturesFamily } from "@/lib/types";

type Leg = {
  name: string;
  probability: number;
  is_winner?: boolean | null;
  resolution_source?: string | null;
  movement?: number | null;
};

const card = (status: "open" | "resolved", leg: Leg): FuturesFamily =>
  ({
    family_key: "entity:fed-chair",
    label: "Fed & Rates",
    headline: {
      id: 2558995,
      name: "Who will be confirmed as Fed chair?",
      status,
      outcome_count: 4,
      resolution_date: null,
      top_outcomes: [{ id: 1, american_odds: null, movement: null, ...leg }],
    },
    members: [],
    more_count: 0,
    member_count: 1,
  }) as unknown as FuturesFamily;

/** What the reader sees: tags stripped, then `>`/`<` decoded (React escapes them). */
const text = (f: FuturesFamily): string =>
  renderToStaticMarkup(<SearchFamilyCard family={f} />)
    .replace(/<[^>]*>/g, " ")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/\s+/g, " ")
    .trim();

describe("#8640 search ANSWERS: a graded leader reads as a result", () => {
  it("the production specimen: an authoritative winner on an OPEN market reads Won, not >99%", () => {
    const t = text(
      card("open", {
        name: "Kevin Warsh",
        probability: 0.9995,
        is_winner: true,
        resolution_source: "api_settlement",
      }),
    );
    expect(t).toContain("Kevin Warsh Won");
    expect(t).not.toContain("%");
  });

  it("a won row prints no movement arrow — a result does not move", () => {
    const t = text(
      card("open", {
        name: "Kevin Warsh",
        probability: 0.9995,
        is_winner: true,
        resolution_source: "api_settlement",
        movement: 0.12,
      }),
    );
    expect(t).toContain("Won");
    expect(t).not.toContain("↑");
  });

  it("CONTROL — the retraction (`ungradeable_result`, 109658's rows) keeps its price", () => {
    const t = text(
      card("open", {
        name: "Above 3.00%",
        probability: 0.99,
        is_winner: false,
        resolution_source: "ungradeable_result",
      }),
    );
    expect(t).toContain("99%");
    expect(t).not.toMatch(/\b(Won|Lost)\b/);
  });

  it("CONTROL — a FALSE grade on an open market is not called Lost (defaulted false is not a loss)", () => {
    const t = text(
      card("open", {
        name: "Judy Shelton",
        probability: 0.02,
        is_winner: false,
        resolution_source: "api_settlement",
      }),
    );
    expect(t).toContain("2%");
    expect(t).not.toMatch(/\b(Won|Lost)\b/);
  });

  it("CONTROL — a payload without `resolution_source` (older deploy) keeps today's price", () => {
    const t = text(card("open", { name: "Kevin Warsh", probability: 0.9995, is_winner: true }));
    expect(t).toContain(">99%");
    expect(t).not.toContain("Won");
  });

  it("CONTROL — an ungraded live leader keeps its price and its arrow", () => {
    const t = text(
      card("open", {
        name: "Kevin Warsh",
        probability: 0.6,
        is_winner: false,
        resolution_source: null,
        movement: 0.05,
      }),
    );
    expect(t).toContain("60%");
    expect(t).toContain("↑");
  });

  it("a RESOLVED market's graded loser reads Lost", () => {
    const t = text(
      card("resolved", {
        name: "Kevin Hassett",
        probability: 0.0,
        is_winner: false,
        resolution_source: "api_settlement",
      }),
    );
    expect(t).toContain("Kevin Hassett Lost");
    expect(t).not.toContain("%");
  });
});
