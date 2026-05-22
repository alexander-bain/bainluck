"use client";

import { useState, useEffect, useCallback } from "react";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com";

interface MarketItem {
  item_id: string;
  item_name: string | null;
  score: number | null;
  engagement_rate: number;
  impressions: number;
}

interface CategoryRow {
  category: string;
  avg_score: number | null;
  avg_engagement_rate: number;
  market_count: number;
  total_impressions: number;
  top_markets: MarketItem[];
  bottom_markets: MarketItem[];
}

interface ScoreBucket {
  score_range: string;
  market_count: number;
  total_impressions: number;
  total_opens: number;
  total_shares: number;
  total_likes: number;
  total_dismisses: number;
  avg_engagement_rate: number;
}

interface OpportunityItem {
  item_id: string;
  item_name: string | null;
  category: string;
  score: number | null;
  engagement_rate: number;
  impressions: number;
  verdict: string;
}

interface ReviewData {
  generated_at: string;
  window_hours: number;
  total_markets_with_interactions: number;
  by_category: CategoryRow[];
  score_buckets: ScoreBucket[];
  opportunities: {
    under_ranked: OpportunityItem[];
    over_ranked: OpportunityItem[];
  };
  status?: string;
  message?: string;
}

function verdict(avgEngagement: number, overallAvg: number): string {
  if (overallAvg === 0) return "ok";
  const ratio = avgEngagement / overallAvg;
  if (ratio >= 1.3) return "under-ranked";
  if (ratio <= 0.7) return "over-ranked";
  return "ok";
}

function verdictColor(v: string): string {
  if (v === "under-ranked") return "text-accent-live bg-accent-live/10";
  if (v === "over-ranked") return "text-accent-danger bg-accent-danger/10";
  return "text-text-secondary bg-surface-card";
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function EngagementReviewTab() {
  const { secret } = useAdminAuth();
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/api/admin/engagement/review?secret=${encodeURIComponent(secret)}`
      );
      if (!res.ok) {
        const text = await res.text();
        setError(`API error ${res.status}: ${text}`);
        return;
      }
      setData(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [secret]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const overallAvg =
    data?.by_category && data.by_category.length > 0
      ? data.by_category.reduce(
          (sum: number, c: CategoryRow) => sum + c.avg_engagement_rate * c.market_count,
          0
        ) /
        data.by_category.reduce((sum: number, c: CategoryRow) => sum + c.market_count, 0)
      : 0;

  if (loading) return <p className="text-text-muted py-8">Loading engagement data...</p>;

  if (error) return (
    <div className="bg-accent-danger/5 border border-accent-danger/20 rounded-lg p-4 mb-6">
      <p className="text-accent-danger text-sm">{error}</p>
    </div>
  );

  if (!data || !data.by_category) return <p className="text-text-muted py-8">No engagement data available.</p>;

  if (data.status === "no_data") return (
    <div className="bg-accent-warning/5 border border-accent-warning/20 rounded-lg p-4 mb-6">
      <p className="text-accent-warning text-sm">{data.message}</p>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex gap-6 text-sm text-text-secondary">
        <span>Generated: {new Date(data.generated_at).toLocaleString()}</span>
        <span>Window: {data.window_hours}h</span>
        <span>Markets: {data.total_markets_with_interactions}</span>
        <button onClick={fetchData} className="text-accent-brand hover:underline">Refresh</button>
      </div>

      <section>
        <h2 className="text-sm font-semibold text-text-primary mb-3">By Category</h2>
        <div className="overflow-x-auto rounded-lg border border-surface-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-elevated text-text-muted text-xs">
                <th className="text-left font-medium p-3">Category</th>
                <th className="text-right font-medium p-3">Avg Score</th>
                <th className="text-right font-medium p-3">Engagement</th>
                <th className="text-right font-medium p-3">Impressions</th>
                <th className="text-right font-medium p-3">Markets</th>
                <th className="text-center font-medium p-3">Verdict</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/60">
              {data.by_category.map((cat) => {
                const v = verdict(cat.avg_engagement_rate, overallAvg);
                const isExpanded = expandedCategory === cat.category;
                return (
                  <tr
                    key={cat.category}
                    className="hover:bg-surface-elevated/40 cursor-pointer"
                    onClick={() => setExpandedCategory(isExpanded ? null : cat.category)}
                  >
                    <td className="p-3 text-text-primary font-medium">
                      {cat.category}
                      {isExpanded && cat.top_markets.length > 0 && (
                        <div className="mt-2 bg-surface-elevated/50 rounded-lg p-3">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <h4 className="text-[10px] font-semibold text-text-muted mb-2 uppercase">Top Markets</h4>
                              {cat.top_markets.map((m) => (
                                <div key={m.item_id} className="text-xs text-text-primary mb-1 truncate">
                                  {pct(m.engagement_rate)} — {m.item_name || m.item_id}{" "}
                                  <span className="text-text-muted">(score: {m.score ?? "—"}, {m.impressions} imp)</span>
                                </div>
                              ))}
                            </div>
                            {cat.bottom_markets.length > 0 && (
                              <div>
                                <h4 className="text-[10px] font-semibold text-text-muted mb-2 uppercase">Bottom Markets</h4>
                                {cat.bottom_markets.map((m) => (
                                  <div key={m.item_id} className="text-xs text-text-primary mb-1 truncate">
                                    {pct(m.engagement_rate)} — {m.item_name || m.item_id}{" "}
                                    <span className="text-text-muted">(score: {m.score ?? "—"}, {m.impressions} imp)</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="p-3 text-right text-text-primary align-top">{cat.avg_score !== null ? cat.avg_score.toFixed(1) : "—"}</td>
                    <td className="p-3 text-right text-text-primary align-top">{pct(cat.avg_engagement_rate)}</td>
                    <td className="p-3 text-right text-text-secondary align-top">{cat.total_impressions.toLocaleString()}</td>
                    <td className="p-3 text-right text-text-secondary align-top">{cat.market_count}</td>
                    <td className="p-3 text-center align-top">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${verdictColor(v)}`}>{v}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-text-primary mb-2">Score Buckets</h2>
        <p className="text-xs text-text-muted mb-3">Does higher score correlate with higher engagement?</p>
        <div className="overflow-x-auto rounded-lg border border-surface-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-elevated text-text-muted text-xs">
                <th className="text-left font-medium p-3">Score Range</th>
                <th className="text-right font-medium p-3">Markets</th>
                <th className="text-right font-medium p-3">Impressions</th>
                <th className="text-right font-medium p-3">Engagement</th>
                <th className="text-right font-medium p-3">Opens</th>
                <th className="text-right font-medium p-3">Dismisses</th>
                <th className="text-right font-medium p-3">Shares</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/60">
              {data.score_buckets.map((b) => (
                <tr key={b.score_range} className="hover:bg-surface-elevated/40">
                  <td className="p-3 text-text-primary font-medium">{b.score_range}</td>
                  <td className="p-3 text-right text-text-secondary">{b.market_count}</td>
                  <td className="p-3 text-right text-text-secondary">{b.total_impressions.toLocaleString()}</td>
                  <td className="p-3 text-right text-text-primary font-medium">{pct(b.avg_engagement_rate)}</td>
                  <td className="p-3 text-right text-text-secondary">{b.total_opens}</td>
                  <td className="p-3 text-right text-text-secondary">{b.total_dismisses}</td>
                  <td className="p-3 text-right text-text-secondary">{b.total_shares}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-text-primary mb-3">Opportunities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h3 className="text-xs font-semibold text-accent-live mb-2 uppercase">Under-Ranked (high engagement, low score)</h3>
            {data.opportunities.under_ranked.length === 0 ? (
              <p className="text-text-muted text-xs">No under-ranked markets.</p>
            ) : (
              <div className="space-y-2">
                {data.opportunities.under_ranked.map((m) => (
                  <div key={m.item_id} className="bg-accent-live/5 border border-accent-live/20 rounded-lg p-3">
                    <div className="text-sm text-text-primary font-medium truncate">{m.item_name || m.item_id}</div>
                    <div className="text-xs text-text-secondary mt-1 flex gap-3">
                      <span>{m.category}</span>
                      <span>Score: {m.score ?? "—"}</span>
                      <span>Engagement: {pct(m.engagement_rate)}</span>
                      <span>{m.impressions} imp</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <h3 className="text-xs font-semibold text-accent-danger mb-2 uppercase">Over-Ranked (low engagement, high score)</h3>
            {data.opportunities.over_ranked.length === 0 ? (
              <p className="text-text-muted text-xs">No over-ranked markets.</p>
            ) : (
              <div className="space-y-2">
                {data.opportunities.over_ranked.map((m) => (
                  <div key={m.item_id} className="bg-accent-danger/5 border border-accent-danger/20 rounded-lg p-3">
                    <div className="text-sm text-text-primary font-medium truncate">{m.item_name || m.item_id}</div>
                    <div className="text-xs text-text-secondary mt-1 flex gap-3">
                      <span>{m.category}</span>
                      <span>Score: {m.score ?? "—"}</span>
                      <span>Engagement: {pct(m.engagement_rate)}</span>
                      <span>{m.impressions} imp</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
