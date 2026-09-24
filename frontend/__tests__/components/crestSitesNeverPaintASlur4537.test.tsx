/**
 * #4537 — the last two ux surfaces that could paint a blocked word as a crest.
 *
 * `teamCrestBadge` only refuses a blocked badge it would newly INTRODUCE (its
 * backstop reads `UNSHIPPABLE_BADGES.has(candidate) && !…has(shipped)`), so a
 * name whose shipped badge was already blocked still comes back blocked:
 * "Detroit Pistons" → "PIS", "Avispa Fukuoka" → "FUK". Two ux sites called it
 * bare (routed by discover, 2026-09-24, beside its own PR #8450):
 *
 *   - `components/PlayerPropsDashboard.tsx` — the Home/Away filter chips;
 *   - `app/events/[id]/opengraph-image.tsx` — the link-preview image, which has
 *     no logo branch at all, so every unfurl of such a game carried the word.
 *
 * Both now call `shippableCrestBadge`, the event hero's helper (#7270). The
 * share image is an edge `ImageResponse` (a PNG), so its half is the source
 * scan in `shareCardReaderWords4839.test.ts`; the chips are rendered here.
 *
 * Both directions (gotcha #43): a spoiled name loses the word; an ordinary
 * name keeps exactly the badge it had.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import { shippableCrestBadge, teamCrestBadge } from "../../lib/teamShortName";

const BLOCKED = new Set([
  "ASS", "FAG", "FUC", "FUK", "CUM", "COC", "COK", "CNT", "KKK",
  "NIG", "SHT", "TIT", "TWA", "WTF", "JIZ", "PIS", "SEX", "HOE",
]);

function row(outcome: string, team: "home" | "away") {
  return {
    market_name: "Props",
    outcome_name: outcome,
    threshold: 20.5,
    over_probability: 0.5,
    source: "polymarket",
    movement: null,
    actual: null,
    hit: null,
    is_winner: false,
    resolution_source: null,
    player_team: team,
  };
}

function chipLabels(homeTeam: string, awayTeam: string): string[] {
  const html = renderToStaticMarkup(
    <PlayerPropsDashboard
      data={
        {
          player_props: [
            row("Cade Cunningham: Points O/U 20.5", "home"),
            row("Jayson Tatum: Points O/U 20.5", "away"),
          ],
          other: [],
        } as unknown as GameMarketsResponse
      }
      eventStatus="scheduled"
      homeTeam={homeTeam}
      awayTeam={awayTeam}
      boxScore={null}
    />,
  );
  // The filter chips are the only buttons whose whole text is "All" or a badge.
  const labels = (html.match(/<button[^>]*>([^<]*)<\/button>/g) ?? []).map((b) =>
    b.replace(/<button[^>]*>/, "").replace(/<\/button>$/, ""),
  );
  const all = labels.indexOf("All");
  expect(all).toBeGreaterThanOrEqual(0);
  return labels.slice(all, all + 3);
}

describe("#4537 the player-props filter chips never paint a blocked word", () => {
  test("premise: the bare helper badges the Pistons with a blocked word", () => {
    expect(teamCrestBadge("Detroit Pistons")).toBe("PIS");
  });

  test("Detroit Pistons v Boston Celtics: the home chip is not 'PIS'", () => {
    const [all, home, away] = chipLabels("Detroit Pistons", "Boston Celtics");
    expect(all).toBe("All");
    expect(BLOCKED.has(home)).toBe(false);
    expect(home).toBe(shippableCrestBadge("Detroit Pistons"));
    expect(home).not.toBe("");
    // The ordinary side is untouched.
    expect(away).toBe(teamCrestBadge("Boston Celtics"));
  });

  test("control: an ordinary pair keeps exactly the badges it had", () => {
    const [, home, away] = chipLabels("Tampa Bay Rays", "Seattle Mariners");
    expect(home).toBe(teamCrestBadge("Tampa Bay Rays"));
    expect(away).toBe(teamCrestBadge("Seattle Mariners"));
  });
});

describe("#4537 neither ux crest site calls the bare helper", () => {
  const FILES = [
    ["components", "PlayerPropsDashboard.tsx"],
    ["app", "events", "[id]", "opengraph-image.tsx"],
  ];

  test.each(FILES)("%s/…%s", (...parts) => {
    const src = readFileSync(join(process.cwd(), ...parts), "utf8");
    expect(src.length).toBeGreaterThan(500);
    expect(src).toContain("shippableCrestBadge(");
    expect(src).not.toMatch(/\bteamCrestBadge\(/);
  });
});
