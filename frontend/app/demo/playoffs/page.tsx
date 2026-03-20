"use client";

/**
 * /demo/playoffs — Preview page for TeamPlayoffCard + ChampionshipGrid
 *
 * Shows:
 *  1. Two TeamPlayoffCards side-by-side (OKC vs CLE, simulating an event detail page)
 *  2. Full ChampionshipGrid with all mock NBA teams
 */

import { useState, Component } from "react";
import type { ReactNode } from "react";
import TeamPlayoffCard from "@/components/TeamPlayoffCard";
import ChampionshipGrid from "@/components/ChampionshipGrid";
import { MOCK_TEAMS, NBA_GRID, LEAGUE_TABS } from "@/lib/playoff-mock-data";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-4 rounded-lg m-4" style={{ backgroundColor: "#1C0A0A", border: "1px solid #EF4444" }}>
          <p className="text-sm font-semibold" style={{ color: "#EF4444" }}>Render error</p>
          <pre className="text-xs mt-2 whitespace-pre-wrap" style={{ color: "#94A3B8" }}>
            {this.state.error.message}
            {"\n"}
            {this.state.error.stack?.split("\n").slice(0, 5).join("\n")}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function PlayoffsDemoPage() {
  const [activeLeague, setActiveLeague] = useState("nba");

  // Pick two teams for the event-detail pair (OKC + CLE)
  const teamA = MOCK_TEAMS.find((t) => t.short === "OKC")!;
  const teamB = MOCK_TEAMS.find((t) => t.short === "CLE")!;

  return (
    <ErrorBoundary>
    <div className="max-w-2xl mx-auto py-6 px-4 space-y-10">
      {/* ── Section 1: Event Detail Card Pair ── */}
      <section>
        <div className="mb-3">
          <h2
            className="text-[11px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Event Detail
          </h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
            Championship probability funnel for both teams in a matchup.
          </p>
        </div>

        {/* Match header */}
        <div
          className="rounded-xl border px-4 py-3 mb-3 flex items-center gap-2"
          style={{
            backgroundColor: "var(--surface-elevated)",
            borderColor: "var(--surface-border)",
          }}
        >
          <span className="text-base">🏀</span>
          <span
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {teamA.name}
          </span>
          <span
            className="text-xs font-mono px-2"
            style={{ color: "var(--text-muted)" }}
          >
            vs
          </span>
          <span
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {teamB.name}
          </span>
          <span
            className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: "rgba(34,197,94,0.12)",
              color: "#22C55E",
            }}
          >
            LIVE · Q3 4:32
          </span>
        </div>

        {/* Two TeamPlayoffCards stacked */}
        <div className="space-y-2">
          <TeamPlayoffCard team={teamA} gridHref="/playoffs/nba" />
          <TeamPlayoffCard team={teamB} gridHref="/playoffs/nba" />
        </div>

        {/* Explanation note */}
        <p
          className="text-[10px] mt-2 text-center"
          style={{ color: "var(--text-muted)" }}
        >
          Tap a card to navigate to the full championship grid.
        </p>
      </section>

      {/* Divider */}
      <div style={{ borderTop: "1px solid var(--surface-border)" }} />

      {/* ── Section 2: Championship Grid ── */}
      <section>
        <div className="mb-3">
          <h2
            className="text-[11px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Championship Grid
          </h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
            Mobile-first leaderboard. Select a stage to re-rank all teams.
            Tap a team row to expand its full funnel.
          </p>
        </div>

        <ChampionshipGrid
          data={NBA_GRID}
          leagueTabs={LEAGUE_TABS}
          activeLeagueSlug={activeLeague}
          onLeagueChange={setActiveLeague}
          gridHref="/playoffs/nba"
        />
      </section>
    </div>
    </ErrorBoundary>
  );
}
