"use client";

import Link from "next/link";
import type { ChamberControl } from "@/lib/api";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { TwoSidedHistoryTimeline } from "@/components/event/TwoSidedTimeline";
import { SourceBadge } from "./atoms";
import s from "@/app/politics/politics.module.css";

type Control = ChamberControl & { source?: string; winner?: string };

export default function PartyControlRow({
  senate,
  house,
  stacked = false,
}: {
  senate: Control | null;
  house: Control | null;
  stacked?: boolean;
}) {
  if (!senate && !house) return null;
  return (
    <div className={stacked ? "grid grid-cols-2 gap-3" : s.chamberGrid}>
      {senate && <ChamberControlCard chamber="Senate" probs={senate} compact={stacked} />}
      {house && <ChamberControlCard chamber="House" probs={house} compact={stacked} />}
    </div>
  );
}

function ChamberControlCard({
  chamber,
  probs,
  compact = false,
}: {
  chamber: string;
  probs: Control;
  compact?: boolean;
}) {
  // #6778: the two sides are one question in FIXED positions, so they round once
  // together through the pair contract (#2831) instead of independently. The
  // served pair is an exact complement on a half-percent grid — Senate control
  // is `41.5 / 58.5` — and `Math.round` is half-up, so both sides rounded UP at
  // once and the card printed `42% R vs 59% D`. `renderedDuelPercents` rounds
  // the favourite and derives the other, which is the same rule the market cards
  // a few hundred pixels down this page already use. The BAR stays on the raw
  // values: it is drawing the split, not printing it.
  const [gopPct, demPct] = renderedDuelPercents(probs.gop / 100, probs.dem / 100);
  if (compact) {
    return (
      <div className="min-w-0 rounded-card border border-surface-border bg-surface-card p-3">
        <Link href={`/futures/${probs.market_id}`} data-midterms-card="control" className="block space-y-3 hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-brand">
          <div className="flex items-center justify-between gap-1"><h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{chamber}</h3><SourceBadge source={probs.source ?? "both"} /></div>
          {probs.winner ? <p className="text-sm font-semibold text-text-primary">Settled - {probs.winner}</p> : <>
            <div className="grid grid-cols-2 gap-2">
              <div style={{ color: "var(--party-democratic)" }}><p className="font-mono text-2xl font-semibold tabular-nums">{demPct ?? Math.round(probs.dem)}%</p><p className="text-[10px] font-medium">Democratic</p></div>
              <div className="text-right" style={{ color: "var(--party-republican)" }}><p className="font-mono text-2xl font-semibold tabular-nums">{gopPct ?? Math.round(probs.gop)}%</p><p className="text-[10px] font-medium">Republican</p></div>
            </div>
            <div aria-hidden className="flex h-1.5 overflow-hidden rounded-full bg-surface-elevated"><span style={{ width: `${probs.dem}%`, backgroundColor: "var(--party-democratic)" }} /><span style={{ width: `${probs.gop}%`, backgroundColor: "var(--party-republican)" }} /></div>
          </>}
        </Link>
        {!probs.winner && probs.market_id > 0 && (
          <TwoSidedHistoryTimeline
            marketId={probs.market_id}
            defaultHours={8760}
            height={180}
          />
        )}
      </div>
    );
  }
  const gopLeads = probs.gop >= probs.dem;
  const summary = (
    <div className={s.chamberCard}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--text-muted)",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
          }}
        >
          {chamber} control
        </span>
        <SourceBadge source={probs.source ?? "both"} compact />
      </div>

      {probs.winner ? <p className="font-semibold text-text-primary">Settled - {probs.winner}</p> : <>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span
            className={s.probNum}
            style={{
              fontSize: 28,
              color: gopLeads ? "#DC2626" : "#9CA3AF",
            }}
          >
            {gopPct ?? Math.round(probs.gop)}%
          </span>
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>R</span>
        </div>
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>vs</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span
            className={s.probNum}
            style={{
              fontSize: 28,
              color: !gopLeads ? "#2563EB" : "#9CA3AF",
            }}
          >
            {demPct ?? Math.round(probs.dem)}%
          </span>
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>D</span>
        </div>
      </div>

      <div className={s.binaryBar} style={{ height: 6 }}>
        <div className={s.binaryR} style={{ width: `${probs.gop}%` }} />
        <div className={s.binaryD} style={{ width: `${probs.dem}%` }} />
      </div>
      </>}
    </div>
  );

  return (
    <Link href={`/futures/${probs.market_id}`}>
      {summary}
    </Link>
  );
}

