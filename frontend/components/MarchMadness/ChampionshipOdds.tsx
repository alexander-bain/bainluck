"use client";

import type { MarchMadnessTeam } from "@/lib/types";

interface ChampionshipOddsProps {
  teams: MarchMadnessTeam[];
  almaMaterTeams: string[] | null;
}

export default function ChampionshipOdds({ teams, almaMaterTeams }: ChampionshipOddsProps) {
  if (!teams.length) return null;

  const almaMaterSet = new Set((almaMaterTeams || []).map(t => t.toLowerCase()));

  return (
    <div className="mm-section">
      <div className="mm-section-header">
        <h2 className="mm-section-title">Championship Odds</h2>
        <span className="mm-section-badge">
          {Object.keys(teams[0]?.sources || {}).length} sources
        </span>
      </div>
      <div className="mm-odds-grid">
        {teams.slice(0, 24).map((team, i) => {
          const isAlma = almaMaterSet.has(team.team_name.toLowerCase()) || team.is_alma_mater;
          return (
            <div key={team.team_name} className={`mm-team-card${isAlma ? " alma-mater" : ""}`}>
              <div className="mm-team-rank">{i + 1}</div>
              <div className="mm-team-info">
                <div className="mm-team-name">
                  {team.team_name}
                  {isAlma && <span style={{ marginLeft: 6, fontSize: "0.75rem", color: "var(--mm-gold)" }}>Your School</span>}
                </div>
                <div className="mm-team-meta">
                  {team.seed && <span className="mm-seed-badge">{team.seed}</span>}
                  {team.region && <span>{team.region}</span>}
                  {team.is_eliminated && <span style={{ color: "var(--mm-upset-red)" }}>Eliminated</span>}
                </div>
              </div>
              <div className="mm-team-prob">
                <div className="mm-prob-value">{(team.probability * 100).toFixed(1)}%</div>
                {team.movement_24h !== null && team.movement_24h !== 0 && (
                  <div className={`mm-prob-movement ${team.movement_24h > 0 ? "up" : "down"}`}>
                    {team.movement_24h > 0 ? "+" : ""}
                    {(team.movement_24h * 100).toFixed(1)}%
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
