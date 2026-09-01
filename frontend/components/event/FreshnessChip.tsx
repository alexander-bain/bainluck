"use client";

// #999 L2-66 — freshness as a feature. Shows an honest "as of Xs/Xm ago" for the
// live leaderboard, and flips to a visible warning past the threshold so old
// data never reads as current (honesty > polish). SSR-safe: the relative age is
// computed in an effect (Date only runs client-side), so the server + first
// client render show a stable "live" placeholder — no hydration mismatch.
//
// UX-P251: the warning state used to name our own `price_state` enum at the
// reader. That word has been in `JARGON_BANS` since UX-P145 and shipped anyway,
// because no guard could see it — `__tests__/lib/freshnessChipCopy` carries the
// reason and the general clause. The copy now lives in `freshnessLabel`: ONE
// pure function, so the sentence a reader sees exists somewhere a test can hold
// it whole.

import { useEffect, useState } from "react";

const STOPPED_MS = 5 * 60 * 1000; // >5 min during play = the data has stopped

function formatAge(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

export interface FreshnessLabel {
  /** Exactly what the reader reads. The whole sentence, in one place. */
  text: string;
  /** Drives the colour and the dot. Derived here so the two cannot disagree. */
  stopped: boolean;
}

/**
 * The chip's copy, as a pure function of one number.
 *
 * `age === null` is the SSR / first-client-render state, before the effect has
 * run. It is not "we have no data" — the caller has already returned `null` for
 * that — so it says `live` rather than inventing an age.
 *
 * Past the threshold the chip states what IS true rather than naming our
 * internal state for it. The age stays: removing the jargon must not remove the
 * warning, or the fix trades one dishonesty for another.
 */
export function freshnessLabel(age: number | null): FreshnessLabel {
  if (age == null) return { text: "live", stopped: false };
  if (age > STOPPED_MS) return { text: `not updating · ${formatAge(age)}`, stopped: true };
  return { text: `as of ${formatAge(age)}`, stopped: false };
}

export default function FreshnessChip({ asOf }: { asOf?: string | null }) {
  const [age, setAge] = useState<number | null>(null);

  useEffect(() => {
    if (!asOf) return;
    const t = new Date(asOf).getTime();
    if (Number.isNaN(t)) return;
    const tick = () => setAge(Date.now() - t);
    tick();
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, [asOf]);

  if (!asOf) return null;
  const { text, stopped } = freshnessLabel(age);

  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${
        stopped ? "bg-accent-danger/12 text-accent-danger" : "bg-accent-live/12 text-accent-live"
      }`}
      title={`Data as of ${asOf}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          stopped ? "bg-accent-danger" : "bg-accent-live animate-pulse"
        }`}
      />
      {text}
    </span>
  );
}
