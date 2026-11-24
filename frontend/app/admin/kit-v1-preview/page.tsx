"use client";

/**
 * #13551 (Rulings 366: B & 367: A) — /admin/kit-v1-preview:
 * Renders all 8 Kit v1 worked examples at 390px directly from GET /api/containers/preview/kit-v1
 * so web proves every shape before iPhone matches from the same JSON.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { KitCardRenderer } from "@/components/discover/kit/KitCardRenderer";
import type { KitV1PreviewResponse } from "@/components/discover/kit/types";
import { adminFetchJSON, isAdminAuthError } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";

export default function AdminKitV1PreviewPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return <KitV1PreviewBody />;
}

function KitV1PreviewBody() {
  const { secret, clearSecret } = useAdminAuth();
  const [payload, setPayload] = useState<KitV1PreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [openJsonIdx, setOpenJsonIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!secret) return;
    let cancelled = false;
    setLoading(true);
    setErrorMsg(null);
    adminFetchJSON<KitV1PreviewResponse>("/api/containers/preview/kit-v1", secret)
      .then((res) => {
        if (!cancelled) setPayload(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (isAdminAuthError(err)) {
          clearSecret({ rejected: true });
          return;
        }
        setErrorMsg(err instanceof Error ? err.message : "Failed to load Kit v1 preview");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [secret, clearSecret]);

  return (
    <main className="min-h-screen bg-surface-deep px-3 py-4 text-text-primary">
      <div className="mx-auto w-full max-w-[390px] space-y-4">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <Link href="/admin" className="font-semibold text-accent-brand hover:underline">
              ← Admin home
            </Link>
            <span>kit_version: 1</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Kit v1 Preview (366: B &amp; 367: A)
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Web renderer first across all 7 better-than-today looks plus Ruling 367: A calendar strip, driven directly by shared server JSON.
          </p>
        </header>

        {loading && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-xs text-text-muted">
            Loading Kit v1 specs…
          </div>
        )}

        {errorMsg && (
          <div className="rounded-xl border border-accent-danger/40 bg-surface-card p-4 text-xs text-accent-danger">
            {errorMsg}
          </div>
        )}

        {payload && (
          <>
            <section className="space-y-4">
              {payload.items.map((spec, idx) => (
                <div key={`${spec.id || spec.variant}-${idx}`} className="space-y-1.5">
                  <div className="flex items-center justify-between px-1 text-[11px] font-semibold text-text-muted">
                    <span>
                      {idx + 1}. {spec.layout} / {spec.variant}
                    </span>
                    <button
                      type="button"
                      onClick={() => setOpenJsonIdx(openJsonIdx === idx ? null : idx)}
                      className="text-accent-brand hover:underline"
                    >
                      {openJsonIdx === idx ? "Hide JSON" : "View JSON"}
                    </button>
                  </div>
                  <KitCardRenderer spec={spec} />
                  {openJsonIdx === idx && (
                    <pre className="max-h-60 overflow-auto rounded-xl border border-surface-border bg-surface-card p-2.5 text-[10px] text-text-secondary">
                      {JSON.stringify(spec, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </section>

            <section className="space-y-2.5 pt-2">
              <h2 className="px-1 text-xs font-bold uppercase tracking-wide text-text-muted">
                Rule &amp; Refusal Gates ({payload.refusals.length})
              </h2>
              {payload.refusals.map((ref) => (
                <div key={ref.title} className="space-y-1">
                  <div className="px-1 text-[11px] font-semibold text-text-secondary">
                    {ref.title}
                  </div>
                  <KitCardRenderer spec={ref.spec} />
                </div>
              ))}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
