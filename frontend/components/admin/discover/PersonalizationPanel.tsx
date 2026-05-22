"use client";

import type { PersonalizationRollup } from "./types";
import { StatusPill } from "./ui";
import { formatTargetName, signedNumber } from "./utils";

export default function PersonalizationPanel({ rollup }: { rollup: PersonalizationRollup }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Personalization</h2>
          <p className="text-xs text-text-muted mt-1">
            Authenticated debug traces across the current top 50.
          </p>
        </div>
        <StatusPill tone={rollup.traced > 0 ? "ok" : "muted"}>
          {rollup.traced > 0 ? `${rollup.traced} traced` : "anonymous"}
        </StatusPill>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
        <div>
          <div className="text-text-muted">Personalized</div>
          <div className="text-text-primary font-semibold">{rollup.personalized}/{rollup.total}</div>
        </div>
        <div>
          <div className="text-text-muted">Boosted</div>
          <div className="text-accent-live font-semibold">{rollup.boosted}</div>
        </div>
        <div>
          <div className="text-text-muted">Suppressed</div>
          <div className="text-accent-danger font-semibold">{rollup.suppressed}</div>
        </div>
        <div>
          <div className="text-text-muted">Avg multiplier</div>
          <div className="text-text-primary font-semibold">
            {rollup.avgMultiplier === null ? "none" : `${rollup.avgMultiplier.toFixed(2)}x`}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Avg score delta</div>
          <div className="text-text-primary font-semibold">
            {rollup.avgScoreDelta === null ? "none" : signedNumber(rollup.avgScoreDelta, 1)}
          </div>
        </div>
      </div>

      {rollup.categories.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">Category Effects</div>
          <div className="grid md:grid-cols-2 gap-2">
            {rollup.categories.slice(0, 6).map((row) => (
              <div key={row.category} className="rounded-lg bg-surface-elevated/50 border border-surface-border p-2">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-text-primary">{formatTargetName(row.category)}</span>
                  <span className="text-text-muted">{row.count} cards</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <StatusPill tone={row.avgScoreDelta >= 0 ? "ok" : "warn"}>
                    {`score ${signedNumber(row.avgScoreDelta, 1)}`}
                  </StatusPill>
                  <StatusPill tone="muted">{`${row.avgMultiplier.toFixed(2)}x`}</StatusPill>
                  {row.boosted > 0 && <StatusPill tone="ok">{`${row.boosted} boosted`}</StatusPill>}
                  {row.suppressed > 0 && <StatusPill tone="warn">{`${row.suppressed} suppressed`}</StatusPill>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-text-muted">
          Sign in before loading this admin page to inspect personalized ranking effects.
        </div>
      )}

      {rollup.reasons.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rollup.reasons.slice(0, 8).map((row) => (
            <StatusPill key={row.reason} tone="muted">
              {`${formatTargetName(row.reason)}: ${row.count}`}
            </StatusPill>
          ))}
        </div>
      )}
    </div>
  );
}
