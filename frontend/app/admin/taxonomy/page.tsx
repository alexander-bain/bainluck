"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import PageHeader from "@/components/admin/PageHeader";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";

interface TagCount {
  tag: string;
  count: number;
}

interface SportCount {
  sport: string;
  count: number;
}

interface ActionableDefect {
  kind: string;
  id: number;
  reasons: string[];
}

interface ClassificationHealth {
  version: number;
  verdict: "green" | "yellow" | "red" | "unknown";
  reason: string;
  generated_at: string;
  census_complete: boolean;
  eligible: {
    numerator: number;
    denominator: number;
    events: number;
    futures: number;
  };
  actionable: {
    count: number;
    reasons: Record<string, number>;
    representative_ids: ActionableDefect[];
  };
}

interface DashboardData {
  generated_at: string;
  classification_health?: ClassificationHealth;
  event_coverage: { tagged: number; untagged: number };
  futures_coverage: { tagged: number; untagged: number };
  event_tag_distribution: TagCount[];
  futures_tag_distribution: TagCount[];
  sport_distribution: SportCount[];
  signal_distribution: TagCount[];
}

// The page reads the server verdict directly — no client-side thresholds.
const VERDICT_TO_STATUS: Record<
  ClassificationHealth["verdict"],
  "good" | "warning" | "critical"
> = {
  green: "good",
  yellow: "warning",
  red: "critical",
  unknown: "warning",
};

// Human labels for the reason-coded actionable defects.
const REASON_LABELS: Record<string, string> = {
  missing: "No sport identity — can't classify",
  invalid: "Invalid stored tag (out of vocabulary)",
  authority_disagree: "Stored tag disagrees with the source",
};

function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

async function fetchDashboard(secret: string): Promise<DashboardData> {
  return adminFetchJSON<DashboardData>("/api/admin/taxonomy/dashboard", secret);
}

function healthSummary(h: ClassificationHealth): string {
  const { denominator, numerator } = h.eligible;
  switch (h.verdict) {
    case "green":
      return `No — every one of ${denominator.toLocaleString()} eligible items is correctly classified.`;
    case "red":
      return `Yes — ${h.actionable.count.toLocaleString()} eligible item${
        h.actionable.count === 1 ? "" : "s"
      } ${h.actionable.count === 1 ? "has" : "have"} a classification defect.`;
    case "yellow":
      return `Unverified — no defects in ${numerator.toLocaleString()}/${denominator.toLocaleString()} checked, but the census could not be completed.`;
    case "unknown":
    default:
      return "Could not verify — the classification census failed to run.";
  }
}

function CoverageBar({
  label,
  tagged,
  untagged,
}: {
  label: string;
  tagged: number;
  untagged: number;
}) {
  const total = tagged + untagged;
  const pct = total > 0 ? Math.round((tagged / total) * 100) : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-text-primary">{label}</span>
        <span className="text-text-muted">
          {tagged.toLocaleString()} / {total.toLocaleString()} ({pct}%)
        </span>
      </div>
      <div className="h-2 bg-surface-border rounded-full overflow-hidden">
        <div
          className="h-full bg-accent-futures rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ActionableDefects({ health }: { health: ClassificationHealth }) {
  const { actionable } = health;

  if (health.verdict === "unknown") {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-1">
          Actionable defects
        </h2>
        <p className="text-xs text-text-muted">
          The census could not run ({health.reason}); the verdict is unknown
          rather than assumed healthy.
        </p>
      </div>
    );
  }

  if (actionable.count === 0) {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-1">
          Actionable defects
        </h2>
        <p className="text-xs text-text-secondary">
          None. Every eligible (product-visible) item classifies correctly.
          {!health.census_complete &&
            " Census incomplete, so this is not yet a clean bill of health."}
        </p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">
          Actionable defects
        </h2>
        <span className="text-xs text-text-muted">
          {actionable.count.toLocaleString()} eligible item
          {actionable.count === 1 ? "" : "s"}
        </span>
      </div>

      {/* Reason breakdown */}
      <div className="space-y-1">
        {Object.entries(actionable.reasons).map(([reason, count]) => (
          <div
            key={reason}
            className="flex items-center justify-between text-xs"
          >
            <span className="text-text-secondary">{reasonLabel(reason)}</span>
            <span className="text-text-muted">{count.toLocaleString()}</span>
          </div>
        ))}
      </div>

      {/* Representative IDs (bounded sample, not the headline) */}
      {actionable.representative_ids.length > 0 && (
        <div className="pt-2 border-t border-surface-border">
          <p className="text-micro text-text-muted mb-1.5">
            Sample ({actionable.representative_ids.length} of{" "}
            {actionable.count.toLocaleString()}):
          </p>
          <div className="flex flex-wrap gap-1.5">
            {actionable.representative_ids.map((d) => (
              <span
                key={`${d.kind}-${d.id}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-border text-micro text-text-secondary"
                title={d.reasons.map(reasonLabel).join("; ")}
              >
                <code>
                  {d.kind}:{d.id}
                </code>
                <span className="text-text-muted">
                  {d.reasons.map(reasonLabel).join(", ")}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TagTable({
  title,
  items,
  keyField,
}: {
  title: string;
  items: { tag?: string; sport?: string; count: number }[];
  keyField: "tag" | "sport";
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, 15);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-text-muted">No data</p>
      ) : (
        <>
          <div className="space-y-1">
            {visible.map((item, i) => {
              const label =
                keyField === "tag" ? item.tag! : item.sport!;
              const maxCount = items[0].count;
              const barWidth =
                maxCount > 0
                  ? Math.max(4, Math.round((item.count / maxCount) * 100))
                  : 0;

              // Color-code by namespace
              let barColor = "bg-text-muted";
              if (label.startsWith("sport:")) barColor = "bg-blue-500";
              else if (label.startsWith("status:")) barColor = "bg-green-500";
              else if (label.startsWith("signal:")) barColor = "bg-orange-500";
              else if (label.startsWith("importance:"))
                barColor = "bg-purple-500";
              else if (label.startsWith("timing:")) barColor = "bg-yellow-500";
              else if (label.startsWith("league:")) barColor = "bg-cyan-500";
              else if (label.startsWith("source:")) barColor = "bg-pink-500";

              return (
                <div key={label} className="flex items-center gap-2 text-xs">
                  <span className="text-text-muted w-5 text-right shrink-0">
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <code className="text-text-secondary truncate">
                        {label}
                      </code>
                      <span className="text-text-muted shrink-0">
                        {item.count.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-1 bg-surface-border rounded-full mt-0.5">
                      <div
                        className={`h-full rounded-full ${barColor}`}
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {items.length > 15 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-accent-futures mt-2 hover:underline"
            >
              {expanded
                ? "Show less"
                : `Show all ${items.length} items`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

export default function TaxonomyDashboard() {
  usePageTracking({
    pageType: "admin_taxonomy",
    pageTitle: "Taxonomy Dashboard",
  });
  useScrollDepth({ pageType: "admin_taxonomy" });
  useEngagementTime({ pageType: "admin_taxonomy" });

  const { secret } = useAdminAuth();

  const { data, error, isLoading } = useSWR(
    ["taxonomy-dashboard", secret],
    () => fetchDashboard(secret),
    { refreshInterval: 60000 }
  );

  const health = data?.classification_health;
  const headerStatus = isLoading
    ? "loading"
    : health
    ? VERDICT_TO_STATUS[health.verdict]
    : "warning";
  const headerSummary = isLoading
    ? "Loading..."
    : health
    ? healthSummary(health)
    : "Verdict unavailable — showing coverage only.";

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <PageHeader
          question="Is classification hurting the product?"
          status={headerStatus}
          summary={headerSummary}
          ideal="Zero eligible (product-visible) items with a classification defect."
        />
        {data && (
          <span className="text-micro text-text-muted">
            Updated{" "}
            {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg">
          {error.message}
        </div>
      )}

      {isLoading && (
        <div className="text-sm text-text-muted animate-pulse">Loading...</div>
      )}

      {data && (
        <>
          {/* The real question: actionable, product-visible defects */}
          {health && <ActionableDefects health={health} />}

          {/* Signal Distribution */}
          {data.signal_distribution.length > 0 && (
            <TagTable
              title="Signal Tags (live + scheduled events)"
              items={data.signal_distribution}
              keyField="tag"
            />
          )}

          {/* Tag Distributions */}
          <div className="grid md:grid-cols-2 gap-4">
            <TagTable
              title="Event Tags (7-day)"
              items={data.event_tag_distribution}
              keyField="tag"
            />
            <TagTable
              title="Futures Tags"
              items={data.futures_tag_distribution}
              keyField="tag"
            />
          </div>

          {/* Sport Distribution */}
          <TagTable
            title="Sport Distribution (active events)"
            items={data.sport_distribution.map((s) => ({
              tag: s.sport,
              count: s.count,
            }))}
            keyField="tag"
          />

          {/* Backfill Coverage — maintenance debt, NOT product health */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4 space-y-3">
            <h2 className="text-sm font-semibold text-text-primary">
              Backfill Coverage
            </h2>
            <p className="text-xs text-text-muted">
              How many items have <em>persisted</em> tags. This is maintenance
              debt, not product health: classification is computed inline from
              the source columns, so an item with empty persisted tags still
              renders correctly. Low coverage here does not mean users are
              affected — the verdict above answers that.
            </p>
            <CoverageBar
              label="Events (active) — persisted"
              tagged={data.event_coverage.tagged}
              untagged={data.event_coverage.untagged}
            />
            <CoverageBar
              label="Futures (open) — persisted"
              tagged={data.futures_coverage.tagged}
              untagged={data.futures_coverage.untagged}
            />
          </div>
        </>
      )}
    </div>
  );
}
