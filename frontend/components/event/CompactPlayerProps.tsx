"use client";

import { useState, type ReactNode } from "react";
import type { PlayerData, PlayerStat } from "@/lib/playerPropsGrouping";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import SectionErrorBoundary from "../SectionErrorBoundary";
import MarketBrowser from "./MarketBrowser";

function TargetRow({ stat, live }: { stat: PlayerStat; live: boolean }) {
  const rungs =
    stat.shape === "ladder"
      ? (stat.rungs ?? [])
      : [{ threshold: stat.threshold, overProb: stat.overProb }];
  const [target, setTarget] = useState<number | undefined>();
  // A quoted target nearest even odds is a useful entry point, never a derived price.
  const selected =
    rungs.find((r) => r.threshold === target) ??
    [...rungs].sort(
      (a, b) =>
        Math.abs((a.overProb ?? 0) - 0.5) - Math.abs((b.overProb ?? 0) - 0.5),
    )[0];
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <span className="text-sm text-text-secondary">
          {stat.type}
          {selected?.threshold != null ? ` · ${selected.threshold}+` : ""}
        </span>
        {selected?.overProb != null && (
          <strong className="text-lg font-mono tabular-nums">
            {formatProbabilityPercent(selected.overProb)}
          </strong>
        )}
      </div>
      {rungs.length > 1 ? (
        <div
          className="flex gap-1 overflow-x-auto pb-1"
          aria-label={`${stat.type} targets`}
        >
          {rungs.map((r) => (
            <button
              key={r.threshold}
              type="button"
              aria-pressed={selected === r}
              aria-label={`${r.threshold}+ ${stat.type}${r.overProb != null ? `, ${formatProbabilityPercent(r.overProb)}` : ""}`}
              onClick={() => setTarget(r.threshold)}
              className={`relative isolate overflow-hidden min-w-12 min-h-11 rounded-md border text-xs font-mono tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${selected === r ? "border-accent-brand text-text-primary font-bold" : "border-surface-border text-text-secondary"}`}
            >
              {r.overProb != null && (
                <span
                  aria-hidden="true"
                  className="absolute inset-x-0 bottom-0 -z-10 bg-accent-brand/20"
                  style={{ height: `${r.overProb * 100}%` }}
                />
              )}
              {r.threshold}+
            </button>
          ))}
        </div>
      ) : (
        selected?.overProb != null && (
          <div
            aria-hidden="true"
            className="h-1.5 bg-surface-elevated rounded-full overflow-hidden"
          >
            <div
              className="h-full bg-accent-brand"
              style={{ width: `${selected.overProb * 100}%` }}
            />
          </div>
        )
      )}
      {live && stat.actual != null && (
        <p className="text-xs text-text-secondary mt-1">{stat.actual} so far</p>
      )}
    </div>
  );
}

export default function CompactPlayerProps({
  players,
  settled,
  live,
  renderSettled,
}: {
  players: PlayerData[];
  settled: boolean;
  live: boolean;
  renderSettled: (stat: PlayerStat, color: string) => ReactNode;
}) {
  return (
    <MarketBrowser
      label="Player props"
      items={players.flatMap((player) =>
        player.stats.map((stat, index) => ({
          key: `${player.name}-${stat.type}-${index}`,
          group: stat.type,
          search: `${player.name} ${stat.type}`,
          content: (
            <SectionErrorBoundary label={player.name} resetKey={stat}>
              <div className="grid sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-5 py-3 border-b border-surface-border">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    aria-hidden="true"
                    className="w-8 h-8 shrink-0 rounded-full bg-surface-elevated grid place-items-center text-xs font-semibold"
                  >
                    {player.initials}
                  </span>
                  <span className="text-sm font-semibold break-words">
                    {player.name}
                  </span>
                </div>
                {settled ? (
                  renderSettled(stat, player.color)
                ) : (
                  <TargetRow stat={stat} live={live} />
                )}
              </div>
            </SectionErrorBoundary>
          ),
        })),
      )}
    />
  );
}
