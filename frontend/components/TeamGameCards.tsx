"use client";

import Link from "next/link";
import type { TeamGameBrief } from "@/lib/api";
import { cn } from "@/lib/utils";
import { isGameLive, teamResult } from "@/lib/teamGames";

// ---------------------------------------------------------------------------
// Team-page game cards (L2-158). Extracted from the team page so the
// probability-first / result-first / chip-honesty logic is unit-testable via
// renderToStaticMarkup.
// ---------------------------------------------------------------------------

function GameNoChip({ n }: { n: number }) {
  return (
    <span className="text-[10px] font-semibold px-1 py-0.5 rounded bg-surface-elevated text-text-secondary">
      G{n}
    </span>
  );
}

/**
 * Probability-first card for scheduled/live games — the win-prob split is the
 * star (L2-158 Item 1). Chip honesty (L2-158 Item 2): a game is only LIVE once
 * it has actually started; a future commence_time renders "Starts <time>"
 * regardless of a premature backend 'live' status.
 */
export function UpcomingGameCard({
  game,
  teamName,
  teamColor,
  gameNo,
}: {
  game: TeamGameBrief;
  teamName: string;
  teamColor: string | null;
  gameNo?: number;
}) {
  const opponent = game.opponent || (game.is_home ? game.away_team : game.home_team);
  const live = isGameLive(game);
  const wp = game.win_probability; // team-relative, 0-1
  const teamPct = wp !== null && wp !== undefined ? Math.round(wp * 100) : null;
  const oppPct = teamPct !== null ? 100 - teamPct : null;
  const teamShort = teamName.split(" ").pop() || teamName;

  const teamScore = game.is_home ? game.home_score : game.away_score;
  const oppScore = game.is_home ? game.away_score : game.home_score;

  return (
    <Link
      href={`/events/${game.id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow block"
      style={
        teamColor
          ? { borderLeftWidth: 3, borderLeftColor: teamColor }
          : undefined
      }
    >
      {/* Top row: matchup + status */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="text-xs text-text-muted flex items-center gap-1.5 min-w-0">
          <span className="truncate">
            {game.is_home ? "vs" : "@"} {opponent}
          </span>
          {gameNo && <GameNoChip n={gameNo} />}
        </div>
        {live ? (
          <span className="flex items-center gap-1 text-accent-live font-semibold text-[11px] flex-shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
            LIVE
          </span>
        ) : (
          <span className="text-[11px] text-text-muted flex-shrink-0">
            {game.commence_time ? `Starts ${formatTime(game.commence_time)}` : "TBD"}
          </span>
        )}
      </div>

      {teamPct !== null ? (
        <>
          <div className="flex items-baseline justify-between">
            <span
              className="text-3xl font-mono font-bold"
              style={{ color: teamColor || undefined }}
            >
              {teamPct}%
            </span>
            {live && teamScore !== null && oppScore !== null && (
              <span className="font-mono text-sm font-bold text-accent-live">
                {teamScore}–{oppScore}
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-muted mb-2">win prob</div>
          {/* Split bar: team share vs opponent share */}
          <div className="h-2 rounded-full overflow-hidden flex bg-surface-elevated">
            <div
              className={teamColor ? "" : "bg-accent-brand"}
              style={{
                width: `${teamPct}%`,
                backgroundColor: teamColor || undefined,
              }}
            />
            <div className="bg-surface-border" style={{ width: `${oppPct}%` }} />
          </div>
          <div className="flex justify-between text-[11px] text-text-muted mt-1">
            <span className="truncate">{teamShort}</span>
            <span className="truncate ml-2">
              {opponent} {oppPct}%
            </span>
          </div>
        </>
      ) : (
        <div className="text-sm text-text-secondary">
          {game.commence_time ? formatTime(game.commence_time) : "TBD"}
        </div>
      )}
    </Link>
  );
}

/**
 * Result-first card for settled games (L2-158 Item 1). The result is the star
 * ("settled means settled"). "we had them at X%" + the upset flag render only
 * when the backend supplies a pre-game/closing probability — a settled game's
 * CURRENT win_probability is the frozen outcome, not a pre-game expectation, so
 * we do not label it as one. Backend gap filed (teams.py _format_event_brief:
 * add pregame_win_probability + completed_at; include 'closed' status in
 * recent_events). Renders both 'completed' AND 'closed' games.
 */
export function RecentGameCard({
  game,
  gameNo,
}: {
  game: TeamGameBrief;
  gameNo?: number;
}) {
  const opponent = game.opponent || (game.is_home ? game.away_team : game.home_team);
  const result = teamResult(game);
  const dateStr = formatSettledDate(game.completed_at || game.commence_time);

  const pre = game.pregame_win_probability;
  const teamWon = result?.char === "W";
  const upset = pre !== null && pre !== undefined && teamWon && pre < 0.35;

  return (
    <Link
      href={`/events/${game.id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow block"
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="text-xs text-text-muted flex items-center gap-1.5 min-w-0">
          <span className="truncate">
            {game.is_home ? "vs" : "@"} {opponent}
          </span>
          {gameNo && <GameNoChip n={gameNo} />}
        </div>
        {dateStr && (
          <span className="text-[11px] text-text-muted flex-shrink-0">{dateStr}</span>
        )}
      </div>

      <div className="flex items-baseline gap-2">
        {result ? (
          <>
            <span
              className={cn(
                "text-lg font-bold",
                result.char === "W"
                  ? "text-accent-live"
                  : result.char === "L"
                  ? "text-accent-danger"
                  : "text-text-secondary",
              )}
            >
              {result.char}
            </span>
            <span className="font-mono text-base font-semibold text-text-primary">
              {result.teamScore}–{result.oppScore}
            </span>
          </>
        ) : (
          <span className="text-sm text-text-secondary uppercase">Final</span>
        )}
      </div>

      {pre !== null && pre !== undefined && (
        <div className="text-xs mt-0.5">
          {upset ? (
            <span className="text-accent-brand font-medium">
              Upset — beat {Math.round((1 - pre) * 100)}% odds
            </span>
          ) : (
            <span className="text-text-muted">
              we had them at {Math.round(pre * 100)}%
            </span>
          )}
        </div>
      )}
    </Link>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffH = (d.getTime() - now.getTime()) / 3600000;

  if (diffH < 0) return "Recently";
  if (diffH < 1) return `In ${Math.round(diffH * 60)} min`;
  if (diffH < 24) {
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Settled-game date. Guards the impossible future-date-beside-Final state
// (gotcha #22/#46: completed/closed times can carry a stale/close timestamp).
function formatSettledDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  if (d.getTime() > now.getTime()) return "";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}
