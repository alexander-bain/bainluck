/**
 * #5546 — BOTH ENDS OF THE WIN-PROB BAR ARE NAMED BY ONE RULE.
 *
 * ═══ THE DEFECT ═══
 *
 * `/sport/baseball/mlb/team/boston-red-sox`, UPCOMING GAMES, production
 * 2026-09-12 (filed by authority/150 under D48):
 *
 *     vs Kansas City Royals                      Starts 1:10 PM
 *     64%  win prob
 *     [=========================----------------]
 *     Sox                      Kansas City Royals 36%
 *
 * One end of a bar comparing two clubs printed the bare word **Sox**; the other
 * printed the full **Kansas City Royals**. `TeamGameCards.tsx` shortened the
 * left with a raw `teamName.split(" ").pop()` and left the right untouched.
 *
 * The backend is not involved: `GET /api/teams/boston-red-sox` serves both
 * names in full. The asymmetry was entirely that one line.
 *
 * ═══ WHAT THIS FIX DOES NOT DO, STATED UP FRONT ═══
 *
 * ⚠️ **It does not make "Sox" unambiguous.** `teamShortName` deliberately keeps
 * the last word for the American `<place> <nickname>` convention, so Red Sox v
 * Royals still renders `Sox` against `Royals`. The issue separates that out as
 * its second half, and it is #5634's subject (the last-word rule naming a city
 * or a shared nickname — five Berlin clubs all render "Berlin"). Fixing it
 * belongs in `teamShortName`, not at this call site; doing it here would put a
 * THIRD naming rule on a page that already had two.
 *
 * So the guard below asserts SYMMETRY and the collision backstop — not that
 * "Sox" went away. A test that asserted "Boston Red Sox" appears in full at the
 * bar would be asserting a fix nobody made.
 *
 * ═══ WHY THE PAIR HELPER AND NOT `teamShortName` TWICE ═══
 *
 * `teamShortNames` decides both sides together, which is the only way to get
 * the collision backstop: Boston Red Sox against Chicago White Sox BOTH shorten
 * to "Sox", and the pair form falls both back to their full names rather than
 * drawing "Sox" against "Sox". Shortening each side independently cannot see
 * that. The last test is that case.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { UpcomingGameCard } from "../../components/TeamGameCards";
import type { TeamGameBrief } from "../../lib/api";

function brief(overrides: Partial<TeamGameBrief>): TeamGameBrief {
  return {
    id: 1,
    home_team: "Boston Red Sox",
    away_team: "Kansas City Royals",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: new Date(Date.now() + 4 * 3600_000).toISOString(),
    sport_key: "baseball_mlb",
    is_home: true,
    opponent: "Kansas City Royals",
    win_probability: 0.64,
    ...overrides,
  };
}

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(overrides: Partial<TeamGameBrief> = {}, teamName = "Boston Red Sox") {
  return visibleText(
    renderToStaticMarkup(
      <UpcomingGameCard
        game={brief(overrides)}
        teamName={teamName}
        teamColor="#BD3039"
      />
    )
  );
}

describe("#5546 — the win-prob bar names both sides the same way", () => {
  test("THE DEFECT: the opponent end no longer prints the full club name beside a percentage", () => {
    // This is the assertion that is red before the fix. It is anchored to the
    // PERCENTAGE because the full name legitimately appears elsewhere on the
    // card (the matchup line, "vs Kansas City Royals") — a bare `not.toContain`
    // on the name would fail against the fixed card too.
    const text = render();
    expect(text).not.toMatch(/Kansas City Royals\s+36%/);
    expect(text).toMatch(/Royals\s+36%/);
  });

  test("THE FIX: both ends are short, so the bar reads as one comparison", () => {
    const text = render();
    expect(text).toMatch(/Sox\s+Royals\s+36%/);
  });

  test("CONTROL — the matchup line above the bar keeps the FULL opponent name", () => {
    // The card's title is not the bar. Shortening it too would be a different
    // change to a different line, and would lose the only place on this card
    // that says which Kansas City club this is.
    const text = render();
    expect(text).toContain("vs Kansas City Royals");
  });

  test("CONTROL — the card still leads with the probability", () => {
    // Without this, every assertion above could pass against a card that
    // stopped rendering the bar at all.
    const text = render();
    expect(text).toContain("64%");
    expect(text).toContain("win prob");
  });

  test("the away fixture names the opponent the same way", () => {
    // `is_home` drives the "vs"/"@" prefix and the score sides; it must not
    // drive the naming rule.
    const text = render({ is_home: false });
    expect(text).toContain("@ Kansas City Royals");
    expect(text).toMatch(/Sox\s+Royals\s+36%/);
  });

  test("COLLISION BACKSTOP — Red Sox against White Sox falls BOTH back to full names", () => {
    // The reason for the pair helper. Shortening each side alone would draw
    // "Sox" against "Sox 36%" and the bar would compare a team with itself.
    const text = render(
      { away_team: "Chicago White Sox", opponent: "Chicago White Sox" },
      "Boston Red Sox"
    );
    expect(text).toMatch(/Boston Red Sox\s+Chicago White Sox\s+36%/);
    expect(text).not.toMatch(/Sox\s+Sox\s+36%/);
  });

  test("a club whose distinctive word is NOT last keeps its full name", () => {
    // `isNonDistinctiveTrailingWord` is the half of the helper the raw `.pop()`
    // never had: "Tottenham Hotspur FC" must not render as "FC".
    const text = render(
      { away_team: "Tottenham Hotspur FC", opponent: "Tottenham Hotspur FC" },
      "Arsenal FC"
    );
    //
    // Asserted as the POSITIVE form. The first cut of this test used
    // `not.toMatch(/\bFC\s+36%/)` and went red against a correctly-rendered
    // card: the full name "Tottenham Hotspur FC" itself ends in "FC", so that
    // pattern matches the tail of the right answer. A negative assertion about
    // a suffix cannot tell "the name was truncated to FC" from "the name ends
    // in FC".
    expect(text).toMatch(/Arsenal FC\s+Tottenham Hotspur FC\s+36%/);
    expect(text).not.toMatch(/FC\s+FC\s+36%/);
  });
});
