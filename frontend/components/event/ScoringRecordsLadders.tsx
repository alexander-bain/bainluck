"use client";

// L2-135 Item 3 — "Scoring & Records" stops being a wall of numbers. The golf
// scoring/records markets (winning score, lowest round, margin of victory,
// wire-to-wire, under-par…) arrive in the concept envelope's `children` with full
// `outcomes` (they come straight from `related_futures`). These Under-N families
// are literally Quantities, so they render through the shared QuantityGroup ladder
// — one heat-strip per question — instead of a flat outcome list.
//
// The parent excludes these market_ids from the props-script rows via
// `scoringRecordMarketIds` so nothing double-renders (the L2-121 "don't
// double-render" rule). Probability-only, light tokens.

import type { EventConceptChild } from "@/lib/types";
import { RELATED_SECTIONS } from "@/lib/golfRelatedSections";
import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";

const SCORING_TEST =
  RELATED_SECTIONS.find((s) => s.id === "scoring")?.test ??
  /best round|lowest round|shoot|low(est)?\s*score|margin of victory|winning score|wire[\s-]?to[\s-]?wire|under par/i;

function childLabel(c: EventConceptChild): string {
  return (c.market_name || c.name || "").trim();
}

/** A child is a scoring/records ladder iff its name matches the scoring bucket and
 *  it carries at least two priced outcomes (a single outcome isn't a ladder). */
function isScoringLadder(c: EventConceptChild): boolean {
  const name = childLabel(c);
  if (!name || !SCORING_TEST.test(name)) return false;
  const priced = (c.outcomes || []).filter(
    (o) => typeof o.probability === "number",
  );
  return priced.length >= 2;
}

/** Children (in payload order) that this section will render as ladders. Exported
 *  so the concept page can drop these market_ids from the props-script rows. */
export function scoringRecordChildren(
  children: EventConceptChild[] | undefined,
): EventConceptChild[] {
  return (children || []).filter(isScoringLadder);
}

/** The market_ids rendered here — the parent's props-script exclusion set. */
export function scoringRecordMarketIds(
  children: EventConceptChild[] | undefined,
): Set<number> {
  const ids = new Set<number>();
  for (const c of scoringRecordChildren(children)) {
    if (typeof c.market_id === "number") ids.add(c.market_id);
  }
  return ids;
}

/** Extract the first signed number in an outcome label (e.g. "Under 270" → 270,
 *  "15 under or better" → 15) for ascending ladder ordering. */
function parseValue(name: string): number | null {
  const m = name.match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : null;
}

function toRungs(c: EventConceptChild): { rungs: QuantityRung[]; numeric: boolean } {
  const outs = (c.outcomes || []).filter((o) => o.name);
  let numericCount = 0;
  const rungs: QuantityRung[] = outs.map((o, i) => {
    const value = parseValue(o.name);
    if (value != null) numericCount += 1;
    return {
      key: `${c.market_id ?? childLabel(c)}-${i}`,
      label: o.name,
      probability: typeof o.probability === "number" ? o.probability : null,
      value: value ?? undefined,
    };
  });
  const numeric = numericCount >= 2;
  // Non-numeric families read best as most-likely-first; numeric ladders let
  // QuantityGroup sort ascending by threshold.
  if (!numeric) {
    rungs.sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
  }
  return { rungs, numeric };
}

export default function ScoringRecordsLadders({
  items,
}: {
  items: EventConceptChild[] | undefined;
}) {
  const families = scoringRecordChildren(items);
  if (families.length === 0) return null;

  return (
    <section id="scoring-records" className="space-y-3">
      <h2 className="text-title-3 font-semibold text-text-primary">Scoring &amp; Records</h2>
      {families.map((c) => {
        const { rungs, numeric } = toRungs(c);
        if (rungs.length === 0) return null;
        return (
          <QuantityGroup
            key={c.market_id ?? childLabel(c)}
            title={childLabel(c)}
            rungs={rungs}
            sort={numeric}
            wideLabels={!numeric}
            maxRungs={numeric ? undefined : 8}
          />
        );
      })}
    </section>
  );
}
