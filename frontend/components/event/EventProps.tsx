"use client";

// #999 L2-84 (B2) Event Concept Page — a real PROPS section for UFC cards.
// Fights render in the MatchupsRail; props (method-of-victory / round / go-the-
// distance / occurrence) render here, grouped by type so a card reads like a
// real card (fights + props), not one undifferentiated rail. Probability-only,
// no odds, no source names — same visual language as MatchupCard.

import { formatProbability } from "@/lib/api";
import type { EventConceptChild } from "@/lib/types";

const PROP_GROUPS: { key: string; label: string }[] = [
  { key: "method", label: "Method of victory" },
  { key: "rounds", label: "Rounds" },
  { key: "distance", label: "Goes the distance" },
  { key: "occurrence", label: "Will it happen?" },
];

function topOutcomes(child: EventConceptChild): { name: string; probability: number | null }[] {
  const outs = child.outcomes || [];
  return [...outs]
    .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))
    .slice(0, 2);
}

function PropCard({ child }: { child: EventConceptChild }) {
  const outs = topOutcomes(child);
  return (
    <div className="flex-shrink-0 w-60 bg-surface-card rounded-card shadow-card p-3">
      <div className="text-xs text-text-muted truncate mb-2">
        {child.market_name || child.name || "Prop"}
      </div>
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
                    className="h-full rounded-full bg-accent-futures"
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface EventPropsProps {
  items: EventConceptChild[];
}

export default function EventProps({ items }: EventPropsProps) {
  if (!items || items.length === 0) return null;

  // Group by prop_type in a stable order; any unknown type falls to "Other".
  const known = new Set(PROP_GROUPS.map((g) => g.key));
  const groups = PROP_GROUPS.map((g) => ({
    ...g,
    props: items.filter((p) => p.prop_type === g.key),
  })).filter((g) => g.props.length > 0);
  const other = items.filter((p) => !p.prop_type || !known.has(p.prop_type));
  if (other.length > 0) groups.push({ key: "other", label: "Other props", props: other });

  return (
    <section id="props" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">Props</h2>
      <div className="space-y-5">
        {groups.map((g) => (
          <div key={g.key}>
            <div className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">
              {g.label}
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
              {g.props.map((p) => (
                <PropCard key={p.market_id} child={p} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
