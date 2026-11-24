"use client";

/**
 * #13551 (Item 3) — /admin/kit-v1-real-sets:
 * Side-by-side 390px comparison sheet: Today's served card (left) beside
 * deterministic Kit v1 card (right), covering tonight's Top 10 Discover sets
 * and every additional public set that fits, plus the full list of sets kept
 * on today's card with exact refusal reasons.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { KitCardRenderer } from "@/components/discover/kit/KitCardRenderer";
import type { KitV1CardSpec } from "@/components/discover/kit/types";
import { adminFetchJSON, isAdminAuthError } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";

interface TodayRow {
  label: string;
  value: string;
  img?: string | null;
}

interface TodayCardSummary {
  slug: string;
  kind: string;
  form_id: string;
  kicker: string;
  headline: string;
  subtitle: string;
  rows: TodayRow[];
}

interface RealSetComparisonEntry {
  rank: number;
  in_top_10: boolean;
  slug: string;
  common_headline: string;
  stat_caption: string;
  fits: boolean;
  layout: string | null;
  variant: string | null;
  refusal_reason: string | null;
  today: TodayCardSummary;
  kit_card: KitV1CardSpec;
}

interface KeptTodayRow {
  rank: number;
  in_top_10: boolean;
  slug: string;
  name: string;
  today_form: string;
  refusal_reason: string;
}

interface KitV1RealSetsReport {
  kit_version: number;
  generated_at: string;
  total_sets: number;
  fitting_count: number;
  kept_today_count: number;
  top_10: RealSetComparisonEntry[];
  fitting_beyond_top_10: RealSetComparisonEntry[];
  kept_today: KeptTodayRow[];
}

export default function AdminKitV1RealSetsPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return <KitV1RealSetsBody />;
}

function TodayCardBox({ today, rank }: { today: TodayCardSummary; rank: number }) {
  return (
    <article className="w-[390px] max-w-full rounded-2xl border border-surface-border bg-surface-card p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-wider text-text-muted">
        <span className="truncate">{today.kicker || "TODAY"}</span>
        <span className="shrink-0">
          Today #{rank} · {today.form_id}
        </span>
      </div>
      <h3 className="mt-1.5 text-[15px] font-bold leading-snug text-text-primary">
        {today.headline}
      </h3>
      {today.subtitle && (
        <p className="mt-1 text-[12px] leading-relaxed text-text-secondary">
          {today.subtitle}
        </p>
      )}
      {today.rows.length > 0 && (
        <ul className="mt-2.5 space-y-1.5 border-t border-surface-border pt-2">
          {today.rows.map((r, idx) => {
            const initials = r.label
              .split(/\s+/)
              .filter(Boolean)
              .slice(0, 2)
              .map((w) => w[0]?.toUpperCase() ?? "")
              .join("");
            return (
              <li
                key={`${r.label}-${idx}`}
                className="flex items-center justify-between gap-2 text-[12px]"
              >
                <div className="flex min-w-0 items-center gap-2">
                  {r.img ? (
                    <img
                      src={r.img}
                      alt={r.label}
                      className="h-7 w-7 shrink-0 rounded-full border border-surface-border bg-surface-elevated object-cover"
                    />
                  ) : (
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[10px] font-bold text-text-muted">
                      {initials || "·"}
                    </span>
                  )}
                  <span className="truncate text-text-primary">{r.label}</span>
                </div>
                <span className="shrink-0 font-semibold tabular-nums text-text-secondary">
                  {r.value}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

function ComparisonRow({ entry }: { entry: RealSetComparisonEntry }) {
  return (
    <div
      data-comparison-slug={entry.slug}
      className="space-y-1.5 rounded-2xl border border-surface-border bg-surface-elevated/60 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] font-semibold text-text-muted">
        <span>
          #{entry.rank} · <code className="text-text-primary">{entry.slug}</code>
        </span>
        <span>
          {entry.fits
            ? `Kit: ${entry.layout} (${entry.variant ?? "none"})`
            : "Kept today's card"}
        </span>
      </div>
      <div className="flex flex-col items-center gap-3 md:grid md:grid-cols-[390px_390px] md:items-start md:justify-center md:gap-4">
        <div className="w-[390px] max-w-full space-y-1">
          <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-text-muted">
            Today
          </div>
          <TodayCardBox today={entry.today} rank={entry.rank} />
        </div>
        <div className="w-[390px] max-w-full space-y-1">
          <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-accent-brand">
            Kit v1
          </div>
          <KitCardRenderer spec={entry.kit_card} />
        </div>
      </div>
    </div>
  );
}

function KitV1RealSetsBody() {
  const { secret, clearSecret } = useAdminAuth();
  const [report, setReport] = useState<KitV1RealSetsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!secret) return;
    let cancelled = false;
    setLoading(true);
    setErrorMsg(null);
    adminFetchJSON<KitV1RealSetsReport>("/api/containers/preview/kit-v1-real-sets", secret)
      .then((res) => {
        if (!cancelled) setReport(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (isAdminAuthError(err)) {
          clearSecret({ rejected: true });
          return;
        }
        setErrorMsg(err instanceof Error ? err.message : "Failed to load real-sets audit");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [secret, clearSecret]);

  return (
    <main className="min-h-screen bg-surface-deep px-4 py-4 text-text-primary">
      <div className="mx-auto w-full max-w-[880px] space-y-5">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <Link href="/admin" className="font-semibold text-accent-brand hover:underline">
              ← Admin home
            </Link>
            <span>#13551 · kit_version: 1</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Kit v1 vs. Today — Real Public Sets (390px Cards Side by Side)
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Deterministic conversion of tonight&apos;s Top 10 Discover sets and every other fitting
            public container. Preview only — nothing changed in the live feed.
          </p>
          {report && (
            <div className="mt-2.5 flex flex-wrap gap-2 text-[11px] font-semibold">
              <span className="rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-text-primary">
                Total sets: {report.total_sets}
              </span>
              <span className="rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-accent-brand">
                Fitting Kit v1: {report.fitting_count}
              </span>
              <span className="rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-text-secondary">
                Kept today&apos;s card: {report.kept_today_count}
              </span>
            </div>
          )}
        </header>

        {loading && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-xs text-text-muted">
            Running deterministic Kit v1 audit…
          </div>
        )}

        {errorMsg && (
          <div className="rounded-xl border border-accent-danger/40 bg-surface-card p-4 text-xs text-accent-danger">
            {errorMsg}
          </div>
        )}

        {report && (
          <>
            <section className="space-y-3">
              <h2 className="px-1 text-xs font-bold uppercase tracking-wide text-text-muted">
                Tonight&apos;s First 10 on Discover ({report.top_10.length})
              </h2>
              {report.top_10.map((entry) => (
                <ComparisonRow key={`top-${entry.rank}-${entry.slug}`} entry={entry} />
              ))}
            </section>

            <section className="space-y-3 pt-2">
              <h2 className="px-1 text-xs font-bold uppercase tracking-wide text-text-muted">
                Every Other Fitting Public Set ({report.fitting_beyond_top_10.length})
              </h2>
              {report.fitting_beyond_top_10.map((entry) => (
                <ComparisonRow key={`extra-${entry.rank}-${entry.slug}`} entry={entry} />
              ))}
            </section>

            <section className="space-y-2 pt-2">
              <h2 className="px-1 text-xs font-bold uppercase tracking-wide text-text-muted">
                Sets Kept on Today&apos;s Card &amp; Why ({report.kept_today.length})
              </h2>
              <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface-card">
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="border-b border-surface-border bg-surface-elevated text-[11px] uppercase tracking-wider text-text-muted">
                    <tr>
                      <th className="px-3 py-2">#</th>
                      <th className="px-3 py-2">Set</th>
                      <th className="px-3 py-2">Today Form</th>
                      <th className="px-3 py-2">Why Kept on Today&apos;s Card</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {report.kept_today.map((row) => (
                      <tr key={`kept-${row.rank}-${row.slug}`}>
                        <td className="px-3 py-2 font-mono text-text-muted">
                          {row.rank}
                          {row.in_top_10 ? "★" : ""}
                        </td>
                        <td className="px-3 py-2 font-semibold text-text-primary">{row.slug}</td>
                        <td className="px-3 py-2 font-mono text-text-secondary">
                          {row.today_form}
                        </td>
                        <td className="px-3 py-2 text-text-secondary">{row.refusal_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
