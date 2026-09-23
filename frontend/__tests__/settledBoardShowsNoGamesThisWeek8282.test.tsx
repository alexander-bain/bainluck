/**
 * #8282 — a settled market prints no "Games This Week".
 *
 * Specimen: production `GET /api/futures/114108/related-events` (Kings vs. Blue
 * Jackets, settled 2026-03-08), first row as served on 2026-09-23. The page
 * printed "Columbus Blue Jackets >99%" beside tomorrow's Penguins game.
 */
import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import GamesThisWeek from "@/components/futures/GamesThisWeek";
import type { RelatedEvent } from "@/lib/types";

const PENGUINS_AT_BLUE_JACKETS: RelatedEvent = {
  event_id: 15314262,
  home_team: "Columbus Blue Jackets",
  away_team: "Pittsburgh Penguins",
  commence_time: "2026-09-24T23:00:00+00:00",
  status: "scheduled",
  sport: "icehockey_nhl",
  home_score: null,
  away_score: null,
  linked_teams: [
    {
      side: "home",
      team_name: "Columbus Blue Jackets",
      outcome_name: "Kings",
      probability: 0.9995,
      american_odds: -199900,
      rank: 1,
    },
  ],
};

describe("#8282 GamesThisWeek on a settled market", () => {
  it("renders nothing when the market is resolved", () => {
    const html = renderToStaticMarkup(
      <GamesThisWeek events={[PENGUINS_AT_BLUE_JACKETS]} marketResolved />,
    );
    expect(html).toBe("");
  });

  it("still renders the same rows on an open market (control)", () => {
    const html = renderToStaticMarkup(
      <GamesThisWeek events={[PENGUINS_AT_BLUE_JACKETS]} marketResolved={false} />,
    );
    expect(html).toContain("Games This Week");
    expect(html).toContain("Pittsburgh Penguins");
    expect(html).toContain("&gt;99%");
  });

  it("defaults to open when the prop is absent (existing callers unchanged)", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={[PENGUINS_AT_BLUE_JACKETS]} />);
    expect(html).toContain("Games This Week");
  });

  it("the futures page passes its settled flag to the section", () => {
    const src = fs.readFileSync(
      path.join(__dirname, "..", "app", "futures", "[id]", "page.tsx"),
      "utf8",
    );
    const mounts = src.match(/<GamesThisWeek\b[^>]*\/>/g) ?? [];
    expect(mounts).toHaveLength(1);
    expect(mounts[0]).toContain("marketResolved={isResolved}");
    expect(src).toMatch(/const isResolved = market\.status === "resolved";/);
  });
});
