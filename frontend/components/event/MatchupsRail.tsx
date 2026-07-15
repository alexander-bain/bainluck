"use client";

// #999 L2-64 Event Concept Page — matchups & props rail. Live matchups render as
// cards (top outcomes with probability bars); decided ones are grouped under a
// collapsed "Completed (N)" so a settled 99% never reads as live (L2-63 Item 2).
// Probability-only, no source names.
//
// L2-130: soccer bracket games are TEAM duels (home vs away crest + score + win
// probability), not fight-card outcome lists — they render via MatchupDuel. The
// combat/golf outcome-card path is unchanged for non-matchup children.

import { formatProbability } from "@/lib/api";
import {
  childLeader,
  childReactKey,
  isMatchupChild,
  splitChildren,
} from "@/lib/eventConceptDisplay";
import type { EventConceptChild } from "@/lib/types";
import FighterAvatar from "./FighterAvatar";
import MatchupDuel from "./MatchupDuel";

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
      className={`flex-shrink-0 w-60 md:w-auto bg-surface-card rounded-card shadow-card border border-surface-border p-3.5 transition-shadow hover:shadow-card-hover ${
        dim ? "opacity-70" : ""
      }`}
    >
      <div className="text-xs text-text-muted truncate mb-2.5">
        {child.market_name || child.name || "Market"}
      </div>
      {dim ? (
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {lead?.name && <FighterAvatar name={lead.name} size={28} dim />}
            <span className="text-sm text-text-secondary truncate">{lead?.name}</span>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-text-muted/15 text-text-secondary shrink-0">
            Final
          </span>
        </div>
      ) : (
        <div className="space-y-2.5">
          {outs.map((o, i) => {
            const pct = o.probability != null ? Math.round(o.probability * 100) : null;
            return (
              <div key={`${o.name}-${i}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FighterAvatar name={o.name} size={32} />
                    <span className="text-sm text-text-primary truncate">{o.name}</span>
                  </div>
                  <span className="font-mono text-xs font-semibold text-text-primary tabular-nums shrink-0">
                    {formatProbability(o.probability)}
                  </span>
                </div>
                {pct != null && (
                  <div className="mt-1.5 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
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

/** Render one child in the rail: a soccer team duel (crest + score + win prob) or
 *  the combat/golf outcome card. `dim` is passed to the combat card for the
 *  completed group; MatchupDuel handles its own settled treatment internally. */
function RailChild({ child, index, dim }: { child: EventConceptChild; index: number; dim?: boolean }) {
  if (isMatchupChild(child)) {
    return <MatchupDuel child={child} />;
  }
  return <MatchupCard child={child} dim={dim} />;
}

interface MatchupsRailProps {
  items: EventConceptChild[];
  /** L2-130: a child already shown in the container hero — excluded from the rail
   *  so the headliner isn't rendered twice. Matched by reference identity. */
  exclude?: EventConceptChild | null;
  /** Optional section heading override (soccer reads "Matches", not "Matchups"). */
  title?: string;
}

export default function MatchupsRail({ items, exclude, title }: MatchupsRailProps) {
  const shown = (items || []).filter((c) => c !== exclude);
  if (shown.length === 0) return null;
  const { live, settled } = splitChildren(shown);
  const gridClass =
    "flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-4 md:overflow-visible md:mx-0 md:px-0 md:pb-0";

  return (
    <section id="matchups" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">{title || "Matchups & props"}</h2>
      {live.length > 0 && (
        // Mobile: a horizontal-scroll rail. Desktop (L2-113): a responsive 2–3-col
        // grid so wide viewports don't hide bouts behind a scroll gutter.
        <div className={gridClass}>
          {live.map((child, i) => (
            <RailChild key={childReactKey(child, i)} child={child} index={i} />
          ))}
        </div>
      )}
      {settled.length > 0 && (
        <details className="mt-4">
          <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
            Completed ({settled.length})
          </summary>
          <div className={`${gridClass} mt-2`}>
            {settled.map((child, i) => (
              <RailChild key={childReactKey(child, i)} child={child} index={i} dim />
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
