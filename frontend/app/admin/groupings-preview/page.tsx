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

const ORDERED_PREVIEW_SLUGS = [
  "machinery-nfl-week",
  "machinery-oscars-best-picture",
  "machinery-2028-presidential",
  "machinery-fed-and-macro",
  "machinery-nba-night",
] as const;

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

function buildClientErrorEntry(
  slug: string,
  code: string,
  message: string
): MachineryPreviewEntry {
  return {
    slug,
    status: "error",
    error: message,
    error_code: code,
    definition: { slug, name: slug, category: "", kicker: "", footer: "" },
    feed_item: null,
    container: null,
    diversity_report: null,
  };
}

function GroupingsPreviewBody() {
  const { secret, clearSecret } = useAdminAuth();
  const [publicSwitchEnabled, setPublicSwitchEnabled] = useState(false);
  const [itemsBySlug, setItemsBySlug] = useState<Record<string, MachineryPreviewEntry>>({});
  const [loadingBySlug, setLoadingBySlug] = useState<Record<string, boolean>>({});
  const [showAll, setShowAll] = useState(true);
  const [viewport, setViewport] = useState<"390" | "1280">("390");

  const loadSlug = useCallback(
    async (slug: string) => {
      setLoadingBySlug((prev) => ({ ...prev, [slug]: true }));
      try {
        const res = await adminFetchJSON<MachineryPreviewResponse>(
          `/api/containers/preview/machinery?slugs=${encodeURIComponent(slug)}`,
          secret
        );
        setPublicSwitchEnabled(Boolean(res.public_switch_enabled));
        const match =
          (res.items ?? []).find((it) => it.slug === slug) ?? (res.items ?? [])[0];
        if (match) {
          setItemsBySlug((prev) => ({ ...prev, [slug]: match }));
        } else {
          setItemsBySlug((prev) => ({
            ...prev,
            [slug]: buildClientErrorEntry(
              slug,
              "empty_response",
              `Preview response omitted ${slug}.`
            ),
          }));
        }
      } catch (err) {
        if (isAdminAuthError(err)) {
          clearSecret({ rejected: true });
          return;
        }
        setItemsBySlug((prev) => ({
          ...prev,
          [slug]: buildClientErrorEntry(
            slug,
            "request_failed",
            err instanceof Error ? err.message : `Failed to load ${slug}.`
          ),
        }));
      } finally {
        setLoadingBySlug((prev) => ({ ...prev, [slug]: false }));
      }
    },
    [secret, clearSecret]
  );

  const loadAll = useCallback(() => {
    void Promise.all(ORDERED_PREVIEW_SLUGS.map((slug) => loadSlug(slug)));
  }, [loadSlug]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const targetSlugs = useMemo(
    () =>
      showAll
        ? [...ORDERED_PREVIEW_SLUGS]
        : ORDERED_PREVIEW_SLUGS.filter((slug) => SLICE1_SLUGS.has(slug)),
    [showAll]
  );
  const anyLoading = targetSlugs.some((slug) => loadingBySlug[slug]);
  const loadedCount = targetSlugs.filter((slug) => Boolean(itemsBySlug[slug])).length;

  return (
    <main className="min-h-screen bg-surface-primary px-4 py-6 text-text-primary sm:px-6">
      <div className="mx-auto max-w-[1360px] space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surface-border pb-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-accent-brand">
              Private Admin Preview · Public Switch{" "}
              {publicSwitchEnabled ? "ON" : "OFF"}
            </div>
            <h1 className="text-2xl font-bold text-text-primary">
              Grouping &amp; Container Machinery (#12288)
            </h1>
            <p className="text-sm text-text-secondary">
              One definition produces both the Discover card and the multi-section
              container page, with 227: A Diversity Report counts and member-page
              number parity. Each grouping loads independently (60s cache).
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated"
            >
              {showAll
                ? `Showing all ${ORDERED_PREVIEW_SLUGS.length} groupings`
                : "Showing Slice 1 (3 groupings)"}
            </button>
            <button
              type="button"
              onClick={() => setViewport((v) => (v === "390" ? "1280" : "390"))}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated"
            >
              Viewport: {viewport} px
            </button>
            <button
              type="button"
              onClick={() => loadAll()}
              disabled={anyLoading}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated disabled:opacity-50"
            >
              {anyLoading
                ? `Loading (${loadedCount}/${targetSlugs.length})…`
                : "Refresh all"}
            </button>
          </div>
        </div>

        <div
          className={
            viewport === "390"
              ? "flex flex-wrap items-start gap-6"
              : "space-y-10"
          }
        >
          {targetSlugs.map((slug) => {
            const entry = itemsBySlug[slug];
            if (!entry) {
              return (
                <section
                  key={slug}
                  data-testid={`machinery-loading-${slug}`}
                  className={
                    viewport === "390"
                      ? "w-full max-w-[390px] rounded-card border border-surface-border bg-surface-card p-6 text-sm text-text-secondary"
                      : "w-full rounded-card border border-surface-border bg-surface-card p-6 text-sm text-text-secondary"
                  }
                >
                  Loading {slug}…
                </section>
              );
            }
            return (
              <PreviewGroupingColumn
                key={slug}
                entry={entry}
                viewport={viewport}
                onRetry={() => void loadSlug(slug)}
              />
            );
          })}
        </div>
      </div>
    </main>
  );
}
