"use client";

// #999 L2-64 Event Concept Page — matchups & props rail. Live matchups render as
// cards (top outcomes with probability bars); decided ones are grouped under a
// collapsed "Completed (N)" so a settled 99% never reads as live (L2-63 Item 2).
// Probability-only, no source names.

import { formatProbability } from "@/lib/api";
import { childLeader, splitChildren } from "@/lib/eventConceptDisplay";
import type { EventConceptChild } from "@/lib/types";

function topOutcomes(child: EventConceptChild): { name: string; probability: number | null }[] {
  const outs = child.outcomes || [];
  if (outs.length > 0) {
    return [...outs]
      .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))
      .slice(0, 2);
  }
  const lead = childLeader(child);
  return lead ? [lead] : [];
}

function MatchupCard({ child, dim }: { child: EventConceptChild; dim?: boolean }) {
  const outs = topOutcomes(child);
  const lead = childLeader(child);
  return (
    <div
      className={`flex-shrink-0 w-60 bg-surface-card rounded-card shadow-card p-3 ${
        dim ? "opacity-70" : ""
      }`}
    >
      <div className="text-xs text-text-muted truncate mb-2">
        {child.market_name || child.name || "Market"}
      </div>
      {dim ? (
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-secondary truncate">{lead?.name}</span>
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1 py-0.5 rounded bg-text-muted/15 text-text-secondary shrink-0">
            Final
          </span>
        </div>
      ) : (
        <div className="space-y-1.5">
          {outs.map((o, i) => {
            const pct = o.probability != null ? Math.round(o.probability * 100) : null;
            return (
              <div key={`${o.name}-${i}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-text-primary truncate">{o.name}</span>
                  <span className="font-mono text-xs font-semibold text-text-primary tabular-nums shrink-0">
                    {formatProbability(o.probability)}
                  </span>
                </div>
                {pct != null && (
                  <div className="mt-1 h-1 rounded-full bg-surface-elevated overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent-brand"
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface MatchupsRailProps {
  items: EventConceptChild[];
}

export default function MatchupsRail({ items }: MatchupsRailProps) {
  if (!items || items.length === 0) return null;
  const { live, settled } = splitChildren(items);

  return (
    <section id="matchups" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">Matchups &amp; props</h2>
      {live.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
          {live.map((child) => (
            <MatchupCard key={child.market_id} child={child} />
          ))}
        </div>
      )}
      {settled.length > 0 && (
        <details className="mt-4">
          <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
            Completed ({settled.length})
          </summary>
          <div className="flex gap-3 overflow-x-auto pb-2 mt-2 -mx-1 px-1">
            {settled.map((child) => (
              <MatchupCard key={child.market_id} child={child} dim />
            ))}
          </div>
        </details>
      )}
      {live.length === 0 && settled.length === 0 && (
        <p className="text-sm text-text-secondary">No matchups yet.</p>
      )}
    </section>
  );
}
