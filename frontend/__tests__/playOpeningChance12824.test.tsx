import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import CoolOrBoring from "@/app/play/CoolOrBoring";
import type { FeedItem } from "@/lib/types";

function game(source: "opening" | "blend", chance: number): FeedItem {
  const data = {
    id: 15184640,
    external_id: "bills-patriots-12824",
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    away_team: "Buffalo Bills",
    home_team: "New England Patriots",
    commence_time: new Date(Date.now() + 86_400_000).toISOString(),
    status: "scheduled" as const,
    home_score: null,
    away_score: null,
    hero_probability_source: source,
    current_odds: { home_probability: chance, away_probability: 1 - chance },
  };
  return {
    type: "event",
    reason: "",
    score: 50,
    headline: null,
    data,
  };
}

async function playCardText(item: FeedItem): Promise<string> {
  const host = document.createElement("div");
  const root = createRoot(host);
  const onAction = () => {};
  try {
    await act(async () => {
      root.render(
        <CoolOrBoring
          deck={[item]}
          playerName="Player"
          playerEmoji="🏈"
          initialRated={0}
          poolStatus="ready"
          hasMore={false}
          onRatedChange={onAction}
          onNeedMore={onAction}
          onRetry={onAction}
          onRefresh={onAction}
          onExit={onAction}
        />,
      );
    });
    return host.textContent ?? "";
  } finally {
    await act(async () => root.unmount());
  }
}

it("keeps the Play rating card without the cached opening chance", async () => {
  const text = await playCardText(game("opening", 0.58));
  expect(text).toContain("Buffalo Bills");
  expect(text).toContain("Cool or Boring?");
  expect(text).not.toContain("58%");
  expect(text).not.toContain("chance: New England Patriots");
});

it.each([0.58, 0])("still prints a genuine Play chance of %s", async (chance) => {
  const text = await playCardText(game("blend", chance));
  expect(text).toContain(`${Math.round(chance * 100)}%`);
  expect(text).toContain("chance: New England Patriots");
});
