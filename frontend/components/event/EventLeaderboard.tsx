"use client";

// #999 L2-64 Event Concept Page — winner-field leaderboard. One row per
// competitor: rank, optional seed, a live-state chip, a probability bar, an
// optional sparkline (real history only), the big probability %, and 24h
// movement. Probability-only, no source names, light tokens.

import { formatProbability } from "@/lib/api";
import {
  fieldOrder,
  settledChampion,
  competitorMovement,
  formatMovement,
  seriesForName,
  seriesFromCompetitor,
  partitionWinnerField,
  isEliminatedCompetitor,
} from "@/lib/eventConceptDisplay";
import type { EventConceptCompetitor, FuturesOutcomeHistory } from "@/lib/types";
import Sparkline from "./Sparkline";
import FreshnessChip from "./FreshnessChip";
import { TeamCrest } from "./MatchupDuel";

interface EventLeaderboardProps {
  competitors: EventConceptCompetitor[];
  label: string;
  /** Shared history from the evolution market — powers per-row sparklines. */
  historyOutcomes?: FuturesOutcomeHistory[];
  /** Tweak: hide sparklines even when history is present. */
  showSparkline?: boolean;
  limit?: number;
  /** Rank 1 gets a "Leader" chip when the event is live. */
  live?: boolean;
  /** L2-81: the event has concluded — render the champion as "Won" (no stale %). */
  settled?: boolean;
  /** L2-66: freshness stamp — drives the "as of" chip in golf live mode. */
  asOf?: string | null;
}

/** Score-to-par display: E / -N / +N. */
function fmtToPar(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n === 0) return "E";
  return n > 0 ? `+${n}` : `${n}`;
}

/** Thru display: "F" (finished), "H12" (hole), "—" for not-yet-started
 *  (null/"0" — later tee times in round 1), else the raw string. */
function fmtThru(t: string | null | undefined): string {
  if (!t || t === "0") return "—";
  if (t.toUpperCase() === "F") return "F";
  return /^\d+$/.test(t) ? `H${t}` : t;
}

const CUT_STATUSES = new Set(["cut", "mc", "wd", "w/d", "dq", "dnf", "dns", "mdf"]);

/** L2-68: a player who missed the cut / withdrew / was DQ'd — DataGolf reports
 *  these as a status string in `position`. They must NOT sort mid-field by a stale
 *  score; they sink into a collapsed "Missed cut" group. Honest — only real status
 *  strings count, never a fabricated position. */
function isCutStatus(position: string | null | undefined): boolean {
  if (!position) return false;
  return CUT_STATUSES.has(position.trim().toLowerCase().replace(/\s+/g, ""));
}

/** Chip label for a cut player (normalized). */
function cutLabel(position: string | null | undefined): string {
  const p = (position || "CUT").trim().toUpperCase().replace(/\s+/g, "");
  return p === "W/D" ? "WD" : p;
}

/** One golf-live leaderboard row (active or cut). Cut rows are dimmed, show a
 *  status chip instead of a hole, and no win% (they can't win). */
function GolfRow({
  c,
  index,
  cut = false,
}: {
  c: EventConceptCompetitor;
  index: number;
  cut?: boolean;
}) {
  // L2-69: prefer the true in-play win-prob delta ("who's charging"); it's in
  // POINTS, so pass /100 through the shared points formatter. Fall back to the 24h
  // move (which is null during live play → no chip). Cut rows show no delta.
  const mv = cut
    ? null
    : c.prob_delta_live != null
      ? formatMovement(c.prob_delta_live / 100)
      : formatMovement(competitorMovement(c));
  const toPar = c.score_to_par;
  const parClass =
    toPar == null ? "text-text-muted" : toPar < 0 ? "text-accent-brand" : "text-text-primary";
  return (
    <div className={`flex items-center gap-2 py-2 text-sm ${cut ? "opacity-70" : ""}`}>
      <span className="w-8 shrink-0 font-mono text-xs text-text-secondary tabular-nums">
        {cut ? (
          <span className="text-[9px] font-semibold uppercase tracking-wide px-1 py-0.5 rounded bg-text-muted/15 text-text-secondary">
            {cutLabel(c.position)}
          </span>
        ) : (
          c.position || index + 1
        )}
      </span>
      <span className="flex-1 min-w-0 truncate text-text-primary">{c.name}</span>
      <span className={`w-12 text-right shrink-0 font-mono tabular-nums ${parClass}`}>
        {fmtToPar(toPar)}
      </span>
      <span className="w-12 text-right shrink-0 font-mono text-xs text-text-secondary tabular-nums">
        {cut ? "—" : fmtThru(c.thru)}
      </span>
      <span className="w-20 text-right shrink-0 flex items-baseline justify-end gap-1">
        {mv && (
          <span
            className={`font-mono text-[10px] tabular-nums ${
              mv.dir === "up" ? "text-accent-brand" : "text-accent-danger"
            }`}
          >
            {mv.dir === "up" ? "▲" : "▼"}
            {mv.text.replace(/^[+−]/, "")}
          </span>
        )}
        <span className="font-mono font-semibold text-text-primary tabular-nums">
          {cut ? "—" : formatProbability(c.probability)}
        </span>
      </span>
    </div>
  );
}

/** One winner-field leaderboard row (live/upcoming).
 *  - Contenders: green probability bar + big %.
 *  - `out` (adapter-eliminated): NO green (true-0 empty track), an "OUT" chip,
 *    muted, and never a stale live % (reads 0%).
 *  - zero-probability longshots (dimmed, no chip): honest "0%" with a true-0 bar.
 *  A 0% row NEVER shows a min-width green stub — true 0 reads as empty (L2-132). */
function WinnerFieldRow({
  c,
  rank,
  anyCrest,
  live,
  showSparkline,
  historyOutcomes,
  out,
}: {
  c: EventConceptCompetitor;
  rank: number;
  anyCrest: boolean;
  live: boolean;
  showSparkline: boolean;
  historyOutcomes?: FuturesOutcomeHistory[];
  out: boolean;
}) {
  const seed = (c as Record<string, unknown>).seed;
  const pct = c.probability != null ? Math.round(c.probability * 100) : null;
  const zero = pct === 0; // rounds to 0% — a longshot / eliminated row
  const dim = out || zero;
  // Dead/zero rows carry no movement/sparkline — there is no live story to tell.
  const mv = dim ? null : formatMovement(competitorMovement(c));
  const ownSeries = showSparkline && !dim ? seriesFromCompetitor(c) : [];
  const series =
    !showSparkline || dim
      ? []
      : ownSeries.length >= 2
        ? ownSeries
        : seriesForName(historyOutcomes, c.name);
  return (
    <div
      className={`flex items-center gap-3 py-2 border-b border-surface-border/40 last:border-0 ${
        dim ? "opacity-55" : ""
      }`}
    >
      {/* Rank */}
      <span className="text-text-muted font-mono text-xs w-5 text-right tabular-nums shrink-0">
        {rank}
      </span>

      {/* Team crest (soccer) — reserved slot so rows stay aligned. */}
      {anyCrest &&
        (c.team ? (
          <TeamCrest side={c.team} size={22} />
        ) : (
          <span className="shrink-0" style={{ width: 22, height: 22 }} />
        ))}

      {/* Name + chips + bar */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm text-text-primary truncate">{c.name}</span>
          {typeof seed === "number" && (
            <span className="text-[10px] text-text-muted font-mono shrink-0">
              #{seed}
            </span>
          )}
          {out ? (
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1 py-0.5 rounded bg-text-muted/15 text-text-secondary shrink-0">
              Out
            </span>
          ) : (
            live &&
            rank === 1 && (
              <span className="text-[10px] font-semibold uppercase tracking-wide px-1 py-0.5 rounded bg-accent-live/15 text-accent-live shrink-0">
                Leader
              </span>
            )
          )}
        </div>
        {/* Bar track. A real contender shows a green fill; a 0% row (longshot or
            OUT) shows a true-0 empty track — never a min-width green stub. */}
        {(pct != null || out) && (
          <div className="mt-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
            {!out && pct != null && pct >= 1 && (
              <div
                className="h-full rounded-full bg-accent-brand"
                style={{ width: `${Math.max(2, pct)}%` }}
              />
            )}
          </div>
        )}
      </div>

      {/* Sparkline (real history only) */}
      {series.length >= 2 && (
        <div className="hidden sm:block shrink-0">
          <Sparkline series={series} />
        </div>
      )}

      {/* 24h movement */}
      {mv && (
        <span
          className={`font-mono text-[11px] tabular-nums shrink-0 w-12 text-right ${
            mv.dir === "up" ? "text-accent-brand" : "text-accent-danger"
          }`}
        >
          {mv.dir === "up" ? "▲" : "▼"}
          {mv.text}
        </span>
      )}

      {/* Big probability — OUT rows never show a stale live % (reads 0%). */}
      <span className="font-mono text-base font-semibold text-text-primary tabular-nums shrink-0 w-14 text-right">
        {formatProbability(out ? 0 : c.probability)}
      </span>
    </div>
  );
}

export default function EventLeaderboard({
  competitors,
  label,
  historyOutcomes,
  showSparkline = true,
  limit = 20,
  live = false,
  settled = false,
  asOf = null,
}: EventLeaderboardProps) {
  // L2-81 settled winner-field: once the event concludes, showing a normalized
  // field ("champion 30%, runner-up 25%") reads as a live prediction and is
  // dishonest. Render the champion with a "Won" chip and NO stale percentages;
  // collapse the rest into a dimmed "Did not win" list (mirrors the L2-53 futures
  // detail ruling + the completed-matchups grouping). Applies to any winner-field
  // domain (tennis slam, golf tournament, F1 race).
  if (settled) {
    const ranked = fieldOrder(competitors);
    if (ranked.length === 0) return null;
    const champion = settledChampion(competitors);
    const others = ranked.filter((c) => c !== champion).slice(0, limit);
    return (
      <section id="leaderboard" className="bg-surface-card rounded-card shadow-card p-6">
        <h2 className="text-title-3 font-semibold text-text-primary mb-4">
          {champion ? "Final result" : label || "Final standings"}
        </h2>
        {champion ? (
          <div className="flex items-center gap-3 py-1">
            <span aria-hidden className="text-xl shrink-0">
              🏆
            </span>
            {champion.team && <TeamCrest side={champion.team} size={28} />}
            <span className="flex-1 min-w-0 truncate text-base font-semibold text-text-primary">
              {champion.name}
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded bg-accent-brand/15 text-accent-brand shrink-0">
              Won
            </span>
          </div>
        ) : (
          <p className="text-sm text-text-secondary">Awaiting the final result.</p>
        )}
        {others.length > 0 && (
          <details className="mt-3">
            <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
              {champion ? `Did not win (${others.length})` : `Field (${others.length})`}
            </summary>
            <div className="divide-y divide-surface-border/40 mt-2">
              {others.map((c, i) => (
                <div
                  key={`${c.name}-${i}`}
                  className="flex items-center gap-3 py-2 opacity-70"
                >
                  <span className="text-text-muted font-mono text-xs w-5 text-right tabular-nums shrink-0">
                    {i + 1}
                  </span>
                  <span className="flex-1 min-w-0 truncate text-sm text-text-secondary">
                    {c.name}
                  </span>
                </div>
              ))}
            </div>
          </details>
        )}
      </section>
    );
  }

  // L2-66 golf live mode: when live competitors carry a leaderboard position/thru,
  // render the fused row (position · name · to-par · thru · win% · Δ) and order by
  // score-to-par (a real leaderboard), not win%.
  const golfLive =
    live && competitors.some((c) => c.thru != null || c.position != null);

  if (golfLive) {
    // Order by score-to-par (real leaderboard), win% as tiebreak. L2-68: cut/MC/WD
    // players sink into a collapsed "Missed cut" group instead of sorting mid-field
    // on a stale score.
    const sorted = [...competitors].sort((a, b) => {
      const sa = a.score_to_par ?? Number.POSITIVE_INFINITY;
      const sb = b.score_to_par ?? Number.POSITIVE_INFINITY;
      if (sa !== sb) return sa - sb;
      return (b.probability ?? -1) - (a.probability ?? -1);
    });
    const active = sorted.filter((c) => !isCutStatus(c.position)).slice(0, limit);
    const cutPlayers = sorted.filter((c) => isCutStatus(c.position));
    if (active.length === 0 && cutPlayers.length === 0) return null;

    return (
      <section id="leaderboard" className="bg-surface-card rounded-card shadow-card p-6">
        <div className="flex items-center justify-between gap-2 mb-4">
          <h2 className="text-title-3 font-semibold text-text-primary">{label || "Leaderboard"}</h2>
          <FreshnessChip asOf={asOf} />
        </div>
        {/* Column header */}
        <div className="flex items-center gap-2 px-1 pb-1.5 text-[10px] uppercase tracking-wide text-text-muted">
          <span className="w-8 shrink-0">Pos</span>
          <span className="flex-1 min-w-0">Player</span>
          <span className="w-12 text-right shrink-0">To&nbsp;par</span>
          <span className="w-12 text-right shrink-0">Thru</span>
          <span className="w-20 text-right shrink-0">Win</span>
        </div>
        <div className="divide-y divide-surface-border/40">
          {active.map((c, i) => (
            <GolfRow key={`${c.name}-${i}`} c={c} index={i} />
          ))}
        </div>
        {cutPlayers.length > 0 && (
          <details className="mt-4">
            <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
              Missed cut ({cutPlayers.length})
            </summary>
            <div className="divide-y divide-surface-border/40 mt-2">
              {cutPlayers.map((c, i) => (
                <GolfRow key={`cut-${c.name}-${i}`} c={c} index={i} cut />
              ))}
            </div>
          </details>
        )}
      </section>
    );
  }

  // L2-132: split the winner field into contenders and the collapsed tail (zero-%
  // longshots + adapter-eliminated rows). Contenders render with bars (top `limit`
  // shown); everything below — low-ranked survivors AND the 0% tail (48-nation
  // World Cup: 45 zeros pre-tournament) — collapses behind a "Show all N" expander
  // so the main view isn't a wall of zeros. Within the tail, adapter-eliminated
  // rows carry an OUT chip; longshots simply read 0%. See partitionWinnerField.
  const { contenders, tail } = partitionWinnerField(competitors);
  if (contenders.length === 0 && tail.length === 0) return null;
  // L2-130: reserve a crest slot only when at least one competitor resolved to a
  // team (soccer World Cup) — golf/tennis/F1 fields stay text-only and unshifted.
  const anyCrest = competitors.some((c) => c.team);
  const visible = contenders.slice(0, limit);
  const rest = [...contenders.slice(limit), ...tail];

  return (
    <section id="leaderboard" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <h2 className="text-title-3 font-semibold text-text-primary">{label || "Winner"}</h2>
        {live && <FreshnessChip asOf={asOf} />}
      </div>
      <div className="space-y-0.5">
        {visible.map((c, i) => (
          <WinnerFieldRow
            key={`${c.name}-${i}`}
            c={c}
            rank={i + 1}
            anyCrest={anyCrest}
            live={live}
            showSparkline={showSparkline}
            historyOutcomes={historyOutcomes}
            out={false}
          />
        ))}
      </div>
      {rest.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
            Show all {competitors.length}
          </summary>
          <div className="space-y-0.5 mt-2">
            {rest.map((c, i) => (
              <WinnerFieldRow
                key={`rest-${c.name}-${i}`}
                c={c}
                rank={visible.length + i + 1}
                anyCrest={anyCrest}
                live={live}
                showSparkline={showSparkline}
                historyOutcomes={historyOutcomes}
                out={isEliminatedCompetitor(c)}
              />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
