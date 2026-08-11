"use client";

import Link from "next/link";
import type { LeagueGameBrief } from "@/lib/api";
import { probabilityBarWidth } from "@/lib/entityPageChrome";

/**
 * The league page's games rails (UX-P062 / #1743, Alex's 2026-08-11 amendment).
 *
 * "League pages include an UPCOMING GAMES rail and a RECENT RESULTS rail — event
 * cards, the product's richest and freshest content."
 *
 * ── WHY THESE RENDER FROM THE LEAGUE ENVELOPE, NOT FROM THE FEED ──
 *
 * The page used to fetch `/api/feed?sport=…` for its games. The feed answers a
 * DIFFERENT question — "which games are interesting?" — and applies its own
 * scoring, pools and diversity caps. Since the tier census counts games (the
 * amendment), sourcing the render from the feed would let the backend count eight
 * games while the reader sees two: the broken shelf, arriving through the census
 * instead of the template. Same route declares the tier and supplies the rail.
 */

function scoreLine(game: LeagueGameBrief): string | null {
  if (game.home_score == null || game.away_score == null) return null;
  return `${game.away_score}–${game.home_score}`;
}

function timeLabel(game: LeagueGameBrief): string | null {
  if (!game.commence_time) return null;
  const d = new Date(game.commence_time);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function GameRow({ game, settled }: { game: LeagueGameBrief; settled: boolean }) {
  // Register E2 / doctrine A3: a null probability must not become a 0%-wide bar.
  // `probabilityBarWidth` returns null and we withhold the whole track — a
  // 0%-width bar inside a visible track is the same lie with extra steps.
  const width = probabilityBarWidth(game.home_win_probability);
  const score = scoreLine(game);
  const when = timeLabel(game);
  const isLive = game.status === "live";

  return (
    <Link
      href={`/events/${game.id}`}
      className="block rounded-xl border border-surface-border bg-surface-card p-3 hover:border-text-muted transition-colors"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-text-primary truncate">
          {game.away_team} @ {game.home_team}
        </span>
        {isLive ? (
          <span className="text-xs font-medium text-accent-live shrink-0">LIVE</span>
        ) : score ? (
          <span className="text-xs font-medium text-text-primary shrink-0">{score}</span>
        ) : when ? (
          <span className="text-xs text-text-muted shrink-0">{when}</span>
        ) : null}
      </div>

      {/* Settled means settled: a finished game shows its result, not a forecast. */}
      {!settled && width != null && (
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-surface-border overflow-hidden">
            <div className="h-full bg-accent-brand" style={{ width: `${width}%` }} />
          </div>
          <span className="text-xs text-text-secondary tabular-nums shrink-0">
            {width}%
          </span>
        </div>
      )}
    </Link>
  );
}

export default function LeagueGameRail({
  title,
  games,
  hasMore,
  settled = false,
  emptyStateName,
}: {
  title: string;
  games: LeagueGameBrief[];
  hasMore?: boolean;
  settled?: boolean;
  emptyStateName?: string;
}) {
  if (games.length === 0) {
    // Honest-empty is the PAGE's job (spec §6), not a per-rail "check back later".
    // A rail with nothing in it renders nothing at all.
    return emptyStateName ? (
      <div data-empty-state-name={emptyStateName} className="hidden" />
    ) : null;
  }

  return (
    <section data-section-key={settled ? "results" : "games"}>
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        {title}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {games.map((g) => (
          <GameRow key={g.id} game={g} settled={settled} />
        ))}
      </div>
      {/* A cap is always DECLARED (spec §4). An uncounted cap reads as coverage. */}
      {hasMore && (
        <p className="mt-2 text-xs text-text-muted">
          Showing the {games.length} most recent — more exist.
        </p>
      )}
    </section>
  );
}
