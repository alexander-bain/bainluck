/**
 * #8816 — A MATCH THE VENUE HAS GRADED IS SETTLED FOR ITS PROPS CARD TOO.
 *
 * `/events/15318588`, Vacherot v Harris (ATP), production 2026-09-26 13:30Z.
 * The event is `suspended` (the #7186 state class), so `isSettledStatus` is
 * false. But `venue_settled` is true, and the page header already reads
 * "Settled · Harris wins". Below it, the Additional Markets card drew live bars
 * (Exact Match Score 59 / 20 / 19 / 2%, "4h ago") and left the graded moneyline
 * printing "Lloyd Harris 100%" beside an unpriced Vacherot row.
 *
 * The fixture is `/api/events/15318588/game-markets`, verbatim (13:5xZ). The
 * page now passes `venueSettled={venueSettledSentence !== null}`, the same
 * answer as the header pill (#6381) and the hero (#6438). The arms differ ONLY in
 * that boolean. Same payload, same `suspended` status, so the settled render
 * is the prop and nothing else.
 */

import { readFileSync } from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import type { GameMarketsResponse } from "@/lib/api";
import fixture from "../fixtures/ux8816_game_markets_15318588.20260926.json";

const DATA = fixture as unknown as GameMarketsResponse;

const render = (venueSettled?: boolean) =>
  renderToStaticMarkup(
    <SpecialEventMarkets data={DATA} eventStatus="suspended" venueSettled={venueSettled} />,
  );

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

/** Each verdict row's whole text, bounded by the row element (see #6138's suite). */
const verdictRows = (html: string): string[] =>
  [...html.matchAll(/<div[^>]*data-testid="special-markets-verdict"[\s\S]*?<\/span><\/div>/g)].map(
    (m) => visible(m[0]).trim(),
  );

const EXACT = ["Lloyd Harris wins 2-0", "Lloyd Harris wins 2-1", "Valentin Vacherot wins 2-1", "Valentin Vacherot wins 2-0"];

describe("#8816 a suspended match the venue graded", () => {
  test("fixture is the specimen: suspended status, graded moneyline, ungraded exact book", () => {
    expect(DATA.other?.length).toBe(10);
    expect(DATA.other?.filter((r) => r.resolution_source === "api_settlement")).toHaveLength(2);
  });

  test("the graded moneyline reads Won / Lost, not 100% beside a blank", () => {
    const rows = verdictRows(render(true));
    expect(rows).toContain("Lloyd Harris Won");
    expect(rows).toContain("Valentin Vacherot Lost");
  });

  test("every exact-score percentage is a last quote, not a live bar", () => {
    const text = visible(render(true));
    for (const label of EXACT) {
      expect(text).toMatch(new RegExp(`${label} ${SETTLED_QUOTE_PREFIX} \\d+%`));
    }
  });

  test("no live price-age mark survives on a settled card", () => {
    expect(render(true)).not.toContain('data-testid="price-age-mark"');
  });

  test("control: without the page's answer the same payload still renders as live", () => {
    // What production showed. Also proves the fixture reaches the live branch at
    // all, so the settled assertions above are not an empty card's silence.
    const html = render(false);
    const text = visible(html);
    expect(verdictRows(html)).toHaveLength(0);
    expect(text).toContain("Lloyd Harris wins 2-0 59%");
    expect(text).not.toContain(SETTLED_QUOTE_PREFIX);
    expect(html).toContain('data-testid="price-age-mark"');
  });

  test("the prop defaults to false: callers that pass nothing are unchanged", () => {
    expect(render(undefined)).toBe(render(false));
  });

  test("the event page passes its one venue-settled answer into this section", () => {
    // A component that CAN settle is inert if the page never tells it to — #2086
    // was a declared-and-passed prop that nothing read. Read the call site.
    const page = readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
    const call = page.slice(page.indexOf("<SpecialEventMarkets"), page.indexOf("/>", page.indexOf("<SpecialEventMarkets")));
    expect(call).toContain("eventStatus={event.status}");
    expect(call).toContain("venueSettled={venueSettledSentence !== null}");
  });
});
