"use client";

import { useRef } from "react";
import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  Card, SourceChip, FooterNote, ProbBar, probColor,
} from "@/components/economics/atoms";
import { fetchPolitics } from "@/lib/api";
import type { PoliticsData, PoliticsMarketRow } from "@/lib/api";

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const THEME_COLOR: Record<string, string> = {
  presidential: "#3B82F6",
  congressional: "#8B5CF6",
  gubernatorial: "#10B981",
  policy: "#F59E0B",
  scotus: "#EF4444",
  international: "#0EA5E9",
  other: "#6B7280",
};

const THEME_META: Record<string, { label: string; title: string }> = {
  presidential: { label: "Presidential", title: "The race for the White House" },
  congressional: { label: "Congressional", title: "Senate, House, and midterm races" },
  gubernatorial: { label: "Gubernatorial", title: "State-level races" },
  policy: { label: "Policy & Legislation", title: "Bills, executive orders, and regulatory moves" },
  scotus: { label: "Supreme Court", title: "Rulings, nominations, and the bench" },
  international: { label: "International", title: "Elections and politics beyond US borders" },
  other: { label: "More Politics", title: "Other political markets" },
};

const JUMP_THEMES = ["presidential", "congressional", "gubernatorial", "policy", "scotus", "international"] as const;

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function JumpChips({ active }: { active?: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  return (
    <div ref={scrollRef} className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1">
      {JUMP_THEMES.map((key) => {
        const m = THEME_META[key];
        const isActive = active === key;
        return (
          <a
            key={key}
            href={`#${key}`}
            className={`shrink-0 text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
              isActive
                ? "bg-[#111827] text-white border-[#111827]"
                : "bg-white text-[#374151] border-[#E5E7EB] hover:border-[#9CA3AF]"
            }`}
          >
            {m.label}
          </a>
        );
      })}
    </div>
  );
}

function CandidateBar({ name, prob, rank }: { name: string; prob: number; rank: number }) {
  const col = rank === 0 ? "#4338CA" : probColor(prob);
  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="text-[10px] text-[#9CA3AF] w-4 text-right shrink-0 font-mono">
        {rank + 1}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className={`text-[13px] truncate ${rank === 0 ? "font-bold text-[#111827]" : "text-[#374151]"}`}>
            {name}
          </span>
          <span className="font-mono text-sm font-semibold tabular-nums shrink-0 ml-2" style={{ color: col }}>
            {Math.round(prob)}%
          </span>
        </div>
        <ProbBar value={prob} height={rank === 0 ? 8 : 5} color={col} />
      </div>
    </div>
  );
}

function MarketCard({ market, theme }: { market: PoliticsMarketRow; theme: string }) {
  const borderColor = THEME_COLOR[theme] || THEME_COLOR.other;
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div
        className="bg-white border border-[#E5E7EB] rounded-xl p-4 hover:shadow-md transition-all cursor-pointer h-full"
        style={{ borderTop: `2px solid ${borderColor}` }}
      >
        <div className="text-[13px] font-medium text-[#374151] mb-3 line-clamp-2 leading-snug">
          {market.q}
        </div>
        <div className="space-y-1">
          {market.top_outcomes.slice(0, 3).map((o, i) => (
            <div key={i} className="flex items-center justify-between gap-2">
              <span className="text-xs text-[#6B7280] truncate flex-1">{o.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <div className="w-14 h-1.5 bg-[#F3F4F6] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.max(3, o.prob)}%`, background: probColor(o.prob) }}
                  />
                </div>
                <span className="font-mono text-xs font-semibold tabular-nums w-8 text-right" style={{ color: probColor(o.prob) }}>
                  {Math.round(o.prob)}%
                </span>
              </div>
            </div>
          ))}
        </div>
        {market.outcome_count > 3 && (
          <div className="text-[10px] text-[#9CA3AF] mt-1.5">+{market.outcome_count - 3} more</div>
        )}
        <div className="mt-2.5">
          <SourceChip src={market.src} />
        </div>
      </div>
    </Link>
  );
}

function ThemeSectionHeader({ theme, count }: { theme: string; count: number }) {
  const meta = THEME_META[theme] || { label: theme, title: "" };
  const color = THEME_COLOR[theme] || THEME_COLOR.other;
  return (
    <div className="mb-5 flex items-end justify-between gap-4 flex-wrap">
      <div>
        <span className="text-[11px] font-bold tracking-[0.12em] uppercase" style={{ color }}>
          {meta.label}
        </span>
        <h2 className="text-[28px] font-semibold text-[#111827] leading-tight mt-1 tracking-tight">
          {meta.title}
        </h2>
      </div>
      <span className="text-[11px] font-semibold text-[#6B7280] bg-[#F3F4F6] px-2.5 py-1 rounded-full shrink-0">
        {count} active
      </span>
    </div>
  );
}

function MarketGrid({ markets, theme }: { markets: PoliticsMarketRow[]; theme: string }) {
  if (!markets || markets.length === 0) return null;
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {markets.map((m, i) => (
        <MarketCard key={i} market={m} theme={theme} />
      ))}
    </div>
  );
}

function SimpleSection({ id, theme, markets, count }: {
  id: string; theme: string; markets: PoliticsMarketRow[]; count: number;
}) {
  if (!markets || markets.length === 0) return null;
  return (
    <section id={id} className="mb-12 scroll-mt-20">
      <ThemeSectionHeader theme={theme} count={count} />
      <MarketGrid markets={markets} theme={theme} />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Main Page                                                           */
/* ------------------------------------------------------------------ */

export default function PoliticsPage() {
  usePageTracking({ pageType: "politics", pageTitle: "Politics Dashboard" });
  useScrollDepth({ pageType: "politics" });
  useEngagementTime({ pageType: "politics" });

  const { data, error } = useSWR("politics-data", fetchPolitics, { refreshInterval: 60000 });

  if (error) return (
    <div className="max-w-5xl mx-auto py-20 text-center text-text-muted text-sm">
      Failed to load politics data
    </div>
  );

  if (!data) return (
    <div className="max-w-5xl mx-auto py-20 text-center text-text-muted text-sm animate-pulse">
      Loading politics markets...
    </div>
  );

  const t = data.themes;
  const pres = t.presidential;

  return (
    <div className="-mx-3 md:-mx-6 -mt-4" style={{ background: "#FAFBFC" }}>
      {/* Hero header */}
      <div className="px-4 md:px-6 pt-10 pb-6" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <span className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            Live
          </span>
          <span className="font-mono text-xs text-[#9CA3AF]">
            {data.total_markets.toLocaleString()} markets
          </span>
          <span className="flex items-center gap-1.5">
            <SourceChip src="kalshi" />
            <SourceChip src="polymarket" />
          </span>
        </div>
        <h1 className="text-[42px] md:text-[56px] font-semibold text-[#111827] leading-[1.1] tracking-tight">
          What do markets think about{" "}
          <span className="italic text-[#4338CA]" style={{ fontFamily: "'Georgia', serif" }}>politics</span>?
        </h1>
        <p className="text-base text-[#6B7280] mt-4 max-w-[640px]">
          {data.total_markets.toLocaleString()} political prediction markets from Kalshi and Polymarket translated into
          plain probabilities. Elections, policy, courts — no odds, just percentages.
        </p>
      </div>

      {/* Jump links */}
      <div className="px-4 md:px-6 pb-8 sticky top-0 z-10 bg-[#FAFBFC]/95 backdrop-blur-sm" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <JumpChips />
      </div>

      <div className="px-4 md:px-6 pb-16" style={{ maxWidth: 1440, margin: "0 auto" }}>
        {/* Presidential hero */}
        {pres && pres.count > 0 && (
          <section id="presidential" className="mb-12 scroll-mt-20">
            <ThemeSectionHeader theme="presidential" count={pres.count} />

            {pres.headline && (
              <Card className="mb-4" style={{ borderTop: "3px solid #3B82F6" }}>
                <div className="flex justify-between items-start mb-4 flex-wrap gap-2">
                  <div>
                    <h3 className="text-xl font-semibold text-[#111827]">
                      {pres.headline.q}
                    </h3>
                    <p className="text-[13px] text-[#6B7280] mt-1">
                      {pres.headline.outcome_count} candidates &middot; Market-implied probability
                    </p>
                  </div>
                  <SourceChip src={pres.headline.src} />
                </div>
                <div className="space-y-0.5">
                  {pres.headline.candidates.slice(0, 8).map((c, i) => (
                    <CandidateBar key={i} name={c.name} prob={c.prob} rank={i} />
                  ))}
                </div>
                {pres.headline.outcome_count > 8 && (
                  <Link href={`/futures/${pres.headline.market_id}`}>
                    <div className="mt-3 text-sm font-medium text-[#3B82F6] hover:text-[#2563EB] transition-colors">
                      View all {pres.headline.outcome_count} candidates &rarr;
                    </div>
                  </Link>
                )}
                <FooterNote
                  left={`${pres.headline.outcome_count} total candidates`}
                  right="Updates hourly"
                />
              </Card>
            )}

            {/* Presidential side markets */}
            {pres.side_markets && pres.side_markets.length > 0 && (
              <MarketGrid markets={pres.side_markets} theme="presidential" />
            )}
          </section>
        )}

        {/* Congressional */}
        <SimpleSection id="congressional" theme="congressional" markets={t.congressional?.markets} count={t.congressional?.count || 0} />

        {/* Gubernatorial */}
        <SimpleSection id="gubernatorial" theme="gubernatorial" markets={t.gubernatorial?.markets} count={t.gubernatorial?.count || 0} />

        {/* Policy */}
        <SimpleSection id="policy" theme="policy" markets={t.policy?.markets} count={t.policy?.count || 0} />

        {/* SCOTUS */}
        <SimpleSection id="scotus" theme="scotus" markets={t.scotus?.markets} count={t.scotus?.count || 0} />

        {/* International */}
        <SimpleSection id="international" theme="international" markets={t.international?.markets} count={t.international?.count || 0} />

        {/* Other */}
        <SimpleSection id="other" theme="other" markets={t.other?.markets} count={t.other?.count || 0} />
      </div>

      {/* Footer */}
      <footer className="border-t border-[#E5E7EB]" style={{ background: "#fff" }}>
        <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-[#9CA3AF]">
          <span>
            Data from{" "}
            <span className="font-medium text-[#6B7280]">Kalshi</span> &amp;{" "}
            <span className="font-medium text-[#6B7280]">Polymarket</span>{" "}
            prediction markets &middot; Not political advice.
          </span>
          <span className="font-mono">
            bainluck.com/politics &middot; {data.total_markets.toLocaleString()} active
          </span>
        </div>
      </footer>
    </div>
  );
}
