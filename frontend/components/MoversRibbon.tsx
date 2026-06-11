"use client";

import Link from "next/link";
import type { ChampionshipGridMover } from "@/lib/types";

interface MoversRibbonProps {
  movers: ChampionshipGridMover[];
  /** Link to the full grid page (e.g. /sport/basketball/nba) */
  gridHref?: string;
}

/**
 * Horizontal ribbon showing the biggest 24h championship odds movers.
 * Displays team logo/color swatch, name, change direction, and magnitude.
 */
export default function MoversRibbon({ movers, gridHref }: MoversRibbonProps) {
  if (!movers || movers.length === 0) return null;

  // Show up to 6 movers, sorted by absolute change descending
  // Filter out zero/null movers and guard against NaN from null change_24h
  const sorted = [...movers]
    .filter((m) => m.change_24h != null && Math.abs(m.change_24h) >= 0.001)
    .sort((a, b) => Math.abs(b.change_24h ?? 0) - Math.abs(a.change_24h ?? 0))
    .slice(0, 6);

  return (
    <section aria-label="Biggest odds movers in the last 24 hours">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide">
          Biggest Movers (24h)
        </h2>
        {gridHref && (
          <Link
            href={gridHref}
            className="text-xs font-medium text-accent-brand hover:underline"
          >
            Full grid &rarr;
          </Link>
        )}
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
        {sorted.map((mover, i) => {
          const isUp = mover.direction === "up";
          const pct = Math.abs(mover.change_24h * 100);
          const formatted = pct >= 10 ? `${Math.round(pct)}` : pct.toFixed(1);

          return (
            <div
              key={`${mover.name}-${mover.column}-${i}`}
              className="flex items-center gap-2.5 rounded-xl border border-surface-border bg-surface-card px-3.5 py-2.5 min-w-[160px] flex-shrink-0"
            >
              {/* Team identity: logo or color swatch */}
              {mover.logo_url ? (
                <img
                  src={mover.logo_url}
                  alt=""
                  className="w-6 h-6 object-contain flex-shrink-0"
                />
              ) : mover.primary_color ? (
                <div
                  className="w-6 h-6 rounded-full flex-shrink-0"
                  style={{ backgroundColor: mover.primary_color }}
                />
              ) : (
                <div className="w-6 h-6 rounded-full bg-surface-elevated flex-shrink-0" />
              )}

              {/* Name + change */}
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-text-primary truncate">
                  {mover.short_name || mover.name}
                </div>
                <div className="text-[10px] text-text-muted capitalize">
                  {mover.column.replace(/_/g, " ")}
                </div>
              </div>

              {/* Arrow + magnitude */}
              <div className={`flex items-center gap-0.5 flex-shrink-0 font-mono text-sm font-bold ${
                isUp ? "text-accent-live" : "text-accent-danger"
              }`}>
                <span className="text-xs">{isUp ? "▲" : "▼"}</span>
                <span>{formatted}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
