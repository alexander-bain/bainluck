/**
 * #2553 — a duel's price is one contest's price, so "Games This Week" on a duel
 * prints no number.
 *
 * Specimen: production `GET /api/futures/61226191/related-events` (Sabres vs.
 * Canadiens, `market_type: "duel"`), rows as served 2026-10-02 ~01:40Z. The page
 * printed "Buffalo Sabres 42%" — the Sabres' price to beat Montreal — beside the
 * live Sabres at Blue Jackets game and beside the Blackhawks game.
 */
import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import GamesThisWeek from "@/components/futures/GamesThisWeek";
import type { RelatedEvent } from "@/lib/types";

const SABRES_42 = {
  side: "away" as const,
  team_name: "Buffalo Sabres",
  outcome_name: "Sabres",
  probability: 0.42,
  american_odds: null,
  rank: null,
  outcome_is_team: true,
};

const SABRES_AT_BLUE_JACKETS: RelatedEvent = {
  event_id: 1,
  home_team: "Columbus Blue Jackets",
  away_team: "Buffalo Sabres",
  commence_time: "2026-10-01T23:00:00+00:00",
  status: "live",
  sport: "icehockey_nhl",
  home_score: null,
  away_score: null,
  linked_teams: [SABRES_42],
};

const BLACKHAWKS_AT_SABRES: RelatedEvent = {
  event_id: 2,
  home_team: "Buffalo Sabres",
  away_team: "Chicago Blackhawks",
  commence_time: "2026-10-03T23:00:00+00:00",
  status: "scheduled",
  sport: "icehockey_nhl",
  home_score: null,
  away_score: null,
  linked_teams: [{ ...SABRES_42, side: "home" }],
};

const ROWS = [SABRES_AT_BLUE_JACKETS, BLACKHAWKS_AT_SABRES];

describe("#2553 GamesThisWeek on a duel", () => {
  it("prints the fixtures and links but no price and no caption", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={ROWS} marketIsDuel />);
    expect(html).toContain("Games This Week");
    expect(html).toContain("Columbus Blue Jackets");
    expect(html).toContain("Chicago Blackhawks");
    expect(html).toContain('href="/events/1"');
    expect(html).toContain('href="/events/2"');
    expect(html).not.toMatch(/\d+%/);
    expect(html).not.toContain("in this market");
  });

  it("a field still prints each team's price under its caption (control)", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={ROWS} marketIsDuel={false} />);
    expect(html.match(/42%/g)).toHaveLength(2);
    expect(html).toContain("Each team&#x27;s odds in this market.");
  });

  it("defaults to a field when the prop is absent (existing callers unchanged)", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={ROWS} />);
    expect(html).toContain("42%");
  });

  it("the futures page passes the duel shape to the section", () => {
    const src = fs.readFileSync(
      path.join(__dirname, "..", "app", "futures", "[id]", "page.tsx"),
      "utf8",
    );
    const mounts = src.match(/<GamesThisWeek\b[^>]*\/>/g) ?? [];
    expect(mounts).toHaveLength(1);
    expect(mounts[0]).toContain("marketIsDuel={marketShape === SHAPE_DUEL}");
  });
});
