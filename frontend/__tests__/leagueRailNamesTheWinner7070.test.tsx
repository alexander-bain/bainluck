// A LEAGUE RAIL STOPS DENYING A RESULT ITS OWN PAYLOAD CARRIES — #7070.
//
// Photographed by live/398 on production, `/sport/tennis/atp` at 390px,
// 2026-09-18 23:4xZ, under the heading NO RESULT REPORTED:
//
//     No result reported · Sep 18     Sanchez Izquierdo / Kolar
//     No result reported · Sep 18     Cervantes / Molchanov / Jecan / Pavel
//
// One tap away, in the same minute, each of those rows' own hero read
// "Settled · Sanchez Izquierdo wins" / "Settled · Cervantes / Molchanov wins".
// The page and the card disagreed about the same match because only the page
// had ever been given the venue's grade (#6381). Reach, measured through the
// routes across eight leagues: 17 of 42 rail rows hold a venue winner, and FOUR
// of the eight leagues hold none — the sentence appears where the venue graded
// and nowhere else, which is the half that proves this is not a relabelling.
//
// ── WHAT IS PINNED HERE, AND WHY EACH ARM EXISTS ──
//
//  1. The CARD, rendered, driven through `leagueGameToEvent` — the surface's own
//     builder, not a hand-written `Event`. A consumer fix can be perfect and
//     still never reach the reader because the mapper dropped the key on the way
//     in; running the real mapper is the only arm that can see that.
//  2. The MAPPER, on the three states the envelope has (absent / false / true).
//     The middle one is a real answer ("we asked, nothing graded it") and a
//     truthiness test would flatten it into the first.
//  3. The rail HEADING (`unreportedRailTitle`), because a heading reading NO
//     RESULT REPORTED over a card reading "Settled · … wins" is the same
//     self-contradiction one screen wide — #7060 in a heading instead of a
//     banner.
//  4. The PAGE AS SOURCE. Arms 1-3 cannot see the literal string being typed
//     back into the JSX beside the function, which is the cheapest way for this
//     to regress, and a Next.js page exports nothing a test can call.
//
// BOTH DIRECTIONS EVERYWHERE (gotcha #43): every case asserting the new sentence
// APPEARS has a sibling asserting the denial is untouched where it is still
// true, so a fix written one condition too wide cannot pass. And every absence
// assertion is backed by a control that makes the same probe say PRESENT — an
// absence assertion passes just as happily over a string that never existed.

import React from "react";
import fs from "fs";
import path from "path";
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
import type { LeagueGameBrief } from "@/lib/api";
import {
  MIXED_UNREPORTED_RAIL_TITLE,
  leagueGameToEvent,
  unreportedRailTitle,
} from "@/lib/leagueCards";
import { SUSPENDED_LABEL } from "@/lib/eventState";

const DENIAL = SUSPENDED_LABEL; // "No result reported"

// Offsets, never literals (gotcha #44): a hard-coded "Sep 18" grows a year
// suffix the moment the calendar rolls over, and the offset is in DAYS so the
// anchor cannot drift across a local midnight mid-run.
const DAY = 24 * 3600_000;
const PLAYED_2D_AGO = new Date(Date.now() - 2 * DAY).toISOString();

/**
 * `/api/leagues/tennis_atp` → `unreported_games[]`, event 15314430, copied
 * VERBATIM from production on 2026-09-19 00:4xZ apart from the clock-safe
 * commence stamp. Every price field is genuinely absent on this row — the rail
 * that produced the photograph is unpriced, so a fixture carrying odds would be
 * testing a card state the defect does not live in.
 */
function brief(over: Partial<LeagueGameBrief> = {}): LeagueGameBrief {
  return {
    id: 15314430,
    external_id: null,
    sport: "tennis_atp",
    home_team: "Sanchez Izquierdo",
    away_team: "Kolar",
    commence_time: PLAYED_2D_AGO,
    completed_at: null,
    status: "suspended",
    home_score: null,
    away_score: null,
    home_win_probability: null,
    ...over,
  } as LeagueGameBrief;
}

function renderCard(over: Partial<LeagueGameBrief> = {}): string {
  return renderToStaticMarkup(<EventCard event={leagueGameToEvent(brief(over))} />);
}

/** Rendered text with entities decoded. `&amp;` LAST — see the sibling suites:
 *  unescaping it first turns `&amp;#x27;` into an apostrophe, one escape too
 *  many, so an assertion could pass on text the page never showed. */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** The day-of-month as the card's own locale renders it (#6361's date tail). */
function dayOfMonth(iso: string): string {
  return String(new Date(iso).getDate());
}

// ───────────────────────────────────────────────────────────────────────────
// 1. THE CARD
// ───────────────────────────────────────────────────────────────────────────

describe("the league rail card, rendered through its own mapper", () => {
  it("CONTROL — today's payload, which carries neither key, still denies", () => {
    // The BEFORE, and the reason every absence assertion below means anything.
    // This is the exact shape production served while the photograph was taken:
    // no `venue_settled` key at all. If the card had stopped reaching the
    // suspended arm for some unrelated reason, this case would go red instead
    // of quietly making the rest of the file vacuous.
    const rendered = text(renderCard());
    expect(rendered).toContain(DENIAL);
    expect(rendered).toContain(dayOfMonth(PLAYED_2D_AGO));
    expect(rendered).not.toContain("Settled");
  });

  it("names the winner the venue named, and stops denying", () => {
    const rendered = text(
      renderCard({ venue_settled: true, venue_settled_result: "Sanchez Izquierdo wins" }),
    );
    expect(rendered).toContain("Settled · Sanchez Izquierdo wins");
    expect(rendered).not.toContain(DENIAL);
  });

  it("keeps the date, after the sentence — two meetings of one pair stay tellable apart", () => {
    // #6361's harm, restated on the new sentence: the date is what separates
    // two cards for the same fixture pair, and it is as true of a graded row as
    // of a denied one. It must not be lost in the swap.
    const rendered = text(
      renderCard({ venue_settled: true, venue_settled_result: "Sanchez Izquierdo wins" }),
    );
    // Format-free: the assertion is that the date is still there and still
    // AFTER the sentence (#3211 — a bare stamp ahead of the words reads as a
    // kickoff), not what the date looks like.
    expect(rendered).toMatch(
      new RegExp(`Sanchez Izquierdo wins · [^·]*\\b${dayOfMonth(PLAYED_2D_AGO)}\\b`),
    );
  });

  it("prints the verbatim result even when it carries a score, and parses nothing", () => {
    // `"Draw 0-0"` and `"Aryna Sabalenka wins 2-0"` are the producer's other
    // shape (#6381). The client renders the string as given: the rule about
    // which market may speak lives in one place, and a consumer that read
    // inside this string would be the second place it lives.
    const rendered = text(
      renderCard({ venue_settled: true, venue_settled_result: "Draw 0-0" }),
    );
    expect(rendered).toContain("Settled · Draw 0-0");
    expect(rendered).not.toContain(DENIAL);
  });

  it("graded with nobody named prints the badge alone, never 'Settled · null'", () => {
    // 16 graded props settle an event without ever saying who won it. The badge
    // alone is deliberate: on a card whose siblings print real scorelines, "no
    // result" would invite the reader to supply one.
    const rendered = text(renderCard({ venue_settled: true, venue_settled_result: null }));
    expect(rendered).toContain("Settled");
    expect(rendered).not.toContain(DENIAL);
    expect(rendered).not.toContain("null");
  });

  it("ASKED AND NOTHING GRADED IT — `false` keeps the denial word for word", () => {
    const rendered = text(renderCard({ venue_settled: false, venue_settled_result: null }));
    expect(rendered).toContain(DENIAL);
    expect(rendered).not.toContain("Settled");
  });

  it("a result without the flag is a producer bug, and the card refuses to print it", () => {
    // Not a hypothetical shape worth rendering: the flag is what licenses the
    // sentence, so a payload carrying only the string gets today's card. The
    // card must not treat the presence of a string as permission.
    const rendered = text(
      renderCard({ venue_settled: false, venue_settled_result: "Kolar wins" }),
    );
    expect(rendered).toContain(DENIAL);
    expect(rendered).not.toContain("Kolar wins");
  });

  it("A FINAL IS UNTOUCHED — our own result still outranks everything", () => {
    // The recent-results rail carries the same keys (the producer attaches to
    // all three rails), so this is a live case on the same page, not a
    // contrivance: a row we scored keeps its score block and its FINAL badge.
    const rendered = text(
      renderCard({
        status: "completed",
        completed_at: PLAYED_2D_AGO,
        home_score: 2,
        away_score: 0,
        venue_settled: true,
        venue_settled_result: "Sanchez Izquierdo wins",
      }),
    );
    expect(rendered).toContain("Final");
    expect(rendered).not.toContain("Settled · Sanchez Izquierdo wins");
    expect(rendered).not.toContain(DENIAL);
  });

  it("A FIXTURE THAT HAS NOT STARTED IS UNTOUCHED", () => {
    // The upcoming rail carries the keys too. `hasNoReportedResult` is false
    // here, so the sentence is not computed at all — the same gating the event
    // hero uses, and the reason the flag's other consumers keep their answers.
    const rendered = text(
      renderCard({
        status: "scheduled",
        commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
        venue_settled: true,
        venue_settled_result: "Sanchez Izquierdo wins",
      }),
    );
    expect(rendered).not.toContain("Settled · Sanchez Izquierdo wins");
    expect(rendered).not.toContain(DENIAL);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 2. THE MAPPER
// ───────────────────────────────────────────────────────────────────────────

describe("leagueGameToEvent carries the venue keys, absence included", () => {
  it("an envelope without the keys produces an event without them", () => {
    // Membership, not truthiness: absent and `false` are different answers and
    // the mapper is the one place that can still tell them apart.
    const event = leagueGameToEvent(brief());
    expect("venue_settled" in event).toBe(false);
    expect("venue_settled_result" in event).toBe(false);
  });

  it("`false` survives as `false`, not as absent", () => {
    const event = leagueGameToEvent(brief({ venue_settled: false, venue_settled_result: null }));
    expect("venue_settled" in event).toBe(true);
    expect(event.venue_settled).toBe(false);
  });

  it("`true` and the result travel together, verbatim", () => {
    const event = leagueGameToEvent(
      brief({ venue_settled: true, venue_settled_result: "Sanchez Izquierdo wins" }),
    );
    expect(event.venue_settled).toBe(true);
    expect(event.venue_settled_result).toBe("Sanchez Izquierdo wins");
  });

  it("an undefined result normalises to null rather than to an absent key", () => {
    const event = leagueGameToEvent(brief({ venue_settled: true }));
    expect(event.venue_settled).toBe(true);
    expect(event.venue_settled_result).toBeNull();
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 3. THE RAIL HEADING
// ───────────────────────────────────────────────────────────────────────────

describe("unreportedRailTitle", () => {
  it("keeps the denial where it is true of every row", () => {
    expect(
      unreportedRailTitle([
        {},
        { venue_settled: false, venue_settled_result: null },
      ]),
    ).toBe(DENIAL);
  });

  it("an empty rail keeps the denial (the rail renders nothing anyway)", () => {
    expect(unreportedRailTitle([])).toBe(DENIAL);
  });

  it("ONE graded row is enough to stop the heading denying", () => {
    // The heading sits over all of them, so one contradiction below it is one
    // too many. This is the case the photograph was.
    expect(
      unreportedRailTitle([
        {},
        { venue_settled: true, venue_settled_result: "Sanchez Izquierdo wins" },
      ]),
    ).toBe(MIXED_UNREPORTED_RAIL_TITLE);
  });

  it("a row graded without a named side counts — the bare badge contradicts it too", () => {
    // Keyed on the SUMMARY, not on the result string: `venue_settled: true`
    // with a null result still prints "Settled" on the card.
    expect(
      unreportedRailTitle([{ venue_settled: true, venue_settled_result: null }]),
    ).toBe(MIXED_UNREPORTED_RAIL_TITLE);
  });

  it("the mixed heading claims nothing about results", () => {
    // Every heading that carries information is false about half this rail —
    // "No score reported" is contradicted by `"Draw 0-0"`, "Results" by the
    // ungraded rows, "Awaiting results" is a promise the rail refuses to make.
    // So the mixed heading must not contain a verdict word at all.
    expect(MIXED_UNREPORTED_RAIL_TITLE).not.toMatch(/result|score|settled|final/i);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 4. THE PAGE, AS SOURCE
// ───────────────────────────────────────────────────────────────────────────

describe("the league page reads the heading off the rail", () => {
  const PAGE = path.join(__dirname, "..", "app", "sport", "[sport]", "[league]", "page.tsx");
  const source = fs.readFileSync(PAGE, "utf8");

  /** The literal this ship removed, as it stood in the JSX before it. */
  const HARDCODED_DENIAL = /title="No result reported"/;

  it("CONTROL — the probe finds the literal in the pre-fix line", () => {
    // Frozen verbatim (notice 50): this is what the page said on `28656f561`,
    // and it exists so a typo in the pattern above fails HERE instead of
    // silently disarming the assertion below.
    const PRE_FIX_LINE = '        <LeagueGameRail\n          title="No result reported"\n';
    expect(HARDCODED_DENIAL.test(PRE_FIX_LINE)).toBe(true);
  });

  it("the denial is no longer typed into the JSX", () => {
    expect(source).not.toMatch(HARDCODED_DENIAL);
  });

  it("the rail's title comes from the function, computed on that rail's games", () => {
    // Not merely "imports it": the heading has to be computed on the rail's OWN
    // list, and passing the upcoming rail's games would read as a fix.
    expect(source).toContain("title={unreportedRailTitle(unreportedGames)}");
  });
});
