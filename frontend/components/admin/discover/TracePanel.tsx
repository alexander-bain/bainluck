"use client";

import type { DiscoverMarketTrace } from "./types";
import { StatusPill } from "./ui";
import { formatTargetName, signedNumber, percentText, rankText } from "./utils";

export default function TracePanel({ trace }: { trace: DiscoverMarketTrace }) {
  const phases = trace.rank_phases;
  const scores = trace.score_trace.scores;
  const scoreSteps = [
    { label: "Highlight", value: scores.highlight, delta: null, sub: null },
    {
      label: "Quality",
      value: scores.after_quality,
      delta: scores.after_quality - scores.highlight,
      sub: null,
    },
    {
      label: "Explanation",
      value: scores.after_explanation,
      delta: scores.after_explanation - scores.after_quality,
      sub: null,
    },
    {
      label: "Final",
      value: scores.final,
      delta: scores.final - scores.after_explanation,
      sub: `${scores.personalization_multiplier.toFixed(2)}x`,
    },
  ];
  const blockers = [
    ...trace.base_eligibility.blockers,
    ...trace.score_trace.blockers,
  ];

  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold text-text-primary">Suggested fix</div>
          <div className="text-xs text-text-secondary mt-1">{trace.suggested_fix}</div>
        </div>
        <div className="flex flex-wrap justify-end gap-1 shrink-0">
          <StatusPill tone={trace.base_eligibility.eligible ? "ok" : "warn"}>
            {trace.base_eligibility.eligible ? "base eligible" : "base blocked"}
          </StatusPill>
          <StatusPill tone={trace.candidate_pools.included ? "ok" : "warn"}>
            {trace.candidate_pools.included ? "in pool" : "pool miss"}
          </StatusPill>
          <StatusPill tone={trace.final_ranking.survived_final_caps ? "ok" : "warn"}>
            {trace.final_ranking.survived_final_caps ? "survived caps" : "not in final"}
          </StatusPill>
        </div>
      </div>

      <div className="grid md:grid-cols-5 gap-2 text-xs">
        <div className="md:col-span-2">
          <div className="text-text-muted">Score path</div>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-1">
            {scoreSteps.map((step) => (
              <div key={step.label} className="rounded-md border border-surface-border bg-surface-card px-2 py-1">
                <div className="text-[10px] uppercase text-text-muted">{step.label}</div>
                <div className="font-semibold text-text-primary">{Math.round(step.value)}</div>
                <div className="text-[11px] text-text-muted">
                  {step.delta === null ? "base" : signedNumber(step.delta, 1)}
                  {step.sub ? ` / ${step.sub}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Returned rank</div>
          <div className="text-text-primary font-medium">
            {rankText(phases?.returned_rank ?? null)}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Candidate position</div>
          <div className="text-text-primary font-medium">
            {trace.candidate_pools.candidate_position ? `#${trace.candidate_pools.candidate_position}` : "none"}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Quality</div>
          <div className="text-text-primary font-medium">{formatTargetName(trace.score_trace.quality.class)}</div>
        </div>
      </div>

      <div className="text-xs">
        <div className="text-text-muted">Headline</div>
        <div className="text-text-primary mt-1">{trace.score_trace.highlight.headline || "No headline"}</div>
        {trace.score_trace.highlight.reason && (
          <div className="text-text-secondary mt-1">{trace.score_trace.highlight.reason}</div>
        )}
      </div>

      {phases && (
        <div className="text-xs">
          <div className="font-medium text-text-primary mb-1">Rank Phases</div>
          <div className="grid md:grid-cols-3 gap-2">
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">Raw futures</span>
              <span className="text-text-primary">{rankText(phases.raw_futures_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After canonical dedupe</span>
              <span className="text-text-primary">{rankText(phases.post_canonical_dedupe_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">Initial feed sort</span>
              <span className="text-text-primary">{rankText(phases.post_initial_sort_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After event demotion</span>
              <span className="text-text-primary">{rankText(phases.post_event_demote_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After event mix</span>
              <span className="text-text-primary">{rankText(phases.post_event_mix_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After diversity</span>
              <span className="text-text-primary">{rankText(phases.post_diversity_rank)}</span>
            </div>
          </div>
          {phases.dropped_by_canonical_dedupe && phases.canonical_replacement && (
            <div className="mt-2 text-text-muted">
              Deduped behind #{phases.canonical_replacement.id}: {phases.canonical_replacement.name}
            </div>
          )}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3 text-xs">
        <div>
          <div className="font-medium text-text-primary mb-1">Candidate Pools</div>
          <div className="space-y-1">
            {trace.candidate_pools.pools.map((pool) => (
              <div key={pool.name} className="flex items-center justify-between gap-2">
                <span className="text-text-secondary">{formatTargetName(pool.name)}</span>
                <span className={pool.included ? "text-accent-live" : "text-text-muted"}>
                  {pool.included ? `#${pool.position}` : "out"} / {pool.candidate_count}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="font-medium text-text-primary mb-1">Blockers & Signals</div>
          <div className="flex flex-wrap gap-1">
            {blockers.length === 0 && <StatusPill tone="ok">No blockers</StatusPill>}
            {trace.base_eligibility.blockers.map((blocker) => (
              <StatusPill key={blocker} tone="warn">{formatTargetName(blocker)}</StatusPill>
            ))}
            {trace.score_trace.blockers.map((blocker) => (
              <StatusPill key={blocker} tone="warn">{formatTargetName(blocker)}</StatusPill>
            ))}
            {trace.score_trace.quality.reasons.map((reason) => (
              <StatusPill key={reason} tone="muted">{formatTargetName(reason)}</StatusPill>
            ))}
            {trace.score_trace.explanation.has_hook && <StatusPill tone="ok">hook</StatusPill>}
            {trace.score_trace.explanation.has_image && <StatusPill tone="ok">image</StatusPill>}
          </div>
        </div>
      </div>

      {trace.score_trace.top_outcomes.length > 0 && (
        <div className="text-xs">
          <div className="font-medium text-text-primary mb-1">Top Outcomes</div>
          <div className="grid md:grid-cols-2 gap-1">
            {trace.score_trace.top_outcomes.slice(0, 4).map((outcome) => (
              <div key={outcome.name} className="flex justify-between gap-3 text-text-secondary">
                <span className="truncate">{outcome.name}</span>
                <span className="shrink-0">
                  {percentText(outcome.probability)}
                  {outcome.probability_change_24h !== null ? ` (${outcome.probability_change_24h > 0 ? "+" : ""}${Math.round(outcome.probability_change_24h * 100)}pp)` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
