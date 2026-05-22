"use client";

import { useState, useEffect, useCallback } from "react";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";

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
  if (v === "under-ranked") return "text-green-700 bg-green-50";
  if (v === "over-ranked") return "text-red-700 bg-red-50";
  return "text-text-secondary bg-surface-card";
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function EngagementReviewPage() {
  usePageTracking({ pageType: "engagement_review", pageTitle: "Engagement Review" });
  useScrollDepth({ pageType: "engagement_review" });
  useEngagementTime({ pageType: "engagement_review" });

  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!secret) return;
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
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [secret]);

  useEffect(() => {
    const stored = localStorage.getItem("admin_secret");
    if (stored) {
      setSecret(stored);
    }
  }, []);

  useEffect(() => {
    if (secret) {
      localStorage.setItem("admin_secret", secret);
      fetchData();
    }
  }, [secret, fetchData]);

  const overallAvg =
    data?.by_category && data.by_category.length > 0
      ? data.by_category.reduce(
          (sum: number, c: CategoryRow) => sum + c.avg_engagement_rate * c.market_count,
          0
        ) /
        data.by_category.reduce((sum: number, c: CategoryRow) => sum + c.market_count, 0)
      : 0;

  return (
    <div className="min-h-screen bg-surface-primary p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Engagement-Calibrated Ranking Review
      </h1>
      <p className="text-text-secondary mb-6">
        Nightly export of Discover interaction data. Reporting only — does not
        auto-tune production weights.
      </p>

      {!secret && (
        <div className="mb-6">
          <label className="block text-text-secondary text-sm mb-1">
            Admin Secret
          </label>
          <input
            type="password"
            className="border border-surface-border rounded px-3 py-2 w-64 text-text-primary bg-surface-card"
            placeholder="Enter admin secret"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setSecret((e.target as HTMLInputElement).value);
              }
            }}
          />
        </div>
      )}

      {loading && secret && (
        <p className="text-text-muted">Loading engagement data...</p>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6">
          <p className="text-red-700">{error}</p>
        </div>
      )}

      {data?.status === "no_data" && (
        <div className="bg-yellow-50 border border-yellow-200 rounded p-4 mb-6">
          <p className="text-yellow-800">{data.message}</p>
        </div>
      )}

      {data && data.by_category && (
        <>
          <div className="flex gap-6 mb-6 text-sm text-text-secondary">
            <span>
              Generated:{" "}
              {new Date(data.generated_at).toLocaleString()}
            </span>
            <span>Window: {data.window_hours}h</span>
            <span>Markets: {data.total_markets_with_interactions}</span>
            <button
              onClick={fetchData}
              className="text-accent-brand hover:underline"
            >
              Refresh
            </button>
          </div>

          <section className="mb-8">
            <h2 className="text-lg font-semibold text-text-primary mb-3">
              By Category
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-surface-card border-b border-surface-border">
                    <th className="text-left p-3 text-text-secondary font-medium">Category</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Avg Score</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Engagement Rate</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Impressions</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Markets</th>
                    <th className="text-center p-3 text-text-secondary font-medium">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_category.map((cat) => {
                    const v = verdict(cat.avg_engagement_rate, overallAvg);
                    const isExpanded = expandedCategory === cat.category;
                    return (
                      <tr
                        key={cat.category}
                        className="border-b border-surface-border hover:bg-surface-card cursor-pointer"
                        onClick={() =>
                          setExpandedCategory(isExpanded ? null : cat.category)
                        }
                      >
                        <td className="p-3 text-text-primary font-medium">
                          {cat.category}
                          {isExpanded && cat.top_markets.length > 0 && (
                            <div className="mt-2 bg-surface-card rounded p-3">
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <h4 className="text-xs font-semibold text-text-secondary mb-2 uppercase">
                                    Top Markets
                                  </h4>
                                  {cat.top_markets.map((m) => (
                                    <div
                                      key={m.item_id}
                                      className="text-xs text-text-primary mb-1 truncate"
                                    >
                                      {pct(m.engagement_rate)} -{" "}
                                      {m.item_name || m.item_id}{" "}
                                      <span className="text-text-muted">
                                        (score: {m.score ?? "--"}, {m.impressions} imp)
                                      </span>
                                    </div>
                                  ))}
                                </div>
                                {cat.bottom_markets.length > 0 && (
                                  <div>
                                    <h4 className="text-xs font-semibold text-text-secondary mb-2 uppercase">
                                      Bottom Markets
                                    </h4>
                                    {cat.bottom_markets.map((m) => (
                                      <div
                                        key={m.item_id}
                                        className="text-xs text-text-primary mb-1 truncate"
                                      >
                                        {pct(m.engagement_rate)} -{" "}
                                        {m.item_name || m.item_id}{" "}
                                        <span className="text-text-muted">
                                          (score: {m.score ?? "--"}, {m.impressions} imp)
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="p-3 text-right text-text-primary align-top">
                          {cat.avg_score !== null ? cat.avg_score.toFixed(1) : "--"}
                        </td>
                        <td className="p-3 text-right text-text-primary align-top">
                          {pct(cat.avg_engagement_rate)}
                        </td>
                        <td className="p-3 text-right text-text-secondary align-top">
                          {cat.total_impressions.toLocaleString()}
                        </td>
                        <td className="p-3 text-right text-text-secondary align-top">
                          {cat.market_count}
                        </td>
                        <td className="p-3 text-center align-top">
                          <span
                            className={`px-2 py-1 rounded text-xs font-medium ${verdictColor(v)}`}
                          >
                            {v}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mb-8">
            <h2 className="text-lg font-semibold text-text-primary mb-3">
              Score Buckets
            </h2>
            <p className="text-text-muted text-sm mb-3">
              Does higher score correlate with higher engagement?
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-surface-card border-b border-surface-border">
                    <th className="text-left p-3 text-text-secondary font-medium">Score Range</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Markets</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Impressions</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Engagement Rate</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Opens</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Dismisses</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Shares</th>
                  </tr>
                </thead>
                <tbody>
                  {data.score_buckets.map((bucket) => (
                    <tr
                      key={bucket.score_range}
                      className="border-b border-surface-border"
                    >
                      <td className="p-3 text-text-primary font-medium">{bucket.score_range}</td>
                      <td className="p-3 text-right text-text-secondary">{bucket.market_count}</td>
                      <td className="p-3 text-right text-text-secondary">{bucket.total_impressions.toLocaleString()}</td>
                      <td className="p-3 text-right text-text-primary font-medium">{pct(bucket.avg_engagement_rate)}</td>
                      <td className="p-3 text-right text-text-secondary">{bucket.total_opens}</td>
                      <td className="p-3 text-right text-text-secondary">{bucket.total_dismisses}</td>
                      <td className="p-3 text-right text-text-secondary">{bucket.total_shares}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mb-8">
            <h2 className="text-lg font-semibold text-text-primary mb-3">
              Opportunities
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-semibold text-green-700 mb-2 uppercase">
                  Under-Ranked (high engagement, low score)
                </h3>
                {data.opportunities.under_ranked.length === 0 ? (
                  <p className="text-text-muted text-sm">
                    No under-ranked markets detected.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {data.opportunities.under_ranked.map((m) => (
                      <div
                        key={m.item_id}
                        className="bg-green-50 border border-green-200 rounded p-3"
                      >
                        <div className="text-sm text-text-primary font-medium truncate">
                          {m.item_name || m.item_id}
                        </div>
                        <div className="text-xs text-text-secondary mt-1 flex gap-3">
                          <span>Category: {m.category}</span>
                          <span>Score: {m.score ?? "--"}</span>
                          <span>Engagement: {pct(m.engagement_rate)}</span>
                          <span>{m.impressions} imp</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h3 className="text-sm font-semibold text-red-700 mb-2 uppercase">
                  Over-Ranked (low engagement, high score)
                </h3>
                {data.opportunities.over_ranked.length === 0 ? (
                  <p className="text-text-muted text-sm">
                    No over-ranked markets detected.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {data.opportunities.over_ranked.map((m) => (
                      <div
                        key={m.item_id}
                        className="bg-red-50 border border-red-200 rounded p-3"
                      >
                        <div className="text-sm text-text-primary font-medium truncate">
                          {m.item_name || m.item_id}
                        </div>
                        <div className="text-xs text-text-secondary mt-1 flex gap-3">
                          <span>Category: {m.category}</span>
                          <span>Score: {m.score ?? "--"}</span>
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
        </>
      )}
    </div>
  );
}
