"use client";

// #999 L2-84 (B2) Event Concept Page — a real PROPS section for UFC cards.
// Fights render in the MatchupsRail; props (method-of-victory / round / go-the-
// distance / occurrence) render here, grouped by type so a card reads like a
// real card (fights + props), not one undifferentiated rail. Probability-only,
// no odds, no source names — same visual language as MatchupCard.

import { formatProbability } from "@/lib/api";
import type { EventConceptChild, EventConceptSection } from "@/lib/types";

const PROP_GROUPS: { key: string; label: string }[] = [
  { key: "method", label: "Method of victory" },
  { key: "rounds", label: "Rounds" },
  { key: "distance", label: "Goes the distance" },
  { key: "nominations", label: "Nominations" }, // L2-87: awards nomination markets
  { key: "round", label: "By round" }, // L2-89: golf round leaders + per-round Top-N
  { key: "primary", label: "Primaries" }, // L2-89: election primary/nominee contests
  { key: "seats", label: "Seat forecasts" }, // L2-89: election seat-count markets
  // L2-146: cycling grand-tour props (Tour de France) — the stage winners and
  // classification/jersey markets that hang off the GC winner-field leaderboard.
  // These prop_types are set ONLY by event_cycling.py, so the labels can't leak
  // into UFC/golf/election concepts. Without them all 24 TdF markets collapse
  // into one undifferentiated "Other props" bucket.
  { key: "stage", label: "Stages" },
  { key: "team", label: "Team classification" },
  { key: "jersey", label: "Jerseys" },
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
    <div className="flex-shrink-0 w-60 md:w-auto bg-surface-card rounded-card shadow-card border border-surface-border p-3.5 transition-shadow hover:shadow-card-hover">
      <div className="text-xs text-text-muted truncate mb-2.5">
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

/** L2-146 fallback: group children by `prop_type` against the fixed PROP_GROUPS
 *  list, unknown/missing types collapsing into "Other props". */
function groupByPropType(
  items: EventConceptChild[],
): { key: string; label: string; props: EventConceptChild[] }[] {
  const known = new Set(PROP_GROUPS.map((g) => g.key));
  const groups = PROP_GROUPS.map((g) => ({
    ...g,
    props: items.filter((p) => p.prop_type === g.key),
  })).filter((g) => g.props.length > 0);
  const other = items.filter((p) => !p.prop_type || !known.has(p.prop_type));
  if (other.length > 0) groups.push({ key: "other", label: "Other props", props: other });
  return groups;
}

/** L2-147 Item 4: group children by the backend-owned `sections` split — each
 *  section claims a set of `market_ids`, and a child renders under the first
 *  section that claims its id (in section order). Children not claimed by any
 *  section fall back to `prop_type` grouping so nothing is dropped. The backend
 *  owns the section split going forward (GC / Stages / Jerseys …); this replaces
 *  the page re-deriving it from `prop_type` when the split is available. */
function groupBySections(
  items: EventConceptChild[],
  sections: EventConceptSection[],
): { key: string; label: string; props: EventConceptChild[] }[] {
  // market_id → the first section (in order) that lists it.
  const idToSection = new Map<number, { label: string; order: number }>();
  sections.forEach((s, order) => {
    (s.market_ids || []).forEach((id) => {
      if (typeof id === "number" && !idToSection.has(id)) {
        idToSection.set(id, { label: s.label, order });
      }
    });
  });

  const claimed = items.filter(
    (p) => typeof p.market_id === "number" && idToSection.has(p.market_id),
  );
  // No child maps to a section → the split doesn't apply here; fall back entirely.
  if (claimed.length === 0) return groupByPropType(items);

  const bySection = new Map<
    number,
    { label: string; order: number; props: EventConceptChild[] }
  >();
  for (const p of claimed) {
    const meta = idToSection.get(p.market_id as number)!;
    const g =
      bySection.get(meta.order) ??
      { label: meta.label, order: meta.order, props: [] as EventConceptChild[] };
    g.props.push(p);
    bySection.set(meta.order, g);
  }
  const sectionGroups = [...bySection.values()]
    .sort((a, b) => a.order - b.order)
    .map((g) => ({ key: `section-${g.order}`, label: g.label, props: g.props }));

  // Any leftover child (a section didn't claim it) still groups by prop_type so
  // the backend split is additive, never lossy.
  const unclaimed = items.filter((p) => !claimed.includes(p));
  return [...sectionGroups, ...groupByPropType(unclaimed)];
}

interface EventPropsProps {
  items: EventConceptChild[];
  /** L2-147 Item 4: backend-owned section split. When present (and it claims at
   *  least one child), children group by section instead of re-derived prop_type;
   *  absent/non-matching → the prop_type grouping (unchanged). */
  sections?: EventConceptSection[] | null;
  /** L2-148: heading + anchor id. A secondary instance — golf's section-grouped
   *  prop children (per-round Top-N) rendered ALONGSIDE the props-script — reads
   *  "More props" / #more-props so it doesn't collide with the primary props
   *  section's "Props" / #props. Defaults preserve the sole-section behavior. */
  title?: string;
  anchorId?: string;
}

export default function EventProps({
  items,
  sections,
  title = "Props",
  anchorId = "props",
}: EventPropsProps) {
  if (!items || items.length === 0) return null;

  const groups =
    sections && sections.length > 0
      ? groupBySections(items, sections)
      : groupByPropType(items);

  return (
    <section id={anchorId} className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">{title}</h2>
      <div className="space-y-5">
        {groups.map((g) => (
          <div key={g.key}>
            <div className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">
              {g.label}
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-4 md:overflow-visible md:mx-0 md:px-0 md:pb-0">
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
