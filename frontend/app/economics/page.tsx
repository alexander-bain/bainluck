"use client";

import useSWR from "swr";
import ErrorBoundary from "@/components/ErrorBoundary";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  SectionHeader, Card, SourceChip, MarketRow, FooterNote,
  ProbNum, ProbBar, Histogram, Delta, probColor,
} from "@/components/economics/atoms";
import ErrorState from "@/components/ErrorState";
import EconomicsSkeleton from "@/components/skeletons/EconomicsSkeleton";
import { fetchEconomics } from "@/lib/api";
import type { EconData } from "@/lib/api";

// ---------------------------------------------------------------------------
// Fed Heatmap Section
// ---------------------------------------------------------------------------

function FedHeatmap({ meetings }: { meetings: any[] }) {
  if (!meetings.length) return null;

  const allLabels = new Set<string>();
  meetings.forEach(m => m.dist?.forEach((d: any) => allLabels.add(d[1])));
  const rates = Array.from(allLabels).sort().reverse();

  const get = (m: any, r: string) => {
    const found = m.dist?.find((d: any) => d[1] === r);
    return found ? found[0] : 0;
  };

  const cellColor = (p: number) => {
    if (p === 0) return "#FAFBFC";
    const intensity = Math.min(1, p / 60);
    return `rgba(16, 185, 129, ${0.08 + intensity * 0.72})`;
  };

  return (
    <div>
      <div className="text-[11px] text-text-secondary mb-2.5 font-mono">
        Probability heatmap · Darker = more likely
      </div>
      <div className="overflow-x-auto">
        <div style={{
          display: "grid",
          gridTemplateColumns: `70px repeat(${meetings.length}, 1fr)`,
          gap: 2,
          minWidth: 500,
        }}>
          <div />
          {meetings.map((m: any, i: number) => (
            <div key={i} className="text-center pb-1.5">
              <div className="text-[11px] font-semibold text-text-secondary">{m.mo || m.date}</div>
              <div className="font-mono text-[9px] text-text-muted">{m.date}</div>
            </div>
          ))}
          {rates.map(r => (
            <div key={r} className="contents">
              <div className="font-mono text-[10px] text-text-secondary text-right pr-2 flex items-center justify-end" style={{ height: 38 }}>
                {r}
              </div>
              {meetings.map((m: any, mi: number) => {
                const prob = get(m, r);
                const modal = m.dist?.reduce((best: number, d: any, i: number) =>
                  d[0] > (m.dist[best]?.[0] || 0) ? i : best, 0) || 0;
                const isModal = m.dist?.[modal]?.[1] === r;
                return (
                  <div key={mi} className="flex items-center justify-center rounded font-mono text-[11px] font-semibold"
                    style={{
                      height: 38,
                      background: cellColor(prob),
                      border: isModal ? "1.5px solid var(--accent-brand)" : "1px solid var(--surface-border)",
                      color: prob >= 30 ? "#064E3B" : prob >= 10 ? "var(--text-secondary)" : "var(--text-muted)",
                    }}>
                    {prob > 0 ? prob : ""}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RateCutsChart({ cuts }: { cuts: [number, string][] }) {
  if (!cuts.length) return null;
  const max = Math.max(...cuts.map(c => c[0]));
  return (
    <div className="flex flex-col gap-2 mt-2">
      {cuts.map(([prob, label], i) => {
        const w = (prob / max) * 100;
        const col = probColor(prob);
        const isModal = prob === max;
        return (
          <div key={i} className="grid items-center gap-2" style={{ gridTemplateColumns: "60px 1fr 40px" }}>
            <span className={`text-xs ${isModal ? "font-semibold text-text-primary" : "font-medium text-text-secondary"}`}>
              {label}
            </span>
            <div className="h-2 bg-surface-secondary rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${w}%`, background: col }} />
            </div>
            <span className="font-mono text-xs font-semibold text-right" style={{ color: col }}>
              {prob}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function EconomicsPage() {
  usePageTracking({ pageType: "economics", pageTitle: "Economics Dashboard" });
  useScrollDepth({ pageType: "economics" });
  useEngagementTime({ pageType: "economics" });

  const { data, error } = useSWR("economics-data", fetchEconomics, { refreshInterval: 60000 });

  if (error) return (
    <div className="max-w-7xl mx-auto">
      <ErrorState message="Failed to load economics data" onRetry={() => window.location.reload()} />
    </div>
  );

  if (!data) return (
    <div className="max-w-7xl mx-auto">
      <EconomicsSkeleton />
    </div>
  );

  const t = data.themes;

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="-mx-3 md:-mx-6 -mt-4 bg-surface-deep">
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <div className="flex items-center gap-3 mb-4">
          <span className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-green-50 text-green-700 border border-green-200">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            Economics markets · Live
          </span>
          <span className="font-mono text-xs text-text-muted">
            {data.total_markets.toLocaleString()} active markets
          </span>
        </div>
        <h1 className="text-[42px] md:text-[56px] font-semibold text-text-primary leading-[1.1] tracking-tight">
          What do markets think about{" "}
          <span className="italic text-accent-brand" style={{ fontFamily: "'Georgia', serif" }}>the economy</span>?
        </h1>
        <p className="text-base text-text-secondary mt-4 max-w-[640px]">
          {data.total_markets.toLocaleString()} economic prediction markets translated into
          plain probabilities. Rates, inflation, jobs, GDP — no odds, just percentages.
        </p>
      </div>

      <div className="px-4 md:px-6 pb-16" style={{ maxWidth: 1440, margin: "0 auto" }}>

        {/* Fed Rates */}
        {t.fed && t.fed.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Federal Reserve"
              title="Rate-path dot plot — but from markets, not the Fed"
              meta={`${t.fed.fomc_meetings?.length || 0} FOMC meetings`}
              count={t.fed.count}
            />
            <div className="grid md:grid-cols-[1.6fr_1fr] gap-3.5">
              <Card>
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-xl font-semibold text-text-primary">2026 rate path</h3>
                    <p className="text-[13px] text-text-secondary mt-1">
                      Market-implied probability of each Fed funds bracket
                    </p>
                  </div>
                  <SourceChip src="kalshi" />
                </div>
                <FedHeatmap meetings={t.fed.fomc_meetings || []} />
                <FooterNote left="Each column = one FOMC meeting" right="Resolves post-FOMC" />
              </Card>
              <div className="flex flex-col gap-3.5">
                {t.fed.rate_cuts && t.fed.rate_cuts.length > 0 && (
                  <Card>
                    <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-1.5">
                      How many cuts in 2026?
                    </div>
                    <RateCutsChart cuts={t.fed.rate_cuts as [number, string][]} />
                    <FooterNote left="Modal outcome highlighted" right="Kalshi" />
                  </Card>
                )}
                {t.fed.side_markets && t.fed.side_markets.length > 0 && (
                  <Card>
                    <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                      Side markets
                    </div>
                    {t.fed.side_markets.map((m: any, i: number) => (
                      <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                    ))}
                  </Card>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Inflation */}
        {t.inflation && t.inflation.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Inflation & Consumer Prices"
              title="CPI releases · Market expectations"
              count={t.inflation.count}
            />
            <div className="grid md:grid-cols-[1.6fr_1fr] gap-3.5">
              <Card>
                {t.inflation.cpi_releases?.map((cpi: any, i: number) => (
                  <div key={i} className="py-3 border-b border-surface-secondary last:border-0">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-text-secondary">{cpi.mo}</span>
                      {cpi.upcoming && (
                        <span className="text-[9px] font-bold tracking-wide bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded-full">
                          NEXT
                        </span>
                      )}
                    </div>
                    {cpi.brackets && (
                      <Histogram buckets={cpi.brackets.slice(0, 8)} color="#10B981" />
                    )}
                  </div>
                ))}
              </Card>
              {t.inflation.side_markets && t.inflation.side_markets.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                    Related markets
                  </div>
                  {t.inflation.side_markets.map((m: any, i: number) => (
                    <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                  ))}
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Jobs */}
        {t.jobs && t.jobs.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Jobs & Employment"
              title="Monthly reports. Weekly claims."
              count={t.jobs.count}
            />
            <Card>
              <div className="grid md:grid-cols-2 gap-x-6">
                {t.jobs.markets?.map((m: any, i: number) => (
                  <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                ))}
              </div>
            </Card>
          </section>
        )}

        {/* GDP & Recession */}
        {t.recession && t.recession.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="GDP & Recession"
              title="The big macro question"
              count={t.recession.count}
            />
            <div className="grid md:grid-cols-[1fr_1.4fr] gap-3.5">
              <Card>
                <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
                  Recession by end of 2026
                </div>
                <div className="mb-4">
                  <ProbNum value={t.recession.main_prob || 0} size={64} />
                </div>
                {t.recession.side_markets?.map((m: any, i: number) => (
                  <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                ))}
              </Card>
              {t.recession.gdp_quarters && t.recession.gdp_quarters.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
                    Quarterly GDP growth expectations
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {t.recession.gdp_quarters.map((gdp: any, i: number) => (
                      <div key={i} className="border border-surface-border rounded-xl p-3">
                        <div className="text-xs font-semibold text-text-secondary mb-2">{gdp.q}</div>
                        <Histogram buckets={(gdp.dist || []).slice(0, 6)} color="#10B981" />
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Markets & Indices */}
        {t.markets && t.markets.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Markets & Indices"
              title="Resolves daily. Highest-velocity section."
              count={t.markets.count}
            />
            <div className="grid md:grid-cols-3 gap-3.5">
              {t.markets.today && t.markets.today.length > 0 && (
                <Card>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase">Today&apos;s close</span>
                    <span className="text-[10px] font-mono text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                      ● LIVE
                    </span>
                  </div>
                  {t.markets.today.map((idx: any, i: number) => (
                    <div key={i} className="flex items-center justify-between py-2 border-t border-surface-secondary">
                      <span className="text-[13px] text-text-secondary">{idx.sym}</span>
                      <span className="font-mono text-[13px] font-semibold" style={{ color: probColor(idx.prob) }}>
                        {idx.prob}% {idx.dir}
                      </span>
                    </div>
                  ))}
                </Card>
              )}
              {t.markets.stocks && t.markets.stocks.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
                    Single stocks — up today?
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    {t.markets.stocks.map((s: any, i: number) => (
                      <div key={i} className="flex items-center justify-between py-1.5 border-b border-surface-secondary">
                        <span className="font-mono text-[11px] text-text-secondary font-medium">{s.sym}</span>
                        <span className="font-mono text-sm font-semibold" style={{ color: probColor(s.prob) }}>
                          {s.prob}%
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
              {t.markets.side_markets && t.markets.side_markets.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                    More markets
                  </div>
                  {t.markets.side_markets.slice(0, 5).map((m: any, i: number) => (
                    <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                  ))}
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Energy */}
        {t.energy && t.energy.count > 0 && (
          <section className="mb-12">
            <SectionHeader
              kicker="Energy & Commodities"
              title="Gas, oil, and the price at the pump"
              count={t.energy.count}
            />
            <div className="grid md:grid-cols-3 gap-3.5">
              {t.energy.gas?.map((g: any, i: number) => (
                <Card key={i}>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                    {g.label?.slice(0, 40) || "Gas price"}
                  </div>
                  <ProbNum value={g.val || "?"} size={32} color="#10B981" suffix="" />
                  <div className="text-xs text-text-secondary mt-1 mb-3">Modal bracket · {g.prob}%</div>
                  <Histogram buckets={g.brackets || []} color="#10B981" height={70} />
                  <FooterNote left={`${g.brackets?.length || 0} brackets`} right={g.src} />
                </Card>
              ))}
              {t.energy.oil && t.energy.oil.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                    Crude oil
                  </div>
                  {t.energy.oil.map((o: any, i: number) => (
                    <MarketRow key={i} q={o.sym ? `${o.sym} ${o.range || ""}` : o.q} prob={o.prob} src={o.src} />
                  ))}
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Housing */}
        {t.housing && t.housing.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Housing & Mortgages" title="Rates, prices, and the American dream" count={t.housing.count} />
            <div className="grid md:grid-cols-[1.2fr_1fr] gap-3.5">
              {t.housing.mortgage_brackets && t.housing.mortgage_brackets.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
                    30-year mortgage rate by end of 2026
                  </div>
                  <Histogram buckets={t.housing.mortgage_brackets as [number, string][]} color="#8B5CF6" height={90} />
                </Card>
              )}
              {t.housing.markets && t.housing.markets.length > 0 && (
                <Card>
                  <div className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-2">
                    Housing markets
                  </div>
                  {t.housing.markets.map((m: any, i: number) => (
                    <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                  ))}
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Trade & Tariffs */}
        {t.trade && t.trade.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Trade & Tariffs" title="The economic story of 2026" count={t.trade.count} />
            <Card>
              <div className="grid md:grid-cols-2 gap-x-6">
                {t.trade.markets?.map((m: any, i: number) => (
                  <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                ))}
              </div>
            </Card>
          </section>
        )}

        {/* Government & Fiscal */}
        {t.government && t.government.count > 0 && (
          <section className="mb-12">
            <SectionHeader kicker="Government & Fiscal" title="Shutdowns, debt, DOGE" count={t.government.count} />
            <Card>
              <div className="grid md:grid-cols-2 gap-x-6">
                {t.government.markets?.map((m: any, i: number) => (
                  <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} />
                ))}
              </div>
            </Card>
          </section>
        )}
      </div>

      {/* Footer */}
      <footer className="border-t border-surface-border bg-surface-card">
        <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-text-muted">
          <span>Prediction market data · Not financial advice.</span>
          <span className="font-mono">
            bainluck.com/economics · {data.total_markets.toLocaleString()} active
          </span>
        </div>
      </footer>
    </div>
    </ErrorBoundary>
  );
}
