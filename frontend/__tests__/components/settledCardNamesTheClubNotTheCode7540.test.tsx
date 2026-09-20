// #7540 — a finished Discover card names the winner with the CLUB, not an
// airport code.
//
// MEASURED ON PRODUCTION 2026-09-20 15:57Z, `https://bainluck.com/` at 390px,
// page one slot 11: a card whose crests, title and score all said
// "Sunderland @ Manchester City" carried the verdict line **"MNC won"** — a
// three-letter code appearing nowhere else on the card, in a one-word prose
// sentence. Two cards further down the same page the same component in the same
// state read "Getafe won".
//
// THE CAUSE IS THE SLOT, NOT THE HELPER. `teamShortName("Manchester City")`
// returns the FULL name, correctly: "City" is a `CLUB_TYPE_SUFFIXES` entry, so
// the last-word rule declines rather than print a word that names nobody.
// `teamShortNames` then reads `short === full` as `gaveUp` and fires its
// ABBREVIATION RESCUE — which is a PAIR-SYMMETRY device. Its docstring keeps it
// so a card can never read "IPS vs Liverpool", and it fires only when BOTH sides
// carry a code. This slot renders ONE name, so there is no pair on screen to
// keep symmetric: it paid the rescue's whole cost for none of its benefit.
//
// Measured through the real `teamShortNames` (not a re-implementation) over ALL
// 590 settled-and-decided events of the previous 7 days, `db-query`,
// `truncated: false`: 24 (4.1%) printed a code where a club name was in hand,
// every one of them soccer — "LEE" for Leeds United, "BHA" for Brighton and
// Hove Albion, "HSV" for Hamburg SV, "ATX" for Austin FC.
//
// Guards run BOTH directions per gotcha #43: the coded names become clubs, AND
// the three properties that must NOT move are pinned — the #2936 club-type case
// that made this slot pair-aware in the first place, the collide case the pair
// FORM exists for, and the ordinary single-word card that was always right.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { EventCard } from "../../components/discover/EventCard";

/**
 * The production shape of the specimen, keyed by the fields this slot reads.
 *
 * `home_team_data.abbreviation` / `away_team_data.abbreviation` are SET on every
 * fixture below and set to the values production actually served, because a
 * fixture that omitted them could not tell the fix from the defect: the rescue
 * only fires when both are present, so an absent pair passes on master too.
 */
function finished(
  homeTeam: string,
  awayTeam: string,
  homeAbbrev: string,
  awayAbbrev: string,
  scores: { home: number; away: number },
): FeedItem {
  return {
    type: "event",
    headline: "",
    reason: "",
    context_summary: null,
    score: 48,
    data: {
      id: 15305236,
      status: "completed",
      commence_time: "2026-09-20T13:00:00Z",
      away_team: awayTeam,
      home_team: homeTeam,
      away_score: scores.away,
      home_score: scores.home,
      sport: "soccer_epl",
      home_team_data: { abbreviation: homeAbbrev },
      away_team_data: { abbreviation: awayAbbrev },
    } as unknown as FeedEventData,
  } as unknown as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(
    <EventCard
      item={item}
      data={item.data as FeedEventData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

/**
 * The name inside the winner line, read out of its own span.
 *
 * Anchored on the span rather than on a `/(\S+) won/` sweep of the stripped
 * text, because the card's title two lines above already contains both club
 * names: a loose match reads "Sunderland @ Manchester City … Manchester City"
 * as the answer and would pass on master as happily as here.
 */
function verdict(item: FeedItem): string {
  const match = render(item).match(
    /<span class="text-sm font-semibold text-text-primary">(.*?)\s+won<\/span>/,
  );
  return match ? match[1] : "";
}

describe("#7540 — the settled Discover card names the club", () => {
  // The production specimen, exactly as page one served it at 15:57Z.
  it("names Manchester City rather than MNC", () => {
    const line = verdict(
      finished("Manchester City", "Sunderland", "MNC", "SUN", { home: 5, away: 3 }),
    );
    expect(line).toBe("Manchester City");
    expect(line).not.toBe("MNC");
  });

  // The sharpest form of the defect: the WINNER is coded only because of the
  // shape of the LOSER's name. "Everton" is one word the last-word rule handles
  // perfectly; on master it printed "EVE" because its opponent is "Ipswich Town".
  it("does not let the loser's name shape demote the winner's", () => {
    expect(
      verdict(finished("Everton", "Ipswich Town", "EVE", "IPS", { home: 2, away: 0 })),
    ).toBe("Everton");
  });

  // The away-winner arm, so the fix is not pinned on the home branch alone.
  it("names an away winner by its club too", () => {
    expect(
      verdict(finished("Nottingham Forest", "Manchester City", "NFO", "MNC", { home: 0, away: 3 })),
    ).toBe("Manchester City");
  });

  // ── The three properties that must NOT move ───────────────────────────────

  // #2936, the reason this slot is pair-aware at all: a club-type trailing token
  // may never be the whole name. Dropping the abbreviation must not reopen it.
  it("still never prints a club-type token as the winner's name", () => {
    for (const line of [
      verdict(finished("Ipswich Town", "Everton", "IPS", "EVE", { home: 1, away: 0 })),
      verdict(finished("Austin FC", "Vancouver Whitecaps FC", "ATX", "VAN", { home: 2, away: 1 })),
    ]) {
      expect(["Town", "FC", "City", "United"]).not.toContain(line);
    }
  });

  // The pair FORM is kept, and this is what it buys: two sides shortening to one
  // word fall back to both FULL names, so the card cannot crown a name that is
  // equally the loser. With no code in hand this reads better than the rescue's
  // "ATM", which is the second half of why the abbreviation is not passed.
  it("falls back to the full name when both sides shorten to one word", () => {
    const line = verdict(
      finished("Atlético Madrid", "Real Madrid", "ATM", "RMA", { home: 2, away: 0 }),
    );
    expect(line).toBe("Atlético Madrid");
    expect(line).not.toBe("Madrid");
    expect(line).not.toBe("ATM");
  });

  // The 95.9% of the population that was already right is asserted unchanged.
  it("leaves an ordinary single-word card exactly as it was", () => {
    expect(
      verdict(finished("Getafe", "Málaga", "GET", "MCF", { home: 1, away: 0 })),
    ).toBe("Getafe");
  });

  // A drawn card names nobody — the winner line is conditional on a decisive
  // score and this change must not make it render.
  it("still names nobody on a draw", () => {
    const html = render(
      finished("Manchester City", "Sunderland", "MNC", "SUN", { home: 1, away: 1 }),
    );
    expect(html.replace(/<[^>]*>/g, " ")).not.toMatch(/\bwon\b/);
  });
});
