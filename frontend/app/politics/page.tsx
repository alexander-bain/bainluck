"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { SourceChip, probColor } from "@/components/economics/atoms";
import { fetchPolitics } from "@/lib/api";
import type { PoliticsData, PoliticsMarketRow } from "@/lib/api";

const THEMES = [
  { key: "presidential", emoji: "🏛", label: "Presidential 2028" },
  { key: "congressional", emoji: "🏤", label: "Congressional" },
  { key: "gubernatorial", emoji: "🏢", label: "Gubernatorial" },
  { key: "policy", emoji: "📜", label: "Policy" },
  { key: "scotus", emoji: "⚖️", label: "Supreme Court" },
  { key: "international", emoji: "🌍", label: "International" },
  { key: "other", emoji: "📊", label: "Other" },
] as const;

const BORDER_COLOR: Record<string, string> = {
  presidential: "#3B82F6", congressional: "#8B5CF6", gubernatorial: "#10B981",
  policy: "#F59E0B", scotus: "#EF4444", international: "#0EA5E9", other: "#9CA3AF",
};

/* ── Sub-theme nav chips ──────────────────────────────────────────── */
function SubNav({ active, onJump }: { active: string | null; onJump: (k: string) => void }) {
  return (
    <div className="sticky top-0 z-30 bg-[#F5F5F7]/92 backdrop-blur-xl border-b border-[#E5E7EB]">
      <div className="max-w-[1200px] mx-auto px-5 py-2 flex gap-1.5 overflow-x-auto scrollbar-hide">
        {THEMES.map((t) => (
          <button
            key={t.key}
            onClick={() => onJump(t.key)}
            className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all border ${
              active === t.key
                ? "bg-[#111827] text-white border-[#111827]"
                : "bg-white text-[#6B7280] border-[#E5E7EB] hover:border-[#9CA3AF] hover:text-[#111827]"
            }`}
          >
            <span className="text-[13px]">{t.emoji}</span>
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Presidential hero — bar race ─────────────────────────────────── */
function PresHero({ data }: { data: NonNullable<PoliticsData["themes"]["presidential"]> }) {
  const headline = data.headline;
  if (!headline) return null;
  const candidates = headline.candidates;
  const maxProb = Math.max(...candidates.map((c) => c.prob), 1);
  const scale = 100 / Math.max(maxProb * 1.1, 10);

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-[#E5E7EB]">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-lg font-semibold text-[#111827] tracking-tight">{headline.q}</h3>
            <p className="text-[11px] text-[#9CA3AF] mt-1 tracking-wide">
              {headline.outcome_count} candidates tracked · Market-implied probability
            </p>
          </div>
          <SourceChip src={headline.src} />
        </div>
      </div>

      {/* Column header */}
      <div className="grid items-center gap-2.5 px-5 py-2 text-[10px] font-semibold text-[#9CA3AF] uppercase tracking-widest border-b border-[#E5E7EB]"
           style={{ gridTemplateColumns: "24px 1fr 1fr 52px" }}>
        <span></span>
        <span>Candidate</span>
        <span>Probability</span>
        <span className="text-right">Now</span>
      </div>

      {/* Candidate rows */}
      <div className="divide-y divide-[#F3F4F6]">
        {candidates.slice(0, 10).map((c, i) => {
          const isLeader = i === 0;
          const barWidth = c.prob * scale;
          return (
            <div key={c.name}
                 className="grid items-center gap-2.5 px-5 py-2.5 hover:bg-[#FAFBFC] transition-colors"
                 style={{ gridTemplateColumns: "24px 1fr 1fr 52px" }}>
              <span className="font-mono text-[11px] font-semibold text-[#9CA3AF] text-right tabular-nums">
                {i + 1}
              </span>
              <span className={`text-[13px] truncate ${isLeader ? "font-bold text-[#111827]" : "font-medium text-[#374151]"}`}>
                {c.name}
              </span>
              <div className="h-2.5 bg-[#F3F4F6] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max(barWidth, 1.5)}%`,
                    background: isLeader ? "#3B82F6" : probColor(c.prob),
                    opacity: isLeader ? 1 : 0.6,
                  }}
                />
              </div>
              <span className={`font-mono text-right tabular-nums ${isLeader ? "text-sm font-bold text-[#111827]" : "text-xs font-semibold text-[#6B7280]"}`}>
                {c.prob.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {headline.outcome_count > 10 && (
        <div className="px-5 py-3 border-t border-[#E5E7EB] bg-[#FAFBFC]">
          <Link href={`/futures/${headline.market_id}`} className="text-xs font-medium text-[#3B82F6] hover:underline">
            View all {headline.outcome_count} candidates →
          </Link>
        </div>
      )}

      {/* Side markets */}
      {data.side_markets && data.side_markets.length > 0 && (
        <div className="px-5 py-4 border-t border-[#E5E7EB]">
          <div className="text-[11px] font-semibold text-[#9CA3AF] uppercase tracking-widest mb-3">
            Related markets
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {data.side_markets.slice(0, 6).map((m, i) => (
              <SideCard key={i} market={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Side market card (compact) ───────────────────────────────────── */
function SideCard({ market }: { market: PoliticsMarketRow }) {
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className="bg-[#F5F5F7] rounded-lg p-3 hover:bg-[#ECECEF] transition-colors cursor-pointer flex flex-col gap-2">
        <p className="text-xs text-[#6B7280] leading-snug line-clamp-2 min-h-[30px]">{market.q}</p>
        <div className="flex items-baseline justify-between">
          <span className="text-[13px] font-medium text-[#374151] truncate">
            {market.top_outcomes?.[0]?.name || "Yes"}
          </span>
          <span className="font-mono text-base font-bold tabular-nums" style={{ color: probColor(market.prob) }}>
            {Math.round(market.prob)}%
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
            market.src === "kalshi" ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"
          }`}>
            {market.src}
          </span>
        </div>
      </div>
    </Link>
  );
}

/* ── Section header ───────────────────────────────────────────────── */
function SectionHead({ themeKey, count }: { themeKey: string; count: number }) {
  const t = THEMES.find((x) => x.key === themeKey);
  const color = BORDER_COLOR[themeKey] || "#9CA3AF";
  return (
    <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
      <h2 className="text-lg font-semibold text-[#111827] flex items-baseline gap-2 tracking-tight">
        <span className="text-base">{t?.emoji}</span>
        <span>{t?.label || themeKey}</span>
        <span className="text-[11px] font-mono font-medium tabular-nums" style={{ color }}>{count} markets</span>
      </h2>
      <span className="text-xs text-[#9CA3AF]">
        {count} active
      </span>
    </div>
  );
}

/* ── Market card ──────────────────────────────────────────────────── */
function MarketCard({ market, theme }: { market: PoliticsMarketRow; theme: string }) {
  const borderColor = BORDER_COLOR[theme] || "#9CA3AF";
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className="bg-white border border-[#E5E7EB] rounded-lg shadow-sm hover:shadow-md hover:scale-[1.005] transition-all cursor-pointer h-full flex flex-col"
           style={{ borderTop: `2px solid ${borderColor}` }}>
        <div className="p-3.5 flex-1 flex flex-col gap-2.5">
          {/* Source + outcome count */}
          <div className="flex items-center justify-between">
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
              market.src === "kalshi" ? "bg-green-50 text-green-700" : market.src === "polymarket" ? "bg-blue-50 text-blue-700" : "bg-gray-50 text-gray-600"
            }`}>
              {market.src}
            </span>
            {market.outcome_count > 3 && (
              <span className="text-[10px] text-[#9CA3AF] font-mono tabular-nums">+{market.outcome_count - 3} more</span>
            )}
          </div>

          {/* Question */}
          <h3 className="text-[13.5px] font-medium text-[#111827] leading-snug line-clamp-2">{market.q}</h3>

          {/* Outcomes */}
          <div className="flex flex-col gap-1.5 mt-auto">
            {market.top_outcomes.slice(0, 3).map((o, i) => {
              const isLeader = i === 0;
              return (
                <div key={i} className="flex items-center gap-2">
                  <span className={`text-xs truncate flex-1 ${isLeader ? "font-medium text-[#374151]" : "text-[#6B7280]"}`}>
                    {o.name}
                  </span>
                  <div className="w-12 h-1.5 bg-[#F3F4F6] rounded-full overflow-hidden shrink-0">
                    <div className="h-full rounded-full" style={{
                      width: `${Math.max(3, o.prob)}%`,
                      background: probColor(o.prob),
                      opacity: isLeader ? 1 : 0.4,
                    }} />
                  </div>
                  <span className={`font-mono text-xs tabular-nums w-9 text-right shrink-0 ${
                    isLeader ? "font-bold text-[#111827]" : "font-medium text-[#9CA3AF]"
                  }`}>
                    {Math.round(o.prob)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Link>
  );
}

/* ── Market card grid ─────────────────────────────────────────────── */
function MarketGrid({ markets, theme }: { markets: PoliticsMarketRow[]; theme: string }) {
  if (!markets || markets.length === 0) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {markets.map((m, i) => <MarketCard key={i} market={m} theme={theme} />)}
    </div>
  );
}

/* ── Theme section ────────────────────────────────────────────────── */
function ThemeSection({ themeKey, data }: { themeKey: string; data: { count: number; markets?: PoliticsMarketRow[] } | null }) {
  if (!data || data.count === 0 || !data.markets?.length) return null;
  return (
    <section id={themeKey} className="scroll-mt-28">
      <SectionHead themeKey={themeKey} count={data.count} />
      <MarketGrid markets={data.markets} theme={themeKey} />
    </section>
  );
}

/* ── Main page ────────────────────────────────────────────────────── */
export default function PoliticsPage() {
  usePageTracking({ pageType: "politics", pageTitle: "Politics Dashboard" });
  useScrollDepth({ pageType: "politics" });
  useEngagementTime({ pageType: "politics" });

  const [activeTheme, setActiveTheme] = useState<string | null>(null);
  const { data, error } = useSWR("politics-data", fetchPolitics, { refreshInterval: 60000 });

  if (error) return <div className="max-w-5xl mx-auto py-20 text-center text-[#9CA3AF] text-sm">Failed to load politics data</div>;
  if (!data) return <div className="max-w-5xl mx-auto py-20 text-center text-[#9CA3AF] text-sm animate-pulse">Loading politics markets...</div>;

  const handleJump = (key: string) => {
    setActiveTheme(key);
    document.getElementById(key)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const t = data.themes;

  return (
    <div className="-mx-3 md:-mx-6 -mt-4 min-h-screen" style={{ background: "#F5F5F7" }}>
      {/* Page header */}
      <div className="max-w-[1200px] mx-auto px-5 pt-8 pb-5">
        <div className="flex items-end justify-between gap-4 flex-wrap mb-1">
          <div>
            <h1 className="text-[32px] font-bold text-[#111827] tracking-tight leading-none">Politics</h1>
            <p className="text-[13px] text-[#6B7280] mt-2">
              Probabilities for races, policy, and power across U.S. and global politics.
            </p>
          </div>
          <div className="flex gap-4 text-[11px] text-[#9CA3AF] tracking-wide">
            <span><b className="font-mono font-semibold text-[#111827] tabular-nums">{data.total_markets.toLocaleString()}</b> markets</span>
            <span><b className="font-mono font-semibold text-[#111827]">2</b> sources</span>
          </div>
        </div>
      </div>

      {/* Sub-theme nav */}
      <SubNav active={activeTheme} onJump={handleJump} />

      {/* Content */}
      <div className="max-w-[1200px] mx-auto px-5 py-6 space-y-10">

        {/* Presidential hero */}
        {t.presidential && t.presidential.count > 0 && (
          <section id="presidential" className="scroll-mt-28">
            <SectionHead themeKey="presidential" count={t.presidential.count} />
            <PresHero data={t.presidential} />
          </section>
        )}

        <ThemeSection themeKey="congressional" data={t.congressional} />
        <ThemeSection themeKey="gubernatorial" data={t.gubernatorial} />
        <ThemeSection themeKey="policy" data={t.policy} />
        <ThemeSection themeKey="scotus" data={t.scotus} />
        <ThemeSection themeKey="international" data={t.international} />
        <ThemeSection themeKey="other" data={t.other} />
      </div>

      {/* Footer */}
      <footer className="border-t border-[#E5E7EB] bg-white">
        <div className="max-w-[1200px] mx-auto px-5 py-6 flex items-center justify-between flex-wrap gap-3 text-xs text-[#9CA3AF]">
          <span>Data from Kalshi &amp; Polymarket prediction markets · Not political advice.</span>
          <span className="font-mono tabular-nums">bainluck.com/politics · {data.total_markets.toLocaleString()} active</span>
        </div>
      </footer>
    </div>
  );
}
