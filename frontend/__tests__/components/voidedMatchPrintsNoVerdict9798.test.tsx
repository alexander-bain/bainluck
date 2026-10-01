/**
 * #9798 — A MATCH THE VENUE VOIDED PRINTS NO VERDICT AND NO PRICE.
 *
 * `/events/15321431`, Fernandez v Dickerson (Curitiba), production 2026-09-30.
 * The match was never played: Polymarket resolved "Completed Match" No and paid
 * every other leg at the void price — `is_winner=false` on BOTH players,
 * probability 0.5, `clob_authoritative`. The event serves `suspended`,
 * `venue_settled: false`, `venue_closed_no_winner: true`, and the header pill
 * reads "Ended · no winner" (#5811).
 *
 * Before this fix the page passed `venueSettled={venueSettledSentence !== null}`,
 * which is true for the void sentence too, so Additional Markets read every leg
 * as graded and printed "Lost" beside both players on both sets (LOOK at 390px,
 * `artifacts/ux-0930-9798/before-15321431.png`). Before #5811's key it printed
 * 50% on each, which reads as a coin-flip price on a match nobody played.
 *
 * The fixture is `/api/events/15321431/game-markets`, verbatim (16:11Z).
 */

import { readFileSync } from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { isVenueVoided, venueSettledSummary } from "@/lib/eventState";
import type { GameMarketsResponse } from "@/lib/api";
import fixture from "../fixtures/ux9798_game_markets_15321431.20260930.json";

const DATA = fixture as unknown as GameMarketsResponse;

const render = (props: { venueSettled?: boolean; voided?: boolean }) =>
  renderToStaticMarkup(<SpecialEventMarkets data={DATA} eventStatus="suspended" {...props} />);

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

const PLAYERS = ["Bruno Fernandez wins Set 1", "Ryan Dickerson wins Set 1", "Bruno Fernandez wins Set 2", "Ryan Dickerson wins Set 2"];

const page = readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

describe("#9798 a voided match", () => {
  test("fixture is the specimen: every set leg is is_winner=false at the 0.5 void price", () => {
    const legs = (DATA.other ?? []).filter((r) => /^Set \d Winner/.test(r.market_name ?? ""));
    expect(legs).toHaveLength(4);
    for (const r of legs) {
      expect(r.is_winner).toBe(false);
      expect(r.probability).toBe(0.5);
      expect(r.resolution_source).toBe("clob_authoritative");
    }
  });

  test("control: read as venue-settled, the void prints Lost on both players (production)", () => {
    // What /events/15321431 showed at 390px. Also proves the fixture reaches the
    // verdict branch, so the voided silence below is not an empty card's.
    const text = visible(render({ venueSettled: true }));
    for (const label of PLAYERS) expect(text).toContain(`${label} Lost`);
  });

  test("control: read as unsettled, the void prints 50% on every leg (before #5811)", () => {
    const text = visible(render({}));
    for (const label of PLAYERS) expect(text).toMatch(new RegExp(`${label} 50%`));
  });

  test("voided: no Lost, no Won, no percentage, no settled caption — each card says Void once", () => {
    const html = render({ voided: true });
    const text = visible(html);
    expect(text).not.toMatch(/\bLost\b|\bWon\b/);
    expect(text).not.toMatch(/\d+%/);
    expect(html).not.toContain('data-testid="special-markets-verdict"');
    expect(html).not.toContain('data-testid="special-markets-settled-note"');
    expect(html).not.toContain('data-testid="price-age-mark"');
    const cards = (html.match(/class="border border-surface-border rounded-lg p-3"/g) ?? []).length;
    expect(cards).toBeGreaterThan(0);
    expect((html.match(/data-testid="special-markets-void"/g) ?? []).length).toBe(cards);
    // The names stay: the reader still sees what was asked.
    for (const label of PLAYERS) expect(text).toContain(label);
  });

  test("voided outranks the venue-settled flag and a settled status", () => {
    for (const html of [
      render({ voided: true, venueSettled: true }),
      renderToStaticMarkup(<SpecialEventMarkets data={DATA} eventStatus="completed" voided />),
    ]) {
      expect(visible(html)).not.toMatch(/\bLost\b|\d+%/);
      // The section caption is the settled state word; a void is not that state.
      expect(html).not.toContain('data-testid="special-markets-settled-note"');
    }
  });

  test("the prop defaults to false: callers that pass nothing are unchanged", () => {
    expect(render({ voided: undefined })).toBe(render({ voided: false }));
  });

  test("isVenueVoided follows venueSettledSummary's rule: a graded winner wins", () => {
    expect(isVenueVoided(false, true)).toBe(true);
    expect(isVenueVoided(undefined, true)).toBe(true);
    expect(isVenueVoided(true, true)).toBe(false);
    expect(isVenueVoided(false, false)).toBe(false);
    expect(isVenueVoided(false, null)).toBe(false);
    // Every voided answer is also the page's "Ended · no winner" pill, so the
    // two never disagree about the same row.
    expect(venueSettledSummary(false, null, true)).toBe("Ended · no winner");
    expect(venueSettledSummary(true, "Ymer wins", true)).toBe("Settled · Ymer wins");
  });

  test("the event page keeps a void out of venueSettled and passes it as voided", () => {
    const start = page.indexOf("<SpecialEventMarkets");
    const call = page.slice(start, page.indexOf("/>", start));
    expect(call).toContain("venueSettled={venueSettledSentence !== null && !venueVoided}");
    expect(call).toContain("voided={venueVoided}");
    expect(page).toContain(
      "const venueVoided = isVenueVoided(event?.venue_settled, event?.venue_closed_no_winner);",
    );
  });

  test("the event page does not mount the games/margin maps on a voided match", () => {
    expect(page).toContain("{gameMarkets && !venueVoided && marketMapSectionMounts(gameMarkets) && (");
    // #3240: the note that points at the map must agree the map is not there.
    expect(page).toContain(
      "totalsMapPresent={!venueVoided && totalsMapRenders(gameMarkets, event.status, sportVocab(event.sport || undefined))}",
    );
  });
});
