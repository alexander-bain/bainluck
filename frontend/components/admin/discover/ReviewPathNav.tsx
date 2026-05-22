"use client";

import { formatTargetName, rateText } from "./utils";

export default function ReviewPathNav({
  groundTruthHits,
  missingCount,
  persistedRuns,
  hardGateIssues,
  topMissBucket,
  repeatRate,
  staleRate,
}: {
  groundTruthHits: number;
  missingCount: number;
  persistedRuns: number;
  hardGateIssues: number;
  topMissBucket: string | null;
  repeatRate: number | null;
  staleRate: number | null;
}) {
  const links = [
    {
      href: "#health",
      label: "Health",
      sub: hardGateIssues === 0 ? `clean / ${groundTruthHits} GT` : `${hardGateIssues} issues`,
    },
    { href: "#diagnostics", label: "Diagnostics", sub: `${persistedRuns} runs` },
    {
      href: "#misses",
      label: "Misses",
      sub: topMissBucket ? formatTargetName(topMissBucket) : `${missingCount} open`,
    },
    {
      href: "#behavior",
      label: "Behavior",
      sub: repeatRate === null || staleRate === null
        ? "loading"
        : `${rateText(repeatRate)} repeat / ${rateText(staleRate)} stale`,
    },
    { href: "#top50", label: "Top 50", sub: "live cards" },
  ];

  return (
    <div className="sticky top-0 z-20 -mx-4 border-y border-surface-border bg-bg-surface/95 px-4 py-2 backdrop-blur">
      <div className="flex items-center gap-2 overflow-x-auto">
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          Review Path
        </span>
        {links.map((link, index) => (
          <a
            key={link.href}
            href={link.href}
            className="shrink-0 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs hover:bg-surface-elevated"
          >
            <span className="font-medium text-text-primary">{index + 1}. {link.label}</span>
            <span className="ml-2 text-text-muted">{link.sub}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
