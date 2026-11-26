"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * #13102 (Decision 385: A) — /grade/scout: 390px blind morning deck of nightly scout sets
 * mixed 1:1 with live public sets. Origin and slugs are kept sealed in server-side Redis only.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  canonicalContainerGradesString,
  computeSha256Hex,
  type ContainerGrade,
  type ContainerGradeEntry,
} from "@/lib/ranking/blindDeckGrade363a";
import {
  parseScoutDeckSearchParams,
  SCOUT_DECK_DEFAULT_SURFACE,
  SCOUT_DECK_ITEM_TYPE,
  type ScoutMorningDeckResponse,
} from "@/lib/ranking/scoutMorningDeck13102";

interface SavedScoutJudgmentRow {
  market_name?: string;
  label?: string;
  notes?: string | null;
  created_at?: string;
  label_metadata?: {
    deck_date?: string;
    item_id?: string;
    grade?: ContainerGrade;
    note?: string;
    timestamp?: string;
  };
}

function formatPct(prob: number | null): string {
  if (prob === null || Number.isNaN(prob)) return "—";
  return `${Math.round(prob * 100)}%`;
}

function formatDeltaPts(delta: number | null): string | null {
  if (delta === null || Number.isNaN(delta)) return null;
  const pts = Math.round(delta * 100);
  if (pts === 0) return null;
  return pts > 0 ? `+${pts} pts` : `${pts} pts`;
}

export default function GradeScoutMorningDeckPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <ScoutDeckSession />
    </AdminAuthProvider>
  );
}

function ScoutDeckSession() {
  const { secret, clearSecret } = useAdminAuth();
  const [paramsInfo, setParamsInfo] = useState<{
    deckDate: string | null;
    activeSurface: string;
  } | null>(null);
  const [deck, setDeck] = useState<ScoutMorningDeckResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [grades, setGrades] = useState<Record<string, ContainerGradeEntry>>({});
  const [noteInput, setNoteInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [frozenSha, setFrozenSha] = useState<string | null>(null);
  const [copiedSha, setCopiedSha] = useState(false);

  useEffect(() => {
    setParamsInfo(parseScoutDeckSearchParams(window.location.search));
  }, []);

  useEffect(() => {
    if (!secret || !paramsInfo) return;
    let cancelled = false;
    setLoading(true);
    setErrorMsg(null);
    const path = paramsInfo.deckDate
      ? `/api/admin/ranking/scout-deck?date=${encodeURIComponent(paramsInfo.deckDate)}`
      : "/api/admin/ranking/scout-deck";

    adminFetchJSON<ScoutMorningDeckResponse>(path, secret)
      .then((res) => {
        if (cancelled) return;
        setDeck(res);
        setIndex(0);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to load morning scout deck";
        if (msg.includes("401") || msg.includes("403")) {
          clearSecret({ rejected: true });
          return;
        }
        setErrorMsg(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [secret, paramsInfo, clearSecret]);

  const draftStorageKey = useMemo(() => {
    if (!deck || !paramsInfo) return null;
    return `bainluck_385a_scout_${paramsInfo.activeSurface}_${deck.deck_date}`;
  }, [deck, paramsInfo]);

  useEffect(() => {
    if (!draftStorageKey) return;
    try {
      const raw = localStorage.getItem(draftStorageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as Record<string, ContainerGradeEntry>;
        if (parsed && typeof parsed === "object") {
          setGrades(parsed);
        }
      }
    } catch {
      // storage unavailable
    }
  }, [draftStorageKey]);

  useEffect(() => {
    if (!secret || !deck || !paramsInfo) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await adminFetchJSON<{ judgments?: SavedScoutJudgmentRow[] }>(
          `/api/admin/ranking-judgments?surface=${encodeURIComponent(paramsInfo.activeSurface)}&limit=100`,
          secret,
        );
        if (cancelled) return;
        const restored: Record<string, ContainerGradeEntry> = {};
        for (const row of res.judgments || []) {
          const rowDate = row.label_metadata?.deck_date;
          if (rowDate && rowDate !== deck.deck_date) continue;
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
  }, [secret, deck, paramsInfo]);

  useEffect(() => {
    if (!draftStorageKey) return;
    try {
      localStorage.setItem(draftStorageKey, JSON.stringify(grades));
    } catch {
      // ignore
    }
  }, [draftStorageKey, grades]);

  const items = useMemo(() => deck?.items ?? [], [deck]);
  const currentCard = items[index] ?? null;

  useEffect(() => {
    if (!currentCard) return;
    setNoteInput(grades[currentCard.item_id]?.note || "");
    setStatusMsg(null);
  }, [index, currentCard, grades]);

  const gradedCount = useMemo(
    () => items.filter((it) => Boolean(grades[it.item_id])).length,
    [items, grades],
  );

  const counts = useMemo(() => {
    const c = { Keep: 0, Fix: 0, Drop: 0 };
    for (const it of items) {
      const g = grades[it.item_id]?.grade;
      if (g) c[g] += 1;
    }
    return c;
  }, [items, grades]);

  useEffect(() => {
    if (items.length > 0 && gradedCount === items.length) {
      let cancelled = false;
      const deckKeyId = `${paramsInfo?.activeSurface ?? SCOUT_DECK_DEFAULT_SURFACE}:${deck?.deck_date ?? "unknown"}`;
      const canonical = canonicalContainerGradesString(deckKeyId, grades);
      void computeSha256Hex(canonical).then((hex) => {
        if (!cancelled) setFrozenSha(hex);
      });
      return () => {
        cancelled = true;
      };
    }
    setFrozenSha(null);
  }, [gradedCount, items, grades, deck, paramsInfo]);

  const submitGrade = async (grade: ContainerGrade) => {
    if (!currentCard || !deck || !paramsInfo || saving) return;
    setSaving(true);
    setErrorMsg(null);
    setStatusMsg(null);
    const trimmedNote = noteInput.trim();
    const ts = new Date().toISOString();

    try {
      const res = await adminFetch("/api/admin/ranking-judgments", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          surface: paramsInfo.activeSurface,
          item_type: SCOUT_DECK_ITEM_TYPE,
          market_name: currentCard.item_id,
          label: grade,
          notes: trimmedNote || null,
          reviewer: "admin",
          category_at_review: currentCard.category,
          headline_at_review: currentCard.title,
          label_metadata: {
            deck_date: deck.deck_date,
            item_id: currentCard.item_id,
            grade,
            note: trimmedNote,
            timestamp: ts,
            sealed_key_sha256: deck.sealed_key_sha256,
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
      setGrades((prev) => ({
        ...prev,
        [currentCard.item_id]: { grade, note: trimmedNote, updated_at: ts },
      }));
      setStatusMsg(`Saved ${currentCard.item_id}: ${grade}`);
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
            <span>{deck ? deck.deck_date : "Morning Scout"}</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Scout Morning Deck (385: A)
          </h1>
          {deck && items.length > 0 && (
            <>
              <div className="mt-2 flex items-center justify-between text-xs font-semibold">
                <span className="text-accent-brand">
                  Card {index + 1} of {items.length} ({currentCard?.item_id})
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
                      className={`rounded border py-1 text-[10px] font-bold ${
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
            </>
          )}
        </header>

        {loading && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-muted">
            Loading morning blind deck…
          </section>
        )}

        {!loading && errorMsg && items.length === 0 && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-accent-danger">
            {errorMsg}
          </section>
        )}

        {!loading && !errorMsg && deck && items.length === 0 && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
            <h2 className="text-sm font-bold text-text-primary">No staged sets waiting yet</h2>
            <p className="text-xs text-text-secondary">
              {deck.message || "The nightly scout has not staged sets for this date yet."}
            </p>
          </section>
        )}

        {frozenSha && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2">
            <div className="text-xs font-bold uppercase tracking-wide text-accent-live">
              All {items.length} cards graded · Ready for Key Check
            </div>
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

        {currentCard && (
          <>
            <section className="rounded-xl border border-surface-border bg-surface-card p-3.5 space-y-2.5">
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>
                  Current grade:{" "}
                  <strong className="text-text-primary">
                    {grades[currentCard.item_id]?.grade || "Not graded yet"}
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
                  const selected = grades[currentCard.item_id]?.grade === option;
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

            {/* Reader-facing Discover set preview */}
            <article className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3">
              <div className="flex items-center justify-between gap-2 text-[11px] font-bold uppercase tracking-wide">
                <span className="text-accent-brand">{currentCard.kicker}</span>
                <span className="rounded border border-surface-border bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
                  {currentCard.category} · {currentCard.look}
                </span>
              </div>
              <h2 className="text-base font-bold leading-snug text-text-primary">
                {currentCard.title}
              </h2>
              {currentCard.summary && (
                <p className="text-xs leading-relaxed text-text-secondary">
                  {currentCard.summary}
                </p>
              )}

              {/* Compact card bars preview (top 3 members) */}
              <div className="space-y-1.5 rounded-lg border border-surface-border bg-surface-elevated p-2.5">
                {currentCard.members.slice(0, 3).map((m, idx) => (
                  <div key={`${m.title}-${idx}`} className="flex items-center justify-between gap-2 text-xs">
                    <div className="flex min-w-0 items-center gap-2">
                      {m.image_url && (
                        <img
                          src={m.image_url}
                          alt=""
                          className="h-5 w-5 shrink-0 rounded-full object-cover"
                        />
                      )}
                      <span className="truncate font-medium text-text-primary">{m.title}</span>
                    </div>
                    <span className="shrink-0 font-bold text-accent-brand">
                      {formatPct(m.probability)}
                    </span>
                  </div>
                ))}
              </div>

              {/* Full opened set member rows */}
              <div className="border-t border-surface-border pt-2">
                <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-text-muted">
                  Opened set · {currentCard.member_count} markets
                </div>
                <ul className="divide-y divide-surface-border/70">
                  {currentCard.members.map((member, idx) => {
                    const deltaLabel = formatDeltaPts(member.change_24h);
                    return (
                      <li key={`${member.title}-row-${idx}`} className="py-2 space-y-0.5">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-xs font-semibold leading-snug text-text-primary">
                            {member.title}
                          </span>
                          <span className="shrink-0 text-xs font-bold text-accent-brand">
                            {formatPct(member.probability)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-text-secondary">
                          <span>{member.leading_outcome}</span>
                          {deltaLabel && <span>{deltaLabel} 24h</span>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </article>
          </>
        )}
      </div>
    </main>
  );
}
