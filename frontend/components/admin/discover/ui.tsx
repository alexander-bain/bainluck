"use client";

import { CheckCircle2, AlertTriangle } from "lucide-react";
import { formatTargetName, signedNumber } from "./utils";

export function StatCard({
  label,
  value,
  ok,
  sub,
}: {
  label: string;
  value: string | number;
  ok?: boolean;
  sub?: string;
}) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-text-muted">{label}</span>
        {ok === undefined ? null : ok ? (
          <CheckCircle2 className="w-4 h-4 text-accent-live" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-accent-danger" />
        )}
      </div>
      <div className="mt-2 text-2xl font-semibold text-text-primary">{value}</div>
      {sub && <div className="mt-1 text-xs text-text-muted">{sub}</div>}
    </div>
  );
}

export function DistributionBars({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data);
  const max = Math.max(...entries.map(([, count]) => count), 1);

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4">
      <h2 className="text-sm font-semibold text-text-primary mb-3">{title}</h2>
      <div className="space-y-2">
        {entries.map(([name, count]) => (
          <div key={name}>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-text-secondary truncate">{formatTargetName(name)}</span>
              <span className="text-text-muted">{count}</span>
            </div>
            <div className="mt-1 h-1.5 bg-surface-elevated rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-futures rounded-full"
                style={{ width: `${Math.max(4, (count / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StatusPill({ children, tone }: { children: string; tone: "ok" | "warn" | "muted" }) {
  const classes =
    tone === "ok"
      ? "bg-accent-live/10 text-accent-live border-accent-live/30"
      : tone === "warn"
        ? "bg-accent-danger/10 text-accent-danger border-accent-danger/30"
        : "bg-surface-elevated text-text-muted border-surface-border";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${classes}`}>
      {children}
    </span>
  );
}

export function DeltaPill({
  value,
  lowerIsBetter,
}: {
  value: number | undefined;
  lowerIsBetter: boolean;
}) {
  if (value === undefined) return null;
  const tone =
    value === 0
      ? "muted"
      : lowerIsBetter
        ? value < 0 ? "ok" : "warn"
        : value > 0 ? "ok" : "warn";
  return <StatusPill tone={tone}>{signedNumber(value, 0)}</StatusPill>;
}
