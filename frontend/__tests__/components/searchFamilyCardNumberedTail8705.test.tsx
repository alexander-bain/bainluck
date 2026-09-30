/**
 * #8705 — a numbered card printed its rows as bare numbers.
 *
 * Production 2026-09-28 01:3xZ, `/search?q=lgd` at 390px, the OTHER SPORTS card:
 * the header read `Dota 2: LGD Gaming vs Xtreme Gaming - Game` and its two rows
 * read `1 Winner` / `2 Winner`. Siblings numbered `Game 1` / `Game 2` diverge AT
 * the number, so the split landed between the noun and its index.
 *
 * Rendered through the card (not only `familyRowTitles`) because the reader-
 * visible defect is the hoisted header plus the row text together.
 */

import { renderToStaticMarkup } from "react-dom/server";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import type { FuturesFamily } from "@/lib/types";

const row = (id: number, name: string, leader: string, probability: number) => ({
  id,
  name,
  outcome_count: 2,
  resolution_date: null,
  top_outcomes: [{ id: id * 10, name: leader, probability, movement: null, american_odds: null }],
});

const LGD_CARD = {
  family_key: "sport:esports",
  label: "Other Sports",
  headline: row(1, "Dota 2: LGD Gaming vs Xtreme Gaming - Game 1 Winner", "LGD Gaming", 0.58),
  members: [row(2, "Dota 2: LGD Gaming vs Xtreme Gaming - Game 2 Winner", "LGD Gaming", 0.6)],
  more_count: 0,
  member_count: 2,
} as unknown as FuturesFamily;

const markup = renderToStaticMarkup(<SearchFamilyCard family={LGD_CARD} />);
/** Visible text only: `sr-only` spans carry the subject for screen readers and
 *  are not what a sighted reader sees on the row. */
const visibleText = markup
  .replace(/<span class="sr-only">[^<]*<\/span>/g, " ")
  .replace(/<[^>]*>/g, " ")
  .replace(/\s+/g, " ");

describe("#8705: SearchFamilyCard keeps a number with the noun it indexes", () => {
  test("the hoisted header is the matchup, with no dangling noun", () => {
    expect(markup).toContain(">Dota 2: LGD Gaming vs Xtreme Gaming</div>");
    expect(markup).not.toMatch(/- Game<\/div>/);
  });

  test("each row names its game", () => {
    expect(visibleText).toContain("Game 1 Winner");
    expect(visibleText).toContain("Game 2 Winner");
  });

  test("no row opens on a bare number", () => {
    expect(visibleText).not.toMatch(/(^|>)\s*[12] Winner/);
    expect(markup).not.toMatch(/>[12] Winner</);
  });
});
