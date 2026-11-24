"use client";

/**
 * Admin-only preview surface for Forms Lab Batch 1 (#13551).
 * Never public until Alex grades every look in the blind forms deck (#13550).
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { FormsLabBatch1Card } from "@/components/discover/forms/FormsLabBatch1Dispatcher";
import styles from "@/components/discover/forms/formsLabPreview.module.css";
import type {
  FormsLabBatch1PreviewPayload,
  FormsLabCardEnvelope,
  FormsLabLookGroup,
} from "@/components/discover/forms/types_forms_lab_13551";
import { adminFetchJSON, isAdminAuthError } from "@/lib/adminFetch";

const LOOK_TITLES: Record<FormsLabCardEnvelope["look_id"], string> = {
  grid_of_cells: "Item 3 · Grid of cells (Places + Scoreboard)",
  one_axis: "Item 4 · One axis (Shared scale + Deadline race + The climb)",
  calendar_strip: "Item 5 · Calendar strip (Decision 367 shaded-only)",
  casting_sheet: "Item 6 · Casting sheet with pictures",
  bubble_and_cut: "Item 7 · Bubble line + The cut by conference",
};

export default function AdminFormsLabPreviewPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-surface-base px-4 py-8 text-text-primary">
          <div className="mx-auto max-w-5xl text-sm text-text-secondary">Loading Forms Lab preview…</div>
        </main>
      }
    >
      <AdminFormsLabPreviewInner />
    </Suspense>
  );
}

function AdminFormsLabPreviewInner() {
  const { secret, clearSecret } = useAdminAuth();
  const searchParams = useSearchParams();
  const queryLook = searchParams?.get("look") || "";
  const sheetMode = searchParams?.get("sheet") === "1";

  const [payload, setPayload] = useState<FormsLabBatch1PreviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeRefusals, setIncludeRefusals] = useState(true);
  const [activeLook, setActiveLook] = useState<string>(queryLook);

  useEffect(() => {
    setActiveLook(queryLook);
  }, [queryLook]);

  const loadPreview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (includeRefusals) qs.set("include_refusals", "true");
      if (queryLook) qs.set("look", queryLook);
      const data = await adminFetchJSON<FormsLabBatch1PreviewPayload>(
        `/api/containers/preview/forms-lab?${qs.toString()}`,
        secret,
      );
      setPayload(data);
    } catch (err) {
      if (isAdminAuthError(err)) {
        clearSecret({ rejected: true });
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load preview");
    } finally {
      setLoading(false);
    }
  }, [clearSecret, includeRefusals, queryLook, secret]);

  useEffect(() => {
    void loadPreview();
  }, [loadPreview]);

  const visibleLooks = useMemo(() => {
    const looks = payload?.looks || [];
    if (!activeLook) return looks;
    return looks.filter((g) => g.look_id === activeLook);
  }, [payload, activeLook]);

  return (
    <main className="min-h-screen bg-surface-base px-4 py-6 text-text-primary">
      <div className="mx-auto max-w-6xl space-y-6">
        {!sheetMode && (
          <header className="rounded-xl border border-surface-border bg-surface-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
                  Admin Preview Only · Not Public (#13551)
                </p>
                <h1 className="mt-1 text-xl font-bold text-text-primary">
                  Forms Lab Batch 1 Preview (390px Light &amp; Dark)
                </h1>
                <p className="mt-1 text-sm text-text-secondary">
                  Pre-draw truth checks active · Decision 367 daily numbers:{" "}
                  {payload?.decision_367_daily_numbers_enabled ? "enabled" : "off (shaded only)"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-medium text-text-primary">
                  <input
                    type="checkbox"
                    checked={includeRefusals}
                    onChange={(e) => setIncludeRefusals(e.target.checked)}
                  />
                  Show refusal demos
                </label>
                <select
                  aria-label="Filter look"
                  value={activeLook}
                  onChange={(e) => setActiveLook(e.target.value)}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-medium text-text-primary"
                >
                  <option value="">All Batch 1 looks</option>
                  {Object.entries(LOOK_TITLES).map(([lid, label]) => (
                    <option key={lid} value={lid}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </header>
        )}

        {loading && !payload && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-secondary">
            Loading Forms Lab Batch 1 preview…
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-accent-danger">
            {error}
          </div>
        )}

        {visibleLooks.map((group: FormsLabLookGroup) => (
          <section
            key={group.look_id}
            data-sheet-look={group.look_id}
            className="space-y-4 rounded-xl border border-surface-border bg-surface-card p-4"
          >
            {!sheetMode && (
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-surface-border pb-3">
                <h2 className="text-base font-bold text-text-primary">
                  {LOOK_TITLES[group.look_id] || group.look_id}
                </h2>
                <span className="text-xs text-text-secondary">
                  {group.real_sets.length} real sets across{" "}
                  {new Set(group.real_sets.map((s) => s.topic.split("·")[0].trim())).size} topics
                </span>
              </div>
            )}

            <div className={styles.sheetRow}>
              <div className={`${styles.phoneCanvas} ${styles.flTheme}`} data-theme="light">
                <div className={styles.modeBadge}>Light · 390px</div>
                {group.cards.map((card) => (
                  <FormsLabBatch1Card key={`light-${card.card_id}`} card={card} />
                ))}
              </div>
              <div className={`${styles.phoneCanvas} ${styles.flTheme} ${styles.flDark}`} data-theme="dark">
                <div className={styles.modeBadge}>Dark · 390px</div>
                {group.cards.map((card) => (
                  <FormsLabBatch1Card key={`dark-${card.card_id}`} card={card} />
                ))}
              </div>
            </div>

            {!sheetMode && (
              <div className="rounded-lg border border-surface-border bg-surface-elevated p-3">
                <div className="text-xs font-semibold text-text-primary">
                  Verified Real Sets ({group.real_sets.length})
                </div>
                <ul className="mt-1.5 grid gap-1 text-xs text-text-secondary md:grid-cols-2">
                  {group.real_sets.map((s) => (
                    <li key={s.set_name}>
                      <strong>[{s.topic}]</strong> {s.set_name}{" "}
                      <span className="text-text-muted">({s.source_ref})</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
