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

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TagCount {
  tag: string;
  count: number;
}

interface SportCount {
  sport: string;
  count: number;
}

interface DashboardData {
  generated_at: string;
  event_coverage: { tagged: number; untagged: number };
  futures_coverage: { tagged: number; untagged: number };
  event_tag_distribution: TagCount[];
  futures_tag_distribution: TagCount[];
  sport_distribution: SportCount[];
  signal_distribution: TagCount[];
}

async function fetchDashboard(secret: string): Promise<DashboardData> {
  const res = await fetch(
    `${API_URL}/api/admin/taxonomy/dashboard?secret=${encodeURIComponent(secret)}`
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
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

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
<PageHeader
          question="How well is our content classified?"
          status={isLoading ? "loading" : data ? (data.event_coverage.untagged > 0 || data.futures_coverage.untagged > 0 ? "warning" : "good") : "good"}
          summary={isLoading ? "Loading..." : data ? `Events: ${data.event_coverage.tagged}/${data.event_coverage.tagged + data.event_coverage.untagged} tagged` : "No data"}
          ideal="100% of events and futures markets classified."
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
          {/* Coverage */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4 space-y-3">
            <h2 className="text-sm font-semibold text-text-primary">
              Tag Coverage
            </h2>
            <CoverageBar
              label="Events (active)"
              tagged={data.event_coverage.tagged}
              untagged={data.event_coverage.untagged}
            />
            <CoverageBar
              label="Futures (open)"
              tagged={data.futures_coverage.tagged}
              untagged={data.futures_coverage.untagged}
            />
          </div>

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
        </>
      )}
    </div>
  );
}
