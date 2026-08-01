"use client";

import { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useAnalytics } from "@/hooks/useAnalytics";
import type { ProgressionResponse, ProgressionParticipant, ProgressionStage } from "@/lib/types";
import type { ProgressionCellStatus } from "@/lib/gridCellState";
import { progressionSortValue } from "@/lib/gridCellState";
import TeamNameLink from "./TeamNameLink";

interface TournamentProgressionTableProps {
  data: ProgressionResponse;
  /** Show team logos in the first column */
  showLogos?: boolean;
  /** Callback when hovering a participant row */
  onHoverParticipant?: (name: string | null) => void;
  /** Page type for analytics (e.g. "futures_detail", "golf") */
  pageType?: string;
  className?: string;
}

type SortConfig = {
  stageKey: string | null; // null = sort by name
  direction: "asc" | "desc";
};

/**
 * Compute inline data bar width as a percentage (0-100).
 * Uses square-root scaling so differences at the low end (2% vs 8%)
 * are as visible as differences at the high end (20% vs 35%).
 * Scaled relative to a column max of ~40% (sqrt(0.4) ≈ 0.632).
 */
function barWidth(probability: number | null): number {
  if (probability === null || probability === undefined || probability <= 0) return 0;
  // sqrt scaling, capped at 100% bar width
  return Math.min(100, (Math.sqrt(probability) / Math.sqrt(0.4)) * 100);
}

/**
 * Font weight / opacity class based on probability value.
 * Higher values get bolder text; very small values fade out.
 */
function probTextClass(probability: number | null, status?: ProgressionCellStatus): string {
  // Eliminated with no number left to strike renders the terminal glyph, so the
  // strike-through only applies where a legacy producer still supplies one.
  if (status === "eliminated") {
    return probability === null ? "text-red-400/60" : "text-red-400/60 line-through";
  }
  if (status === "clinched") return "text-emerald-600 font-bold";
  if (status === "missing" || status === "unavailable") return "text-text-secondary/40";
  if (probability === null) return "text-text-secondary/40";
  if (probability >= 0.10) return "text-text-primary font-semibold";
  if (probability >= 0.01) return "text-text-primary";
  return "text-text-secondary/50";
}

/**
 * Glyph + accessible name for a stage cell (L2-227).
 *
 * "Settled means settled": a clinched cell shows ✓, an eliminated cell shows ✕,
 * and neither ever shows a number. A cell with no market (missing) or one the
 * register cannot vouch for (unavailable) shows a muted em-dash — never 50%,
 * never a stale live-looking probability. The em-dash keeps the cell's
 * dimensions stable so a row cannot collapse.
 */
function cellDisplay(
  probability: number | null,
  status: ProgressionCellStatus,
): { text: string; label: string } {
  switch (status) {
    case "clinched":
      return { text: "✓", label: "Clinched" };
    case "eliminated":
      // A legacy producer may still send a probability alongside the status;
      // keep showing it (struck through) rather than dropping information.
      return probability === null
        ? { text: "✕", label: "Eliminated" }
        : { text: formatProb(probability), label: "Eliminated" };
    case "missing":
      return { text: "—", label: "No market" };
    case "unavailable":
      return { text: "—", label: "Unavailable" };
    default:
      return {
        text: formatProb(probability),
        label: probability === null ? "No data" : "Live probability",
      };
  }
}

/**
 * Format probability for display in cells.
 * Shows percentage with appropriate precision.
 */
function formatProb(p: number | null): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return "—";
  const pct = p * 100;
  if (pct >= 10) return `${Math.round(pct)}%`;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  if (pct >= 0.1) return `${pct.toFixed(1)}%`;
  return "<0.1%";
}

/**
 * Change indicator (small triangle + delta).
 */
function ChangeIndicator({ change }: { change: number | null | undefined }) {
  if (!change || Math.abs(change) < 0.001) return null;
  const pct = change * 100;
  const isPositive = change > 0;
  return (
    <span
      className={`text-[10px] leading-none ${
        isPositive ? "text-emerald-400" : "text-red-400"
      }`}
      title={`${isPositive ? "+" : ""}${pct.toFixed(1)}% in 24h`}
    >
      {isPositive ? "▲" : "▼"}
      {Math.abs(pct) >= 1 ? Math.round(Math.abs(pct)) : Math.abs(pct).toFixed(1)}
      <span className="text-[8px] opacity-60 ml-px">24h</span>
    </span>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Books",
  kalshi: "Kalshi",
  polymarket: "Poly",
  datagolf: "DG",
};

function SourceBreakdown({ sources }: { sources: { source: string; probability: number }[] }) {
  if (!sources || sources.length <= 1) return null;
  return (
    <div className="flex gap-1.5 justify-center mt-0.5">
      {sources.map((s) => {
        const pct = s.probability * 100;
        const label = SOURCE_LABELS[s.source] || s.source;
        const probStr = pct >= 10 ? `${Math.round(pct)}` : pct >= 1 ? pct.toFixed(1) : pct < 0.1 ? "<.1" : pct.toFixed(1);
        return (
          <span
            key={s.source}
            className="text-[9px] leading-none text-text-secondary/40 font-mono whitespace-nowrap"
            title={`${label}: ${pct >= 1 ? pct.toFixed(1) : pct.toFixed(2)}%`}
          >
            <span className="text-text-secondary/25">{label[0]}</span>{probStr}
          </span>
        );
      })}
    </div>
  );
}

export default function TournamentProgressionTable({
  data,
  showLogos = true,
  onHoverParticipant,
  pageType = "futures_detail",
  className,
}: TournamentProgressionTableProps) {
  const { track } = useAnalytics();
  const [sort, setSort] = useState<SortConfig>({
    stageKey: Array.isArray(data.stages) && data.stages.length > 0
      ? data.stages[data.stages.length - 1]?.key ?? null
      : null,
    direction: "desc",
  });

  // One poison row must not blank the table: drop entries that are not usable
  // objects instead of letting a `.name`/`.probabilities` access throw during
  // render (gotcha #42, applied to the grid surface).
  const safeParticipants = useMemo(
    () =>
      (Array.isArray(data.participants) ? data.participants : []).filter(
        (p): p is ProgressionParticipant =>
          !!p && typeof p === "object" && typeof p.name === "string",
      ),
    [data.participants],
  );

  const safeStages = useMemo(
    () =>
      (Array.isArray(data.stages) ? data.stages : []).filter(
        (s): s is ProgressionStage => !!s && typeof s === "object" && typeof s.key === "string",
      ),
    [data.stages],
  );

  const sortedParticipants = useMemo(() => {
    if (!safeParticipants.length) return [];

    return [...safeParticipants].sort((a, b) => {
      if (sort.stageKey === null) {
        const cmp = a.name.localeCompare(b.name);
        return sort.direction === "asc" ? cmp : -cmp;
      }
      // Terminal cells carry no probability, so sorting on the raw number would
      // file a clinched champion below a 0.1% longshot. Live cells are unchanged.
      const aVal = progressionSortValue(
        a.probabilities?.[sort.stageKey],
        a.status?.[sort.stageKey] ?? null,
      );
      const bVal = progressionSortValue(
        b.probabilities?.[sort.stageKey],
        b.status?.[sort.stageKey] ?? null,
      );
      const cmp = bVal - aVal;
      return sort.direction === "desc" ? cmp : -cmp;
    });
  }, [safeParticipants, sort]);

  const handleSort = useCallback((stageKey: string | null) => {
    setSort((prev) => {
      const newDirection =
        prev.stageKey === stageKey
          ? prev.direction === "desc" ? "asc" : "desc"
          : stageKey === null ? "asc" : "desc";

      const stageLabel = stageKey
        ? safeStages.find((s) => s.key === stageKey)?.label ?? stageKey
        : "name";

      track("progression_sort", {
        stage_key: stageKey ?? "name",
        stage_label: stageLabel,
        direction: newDirection,
        sport: data.sport,
        page_type: pageType,
      });

      return { stageKey, direction: newDirection };
    });
  }, [safeStages, data.sport, pageType, track]);

  const handleStageClick = useCallback((stage: ProgressionStage) => {
    if (!stage.market_id) return;
    track("progression_stage_click", {
      stage_key: stage.key,
      stage_label: stage.label,
      market_id: stage.market_id,
      sport: data.sport,
      page_type: pageType,
    });
  }, [data.sport, pageType, track]);

  // Find unique sources across all participants for column header labels
  const uniqueSources = useMemo(() => {
    const srcSet = new Set<string>();
    for (const p of safeParticipants) {
      for (const sources of Object.values(p.sources_data ?? {})) {
        for (const s of sources) srcSet.add(s.source);
      }
    }
    return Array.from(srcSet).sort();
  }, [safeParticipants]);

  const hasSources = uniqueSources.length > 1;

  if (!safeStages.length || !safeParticipants.length) {
    return (
      <div className={`text-center text-text-secondary py-8 ${className || ""}`}>
        No multi-stage data available for this market.
      </div>
    );
  }

  const stagesAvailable = safeStages.length;
  const sportStageCount = _sportStageCount(data.sport);

  return (
    <div className={className}>
      {/* Tournament name header */}
      {data.tournament_name && (
        <h3 className="text-base font-semibold text-text-primary mb-1">
          {data.tournament_name}
        </h3>
      )}
      {/* Legends row: color + source */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-1.5">
        {/* Bar legend */}
        <div className="flex items-center gap-1 text-[10px] text-text-secondary/50">
          <span className="text-text-secondary/40">Bar width = probability</span>
        </div>
        {/* Source legend */}
        {hasSources && uniqueSources.length > 1 && (
          <p className="text-[10px] text-text-secondary/40">
            Sources: {uniqueSources.map((s) => `${(SOURCE_LABELS[s] || s)[0]}=${SOURCE_LABELS[s] || s}`).join(", ")}
          </p>
        )}
      </div>
      {/* Stage coverage indicator */}
      {sportStageCount > stagesAvailable && (
        <p className="text-xs text-text-secondary mb-2">
          {stagesAvailable} of {sportStageCount} stages available
        </p>
      )}

      {/* Scrollable table container */}
      <div className="overflow-x-auto -mx-2 px-2">
        <table className="w-full border-collapse text-sm min-w-[500px]">
          <thead>
            <tr className="border-b border-white/10">
              {/* Rank column */}
              <th className="sticky left-0 z-10 bg-surface-card py-2 px-1 text-center text-text-secondary font-medium w-8">
                #
              </th>
              {/* Name column - sticky */}
              <th
                className="sticky left-8 z-10 bg-surface-card py-2 px-2 text-left text-text-secondary font-medium cursor-pointer hover:text-text-primary transition-colors min-w-[140px]"
                onClick={() => handleSort(null)}
              >
                <span className="flex items-center gap-1">
                  {data.sport === "golf" ? "Golfer" : "Team"}
                  {sort.stageKey === null && (
                    <SortArrow direction={sort.direction} />
                  )}
                </span>
              </th>
              {/* Stage columns */}
              {safeStages.map((stage) => {
                // Resolved (season-state decided) columns are de-emphasized so
                // they no longer read as live probability bars (#927).
                const isResolved = !!stage.resolved;
                return (
                <th
                  key={stage.key}
                  className={`py-2 px-2 text-center font-medium cursor-pointer transition-colors whitespace-nowrap ${isResolved ? "text-text-muted" : "text-text-secondary hover:text-text-primary"}`}
                  onClick={() => handleSort(stage.key)}
                >
                  {stage.market_id ? (
                    <Link
                      href={`/futures/${stage.market_id}`}
                      className="hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStageClick(stage);
                      }}
                    >
                      <span className="flex items-center justify-center gap-1">
                        {stage.label}
                        {sort.stageKey === stage.key && (
                          <SortArrow direction={sort.direction} />
                        )}
                      </span>
                    </Link>
                  ) : (
                    <span className="flex items-center justify-center gap-1">
                      {stage.label}
                      {sort.stageKey === stage.key && (
                        <SortArrow direction={sort.direction} />
                      )}
                    </span>
                  )}
                  {isResolved && (
                    <span className="block text-[9px] font-normal text-text-muted uppercase tracking-wide mt-0.5">
                      decided
                    </span>
                  )}
                </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedParticipants.map((participant, idx) => (
              <tr
                key={participant.team_id ?? participant.name}
                className="border-b border-white/5 hover:bg-white/5 transition-colors"
                onMouseEnter={() => onHoverParticipant?.(participant.name)}
                onMouseLeave={() => onHoverParticipant?.(null)}
              >
                {/* Rank */}
                <td className="sticky left-0 z-10 bg-surface-card py-1.5 px-1 text-center text-text-secondary text-xs">
                  {idx + 1}
                </td>
                {/* Name */}
                <td className="sticky left-8 z-10 bg-surface-card py-1.5 px-2">
                  <div className="flex items-center gap-2">
                    {showLogos && participant.logo_url && (
                      <img
                        src={participant.logo_url}
                        alt=""
                        className="w-5 h-5 object-contain flex-shrink-0"
                        loading="lazy"
                      />
                    )}
                    {showLogos && !participant.logo_url && participant.primary_color && (
                      <span
                        className="w-5 h-5 rounded-full flex-shrink-0 inline-block"
                        style={{ backgroundColor: participant.primary_color }}
                      />
                    )}
                    {participant.seed != null && (
                      <span className="text-[10px] font-mono text-text-secondary/60 flex-shrink-0">
                        {participant.seed}
                      </span>
                    )}
                    <TeamNameLink
                      name={participant.name}
                      sportKey={data.sport}
                      className="text-text-primary font-medium truncate max-w-[240px] sm:max-w-[300px] hover:underline"
                    />
                    {participant.record && (
                      <span className="text-[10px] text-text-secondary hidden sm:inline">
                        {participant.record}
                      </span>
                    )}
                  </div>
                </td>
                {/* Stage cells */}
                {safeStages.map((stage) => {
                  // Every lookup is guarded: a participant missing one of these
                  // maps (poison payload, partial adapter) must render an empty
                  // cell, never throw and blank the whole table.
                  const prob = participant.probabilities?.[stage.key] ?? null;
                  const change = participant.changes_24h?.[stage.key];
                  const status = participant.status?.[stage.key] ?? null;
                  const sources = participant.sources_data?.[stage.key];
                  // Build tooltip with per-source values
                  const tooltip = sources?.length
                    ? sources.map((s) => {
                        const label = SOURCE_LABELS[s.source] || s.source;
                        const pct = s.probability * 100;
                        return `${label}: ${pct >= 1 ? pct.toFixed(1) : pct.toFixed(2)}%`;
                      }).join(" · ")
                    : undefined;
                  const isResolved = !!stage.resolved;
                  // Resolved columns: no live bar, no change indicator — a muted
                  // decided glyph (in@✓ / out@—) so it can't read as a live bar.
                  const bw = isResolved ? 0 : barWidth(prob);
                  const display = cellDisplay(prob, status);
                  return (
                    <td
                      key={stage.key}
                      className="py-1.5 px-2 text-center relative"
                      title={isResolved ? "Decided" : (tooltip ?? display.label)}
                    >
                      {/* Inline data bar — scaled width, single-hue accent */}
                      {bw > 0 && (
                        <div
                          className="absolute inset-y-0 left-0 bg-blue-500/[0.08] transition-all"
                          style={{ width: `${bw}%` }}
                        />
                      )}
                      <div className="flex flex-col items-center relative">
                        {isResolved ? (
                          <span className="font-mono text-sm text-text-muted">
                            {prob != null && prob >= 0.5 ? "✓" : "—"}
                          </span>
                        ) : (
                          <>
                            <span
                              className={`font-mono text-sm ${probTextClass(prob, status)}`}
                              aria-label={display.label}
                              data-cell-state={status ?? "live"}
                            >
                              {display.text}
                            </span>
                            <SourceBreakdown sources={sources ?? []} />
                            <ChangeIndicator change={change} />
                          </>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortArrow({ direction }: { direction: "asc" | "desc" }) {
  return (
    <span className="text-[10px] text-blue-400">
      {direction === "desc" ? "▼" : "▲"}
    </span>
  );
}

/**
 * Total possible stages for a sport (for "X of Y stages" indicator).
 */
function _sportStageCount(sport: string): number {
  const counts: Record<string, number> = {
    golf: 5,
    football: 4,
    basketball: 3,
    baseball: 4,
    hockey: 4,
    soccer: 2,
    tennis: 2,
  };
  return counts[sport] ?? 0;
}
