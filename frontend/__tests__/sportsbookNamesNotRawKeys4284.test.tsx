/**
 * #4284 (web half) — THE EVENT PAGE NAMES A SPORTSBOOK OR DRAWS NO ROW.
 *
 * ═══ WHAT PRODUCTION SERVED ═══
 *
 * `/events/15308043` (Tigers vs Twins), phone width, "Sportsbooks" disclosure
 * open, 2026-09-09. Read straight off the live DOM — all 17 first-column cells:
 *
 *     betrivers · betmgm · hardrockbet · fanduel · bovada · espnbet · rebet
 *     williamhill_us · mybookieag · draftkings · betonlineag · betus · lowvig
 *     fliff · ballybet · betparx · fanatics
 *
 * Not a subset — EVERY row. `BookmakerTable` rendered `{odds.bookmaker}` raw and
 * never consulted a map, while `SourceAggregationBlock` two sections up held a
 * 23-entry one it did not export. That block's own unknown branch title-cased
 * (`betanysports` → "Betanysports", `williamhill_us` → "Williamhill_us"), which
 * reads like a brand and is not one.
 *
 * ═══ WHY THE FILTER IS AT THE TOP AND NOT AT THE CELL ═══
 *
 * Naming the cell alone would leave the passthrough: the next key the provider
 * adds still reaches the screen. Both components now drop unnameable sources
 * BEFORE anything is derived, so the rows, the "(N of M open)" footer, the
 * consensus average and the divergence flag all describe one set. native/082
 * paid for this on the iOS half in the other order — cap first, label second —
 * where one unknown key cost a *named* sportsbook its slot on the page.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * Every absence below is paired with a survival. `not.toContain("ballybet")`
 * passes perfectly against a component that renders nothing at all, and this
 * file's first draft would have: a table whose rows are all filtered out returns
 * the empty-state string, which contains none of the banned keys.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import BookmakerTable from "@/components/BookmakerTable";
import { SourceAggregationBlock } from "@/components/SourceAggregationBlock";
import { sourceLabel, isNamedSource } from "@/lib/sourceLabels";
import type { BookmakerOddsDetail } from "@/lib/types";

/**
 * The measured production census: `odds_snapshots`, distinct `bookmaker`, the 24
 * hours to 2026-09-09, `truncated: false`. 18 keys, and the name each must show.
 */
const PRODUCTION_KEYS: Array<[string, string]> = [
  ["bovada", "Bovada"],
  ["betonlineag", "BetOnline"],
  ["lowvig", "LowVig"],
  ["draftkings", "DraftKings"],
  ["fanduel", "FanDuel"],
  ["betus", "BetUS"],
  ["betmgm", "BetMGM"],
  ["betrivers", "BetRivers"],
  ["fanatics", "Fanatics"],
  ["williamhill_us", "Caesars"],
  ["mybookieag", "MyBookie"],
  ["fliff", "Fliff"],
  ["ballybet", "Bally Bet"],
  ["betparx", "betPARX"],
  ["espnbet", "ESPN BET"], // #4311: matched to iOS, the brand's own styling
  ["rebet", "Rebet"],
  ["hardrockbet", "Hard Rock"],
  ["betanysports", "BetAnySports"],
];

function odds(bookmaker: string, homeProb: number): BookmakerOddsDetail {
  return {
    bookmaker,
    home_moneyline: -120,
    away_moneyline: 100,
    home_probability: homeProb,
    away_probability: 1 - homeProb,
    captured_at: new Date().toISOString(),
  } as BookmakerOddsDetail;
}

function renderTable(rows: BookmakerOddsDetail[]): string {
  return renderToStaticMarkup(
    <BookmakerTable
      bookmakerOdds={rows}
      homeTeam="Detroit Tigers"
      awayTeam="Minnesota Twins"
    />
  );
}

describe("#4284 — the sportsbook table prints brands, never Odds API keys", () => {
  it("names every one of the 18 keys production actually serves", () => {
    const unnamed = PRODUCTION_KEYS.filter(([key]) => !isNamedSource(key));
    expect(unnamed).toEqual([]);
    for (const [key, name] of PRODUCTION_KEYS) {
      expect(sourceLabel(key)).toBe(name);
    }
  });

  it("renders the brand and not the key, for the whole production slate", () => {
    // The exact 17 rows the live page drew, in the order it drew them.
    const rows = PRODUCTION_KEYS.filter(([k]) => k !== "betanysports").map(
      ([key], i) => odds(key, 0.55 - i * 0.001)
    );
    const html = renderTable(rows);

    // SURVIVAL FIRST — an empty render passes every absence below it.
    expect(html).toContain("<tbody");
    for (const [key, name] of PRODUCTION_KEYS) {
      if (key === "betanysports") continue;
      expect(html).toContain(name);
    }

    // Now the absences. Each key is checked as the raw string the page printed.
    for (const [key] of PRODUCTION_KEYS) {
      if (key === "betanysports") continue;
      expect(html).not.toContain(key);
    }
  });

  it("maps williamhill_us to Caesars, the brand that actually takes the bet", () => {
    const html = renderTable([odds("williamhill_us", 0.543)]);
    expect(html).toContain("Caesars");
    expect(html).not.toContain("williamhill_us");
    // Not the stale brand behind the stale key — that would name a sportsbook
    // this row does not come from.
    expect(html).not.toContain("William Hill");
  });

  it("drops a source it cannot name instead of printing or title-casing it", () => {
    const html = renderTable([
      odds("draftkings", 0.55),
      odds("someNewBookie", 0.61),
    ]);
    expect(html).toContain("DraftKings"); // survival
    expect(html).not.toContain("someNewBookie");
    expect(html).not.toContain("SomeNewBookie");
    expect(html).not.toContain("Somenewbookie");
  });

  it("keeps the footer count honest about the rows it is showing", () => {
    // Two named + one unnameable. The old code would have counted three.
    const stale = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    const html = renderTable([
      odds("draftkings", 0.55),
      { ...odds("fanduel", 0.54), captured_at: stale },
      odds("someNewBookie", 0.61),
    ]);
    expect(html).toContain("DraftKings"); // survival
    expect(html).toContain("1 of 2 open");
    expect(html).not.toContain("1 of 3 open");
  });

  it("never lets an unnameable price move the consensus average", () => {
    // 0.50 and 0.60 average to 55.0%. A third row at 0.90 would drag it to 66.7%
    // if the naming filter ran after the arithmetic instead of before it.
    const html = renderTable([
      odds("draftkings", 0.5),
      odds("fanduel", 0.6),
      odds("someNewBookie", 0.9),
    ]);
    expect(html).toContain("55.0%");
    expect(html).not.toContain("66.7%");
  });
});

describe("#4284 — the source block stops title-casing keys into brands", () => {
  function renderBlock(sources: string[]): string {
    return renderToStaticMarkup(
      <SourceAggregationBlock
        sources={sources.map((source, i) => ({
          source,
          outcomes: { 42: 55 + i },
          captured_at: new Date().toISOString(),
          stale: false,
        }))}
        primaryOutcomeId={42}
        aggregatedProbability={55}
      />
    );
  }

  it("counts only the sources it shows", () => {
    // Three payload rows, one unnameable — the line must say two, not three.
    // This is the whole filter, observed: the per-source rows themselves sit
    // behind `expanded` state that `renderToStaticMarkup` cannot open (there is
    // no @testing-library in this project), so the header count is the reachable
    // proof, and the row LABEL is pinned by the source scan below.
    const html = renderBlock(["kalshi", "draftkings", "someNewBookie"]);
    expect(html).toContain("Aggregated from"); // survival
    expect(html).toContain("2 sources");
    expect(html).not.toContain("3 sources");
    expect(html).not.toContain("someNewBookie");
    expect(html).not.toContain("SomeNewBookie");
  });

  it("still counts every source it CAN name", () => {
    // The control for the case above: drop the unnameable key and the count must
    // come back to three, or the test would be passed by a component that has
    // simply stopped counting.
    const html = renderBlock(["kalshi", "draftkings", "fanduel"]);
    expect(html).toContain("3 sources");
  });

  it("has no title-casing fallback left in the label expression", () => {
    // Anchored on the CODE, not on prose: this file's own header quotes the
    // strings the old branch produced, and so does the component's comment, so a
    // scan for those words would red on the explanation of the fix.
    const src = readFileSync(
      join(__dirname, "..", "components", "SourceAggregationBlock.tsx"),
      "utf8"
    );
    expect(src).toContain("sourceLabel(src.source)"); // survival
    expect(src).not.toContain("charAt(0).toUpperCase()");
    // And it no longer keeps a second copy of the map.
    expect(src).not.toMatch(/const SOURCE_LABELS\b/);
  });
});

describe("standing notice 33 — no reader ever sees the word 'bookmaker'", () => {
  it("keeps it out of the rendered table", () => {
    const html = renderTable([odds("draftkings", 0.55)]);
    expect(html).toContain("DraftKings"); // survival
    // Machine keys are out of scope (Fable-5's 2026-09-08 clarification); this
    // asserts on rendered TEXT, so strip the markup before looking.
    const text = html.replace(/<[^>]*>/g, " ");
    expect(text.toLowerCase()).not.toContain("bookmaker");
    expect(text).not.toMatch(/\bbooks\b/i);
    expect(text).toContain("Sportsbook");
  });
});
