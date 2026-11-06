"use client";

import React, { useState } from "react";
import type { EconData, EconDistribution } from "@/lib/api";
import { ratePathHeading } from "@/lib/fedRatePath";
import {
  BinaryRow,
  BucketDistribution,
  ReleaseCard,
  ThresholdLadderCard,
  type AtlasCategoryOutcome,
} from "@/components/atlas/CategoryAtlasComponents";

function parseLeadingNumber(label: string): number | null {
  const m = /(-?\d+(?:\.\d+)?)/.exec(label || "");
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function toProb01(prob: number | null | undefined): number | null {
  return typeof prob === "number" && Number.isFinite(prob) ? prob / 100 : null;
}

function toRenderedPct(prob: number | null | undefined): number | null {
  return typeof prob === "number" && Number.isFinite(prob)
    ? Math.round(prob)
    : null;
}

function orderPairsNumerically(
  pairs: [number | null | undefined, string][]
): [number | null | undefined, string][] {
  const withIdx = pairs.map((item, idx) => ({
    item,
    idx,
    num: parseLeadingNumber(item[1]),
  }));
  const numericCount = withIdx.filter((x) => x.num !== null).length;
  if (numericCount < 2) return pairs;
  return [...withIdx]
    .sort((a, b) => {
      if (a.num !== null && b.num !== null && a.num !== b.num) {
        return a.num - b.num;
      }
      if (a.num !== null && b.num === null) return -1;
      if (a.num === null && b.num !== null) return 1;
      return a.idx - b.idx;
    })
    .map((x) => x.item);
}

export function cleanSource(src?: string | null): string | null {
  return typeof src === "string" && src.trim().length > 0 ? src.trim() : null;
}

function pairsToOutcomes(
  pairs: [number | null | undefined, string][] | undefined,
  orderNumeric = true
): AtlasCategoryOutcome[] {
  if (!Array.isArray(pairs)) return [];
  const valid = pairs.filter(
    (p): p is [number | null | undefined, string] =>
      Array.isArray(p) && typeof p[1] === "string" && p[1].trim().length > 0
  );
  const ordered = orderNumeric ? orderPairsNumerically(valid) : valid;
  return ordered.map(([prob, label], idx) => {
    const trimmed = label.trim();
    return {
      id: `${trimmed}-${idx}`,
      label: trimmed,
      probability: toProb01(prob),
      renderedPercent: toRenderedPct(prob),
    };
  });
}

function renderSideBinaryRow(m: any, i: number) {
  const leader = typeof m?.leader === "string" ? m.leader.trim() : "";
  const q = typeof m?.q === "string" ? m.q.trim() : "";
  const label = leader || q;
  if (!label) return null;
  return (
    <BinaryRow
      key={m.market_id ?? i}
      meta={{
        marketId: m.market_id ?? null,
        marketTitle: leader && q ? `${q} — ${leader}` : label,
        source: cleanSource(m.src),
      }}
      outcome={{
        id: m.market_id ?? i,
        label,
        probability: toProb01(m.prob),
        renderedPercent: toRenderedPct(m.prob),
      }}
    />
  );
}

function renderDistributionBlock(dist: EconDistribution, key: string | number) {
  if (!dist.rows?.length) return null;
  const outcomes = pairsToOutcomes(dist.rows, true);
  if (outcomes.length === 0) return null;
  if (dist.kind === "ladder") {
    return (
      <ThresholdLadderCard
        key={key}
        meta={{
          marketTitle: dist.q,
          source: cleanSource(dist.src),
        }}
        rungs={outcomes}
      />
    );
  }
  return (
    <BucketDistribution
      key={key}
      meta={{
        marketTitle: dist.q,
        source: cleanSource(dist.src),
      }}
      buckets={outcomes}
    />
  );
}

export default function EconomicsAtlasView({ data }: { data: EconData }) {
  const [showAllMeetings, setShowAllMeetings] = useState(false);
  const t = data.themes;
  const meetings = t.fed?.fomc_meetings ?? [];
  const visibleMeetings = showAllMeetings ? meetings : meetings.slice(0, 3);
  const hiddenMeetingCount = Math.max(0, meetings.length - visibleMeetings.length);

  return (
    <div
      data-testid="economics-atlas-view"
      className="max-w-[1120px] mx-auto px-4 md:px-6 py-8 space-y-12"
    >
      {/* Hero */}
      <section data-section="HERO">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          ECONOMICS · PROBABILITY FIRST
        </p>
        <h1 className="text-3xl md:text-5xl font-semibold text-text-primary leading-[1.1] tracking-tight mt-1.5">
          What do markets think about{" "}
          <span className="italic text-accent-brand" style={{ fontFamily: "'Georgia', serif" }}>
            the economy
          </span>
          ?
        </h1>
        <p className="text-base text-text-secondary mt-3 max-w-[640px]">
          Economic prediction markets translated into plain probabilities. Rates,
          inflation, jobs, and GDP — one calibrated reading per market.
        </p>
      </section>

      {/* Federal Reserve */}
      {t.fed && t.fed.count > 0 && (
        <section data-section="FED" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              FEDERAL RESERVE
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              {ratePathHeading(meetings)}
            </h2>
          </div>

          {visibleMeetings.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {visibleMeetings.map((m: any, idx: number) => (
                <BucketDistribution
                  key={`${m.date ?? idx}`}
                  meta={{
                    kicker: `FOMC · ${m.date || m.mo || "Meeting"}`,
                    marketTitle: `${m.mo || m.date || "FOMC"} Fed funds rate`,
                    source: cleanSource(m.src),
                  }}
                  buckets={pairsToOutcomes(m.dist, true)}
                />
              ))}
            </div>
          )}

          {hiddenMeetingCount > 0 && (
            <button
              type="button"
              onClick={() => setShowAllMeetings(true)}
              className="text-xs font-medium text-accent-brand hover:underline"
              data-testid="economics-atlas-all-meetings"
            >
              All {meetings.length} meetings ›
            </button>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {t.fed.rate_cuts && t.fed.rate_cuts.length > 0 && (
              <BucketDistribution
                meta={{
                  kicker: "RATE CUTS",
                  marketTitle: "How many cuts in 2026?",
                  source: null,
                }}
                buckets={pairsToOutcomes(t.fed.rate_cuts as [number, string][], true)}
              />
            )}

            {t.fed.side_markets && t.fed.side_markets.length > 0 && (
              <div className="space-y-2.5">
                {t.fed.side_markets.map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Inflation & Consumer Prices */}
      {t.inflation && t.inflation.count > 0 && (
        <section data-section="INFLATION" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              INFLATION &amp; CONSUMER PRICES
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Inflation releases · Market expectations
            </h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-4 items-start">
            <div className="space-y-4">
              {t.inflation.cpi_releases?.map((cpi: any, i: number) => {
                const outcomes = pairsToOutcomes(cpi.brackets, true);
                const releaseAt = cpi.release_at ?? cpi.releaseAt ?? null;
                if (cpi.is_next && releaseAt) {
                  return (
                    <ReleaseCard
                      key={i}
                      meta={{
                        kicker: "NEXT RELEASE",
                        marketTitle: cpi.q || cpi.mo || "Inflation release",
                        source: cleanSource(cpi.src),
                      }}
                      releaseAt={releaseAt}
                      shape="buckets"
                      outcomes={outcomes}
                    />
                  );
                }
                return (
                  <BucketDistribution
                    key={i}
                    meta={{
                      kicker: cpi.is_next ? "NEXT RELEASE" : cpi.mo || "INFLATION",
                      marketTitle: cpi.q || cpi.mo || "Inflation release",
                      source: cleanSource(cpi.src),
                    }}
                    buckets={outcomes}
                  />
                );
              })}
            </div>

            {t.inflation.side_markets && t.inflation.side_markets.length > 0 && (
              <div className="space-y-2.5">
                {t.inflation.side_markets.map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Jobs & Employment */}
      {t.jobs && t.jobs.count > 0 && (
        <section data-section="JOBS" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              JOBS &amp; EMPLOYMENT
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Monthly reports &amp; weekly claims
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {t.jobs.markets?.map((m: any, i: number) => renderSideBinaryRow(m, i))}
          </div>
        </section>
      )}

      {/* GDP & Recession */}
      {t.recession && t.recession.count > 0 && (
        <section data-section="RECESSION" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              GDP &amp; RECESSION
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Macro growth &amp; recession probabilities
            </h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-4 items-start">
            <div className="space-y-2.5">
              {t.recession.main_q && String(t.recession.main_q).trim() && (
                <BinaryRow
                  meta={{
                    kicker: "HEADLINE MACRO",
                    marketTitle: String(t.recession.main_q).trim(),
                  }}
                  outcome={{
                    id: "recession-main",
                    label: String(t.recession.main_q).trim(),
                    probability: toProb01(t.recession.main_prob),
                    renderedPercent: toRenderedPct(t.recession.main_prob),
                  }}
                />
              )}
              {t.recession.side_markets?.map((m: any, i: number) => renderSideBinaryRow(m, i))}
            </div>

            {t.recession.gdp_quarters && t.recession.gdp_quarters.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {t.recession.gdp_quarters.map((gdp: any, i: number) => (
                  <BucketDistribution
                    key={i}
                    meta={{
                      kicker: "QUARTERLY GDP",
                      marketTitle: gdp.q,
                    }}
                    buckets={pairsToOutcomes(gdp.dist, true)}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Markets & Indices */}
      {t.markets && t.markets.count > 0 && (
        <section data-section="MARKETS" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              MARKETS &amp; INDICES
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Indices &amp; equities
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {t.markets.today && t.markets.today.length > 0 && (
              <div className="space-y-2.5">
                {t.markets.today.map((idx: any, i: number) => {
                  const sym = typeof idx?.sym === "string" ? idx.sym.trim() : "";
                  if (!sym) return null;
                  return (
                    <BinaryRow
                      key={i}
                      meta={{
                        kicker: "TODAY'S CLOSE",
                        marketTitle: `${sym} ${idx.dir || ""}`.trim(),
                        source: cleanSource(idx.src),
                      }}
                      outcome={{
                        id: `idx-${i}`,
                        label: sym,
                        probability: toProb01(idx.prob),
                        renderedPercent: toRenderedPct(idx.prob),
                      }}
                    />
                  );
                })}
              </div>
            )}
            {t.markets.stocks && t.markets.stocks.length > 0 && (
              <div className="space-y-2.5">
                {t.markets.stocks.map((s: any, i: number) => {
                  const sym = typeof s?.sym === "string" ? s.sym.trim() : "";
                  if (!sym) return null;
                  return (
                    <BinaryRow
                      key={i}
                      meta={{
                        kicker: "SINGLE STOCK",
                        marketTitle: `${sym} — up today`,
                        source: cleanSource(s.src),
                      }}
                      outcome={{
                        id: `stock-${i}`,
                        label: sym,
                        probability: toProb01(s.prob),
                        renderedPercent: toRenderedPct(s.prob),
                      }}
                    />
                  );
                })}
              </div>
            )}
            {t.markets.side_markets && t.markets.side_markets.length > 0 && (
              <div className="space-y-2.5">
                {t.markets.side_markets.slice(0, 5).map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Energy */}
      {t.energy && t.energy.count > 0 && (
        <section data-section="ENERGY" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              ENERGY
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Gas, oil, and the price at the pump
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {t.energy.gas?.map((g: any, i: number) => (
              <BucketDistribution
                key={i}
                meta={{
                  kicker: "GASOLINE",
                  marketTitle: g.label || "Gas price",
                  source: cleanSource(g.src),
                }}
                buckets={pairsToOutcomes(g.brackets, true)}
              />
            ))}
            {t.energy.oil && t.energy.oil.length > 0 && (
              <div className="space-y-2.5">
                {t.energy.oil.map((o: any, i: number) => {
                  const title = (o.sym ? `${o.sym} ${o.range || ""}`.trim() : o.q || "").trim();
                  const label = (typeof o.leader === "string" && o.leader.trim() ? o.leader.trim() : title);
                  if (!label) return null;
                  return (
                    <BinaryRow
                      key={o.market_id ?? i}
                      meta={{
                        marketId: o.market_id ?? null,
                        marketTitle: title || label,
                        source: cleanSource(o.src),
                      }}
                      outcome={{
                        id: o.market_id ?? i,
                        label,
                        probability: toProb01(o.prob),
                        renderedPercent: toRenderedPct(o.prob),
                      }}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Metals */}
      {t.metals && t.metals.count > 0 && (
        <section data-section="METALS" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              METALS
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Gold, silver, and copper
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {t.metals.cards?.map((c: any, i: number) => (
              <BucketDistribution
                key={i}
                meta={{
                  kicker: "METALS",
                  marketTitle: c.label || "Metal price",
                  source: cleanSource(c.src),
                }}
                buckets={pairsToOutcomes(c.brackets, true)}
              />
            ))}
            {t.metals.markets && t.metals.markets.length > 0 && (
              <div className="space-y-2.5">
                {t.metals.markets.map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Housing */}
      {t.housing && t.housing.count > 0 && (
        <section data-section="HOUSING" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              HOUSING &amp; MORTGAGES
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Rates &amp; housing markets
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr] gap-4">
            {t.housing.mortgage_dist &&
              renderDistributionBlock(t.housing.mortgage_dist, "mortgage")}
            {t.housing.markets && t.housing.markets.length > 0 && (
              <div className="space-y-2.5">
                {t.housing.markets.map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Trade & Tariffs */}
      {t.trade && t.trade.count > 0 && (
        <section data-section="TRADE" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              TRADE &amp; TARIFFS
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Trade &amp; tariff probabilities
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {t.trade.markets?.map((m: any, i: number) => renderSideBinaryRow(m, i))}
          </div>
        </section>
      )}

      {/* Government & Fiscal */}
      {t.government &&
        ((t.government.markets?.length ?? 0) > 0 ||
          (t.government.distributions?.length ?? 0) > 0) && (
          <section data-section="GOVERNMENT" className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                GOVERNMENT &amp; FISCAL
              </p>
              <h2 className="text-xl font-semibold text-text-primary mt-0.5">
                Shutdowns, debt, and fiscal policy
              </h2>
            </div>
            {t.government.markets && t.government.markets.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {t.government.markets.map((m: any, i: number) => renderSideBinaryRow(m, i))}
              </div>
            )}
            {t.government.distributions && t.government.distributions.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {t.government.distributions.map((d, i) => renderDistributionBlock(d, i))}
              </div>
            )}
          </section>
        )}
    </div>
  );
}
