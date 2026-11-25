"use client";

/**
 * #13544 / #13553 (Split Part A) — /grade/sets-v2: 390px blind 40-set grader (Deck 2).
 * Draws 40 anonymized candidate sets (`blind-01`..`blind-40`) one at a time,
 * hiding provider source fields so "kalshi" / "polymarket" never appear on cards.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import setsV2DeckRaw from "@/data/fun_scout_blind_40_deck_v2_2026_11_23.json";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  canonicalContainerGradesString,
  computeSha256Hex,
  type ContainerGrade,
  type ContainerGradeEntry,
} from "@/lib/ranking/blindDeckGrade363a";

interface BlindSetMemberV2 {
  market_id: number;
  title: string;
}

interface BlindSetCardV2 {
  card_id: string;
  title: string;
  kicker: string;
  category: string;
  summary: string;
  look: string;
  grade_options: readonly ContainerGrade[];
  members: BlindSetMemberV2[];
}

interface BlindSetsV2Deck {
  deck_id: string;
  created_at: string;
  seed: number;
  card_count: number;
  grade_options: readonly ContainerGrade[];
  blind: boolean;
  sealed_checksum_sha256: string;
  cards: BlindSetCardV2[];
}

interface SavedSetJudgmentRow {
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

const SETS_V2_DECK = setsV2DeckRaw as unknown as BlindSetsV2Deck;
const SETS_V2_DRAFT_SLOT = "sets-v2-draft";

export default function GradeSetsV2DeckPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <SetsV2DeckSession />
    </AdminAuthProvider>
  );
}

function SetsV2DeckSession() {
  const { secret, clearSecret } = useAdminAuth();
  const cards = SETS_V2_DECK.cards;

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
      const raw = localStorage.getItem(SETS_V2_DRAFT_SLOT);
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
        const res = await adminFetchJSON<{ judgments?: SavedSetJudgmentRow[] }>(
          "/api/admin/ranking-judgments?surface=grade_sets_v2_deck&limit=100",
          secret,
        );
        if (cancelled) return;
        const restored: Record<string, ContainerGradeEntry> = {};
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

  const currentCard = cards[index] ?? cards[0];

  useEffect(() => {
    if (!currentCard) return;
    setNoteInput(grades[currentCard.card_id]?.note || "");
    setStatusMsg(null);
    setErrorMsg(null);
  }, [currentCard, grades]);

  useEffect(() => {
    try {
      localStorage.setItem(SETS_V2_DRAFT_SLOT, JSON.stringify(grades));
    } catch {
      // ignore
    }
    const gradedCountNow = cards.filter((c) => Boolean(grades[c.card_id])).length;
    if (gradedCountNow === cards.length && cards.length > 0) {
      const canonical = canonicalContainerGradesString(SETS_V2_DECK.deck_id, grades);
      void computeSha256Hex(canonical).then((hex) => setFrozenSha(hex));
    } else {
      setFrozenSha(null);
    }
  }, [grades, cards]);

  const counts = useMemo(() => {
    const out: Record<ContainerGrade, number> = { Keep: 0, Fix: 0, Drop: 0 };
    for (const c of cards) {
      const entry = grades[c.card_id];
      if (entry) out[entry.grade] += 1;
    }
    return out;
  }, [grades, cards]);

  const gradedCount = counts.Keep + counts.Fix + counts.Drop;

  const submitGrade = async (grade: ContainerGrade) => {
    if (!currentCard || saving) return;
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
          surface: "grade_sets_v2_deck",
          item_type: "sets_blind_40_v2",
          market_name: currentCard.card_id,
          label: grade,
          notes: trimmedNote || null,
          reviewer: "alex",
          label_metadata: {
            deck_id: SETS_V2_DECK.deck_id,
            seed: SETS_V2_DECK.seed,
            item_id: currentCard.card_id,
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
        [currentCard.card_id]: { grade, note: trimmedNote, updated_at: ts },
      };
      setGrades(nextGrades);
      setStatusMsg(`Saved ${currentCard.card_id}: ${grade}`);
      if (index + 1 < cards.length) {
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
            <span>Seed {SETS_V2_DECK.seed}</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Sets blind 40 v2 (#13544)
          </h1>
          <div className="mt-2 flex items-center justify-between text-xs font-semibold">
            <span className="text-accent-brand">
              Set {index + 1} of {cards.length} ({currentCard.card_id})
            </span>
            <span className="text-text-secondary">
              {gradedCount}/{cards.length} · Keep {counts.Keep} · Fix {counts.Fix} · Drop {counts.Drop}
            </span>
          </div>
          <div className="mt-2.5 grid grid-cols-10 gap-1">
            {cards.map((c, i) => {
              const g = grades[c.card_id]?.grade;
              const active = i === index;
              return (
                <button
                  key={c.card_id}
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

        {frozenSha && (
          <section className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2">
            <div className="text-xs font-bold uppercase tracking-wide text-accent-live">
              All {cards.length} sets graded · Ready to freeze before key opens
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

        <section className="rounded-xl border border-surface-border bg-surface-card p-3.5 space-y-2.5">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>
              Current grade:{" "}
              <strong className="text-text-primary">
                {grades[currentCard.card_id]?.grade || "Not graded yet"}
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
                disabled={index + 1 >= cards.length}
                onClick={() => setIndex((i) => Math.min(cards.length - 1, i + 1))}
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
              const selected = grades[currentCard.card_id]?.grade === option;
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

        <article className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 text-[11px] font-bold uppercase tracking-wide">
            <span className="text-accent-brand">{currentCard.kicker}</span>
            <span className="rounded border border-surface-border bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
              {currentCard.look}
            </span>
          </div>
          <h2 className="text-base font-bold leading-snug text-text-primary">
            {currentCard.title}
          </h2>
          <p className="text-xs leading-relaxed text-text-secondary">
            {currentCard.summary}
          </p>
          <ul className="divide-y divide-surface-border/70 border-t border-surface-border pt-2">
            {currentCard.members.map((member) => (
              <li
                key={member.market_id}
                className="py-2 text-xs font-medium leading-snug text-text-primary"
              >
                {member.title}
              </li>
            ))}
          </ul>
        </article>
      </div>
    </main>
  );
}
