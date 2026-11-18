"use client";

/**
 * #12288 Slice 2 & Slice 6 (Direction 223, Decision 224, Ruling 227-A) —
 * /admin/groupings-preview: private admin-only preview on the website showing
 * all candidate machinery groupings while the public switch
 * (CONTAINER_MACHINERY_SLICE1_ENABLED) remains strictly off for everyone else.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON, isAdminAuthError } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  PreviewGroupingColumn,
  type MachineryPreviewEntry,
} from "@/components/collections/MachineryPreviewColumn";

interface MachineryPreviewResponse {
  public_switch_enabled: boolean;
  count: number;
  items: MachineryPreviewEntry[];
}

const SLICE1_SLUGS = new Set([
  "machinery-nfl-week",
  "machinery-oscars-best-picture",
  "machinery-2028-presidential",
]);

export default function AdminGroupingsPreviewPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return <GroupingsPreviewBody />;
}

function GroupingsPreviewBody() {
  const { secret, clearSecret } = useAdminAuth();
  const [data, setData] = useState<MachineryPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(true);
  const [viewport, setViewport] = useState<"390" | "1280">("390");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminFetchJSON<MachineryPreviewResponse>(
        "/api/containers/preview/machinery",
        secret
      );
      setData(res);
    } catch (err) {
      if (isAdminAuthError(err)) {
        clearSecret({ rejected: true });
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load machinery preview.");
    } finally {
      setLoading(false);
    }
  }, [secret, clearSecret]);

  useEffect(() => {
    void load();
  }, [load]);

  const allCount = data?.items.length ?? 0;
  const visibleItems = useMemo(() => {
    const all = data?.items ?? [];
    return showAll ? all : all.filter((it) => SLICE1_SLUGS.has(it.slug));
  }, [data, showAll]);

  return (
    <main className="min-h-screen bg-surface-primary px-4 py-6 text-text-primary sm:px-6">
      <div className="mx-auto max-w-[1360px] space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surface-border pb-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-accent-brand">
              Private Admin Preview · Public Switch{" "}
              {data?.public_switch_enabled ? "ON" : "OFF"}
            </div>
            <h1 className="text-2xl font-bold text-text-primary">
              Grouping &amp; Container Machinery (#12288)
            </h1>
            <p className="text-sm text-text-secondary">
              One definition produces both the Discover card and the multi-section
              container page, with 227: A Diversity Report counts and member-page
              number parity.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated"
            >
              {showAll
                ? `Showing all ${allCount || 4} groupings`
                : "Showing Slice 1 (3 groupings)"}
            </button>
            <button
              type="button"
              onClick={() => setViewport((v) => (v === "390" ? "1280" : "390"))}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated"
            >
              Viewport: {viewport} px
            </button>
          </div>
        </div>

        {loading && (
          <div className="rounded-card border border-surface-border bg-surface-card p-6 text-sm text-text-secondary">
            Loading live machinery groupings…
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-card border border-surface-border bg-surface-card p-6 space-y-3 text-sm text-accent-negative"
          >
            <p>{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-button border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-semibold text-accent-brand hover:bg-surface-primary"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && (
          <div
            className={
              viewport === "390"
                ? "flex flex-wrap items-start gap-6"
                : "space-y-10"
            }
          >
            {visibleItems.map((entry) => (
              <PreviewGroupingColumn
                key={entry.slug}
                entry={entry}
                viewport={viewport}
                onRetry={() => void load()}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
