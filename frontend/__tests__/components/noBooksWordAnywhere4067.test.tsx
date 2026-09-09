/**
 * #4067 / STANDING NOTICE 33 — THE READER NEVER SEES "books" OR "bookmaker(s)".
 *
 * Alex, Tue 2026-09-08 2:00pm PT, on D92: *"we wouldn't EVER want to reference
 * 'bookmakers'"*. The notice that came out of it bans four spellings —
 * `books`, `bookmaker`, `bookmakers`, `per-bookmaker` — from every label, table
 * row, caption, tooltip, alt text and spoken sentence. The approved word is
 * `sportsbooks`.
 *
 * ═══ WHY THIS GUARD IS A RENDER SWEEP AND NOT A BUNDLE SCAN ═══
 *
 * `shippedCopyBans.test.ts` is the better instrument for a banned WORD and it
 * is deliberately not used here. Its input is every string literal in the
 * shipped chunks, and two of the strings this ship must PRESERVE are literally
 * the banned word:
 *
 *   • `BOOKS_SOURCE = "books"` — the rung id in the payload, which
 *     `data-prematch-source` carries and the measurement rails key on.
 *   • `"odds_api_bookmaker"` — a calibration source key the API serves.
 *
 * A bundle scan cannot tell those from a caption, so pointed at this class it
 * would fail on the two things that must not change and get switched off inside
 * a week — this file's sibling records that exact failure mode for broad rules.
 * So the sweep runs where the distinction is real: over RENDERED TEXT, with the
 * attributes stripped. An id in `data-prematch-source` is invisible to a reader
 * and invisible here; a word in a `<span>` is both.
 *
 * ═══ THE ARM THAT MATTERS MOST IS THE ONE THAT LOOKS REDUNDANT ═══
 *
 * `keeps the rung id on the attribute` is not a nicety. The defect this ship
 * repairs was one constant doing two jobs: `sourceLabel()` returned
 * `BOOKS_SOURCE` as PRINTED TEXT, so the id and the label could not move
 * independently and `finalLeagueCardPrematch2764` was asserting `Pre-match ·
 * ${BOOKS_SOURCE}` — a test that could never have caught the id being shown to
 * a reader, because that is what it was pinning. The split is the fix; without
 * this arm the cheapest way to make the visible half pass is to rename
 * `BOOKS_SOURCE` itself, which silently breaks every rail keyed on the id.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { BOOKS_LABEL, BOOKS_SOURCE } from "@/lib/prematchReading";
import { BOOKS_MARKER } from "@/lib/tournamentResults";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/image", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ src, alt, ...props }: { src: string; alt: string }) =>
      ReactLib.createElement("img", { src, alt, ...props }),
  };
});

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

/** The four spellings, exactly as notice 33 lists them. */
const BANNED = /\b(books?|bookmakers?|per-bookmaker)\b/i;

/**
 * Visible text only — attributes and comments are not copy.
 *
 * `data-prematch-source="books"` must survive this ship and must not be read as
 * a caption, which is the whole distinction this guard turns on. Dropping each
 * tag WHOLE gets that for free: the attributes live inside the angle brackets,
 * so `<[^>]*>` takes them with the tag and no separate attribute pass is needed.
 *
 * 🔴 THE SEPARATE ATTRIBUTE PASS THIS USED TO DO WAS A ReDoS, AND IT WAS ALSO
 * REDUNDANT. It hand-rolled an attribute parser —
 * `<([a-zA-Z][^\s/>]*)((?:\s+[^\s=/>]+(?:=(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*\/?>`
 * — whose `(?:…)*` over an optional group backtracks exponentially, and CodeQL
 * flagged it `js/redos` at high severity on the first CI run of this branch.
 * Rebuilding it "safely" would have been the wrong instinct: the line beneath
 * already removed everything it removed. Deleting it is the fix.
 *
 * Known and accepted limit: an attribute value containing a literal `>` ends
 * the match early and leaves some attribute text in the output. That can only
 * ADD text, so it can only produce a false positive on a guard whose assertions
 * are all "this word is absent" — it can never hide a banned word. React
 * escapes `>` to `&gt;` in attribute values anyway.
 */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** A settled MLB pairing whose only pre-match rung is the sportsbook median. */
function booksFinal(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15299725,
    external_id: "evt-15299725",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Cincinnati Reds",
    away_team: "San Diego Padres",
    commence_time: "2026-09-02T23:10:00.000Z",
    status: "completed",
    home_score: 3,
    away_score: 5,
    opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
    ...over,
  } as FeedEventData;
}

function makeItem(data: FeedEventData): FeedItem {
  return { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
}

const renderFeed = (d: FeedEventData) =>
  renderToStaticMarkup(<FeedCard item={makeItem(d)} />);

const renderDiscover = (d: FeedEventData) =>
  renderToStaticMarkup(
    <DiscoverEventCard
      item={makeItem(d)}
      data={d}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );

describe("notice 33 — the word the site may not print", () => {
  it("the /sports card's pre-match marker says sportsbooks, and no banned word survives the render", () => {
    const html = renderFeed(booksFinal());

    // POSITIVE FIRST. A bare `not.toContain` passes on an empty render, which is
    // how a guard of this shape lies; the marker has to be PRESENT and correct
    // before its absence in the banned form means anything.
    expect(html).toContain("Pre-match · sportsbooks");
    expect(visibleText(html)).not.toMatch(BANNED);
  });

  it("the Discover card says it the same way", () => {
    const html = renderDiscover(booksFinal());

    expect(html).toContain("Pre-match · sportsbooks");
    expect(visibleText(html)).not.toMatch(BANNED);
  });

  it("keeps the rung id on the attribute, where no reader reads it", () => {
    // THE SPLIT, PINNED FROM BOTH SIDES. If a later edit makes the label follow
    // the id again, one of these two fails whichever direction it is folded.
    expect(BOOKS_SOURCE).toBe("books");
    expect(BOOKS_LABEL).toBe("sportsbooks");

    const html = renderFeed(booksFinal());
    expect(html).toContain('data-prematch-source="books"');
    expect(visibleText(html)).not.toMatch(BANNED);
  });

  it("the tournament list's 9px marker is the same one word, not a second copy of it", () => {
    // `tournamentResults.ts` argued for years that its marker and `FeedCard`'s
    // must be the same string, while declaring the word twice three files apart.
    // They agreed by coincidence, and notice 33 had to move both.
    expect(BOOKS_MARKER).toBe(BOOKS_LABEL);
    expect(BOOKS_MARKER).not.toMatch(BANNED);
  });

  it("the predicate is not vacuous — it fires on the copy that used to ship", () => {
    // Every one of these was on production at 2026-09-08 21:18Z. A banned-word
    // test that has never seen a banned word is a test whose regex is wrong.
    for (const shipped of [
      "Pre-match · books",
      "Betting Odds (20+ books)",
      "Per-Bookmaker (Odds API)",
      "the line below is the books' projected run margin",
      "aggregated across multiple bookmakers by The Odds API",
      "median across 5-15 books via The Odds API",
    ]) {
      expect(shipped).toMatch(BANNED);
    }

    // And it leaves the approved word alone — `\bbooks\b` must not find the
    // tail of "sportsbooks", which is the one way this regex could be quietly
    // useless while every arm above still passes.
    for (const kept of [
      "Pre-match · sportsbooks",
      "Kalshi · Polymarket · 7 sportsbooks",
      "Sportsbooks (Odds API)",
      "Per-sportsbook (Odds API)",
    ]) {
      expect(kept).not.toMatch(BANNED);
    }
  });
});
