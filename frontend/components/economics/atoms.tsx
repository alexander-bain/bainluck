"use client";

import { useState } from "react";

export function probColor(p: number): string {
  if (p >= 65) return "#10B981";
  if (p >= 35) return "#F59E0B";
  return "#94A3B8";
}

export function deltaColor(d: number): string {
  if (d > 0) return "#22C55E";
  if (d < 0) return "#EF4444";
  return "#9CA3AF";
}

const SOURCES: Record<string, { label: string; color: string; bg: string; fg: string }> = {
  kalshi: { label: "Kalshi", color: "#22C55E", bg: "#ECFDF5", fg: "#047857" },
  polymarket: { label: "Polymarket", color: "#3B82F6", bg: "#EFF6FF", fg: "#1D4ED8" },
  cross: { label: "Cross-source", color: "#8B5CF6", bg: "#F5F3FF", fg: "#6D28D9" },
};

export function SectionHeader({ kicker, title, meta, count }: {
  kicker: string; title: string; meta?: string; count?: number;
}) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4 flex-wrap">
      <div>
        <span className="text-[11px] font-bold tracking-[0.12em] uppercase" style={{ color: "#059669" }}>
          {kicker}
        </span>
        <h2 className="text-[28px] font-semibold text-text-primary leading-tight mt-1 tracking-tight">
          {title}
        </h2>
        {meta && <div className="font-mono text-xs text-text-muted mt-1.5">{meta}</div>}
      </div>
      {count != null && (
        <span className="text-[11px] font-semibold text-text-secondary bg-surface-secondary px-2.5 py-1 rounded-full">
          {count} active
        </span>
      )}
    </div>
  );
}

export function Card({ children, className = "", style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <div className={`bg-surface-card border border-surface-border rounded-2xl p-5 ${className}`} style={style}>
      {children}
    </div>
  );
}

export function SourceChip({ src }: { src: string }) {
  const s = SOURCES[src] || SOURCES.kalshi;
  if (src === "cross") {
    return (
      <span className="inline-flex items-center gap-1.5 border border-surface-border rounded-full text-[10px] font-semibold tracking-wide px-2 py-0.5 text-text-secondary"
        style={{ background: `linear-gradient(90deg, ${SOURCES.kalshi.bg} 50%, ${SOURCES.polymarket.bg} 50%)` }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: SOURCES.kalshi.color }} />
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: SOURCES.polymarket.color }} />
        CROSS
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full text-[11px] font-medium px-2 py-0.5"
      style={{ background: s.bg, color: s.fg }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
      {s.label}
    </span>
  );
}

export function Delta({ v, unit = "pp" }: { v: number | null | undefined; unit?: string }) {
  if (v === 0 || v == null) return <span className="font-mono text-[10.5px] text-text-muted">—</span>;
  const col = deltaColor(v);
  const arrow = v > 0 ? "▲" : "▼";
  return (
    <span className="font-mono text-[10.5px] font-semibold" style={{ color: col }}>
      {arrow} {Math.abs(v)}{unit}
    </span>
  );
}

export function ProbBar({ value, height = 6, color }: { value: number; height?: number; color?: string }) {
  const c = color || probColor(value);
  const w = Math.max(1, value);
  return (
    <div className="flex-1 bg-surface-secondary rounded-full overflow-hidden" style={{ height }}>
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${w}%`, background: c }} />
    </div>
  );
}

/**
 * The leading word every bracket label in one histogram restates, or "".
 *
 * #2564 clause 3: the September blocks on /economics render eight rows reading
 * `Exactly …`, `Exactly …`, `Exactly …` — eight different questions, eight
 * different probabilities, and nothing on screen telling them apart. The labels
 * are `Exactly 3.5%`, `Exactly 3.6%`, `Exactly 2.1%`: the value is present and
 * correct in the payload, and the shared word is what eats the column, so the
 * distinguishing suffix is the part that gets truncated away.
 *
 * The idiom is `sharedFamilyPrefix`'s (#2662/#5191, `lib/propFamily.ts`) and
 * the three guards are lifted from it — but not the code: that one retreats to
 * the last `": "` boundary, which a bracket label does not have, so it returns
 * "" on every specimen here. Same rule, different boundary.
 *
 *  1. two or more DISTINCT labels — sharedness across one row is not evidence
 *     of anything;
 *  2. the prefix is a whole leading word, shared by every label;
 *  3. it never strips a label to nothing, and never makes two labels that
 *     differed read the same. A histogram whose rows are told apart only by
 *     the prefix must keep it;
 *  4. IT NEVER STRIPS A BOUND. `Exactly 3.5%` is a bucket and the word is
 *     restated by the seven rows around it; `At least 370` is a cumulative
 *     threshold and the word is the meaning — `least 370` and `370` are both
 *     worse than what they replace. The vocabulary is `economics.py`'s own
 *     `_CUMULATIVE_PREFIXES`, mirrored rather than re-derived, so a rung this
 *     page already knows to keep raw is a rung this label rule keeps whole.
 */
const BOUND_WORDS = [
  "above", "at", "least", "more", "over", "greater", "below", "before",
  "under", "less", "than",
];

export function sharedBucketPrefix(labels: string[]): string {
  const distinct = Array.from(new Set(labels));
  if (distinct.length < 2) return "";

  const lead = /^(\S+\s+)/.exec(distinct[0]);
  if (!lead) return "";
  const prefix = lead[1];
  if (!distinct.every(l => l.startsWith(prefix))) return "";
  if (BOUND_WORDS.includes(prefix.trim().toLowerCase())) return "";

  const stripped = distinct.map(l => l.slice(prefix.length).trim());
  if (stripped.some(s => !s)) return "";
  if (new Set(stripped).size !== distinct.length) return "";
  return prefix;
}

export function Histogram({ buckets, color }: {
  buckets: [number, string][]; color: string; height?: number;
}) {
  const max = Math.max(...buckets.map(b => b[0]));
  const peak = buckets.reduce((best, b, i) => (b[0] > buckets[best][0] ? i : best), 0);
  const shared = sharedBucketPrefix(buckets.map(b => b[1]));
  const label = (raw: string) => (shared && raw.startsWith(shared) ? raw.slice(shared.length).trim() : raw);
  return (
    <div className="flex flex-col gap-px">
      {buckets.map((b, i) => {
        const w = max > 0 ? (b[0] / max) * 100 : 0;
        const isPeak = i === peak;
        return (
          <div key={i} className="flex items-center gap-1.5 h-[22px]">
            {/* Sized to its content between a floor and a ceiling, not pinned
                at 56px. A range label ("1.9 to 2.1%") needs ~72px at this size
                and was ellipsised to `1.9 to 2…` — the reader could not tell
                2.0% from 2.1% on the modal outcome of the next CPI print. The
                bar track beside it is `flex-1` and had the room to spare. The
                ceiling keeps a long label from starving the bar, and `truncate`
                stays as the last resort rather than the first. */}
            <span className="font-mono text-[10px] text-text-secondary min-w-[56px] max-w-[88px] text-right shrink-0 truncate">{label(b[1])}</span>
            <div className="flex-1 h-[16px] bg-surface-secondary rounded-sm overflow-hidden">
              <div className="h-full rounded-sm" style={{
                width: `${Math.max(w, 1.5)}%`,
                background: color,
                opacity: isPeak ? 1 : 0.35 + (b[0] / max) * 0.45,
              }} />
            </div>
            <span className="font-mono text-[10px] font-semibold w-[32px] text-right shrink-0" style={{ color: isPeak ? "var(--text-primary)" : "var(--text-muted)" }}>
              {b[0]}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function MarketRow({ q, prob, src, delta, leader }: {
  q: string; prob: number; src: string; delta?: number | null; leader?: string | null;
}) {
  const col = probColor(prob);
  return (
    <div className="py-2.5 border-t border-surface-secondary">
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1 text-[13px] text-text-secondary leading-snug min-w-0">{q}</div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-[80px] h-[4px] bg-surface-secondary rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.max(prob, 3)}%`, background: col }} />
          </div>
          <span className="font-mono text-[18px] font-semibold w-[48px] text-right" style={{ color: col }}>
            {Math.round(prob)}%
          </span>
        </div>
      </div>
      {/* Wraps rather than truncates. The leader is the longest thing on this
          line ("Above 5.6 million barrels/day") and the one a truncation
          destroys: weather measured 8/8 leaders cut at 390px when the same
          content was laid out as a nowrap row (ux/1083, #3147). Each piece
          stays whole and takes the next line when it must. */}
      <div className="flex items-center flex-wrap gap-1.5 mt-1">
        <SourceChip src={src} />
        {/* Which outcome the row's percentage prices. "What will the tariff
            rate on Canadian imports be on Jan 1, 2027? — 85%" is 85% of "10%
            or above", not a confidence in anything. Omitted when the question
            already answers itself. See EconMarketRow.leader (#6696). */}
        {leader ? (
          <span
            data-testid="econ-market-leader"
            className="text-[11px] font-semibold text-text-secondary"
          >
            {leader}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function FooterNote({ left, right }: { left: string; right?: string }) {
  return (
    <div className="mt-3.5 pt-2.5 border-t border-dashed border-surface-border flex justify-between items-center text-[11px] text-text-muted">
      <span>{left}</span>
      {right && <span className="font-mono">{right}</span>}
    </div>
  );
}

export function ProbNum({ value, size = 36, color, suffix = "%" }: {
  value: number | string; size?: number; color?: string; suffix?: string;
}) {
  const c = color || (typeof value === "number" ? probColor(value) : "#10B981");
  return (
    <span className="font-mono font-semibold tracking-tight leading-none" style={{ fontSize: size, color: c }}>
      {typeof value === "number" ? Math.round(value) : value}
      {suffix && <span style={{ fontSize: size * 0.42, opacity: 0.7 }}>{suffix}</span>}
    </span>
  );
}
