"use client";

import { useMemo, useState } from "react";
import type { GameMarketsResponse } from "@/lib/api";
import { isGraded, SETTLED_NO_GRADE_LABEL } from "@/lib/propGrade";
import {
  groupPlayerProps,
  type PlayerData,
  type PlayerStat,
} from "@/lib/playerPropsGrouping";
import SectionErrorBoundary from "./SectionErrorBoundary";

interface PlayerPropsDashboardProps {
  data: GameMarketsResponse;
  eventStatus?: string;
  homeTeam?: string;
  awayTeam?: string;
  homeColor?: string;
  awayColor?: string;
  boxScore?: { players?: Array<{ name: string; team: string; stats: Record<string, number> }> } | null;
}

function SourceDot({ count }: { count: number }) {
  if (count <= 1) return null;
  return (
    <span
      className="text-[10px] font-semibold text-blue-600 bg-blue-500/10 rounded-full w-4 h-4 grid place-items-center"
      title={`${count} sources`}
    >
      {count}
    </span>
  );
}

function StatBox({
  stat,
  gameState,
  teamColor,
}: {
  stat: PlayerStat;
  gameState: "pre" | "live" | "done" | "settled";
  teamColor: string;
}) {
  const accent = teamColor;
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  // Settled game. Queue #190 Item 3: prefer the authoritative server-side grade
  // (actual stat + hit/miss) from the game-markets payload. Only fall back to
  // "grading unavailable" when the server published no grade at all — a resolved
  // market's over_probability collapses to ~100%/0% and would read as a fake
  // grade (L2-112 Item 3).
  //
  // UX-P040 (#1638): the fallback used to be UNREACHABLE, because the test was
  // `is_winner != null` and `is_winner` is a non-nullable column defaulted to
  // false. Every never-graded prop therefore rendered a red MISS.
  //
  // UX-P044 (#1642): `readPropGrade` is now the ONLY thing that decides. Two
  // routes around it were removed here:
  //   - `firstRung?.hit` used to override the group verdict, which is what made
  //     a ladder whose rungs DISAGREE render whichever rung sorted first (7 of
  //     358 measured production cards). The group badge is now the module's.
  //   - `serverActual` / `stat.actual` no longer top up a withheld grade;
  //     `stat.actual` is the BOX-SCORE number, and pairing it with a verdict the
  //     backend never typed is the client adjudicating (ruling 003).
  if (gameState === "settled") {
    const firstRung =
      stat.shape === "ladder" && stat.rungs && stat.rungs.length > 0
        ? stat.rungs[0]
        : null;
    const firstLine = firstRung ? firstRung.threshold : stat.threshold;
    const grade = stat.grade ?? { state: "WITHHOLD" as const, reason: "no_typed_grade" as const, hit: null, actual: null };
    const graded = grade.state !== "WITHHOLD";
    const gradeActual = graded ? grade.actual : null;
    const hitBool: boolean | null = graded ? grade.hit : null;

    if (graded) {
      const didHit = hitBool === true;
      // No stated verdict → neutral, never the red that reads as "missed".
      const accentColor = hitBool == null ? undefined : didHit ? accent : "#EF4444";
      return (
        <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
            <SourceDot count={stat.sources} />
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <div className="font-mono tabular-nums text-2xl font-bold" style={{ color: accentColor }}>
              {gradeActual != null ? gradeActual : (didHit ? "✓" : "—")}
            </div>
            {firstLine != null && (
              <div className="font-mono tabular-nums text-xs text-text-muted">of {firstLine}</div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* UX-P040: a verdict only when the backend stated one. A grade that
                carries an `actual` but no hit/miss shows the number and stops —
                deriving the verdict from `actual >= threshold` here would be the
                client adjudicating (ruling 003). */}
            {hitBool != null && (
              <span
                className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
                style={didHit ? { background: `${accent}22`, color: accent } : { background: "rgba(239,68,68,0.15)", color: "#EF4444" }}
              >
                {didHit ? "HIT" : "MISS"}
              </span>
            )}
            {firstLine != null && (
              <span className="text-xs text-text-muted font-mono tabular-nums">needed {firstLine}+</span>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        <div className="flex items-baseline gap-2 mb-1.5">
          <div className="font-mono tabular-nums text-lg font-bold text-text-primary">
            {firstLine != null ? `${firstLine}+` : "—"}
          </div>
          <div className="text-xs text-text-muted">line</div>
        </div>
        {/* #1650: ONE settled-state phrase, imported rather than restated, so
            this chip and the WHAT HIT row cannot describe one state two ways. */}
        <span className="text-[10px] font-medium text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded">
          {SETTLED_NO_GRADE_LABEL}
        </span>
      </div>
    );
  }

  if (stat.shape === "ladder" && stat.rungs) {
    const actual = stat.actual ?? 0;
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        {gameState !== "pre" ? (
          <div className="flex items-baseline gap-2 mb-1.5">
            <div className="font-mono tabular-nums text-2xl font-bold">{actual}</div>
            <div className="text-xs text-text-muted">so far</div>
          </div>
        ) : (
          <div className="text-[10px] text-text-muted mb-1.5">chance of hitting</div>
        )}
        <div className="space-y-1 mt-0.5">
          {stat.rungs.map((r) => {
            const hit = gameState !== "pre" && actual >= r.threshold;
            const prob = gameState === "done" ? (hit ? 1 : 0) : r.overProb;
            const fillStyle = gameState === "done" && !hit ? "rgba(156,163,175,0.3)" : `${accent}${hit ? "" : "AA"}`;
            return (
              <div key={r.threshold} className="flex items-center gap-2">
                <div
                  className={`font-mono tabular-nums text-xs w-8 ${hit ? "font-semibold" : "text-text-secondary"}`}
                  style={hit ? { color: accent } : undefined}
                >
                  {r.threshold}+
                </div>
                <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${prob * 100}%`, background: fillStyle }}
                  />
                </div>
                <div
                  className={`font-mono tabular-nums text-xs w-10 text-right ${hit ? "font-semibold" : "text-text-primary"}`}
                  style={hit ? { color: accent } : undefined}
                >
                  {gameState === "done" ? (hit ? "\u2713" : "\u2014") : pct(prob)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Line shape (single threshold O/U)
  const overThreshold = stat.actual != null && stat.threshold != null && stat.actual > stat.threshold;

  if (gameState === "pre") {
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <div className="font-mono tabular-nums text-2xl font-bold text-text-primary">{stat.threshold}+</div>
          <div className="text-xs text-text-muted">threshold</div>
        </div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] text-text-muted">Pre-game odds</div>
          {stat.movement != null && Math.abs(stat.movement) >= 0.01 && (
            <div className={`text-[10px] font-mono tabular-nums ${stat.movement > 0 ? "text-accent-brand" : "text-accent-danger"}`}>
              {stat.movement >= 0 ? "\u2191" : "\u2193"}{Math.round(Math.abs(stat.movement) * 100)}% 24h
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${(stat.overProb ?? 0) * 100}%`, background: accent }} />
          </div>
          <div className="font-mono tabular-nums text-xs font-semibold w-10 text-right">{pct(stat.overProb ?? 0)}</div>
        </div>
      </div>
    );
  }

  if (gameState === "live") {
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <div className="font-mono tabular-nums text-2xl font-bold">{stat.actual ?? 0}</div>
          <div className="text-xs text-text-muted">of {stat.threshold} so far</div>
        </div>
        <div className="space-y-1.5">
          <div className="grid grid-cols-[44px_1fr_36px] items-center gap-2">
            <div className="text-[10px] text-text-muted">Pre</div>
            <div className="h-1.5 rounded-full bg-surface-border overflow-hidden">
              <div className="h-full bg-text-muted/60 transition-all duration-500" style={{ width: `${(stat.overProb ?? 0) * 100}%` }} />
            </div>
            <div className="font-mono tabular-nums text-[11px] text-right">{pct(stat.overProb ?? 0)}</div>
          </div>
        </div>
      </div>
    );
  }

  // Done
  const hit = overThreshold;
  return (
    <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
        <SourceDot count={stat.sources} />
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <div className="font-mono tabular-nums text-2xl font-bold" style={{ color: hit ? accent : "#EF4444" }}>
          {stat.actual ?? 0}
        </div>
        <div className="font-mono tabular-nums text-xs text-text-muted">of {stat.threshold}</div>
      </div>
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
          style={hit ? { background: `${accent}22`, color: accent } : { background: "rgba(239,68,68,0.15)", color: "#EF4444" }}
        >
          {hit ? "HIGHER" : "LOWER"}
        </span>
        <span className="text-xs text-text-muted font-mono tabular-nums">
          by {Math.abs((stat.actual ?? 0) - (stat.threshold ?? 0)).toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function PlayerCard({ player, gameState, showAllStats }: { player: PlayerData; gameState: "pre" | "live" | "done" | "settled"; showAllStats: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const isExpanded = showAllStats || expanded;
  const pointsStats = player.stats.filter((s) => /^points?$/i.test(s.type));
  const otherStats = player.stats.filter((s) => !/^points?$/i.test(s.type));
  const visibleStats = isExpanded ? player.stats : pointsStats;
  const statsToShow = visibleStats.length > 0 ? visibleStats : player.stats.slice(0, 1);
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-4 flex flex-col">
      <div className="flex items-center gap-3 mb-3">
        {player.headshot ? (
          <img
            src={player.headshot}
            alt={player.name}
            loading="eager"
            fetchPriority="high"
            className="w-11 h-11 rounded-full object-cover shrink-0"
            style={{ backgroundColor: player.color }}
          />
        ) : (
          <div
            className="w-11 h-11 rounded-full grid place-items-center font-mono font-bold text-white shrink-0"
            style={{ background: player.color }}
          >
            {player.initials}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">{player.name}</div>
          <div className="text-xs text-text-muted font-mono">{player.team === "home" ? "Home" : player.team === "away" ? "Away" : ""}</div>
        </div>
        {gameState === "live" && (
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-live/15 text-accent-live flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-accent-live animate-pulse" />
            LIVE
          </span>
        )}
      </div>
      <div className={`grid gap-2 ${statsToShow.length >= 3 ? "grid-cols-2" : "grid-cols-1"}`}>
        {statsToShow.map((s) => (
          <StatBox key={s.type} stat={s} gameState={gameState} teamColor={player.color} />
        ))}
      </div>
      {!isExpanded && otherStats.length > 0 && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 text-[11px] font-medium text-blue-600 hover:text-blue-700 transition-colors text-left"
        >
          +{otherStats.length} more stat{otherStats.length > 1 ? "s" : ""} (rebounds, assists, 3PT...)
        </button>
      )}
      {expanded && !showAllStats && otherStats.length > 0 && (
        <button
          onClick={() => setExpanded(false)}
          className="mt-1 text-[10px] text-text-muted hover:text-text-secondary transition-colors text-left"
        >
          Show less
        </button>
      )}
    </div>
  );
}

export default function PlayerPropsDashboard({
  data,
  eventStatus,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  boxScore,
}: PlayerPropsDashboardProps) {
  const [teamFilter, setTeamFilter] = useState<"all" | "home" | "away">("all");
  const [showAllStats, setShowAllStats] = useState(false);

  const hasBoxScore = boxScore?.players != null && boxScore.players.length > 0;
  const isSettled = eventStatus === "completed" || eventStatus === "closed";
  // L2-112 Item 3: a settled game with no box score can't be graded client-side
  // (the game-markets payload carries no actual/is_winner field — see report).
  // It must NOT fall through to "pre", which renders the resolved over_probability
  // as a misleading 100%/0% bar. "settled" → honest line-only fallback.
  const gameState: "pre" | "live" | "done" | "settled" =
    eventStatus === "live" ? "live" :
    isSettled && hasBoxScore ? "done" :
    isSettled ? "settled" : "pre";

  // UX-P056 — the grouping moved to `lib/playerPropsGrouping.ts`, GUARDED per
  // item (gotcha #42). It used to live here as ~150 lines of inline loops over
  // free text, which meant two things: a throw anywhere in it removed ALL
  // seventeen players (cycle 55 reduced that from the whole page to the whole
  // section, and no further), and it could not be tested at all — there is no
  // jsdom here, so the only way to exercise it was to render the component.
  //
  // A per-CARD boundary, which is what was ranked next after cycle 55, would
  // NOT have caught #1722: that throw happened HERE, before any card existed.
  //
  // `dropped` is deliberately surfaced rather than swallowed — see below.
  const { players, dropped, emptyReason } = useMemo(
    () =>
      groupPlayerProps({
        playerProps: data.player_props,
        other: data.other,
        homeTeam,
        awayTeam,
        homeColor,
        awayColor,
        // Dead by design (ruling 003) — `box_score_data.players` is a dict, so
        // the caller's `hasBoxScore` is false and this is always empty. Passed
        // through so the module keeps the caller's shape, not to switch it on.
        boxScorePlayers: hasBoxScore ? boxScore?.players : null,
      }),
    // UX-P055 (#1722 follow-up): `data.other` was MISSING here while the body
    // reads it twice (the `hasOtherProps` early return, and the "scan other
    // markets" pass). On a polling surface that means a stale card: when a
    // refetch changes only `other`, the memo hands back the previous result.
    [data.player_props, data.other, homeTeam, awayTeam, homeColor, awayColor, boxScore, hasBoxScore],
  );

  // UX-P058 Item 2 (C277) — an empty section states WHICH empty it is.
  //
  // This was `if (players.length === 0) return null`, which drew nothing whether
  // the game had no props or every prop it had failed to parse. The
  // "N props couldn't be read" line below was written for exactly the second
  // case and sat AFTER this return, so it was unreachable there.
  //
  // Gotcha #53 in the client: an empty is not an absence. A poisoned section
  // rendering as a clean absence is the worst of the three states — the surface
  // asserts "this game has no player props", which is a claim about the WORLD
  // made from a fact about our parsing.
  //
  // Bounded on purpose: a fixed one-line notice, no row list, no error text, no
  // retry. The section says it could not read this and stops. It never grows to
  // fill the space the cards would have taken.
  if (players.length === 0) {
    if (emptyReason !== "unreadable") return null;
    return (
      <div>
        <h3 className="text-lg font-semibold tracking-tight">Player Props</h3>
        <p className="text-[11px] text-text-muted mt-0.5">
          Player props couldn&apos;t be read for this game.
        </p>
      </div>
    );
  }

  const filtered = teamFilter === "all" ? players : players.filter((p) => p.team === teamFilter || p.team === "unknown");
  const totalProps = players.reduce((a, p) => a + p.stats.length, 0);
  // Queue #190 Item 3: is any settled prop graded server-side? If so, drop the
  // blanket "grading unavailable" subtitle.
  // UX-P040 (#1638): this asked `serverIsWinner != null` too, so a game with zero
  // published grades advertised "Final · graded results" over a grid of red MISSes.
  const anyGraded = players.some((p) =>
    p.stats.some((s) => s.grade != null && isGraded(s.grade)),
  );
  // L2-52: source-name attribution removed (blend-only).

  const homeShortCode = homeTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "HOME";
  const awayShortCode = awayTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "AWAY";

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Player Props</h3>
          {gameState === "settled" && (
            <p className="text-[11px] text-text-muted mt-0.5">
              {anyGraded ? "Final · graded results" : "Final · per-player grading unavailable for this game"}
            </p>
          )}
          {/* UX-P056 — say so when a guard fired. A per-item guard that drops
              silently turns "we could not read this" into "there is nothing
              here", which is the same lie the section fallback exists to avoid.
              Empty on every production payload measured, so this renders on no
              card today (gotcha #43). */}
          {dropped.length > 0 && (
            <p className="text-[11px] text-text-muted mt-0.5">
              {dropped.length} {dropped.length === 1 ? "prop" : "props"} couldn&apos;t be read.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAllStats((s) => !s)}
            className="text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
          >
            {showAllStats ? "Points only" : "All stats"}
          </button>
          {/* L2-52: source-name pill removed (blend-only). */}
          <div className="flex bg-surface-card rounded-lg border border-surface-border p-0.5">
            {(["all", "home", "away"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setTeamFilter(f)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  teamFilter === f ? "bg-text-primary text-white" : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {f === "all" ? "All" : f === "home" ? homeShortCode : awayShortCode}
              </button>
            ))}
          </div>
        </div>
      </div>


      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        {/* UX-P056 — the render half of the same rule. The grouping above is
            guarded per player; this guards the RENDER per player, so a throw
            inside one card costs that card and its seventeen neighbours stay up.
            A DELEGATION, not a second boundary (the #1717 shape): ErrorBoundary
            remains the only class that catches. `resetKey` is the player's own
            data, so a transient bad payload on this 32s-polling page does not
            latch one card dead for the rest of the session (UX-P055's find). */}
        {filtered.map((p) => (
          <SectionErrorBoundary key={p.name} label={p.name} resetKey={p}>
            <PlayerCard player={p} gameState={gameState} showAllStats={showAllStats} />
          </SectionErrorBoundary>
        ))}
      </div>
    </div>
  );
}
