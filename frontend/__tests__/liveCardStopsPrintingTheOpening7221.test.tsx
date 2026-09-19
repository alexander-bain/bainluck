// A LIVE CARD STOPS PRINTING THE PRE-MATCH NUMBER AS ITS LIVE PERCENTAGE — #7221.
//
// Photographed by live/421 on production, `/search?q=Uganda` at 390px,
// 2026-09-19 14:23Z. The live card read:
//
//     INTERNATIONAL T20                                   ● LIVE
//     Uganda                                                 64%
//     Kenya                                                  36%
//     Opened 64/36
//
// The live figure and the pre-match figure were the same number, because they
// WERE the same number: `current_odds.home_probability` was
// `compute_aggregate_probability`'s Tier-3 answer, which is
// `opening_home_probability` itself (#6694). The one book the same payload
// counted and stamped — `bookmaker_odds[0]`, fanduel, `captured_at` to the
// microsecond identical — priced Uganda at 0.0597.
//
// ── WHY THIS TEST EXISTS ON THE FRONTEND AT ALL ──
//
// The fix is a backend one (`routes/events.py`, both `current_odds` sites) and
// it is guarded there. This file answers the other question, the one a payload
// test structurally cannot: DOES THE FIX REACH THE READER. It drives the real
// card on the real BEFORE and AFTER payloads and reads the percentage the card
// actually prints.
//
// The card is the arm with no escape hatch. On the DETAIL page
// `resolveProbability` cross-checks `current_odds` against the chart's own
// series and overrides it when the two differ by more than five points, so the
// worst specimens were partly masked there; `EventCard` — `/search`,
// `/sport/...`, team pages — has no history to cross-check against and prints
// this number flat. Nine of the sixteen live events carrying the signature at
// 14:17Z were more than five points from their books, the worst 58.19.
//
// The BEFORE case is not decoration: it is the control that makes the AFTER
// assertion mean something. If the card stopped reading `current_odds` for some
// unrelated reason, BOTH numbers would vanish and only the control can say so.
//
// This file adds no component code and changes no layout (notice 41): it reads
// `EventCard` exactly as production serves it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import type { Event } from "@/lib/types";

/** Offset, never a literal (gotcha #44): the card's live arm is clock-gated. */
const STARTED_3H_AGO = new Date(Date.now() - 3 * 3600_000).toISOString();

const OPENING = 0.6414; // what `current_odds` served
const BOOK = 0.0597; // what `bookmaker_odds[0]` said, same microsecond

/**
 * `GET /api/events/search?q=Uganda` → `results[]`, event 15314578, copied
 * verbatim from production 2026-09-19 14:21:55Z apart from the clock-safe
 * commence stamp and the one field this ship moves.
 */
function row(currentHome: number): Event {
  return {
    id: 15314578,
    external_id: "b971e7ef248fd92010c62df9aca91449",
    sport: "cricket_international_t20",
    sport_name: "International Twenty20",
    home_team: "Uganda",
    away_team: "Kenya",
    commence_time: STARTED_3H_AGO,
    completed_at: null,
    status: "live",
    started_without_result: false,
    home_score: null,
    away_score: null,
    win_probability_sources: {
      betting_book_count: {
        value: 1.0,
        display_name: "betting_book_count",
        type: "model",
        color: "#6b7280",
        evidence_status: "not_applicable",
      },
    },
    current_odds: {
      captured_at: new Date().toISOString(),
      home_probability: currentHome,
      away_probability: Number((1 - currentHome).toFixed(6)),
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
      bookmaker_count: 1,
    },
    opening_odds: {
      home_probability: OPENING,
      away_probability: Number((1 - OPENING).toFixed(4)),
      spread: null,
      over_under: null,
      favorite: "home",
    },
  } as unknown as Event;
}

/** Rendered text with entities decoded. `&amp;` LAST — unescaping it first
 *  turns `&amp;#x27;` into an apostrophe, one escape too many. */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const render = (currentHome: number) =>
  text(renderToStaticMarkup(<EventCard event={row(currentHome)} />));

describe("the live search/league card, driven on both payloads", () => {
  it("BEFORE — today's payload prints the opening as the live number, twice", () => {
    // The control. This is the photograph: 64% live, and `Opened 64/36` under
    // it, one number wearing two labels.
    const rendered = render(OPENING);
    expect(rendered).toContain("64%");
    expect(rendered).toContain("Opened 64/36");
  });

  it("AFTER — the served book reaches the printed percentage", () => {
    const rendered = render(BOOK);
    expect(rendered).toContain("6%");
    expect(rendered).toContain("94%");
  });

  it("AFTER — and the live figure stops being the pre-match figure", () => {
    const rendered = render(BOOK);
    // `Opened 64/36` STAYS: the opening is a real fact and this ship does not
    // touch it. What must not survive is the live chip repeating it.
    expect(rendered).toContain("Opened 64/36");
    expect(rendered).not.toContain("64%");
  });
});
