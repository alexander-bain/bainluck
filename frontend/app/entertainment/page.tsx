"use client";

import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  SectionHeader, Card, SourceChip,
  ProbBar, probColor,
} from "@/components/economics/atoms";
import { fetchEntertainment } from "@/lib/api";
import type { EntertainmentData, PoliticsMarketRow } from "@/lib/api";

const SECTION_ORDER = [
  "movies", "tv_streaming", "music", "awards", "social_media", "celebrity", "viral", "other",
];

const SECTION_KICKER: Record<string, string> = {
  movies: "Movies & Box Office",
  tv_streaming: "TV & Streaming",
  music: "Music",
  awards: "Awards Season",
  social_media: "Social Media & Creators",
  celebrity: "Celebrity",
  viral: "Viral & Novelty",
  other: "More Entertainment",
};

function MarketCard({ market }: { market: PoliticsMarketRow }) {
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 hover:shadow-md transition-all cursor-pointer h-full">
        <div className="text-[13px] font-medium text-[#374151] mb-3 line-clamp-2 leading-snug">
          {market.q}
        </div>
        <div className="space-y-0.5">
          {market.top_outcomes.map((o, i) => (
            <div key={i} className="flex items-center justify-between gap-2">
              <span className="text-xs text-[#6B7280] truncate flex-1">{o.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <div className="w-12 h-1.5 bg-[#F3F4F6] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.max(3, o.prob)}%`, background: probColor(o.prob) }}
                  />
                </div>
                <span className="font-mono text-xs font-semibold w-8 text-right" style={{ color: probColor(o.prob) }}>
                  {Math.round(o.prob)}%
                </span>
              </div>
            </div>
          ))}
        </div>
        {market.outcome_count > 3 && (
          <div className="text-[10px] text-[#9CA3AF] mt-1.5">+{market.outcome_count - 3} more</div>
        )}
        <div className="mt-2">
          <SourceChip src={market.src} />
        </div>
      </div>
    </Link>
  );
}

export default function EntertainmentPage() {
  usePageTracking({ pageType: "entertainment", pageTitle: "Entertainment Dashboard" });
  useScrollDepth({ pageType: "entertainment" });
  useEngagementTime({ pageType: "entertainment" });

  const { data, error } = useSWR("entertainment-data", fetchEntertainment, { refreshInterval: 60000 });

  if (error) return (
    <div className="max-w-5xl mx-auto py-20 text-center text-text-muted text-sm">
      Failed to load entertainment data
    </div>
  );

  if (!data) return (
    <div className="max-w-5xl mx-auto py-20 text-center text-text-muted text-sm animate-pulse">
      Loading entertainment markets...
    </div>
  );

  return (
    <div className="-mx-3 md:-mx-6 -mt-4" style={{ background: "#FAFBFC" }}>
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <div className="flex items-center gap-3 mb-4">
          <span className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
            Entertainment markets · Live
          </span>
          <span className="font-mono text-xs text-[#9CA3AF]">
            {data.total_markets.toLocaleString()} active · Kalshi {data.by_source.kalshi.toLocaleString()} · Polymarket {data.by_source.polymarket.toLocaleString()}
          </span>
        </div>
        <h1 className="text-[42px] md:text-[56px] font-semibold text-[#111827] leading-[1.1] tracking-tight">
          What do markets think about{" "}
          <span className="italic text-[#7C3AED]" style={{ fontFamily: "'Georgia', serif" }}>culture</span>?
        </h1>
        <p className="text-base text-[#6B7280] mt-4 max-w-[640px]">
          Box office predictions, streaming wars, music charts, awards races, and viral moments —
          all translated into plain probabilities from Kalshi and Polymarket.
        </p>
      </div>

      <div className="px-4 md:px-6 pb-16" style={{ maxWidth: 1440, margin: "0 auto" }}>
        {SECTION_ORDER.map((key) => {
          const section = data.sections[key];
          if (!section || section.markets.length === 0) return null;
          return (
            <section key={key} className="mb-12">
              <SectionHeader
                kicker={SECTION_KICKER[key] || section.label}
                title={section.label}
                count={section.count}
              />
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {section.markets.map((m, i) => (
                  <MarketCard key={i} market={m} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {/* Footer */}
      <footer className="border-t border-[#E5E7EB]" style={{ background: "#fff" }}>
        <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-[#9CA3AF]">
          <span>Data from Kalshi &amp; Polymarket prediction markets · For entertainment purposes only.</span>
          <span className="font-mono">
            bainluck.com/entertainment · {data.total_markets.toLocaleString()} active
          </span>
        </div>
      </footer>
    </div>
  );
}
