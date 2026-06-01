"use client";

import { useState, useEffect, useCallback } from "react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { getIdToken } from "@/lib/firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LabelingOutcome {
  name: string | null;
  probability: number | null;
}

interface LabelingCandidate {
  rank: number;
  id: number;
  market_id: number;
  stable_id: string;
  name: string;
  category: string;
  source: string;
  score: number;
  item_type: string;
  archetype: string;
  quality_class: string;
  headline: string | null;
  reason: string | null;
  context: string | null;
  hook_description: string | null;
  image_url: string | null;
  group_id: string | null;
  story_key: string | null;
  family_key: string | null;
  reasons: string[];
  top_outcomes: LabelingOutcome[];
  rendered_probability: number | null;
}

interface HistoryEntry {
  name: string;
  label: "good" | "bad" | "skip";
  reason?: string;
}

const BAD_REASONS = ["boring", "duplicate", "stale", "bad image", "confusing", "niche"] as const;

function pct(val: number | null | undefined): string {
  if (val == null) return "--";
  return `${Math.round(val * 100)}%`;
}

export default function LabelingPage() {
  usePageTracking({ pageType: "admin_labeling", pageTitle: "Discover Labeling" });
  useScrollDepth({ pageType: "admin_labeling" });
  useEngagementTime({ pageType: "admin_labeling" });

  const { secret } = useAdminAuth();

  const [candidates, setCandidates] = useState<LabelingCandidate[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [awaitingReason, setAwaitingReason] = useState(false);

  const current = idx < candidates.length ? candidates[idx] : null;
  const labeled = history.length;

  // Load candidates
  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getIdToken();
      const params = new URLSearchParams({
        secret,
        limit: "50",
        reviewer: "native",
        reviewed_surface: "web_discover",
      });
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${API_URL}/api/admin/ranking-judgments/candidates?${params}`, { headers });
      if (!res.ok) {
        setError(res.status === 403 ? "Admin access required." : `API error: ${res.status}`);
        setLoading(false);
        return;
      }
      const data = await res.json();
      setCandidates(data.items);
      setIdx(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
    setLoading(false);
  }, [secret]);

  useEffect(() => {
    if (secret) loadCandidates();
  }, [secret, loadCandidates]);

  // Auto-load next batch when exhausted
  useEffect(() => {
    if (candidates.length > 0 && idx >= candidates.length && !loading) {
      loadCandidates();
    }
  }, [idx, candidates.length, loading, loadCandidates]);

  // Submit judgment to API
  const submitToAPI = useCallback(async (
    candidate: LabelingCandidate,
    label: string,
    reasonTags: string[],
  ) => {
    const token = await getIdToken();
    const body = {
      secret,
      surface: "web_discover",
      rank_seen: candidate.rank,
      item_type: candidate.item_type || "futures",
      market_id: candidate.market_id,
      market_name: candidate.name,
      label,
      reason_tags: reasonTags,
      notes: null,
      score_at_review: candidate.score,
      category_at_review: candidate.category,
      archetype_at_review: candidate.archetype,
      quality_class_at_review: candidate.quality_class,
      headline_at_review: candidate.headline,
      card_snapshot: {
        schema_version: "discover-card-v1",
        name: candidate.name,
        source: candidate.source,
        category: candidate.category,
        hook_description: candidate.hook_description,
        image_url: candidate.image_url,
        score: candidate.score,
        rendered_probability: candidate.rendered_probability,
        top_outcomes: candidate.top_outcomes?.slice(0, 5) || [],
      },
      reviewer: "web",
    };
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_URL}/api/admin/ranking-judgments`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  }, [secret]);

  // Advance to next card
  const advance = useCallback((label: "good" | "bad" | "skip", reason?: string) => {
    if (!current) return;
    setHistory(prev => [...prev, { name: current.name, label, reason }]);
    setIdx(i => i + 1);
    setAwaitingReason(false);
  }, [current]);

  // Handle verdict
  const handleVerdict = useCallback(async (verdict: "good" | "bad" | "skip") => {
    if (!current || submitting) return;

    if (verdict === "bad") {
      setAwaitingReason(true);
      return;
    }

    if (verdict === "skip") {
      advance("skip");
      return;
    }

    // Good — submit and advance
    setSubmitting(true);
    try {
      await submitToAPI(current, "love", []);
      advance("good");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
    setSubmitting(false);
  }, [current, submitting, submitToAPI, advance]);

  // Handle bad reason selection
  const handleBadReason = useCallback(async (reason?: string) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      const tags = reason ? [reason.replace(" ", "_")] : [];
      await submitToAPI(current, "bad", tags);
      advance("bad", reason);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
    setSubmitting(false);
  }, [current, submitting, submitToAPI, advance]);

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (submitting) return;

      if (awaitingReason) {
        // Escape or down arrow = skip reason and advance
        if (e.key === "Escape" || e.key === "ArrowDown") {
          e.preventDefault();
          handleBadReason();
        }
        return;
      }

      switch (e.key) {
        case "1": case "ArrowRight":
          e.preventDefault(); handleVerdict("good"); break;
        case "2": case "ArrowLeft":
          e.preventDefault(); handleVerdict("bad"); break;
        case "3": case "ArrowDown":
          e.preventDefault(); handleVerdict("skip"); break;
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleVerdict, handleBadReason, awaitingReason, submitting]);

  // --- Render ---

  return (
    <div className="max-w-lg mx-auto px-4 py-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">Discover Labeling</h1>
        {labeled > 0 && (
          <span className="text-sm font-semibold text-accent-brand bg-accent-brand/10 px-3 py-1 rounded-full">
            {labeled} labeled
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center justify-between p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-600">
          <span>{error}</span>
          <span onClick={() => setError(null)} className="text-red-400 hover:text-red-600 ml-2 cursor-pointer text-xs">dismiss</span>
        </div>
      )}

      {/* Loading */}
      {loading && candidates.length === 0 ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-sm text-text-muted animate-pulse">Loading candidates...</div>
        </div>
      ) : current ? (
        <div className="space-y-4">
          {/* Card preview */}
          <div className="bg-surface-card rounded-2xl border border-surface-border overflow-hidden shadow-sm">
            {current.image_url && (
              <div className="relative h-48 bg-surface-elevated">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={current.image_url}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
              </div>
            )}
            <div className="p-5 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold text-text-primary leading-snug flex-1">
                  {current.name}
                </h2>
                {current.rendered_probability != null && (
                  <span className="text-2xl font-bold text-accent-brand shrink-0">
                    {pct(current.rendered_probability)}
                  </span>
                )}
              </div>
              {current.hook_description && (
                <p className="text-sm text-text-secondary leading-relaxed">
                  {current.hook_description}
                </p>
              )}
              {current.top_outcomes && current.top_outcomes.length > 1 && (
                <div className="space-y-1 pt-1">
                  {current.top_outcomes.slice(0, 4).map((o, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-text-secondary truncate flex-1 mr-2">{o.name || "Outcome"}</span>
                      <span className="font-mono text-text-primary">{pct(o.probability)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-1.5 flex-wrap pt-1">
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">{current.category}</span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">{current.source}</span>
              </div>
            </div>
          </div>

          {/* Verdict buttons or bad reason chips */}
          {awaitingReason ? (
            <div className="space-y-3">
              <p className="text-sm text-text-secondary text-center">Why is it bad?</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {BAD_REASONS.map(reason => (
                  <button
                    key={reason}
                    onClick={() => handleBadReason(reason)}
                    disabled={submitting}
                    className="px-4 py-2 rounded-xl text-sm font-medium bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {reason}
                  </button>
                ))}
              </div>
              <button
                onClick={() => handleBadReason()}
                disabled={submitting}
                className="w-full py-2 rounded-xl text-sm text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
              >
                skip reason (Esc)
              </button>
            </div>
          ) : (
            <div className="flex gap-3">
              <button
                onClick={() => handleVerdict("good")}
                disabled={submitting}
                className="flex-1 py-4 rounded-2xl text-base font-bold bg-emerald-500 text-white hover:bg-emerald-600 transition-colors disabled:opacity-50 cursor-pointer"
              >
                Good
                <span className="block text-xs font-normal opacity-70 mt-0.5">1 or &rarr;</span>
              </button>
              <button
                onClick={() => handleVerdict("bad")}
                disabled={submitting}
                className="flex-1 py-4 rounded-2xl text-base font-bold bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 cursor-pointer"
              >
                Bad
                <span className="block text-xs font-normal opacity-70 mt-0.5">2 or &larr;</span>
              </button>
              <button
                onClick={() => handleVerdict("skip")}
                disabled={submitting}
                className="flex-1 py-4 rounded-2xl text-base font-bold bg-surface-elevated text-text-secondary border border-surface-border hover:bg-surface-border transition-colors disabled:opacity-50 cursor-pointer"
              >
                Skip
                <span className="block text-xs font-normal opacity-70 mt-0.5">3 or &darr;</span>
              </button>
            </div>
          )}
        </div>
      ) : !loading && candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-3">
          <div className="text-sm font-semibold text-text-primary">No candidates available</div>
          <button onClick={loadCandidates} className="text-sm px-4 py-2 rounded-xl bg-surface-elevated border border-surface-border text-text-secondary hover:text-text-primary cursor-pointer">
            Reload
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 space-y-3">
          <div className="text-sm font-semibold text-text-primary">Batch complete!</div>
          <p className="text-xs text-text-muted">{labeled} labeled this session.</p>
          <button
            onClick={loading ? undefined : loadCandidates}
            disabled={loading}
            className="text-sm px-5 py-2.5 rounded-xl bg-accent-brand text-white font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Loading..." : "Load next batch"}
          </button>
        </div>
      )}

      {/* Session history strip */}
      {history.length > 0 && (
        <div className="flex gap-2 overflow-x-auto py-2 border-t border-surface-border mt-4">
          {history.slice(-5).map((h, i) => (
            <div
              key={i}
              className={`shrink-0 flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border ${
                h.label === "good" ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                : h.label === "bad" ? "bg-red-50 border-red-200 text-red-700"
                : "bg-surface-elevated border-surface-border text-text-muted"
              }`}
            >
              <span className="font-semibold">{h.label === "good" ? "G" : h.label === "bad" ? "B" : "S"}</span>
              <span className="truncate max-w-[100px]">{h.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
