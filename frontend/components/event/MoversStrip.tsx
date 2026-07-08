"use client";

// #999 L2-64 Event Concept Page — TODAY'S MOVERS strip. Horizontal, scrollable
// row of the biggest 24h probability movers from the envelope. Probability-only
// (movement shown in points), no source names. Honest-empty: renders nothing when
// there are no movers (controlled by the page + the showMovers tweak).

import { formatMovement } from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

interface MoversStripProps {
  movers: EventConceptResponse["movers"];
  show?: boolean;
}

export default function MoversStrip({ movers, show = true }: MoversStripProps) {
  if (!show) return null;
  const items = (movers || [])
    .map((m) => ({ name: m.name, mv: formatMovement(m.change ?? null) }))
    .filter((m): m is { name: string; mv: NonNullable<ReturnType<typeof formatMovement>> } =>
      Boolean(m.name) && m.mv != null,
    );
  if (items.length === 0) return null;

  return (
    <section aria-label="Today's movers">
      <h2 className="text-[11px] uppercase tracking-widest text-text-muted mb-2">
        Today&apos;s movers
      </h2>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {items.map((m, i) => (
          <div
            key={`${m.name}-${i}`}
            className="flex-shrink-0 flex items-center gap-2 bg-surface-card rounded-card shadow-card px-3 py-2"
          >
            <span className="text-sm text-text-primary whitespace-nowrap max-w-[140px] truncate">
              {m.name}
            </span>
            <span
              className={`font-mono text-xs font-semibold tabular-nums whitespace-nowrap ${
                m.mv.dir === "up" ? "text-accent-brand" : "text-accent-danger"
              }`}
            >
              {m.mv.dir === "up" ? "▲" : "▼"} {m.mv.text}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
