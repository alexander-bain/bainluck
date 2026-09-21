"use client";

import Link from "next/link";
import EntityImage from "@/components/EntityImage";
import { formatProbabilityPercent, NO_READING } from "@/lib/probabilityDisplay";
import type { PropFamily, PropFamilyRow } from "@/lib/api";

// ---------------------------------------------------------------------------
// Prop-family cohort card (L2-167 Item 1) — the cohort-compare kernel's first
// instance. Consumes GET /api/teams/{team}/prop-families: one card per family
// ("Next Team" races, award races, threshold ladders), one entity row each with
// an image-or-initials avatar and a RELATIVE probability bar (bar fills against
// the family's leader, so "who's most likely" reads instantly), sorted desc.
//
// The backend already: only emits families with >=2 distinct entities, collapses
// cross-source duplicate entities into one row, pre-sorts rows (settled sink below
// live; live by probability desc). Settled members get the WHAT-HIT label (the
// 100%-Mitchell-Robinson class) instead of a live 100% row. This component renders
// nothing when there are no qualifying families (yield is unmeasured — the section
// must not embarrass on sparse teams).
// ---------------------------------------------------------------------------

// #7710 — the row's number obeys UX-P046's boundary rule.
//
// This was a bare `Math.round(v * 100)`, so a row the backend ranked and priced
// could print `0%`, which reads as "cannot happen" over a link to the market
// pricing it as possible. Measured on production 2026-09-21 across 12 MLB
// teams, 315 prop-family rows: Dylan Beavers sat at `0.0005` in Baltimore's "Al
// Rookie Of The Year" card and Andy Pages at `0.0005` in the Dodgers' MVP card,
// both printing `0%` beside a full-height cohort bar.
//
// `formatProbabilityPercent` and NOT `probabilityCellText`: this is an outcome
// ROW, the same idiom as `TeamChampionshipPath` two sections up the same page
// (routed by #7687) and as every feed/futures row, so it prints `<1%` / `>99%`.
// The grid vocabulary with its decimal band belongs to grid cells — see
// `TeamDivisionRace`, which is a slice of the playoffs grid and speaks that one.
//
// Settled rows are unaffected, and that is measured rather than assumed: of 156
// settled rows, every one carries exactly `0.0` or exactly `1.0`, the two
// boundaries the payload states and the helper prints plainly. A `✓ Won` badge
// therefore still sits beside `100%`.
function pct(v: number | null): string {
  return v === null ? NO_READING : formatProbabilityPercent(v);
}

// `result` has THREE states and each needs its own branch (#7405). It used to
// have two: `"won"` and everything-else, so `null` rendered the same "Out" as a
// real `"lost"`. `null` is not a loss — it is the backend's explicit "this row
// is settled and we never graded it" (`utils/prop_families.py::_settled_status`
// leaves it None for a terminal market with no graded outcome, and for one
// marked settled by `resolution_date` alone). Measured when this was written,
// across 120 team slugs: of the 440 rows that rendered "OUT", only 110 were a
// real `"lost"` — the other 330 (75%), on 32 of 120 teams, were this bug. The
// loudest was FC Cincinnati's 65% favourite to score first against DC United
// wearing "OUT" on a market whose three outcomes were all `is_winner IS NULL`
// — a stated negative result we had no evidence for.
//
// Silence is not an option here: the row keeps its price, and a price with no
// marker is the #6595->#5481 / #6169->#6815 failure (withholding the field just
// moves the lie into the price channel, which has no marker at all). So the
// unknown case says so, in the site's existing vocabulary for an ungraded
// settled row ("No result reported").
function WhatHitBadge({ result }: { result: "won" | "lost" | null }) {
  if (result === "won") {
    return (
      <span className="rounded-full bg-accent-live/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-accent-live">
        ✓ Won
      </span>
    );
  }
  if (result === "lost") {
    return (
      <span className="rounded-full bg-surface-elevated px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-text-muted">
        Out
      </span>
    );
  }
  return (
    <span className="rounded-full bg-surface-elevated px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-text-muted">
      No result
    </span>
  );
}

function PropFamilyRowLine({
  row,
  maxProb,
  teamColor,
}: {
  row: PropFamilyRow;
  maxProb: number;
  teamColor: string | null;
}) {
  // Bar fills RELATIVE to the family leader — the leader is full-width so the
  // ranking reads instantly; the literal % lives in the trailing number so the
  // absolute value is never lost.
  const barPct =
    row.probability !== null && maxProb > 0
      ? Math.max(2, Math.round((row.probability / maxProb) * 100))
      : 0;
  const barColor = row.settled ? "#9CA3AF" : teamColor || "#3B82F6";

  const inner = (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 border-b border-surface-border/60 last:border-b-0 ${
        row.market_id != null ? "hover:bg-surface-elevated/60 transition-colors" : ""
      }`}
    >
      <EntityImage
        type="wikipedia"
        name={row.entity}
        size={24}
        fallbackColor={row.settled ? "#9CA3AF" : teamColor || "#6B7280"}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={`text-[13px] truncate ${
              row.settled ? "font-medium text-text-secondary" : "font-semibold text-text-primary"
            }`}
          >
            {row.entity}
          </span>
          {row.settled && <WhatHitBadge result={row.result} />}
        </div>
        {row.top_outcome && !row.settled && (
          <div className="text-[11px] text-text-muted truncate">{row.top_outcome}</div>
        )}
        <div className="mt-1 h-1.5 w-full rounded-full bg-surface-border/40 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${barPct}%`, backgroundColor: barColor, opacity: row.settled ? 0.5 : 1 }}
          />
        </div>
      </div>
      <span
        className={`text-right font-mono font-bold text-sm tabular-nums flex-shrink-0 ${
          row.settled ? "text-text-muted" : "text-text-primary"
        }`}
      >
        {pct(row.probability)}
      </span>
    </div>
  );

  if (row.market_id != null) {
    return (
      <Link href={`/futures/${row.market_id}`} className="block">
        {inner}
      </Link>
    );
  }
  return inner;
}

function PropFamilyCard({
  family,
  teamColor,
}: {
  family: PropFamily;
  teamColor: string | null;
}) {
  const maxProb = family.rows.reduce(
    (m, r) => (r.probability !== null && r.probability > m ? r.probability : m),
    0,
  );

  return (
    <div className="bg-surface-card border border-surface-border rounded-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-border">
        <span className="text-[13px] font-semibold text-text-primary">{family.label}</span>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
          {family.entity_count} in the mix
        </span>
      </div>
      <div>
        {family.rows.map((row) => (
          <PropFamilyRowLine
            key={`${row.market_id ?? "m"}-${row.outcome_id ?? row.entity}`}
            row={row}
            maxProb={maxProb}
            teamColor={teamColor}
          />
        ))}
      </div>
    </div>
  );
}

export function TeamPropFamilies({
  families,
  teamColor,
}: {
  families: PropFamily[];
  teamColor: string | null;
}) {
  // Defensive: the backend only emits >=2-entity families, but never render a
  // degenerate card if a stale/sparse payload slips a single-entity family through.
  const shown = (families || []).filter((f) => (f.rows?.length ?? 0) >= 2);
  if (shown.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        Prop Races
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {shown.map((family) => (
          <PropFamilyCard key={family.family_key} family={family} teamColor={teamColor} />
        ))}
      </div>
    </section>
  );
}
