"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface TotalPointsSpectrumProps {
  data: GameMarketsResponse;
  eventStatus?: string;
}

function SourceBadge({ count }: { count: number }) {
  if (count <= 1) return null;
  return (
    <span className="text-[10px] font-semibold tracking-wide uppercase px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600">
      {count} sources
    </span>
  );
}

function ProjectionBar({
  label,
  value,
  scaleMax,
  barColor,
  labelClass,
  bold,
}: {
  label: string;
  value: number;
  scaleMax: number;
  barColor: string;
  labelClass?: string;
  bold?: boolean;
}) {
  const pct = Math.min(100, (value / scaleMax) * 100);
  return (
    <div className="grid grid-cols-[80px_1fr_52px] items-center gap-3">
      <div className={`text-[10px] font-semibold uppercase tracking-wide ${labelClass || "text-text-muted"}`}>
        {label}
      </div>
      <div className="h-2.5 rounded-full bg-surface-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
      <div className={`font-mono text-sm text-right tabular-nums ${bold ? "font-semibold" : ""} ${labelClass || ""}`}>
        {value}
      </div>
    </div>
  );
}

export default function TotalPointsSpectrum({ data, eventStatus }: TotalPointsSpectrumProps) {
  const { totals, pace } = data;

  const thresholds = useMemo(
    () => totals.filter((t) => t.market_type === "game_total").sort((a, b) => a.threshold - b.threshold),
    [totals]
  );

  // Pick 5 representative thresholds for the ladder (must be before any early return)
  const ladderThresholds = useMemo(() => {
    if (thresholds.length <= 5) return thresholds;
    const step = Math.max(1, Math.floor(thresholds.length / 5));
    const picks: typeof thresholds = [];
    for (let i = 0; i < thresholds.length && picks.length < 5; i += step) {
      picks.push(thresholds[i]);
    }
    if (picks.length < 5 && thresholds.length > 0) {
      picks.push(thresholds[thresholds.length - 1]);
    }
    return picks;
  }, [thresholds]);

  if (thresholds.length === 0) return null;

  const sources = [...new Set(thresholds.map((t) => t.source))];
  const sourceCount = sources.length;

  const isLive = eventStatus === "live";
  const isDone = eventStatus === "completed" || eventStatus === "closed";
  const isPre = !isLive && !isDone;

  const centerThreshold = thresholds.reduce((closest, t) =>
    Math.abs(t.over_probability - 0.5) < Math.abs(closest.over_probability - 0.5) ? t : closest
  );
  const ouLine = centerThreshold.threshold;

  const actualTotal = isDone && data.home_score != null && data.away_score != null
    ? data.home_score + data.away_score
    : null;

  const paceTotal = pace?.projected_total ?? null;
  const scored = pace?.total_scored ?? null;

  const unit = "points";

  // Minimal tier: <5 thresholds — just show O/U + probability
  if (thresholds.length < 5 && isPre) {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-5">
        <div className="flex items-end justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold tracking-tight">Projected scoring</h3>
            <p className="text-sm text-text-secondary mt-0.5">Limited market depth</p>
          </div>
          <SourceBadge count={sourceCount} />
        </div>
        <div className="flex items-center justify-between gap-6 flex-wrap">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Pre-game line</div>
            <div className="font-mono tabular-nums text-3xl font-bold">{ouLine}</div>
            <div className="text-xs text-text-muted">combined {unit}</div>
          </div>
          <div className="flex-1 min-w-[280px]">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-1">
              Probability the total clears {ouLine}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-3 rounded-full bg-surface-border overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent-brand transition-all duration-500"
                  style={{ width: `${centerThreshold.over_probability * 100}%` }}
                />
              </div>
              <span className="font-mono tabular-nums font-bold">
                {Math.round(centerThreshold.over_probability * 100)}%
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Projection strip
  const renderProjectionStrip = () => {
    if (isPre) {
      const expected = Math.round(ouLine);
      const scaleMax = expected * 1.12;
      return (
        <div className="bg-surface-elevated border border-surface-border rounded-lg p-4 mb-5">
          <div className="text-sm font-semibold text-text-primary mb-3">Expected total {unit}</div>
          <ProjectionBar label="Pre-game" value={expected} scaleMax={scaleMax} barColor="rgba(156,163,175,0.7)" labelClass="text-text-primary" bold />
        </div>
      );
    }

    if (isLive && paceTotal != null && scored != null) {
      const scaleMax = Math.max(ouLine, paceTotal) * 1.12;
      const pctFn = (v: number) => Math.min(100, (v / scaleMax) * 100);
      const projRemaining = paceTotal - scored;

      return (
        <div className="bg-surface-elevated border border-surface-border rounded-lg p-4 mb-5">
          <div className="text-sm font-semibold text-text-primary mb-3">Projected total {unit}</div>
          <div className="space-y-2">
            <ProjectionBar label="Pre-game" value={ouLine} scaleMax={scaleMax} barColor="rgba(156,163,175,0.55)" labelClass="text-text-muted" />
            {/* Pace bar with scored portion solid */}
            <div className="grid grid-cols-[80px_1fr_52px] items-center gap-3">
              <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "#8B5CF6" }}>Pace</div>
              <div className="relative h-2.5 rounded-full bg-surface-border overflow-hidden">
                <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-500" style={{ width: `${pctFn(paceTotal)}%`, background: "#8B5CF6", opacity: 0.28 }} />
                <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-500" style={{ width: `${pctFn(scored)}%`, background: "#8B5CF6" }} />
              </div>
              <div className="font-mono tabular-nums text-sm text-right font-semibold" style={{ color: "#8B5CF6" }}>{paceTotal}</div>
            </div>
            <div className="grid grid-cols-[80px_1fr_52px] items-center gap-3 -mt-0.5">
              <div />
              <div className="text-[10px] font-semibold text-text-muted">
                <span className="font-semibold" style={{ color: "#8B5CF6" }}>{scored}</span> scored
                {projRemaining > 0 && ` · +${projRemaining.toFixed(0)} projected`}
              </div>
              <div />
            </div>
          </div>
          {paceTotal !== ouLine && (
            <div className="text-xs text-text-muted mt-3">
              Pace projects{" "}
              <span className="font-mono tabular-nums font-semibold" style={{ color: "#8B5CF6" }}>
                {paceTotal > ouLine ? "+" : ""}{(paceTotal - ouLine).toFixed(1)}
              </span>{" "}
              vs pre-game expectation.
            </div>
          )}
        </div>
      );
    }

    if (isDone && actualTotal != null) {
      const scaleMax = Math.max(ouLine, actualTotal) * 1.12;
      const pctFn = (v: number) => Math.min(100, (v / scaleMax) * 100);
      const diff = actualTotal - ouLine;
      const covered = diff > 0;

      return (
        <div className="bg-surface-elevated border border-surface-border rounded-lg p-4 mb-5">
          <div className="text-sm font-semibold text-text-primary mb-3">Final total {unit}</div>
          <div className="space-y-2">
            <ProjectionBar label="Pre-game" value={ouLine} scaleMax={scaleMax} barColor="rgba(156,163,175,0.55)" labelClass="text-text-muted" />
            <div className="grid grid-cols-[80px_1fr_52px] items-center gap-3">
              <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "#8B5CF6" }}>Actual</div>
              <div className="h-2.5 rounded-full bg-surface-border overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pctFn(actualTotal)}%`, background: "#8B5CF6" }} />
              </div>
              <div className="font-mono tabular-nums text-sm text-right font-semibold" style={{ color: "#8B5CF6" }}>{actualTotal}</div>
            </div>
          </div>
          <div className="text-xs text-text-muted mt-3">
            Actual came in{" "}
            <span className={`font-mono tabular-nums font-semibold ${covered ? "text-accent-brand" : "text-accent-danger"}`}>
              {covered ? "+" : ""}{diff.toFixed(1)}
            </span>{" "}
            vs pre-game expectation.
          </div>
        </div>
      );
    }

    return null;
  };

  // Threshold ladder
  const renderLadder = () => {
    return (
      <div className="mt-5">
        <div className="text-sm font-semibold text-text-primary mb-1">Threshold probabilities</div>
        {ladderThresholds.map((t) => {
          const preProb = t.over_probability;
          const finalHit = isDone && actualTotal != null ? actualTotal >= t.threshold : null;

          if (isDone) {
            return (
              <div key={t.threshold} className="grid items-center gap-4 py-3 border-t border-surface-border" style={{ gridTemplateColumns: "80px 1fr 96px" }}>
                <div className="font-mono tabular-nums text-sm font-semibold">{t.threshold}+</div>
                <div className="grid grid-cols-[64px_1fr_42px] items-center gap-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Pre-game</div>
                  <div className="h-2 rounded-full bg-surface-border overflow-hidden">
                    <div className="h-full bg-text-muted/60 transition-all duration-500" style={{ width: `${preProb * 100}%` }} />
                  </div>
                  <div className="font-mono tabular-nums text-[11px] text-right">{Math.round(preProb * 100)}%</div>
                </div>
                <div className="text-right">
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded"
                    style={finalHit
                      ? { background: "rgba(16,185,129,0.15)", color: "#10B981" }
                      : { background: "rgba(239,68,68,0.15)", color: "#EF4444" }
                    }
                  >
                    {finalHit ? "HIT" : "MISS"}
                  </span>
                </div>
              </div>
            );
          }

          return (
            <div key={t.threshold} className="grid items-center gap-4 py-3 border-t border-surface-border" style={{ gridTemplateColumns: "80px 1fr" }}>
              <div className="font-mono tabular-nums text-sm font-semibold">{t.threshold}+</div>
              <div className="grid grid-cols-[64px_1fr_42px] items-center gap-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Pre-game</div>
                <div className="h-2 rounded-full bg-surface-border overflow-hidden">
                  <div className="h-full bg-text-muted/70 transition-all duration-500" style={{ width: `${preProb * 100}%` }} />
                </div>
                <div className="font-mono tabular-nums text-[11px] text-right font-semibold">{Math.round(preProb * 100)}%</div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-5">
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Projected scoring</h3>
        </div>
        <SourceBadge count={sourceCount} />
      </div>
      {renderProjectionStrip()}
      {renderLadder()}
    </div>
  );
}
