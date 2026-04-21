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
        <h2 className="text-[28px] font-semibold text-[#111827] leading-tight mt-1 tracking-tight">
          {title}
        </h2>
        {meta && <div className="font-mono text-xs text-[#9CA3AF] mt-1.5">{meta}</div>}
      </div>
      {count != null && (
        <span className="text-[11px] font-semibold text-[#6B7280] bg-[#F3F4F6] px-2.5 py-1 rounded-full">
          {count} active
        </span>
      )}
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white border border-[#E5E7EB] rounded-2xl p-5 ${className}`}>
      {children}
    </div>
  );
}

export function SourceChip({ src }: { src: string }) {
  const s = SOURCES[src] || SOURCES.kalshi;
  if (src === "cross") {
    return (
      <span className="inline-flex items-center gap-1.5 border border-[#E5E7EB] rounded-full text-[10px] font-semibold tracking-wide px-2 py-0.5 text-[#374151]"
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
  if (v === 0 || v == null) return <span className="font-mono text-[10.5px] text-[#9CA3AF]">—</span>;
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
    <div className="flex-1 bg-[#F3F4F6] rounded-full overflow-hidden" style={{ height }}>
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${w}%`, background: c }} />
    </div>
  );
}

export function Histogram({ buckets, color }: {
  buckets: [number, string][]; color: string; height?: number;
}) {
  const max = Math.max(...buckets.map(b => b[0]));
  const peak = buckets.reduce((best, b, i) => (b[0] > buckets[best][0] ? i : best), 0);
  return (
    <div className="flex flex-col gap-1">
      {buckets.map((b, i) => {
        const w = max > 0 ? (b[0] / max) * 100 : 0;
        const isPeak = i === peak;
        return (
          <div key={i} className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-[#6B7280] w-[72px] text-right shrink-0">{b[1]}</span>
            <div className="flex-1 h-5 bg-[#F3F4F6] rounded overflow-hidden">
              <div className="h-full rounded flex items-center pl-1.5" style={{
                width: `${Math.max(w, 2)}%`,
                background: color,
                opacity: isPeak ? 1 : 0.35 + (b[0] / max) * 0.45,
              }}>
                {b[0] >= 3 && (
                  <span className="font-mono text-[9px] font-semibold text-white whitespace-nowrap">
                    {b[0]}%
                  </span>
                )}
              </div>
            </div>
            {b[0] < 3 && b[0] > 0 && (
              <span className="font-mono text-[9px] text-[#9CA3AF]">{b[0]}%</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function MarketRow({ q, prob, src, delta }: {
  q: string; prob: number; src: string; delta?: number | null;
}) {
  const col = probColor(prob);
  return (
    <div className="flex items-center gap-3 py-2.5 border-t border-[#F3F4F6]">
      <div className="flex-1 text-[13px] text-[#374151] leading-snug min-w-0">{q}</div>
      <span className="font-mono text-[14px] font-bold shrink-0" style={{ color: col }}>
        {Math.round(prob)}%
      </span>
      <div className="shrink-0"><SourceChip src={src} /></div>
    </div>
  );
}

export function FooterNote({ left, right }: { left: string; right?: string }) {
  return (
    <div className="mt-3.5 pt-2.5 border-t border-dashed border-[#E5E7EB] flex justify-between items-center text-[11px] text-[#9CA3AF]">
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
