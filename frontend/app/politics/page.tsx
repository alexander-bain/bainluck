"use client";

import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  SectionHeader, Card, SourceChip, MarketRow, FooterNote,
  ProbNum, ProbBar, probColor,
} from "@/components/economics/atoms";
import { fetchPolitics } from "@/lib/api";
import type { PoliticsData, PoliticsMarketRow } from "@/lib/api";

function CandidateBar({ name, prob, rank }: { name: string; prob: number; rank: number }) {
  const col = rank === 0 ? "#4338CA" : probColor(prob);
  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="text-[10px] text-[#9CA3AF] w-4 text-right shrink-0">
        {rank + 1}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className={`text-[13px] truncate ${rank === 0 ? "font-bold text-[#111827]" : "text-[#374151]"}`}>
            {name}
          </span>
          <span className="font-mono text-sm font-semibold shrink-0 ml-2" style={{ color: col }}>
            {Math.round(prob)}%
          </span>
        </div>
        <ProbBar value={prob} height={rank === 0 ? 8 : 5} color={col} />
      </div>
    </div>
  );
}

function PoliticsMarketCard({ market }: { market: PoliticsMarketRow }) {
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

function SimpleSection({ theme, markets }: { theme: string; markets: PoliticsMarketRow[] }) {
  if (!markets || markets.length === 0) return null;
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {markets.map((m, i) => (
        <PoliticsMarketCard key={i} market={m} />
      ))}
    </div>
  );
}

const THEME_META: Record<string, { kicker: string; title: string; emoji: string }> = {
  presidential: { kicker: "Presidential", title: "Who's running? Who's winning?", emoji: "🏛" },
  congressional: { kicker: "Congressional", title: "Senate, House, and midterm races", emoji: "🗳" },
  gubernatorial: { kicker: "Gubernatorial", title: "State-level races", emoji: "🏢" },
  policy: { kicker: "Policy & Legislation", title: "Bills, executive orders, and regulatory moves", emoji: "📜" },
  scotus: { kicker: "Supreme Court", title: "Rulings, nominations, and the bench", emoji: "⚖️" },
  international: { kicker: "International", title: "Elections and politics beyond US borders", emoji: "🌍" },
  other: { kicker: "More Politics", title: "Other political markets", emoji: "📊" },
};

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

  return (
    <div className="-mx-3 md:-mx-6 -mt-4" style={{ background: "#FAFBFC" }}>
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <div className="flex items-center gap-3 mb-4">
          <span className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            Politics markets · Live
          </span>
          <span className="font-mono text-xs text-[#9CA3AF]">
            {data.total_markets.toLocaleString()} active · Kalshi {data.by_source.kalshi.toLocaleString()} · Polymarket {data.by_source.polymarket.toLocaleString()}
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

      <div className="px-4 md:px-6 pb-16" style={{ maxWidth: 1440, margin: "0 auto" }}>

        {/* Presidential */}
        {t.presidential && t.presidential.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Presidential 2028"
              title="The race for the White House"
              meta={t.presidential.headline ? `${t.presidential.headline.outcome_count} candidates tracked` : undefined}
              count={t.presidential.count}
            />
            <div className="grid md:grid-cols-[1.4fr_1fr] gap-3.5">
              {t.presidential.headline && (
                <Card>
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="text-xl font-semibold text-[#111827]">
                        {t.presidential.headline.q.length > 50
                          ? t.presidential.headline.q.slice(0, 50) + "..."
                          : t.presidential.headline.q}
                      </h3>
                      <p className="text-[13px] text-[#6B7280] mt-1">Market-implied probability by candidate</p>
                    </div>
                    <SourceChip src={t.presidential.headline.src} />
                  </div>
                  <div className="space-y-0.5">
                    {t.presidential.headline.candidates.map((c, i) => (
                      <CandidateBar key={i} name={c.name} prob={c.prob} rank={i} />
                    ))}
                  </div>
                  <FooterNote
                    left={`${t.presidential.headline.outcome_count} total candidates`}
                    right="Updates hourly"
                  />
                </Card>
              )}
              {t.presidential.side_markets && t.presidential.side_markets.length > 0 && (
                <div className="flex flex-col gap-3.5">
                  <Card>
                    <div className="text-[11px] font-bold tracking-[0.12em] text-[#9CA3AF] uppercase mb-2">
                      Related markets
                    </div>
                    {t.presidential.side_markets.map((m, i) => (
                      <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                    ))}
                  </Card>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Congressional */}
        {t.congressional && t.congressional.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Congressional" title="Senate, House, and midterm races" count={t.congressional.count} />
            <SimpleSection theme="congressional" markets={t.congressional.markets} />
          </section>
        )}

        {/* Gubernatorial */}
        {t.gubernatorial && t.gubernatorial.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Gubernatorial" title="State-level races" count={t.gubernatorial.count} />
            <SimpleSection theme="gubernatorial" markets={t.gubernatorial.markets} />
          </section>
        )}

        {/* Policy */}
        {t.policy && t.policy.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Policy & Legislation" title="Bills, executive orders, and regulatory moves" count={t.policy.count} />
            <SimpleSection theme="policy" markets={t.policy.markets} />
          </section>
        )}

        {/* Supreme Court */}
        {t.scotus && t.scotus.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Supreme Court" title="Rulings, nominations, and the bench" count={t.scotus.count} />
            <SimpleSection theme="scotus" markets={t.scotus.markets} />
          </section>
        )}

        {/* International */}
        {t.international && t.international.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="International" title="Elections and politics beyond US borders" count={t.international.count} />
            <SimpleSection theme="international" markets={t.international.markets} />
          </section>
        )}

        {/* Other */}
        {t.other && t.other.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="More Politics" title="Other political markets" count={t.other.count} />
            <SimpleSection theme="other" markets={t.other.markets} />
          </section>
        )}
      </div>

      {/* Footer */}
      <footer className="border-t border-[#E5E7EB]" style={{ background: "#fff" }}>
        <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-[#9CA3AF]">
          <span>Data from Kalshi &amp; Polymarket prediction markets · Not political advice.</span>
          <span className="font-mono">
            bainluck.com/politics · {data.total_markets.toLocaleString()} active
          </span>
        </div>
      </footer>
    </div>
  );
}
