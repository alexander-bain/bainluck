"use client";

/**
 * #12095 Phase 2 (Decide 37-B) — /grade: the family grades the latest captured
 * Discover opening ten, one real card at a time.
 *
 * Behind the existing admin auth (the signed-in admin account, or the admin
 * token). The grader types a name once; "kid" marks their grades non-expert,
 * which keeps them out of the founder score. Each grade is one
 * `POST /api/admin/ranking/grades` into `ranking_grades`;
 * `tools/ranking/grades.py export` copies them to `evals/ranking/grades/`, the
 * store the scorecard reads. The card is drawn from the payload the slate
 * stored, inert (no taps, no swipes, no interaction events).
 */

import { useCallback, useEffect, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import DiscoverCard from "@/components/DiscoverCard";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import {
  GRADES,
  GRADE_LABELS,
  formatTally,
  normalizeGraderName,
  type Grade,
  type GradeDeck,
  type TallyEntry,
} from "@/lib/ranking/gradeSession";

const GRADER_KEY = "bainluck_grader_name";
const KID_KEY = "bainluck_grader_kid";

export default function GradePage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });
  return (
    <AdminAuthProvider>
      <GradeSession />
    </AdminAuthProvider>
  );
}

function GradeSession() {
  const { secret } = useAdminAuth();
  const [deck, setDeck] = useState<GradeDeck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [kid, setKid] = useState(false);
  const [grader, setGrader] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const [graded, setGraded] = useState(0);
  const [saving, setSaving] = useState(false);
  const [tally, setTally] = useState<TallyEntry[]>([]);

  useEffect(() => {
    try {
      setNameInput(localStorage.getItem(GRADER_KEY) || "");
      setKid(localStorage.getItem(KID_KEY) === "1");
    } catch {
      // storage unavailable: the grader just types their name
    }
  }, []);

  const loadTally = useCallback(
    async (slateId: string) => {
      try {
        const res = await adminFetchJSON<{ tally: TallyEntry[] }>(
          `/api/admin/ranking/grades?slate_id=${encodeURIComponent(slateId)}&days=2`,
          secret,
        );
        setTally(res.tally);
      } catch {
        // the tally is a nicety; grading goes on without it
      }
    },
    [secret],
  );

  useEffect(() => {
    let cancelled = false;
    adminFetchJSON<GradeDeck>("/api/admin/ranking/grade-deck", secret)
      .then((d) => {
        if (cancelled) return;
        setDeck(d);
        void loadTally(d.slate_id);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load the cards");
      });
    return () => {
      cancelled = true;
    };
  }, [secret, loadTally]);

  const start = () => {
    const name = normalizeGraderName(nameInput);
    if (!name) return;
    try {
      localStorage.setItem(GRADER_KEY, name);
      localStorage.setItem(KID_KEY, kid ? "1" : "0");
    } catch {
      // not remembered next time; nothing else changes
    }
    setGrader(name);
    setIndex(0);
    setGraded(0);
  };

  const submit = async (grade: Grade) => {
    if (!deck || !grader || saving) return;
    const item = deck.items[index];
    setSaving(true);
    setError(null);
    try {
      const res = await adminFetch("/api/admin/ranking/grades", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slate_id: deck.slate_id,
          surface: deck.surface,
          grader,
          kid,
          position: item.position,
          item_key: item.item_key,
          grade,
          note: note.trim() || null,
        }),
      });
      if (!res.ok) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      setGraded((n) => n + 1);
      setNote("");
      setIndex((i) => i + 1);
      void loadTally(deck.slate_id);
    } catch {
      setError("Not saved: the network dropped. Try that card again.");
    } finally {
      setSaving(false);
    }
  };

  const tallyLine = formatTally(tally);

  if (error && !deck) {
    return <Shell><p className="text-sm text-text-secondary">{error}</p></Shell>;
  }
  if (!deck) {
    return <Shell><p className="text-sm text-text-muted animate-pulse">Loading the cards…</p></Shell>;
  }

  if (!grader) {
    return (
      <Shell tally={tallyLine}>
        <h1 className="text-xl font-semibold text-text-primary">Who&apos;s grading?</h1>
        <p className="mt-1 text-sm text-text-secondary">
          The top {deck.items.length} Discover cards from {deck.captured_at ? new Date(deck.captured_at).toLocaleString() : "the latest capture"}.
        </p>
        <input
          className="mt-4 w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-text-primary"
          placeholder="Your name"
          value={nameInput}
          maxLength={40}
          onChange={(e) => setNameInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") start();
          }}
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-text-secondary">
          <input type="checkbox" checked={kid} onChange={(e) => setKid(e.target.checked)} />
          Kid
        </label>
        <button
          className="mt-4 w-full rounded-lg bg-accent-brand px-4 py-2 font-semibold text-text-inverse disabled:opacity-50"
          disabled={!normalizeGraderName(nameInput)}
          onClick={start}
        >
          Start
        </button>
      </Shell>
    );
  }

  if (index >= deck.items.length) {
    return (
      <Shell tally={tallyLine}>
        <h1 className="text-xl font-semibold text-text-primary">All {deck.items.length} graded. Thanks, {grader}!</h1>
        <button className="mt-4 text-sm font-semibold text-accent-brand hover:underline" onClick={() => setGrader(null)}>
          Next grader
        </button>
      </Shell>
    );
  }

  const item = deck.items[index];
  return (
    <Shell tally={tallyLine}>
      <div className="flex items-baseline justify-between text-sm text-text-secondary">
        <span>
          {grader}
          {kid ? " (kid)" : ""} · card {index + 1} of {deck.items.length}
        </span>
        <span>{graded} graded</span>
      </div>
      <div className="mt-3 pointer-events-none select-none" aria-label={`Card ${item.position}`}>
        {item.card ? (
          <DiscoverCard groupedItem={{ type: "single", item: item.card }} positionIndex={item.position - 1} />
        ) : (
          <div className="rounded-xl border border-surface-border bg-surface-card p-4">
            <div className="font-semibold text-text-primary">{item.title || item.item_key}</div>
            {item.probability != null && (
              <div className="mt-1 text-2xl font-bold text-text-primary">{Math.round(item.probability * 100)}%</div>
            )}
          </div>
        )}
      </div>
      <input
        className="mt-4 w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary"
        placeholder="Note (optional)"
        value={note}
        maxLength={300}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="mt-3 grid grid-cols-3 gap-2">
        {GRADES.map((g) => (
          <button
            key={g}
            className="rounded-lg border border-surface-border bg-surface-elevated px-2 py-3 font-semibold text-text-primary disabled:opacity-50"
            disabled={saving}
            onClick={() => void submit(g)}
          >
            {GRADE_LABELS[g]}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-text-secondary">{error}</p>}
    </Shell>
  );
}

function Shell({ children, tally }: { children: React.ReactNode; tally?: string }) {
  return (
    <div className="min-h-screen bg-surface-deep px-4 py-6">
      <div className="mx-auto max-w-md">
        {children}
        {tally && <p className="mt-6 text-center text-sm text-text-muted">{tally}</p>}
      </div>
    </div>
  );
}
