"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchFuturesHistory } from "@/lib/api";
import type { TeamFutureItem } from "@/lib/api";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { pickJourneyFuture } from "@/lib/teamSeasonJourney";
import { journeyRangeLabel } from "@/lib/teamSeason";
import { FuturesChart } from "@/components/FuturesChart";

// ---------------------------------------------------------------------------
// Season journey (L2-162). One line — the team's championship (or best
// available) probability from opening day → today — drawn by the consolidated
// FuturesChart: fixed 0–100% axis, no smoothing (straight segments), team color.
// The team's year as one picture. Renders nothing until it has ≥2 real points,
// so a team with no season-long history never shows an empty frame.
// ---------------------------------------------------------------------------

// ~6 months back covers opening day → today for the in-season leagues; the
// backend auto-extends further when the series is sparse.
const SEASON_HOURS = 24 * 180;

export function TeamSeasonJourney({
  futures,
  teamColor,
  season,
}: {
  futures: TeamFutureItem[];
  teamColor: string | null;
  // Season string (e.g. "2026-27") from the team payload (#242) — prefixes the
  // header range label. Absent/null for leagues without a modeled season.
  season?: string | null;
}) {
  const pick = useMemo(() => pickJourneyFuture(futures), [futures]);
  const [outcome, setOutcome] = useState<FuturesOutcomeHistory | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!pick) {
      setLoaded(true);
      return;
    }
    let cancelled = false;
    setLoaded(false);
    fetchFuturesHistory(pick.marketId, SEASON_HOURS, pick.outcomeId)
      .then((res) => {
        if (cancelled) return;
        // The endpoint may return the whole field even with outcome_id set —
        // filter to the team's line so the chart draws exactly one series.
        const mine =
          res.outcomes.find((o) => o.outcome_id === pick.outcomeId) ??
          (res.outcomes.length === 1 ? res.outcomes[0] : null);
        setOutcome(mine ?? null);
      })
      .catch(() => {
        if (!cancelled) setOutcome(null);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [pick]);

  const realPoints = outcome
    ? outcome.history.filter((p) => p.probability !== null).length
    : 0;

  // Don't render an empty frame: need a pick, a loaded response, and ≥2 points.
  if (!pick || !loaded || !outcome || realPoints < 2) return null;

  const colorMap = teamColor
    ? new Map<number, string>([[outcome.outcome_id, teamColor]])
    : undefined;
  const currentPct =
    pick.probability !== null ? Math.round(pick.probability * 100) : null;

  return (
    <section className="mb-8">
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        Season Journey
      </h2>
      <div className="bg-surface-card border border-surface-border rounded-card p-5">
        <div className="flex items-baseline gap-2 mb-3 flex-wrap">
          <span className="text-[15px] font-semibold text-text-primary">
            {pick.marketName}
          </span>
          <span className="text-xs text-text-muted">
            {journeyRangeLabel(season)}
          </span>
          {currentPct !== null && (
            <span
              className="ml-auto font-mono font-bold text-lg tabular-nums"
              style={{ color: teamColor || undefined }}
            >
              {currentPct}%
            </span>
          )}
        </div>
        <FuturesChart
          historyData={[outcome]}
          selectedOutcomes={new Set([outcome.outcome_id])}
          outcomeColors={colorMap}
          fixedYAxis
          allowZoom
          showLegend={false}
          height={220}
        />
      </div>
    </section>
  );
}
