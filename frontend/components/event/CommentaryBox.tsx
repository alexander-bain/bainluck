"use client";

// Same-day live feature (Alex, 2026-07-19): AI live-commentary box at the TOP of
// The Open Championship event page. The backend generates this ONLY for The Open
// while play is live, grounded strictly in the leaderboard/win-probability
// numbers (never odds, never invented). This component is purely presentational
// and honest-empty: it renders NOTHING when there is no commentary text — so a
// failed/unavailable generation degrades to no box, never a broken or empty one.

import type { EventConceptResponse } from "@/lib/types";

interface CommentaryBoxProps {
  commentary: EventConceptResponse["commentary"];
  // Belt-and-braces: the page only mounts this when live, but gate here too so a
  // stale cached envelope can never surface the box on a non-live page.
  live: boolean;
}

export default function CommentaryBox({ commentary, live }: CommentaryBoxProps) {
  const text = commentary?.text?.trim();
  if (!live || !text) return null;

  return (
    <section
      aria-label="Live commentary"
      className="bg-surface-card rounded-card shadow-card border border-surface-border px-4 py-3"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-accent-live">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-accent-live opacity-60 animate-ping" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-live" />
          </span>
          Live commentary
        </span>
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          AI · probabilities
        </span>
      </div>
      <p className="text-sm leading-relaxed text-text-primary">{text}</p>
    </section>
  );
}
