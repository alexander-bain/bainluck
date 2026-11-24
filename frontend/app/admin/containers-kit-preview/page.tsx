"use client";

/**
 * Decision 386: A (#12221 Item 9) — Private preview of dynamic Kit container pages
 * side-by-side at 390 px in Light & Dark.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import {
  KitContainerPageView,
  type KitContainerPagesPreviewResponse,
} from "@/components/collections/KitContainerPageView";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { adminFetchJSON } from "@/lib/adminFetch";

export default function AdminContainersKitPreviewPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  return <ContainersKitPreviewContent />;
}

function ContainersKitPreviewContent() {
  const { secret, clearSecret } = useAdminAuth();
  const [payload, setPayload] = useState<KitContainerPagesPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!secret) return;
    let cancelled = false;
    setLoading(true);
    setErrorMsg(null);
    adminFetchJSON<KitContainerPagesPreviewResponse>("/api/containers/preview/kit-pages", secret)
      .then((res) => {
        if (!cancelled) {
          setPayload(res);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("401") || msg.includes("403")) {
          clearSecret({ rejected: true });
          return;
        }
        setErrorMsg(`Could not load Kit container preview pages (${msg})`);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [secret, clearSecret]);

  return (
    <main className="min-h-screen bg-surface-deep px-4 py-6 text-text-primary">
      <div className="mx-auto max-w-[860px] space-y-6">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm">
          <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
            <Link href="/admin/kit-v1-preview" className="font-semibold text-accent-brand hover:underline">
              ← Kit v1 examples
            </Link>
            <span>Decision 386: A · Preview only</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Kit Container Pages Preview (#12221 Item 9)
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Uncovered market families composed dynamically into disjoint Kit sections at 390 px width (Light &amp; Dark).
          </p>
          {payload?.snapshot_captured_at && (
            <p className="mt-1.5 text-[11px] font-medium text-text-muted">
              Snapshot captured: {payload.snapshot_captured_at}
            </p>
          )}
        </header>

        {loading && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-center text-sm text-text-secondary">
            Loading preview container pages…
          </div>
        )}

        {errorMsg && (
          <div className="rounded-xl border border-accent-danger/40 bg-surface-card p-4 text-xs font-medium text-accent-danger">
            {errorMsg}
          </div>
        )}

        {payload && (
          <div className="space-y-8">
            {payload.pages.map((page) => (
              <div key={page.slug} className="space-y-2">
                <div className="flex items-center justify-between px-1 text-xs font-semibold text-text-secondary">
                  <span>{page.title} ({page.slug})</span>
                  <span>{page.section_count} distinct shapes · {page.market_count} markets</span>
                </div>
                <div className="flex flex-wrap gap-6">
                  <div className="w-[390px] max-w-full shrink-0 space-y-1">
                    <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                      Light · 390 px
                    </div>
                    <KitContainerPageView page={page} surfaceScheme="light" />
                  </div>
                  <div className="w-[390px] max-w-full shrink-0 space-y-1">
                    <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                      Dark · 390 px
                    </div>
                    <KitContainerPageView page={page} surfaceScheme="dark" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
