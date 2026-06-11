"use client";

import { useMemo, useState, useEffect, useCallback, useRef } from "react";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import type { DebugItem } from "./types";

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
  rank?: number | null;
  story_key?: string | null;
  family_key?: string | null;
  group_id?: string | null;
  snapshot?: Record<string, unknown>;
}

interface PairResponse {
  card_a: Card;
  card_b: Card;
  pair_id: string;
  pair_strategy?: string;
  batch_id?: string;
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
  pair_id?: string | null;
  pair_strategy?: string | null;
  surface?: string | null;
  ranking_error?: boolean | null;
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

const CHOICE_SHORTCUTS: Record<string, string> = {
  a: "1",
  b: "2",
  both: "3",
  neither: "4",
  skip: "S",
};

const CONFIDENCE_OPTIONS = ["low", "medium", "high"] as const;
type Confidence = (typeof CONFIDENCE_OPTIONS)[number];

const RANKING_ERROR_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "yes", label: "Error" },
  { value: "no", label: "No error" },
] as const;
type RankingErrorOverride = (typeof RANKING_ERROR_OPTIONS)[number]["value"];

function createBatchId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `pairwise-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function itemProbability(item: DebugItem) {
  if (typeof item.rendered_probability === "number") return item.rendered_probability;
  const values = (item.top_outcomes || [])
    .map((outcome) => outcome.probability ?? outcome.current_probability)
    .filter((value): value is number => typeof value === "number");
  return values.length ? Math.max(...values) : null;
}

function snapshotForItem(item: DebugItem, batchId: string): Record<string, unknown> {
  return {
    schema_version: "discover-pairwise-card-v1",
    batch_id: batchId,
    rank: item.rank,
    item_type: item.type,
    item_id: item.id,
    market_id: item.type === "futures" ? item.id : null,
    name: item.name,
    source: item.source,
    category: item.category,
    archetype: item.archetype,
    quality_class: item.quality_class,
    headline: item.headline,
    reason: item.reason,
    context: item.context || item.reason,
    hook_description: item.hook_description || null,
    image_url: item.image_url || null,
    story_key: item.story_key,
    family_key: item.family_key,
    group_id: item.group_id,
    score: item.score,
    rendered_probability: itemProbability(item),
    top_outcomes: item.top_outcomes || [],
    reasons: item.reasons || [],
  };
}

function cardFromDebugItem(item: DebugItem, batchId: string): Card {
  return {
    market_id: item.id || 0,
    name: item.name,
    category: item.category,
    probability: itemProbability(item),
    image_url: item.image_url || null,
    hook_description: item.hook_description || item.reason,
    outcomes: (item.top_outcomes || []).slice(0, 3).map((outcome) => ({
      name: outcome.name || "Outcome",
      probability: outcome.probability ?? outcome.current_probability ?? null,
    })),
    score: Math.round(item.score * 100) / 100,
    rank: item.rank,
    story_key: item.story_key,
    family_key: item.family_key,
    group_id: item.group_id,
    snapshot: snapshotForItem(item, batchId),
  };
}

function buildFeedContextPairs(items: DebugItem[], batchId: string): PairResponse[] {
  const futures = items.filter((item) => item.type === "futures" && item.id);
  const pairs: PairResponse[] = [];
  const seen = new Set<string>();
  const addPair = (left: DebugItem, right: DebugItem, strategy: string) => {
    if (!left.id || !right.id || left.id === right.id) return;
    const key = [left.id, right.id].sort().join(":");
    if (seen.has(key)) return;
    seen.add(key);
    pairs.push({
      card_a: cardFromDebugItem(left, batchId),
      card_b: cardFromDebugItem(right, batchId),
      pair_id: `${strategy}:${batchId}:${left.id}:${right.id}`,
      pair_strategy: strategy,
      batch_id: batchId,
    });
  };

  for (let idx = 0; idx < Math.min(futures.length - 1, 20); idx += 1) {
    addPair(futures[idx], futures[idx + 1], "adjacent_rank");
  }

  const byFamily = new Map<string, DebugItem[]>();
  for (const item of futures) {
    const key = item.story_key || item.group_id || item.family_key;
    if (!key) continue;
    byFamily.set(key, [...(byFamily.get(key) || []), item]);
  }
  for (const rows of byFamily.values()) {
    if (rows.length >= 2) addPair(rows[0], rows[1], "same_story_or_family");
  }

  const highRankLowScore = futures.find((item) => item.rank <= 15 && item.score < 50);
  const lowRankHighScore = futures.find((item) => item.rank > 15 && item.score >= 70);
  if (highRankLowScore && lowRankHighScore) {
    addPair(highRankLowScore, lowRankHighScore, "score_rank_tension");
  }

  return pairs;
}

// --- Page ---

export default function PairwiseTab({ debugItems = [] }: { debugItems?: DebugItem[] }) {
  const { secret: submittedSecret } = useAdminAuth();
  const [reviewer] = useState("alex");
  const [batchId] = useState(createBatchId);
  const [pair, setPair] = useState<PairResponse | null>(null);
  const [stats, setStats] = useState<LabelStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labelCount, setLabelCount] = useState(0);
  const pairIndexRef = useRef(0);
  const [lastChoice, setLastChoice] = useState<string | null>(null);
  const [lastSubmitted, setLastSubmitted] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<Confidence>("medium");
  const [rankingErrorOverride, setRankingErrorOverride] =
    useState<RankingErrorOverride>("auto");
  const [notes, setNotes] = useState("");
  const feedPairs = useMemo(
    () => buildFeedContextPairs(debugItems, batchId),
    [debugItems, batchId]
  );

  const resetReviewFields = useCallback(() => {
    setRankingErrorOverride("auto");
    setNotes("");
  }, []);

  const inferredRankingError = useCallback((choice: string) => {
    if (!pair) return null;
    if (choice === "a") return pair.card_a.score < pair.card_b.score;
    if (choice === "b") return pair.card_b.score < pair.card_a.score;
    return null;
  }, [pair]);

  const rankingErrorForChoice = useCallback((choice: string) => {
    if (rankingErrorOverride === "yes") return true;
    if (rankingErrorOverride === "no") return false;
    return inferredRankingError(choice);
  }, [inferredRankingError, rankingErrorOverride]);

  // Fetch next pair
  const fetchPair = useCallback(async () => {
    if (!submittedSecret) return;
    setLoading(true);
    setError(null);
    setLastChoice(null);
    try {
      if (feedPairs.length) {
        setPair(feedPairs[pairIndexRef.current % feedPairs.length]);
        pairIndexRef.current += 1;
        resetReviewFields();
        return;
      }
      const res = await adminFetch(
        "/api/admin/pairwise/next",
        submittedSecret
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API error: ${res.status}`);
      }
      const data: PairResponse = await res.json();
      setPair(data);
      resetReviewFields();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pair");
      setPair(null);
    } finally {
      setLoading(false);
    }
  }, [feedPairs, resetReviewFields, submittedSecret]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    if (!submittedSecret) return;
    try {
      const res = await adminFetch(
        "/api/admin/pairwise/stats",
        submittedSecret
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
  const submitLabel = useCallback(async (choice: string) => {
    if (!submittedSecret || !pair || !reviewer.trim()) return;
    setSubmitting(true);
    setError(null);
    setLastSubmitted(null);
    try {
      const res = await adminFetch(
        "/api/admin/pairwise/label",
        submittedSecret,
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
            pair_id: pair.pair_id,
            pair_strategy: pair.pair_strategy || "legacy_random",
            surface: "discover_quality",
            batch_id: pair.batch_id || batchId,
            confidence,
            ranking_error: rankingErrorForChoice(choice),
            notes: notes.trim() || null,
            card_a_snapshot: pair.card_a.snapshot || null,
            card_b_snapshot: pair.card_b.snapshot || null,
          }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Submit error: ${res.status}`);
      }
      setLabelCount((c) => c + 1);
      setLastChoice(choice);
      setLastSubmitted(`${CHOICE_LABELS[choice] || choice} submitted`);
      // Auto-load next pair
      await fetchPair();
      fetchStats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit label");
    } finally {
      setSubmitting(false);
    }
  }, [
    batchId,
    confidence,
    fetchPair,
    fetchStats,
    notes,
    pair,
    rankingErrorForChoice,
    reviewer,
    submittedSecret,
  ]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName.toLowerCase();
      if (
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        target?.isContentEditable
      ) {
        return;
      }
      if (!pair || loading || submitting || !submittedSecret) return;

      const key = event.key.toLowerCase();
      const shortcutChoice =
        key === "1" ? "a" :
        key === "2" ? "b" :
        key === "3" ? "both" :
        key === "4" ? "neither" :
        key === "s" ? "skip" :
        null;

      if (shortcutChoice) {
        event.preventDefault();
        submitLabel(shortcutChoice);
      } else if (key === "r") {
        event.preventDefault();
        fetchPair();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [fetchPair, loading, pair, submittedSecret, submitting, submitLabel]);

  // --- Render ---

  return (
    <div>
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
            {lastSubmitted && (
              <span className="text-sm font-medium text-accent-live">
                {lastSubmitted}
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
            {pair.pair_strategy && (
              <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
                <span className="rounded-full border border-surface-border bg-surface-elevated px-2 py-0.5">
                  {pair.pair_strategy.replaceAll("_", " ")}
                </span>
                {pair.card_a.rank && pair.card_b.rank && (
                  <span>#{pair.card_a.rank} vs #{pair.card_b.rank}</span>
                )}
              </div>
            )}
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

            {/* Review metadata */}
            <div className="mb-5 rounded-lg border border-surface-border bg-surface-card p-4">
              <div className="grid gap-4 lg:grid-cols-[1fr_1fr_2fr]">
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Confidence
                  </div>
                  <div className="flex rounded-lg border border-surface-border bg-surface-elevated p-1">
                    {CONFIDENCE_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setConfidence(option)}
                        disabled={submitting}
                        className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          confidence === option
                            ? "bg-surface-card text-text-primary shadow-sm"
                            : "text-text-secondary hover:text-text-primary"
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Ranking error
                  </div>
                  <div className="flex rounded-lg border border-surface-border bg-surface-elevated p-1">
                    {RANKING_ERROR_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setRankingErrorOverride(option.value)}
                        disabled={submitting}
                        className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          rankingErrorOverride === option.value
                            ? "bg-surface-card text-text-primary shadow-sm"
                            : "text-text-secondary hover:text-text-primary"
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-text-muted">
                    Auto marks A/B picks against the current score.
                  </p>
                </div>

                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Notes
                  </span>
                  <textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    disabled={submitting}
                    rows={3}
                    placeholder="Optional reviewer notes"
                    className="min-h-[88px] w-full resize-y rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-brand focus:outline-none focus:ring-2 focus:ring-accent-brand/20 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </label>
              </div>
            </div>

            {/* Choice buttons */}
            <div className="flex flex-wrap items-center justify-center gap-3 mb-8">
              {(["a", "b", "both", "neither", "skip"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => submitLabel(c)}
                  disabled={submitting}
                  aria-keyshortcuts={CHOICE_SHORTCUTS[c].toLowerCase()}
                  title={`${CHOICE_LABELS[c]} (${CHOICE_SHORTCUTS[c]})`}
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
                aria-keyshortcuts="r"
                title="Refresh pair (R)"
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
  );
}
