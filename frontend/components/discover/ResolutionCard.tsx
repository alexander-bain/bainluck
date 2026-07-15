"use client";

import Link from "next/link";

interface ResolutionCardProps {
  /** FuturesMarket id — links the settled result back to its market. */
  marketId: number;
  marketName: string;
  guess: string;
  threshold: number;
  actual: number;
  correct: boolean;
}

/**
 * A single settled Higher/Lower result — the recap of a guess after its market
 * resolved. Queue L2-119 gave it full context (market title + your guess vs the
 * outcome), made it clickable back to the market, and moved it onto design-system
 * tokens with settled (muted) chrome. The grouped "Your results" surface
 * (ResolutionGroup) reuses the same row treatment.
 */
export function ResolutionCard({
  marketId,
  marketName,
  guess,
  threshold,
  actual,
  correct,
}: ResolutionCardProps) {
  return (
    <Link
      href={`/futures/${marketId}`}
      aria-label={`Your resolved guess on ${marketName} — ${correct ? "correct" : "wrong"}`}
      className="group block rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-card hover:shadow-lg transition-shadow"
    >
      <div className="px-4 py-2 bg-surface-elevated flex items-center gap-2">
        <span className="text-sm">📋</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
          Your result · settled
        </span>
        <span className="ml-auto text-text-muted text-[15px] leading-none opacity-0 group-hover:opacity-100 transition-opacity">
          ›
        </span>
      </div>
      <div className="p-4">
        <h3 className="font-semibold text-sm text-text-primary leading-snug mb-2.5 group-hover:text-accent-brand transition-colors">
          {marketName}
        </h3>
        <div
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold mb-2 ${
            correct
              ? "bg-accent-live/10 text-accent-live"
              : "bg-accent-danger/10 text-accent-danger"
          }`}
        >
          {correct ? "✓ You got it right" : "✗ Not this time"}
        </div>
        <div className="text-xs text-text-muted">
          You guessed{" "}
          <span className="font-semibold text-text-secondary">{guess}</span> than{" "}
          {threshold}% — resolved at{" "}
          <span className="font-semibold text-text-secondary">{actual}%</span>
        </div>
      </div>
    </Link>
  );
}
