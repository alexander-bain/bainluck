"use client";

/**
 * 227-A point 6 — /grade/screens: Alex's eye on ten sampled phone screens a week.
 * Each screen is a 390 px picture of a public page; nothing on the page says
 * which page it is or how it counts, so the counts can't steer the eye. Three
 * buttons: Fun, Fine, Wall of numbers. The first grade per screen stands.
 */

import { useEffect, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { handleGradeDeckReadError, normalizeGraderName, saveWithOneRetry } from "@/lib/ranking/gradeSession";
import {
  SCREEN_GRADES,
  SCREEN_GRADE_LABELS,
  nextScreen,
  screensPath,
  weekFromSearch,
  type ScreenGrade,
  type ScreenWeek,
} from "@/lib/ranking/screenSession";

const GRADER_KEY = "bainluck_grader_name";

export default function ScreensPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });
  return (
    <AdminAuthProvider>
      <ScreensSession />
    </AdminAuthProvider>
  );
}

function ScreensSession() {
  const { secret, clearSecret } = useAdminAuth();
  const [week, setWeek] = useState<string | null | undefined>(undefined);
  const [deck, setDeck] = useState<ScreenWeek | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grader, setGrader] = useState("");
  const [n, setN] = useState(1);
  const [answered, setAnswered] = useState<Set<number>>(new Set());
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setWeek(weekFromSearch(window.location.search));
    try {
      setGrader(localStorage.getItem(GRADER_KEY) || "");
    } catch {
      // storage unavailable: the grader types a name
    }
  }, []);

  useEffect(() => {
    if (week === undefined) return;
    let cancelled = false;
    adminFetchJSON<ScreenWeek>(screensPath(week), secret)
      .then((d) => !cancelled && setDeck(d))
      .catch((e: unknown) => !cancelled && handleGradeDeckReadError(e, "Could not load this week's screens", { clearSecret, setError }));
    return () => {
      cancelled = true;
    };
  }, [week, secret, clearSecret]);

  const grade = async (g: ScreenGrade) => {
    const name = normalizeGraderName(grader);
    if (!deck || !name || saving || answered.has(n)) return;
    setSaving(true);
    setError(null);
    try {
      try {
        localStorage.setItem(GRADER_KEY, name);
      } catch {
        // not remembered; nothing else changes
      }
      const body = JSON.stringify({ week: deck.week, n, grader: name, grade: g });
      const res = await saveWithOneRetry(
        () => adminFetch("/api/admin/ranking/screen-grades", secret, { method: "POST", headers: { "Content-Type": "application/json" }, body }),
        (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      );
      if (!res.ok && res.status !== 409) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      // 409: this screen was graded before; the first grade stands.
      setNote(res.status === 409 ? `Screen ${n} was graded already; the first grade stands.` : `Saved screen ${n}.`);
      const done = new Set(answered).add(n);
      setAnswered(done);
      const next = nextScreen(deck.screens.length, done, n);
      if (next !== null) {
        setN(next);
        window.scrollTo({ top: 0 });
      }
    } catch {
      setError("Not saved: the network dropped. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (error && !deck) return <Shell><p className="text-sm text-text-secondary">{error}</p></Shell>;
  if (!deck) return <Shell><p className="text-sm text-text-muted animate-pulse">Loading this week&apos;s screens…</p></Shell>;

  const total = deck.screens.length;
  const screen = deck.screens.find((s) => s.n === n) ?? deck.screens[0];
  const allDone = answered.size >= total;
  const canGrade = !!normalizeGraderName(grader) && !saving && !answered.has(screen.n);
  return (
    <Shell>
      <h1 className="text-base font-semibold text-text-primary">How does this screen feel?</h1>
      <p className="mt-1 text-sm text-text-secondary">
        Ten phone screens from this week. Grade each one on how it feels to look at, not on what it says.
      </p>
      <label className="mt-3 block text-sm text-text-primary">
        Your name
        <input
          value={grader}
          onChange={(e) => setGrader(e.target.value)}
          className="mt-1 w-full max-w-sm rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary"
        />
      </label>
      <p className="mt-3 text-sm font-semibold text-text-primary" aria-live="polite">
        Screen {screen.n} of {total}
      </p>
      <div className="mt-2 w-[390px] max-w-full overflow-hidden rounded-xl border border-surface-border bg-surface-card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={screen.image} alt={`Screen ${screen.n}`} width={390} className="block h-auto w-full" />
      </div>
      <div className="sticky bottom-16 mt-3 grid w-[390px] max-w-full grid-cols-3 gap-2">
        {SCREEN_GRADES.map((g) => (
          <button
            key={g}
            type="button"
            disabled={!canGrade}
            onClick={() => grade(g)}
            className="rounded-xl border border-surface-border bg-surface-card px-2 py-3 text-sm font-semibold text-text-primary disabled:text-text-muted"
          >
            {SCREEN_GRADE_LABELS[g]}
          </button>
        ))}
      </div>
      {note && <p className="mt-2 text-sm text-text-secondary" role="status">{note}</p>}
      {error && <p className="mt-2 text-sm text-text-secondary">{error}</p>}
      {allDone && <p className="mt-2 text-sm font-semibold text-text-primary">All {total} screens graded. Thank you.</p>}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-deep px-3 py-4">
      <div className="mx-auto max-w-[820px]">{children}</div>
    </div>
  );
}
