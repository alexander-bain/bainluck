"use client";

import { useState, useEffect, useCallback } from "react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types ---

interface CardOutcome {
  name: string;
  probability: number | null;
}

interface Card {
  market_id: number;
  name: string;
  category: string;
  probability: number | null;
  image_url: string | null;
  hook_description: string | null;
  outcomes: CardOutcome[];
  score: number;
}

interface PairResponse {
  card_a: Card;
  card_b: Card;
  pair_id: string;
}

interface LabelStats {
  total_labels: number;
  labels_by_choice: Record<string, number>;
  agreement_rate: number | null;
  total_comparable: number;
  per_category_agreement: Record<string, number | null>;
  recent_labels: RecentLabel[];
}

interface RecentLabel {
  id: number;
  reviewer: string;
  card_a_name: string;
  card_b_name: string;
  card_a_score: number | null;
  card_b_score: number | null;
  choice: string;
  created_at: string | null;
}

// --- Helpers ---

function formatPct(p: number | null): string {
  if (p === null || p === undefined) return "--";
  return `${(p * 100).toFixed(1)}%`;
}

const CHOICE_LABELS: Record<string, string> = {
  a: "A is better",
  b: "B is better",
  both: "Both good",
  neither: "Neither good",
  skip: "Skip",
};

const CHOICE_COLORS: Record<string, string> = {
  a: "bg-blue-600 text-white hover:bg-blue-700",
  b: "bg-purple-600 text-white hover:bg-purple-700",
  both: "bg-green-600 text-white hover:bg-green-700",
  neither: "bg-gray-500 text-white hover:bg-gray-600",
  skip: "bg-gray-300 text-gray-700 hover:bg-gray-400",
};

// --- Page ---

export default function PairwiseLabelingPage() {
  // GA4 hooks (mandatory)
  usePageTracking({
    pageType: "admin_pairwise",
    pageTitle: "Admin: Pairwise Labeling",
  });
  useScrollDepth({ pageType: "admin_pairwise" });
  useEngagementTime({ pageType: "admin_pairwise" });

  const [secret, setSecret] = useState("");
  const [submittedSecret, setSubmittedSecret] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [pair, setPair] = useState<PairResponse | null>(null);
  const [stats, setStats] = useState<LabelStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labelCount, setLabelCount] = useState(0);
  const [lastChoice, setLastChoice] = useState<string | null>(null);

  // Read secret from URL params on mount
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("secret");
    if (fromUrl) {
      setSecret(fromUrl);
      setSubmittedSecret(fromUrl);
    }
  }, []);

  // Fetch next pair
  const fetchPair = useCallback(async () => {
    if (!submittedSecret) return;
    setLoading(true);
    setError(null);
    setLastChoice(null);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/pairwise/next?secret=${encodeURIComponent(submittedSecret)}`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API error: ${res.status}`);
      }
      const data: PairResponse = await res.json();
      setPair(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pair");
      setPair(null);
    } finally {
      setLoading(false);
    }
  }, [submittedSecret]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    if (!submittedSecret) return;
    try {
      const res = await fetch(
        `${API_URL}/api/admin/pairwise/stats?secret=${encodeURIComponent(submittedSecret)}`
      );
      if (res.ok) {
        setStats(await res.json());
      }
    } catch {
      // Non-critical
    }
  }, [submittedSecret]);

  // Load pair + stats when secret is submitted
  useEffect(() => {
    if (submittedSecret) {
      fetchPair();
      fetchStats();
    }
  }, [submittedSecret, fetchPair, fetchStats]);

  // Submit label
  const submitLabel = async (choice: string) => {
    if (!submittedSecret || !pair || !reviewer.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/pairwise/label?secret=${encodeURIComponent(submittedSecret)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            card_a_market_id: pair.card_a.market_id,
            card_b_market_id: pair.card_b.market_id,
            card_a_score: pair.card_a.score,
            card_b_score: pair.card_b.score,
            choice,
            reviewer: reviewer.trim(),
          }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Submit error: ${res.status}`);
      }
      setLabelCount((c) => c + 1);
      setLastChoice(choice);
      // Auto-load next pair
      await fetchPair();
      fetchStats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit label");
    } finally {
      setSubmitting(false);
    }
  };

  // --- Render ---

  return (
    <div className="min-h-screen bg-surface-deep">
      <div className="mx-auto max-w-6xl px-4 py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-text-primary">
            Pairwise Card Labeling
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Compare two Discover cards side by side. Pick which is more
            interesting to calibrate ranking quality.
          </p>
        </div>

        {/* Auth bar */}
        <div className="mb-6 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-text-muted mb-1">
              Admin Secret
            </label>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
              placeholder="Enter admin secret"
            />
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="block text-xs font-medium text-text-muted mb-1">
              Reviewer Name
            </label>
            <input
              type="text"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
              placeholder="Your name"
            />
          </div>
          <button
            onClick={() => setSubmittedSecret(secret)}
            disabled={!secret.trim() || !reviewer.trim()}
            className="rounded-lg bg-accent-brand px-5 py-2 text-sm font-medium text-white hover:bg-accent-brand/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Start
          </button>
        </div>

        {/* Session counter */}
        {labelCount > 0 && (
          <div className="mb-4 flex items-center gap-3">
            <span className="rounded-full bg-accent-brand/10 px-3 py-1 text-sm font-medium text-accent-brand">
              {labelCount} labeled this session
            </span>
            {lastChoice && (
              <span className="text-sm text-text-muted">
                Last: {CHOICE_LABELS[lastChoice] || lastChoice}
              </span>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-4 rounded-lg border border-accent-danger/30 bg-accent-danger/5 px-4 py-3 text-sm text-accent-danger">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20 text-text-muted">
            Loading pair...
          </div>
        )}

        {/* Pair comparison */}
        {pair && !loading && submittedSecret && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
              {/* Card A */}
              <div
                className={`flex flex-col rounded-xl border p-5 transition-all ${
                  lastChoice === "a"
                    ? "border-accent-brand ring-2 ring-accent-brand/30"
                    : "border-surface-border"
                } bg-surface-card`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <span className="text-xs font-semibold tracking-wider text-text-muted uppercase">
                    Card A
                  </span>
                  <span className="shrink-0 rounded-full bg-surface-elevated px-2.5 py-0.5 text-xs font-medium text-text-secondary">
                    {pair.card_a.category || "uncategorized"}
                  </span>
                </div>
                {pair.card_a.image_url && (
                  <div className="mb-3 overflow-hidden rounded-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={pair.card_a.image_url}
                      alt={pair.card_a.name}
                      className="w-full h-36 object-cover"
                    />
                  </div>
                )}
                <h3 className="text-base font-semibold text-text-primary leading-snug mb-2">
                  {pair.card_a.name}
                </h3>
                {pair.card_a.hook_description && (
                  <p className="text-sm text-text-secondary leading-relaxed mb-3">
                    {pair.card_a.hook_description}
                  </p>
                )}
                {pair.card_a.outcomes.length > 0 && (
                  <div className="space-y-2 mb-3">
                    {pair.card_a.outcomes.map((o, i) => (
                      <div key={i}>
                        <div className="flex items-center justify-between text-sm mb-0.5">
                          <span className="text-text-primary truncate mr-2">{o.name}</span>
                          <span className="text-text-secondary font-mono text-xs shrink-0">
                            {formatPct(o.probability)}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-surface-elevated overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent-brand transition-all"
                            style={{ width: `${Math.max((o.probability ?? 0) * 100, 1)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-auto pt-2 border-t border-surface-border flex items-center justify-between text-xs text-text-muted">
                  <span>Ranking score</span>
                  <span className="font-mono">{pair.card_a.score}</span>
                </div>
              </div>

              {/* Card B */}
              <div
                className={`flex flex-col rounded-xl border p-5 transition-all ${
                  lastChoice === "b"
                    ? "border-accent-brand ring-2 ring-accent-brand/30"
                    : "border-surface-border"
                } bg-surface-card`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <span className="text-xs font-semibold tracking-wider text-text-muted uppercase">
                    Card B
                  </span>
                  <span className="shrink-0 rounded-full bg-surface-elevated px-2.5 py-0.5 text-xs font-medium text-text-secondary">
                    {pair.card_b.category || "uncategorized"}
                  </span>
                </div>
                {pair.card_b.image_url && (
                  <div className="mb-3 overflow-hidden rounded-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={pair.card_b.image_url}
                      alt={pair.card_b.name}
                      className="w-full h-36 object-cover"
                    />
                  </div>
                )}
                <h3 className="text-base font-semibold text-text-primary leading-snug mb-2">
                  {pair.card_b.name}
                </h3>
                {pair.card_b.hook_description && (
                  <p className="text-sm text-text-secondary leading-relaxed mb-3">
                    {pair.card_b.hook_description}
                  </p>
                )}
                {pair.card_b.outcomes.length > 0 && (
                  <div className="space-y-2 mb-3">
                    {pair.card_b.outcomes.map((o, i) => (
                      <div key={i}>
                        <div className="flex items-center justify-between text-sm mb-0.5">
                          <span className="text-text-primary truncate mr-2">{o.name}</span>
                          <span className="text-text-secondary font-mono text-xs shrink-0">
                            {formatPct(o.probability)}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-surface-elevated overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent-brand transition-all"
                            style={{ width: `${Math.max((o.probability ?? 0) * 100, 1)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-auto pt-2 border-t border-surface-border flex items-center justify-between text-xs text-text-muted">
                  <span>Ranking score</span>
                  <span className="font-mono">{pair.card_b.score}</span>
                </div>
              </div>
            </div>

            {/* Choice buttons */}
            <div className="flex flex-wrap items-center justify-center gap-3 mb-8">
              {(["a", "b", "both", "neither", "skip"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => submitLabel(c)}
                  disabled={submitting || !reviewer.trim()}
                  className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${CHOICE_COLORS[c]}`}
                >
                  {CHOICE_LABELS[c]}
                </button>
              ))}
            </div>

            {/* Skip to next without labeling */}
            <div className="flex justify-center mb-8">
              <button
                onClick={fetchPair}
                disabled={loading}
                className="text-sm text-text-muted hover:text-text-secondary underline transition-colors"
              >
                Refresh pair (no label)
              </button>
            </div>
          </>
        )}

        {/* Stats section */}
        {stats && submittedSecret && (
          <div className="border-t border-surface-border pt-8">
            <h2 className="text-lg font-semibold text-text-primary mb-4">
              Labeling Stats
            </h2>

            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <div className="text-2xl font-bold text-text-primary">
                  {stats.total_labels}
                </div>
                <div className="text-xs text-text-muted">Total Labels</div>
              </div>
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <div className="text-2xl font-bold text-text-primary">
                  {stats.agreement_rate !== null
                    ? `${(stats.agreement_rate * 100).toFixed(1)}%`
                    : "--"}
                </div>
                <div className="text-xs text-text-muted">Agreement Rate</div>
              </div>
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <div className="text-2xl font-bold text-text-primary">
                  {stats.total_comparable}
                </div>
                <div className="text-xs text-text-muted">Comparable (A/B)</div>
              </div>
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <div className="text-2xl font-bold text-text-primary">
                  {Object.keys(stats.per_category_agreement).length}
                </div>
                <div className="text-xs text-text-muted">Categories</div>
              </div>
            </div>

            {/* Labels by choice */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-text-secondary mb-2">
                Labels by Choice
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.labels_by_choice).map(([choice, count]) => (
                  <span
                    key={choice}
                    className="rounded-full bg-surface-elevated px-3 py-1 text-sm text-text-primary"
                  >
                    {CHOICE_LABELS[choice] || choice}: {count}
                  </span>
                ))}
              </div>
            </div>

            {/* Per-category agreement */}
            {Object.keys(stats.per_category_agreement).length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-text-secondary mb-2">
                  Agreement by Category
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                  {Object.entries(stats.per_category_agreement)
                    .sort(([, a], [, b]) => (b ?? 0) - (a ?? 0))
                    .map(([cat, rate]) => (
                      <div
                        key={cat}
                        className="flex items-center justify-between rounded-lg border border-surface-border bg-surface-card px-3 py-2"
                      >
                        <span className="text-sm text-text-primary truncate mr-2">
                          {cat}
                        </span>
                        <span className="text-sm font-mono text-text-secondary shrink-0">
                          {rate !== null ? `${(rate * 100).toFixed(0)}%` : "--"}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Recent labels table */}
            {stats.recent_labels.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-text-secondary mb-2">
                  Recent Labels
                </h3>
                <div className="overflow-x-auto rounded-lg border border-surface-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface-elevated text-left text-xs text-text-muted">
                        <th className="px-3 py-2">Card A</th>
                        <th className="px-3 py-2">Card B</th>
                        <th className="px-3 py-2">Choice</th>
                        <th className="px-3 py-2">Reviewer</th>
                        <th className="px-3 py-2">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.recent_labels.map((lbl) => (
                        <tr
                          key={lbl.id}
                          className="border-t border-surface-border"
                        >
                          <td className="px-3 py-2 text-text-primary max-w-[200px] truncate">
                            {lbl.card_a_name}
                            {lbl.card_a_score !== null && (
                              <span className="ml-1 text-text-muted text-xs">
                                ({lbl.card_a_score.toFixed(1)})
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-text-primary max-w-[200px] truncate">
                            {lbl.card_b_name}
                            {lbl.card_b_score !== null && (
                              <span className="ml-1 text-text-muted text-xs">
                                ({lbl.card_b_score.toFixed(1)})
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-xs font-medium">
                              {CHOICE_LABELS[lbl.choice] || lbl.choice}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-text-secondary">
                            {lbl.reviewer}
                          </td>
                          <td className="px-3 py-2 text-text-muted text-xs whitespace-nowrap">
                            {lbl.created_at
                              ? new Date(lbl.created_at).toLocaleString()
                              : "--"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
