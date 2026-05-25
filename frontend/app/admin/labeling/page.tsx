"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { getIdToken } from "@/lib/firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types ---

interface LabelingOutcome {
  id: number;
  name: string | null;
  probability: number | null;
  movement: number | null;
  rank: number | null;
}

interface LabelingCandidate {
  rank: number;
  type: string;
  item_type: string;
  id: number;
  market_id: number;
  stable_id: string;
  name: string;
  category: string;
  archetype: string;
  source: string;
  stratum: string;
  selection_reason: string;
  candidate_source: string;
  score: number;
  headline: string | null;
  reason: string | null;
  context: string | null;
  hook_description: string | null;
  image_url: string | null;
  group_id: string | null;
  quality_class: string;
  family_key: string | null;
  story_key: string | null;
  ladder: boolean;
  reasons: string[];
  top_outcomes: LabelingOutcome[];
  rendered_probability: number | null;
  resolution_date: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface CandidatesResponse {
  items: LabelingCandidate[];
  total_available: number;
  limit: number;
  offset: number;
  has_more: boolean;
  candidate_source: string;
  strata: string[];
  stratum_sample_counts: Record<string, number>;
  reviewed_filter: {
    enabled: boolean;
    reviewer: string;
    surface: string;
    reviewed_key_count: number;
    filtered_count: number;
  };
}

interface SubmittedJudgment {
  candidate: LabelingCandidate;
  label: string;
  reasonTags: string[];
  notes: string;
}

// --- Constants ---

const VERDICTS = [
  { key: "love",  label: "Love",  shortcut: "1", color: "bg-emerald-600 hover:bg-emerald-700 text-white" },
  { key: "fine",  label: "Fine",  shortcut: "2", color: "bg-sky-600 hover:bg-sky-700 text-white" },
  { key: "bad",   label: "Bad",   shortcut: "3", color: "bg-amber-600 hover:bg-amber-700 text-white" },
  { key: "kill",  label: "Kill",  shortcut: "4", color: "bg-red-600 hover:bg-red-700 text-white" },
  { key: "skip",  label: "Skip",  shortcut: "5", color: "bg-surface-elevated hover:bg-surface-border text-text-secondary" },
] as const;

const SECONDARY_TAGS = [
  { key: "public_story",    label: "Public story" },
  { key: "too_niche",       label: "Niche" },
  { key: "boring",          label: "Boring" },
  { key: "stale",           label: "Stale" },
  { key: "duplicate",       label: "Duplicate" },
  { key: "ladder",          label: "Ladder" },
  { key: "bad_image",       label: "Bad image" },
  { key: "generic_hook",    label: "Bad explanation" },
  { key: "fun_or_weird",    label: "Fun/weird" },
  { key: "surprising_probability", label: "Surprising" },
  { key: "timely",          label: "Timely" },
  { key: "high_stakes",     label: "High stakes" },
];

const STRATUM_LABELS: Record<string, string> = {
  top_feed_like: "Top Feed",
  fresh_public_story: "Fresh Story",
  stale_fixable: "Stale/Fixable",
  weather: "Weather",
  finance_ladder: "Finance Ladder",
  low_confidence: "Boundary",
  duplicate_group: "Duplicate Group",
  explanation_image_gap: "Missing Explanation/Image",
  movement_boundary: "Movement",
  low_volume_editorial: "Low Volume",
};

// --- Helpers ---

function probabilityText(val: number | null | undefined): string {
  if (val == null) return "--";
  return `${Math.round(val * 100)}%`;
}

function stratumBadgeColor(stratum: string): string {
  switch (stratum) {
    case "top_feed_like": return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "fresh_public_story": return "bg-sky-500/15 text-sky-400 border-sky-500/30";
    case "stale_fixable": return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "finance_ladder": return "bg-red-500/15 text-red-400 border-red-500/30";
    case "weather": return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    case "low_confidence": return "bg-purple-500/15 text-purple-400 border-purple-500/30";
    case "duplicate_group": return "bg-orange-500/15 text-orange-400 border-orange-500/30";
    case "explanation_image_gap": return "bg-rose-500/15 text-rose-400 border-rose-500/30";
    case "movement_boundary": return "bg-indigo-500/15 text-indigo-400 border-indigo-500/30";
    default: return "bg-surface-elevated text-text-muted border-surface-border";
  }
}

function verdictBadgeClass(label: string): string {
  switch (label) {
    case "love": return "bg-emerald-500/15 text-emerald-400";
    case "fine": return "bg-sky-500/15 text-sky-400";
    case "bad": return "bg-amber-500/15 text-amber-400";
    case "kill": return "bg-red-500/15 text-red-400";
    default: return "bg-surface-elevated text-text-muted";
  }
}

// --- Main Page ---

export default function LabelingWorkbench() {
  usePageTracking({ pageType: "admin_labeling", pageTitle: "Discover Labeling" });
  useScrollDepth({ pageType: "admin_labeling" });
  useEngagementTime({ pageType: "admin_labeling" });

  const { secret } = useAdminAuth();

  const [candidates, setCandidates] = useState<LabelingCandidate[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState("");
  const [history, setHistory] = useState<SubmittedJudgment[]>([]);
  const [sessionLabels, setSessionLabels] = useState<Record<string, number>>({});
  const [batchSize] = useState(40);
  const [strataInfo, setStrataInfo] = useState<Record<string, number>>({});
  const [reviewedInfo, setReviewedInfo] = useState<{ count: number; filtered: number } | null>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);

  const current = currentIdx < candidates.length ? candidates[currentIdx] : null;
  const reviewed = currentIdx;
  const total = candidates.length;
  const sessionTotal = Object.values(sessionLabels).reduce((s, n) => s + n, 0);

  // Load candidates
  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getIdToken();
      const params = new URLSearchParams({
        secret,
        limit: String(batchSize),
        reviewer: "native",
        reviewed_surface: "web_discover",
      });
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${API_URL}/api/admin/ranking-judgments/candidates?${params}`, { headers });
      if (!res.ok) {
        if (res.status === 403) {
          setError("Admin access required. Check your secret or sign in.");
        } else {
          setError(`API error: ${res.status}`);
        }
        setLoading(false);
        return;
      }
      const data: CandidatesResponse = await res.json();
      setCandidates(data.items);
      setCurrentIdx(0);
      setStrataInfo(data.stratum_sample_counts);
      if (data.reviewed_filter) {
        setReviewedInfo({
          count: data.reviewed_filter.reviewed_key_count,
          filtered: data.reviewed_filter.filtered_count,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candidates");
    }
    setLoading(false);
  }, [secret, batchSize]);

  useEffect(() => {
    if (secret) loadCandidates();
  }, [secret, loadCandidates]);

  // Auto-load next batch when exhausted
  useEffect(() => {
    if (candidates.length > 0 && currentIdx >= candidates.length && !loading) {
      loadCandidates();
    }
  }, [currentIdx, candidates.length, loading, loadCandidates]);

  // Submit judgment
  const submitVerdict = useCallback(async (verdictKey: string) => {
    if (!current || submitting) return;

    if (verdictKey === "skip") {
      setHistory((prev) => [...prev, { candidate: current, label: "skip", reasonTags: [], notes: "" }]);
      setSessionLabels((prev) => ({ ...prev, skip: (prev.skip || 0) + 1 }));
      setCurrentIdx((i) => i + 1);
      setSelectedTags(new Set());
      setNotes("");
      return;
    }

    setSubmitting(true);
    try {
      const token = await getIdToken();
      const snapshot = {
        schema_version: "discover-card-v1",
        batch_id: `web-labeling-${Date.now()}`,
        rank: current.rank,
        item_type: current.item_type || "futures",
        item_id: current.id,
        market_id: current.market_id,
        name: current.name,
        source: current.source,
        category: current.category,
        archetype: current.archetype,
        quality_class: current.quality_class,
        headline: current.headline,
        reason: current.reason,
        context: current.context || current.reason,
        hook_description: current.hook_description,
        image_url: current.image_url,
        story_key: current.story_key,
        family_key: current.family_key,
        group_id: current.group_id,
        score: current.score,
        rendered_probability: current.rendered_probability,
        top_outcomes: current.top_outcomes?.slice(0, 5) || [],
        reasons: current.reasons?.slice(0, 12) || [],
        has_hook: !!current.hook_description,
        has_image: !!current.image_url,
      };

      const body = {
        secret,
        surface: "web_discover",
        rank_seen: current.rank,
        item_type: current.item_type || "futures",
        market_id: current.market_id,
        market_name: current.name,
        label: verdictKey,
        reason_tags: Array.from(selectedTags),
        notes: notes.trim() || null,
        score_at_review: current.score,
        category_at_review: current.category,
        archetype_at_review: current.archetype,
        quality_class_at_review: current.quality_class,
        headline_at_review: current.headline,
        card_snapshot: snapshot,
        reviewer: "web",
      };

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/api/admin/ranking-judgments`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        setError(`Submit failed: ${res.status}`);
        setSubmitting(false);
        return;
      }

      setHistory((prev) => [...prev, {
        candidate: current,
        label: verdictKey,
        reasonTags: Array.from(selectedTags),
        notes: notes.trim(),
      }]);
      setSessionLabels((prev) => ({ ...prev, [verdictKey]: (prev[verdictKey] || 0) + 1 }));
      setCurrentIdx((i) => i + 1);
      setSelectedTags(new Set());
      setNotes("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
    setSubmitting(false);
  }, [current, submitting, secret, selectedTags, notes]);

  // Undo last judgment
  const undo = useCallback(() => {
    if (history.length === 0 || currentIdx === 0) return;
    const last = history[history.length - 1];
    setHistory((prev) => prev.slice(0, -1));
    setSessionLabels((prev) => {
      const next = { ...prev };
      if (next[last.label]) {
        next[last.label]--;
        if (next[last.label] <= 0) delete next[last.label];
      }
      return next;
    });
    setCurrentIdx((i) => i - 1);
    setSelectedTags(new Set(last.reasonTags));
    setNotes(last.notes);
  }, [history, currentIdx]);

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;

      switch (e.key) {
        case "1": e.preventDefault(); submitVerdict("love"); break;
        case "2": e.preventDefault(); submitVerdict("fine"); break;
        case "3": e.preventDefault(); submitVerdict("bad"); break;
        case "4": e.preventDefault(); submitVerdict("kill"); break;
        case "5": e.preventDefault(); submitVerdict("skip"); break;
        case "u": case "z":
          if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); undo(); }
          break;
        case "n":
          e.preventDefault();
          if (notesRef.current) notesRef.current.focus();
          break;
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [submitVerdict, undo]);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg font-bold text-text-primary">Discover Labeling</h1>
          <p className="text-xs text-text-muted mt-0.5">
            Rate cards from the labeling queue. Keyboard: 1-5 verdicts, u=undo, n=notes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {sessionTotal > 0 && (
            <span className="text-xs font-semibold text-accent-brand bg-accent-brand/10 px-2.5 py-1 rounded-full">
              {sessionTotal} labeled
            </span>
          )}
          <span
            onClick={loading ? undefined : loadCandidates}
            className={`text-xs px-3 py-1.5 rounded-lg bg-surface-elevated border border-surface-border text-text-secondary hover:text-text-primary cursor-pointer transition-colors ${loading ? "opacity-50 pointer-events-none" : ""}`}
          >
            {loading ? "Loading..." : "Reload"}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>{reviewed}/{total} reviewed</span>
            <span>{total - reviewed} remaining</span>
          </div>
          <div className="h-2 bg-surface-border rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-brand rounded-full transition-all duration-300"
              style={{ width: `${total > 0 ? (reviewed / total) * 100 : 0}%` }}
            />
          </div>
          {Object.keys(sessionLabels).length > 0 && (
            <div className="flex gap-1.5 flex-wrap">
              {Object.entries(sessionLabels).sort(([a], [b]) => a.localeCompare(b)).map(([label, count]) => (
                <span
                  key={label}
                  className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted"
                >
                  {count} {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Strata info */}
      {Object.keys(strataInfo).length > 0 && (
        <details className="text-xs">
          <summary className="text-text-muted cursor-pointer hover:text-text-secondary">
            Strata: {Object.entries(strataInfo).filter(([, v]) => v > 0).length} active
            {reviewedInfo && ` | ${reviewedInfo.count} previously reviewed, ${reviewedInfo.filtered} filtered`}
          </summary>
          <div className="flex gap-1.5 flex-wrap mt-1.5">
            {Object.entries(strataInfo).map(([stratum, count]) => (
              <span
                key={stratum}
                className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${stratumBadgeColor(stratum)}`}
              >
                {STRATUM_LABELS[stratum] || stratum}: {count}
              </span>
            ))}
          </div>
        </details>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center justify-between p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400">
          <span>{error}</span>
          <span onClick={() => setError(null)} className="text-red-400/60 hover:text-red-400 ml-2 cursor-pointer">dismiss</span>
        </div>
      )}

      {/* Loading */}
      {loading && candidates.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-sm text-text-muted animate-pulse">Loading candidates...</div>
        </div>
      ) : current ? (
        <div className="space-y-3">
          {/* Card preview */}
          <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
            {current.image_url && (
              <div className="relative h-40 bg-surface-elevated">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={current.image_url}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
              </div>
            )}

            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h2 className="text-base font-semibold text-text-primary leading-snug">
                    {current.name}
                  </h2>
                  {current.hook_description && (
                    <p className="text-sm text-text-secondary mt-1 leading-relaxed">
                      {current.hook_description}
                    </p>
                  )}
                </div>
                {current.rendered_probability != null && (
                  <span className="text-2xl font-bold text-accent-brand shrink-0">
                    {probabilityText(current.rendered_probability)}
                  </span>
                )}
              </div>

              <div className="flex gap-1.5 flex-wrap">
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${stratumBadgeColor(current.stratum)}`}>
                  {STRATUM_LABELS[current.stratum] || current.stratum}
                </span>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
                  {current.category}
                </span>
                {current.archetype && current.archetype !== "unknown" && (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
                    {current.archetype}
                  </span>
                )}
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
                  {current.source}
                </span>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
                  {current.quality_class}
                </span>
                {current.ladder && (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/30">
                    ladder
                  </span>
                )}
                {current.story_key && (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
                    {current.story_key}
                  </span>
                )}
              </div>

              <div className="text-[10px] text-text-muted">
                Selection: {current.selection_reason}
              </div>

              {current.top_outcomes && current.top_outcomes.length > 0 && (
                <div className="space-y-1">
                  {current.top_outcomes.slice(0, 4).map((outcome, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-text-secondary truncate flex-1 mr-2">
                        {outcome.name || "Outcome"}
                      </span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="font-mono text-text-primary">
                          {probabilityText(outcome.probability)}
                        </span>
                        {outcome.movement != null && outcome.movement !== 0 && (
                          <span className={`text-xs font-mono ${outcome.movement > 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {outcome.movement > 0 ? "+" : ""}{(outcome.movement * 100).toFixed(1)}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(current.context || current.reason) && (
                <div className="text-xs text-text-muted p-2.5 rounded-lg bg-surface-elevated leading-relaxed">
                  {current.context || current.reason}
                </div>
              )}

              {current.resolution_date && (
                <div className="text-[10px] text-text-muted">
                  Resolves: {new Date(current.resolution_date).toLocaleDateString()}
                </div>
              )}
            </div>
          </div>

          {/* Verdict buttons */}
          <div className="flex gap-2">
            {VERDICTS.map((v) => (
              <span
                key={v.key}
                onClick={submitting ? undefined : () => submitVerdict(v.key)}
                className={`flex-1 py-2.5 rounded-xl text-sm font-semibold text-center cursor-pointer select-none transition-all ${submitting ? "opacity-50 pointer-events-none" : ""} ${v.color}`}
              >
                <span className="block">{v.label}</span>
                <span className="text-[10px] opacity-60 font-normal">{v.shortcut}</span>
              </span>
            ))}
          </div>

          {/* Secondary tags */}
          <div className="flex gap-1.5 flex-wrap">
            {SECONDARY_TAGS.map((tag) => (
              <span
                key={tag.key}
                onClick={() => toggleTag(tag.key)}
                className={`text-xs px-2.5 py-1 rounded-lg border cursor-pointer select-none transition-colors ${
                  selectedTags.has(tag.key)
                    ? "bg-accent-brand/15 text-accent-brand border-accent-brand/40 font-medium"
                    : "bg-surface-elevated text-text-muted border-surface-border hover:text-text-secondary hover:border-text-muted/30"
                }`}
              >
                {tag.label}
              </span>
            ))}
          </div>

          {/* Notes */}
          <textarea
            ref={notesRef}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes (optional, press n to focus)"
            rows={2}
            className="w-full text-sm px-3 py-2 rounded-xl border border-surface-border bg-surface-elevated text-text-primary placeholder:text-text-muted/60 focus:outline-none focus:ring-2 focus:ring-accent-brand/30 resize-none"
          />

          {/* Undo */}
          {history.length > 0 && (
            <div className="flex items-center justify-between">
              <span
                onClick={undo}
                className="text-xs text-text-muted hover:text-text-secondary cursor-pointer transition-colors"
              >
                Undo last ({history[history.length - 1].label}) &middot; u
              </span>
              <span className="text-[10px] text-text-muted">
                Card {currentIdx + 1} of {candidates.length}
              </span>
            </div>
          )}
        </div>
      ) : !loading && candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <div className="text-sm font-semibold text-text-primary">No candidates available</div>
          <p className="text-xs text-text-muted text-center max-w-xs">
            All items have been reviewed or no open markets match the labeling criteria.
          </p>
          <span
            onClick={loadCandidates}
            className="text-xs px-4 py-2 rounded-lg bg-surface-elevated border border-surface-border text-text-secondary hover:text-text-primary cursor-pointer"
          >
            Reload candidates
          </span>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <div className="text-sm font-semibold text-text-primary">Batch complete!</div>
          <p className="text-xs text-text-muted text-center">
            Reviewed {total} cards this batch. {sessionTotal} total this session.
          </p>
          <span
            onClick={loading ? undefined : loadCandidates}
            className={`text-xs px-4 py-2 rounded-lg bg-accent-brand text-white font-medium hover:opacity-90 cursor-pointer ${loading ? "opacity-50 pointer-events-none" : ""}`}
          >
            {loading ? "Loading..." : "Load next batch"}
          </span>
        </div>
      )}

      {/* Recent history */}
      {history.length > 0 && (
        <details className="text-xs">
          <summary className="text-text-muted cursor-pointer hover:text-text-secondary">
            Session history ({history.length} judgments)
          </summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {[...history].reverse().slice(0, 20).map((h, i) => (
              <div key={i} className="flex items-center gap-2 py-1 border-b border-surface-border/50">
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${verdictBadgeClass(h.label)}`}>
                  {h.label}
                </span>
                <span className="text-text-secondary truncate flex-1">{h.candidate.name}</span>
                {h.reasonTags.length > 0 && (
                  <span className="text-text-muted truncate max-w-[120px]">
                    {h.reasonTags.join(", ")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
