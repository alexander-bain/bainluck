"use client";

/**
 * #12288 Slice 2 (Direction 223, Decision 224, Ruling 227-A) —
 * /admin/groupings-preview: private admin-only preview on the website showing
 * Slice 1's three groupings (NFL Week, Oscars Best Picture, 2028 Presidential
 * Race) plus the 4th definition-only grouping (Fed & Economy) while the public
 * switch (CONTAINER_MACHINERY_SLICE1_ENABLED) remains strictly off for everyone else.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON, isAdminAuthError } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import AwardCategoryPairedCard from "@/components/discover/forms/AwardCategoryPairedCard";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";
import { parseCollection, type CollectionHub } from "@/lib/collections";
import type { PairedMetricSet } from "@/lib/discover/visualForms";

interface DiversityPageReport {
  member_count: number;
  section_count: number;
  point_1_pictures_per_screen_390px: {
    screens: number[];
    screen_count: number;
    min_pictures_per_screen: number;
    passes: boolean;
  };
  point_2_longest_form_run: {
    longest_row_run: number;
    longest_section_form_run: number;
    max_allowed: number;
    passes: boolean;
  };
  point_3_forms: {
    member_count: number;
    distinct_forms: string[];
    form_count: number;
    min_required: number;
    passes: boolean;
  };
  point_4_content_mix: {
    content_kinds: Record<string, number>;
    available_topic_kinds: string[];
    kind_count: number;
    largest_kind: string | null;
    largest_kind_share: number;
    max_allowed_share: number;
    passes: boolean;
  };
  direction_228_numerical_scale_order?: {
    checked_scale_markets: number;
    violations: string[];
    passes: boolean;
  };
  overall_passes: boolean;
  failing_points: string[];
}

interface MachineryPreviewEntry {
  slug: string;
  definition: {
    slug: string;
    name: string;
    category: string;
    kicker: string;
    footer: string;
  };
  feed_item: {
    data?: {
      roundup?: {
        machinery_card?: MachineryCardContract | null;
        paired_metric_set?: PairedMetricSet | null;
      } | null;
    } | null;
    roundup_contract?: {
      machinery_card?: MachineryCardContract | null;
      paired_metric_set?: PairedMetricSet | null;
    } | null;
  } | null;
  container: unknown;
  diversity_report: {
    standard: string;
    report_only: boolean;
    slug: string;
    name: string;
    card: {
      form_id: string;
      point_1_pictures_per_screen_390px: { screens: number[]; passes: boolean };
      point_2_longest_form_run: { longest_row_run: number; passes: boolean };
      overall_passes: boolean;
      failing_points: string[];
    };
    page: DiversityPageReport;
    overall_passes: boolean;
  };
}

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

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        ok
          ? "bg-surface-elevated text-accent-positive"
          : "bg-surface-elevated text-accent-negative"
      }`}
    >
      {ok ? "Pass" : "Fail (report-only)"}
    </span>
  );
}

function DiversitySummaryCard({ entry }: { entry: MachineryPreviewEntry }) {
  const { page, card } = entry.diversity_report;
  const p1 = page.point_1_pictures_per_screen_390px;
  const p2 = page.point_2_longest_form_run;
  const p3 = page.point_3_forms;
  const p4 = page.point_4_content_mix;
  const kindSummary = Object.entries(p4.content_kinds)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");

  return (
    <div
      data-testid={`diversity-report-${entry.slug}`}
      className="rounded-card border border-surface-border bg-surface-card p-3.5 text-xs text-text-secondary"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold text-text-primary">
          227: A Diversity Report (report-only)
        </span>
        <StatusBadge ok={page.overall_passes && card.overall_passes} />
      </div>
      <dl className="space-y-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-text-muted">1. Pictures / 390 px screen</dt>
          <dd className="font-medium tabular-nums text-text-primary">
            [{p1.screens.join(", ")}] (min {p1.min_pictures_per_screen}){" "}
            {p1.passes ? "✓" : "✗"}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-text-muted">2. Longest run of 1 form</dt>
          <dd className="font-medium tabular-nums text-text-primary">
            {p2.longest_row_run} rows ({p2.longest_section_form_run} sec, max{" "}
            {p2.max_allowed}) {p2.passes ? "✓" : "✗"}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-text-muted">3. Forms ({p3.member_count} members)</dt>
          <dd className="font-medium tabular-nums text-text-primary">
            {p3.form_count} forms ({p3.distinct_forms.join(", ")}) {p3.passes ? "✓" : "✗"}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-text-muted">4. Content mix &amp; largest share</dt>
          <dd className="font-medium tabular-nums text-text-primary">
            {kindSummary || "none"} · {Math.round(p4.largest_kind_share * 100)}%{" "}
            {p4.largest_kind ?? ""} {p4.passes ? "✓" : "✗"}
          </dd>
        </div>
        {page.direction_228_numerical_scale_order && (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-text-muted">5. Direction 228 scale order</dt>
            <dd className="font-medium tabular-nums text-text-primary">
              {page.direction_228_numerical_scale_order.checked_scale_markets} scale market(s){" "}
              {page.direction_228_numerical_scale_order.passes ? "✓" : "✗"}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function PreviewGroupingColumn({
  entry,
  viewport,
}: {
  entry: MachineryPreviewEntry;
  viewport: "390" | "1280";
}) {
  const parsedHub: CollectionHub | null = useMemo(() => {
    try {
      return parseCollection(entry.container, entry.slug);
    } catch {
      return null;
    }
  }, [entry.container, entry.slug]);

  const contract =
    entry.feed_item?.data?.roundup ?? entry.feed_item?.roundup_contract ?? null;
  const machineryCard = contract?.machinery_card ?? null;
  const pairedSet = contract?.paired_metric_set ?? null;

  return (
    <div
      data-testid={`machinery-preview-${entry.slug}`}
      className={
        viewport === "390"
          ? "w-full max-w-[390px] shrink-0 space-y-5"
          : "w-full max-w-[1200px] space-y-6"
      }
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          <span>Discover card</span>
          <Link
            href={`/collections/${entry.slug}`}
            className="text-accent-brand hover:underline"
          >
            Open /collections/{entry.slug} ›
          </Link>
        </div>
        {machineryCard?.form_id === "paired_stage_bars" && pairedSet ? (
          <AwardCategoryPairedCard set={pairedSet} surface="discover" />
        ) : machineryCard ? (
          <MachineryDiscoverCard card={machineryCard} />
        ) : null}
      </div>

      {parsedHub && parsedHub.state === "published" && (
        <div className="space-y-4 rounded-card border border-surface-border bg-surface-primary p-4">
          <header className="space-y-1 border-b border-surface-border pb-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-accent-brand">
              Container page · {parsedHub.sections.length} sections ·{" "}
              {parsedHub.members.length} members
            </div>
            <h2 className="text-xl font-bold text-text-primary">{parsedHub.title}</h2>
            {parsedHub.subtitle && (
              <p className="text-xs text-text-secondary">{parsedHub.subtitle}</p>
            )}
          </header>
          <div
            className={
              viewport === "1280"
                ? "grid grid-cols-1 gap-6 lg:grid-cols-2"
                : "space-y-5"
            }
          >
            {parsedHub.sections.map((sec) =>
              sec.visualBlock ? (
                <section key={sec.key} className="space-y-2">
                  <div>
                    <h3 className="text-base font-semibold text-text-primary">
                      {sec.title}
                    </h3>
                    {sec.note && (
                      <p className="text-xs text-text-secondary">{sec.note}</p>
                    )}
                  </div>
                  <MachinerySectionRenderer
                    visualBlock={sec.visualBlock}
                    members={sec.members}
                  />
                </section>
              ) : null
            )}
          </div>
        </div>
      )}

      <DiversitySummaryCard entry={entry} />
    </div>
  );
}

function GroupingsPreviewBody() {
  const { secret, clearSecret } = useAdminAuth();
  const [data, setData] = useState<MachineryPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showFourth, setShowFourth] = useState(false);
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

  const visibleItems = useMemo(() => {
    const all = data?.items ?? [];
    return showFourth ? all : all.filter((it) => SLICE1_SLUGS.has(it.slug));
  }, [data, showFourth]);

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
              container page, with Ruling 227-A report-only diversity counts.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowFourth((v) => !v)}
              className="rounded-button border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated"
            >
              {showFourth
                ? "Showing all 4 (+ Fed & Economy)"
                : "Showing Slice 1 (3 groupings) · Show +1 Fed"}
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
          <div className="rounded-card border border-surface-border bg-surface-card p-6 text-sm text-accent-negative">
            {error}
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
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
