"use client";

// #999 L2-66 — freshness as a feature. Shows an honest "as of Xs/Xm ago" for the
// live leaderboard, and flips to a visible STALE state past the threshold so old
// data never reads as current (honesty > polish). SSR-safe: the relative age is
// computed in an effect (Date only runs client-side), so the server + first
// client render show a stable "live" placeholder — no hydration mismatch.

import { useEffect, useState } from "react";

const STALE_MS = 5 * 60 * 1000; // >5 min during play = stale

function formatAge(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
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
  const stale = age != null && age > STALE_MS;

  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${
        stale ? "bg-accent-danger/12 text-accent-danger" : "bg-accent-live/12 text-accent-live"
      }`}
      title={`Data as of ${asOf}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          stale ? "bg-accent-danger" : "bg-accent-live animate-pulse"
        }`}
      />
      {age == null ? "live" : stale ? `Stale · ${formatAge(age)}` : `as of ${formatAge(age)}`}
    </span>
  );
}
