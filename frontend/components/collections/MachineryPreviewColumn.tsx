"use client";

import { useMemo } from "react";
import Link from "next/link";
import AwardCategoryPairedCard from "@/components/discover/forms/AwardCategoryPairedCard";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";
import { parseCollection, type CollectionHub } from "@/lib/collections";
import type { PairedMetricSet } from "@/lib/discover/visualForms";

export interface MemberNumberParityReport {
  checked_numbers: number;
  mismatch_count: number;
  mismatches: Array<{
    location: string;
    shown: number;
    member_page: number | null;
  }>;
  passes: boolean;
}

export interface DiversityPageReport {
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
  member_number_parity?: MemberNumberParityReport;
  overall_passes: boolean;
  failing_points: string[];
}

export interface MachineryPreviewEntry {
  slug: string;
  status?: "ok" | "error";
  error?: string | null;
  error_code?: string | null;
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
      member_number_parity?: MemberNumberParityReport;
      overall_passes: boolean;
      failing_points: string[];
    };
    page: DiversityPageReport;
    member_number_parity?: MemberNumberParityReport;
    overall_passes: boolean;
  } | null;
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

export function DiversitySummaryCard({ entry }: { entry: MachineryPreviewEntry }) {
  if (!entry.diversity_report) return null;
  const { page, card } = entry.diversity_report;
  const parity = entry.diversity_report.member_number_parity ?? page.member_number_parity;
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
        {parity && (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-text-muted">6. Member-page number parity</dt>
            <dd className="font-medium tabular-nums text-text-primary">
              {parity.checked_numbers - parity.mismatch_count}/{parity.checked_numbers} match{" "}
              {parity.passes ? "✓" : "✗"}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export function PreviewGroupingColumn({
  entry,
  viewport,
  onRetry,
}: {
  entry: MachineryPreviewEntry;
  viewport: "390" | "1280";
  onRetry?: () => void;
}) {
  const parsedHub: CollectionHub | null = useMemo(() => {
    if (!entry.container) return null;
    try {
      return parseCollection(entry.container, entry.slug);
    } catch {
      return null;
    }
  }, [entry.container, entry.slug]);

  const readFailed =
    entry.status === "error" ||
    !parsedHub ||
    parsedHub.state !== "published" ||
    Boolean(parsedHub.note) ||
    parsedHub.sections.length === 0;

  if (readFailed) {
    const label = entry.definition?.name || entry.slug;
    const msg =
      entry.error ||
      "Couldn't load this grouping right now. Please try again.";
    return (
      <div
        role="alert"
        data-testid={`machinery-error-${entry.slug}`}
        className={
          viewport === "390"
            ? "w-full max-w-[390px] shrink-0 rounded-card border border-surface-border bg-surface-card p-5 space-y-3"
            : "w-full max-w-[1200px] rounded-card border border-surface-border bg-surface-card p-5 space-y-3"
        }
      >
        <div className="text-[11px] font-bold uppercase tracking-wider text-accent-negative">
          {entry.definition?.kicker || "Grouping unavailable"}
        </div>
        <h2 className="text-base font-bold text-text-primary">{label}</h2>
        <p className="text-xs text-text-secondary">{msg}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-button border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-semibold text-accent-brand hover:bg-surface-primary"
          >
            Try again
          </button>
        )}
      </div>
    );
  }

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
          {parsedHub.sections.map((sec, secIdx) => {
            if (!sec.visualBlock) return null;
            const repeatsPageHeadline =
              secIdx === 0 &&
              Boolean(parsedHub.title) &&
              sec.title.trim().toLowerCase() ===
                (parsedHub.title ?? "").trim().toLowerCase();
            return (
              <section key={sec.key} className="space-y-2">
                {(!repeatsPageHeadline || sec.note) && (
                  <div>
                    {!repeatsPageHeadline && (
                      <h3 className="text-base font-semibold text-text-primary">
                        {sec.title}
                      </h3>
                    )}
                    {sec.note && (
                      <p className="text-xs text-text-secondary">{sec.note}</p>
                    )}
                  </div>
                )}
                <MachinerySectionRenderer
                  visualBlock={sec.visualBlock}
                  members={sec.members}
                />
              </section>
            );
          })}
        </div>
      </div>

      <DiversitySummaryCard entry={entry} />
    </div>
  );
}
