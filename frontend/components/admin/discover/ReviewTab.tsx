"use client";

import { useState, useCallback, useEffect } from "react";
import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
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

const FIX_TYPES = [
  { value: "", label: "Fix type" },
  { value: "staleness", label: "Staleness" },
  { value: "wrong_entity_rank", label: "Wrong entity rank" },
  { value: "missing_context", label: "Missing context" },
  { value: "bad_image", label: "Bad image" },
  { value: "wrong_market_variant", label: "Wrong market variant" },
  { value: "duplicate_variant", label: "Duplicate variant" },
  { value: "category_mismatch", label: "Category mismatch" },
  { value: "data_bug", label: "Data bug" },
  { value: "ranking_rule", label: "Ranking rule" },
  { value: "other", label: "Other" },
];

const TAXONOMY_SELECTS = [
  {
    key: "clarity",
    label: "Clarity",
    options: [
      { value: "clear", label: "Clear" },
      { value: "needs_context", label: "Needs context" },
      { value: "confusing", label: "Confusing" },
    ],
  },
  {
    key: "explanationQuality",
    label: "Explanation",
    options: [
      { value: "good", label: "Good" },
      { value: "generic", label: "Generic" },
      { value: "misleading", label: "Misleading" },
      { value: "missing", label: "Missing" },
    ],
  },
  {
    key: "imageFit",
    label: "Image",
    options: [
      { value: "good", label: "Good" },
      { value: "neutral", label: "Neutral" },
      { value: "bad", label: "Bad" },
      { value: "wrong_entity", label: "Wrong entity" },
      { value: "not_needed", label: "Not needed" },
    ],
  },
  {
    key: "audienceScope",
    label: "Audience",
    options: [
      { value: "broad", label: "Broad" },
      { value: "category_fan", label: "Category fan" },
      { value: "niche", label: "Niche" },
      { value: "almost_nobody", label: "Almost nobody" },
    ],
  },
  {
    key: "resolutionImportance",
    label: "Resolution",
    options: [
      { value: "high", label: "High" },
      { value: "medium", label: "Medium" },
      { value: "low", label: "Low" },
    ],
  },
  {
    key: "duplicateSeverity",
    label: "Duplicate",
    options: [
      { value: "none", label: "None" },
      { value: "minor", label: "Minor" },
      { value: "major", label: "Major" },
    ],
  },
  {
    key: "storyRelationship",
    label: "Story",
    options: [
      { value: "same_question", label: "Same question" },
      { value: "same_story_family", label: "Same family" },
      { value: "related", label: "Related" },
      { value: "unrelated", label: "Unrelated" },
    ],
  },
] as const;

function createBatchId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `review-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function buildCardSnapshot(current: DebugItem, batchId: string, feedRequestId?: string | null) {
  return {
    schema_version: "discover-card-v1",
    batch_id: batchId,
    feed_request_id: feedRequestId || null,
    rank: current.rank,
    item_type: current.type || "futures",
    item_id: current.id,
    market_id: current.type === "futures" ? current.id : null,
    event_id: current.type === "event" ? current.id : null,
    name: current.name,
    source: current.source,
    category: current.category,
    archetype: current.archetype,
    quality_class: current.quality_class,
    headline: current.headline,
    reason: current.reason,
    context: current.context || current.reason,
    hook_description: current.hook_description || null,
    image_url: current.image_url || null,
    story_key: current.story_key,
    family_key: current.family_key,
    group_id: current.group_id || null,
    score: current.score,
    rendered_probability: current.rendered_probability ?? null,
    top_outcomes: current.top_outcomes || [],
    reasons: current.reasons || [],
    has_hook: current.hook,
    has_image: current.image,
    explanation_ok: current.explanation_ok,
  };
}

interface JudgmentSummary {
  total: number;
  labels: Record<string, number>;
}

type TaxonomySelectKey = typeof TAXONOMY_SELECTS[number]["key"];

export default function ReviewTab() {
  const { secret } = useAdminAuth();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [tapworthyScore, setTapworthyScore] = useState("");
  const [clarity, setClarity] = useState("");
  const [explanationQuality, setExplanationQuality] = useState("");
  const [imageFit, setImageFit] = useState("");
  const [audienceScope, setAudienceScope] = useState("");
  const [resolutionImportance, setResolutionImportance] = useState("");
  const [duplicateSeverity, setDuplicateSeverity] = useState("");
  const [storyRelationship, setStoryRelationship] = useState("");
  const [betterThanPrev, setBetterThanPrev] = useState(false);
  const [worseThanNext, setWorseThanNext] = useState(false);
  const [notes, setNotes] = useState("");
  const [wouldBeInterestingIf, setWouldBeInterestingIf] = useState("");
  const [fixableInterestScore, setFixableInterestScore] = useState("");
  const [fixType, setFixType] = useState("");
  const [desiredEntityOrVariant, setDesiredEntityOrVariant] = useState("");
  const [currentEntityOrVariant, setCurrentEntityOrVariant] = useState("");
  const [createIssueCandidate, setCreateIssueCandidate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sessionCount, setSessionCount] = useState(0);
  const [sessionLabels, setSessionLabels] = useState<Record<string, number>>({});
  const [batchId] = useState(createBatchId);

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
      const body = await res.json();
      return {
        ...body,
        feed_request_id: res.headers.get("X-Request-ID"),
      };
    },
    { revalidateOnFocus: false }
  );

  const { data: summary } = useSWR<JudgmentSummary>(
    ["judgment-summary", secret],
    () =>
      adminFetch("/api/admin/ranking-judgments/summary", secret)
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
    setTapworthyScore("");
    setClarity("");
    setExplanationQuality("");
    setImageFit("");
    setAudienceScope("");
    setResolutionImportance("");
    setDuplicateSeverity("");
    setStoryRelationship("");
    setBetterThanPrev(false);
    setWorseThanNext(false);
    setNotes("");
    setWouldBeInterestingIf("");
    setFixableInterestScore("");
    setFixType("");
    setDesiredEntityOrVariant("");
    setCurrentEntityOrVariant("");
    setCreateIssueCandidate(false);
  };

  const taxonomyValue = (key: TaxonomySelectKey) => {
    switch (key) {
      case "clarity":
        return clarity;
      case "explanationQuality":
        return explanationQuality;
      case "imageFit":
        return imageFit;
      case "audienceScope":
        return audienceScope;
      case "resolutionImportance":
        return resolutionImportance;
      case "duplicateSeverity":
        return duplicateSeverity;
      case "storyRelationship":
        return storyRelationship;
    }
  };

  const setTaxonomyValue = (key: TaxonomySelectKey, value: string) => {
    switch (key) {
      case "clarity":
        setClarity(value);
        break;
      case "explanationQuality":
        setExplanationQuality(value);
        break;
      case "imageFit":
        setImageFit(value);
        break;
      case "audienceScope":
        setAudienceScope(value);
        break;
      case "resolutionImportance":
        setResolutionImportance(value);
        break;
      case "duplicateSeverity":
        setDuplicateSeverity(value);
        break;
      case "storyRelationship":
        setStoryRelationship(value);
        break;
    }
  };

  const submit = useCallback(async () => {
    if (!current || !selectedLabel) return;
    setSubmitting(true);
    try {
      const params = new URLSearchParams({
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
      if (data?.feed_request_id) params.set("feed_request_id", data.feed_request_id);
      if (current.id) params.set("market_id", String(current.id));
      if (betterThanPrev && prevItem) params.set("better_than", prevItem.name);
      if (worseThanNext && nextItem) params.set("worse_than", nextItem.name);
      if (notes.trim()) params.set("notes", notes.trim());

      const labelMetadata = {
        would_be_interesting_if: wouldBeInterestingIf.trim() || null,
        fixable_interest_score: fixableInterestScore ? Number(fixableInterestScore) : null,
        fix_type: fixType || null,
        desired_entity_or_variant: desiredEntityOrVariant.trim() || null,
        current_entity_or_variant: currentEntityOrVariant.trim() || null,
        create_issue_candidate: createIssueCandidate,
      };
      const hasLabelMetadata = Object.entries(labelMetadata).some(([key, value]) => (
        key === "create_issue_candidate" ? value === true : value !== null
      ));
      const taxonomyMetadata = {
        tapworthy_score: tapworthyScore ? Number(tapworthyScore) : null,
        clarity: clarity || null,
        explanation_quality: explanationQuality || null,
        image_fit: imageFit || null,
        audience_scope: audienceScope || null,
        resolution_importance: resolutionImportance || null,
        duplicate_severity: duplicateSeverity || null,
        story_relationship: storyRelationship || null,
      };
      const compactTaxonomyMetadata = Object.fromEntries(
        Object.entries(taxonomyMetadata).filter(([, value]) => value !== null)
      );

      await adminFetch(`/api/admin/ranking-judgments?${params}`, secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card_snapshot: buildCardSnapshot(current, batchId, data?.feed_request_id),
          ...(hasLabelMetadata || Object.keys(compactTaxonomyMetadata).length
            ? {
                label_metadata: {
                  ...compactTaxonomyMetadata,
                  ...(hasLabelMetadata ? { fixable_interest: labelMetadata } : {}),
                },
              }
            : {}),
        }),
      });
      setSessionCount((c) => c + 1);
      setSessionLabels((prev) => ({ ...prev, [selectedLabel]: (prev[selectedLabel] || 0) + 1 }));
      resetForm();
      setCurrentIdx((i) => i + 1);
    } finally {
      setSubmitting(false);
    }
  }, [
    current,
    selectedLabel,
    selectedTags,
    betterThanPrev,
    worseThanNext,
    notes,
    prevItem,
    nextItem,
    secret,
    data?.feed_request_id,
    wouldBeInterestingIf,
    fixableInterestScore,
    fixType,
    desiredEntityOrVariant,
    currentEntityOrVariant,
    createIssueCandidate,
    tapworthyScore,
    clarity,
    explanationQuality,
    imageFit,
    audienceScope,
    resolutionImportance,
    duplicateSeverity,
    storyRelationship,
    batchId,
  ]);

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
                {`${count} ${label}`}
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

              {/* Optional taxonomy controls */}
              <div className="mb-3 rounded-lg border border-surface-border bg-surface-elevated p-3">
                <div className="mb-2 text-xs font-semibold text-text-primary">Optional taxonomy</div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <select
                    value={tapworthyScore}
                    onChange={(e) => setTapworthyScore(e.target.value)}
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                    aria-label="Tapworthy score"
                  >
                    <option value="">Tapworthy</option>
                    <option value="1">1 - skip</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5 - must tap</option>
                  </select>
                  {TAXONOMY_SELECTS.map((field) => (
                    <select
                      key={field.key}
                      value={taxonomyValue(field.key)}
                      onChange={(e) => setTaxonomyValue(field.key, e.target.value)}
                      className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                      aria-label={field.label}
                    >
                      <option value="">{field.label}</option>
                      {field.options.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  ))}
                </div>
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

              {/* Structured fixable-interest feedback */}
              <div className="mb-3 rounded-lg border border-surface-border bg-surface-elevated p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-text-primary">Fixable interest</div>
                  <label className="flex items-center gap-2 text-xs text-text-secondary">
                    <input
                      type="checkbox"
                      checked={createIssueCandidate}
                      onChange={(e) => setCreateIssueCandidate(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-surface-border text-accent-brand focus:ring-accent-brand/40"
                    />
                    Issue candidate
                  </label>
                </div>
                <div className="grid gap-2 md:grid-cols-[1fr_120px_150px]">
                  <input
                    type="text"
                    value={wouldBeInterestingIf}
                    onChange={(e) => setWouldBeInterestingIf(e.target.value)}
                    placeholder="Would be interesting if..."
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                  />
                  <select
                    value={fixableInterestScore}
                    onChange={(e) => setFixableInterestScore(e.target.value)}
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                  >
                    <option value="">Score</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5 - very fixable</option>
                  </select>
                  <select
                    value={fixType}
                    onChange={(e) => setFixType(e.target.value)}
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                  >
                    {FIX_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>{type.label}</option>
                    ))}
                  </select>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <input
                    type="text"
                    value={currentEntityOrVariant}
                    onChange={(e) => setCurrentEntityOrVariant(e.target.value)}
                    placeholder="Current entity or variant"
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                  />
                  <input
                    type="text"
                    value={desiredEntityOrVariant}
                    onChange={(e) => setDesiredEntityOrVariant(e.target.value)}
                    placeholder="Desired entity or variant"
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                  />
                </div>
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
