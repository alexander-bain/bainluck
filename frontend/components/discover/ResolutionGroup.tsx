"use client";

import Link from "next/link";
import type { ResolutionItem } from "@/lib/api";

interface ResolutionGroupProps {
  resolutions: ResolutionItem[];
}

/**
 * "Your results" — collapses 3+ settled Higher/Lower guesses into ONE group card
 * instead of stacking individual result cards atop Discover. Queue L2-119: each
 * row keeps full context (market + your guess vs the outcome), stays clickable
 * back to its market, and wears settled (muted) chrome. Same treatment as the
 * single ResolutionCard, just denser.
 */
export function ResolutionGroup({ resolutions }: ResolutionGroupProps) {
  if (resolutions.length === 0) return null;
  const correctCount = resolutions.filter((r) => r.correct).length;
  const total = resolutions.length;

  return (
    <section
      aria-label="Your resolved guesses"
      className="rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-card"
    >
      <div className="px-4 py-2.5 bg-surface-elevated flex items-center gap-2">
        <span className="text-sm">📋</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
          Your results · settled
        </span>
        <span className="ml-auto text-[11px] font-semibold text-text-secondary tabular-nums">
          {correctCount}/{total} correct
        </span>
      </div>
      <div className="divide-y divide-surface-border/60">
        {resolutions.map((r, idx) => (
          <Link
            key={`${r.market_id}-${idx}`}
            href={`/futures/${r.market_id}`}
            aria-label={`Your resolved guess on ${r.market_name} — ${
              r.correct ? "correct" : "wrong"
            }`}
            className="group flex items-center gap-3 px-4 py-2.5 hover:bg-surface-elevated/60 transition-colors"
          >
            <span
              className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold ${
                r.correct
                  ? "bg-accent-live/10 text-accent-live"
                  : "bg-accent-danger/10 text-accent-danger"
              }`}
            >
              {r.correct ? "✓" : "✗"}
            </span>
            <span className="flex-1 min-w-0">
              <span className="block text-[13px] font-semibold text-text-primary leading-snug truncate group-hover:text-accent-brand transition-colors">
                {r.market_name}
              </span>
              <span className="block text-[11px] text-text-muted">
                You guessed {r.guess} than {r.threshold}% — resolved at {r.actual}%
              </span>
            </span>
            <span className="shrink-0 text-text-muted text-[15px] leading-none opacity-0 group-hover:opacity-100 transition-opacity">
              ›
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
