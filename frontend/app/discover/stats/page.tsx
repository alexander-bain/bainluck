"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import LoadingState from "@/components/LoadingState";

interface DetailedStats {
  total: number;
  correct: number;
  accuracy: number;
  current_streak: number;
  best_streak: number;
  by_category: Record<string, { total: number; correct: number; accuracy: number }>;
  trend: Array<{ date: string; total: number; correct: number; accuracy: number }>;
  badges: Array<{ id: string; name: string; emoji: string }>;
  recent: Array<{
    market_name: string;
    category: string | null;
    guess: string;
    threshold: number;
    actual: number;
    correct: boolean;
    created_at: string | null;
  }>;
}

function getSessionId(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("bainluck_session_id") || "";
}

export default function PredictionStatsPage() {
  usePageTracking({ pageType: "prediction_stats", pageTitle: "Prediction Stats" });
  useScrollDepth({ pageType: "prediction_stats" });
  useEngagementTime({ pageType: "prediction_stats" });

  const [stats, setStats] = useState<DetailedStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [shareState, setShareState] = useState<"idle" | "copied" | "shared">("idle");

  const handleShare = useCallback(async () => {
    if (!stats || stats.total === 0) return;

    const accuracy = Math.round(stats.accuracy * 100);
    const shareParams = `accuracy=${accuracy}&total=${stats.total}&correct=${stats.correct}&streak=${stats.current_streak}&best=${stats.best_streak}`;
    const shareUrl = `${window.location.origin}/discover/scorecard?${shareParams}`;
    const shareText = `I'm ${accuracy}% accurate across ${stats.total} predictions on Bain Luck!`;

    if (navigator.share) {
      try {
        await navigator.share({ title: "My Prediction Scorecard", text: shareText, url: shareUrl });
        setShareState("shared");
      } catch {
        // User cancelled — no-op
      }
    } else {
      try {
        await navigator.clipboard.writeText(`${shareText}\n${shareUrl}`);
        setShareState("copied");
        setTimeout(() => setShareState("idle"), 2000);
      } catch {
        // Fallback: select text
        const textarea = document.createElement("textarea");
        textarea.value = `${shareText}\n${shareUrl}`;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        setShareState("copied");
        setTimeout(() => setShareState("idle"), 2000);
      }
    }

    // Log share action
    if (typeof window !== "undefined" && window.gtag) {
      window.gtag("event", "share_scorecard", {
        accuracy,
        total: stats.total,
        streak: stats.current_streak,
      });
    }

  }, [stats]);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch("/api/predictions/detailed-stats", {
          headers: { "x-session-id": getSessionId() },
        });
        if (res.ok) setStats(await res.json());
      } catch {}
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-deep flex items-center justify-center">
        <LoadingState message="Loading stats..." />
      </div>
    );
  }

  if (!stats || stats.total === 0) {
    return (
      <div className="min-h-screen bg-surface-deep">
        <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
          <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
            <Link href="/discover" className="text-text-muted hover:text-text-primary">←</Link>
            <h1 className="text-lg font-black tracking-tight">Your Stats</h1>
          </div>
        </header>
        <div className="max-w-4xl mx-auto px-4 py-20 text-center text-text-muted">
          <p className="text-4xl mb-4">🎯</p>
          <p className="text-lg font-medium">No predictions yet</p>
          <p className="text-sm mt-2">Play the &quot;What are the odds?&quot; cards in <Link href="/discover" className="text-blue-600 hover:underline">Discover</Link> to start tracking your stats.</p>
        </div>
      </div>
    );
  }

  const categories = Object.entries(stats.by_category).sort((a, b) => b[1].total - a[1].total);

  return (
    <div className="min-h-screen bg-surface-deep">
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link href="/discover" className="text-text-muted hover:text-text-primary">←</Link>
          <h1 className="text-lg font-black tracking-tight">Your Stats</h1>
          <div className="ml-auto">
            <button
              onClick={handleShare}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent-brand text-white text-sm font-semibold hover:bg-accent-brand/90 active:scale-95 transition-all"
            >
              {shareState === "copied" ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  Copied
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                  Share
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Hero stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Total" value={stats.total.toString()} />
          <StatCard label="Correct" value={stats.correct.toString()} accent />
          <StatCard label="Accuracy" value={`${Math.round(stats.accuracy * 100)}%`} />
          <StatCard label="Best Streak" value={stats.best_streak.toString()} emoji="🔥" />
        </div>

        {/* Current streak */}
        {stats.current_streak > 0 && (
          <div className="text-center py-4 bg-amber-50 rounded-xl border border-amber-200">
            <div className="text-2xl font-black">🔥 {stats.current_streak}</div>
            <div className="text-sm text-amber-700 font-medium">current streak</div>
          </div>
        )}

        {/* Badges */}
        {stats.badges.length > 0 && (
          <div>
            <h2 className="text-sm font-bold text-text-secondary mb-3">Badges Earned</h2>
            <div className="flex flex-wrap gap-2">
              {stats.badges.map((b) => (
                <div key={b.id} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-card border border-surface-border text-sm">
                  <span>{b.emoji}</span>
                  <span className="font-medium">{b.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Category breakdown */}
        {categories.length > 0 && (
          <div>
            <h2 className="text-sm font-bold text-text-secondary mb-3">By Category</h2>
            <div className="space-y-2">
              {categories.map(([cat, data]) => (
                <div key={cat} className="flex items-center gap-3 p-3 rounded-xl bg-surface-card border border-surface-border">
                  <span className="text-sm font-semibold capitalize w-24 shrink-0">{cat}</span>
                  <div className="flex-1 h-3 rounded-full bg-surface-border overflow-hidden">
                    <div className="h-full rounded-full bg-accent-brand transition-all" style={{ width: `${data.accuracy * 100}%` }} />
                  </div>
                  <span className="font-mono tabular-nums text-sm font-bold w-12 text-right">{Math.round(data.accuracy * 100)}%</span>
                  <span className="text-xs text-text-muted w-16 text-right">{data.correct}/{data.total}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trend */}
        {stats.trend.length > 0 && (
          <div>
            <h2 className="text-sm font-bold text-text-secondary mb-3">Last 14 Days</h2>
            <div className="flex items-end gap-1 h-24 p-3 rounded-xl bg-surface-card border border-surface-border">
              {stats.trend.map((day) => (
                <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full flex flex-col justify-end" style={{ height: 60 }}>
                    <div
                      className="w-full rounded-t bg-accent-brand/70 transition-all"
                      style={{ height: `${Math.max(4, day.accuracy * 60)}px` }}
                    />
                  </div>
                  <span className="text-[8px] text-text-muted">{day.date.slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent predictions */}
        <div>
          <h2 className="text-sm font-bold text-text-secondary mb-3">Recent Predictions</h2>
          <div className="space-y-1">
            {stats.recent.map((r, i) => (
              <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-surface-card border border-surface-border">
                <span className={`text-sm ${r.correct ? "text-green-600" : "text-red-500"}`}>
                  {r.correct ? "✓" : "✗"}
                </span>
                <span className="text-sm flex-1 truncate">{r.market_name}</span>
                <span className="text-xs text-text-muted shrink-0">
                  {r.guess} {r.threshold}% → {r.actual}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, accent, emoji }: { label: string; value: string; accent?: boolean; emoji?: string }) {
  return (
    <div className="p-4 rounded-xl bg-surface-card border border-surface-border text-center">
      <div className={`text-2xl font-black tabular-nums ${accent ? "text-accent-brand" : ""}`}>
        {emoji && <span className="mr-1">{emoji}</span>}{value}
      </div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
    </div>
  );
}
