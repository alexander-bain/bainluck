/**
 * #11541 — on a sport that prices a draw, the team card never prints 100 − team%
 * as the opponent's chance.
 *
 * Production, Arsenal's team page: "vs Borussia Dortmund · 67% win prob ·
 * Dortmund 33%". The 67% is Arsenal's three-way price and matches the game page.
 * The 33% is Dortmund's chance plus the draw's, and the game page prints no
 * Dortmund number at all. The backend half of #11541 fixes the away rows' own
 * number; this half stops the card inventing the opponent's.
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

// Offset from the ambient clock: the card reads it (gotcha #44).
const IN_16_DAYS = new Date(Date.now() + 16 * 24 * 3600_000).toISOString();

function brief(overrides: Partial<TeamGameBrief>): TeamGameBrief {
  return {
    id: 15342698,
    home_team: "Arsenal",
    away_team: "Borussia Dortmund",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: IN_16_DAYS,
    sport_key: "soccer_uefa_champs_league",
    is_home: true,
    opponent: "Borussia Dortmund",
    win_probability: 0.672,
    ...overrides,
  };
}

function render(overrides: Partial<TeamGameBrief> = {}, teamName = "Arsenal") {
  return renderToStaticMarkup(
    <UpcomingGameCard game={brief(overrides)} teamName={teamName} teamColor="#EF0107" />,
  );
}

function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/&[a-z#0-9]+;/g, " ").replace(/\s+/g, " ").trim();
}

describe("#11541 — a draw is not the opponent's win", () => {
  test("THE DEFECT: a soccer card no longer prints the draw as the opponent's chance", () => {
    const text = visibleText(render());
    expect(text).not.toMatch(/33%/);
  });

  test("the club's own number still leads the card", () => {
    const text = visibleText(render());
    expect(text).toContain("67%");
    expect(text).toContain("win prob");
    expect(text).toContain("vs Borussia Dortmund");
  });

  test("the bar draws only the club's share, not a two-way split", () => {
    const html = render();
    expect(html).toContain("width:67%");
    expect(html).not.toContain("width:33%");
  });

  test("an away soccer card prints its own number and no opponent's", () => {
    const text = visibleText(
      render(
        {
          home_team: "Newcastle United",
          away_team: "Arsenal",
          is_home: false,
          opponent: "Newcastle United",
          sport_key: "soccer_epl",
          win_probability: 0.594,
        },
      ),
    );
    expect(text).toContain("@ Newcastle United");
    expect(text).toContain("59%");
    expect(text).not.toMatch(/41%/);
  });

  test("CONTROL: a two-way sport still names the opponent's share", () => {
    const text = visibleText(
      render(
        {
          home_team: "Boston Red Sox",
          away_team: "Kansas City Royals",
          opponent: "Kansas City Royals",
          sport_key: "baseball_mlb",
          win_probability: 0.64,
        },
        "Boston Red Sox",
      ),
    );
    expect(text).toMatch(/Royals\s+36%/);
  });
});
