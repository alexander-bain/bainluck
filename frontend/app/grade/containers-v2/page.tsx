"use client";

/**
 * Decision 386: A (#12221 Item 10 / Condition 6) — /grade/containers-v2:
 * 390 px grader for dynamically proposed Kit container pages (preview only).
 * Keep, Fix or Drop each page, with a note.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import {
  KitContainerPageView,
  type KitContainerPageSpec,
  type KitContainerPagesPreviewResponse,
} from "@/components/collections/KitContainerPageView";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  canonicalContainerGradesString,
  computeSha256Hex,
  type ContainerGrade,
  type ContainerGradeEntry,
} from "@/lib/ranking/blindDeckGrade363a";
import {
  buildContainerV2JudgmentPayload,
  CONTAINERS_V2_DRAFT_STORAGE_KEY,
  CONTAINERS_V2_SURFACE,
  restoreContainerV2Grades,
  type SavedContainerV2JudgmentRow,
} from "@/lib/ranking/containersV2Grade12221";

export default function GradeContainersV2Page() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <ContainersV2Session />
    </AdminAuthProvider>
  );
}

function ContainersV2Session() {
  const { secret, clearSecret } = useAdminAuth();

  const [pages, setPages] = useState<KitContainerPageSpec[]>([]);
  const [snapshotAt, setSnapshotAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [index, setIndex] = useState(0);
  const [surfaceScheme, setSurfaceScheme] = useState<"light" | "dark">("light");
  const [grades, setGrades] = useState<Record<string, ContainerGradeEntry>>({});
  const [noteInput, setNoteInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [frozenSha, setFrozenSha] = useState<string | null>(null);
  const [copiedSha, setCopiedSha] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(CONTAINERS_V2_DRAFT_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Record<string, ContainerGradeEntry>;
        if (parsed && typeof parsed === "object") {
          setGrades(parsed);
        }
      }
    } catch {
      // storage unavailable
    }
  }, []);

  useEffect(() => {
    if (!secret) return;
    let cancelled = false;
    setLoading(true);
    setErrorMsg(null);

    Promise.all([
      adminFetchJSON<KitContainerPagesPreviewResponse>("/api/containers/preview/kit-pages", secret),
      adminFetchJSON<{ judgments?: SavedContainerV2JudgmentRow[] }>(
        `/api/admin/ranking-judgments?surface=${CONTAINERS_V2_SURFACE}&limit=100`,
        secret,
      ).catch(() => ({ judgments: [] as SavedContainerV2JudgmentRow[] })),
    ])
      .then(([previewRes, judgmentsRes]) => {
        if (cancelled) return;
        setPages(previewRes.pages || []);
        setSnapshotAt(previewRes.snapshot_captured_at || null);
        const restored = restoreContainerV2Grades(judgmentsRes.judgments || []);
        if (Object.keys(restored).length > 0) {
          setGrades((prev) => ({ ...prev, ...restored }));
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("401") || msg.includes("403")) {
          clearSecret({ rejected: true });
          return;
        }
        setErrorMsg(`Could not load preview container pages (${msg})`);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [secret, clearSecret]);

  const currentPage = pages[index] ?? pages[0] ?? null;
  const currentSlug = currentPage?.slug ?? "";

  useEffect(() => {
    if (!currentSlug) return;
    setNoteInput(grades[currentSlug]?.note || "");
    setStatusMsg(null);
    setErrorMsg(null);
  }, [currentSlug, grades]);

  useEffect(() => {
    try {
      localStorage.setItem(CONTAINERS_V2_DRAFT_STORAGE_KEY, JSON.stringify(grades));
    } catch {
      // ignore
    }
    const gradedNow = pages.filter((p) => Boolean(grades[p.slug])).length;
    if (pages.length > 0 && gradedNow === pages.length) {
      const deckKey = `kit-containers-v2-${snapshotAt || "preview"}`;
      const filtered: Record<string, ContainerGradeEntry> = {};
      for (const p of pages) {
        if (grades[p.slug]) filtered[p.slug] = grades[p.slug];
      }
      const canonical = canonicalContainerGradesString(deckKey, filtered);
      void computeSha256Hex(canonical).then((hex) => setFrozenSha(hex));
    } else {
      setFrozenSha(null);
    }
  }, [grades, pages, snapshotAt]);

  const counts = useMemo(() => {
    const out: Record<ContainerGrade, number> = { Keep: 0, Fix: 0, Drop: 0 };
    for (const p of pages) {
      const entry = grades[p.slug];
      if (entry) out[entry.grade] += 1;
    }
    return out;
  }, [grades, pages]);

  const gradedCount = counts.Keep + counts.Fix + counts.Drop;

  const submitGrade = async (grade: ContainerGrade) => {
    if (!currentPage || saving) return;
    setSaving(true);
    setErrorMsg(null);
    setStatusMsg(null);
    const ts = new Date().toISOString();
    const payload = buildContainerV2JudgmentPayload(currentPage, grade, noteInput, ts);

    try {
      const res = await adminFetch("/api/admin/ranking-judgments", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.status === 401 || res.status === 403) {
        clearSecret({ rejected: true });
        return;
      }
      if (!res.ok) {
        setErrorMsg(`Save failed (${res.status})`);
        return;
      }
      setGrades((prev) => ({
        ...prev,
        [currentPage.slug]: {
          grade,
          note: payload.label_metadata.note,
          updated_at: ts,
        },
      }));
      setStatusMsg(`Saved ${currentPage.slug}: ${grade}`);
      if (index + 1 < pages.length) {
        setIndex(index + 1);
      }
    } catch {
      setErrorMsg("Network error saving grade. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleCopySha = async () => {
    if (!frozenSha) return;
    try {
      await navigator.clipboard.writeText(frozenSha);
      setCopiedSha(true);
      setTimeout(() => setCopiedSha(false), 2000);
    } catch {
      setCopiedSha(false);
    }
  };

  return (
    <main className="min-h-screen bg-surface-deep px-3 pt-4 pb-24 text-text-primary">
      <div className="mx-auto w-full max-w-[390px] space-y-4">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
            <Link href="/grade" className="font-semibold text-accent-brand hover:underline">
              ← Grade home
            </Link>
            <span>Decision 386: A · Preview only</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Container pages v2 (#12221)
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Keep, Fix or Drop each page, with a note.
          </p>
          {snapshotAt && (
            <p className="mt-1 text-[11px] font-medium text-text-muted">
              Snapshot: {snapshotAt}
            </p>
          )}
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-surface-border pt-2.5 text-xs">
            <span data-testid="grade-progress-summary" className="font-semibold text-text-primary">
              {gradedCount}/{pages.length} · Keep {counts.Keep} · Fix {counts.Fix} · Drop {counts.Drop}
            </span>
            <div className="flex items-center gap-1 rounded-lg border border-surface-border bg-surface-elevated p-0.5 text-[11px] font-semibold">
              <button
                type="button"
                data-testid="scheme-toggle-light"
                onClick={() => setSurfaceScheme("light")}
                className={`rounded px-2 py-0.5 transition ${
                  surfaceScheme === "light"
                    ? "bg-surface-card text-text-primary shadow-sm"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                Light
              </button>
              <button
                type="button"
                data-testid="scheme-toggle-dark"
                onClick={() => setSurfaceScheme("dark")}
                className={`rounded px-2 py-0.5 transition ${
                  surfaceScheme === "dark"
                    ? "bg-surface-card text-text-primary shadow-sm"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                Dark
              </button>
            </div>
          </div>

          {pages.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {pages.map((p, i) => {
                const entry = grades[p.slug];
                const active = i === index;
                const pillTone = entry
                  ? entry.grade === "Keep"
                    ? "border-accent-brand/40 bg-accent-brand/10 text-accent-brand"
                    : entry.grade === "Fix"
                      ? "border-accent-warning/40 bg-accent-warning/10 text-accent-warning"
                      : "border-accent-danger/40 bg-accent-danger/10 text-accent-danger"
                  : "border-surface-border bg-surface-elevated text-text-muted";
                return (
                  <button
                    key={p.slug}
                    type="button"
                    data-testid={`jump-page-${i + 1}`}
                    onClick={() => setIndex(i)}
                    className={`h-7 min-w-[28px] rounded-md border px-2 text-xs font-semibold transition ${pillTone} ${
                      active ? "ring-2 ring-accent-brand" : ""
                    }`}
                  >
                    {i + 1}
                  </button>
                );
              })}
            </div>
          )}
        </header>

        {loading && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-center text-sm text-text-secondary">
            Loading dynamically proposed container pages…
          </div>
        )}

        {errorMsg && (
          <div className="rounded-xl border border-accent-danger/40 bg-surface-card p-4 text-xs font-medium text-accent-danger">
            {errorMsg}
          </div>
        )}

        {!loading && !errorMsg && pages.length === 0 && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-center text-sm text-text-secondary">
            No preview container pages are staged yet.
          </div>
        )}

        {!loading && currentPage && (
          <section className="space-y-3">
            <div className="rounded-xl border border-surface-border bg-surface-card p-3 space-y-2.5">
              <div className="flex items-center justify-between text-xs font-semibold text-text-secondary">
                <span data-testid="current-page-meta">
                  Page {index + 1} of {pages.length} · {currentPage.slug}
                </span>
                {grades[currentPage.slug] && (
                  <span data-testid="current-page-grade" className="text-accent-brand">
                    {grades[currentPage.slug].grade}
                  </span>
                )}
              </div>

              <input
                type="text"
                data-testid="grade-note-input"
                value={noteInput}
                onChange={(e) => setNoteInput(e.target.value)}
                placeholder="Note (optional: what to fix or why drop)"
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-brand focus:outline-none"
              />

              <div className="grid grid-cols-3 gap-2">
                {(["Keep", "Fix", "Drop"] as const).map((grade) => {
                  const isCurrent = grades[currentPage.slug]?.grade === grade;
                  const tone =
                    grade === "Keep"
                      ? isCurrent
                        ? "border-accent-brand bg-accent-brand text-text-inverse"
                        : "border-accent-brand/40 bg-accent-brand/10 text-accent-brand hover:bg-accent-brand/20"
                      : grade === "Fix"
                        ? isCurrent
                          ? "border-accent-warning bg-accent-warning text-text-inverse"
                          : "border-accent-warning/40 bg-accent-warning/10 text-accent-warning hover:bg-accent-warning/20"
                        : isCurrent
                          ? "border-accent-danger bg-accent-danger text-text-inverse"
                          : "border-accent-danger/40 bg-accent-danger/10 text-accent-danger hover:bg-accent-danger/20";
                  return (
                    <button
                      key={grade}
                      type="button"
                      data-testid={`grade-btn-${grade}`}
                      disabled={saving}
                      onClick={() => void submitGrade(grade)}
                      className={`min-h-[44px] rounded-xl border px-3 py-2 text-sm font-bold transition disabled:opacity-50 ${tone}`}
                    >
                      {grade}
                    </button>
                  );
                })}
              </div>

              {statusMsg && (
                <div data-testid="grade-save-status" className="text-xs font-medium text-accent-brand">
                  {statusMsg}
                </div>
              )}

              <div className="flex items-center justify-between pt-1 text-xs">
                <button
                  type="button"
                  disabled={index === 0}
                  onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 font-semibold text-text-secondary disabled:opacity-40"
                >
                  ← Previous
                </button>
                <button
                  type="button"
                  disabled={index + 1 >= pages.length}
                  onClick={() => setIndex((prev) => Math.min(pages.length - 1, prev + 1))}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 font-semibold text-text-secondary disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            </div>

            {frozenSha && (
              <div
                data-testid="frozen-sha-card"
                className="rounded-xl border border-accent-brand/40 bg-surface-card p-3.5 space-y-2"
              >
                <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
                  All {pages.length} pages graded
                </div>
                <div className="break-all rounded-lg border border-surface-border bg-surface-elevated p-2 font-mono text-[11px] text-text-primary">
                  {frozenSha}
                </div>
                <button
                  type="button"
                  onClick={() => void handleCopySha()}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-border/40"
                >
                  {copiedSha ? "Copied SHA-256" : "Copy SHA-256"}
                </button>
              </div>
            )}

            <KitContainerPageView page={currentPage} surfaceScheme={surfaceScheme} showDebugMeta={false} />
          </section>
        )}
      </div>
    </main>
  );
}
