"use client";

// L2-130 Event Concept Page — soccer tournament CONTAINER hero. The winner-field
// leaderboard answers "who wins the trophy"; this hero answers "what's the match
// right now" — the headliner (the live game if one is in play, else the soonest
// upcoming game) as a featured duel with a kickoff countdown. This is the
// is_major container treatment the World Cup page opens with (Lisa's "today's game
// probability in <10s" test). Suppressed when there's no live/upcoming game (a
// concluded tournament reads its champion from the leaderboard below).

import { headlinerMatchup } from "@/lib/eventConceptDisplay";
import type { EventConceptChild } from "@/lib/types";
import MatchupDuel from "./MatchupDuel";

export default function SoccerContainerHero({
  matchups,
}: {
  matchups: EventConceptChild[];
}) {
  const headliner = headlinerMatchup(matchups);
  if (!headliner) return null;
  const isLive = (headliner.status || "").toLowerCase() === "live";

  return (
    <section id="headliner" className="space-y-2">
      <h2 className="text-[11px] font-semibold uppercase tracking-widest text-text-muted">
        {isLive ? "Live now" : "Up next"}
      </h2>
      <MatchupDuel child={headliner} featured />
    </section>
  );
}
