"use client";

import { useState, useCallback, useEffect } from "react";
import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { getIdToken } from "@/lib/firebase";
import { StatusPill } from "./ui";
import { formatTargetName, rateText } from "./utils";
import type { DebugItem, FeedDebugResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const LABELS = [
  { key: "love", label: "Love", color: "bg-accent-live text-white", desc: "Should be higher" },
  { key: "fine", label: "Fine", color: "bg-surface-elevated text-text-primary", desc: "Acceptable" },
  { key: "bad", label: "Bad", color: "bg-accent-warning text-white", desc: "Should be lower" },
  { key: "kill", label: "Kill", color: "bg-accent-danger text-white", desc: "Never show" },
] as const;

const REASON_TAGS = [
  "fun", "important", "too_niche", "stale", "duplicate", "bucket",
  "needs_context", "wrong_category", "too_high", "too_low", "ladder", "no_context",
];

interface JudgmentSummary {
  total: number;
  labels: Record<string, number>;
}

export default function ReviewTab() {
  const { secret } = useAdminAuth();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [betterThanPrev, setBetterThanPrev] = useState(false);
  const [worseThanNext, setWorseThanNext] = useState(false);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sessionCount, setSessionCount] = useState(0);
  const [sessionLabels, setSessionLabels] = useState<Record<string, number>>({});

  const { data, isLoading } = useSWR<FeedDebugResponse>(
    ["review-feed", secret],
    async () => {
      const params = new URLSearchParams({
        limit: "50",
        include_events: "false",
        include_futures: "true",
        event_pct: "0.15",
        debug: "true",
        secret,
      });
      const token = await getIdToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
      const res = await fetch(`${API_URL}/api/feed?${params}`, { headers });
      if (!res.ok) throw new Error(`Feed error: ${res.status}`);
      return res.json();
    },
    { revalidateOnFocus: false }
  );

  const { data: summary } = useSWR<JudgmentSummary>(
    ["judgment-summary", secret],
    () =>
      fetch(`${API_URL}/api/admin/ranking-judgments/summary?secret=${encodeURIComponent(secret)}`)
        .then((r) => r.json()),
    { refreshInterval: 30000 }
  );

  const items = data?.debug_items || [];
  const current = items[currentIdx];
  const prevItem = currentIdx > 0 ? items[currentIdx - 1] : null;
  const nextItem = currentIdx < items.length - 1 ? items[currentIdx + 1] : null;

  const resetForm = () => {
    setSelectedLabel(null);
    setSelectedTags(new Set());
    setBetterThanPrev(false);
    setWorseThanNext(false);
    setNotes("");
  };

  const submit = useCallback(async () => {
    if (!current || !selectedLabel) return;
    setSubmitting(true);
    try {
      const params = new URLSearchParams({
        secret,
        surface: "discover",
        rank_seen: String(current.rank),
        item_type: current.type || "futures",
        market_name: current.name,
        label: selectedLabel,
        reason_tags: Array.from(selectedTags).join(","),
        score_at_review: String(current.score),
        category_at_review: current.category || "",
        archetype_at_review: current.archetype || "",
        quality_class_at_review: current.quality_class || "",
        headline_at_review: current.headline || "",
        reviewer: "alex",
      });
      if (current.id) params.set("market_id", String(current.id));
      if (betterThanPrev && prevItem) params.set("better_than", prevItem.name);
      if (worseThanNext && nextItem) params.set("worse_than", nextItem.name);
      if (notes.trim()) params.set("notes", notes.trim());

      await fetch(`${API_URL}/api/admin/ranking-judgments?${params}`, { method: "POST" });
      setSessionCount((c) => c + 1);
      setSessionLabels((prev) => ({ ...prev, [selectedLabel]: (prev[selectedLabel] || 0) + 1 }));
      resetForm();
      setCurrentIdx((i) => i + 1);
    } finally {
      setSubmitting(false);
    }
  }, [current, selectedLabel, selectedTags, betterThanPrev, worseThanNext, notes, prevItem, nextItem, secret]);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  if (isLoading) return <div className="py-8 text-text-muted">Loading feed...</div>;
  if (!items.length) return <div className="py-8 text-text-muted">No feed items to review.</div>;

  const reviewed = currentIdx;
  const remaining = items.length - currentIdx;

  return (
    <div className="space-y-4">
      {/* Session stats */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm text-text-secondary">
          {reviewed}/{items.length} reviewed
        </span>
        {sessionCount > 0 && (
          <div className="flex gap-1">
            {Object.entries(sessionLabels).map(([label, count]) => (
              <StatusPill key={label} tone={label === "love" ? "ok" : label === "kill" ? "warn" : "muted"}>
                {count} {label}
              </StatusPill>
            ))}
          </div>
        )}
        {summary && summary.total > 0 && (
          <span className="text-xs text-text-muted">
            {summary.total} total judgments
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-surface-elevated rounded-full overflow-hidden">
        <div
          className="h-full bg-accent-brand rounded-full transition-all"
          style={{ width: `${(reviewed / items.length) * 100}%` }}
        />
      </div>

      {current ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          {/* Card header */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <div className="text-sm font-semibold text-text-primary leading-snug">
                {current.name}
              </div>
              {current.headline && (
                <div className="text-xs text-text-secondary mt-1">{current.headline}</div>
              )}
            </div>
            <div className="text-right shrink-0">
              <div className="text-lg font-bold text-text-primary">#{current.rank}</div>
              <div className="text-xs text-text-muted">score {Math.round(current.score)}</div>
            </div>
          </div>

          {/* Metadata pills */}
          <div className="flex flex-wrap gap-1 mb-4">
            <StatusPill tone="muted">{current.category || "uncategorized"}</StatusPill>
            <StatusPill tone="muted">{current.archetype || "?"}</StatusPill>
            <StatusPill tone="muted">{current.source}</StatusPill>
            <StatusPill tone={current.quality_class === "compelling" ? "ok" : current.quality_class === "suppress" ? "warn" : "muted"}>
              {formatTargetName(current.quality_class || "normal")}
            </StatusPill>
            {current.hook && <StatusPill tone="ok">hook</StatusPill>}
            {current.image && <StatusPill tone="ok">image</StatusPill>}
            {current.story_key && <StatusPill tone="muted">{current.story_key}</StatusPill>}
          </div>

          {/* Reason text if present */}
          {current.reason && (
            <div className="text-xs text-text-secondary mb-4 bg-surface-elevated rounded-lg p-2">
              {current.reason}
            </div>
          )}

          {/* Label buttons */}
          <div className="grid grid-cols-4 gap-2 mb-4">
            {LABELS.map((l) => (
              <button
                key={l.key}
                onClick={() => setSelectedLabel(l.key)}
                className={`rounded-xl py-3 text-sm font-semibold transition-all ${
                  selectedLabel === l.key
                    ? `${l.color} ring-2 ring-offset-2 ring-offset-surface-card ring-current scale-105`
                    : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>

          {/* Reason tags (visible after selecting a label) */}
          {selectedLabel && (
            <>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {REASON_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`rounded-full px-2.5 py-1 text-xs font-medium border transition-colors ${
                      selectedTags.has(tag)
                        ? "bg-accent-brand/10 text-accent-brand border-accent-brand/30"
                        : "bg-surface-elevated text-text-muted border-surface-border hover:border-text-muted"
                    }`}
                  >
                    {formatTargetName(tag)}
                  </button>
                ))}
              </div>

              {/* Pairwise controls */}
              <div className="flex gap-2 mb-3">
                {prevItem && (
                  <button
                    onClick={() => setBetterThanPrev(!betterThanPrev)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-xs transition-colors ${
                      betterThanPrev
                        ? "bg-accent-live/10 text-accent-live border-accent-live/30"
                        : "bg-surface-elevated text-text-muted border-surface-border"
                    }`}
                  >
                    Should beat #{currentIdx} above
                  </button>
                )}
                {nextItem && (
                  <button
                    onClick={() => setWorseThanNext(!worseThanNext)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-xs transition-colors ${
                      worseThanNext
                        ? "bg-accent-danger/10 text-accent-danger border-accent-danger/30"
                        : "bg-surface-elevated text-text-muted border-surface-border"
                    }`}
                  >
                    Should lose to #{currentIdx + 2} below
                  </button>
                )}
              </div>

              {/* Notes */}
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes (optional)"
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40 mb-3"
              />

              {/* Submit */}
              <button
                onClick={submit}
                disabled={submitting}
                className="w-full rounded-xl bg-text-primary text-text-inverse py-3 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {submitting ? "Saving..." : "Submit & Next"}
              </button>
            </>
          )}

          {/* Skip */}
          {!selectedLabel && (
            <button
              onClick={() => { resetForm(); setCurrentIdx((i) => i + 1); }}
              className="w-full text-center text-xs text-text-muted hover:text-text-secondary py-2"
            >
              Skip →
            </button>
          )}
        </div>
      ) : (
        <div className="bg-surface-card border border-surface-border rounded-xl p-8 text-center">
          <div className="text-xl font-bold text-accent-live mb-2">All reviewed!</div>
          <div className="text-sm text-text-secondary">{sessionCount} judgments this session</div>
        </div>
      )}

      {/* Score by label (if summary has data) */}
      {summary && summary.total > 0 && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="text-xs font-semibold text-text-primary mb-2">Score by Label</div>
          <div className="text-xs text-text-muted mb-2">
            If love items don&apos;t score highest, the scorer is miscalibrated.
          </div>
          <div className="flex gap-3">
            {Object.entries(summary.labels).map(([label, count]) => (
              <div key={label} className="text-center">
                <div className="text-lg font-bold text-text-primary">{count}</div>
                <div className="text-[10px] text-text-muted">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
