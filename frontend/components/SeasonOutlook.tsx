"use client";

import Link from "next/link";

interface LeagueContextColumn {
  key: string;
  label: string;
}

interface TeamContext {
  cells: Record<string, number>;
  changes_24h: Record<string, number>;
  record?: string | null;
  conference?: string | null;
}

interface LeagueContextData {
  league_slug: string;
  league_name: string;
  columns: LeagueContextColumn[];
  league_page_url: string;
  home_team?: TeamContext;
  away_team?: TeamContext;
}

interface SeasonOutlookProps {
  leagueContext: LeagueContextData;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
}

function TeamRow({
  teamName,
  teamColor,
  context,
  columns,
}: {
  teamName: string;
  teamColor?: string;
  context: TeamContext;
  columns: LeagueContextColumn[];
}) {
  return (
    <div className="flex items-center gap-2 text-sm flex-wrap">
      <span
        className="font-semibold text-text-primary min-w-[100px] truncate"
        style={teamColor ? { color: teamColor } : undefined}
      >
        {teamName}
      </span>
      {context.record && (
        <span className="text-text-muted text-xs">({context.record})</span>
      )}
      <div className="flex items-center gap-1.5 flex-wrap">
        {columns.map((col) => {
          const prob = context.cells[col.key];
          if (prob == null) return null;
          const pct = Math.round(prob * 100);
          const change = context.changes_24h[col.key];
          return (
            <span
              key={col.key}
              className="inline-flex items-center gap-0.5 text-xs"
            >
              <span className="text-text-muted">{col.label}</span>
              <span className="font-semibold text-text-primary tabular-nums">
                {pct}%
              </span>
              {change != null && Math.abs(change) >= 0.005 && (
                <span
                  className={`text-[10px] tabular-nums ${
                    change > 0 ? "text-green-600" : "text-red-500"
                  }`}
                >
                  {change > 0 ? "+" : ""}
                  {Math.round(change * 100)}
                </span>
              )}
              <span className="text-surface-border mx-0.5">›</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default function SeasonOutlook({
  leagueContext,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
}: SeasonOutlookProps) {
  const { columns, league_page_url, home_team, away_team } = leagueContext;

  if (!home_team && !away_team) return null;

  return (
    <div className="border border-surface-border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          Season Outlook
        </h3>
        <Link
          href={league_page_url}
          className="text-xs text-accent-brand hover:underline"
        >
          Full grid →
        </Link>
      </div>
      {home_team && (
        <TeamRow
          teamName={homeTeam}
          teamColor={homeTeamColor}
          context={home_team}
          columns={columns}
        />
      )}
      {away_team && (
        <TeamRow
          teamName={awayTeam}
          teamColor={awayTeamColor}
          context={away_team}
          columns={columns}
        />
      )}
    </div>
  );
}
