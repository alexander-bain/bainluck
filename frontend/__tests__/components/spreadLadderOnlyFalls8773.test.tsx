/**
 * #8773 — THE FULL-GAME MARGIN LADDER ONLY FALLS ON EACH SIDE.
 *
 * Since #8739 the full-game rail reads Polymarket spread markets beside
 * Kalshi's. Polymarket's far end is thinly traded and runs backwards. On the
 * banked payload (`/events/14781134`, Chargers @ Bills, production
 * 2026-09-26 ~18:40Z):
 *
 *   Spread: Chargers (-19.5)  Chargers 0.0395
 *   Spread: Chargers (-20.5)  Chargers 0.0995
 *   Spread: Chargers (-21.5)  Chargers 0.0395
 *
 * so the card printed "LAC by 20.5+ 10%" under "LAC by 19.5+ 4%". Chargers by
 * 21 or more cannot be likelier than Chargers by 20 or more. The half rails
 * and both totals ladders were already forced monotone; this rail was not.
 *
 * A graded (settled) rail is deliberately left alone: it grades each rung
 * against the final score and holds unpriced rungs at 0 (#8811).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { monotoneSpreadRungs, parseSpreadRungs, type ParsedSpread } from "@/lib/marketMapUtils";

import pre14781134 from "../fixtures/ux8773_game_markets_14781134.20260926.json";
import done15315985 from "../fixtures/ux8739_game_markets_15315985.20260925.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(props: Record<string, unknown>): string {
  const p = props as unknown as React.ComponentProps<typeof MarketMapSection>;
  return visibleText(renderToStaticMarkup(<MarketMapSection {...p} />));
}

/** Every "<ABBR> by N+ P%" ladder row the reader sees, in page order. */
function ladderRows(text: string, abbr: string): Array<{ threshold: number; pct: number }> {
  const re = new RegExp(`\\b${abbr} by (\\d+(?:\\.\\d+)?)\\+\\s+(\\d+)%`, "g");
  return Array.from(text.matchAll(re), (m) => ({ threshold: Number(m[1]), pct: Number(m[2]) }));
}

function isFalling(rows: Array<{ threshold: number; pct: number }>): boolean {
  const sorted = [...rows].sort((a, b) => a.threshold - b.threshold);
  return sorted.every((r, i) => i === 0 || r.pct <= sorted[i - 1].pct);
}

// Props as `app/events/[id]/page.tsx` builds them, from the served event read
// in the same minute as the banked payload.
const chargersAtBills = {
  gameMarkets: pre14781134,
  eventStatus: "scheduled",
  homeTeam: "Buffalo Bills",
  awayTeam: "Los Angeles Chargers",
  homeAbbr: "BUF",
  awayAbbr: "LAC",
  homeWinProb: 0.755,
  awayWinProb: 0.245,
  homeSpread: -7.3,
  openingHomeSpread: null,
  sportKey: "americanfootball_nfl",
};

describe("#8773 — monotoneSpreadRungs", () => {
  const rung = (isHome: boolean, threshold: number, probability: number): ParsedSpread => ({
    team: isHome ? "H" : "A",
    threshold,
    probability,
    source: "polymarket",
    isHome,
    margin: isHome ? threshold : -threshold,
    unit: null,
  });

  it("withholds a rung priced above the last rung kept on its own side", () => {
    const out = monotoneSpreadRungs([
      rung(false, 17.5, 0.04),
      rung(false, 19.5, 0.06),
      rung(false, 21.5, 0.09),
      rung(false, 14.5, 0.05),
    ]);
    expect(out.map((r) => [r.threshold, r.probability])).toEqual([
      [14.5, 0.05],
      [17.5, 0.04],
    ]);
  });

  it("judges each side on its own: a home rung never withholds an away rung", () => {
    const out = monotoneSpreadRungs([rung(true, 3.5, 0.2), rung(false, 7.5, 0.6), rung(false, 3.5, 0.7)]);
    expect(out).toHaveLength(3);
  });

  it("the banked Chargers side falls after the pass, and the Bills side loses nothing it did not break", () => {
    const parsed = parseSpreadRungs(pre14781134.spreads, "Buffalo Bills", "Los Angeles Chargers", "points");
    const lac = parsed.filter((r) => !r.isHome);
    const out = monotoneSpreadRungs(parsed);
    const outLac = out.filter((r) => !r.isHome).sort((a, b) => a.threshold - b.threshold);
    expect(outLac.every((r, i) => i === 0 || r.probability <= outLac[i - 1].probability)).toBe(true);
    // The specimen is real: the Chargers side runs backwards before the pass.
    expect(lac.some((r) => r.threshold === 20.5 && r.probability > 0.09)).toBe(true);
    expect(outLac.some((r) => r.threshold === 20.5)).toBe(false);
  });
});

describe("#8773 — the rendered card", () => {
  it("scheduled 14781134: no Chargers rung is printed above a smaller Chargers rung", () => {
    const text = render(chargersAtBills);
    expect(text).toContain("Margin map");
    const lac = ladderRows(text, "LAC");
    const buf = ladderRows(text, "BUF");
    expect(lac.length).toBeGreaterThanOrEqual(5);
    expect(buf.length).toBeGreaterThanOrEqual(5);
    expect(isFalling(lac)).toBe(true);
    expect(isFalling(buf)).toBe(true);
    expect(lac.some((r) => r.threshold === 20.5)).toBe(false);
  });

  it("control — a graded rail is not re-ordered by price: Army @ Temple still grades against ARMY by 4", () => {
    const text = render({
      gameMarkets: done15315985,
      eventStatus: "completed",
      homeTeam: "Temple Owls",
      awayTeam: "Army Black Knights",
      homeAbbr: "TEM",
      awayAbbr: "ARMY",
      homeWinProb: 0.0,
      awayWinProb: 1.0,
      homeSpread: 3.9,
      openingHomeSpread: 4.0,
      sportKey: "americanfootball_ncaaf",
    });
    expect(text).toContain("Margin: expected vs final");
    expect(text).toMatch(/Final\s+ARMY by 4\b/);
    const legs = parseSpreadRungs(done15315985.spreads, "Temple Owls", "Army Black Knights", "points", {
      keepUnpriced: true,
    });
    // Every graded rung still reaches the card.
    const printed = (text.match(/\b(?:ARMY|TEM) by \d+(?:\.\d+)?\+/g) ?? []).length;
    expect(printed).toBeGreaterThanOrEqual(new Set(legs.map((l) => `${l.isHome}|${l.threshold}`)).size);
  });

  it("control — a graded rail keeps won rungs that sit past an unpriced one", () => {
    // The banked settled ladder is already in price order, so on its own it
    // cannot tell whether the pass ran. One unpriced won rung (ARMY by 0.5+,
    // held at 0 on a graded rail) puts every larger won ARMY rung above it.
    const spreads = done15315985.spreads.map((s) =>
      s.market_name === "Spread: Army (-0.5)" && s.outcome_name === "Army" ? { ...s, probability: null } : s
    );
    const text = render({
      gameMarkets: { ...done15315985, spreads },
      eventStatus: "completed",
      homeTeam: "Temple Owls",
      awayTeam: "Army Black Knights",
      homeAbbr: "TEM",
      awayAbbr: "ARMY",
      homeWinProb: 0.0,
      awayWinProb: 1.0,
      homeSpread: 3.9,
      openingHomeSpread: 4.0,
      sportKey: "americanfootball_ncaaf",
    });
    expect(text).toContain("Margin: expected vs final");
    for (const t of ["0.5", "1.5", "2.5", "3.5"]) {
      expect(text).toContain(`ARMY by ${t}+`);
    }
  });
});
