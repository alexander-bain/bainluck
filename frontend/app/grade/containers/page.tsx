"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * #13550 (363: A) — /grade/containers: 390px blind 20-set grader.
 * One set at a time: Discover card on top, opened set page underneath, Keep / Fix / Drop + note.
 * Once all 20 are graded, renders the frozen SHA-256 checksum to post on #13544 before the key opens.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import containersDeckRaw from "@/data/containers_blind_20_deck_2026_11_23.json";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  canonicalContainerGradesString,
  computeSha256Hex,
  type BlindContainersDeck,
  type ContainerGrade,
  type ContainerGradeEntry,
} from "@/lib/ranking/blindDeckGrade363a";

const CONTAINERS_DECK = containersDeckRaw as unknown as BlindContainersDeck;
const DRAFT_STORAGE_KEY = "bainluck_363a_containers_grades_v1";

interface SavedContainerRow {
  market_name?: string;
  label?: string;
  notes?: string | null;
  created_at?: string;
  label_metadata?: {
    item_id?: string;
    grade?: ContainerGrade;
    note?: string;
    timestamp?: string;
  };
}

export default function GradeContainersDeckPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <ContainersDeckSession />
    </AdminAuthProvider>
  );
}

function ContainersDeckSession() {
  const { secret, clearSecret } = useAdminAuth();
  const items = CONTAINERS_DECK.items;

  const [index, setIndex] = useState(0);
  const [grades, setGrades] = useState<Record<string, ContainerGradeEntry>>({});
  const [noteInput, setNoteInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [frozenSha, setFrozenSha] = useState<string | null>(null);
  const [copiedSha, setCopiedSha] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
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
    (async () => {
      try {
        const res = await adminFetchJSON<{ judgments?: SavedContainerRow[] }>(
          "/api/admin/ranking-judgments?surface=grade_containers_deck&limit=100",
          secret,
        );
        if (cancelled) return;
        const restored: Record<string, ContainerGradeEntry> = {};
        // Rows arrive newest-first; keep newest per item_id
        for (const row of res.judgments || []) {
          const itemId = row.label_metadata?.item_id || row.market_name;
          const grade = (row.label_metadata?.grade || row.label) as ContainerGrade | undefined;
          if (!itemId || !grade || !["Keep", "Fix", "Drop"].includes(grade) || restored[itemId]) {
            continue;
          }
          restored[itemId] = {
            grade,
            note: (row.label_metadata?.note ?? row.notes ?? "").trim(),
            updated_at: row.label_metadata?.timestamp || row.created_at || "",
          };
        }
        if (Object.keys(restored).length > 0) {
          setGrades((prev) => ({ ...prev, ...restored }));
        }
      } catch {
        // draft fallback remains active
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [secret]);

  const currentItem = items[index] ?? items[0];

  useEffect(() => {
    if (!currentItem) return;
    setNoteInput(grades[currentItem.item_id]?.note || "");
    setStatusMsg(null);
    setErrorMsg(null);
  }, [currentItem, grades]);

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(grades));
    } catch {
      // ignore
    }
    const gradedCountNow = items.filter((it) => Boolean(grades[it.item_id])).length;
    if (gradedCountNow === items.length && items.length > 0) {
      const canonical = canonicalContainerGradesString(CONTAINERS_DECK.deck_id, grades);
      void computeSha256Hex(canonical).then((hex) => setFrozenSha(hex));
    } else {
      setFrozenSha(null);
    }
  }, [grades, items]);

  const counts = useMemo(() => {
    const out: Record<ContainerGrade, number> = { Keep: 0, Fix: 0, Drop: 0 };
    for (const it of items) {
      const entry = grades[it.item_id];
      if (entry) out[entry.grade] += 1;
    }
    return out;
  }, [grades, items]);

  const gradedCount = counts.Keep + counts.Fix + counts.Drop;

  const submitGrade = async (grade: ContainerGrade) => {
    if (!currentItem || saving) return;
    setSaving(true);
    setErrorMsg(null);
    setStatusMsg(null);
    const ts = new Date().toISOString();
    const trimmedNote = noteInput.trim();
    try {
      const res = await adminFetch("/api/admin/ranking-judgments", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          surface: "grade_containers_deck",
          item_type: "containers_blind_20",
          market_name: currentItem.item_id,
          label: grade,
          notes: trimmedNote || null,
          reviewer: "alex",
          label_metadata: {
            deck_id: CONTAINERS_DECK.deck_id,
            seed: CONTAINERS_DECK.seed,
            item_id: currentItem.item_id,
            grade,
            note: trimmedNote,
            timestamp: ts,
          },
        }),
      });
      if (res.status === 401 || res.status === 403) {
        clearSecret({ rejected: true });
        return;
      }
      if (!res.ok) {
        setErrorMsg(`Save failed (${res.status})`);
        return;
      }
      const nextGrades: Record<string, ContainerGradeEntry> = {
        ...grades,
        [currentItem.item_id]: { grade, note: trimmedNote, updated_at: ts },
      };
      setGrades(nextGrades);
      setStatusMsg(`Saved ${currentItem.item_id}: ${grade}`);
      if (index + 1 < items.length) {
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
    <main className="min-h-screen bg-surface-deep px-3 py-4 text-text-primary">
      <div className="mx-auto w-full max-w-[390px] space-y-4">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
            <Link href="/grade" className="font-semibold text-accent-brand hover:underline">
              ← Grade home
            </Link>
            <span>Seed {CONTAINERS_DECK.seed}</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Containers blind 20 (363: A)
          </h1>
          <div className="mt-2 flex items-center justify-between text-xs font-semibold">
            <span className="text-accent-brand">
              Set {index + 1} of {items.length} ({currentItem.item_id})
            </span>
            <span className="text-text-secondary">
              {gradedCount}/{items.length} · Keep {counts.Keep} · Fix {counts.Fix} · Drop {counts.Drop}
            </span>
          </div>
          <div className="mt-2.5 grid grid-cols-10 gap-1">
            {items.map((it, i) => {
              const g = grades[it.item_id]?.grade;
              const active = i === index;
              return (
                <button
                  key={it.item_id}
                  type="button"
                  onClick={() => setIndex(i)}
                  className={`rounded py-1 text-[10px] font-bold border ${
                    active
                      ? "border-accent-brand bg-accent-brand text-text-inverse"
                      : g
                      ? "border-surface-border bg-surface-elevated text-accent-brand"
                      : "border-surface-border bg-surface-card text-text-muted"
                  }`}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
        </header>

        {/* Frozen checksum summary when all 20 are graded */}
        {frozenSha && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2">
            <div className="text-xs font-bold uppercase tracking-wide text-accent-live">
              All {items.length} sets graded · Ready to post before key opens
            </div>
            <p className="text-xs text-text-secondary">
              Frozen grades SHA-256 (post on #13544 before Fable opens the sealed key):
            </p>
            <div className="rounded-lg border border-surface-border bg-surface-elevated p-2 font-mono text-[11px] text-text-primary break-all">
              {frozenSha}
            </div>
            <button
              type="button"
              onClick={() => void handleCopySha()}
              className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-semibold text-accent-brand"
            >
              {copiedSha ? "Copied SHA-256" : "Copy SHA-256"}
            </button>
          </section>
        )}

        {/* Grade controls (sticky or placed cleanly right above opened page for quick thumb reach) */}
        <section className="rounded-xl border border-surface-border bg-surface-card p-3.5 space-y-2.5">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>
              Current grade:{" "}
              <strong className="text-text-primary">
                {grades[currentItem.item_id]?.grade || "Not graded yet"}
              </strong>
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={index === 0}
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                className="font-semibold text-accent-brand disabled:opacity-35"
              >
                ← Prev
              </button>
              <button
                type="button"
                disabled={index + 1 >= items.length}
                onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}
                className="font-semibold text-accent-brand disabled:opacity-35"
              >
                Next →
              </button>
            </div>
          </div>

          <input
            type="text"
            value={noteInput}
            onChange={(e) => setNoteInput(e.target.value)}
            maxLength={300}
            placeholder="Note (optional: what to fix or why drop)"
            className="w-full rounded-lg border border-surface-border bg-surface-base px-3 py-2 text-xs text-text-primary placeholder:text-text-muted"
          />

          <div className="grid grid-cols-3 gap-2">
            {(["Keep", "Fix", "Drop"] as const).map((option) => {
              const selected = grades[currentItem.item_id]?.grade === option;
              return (
                <button
                  key={option}
                  type="button"
                  disabled={saving}
                  onClick={() => void submitGrade(option)}
                  className={`rounded-lg border py-2.5 text-sm font-bold disabled:opacity-50 ${
                    selected
                      ? "border-accent-brand bg-accent-brand text-text-inverse"
                      : "border-surface-border bg-surface-elevated text-text-primary hover:border-accent-brand"
                  }`}
                >
                  {option}
                </button>
              );
            })}
          </div>
          {statusMsg && <p className="text-xs font-medium text-accent-live">{statusMsg}</p>}
          {errorMsg && <p className="text-xs font-medium text-accent-danger">{errorMsg}</p>}
        </section>

        {/* Card on top, opened set page underneath */}
        <section className="space-y-3">
          <div className="rounded-xl border border-surface-border bg-surface-card p-2.5">
            <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-text-muted">
              Discover card ({currentItem.item_id})
            </div>
            <img
              src={currentItem.card_image_url}
              alt={`Discover card ${currentItem.item_id}`}
              className="block h-auto w-full rounded-lg border border-surface-border bg-surface-base"
              loading="eager"
            />
          </div>

          <div className="rounded-xl border border-surface-border bg-surface-card p-2.5">
            <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-text-muted">
              Opened set page ({currentItem.item_id})
            </div>
            <img
              src={currentItem.page_image_url}
              alt={`Opened set page ${currentItem.item_id}`}
              className="block h-auto w-full rounded-lg border border-surface-border bg-surface-base"
              loading="eager"
            />
          </div>
        </section>
      </div>
    </main>
  );
}
