"use client";

/**
 * #11937 (171-A) — /grade/pair?slate=<id>&pair=<name>: the blind side-by-side.
 * Two first tens for one slate, drawn as Discover draws them, side by side at
 * phone width. The server picks which side is which and never says; the grader
 * answers left, right or no difference, saved per slate and pair.
 */

import { useEffect, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import DiscoverCard from "@/components/DiscoverCard";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import { handleGradeDeckReadError, normalizeGraderName, saveWithOneRetry } from "@/lib/ranking/gradeSession";
import {
  PAIR_CHOICES,
  PAIR_CHOICE_LABELS,
  pairFromSearch,
  gradeDeckHref,
  pairPath,
  type PairChoice,
  type PairDeck,
  type PairSide,
} from "@/lib/ranking/pairSession";

const GRADER_KEY = "bainluck_grader_name";

export default function PairPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });
  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);
  return (
    <AdminAuthProvider>
      <PairSession />
    </AdminAuthProvider>
  );
}

function Column({ side, label }: { side: PairSide[]; label: string }) {
  // Cards are drawn at Discover's own phone width (390 px), never scaled, so
  // both tens read exactly as Discover draws them.
  return (
    <section aria-label={label} className="w-[390px] max-w-full shrink-0">
      <div className="pointer-events-none select-none">
        {side.map((s, i) => (
          <div key={i} className="mb-3">
            <DiscoverCard groupedItem={{ type: "single", item: s.card }} positionIndex={i} />
          </div>
        ))}
      </div>
    </section>
  );
}

function PairSession() {
  const { secret, clearSecret } = useAdminAuth();
  const [ref, setRef] = useState<{ slate: string; pair: string } | null | undefined>(undefined);
  const [deck, setDeck] = useState<PairDeck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grader, setGrader] = useState("");
  const [saved, setSaved] = useState<PairChoice | null>(null);
  const [saving, setSaving] = useState(false);
  // Amendment 2: asked before the columns, stored with the pick.
  const [opened, setOpened] = useState<boolean | null>(null);
  // On a phone the two tens take turns at full size; both must be opened once.
  const [tab, setTab] = useState<"left" | "right">("left");
  const [seenRight, setSeenRight] = useState(false);

  useEffect(() => {
    setRef(pairFromSearch(window.location.search));
    try {
      setGrader(localStorage.getItem(GRADER_KEY) || "");
    } catch {
      // storage unavailable: the grader types a name
    }
  }, []);

  useEffect(() => {
    if (!ref) return;
    let cancelled = false;
    adminFetchJSON<PairDeck>(pairPath(ref.slate, ref.pair), secret)
      .then((d) => !cancelled && setDeck(d))
      .catch((e: unknown) => !cancelled && handleGradeDeckReadError(e, "Could not load the two first tens", { clearSecret, setError }));
    return () => {
      cancelled = true;
    };
  }, [ref, secret, clearSecret]);

  const pick = async (choice: PairChoice) => {
    const name = normalizeGraderName(grader);
    if (!deck || !name || saving || opened === null || saved) return;
    setSaving(true);
    setError(null);
    try {
      try {
        localStorage.setItem(GRADER_KEY, name);
      } catch {
        // not remembered; nothing else changes
      }
      const body = JSON.stringify({
        slate_id: deck.slate_id,
        pair: deck.pair,
        grader: name,
        choice,
        opened_discover_today: opened === true,
      });
      const res = await saveWithOneRetry(
        () => adminFetch("/api/admin/ranking/pair-picks", secret, { method: "POST", headers: { "Content-Type": "application/json" }, body }),
        (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      );
      if (res.status === 409) {
        setError("Already picked for this morning. The first pick stands.");
        setSaved(choice);
        return;
      }
      if (!res.ok) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      setSaved(choice);
    } catch {
      setError("Not saved: the network dropped. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (ref === null) {
    return <Shell><p className="text-sm text-text-secondary">This link needs ?slate= and ?pair=.</p></Shell>;
  }
  if (error && !deck) return <Shell><p className="text-sm text-text-secondary">{error}</p></Shell>;
  if (!deck) return <Shell><p className="text-sm text-text-muted animate-pulse">Loading the two first tens…</p></Shell>;

  const canPick = !!normalizeGraderName(grader) && opened !== null && !saved && !saving;
  return (
    <Shell>
      <h1 className="text-base font-semibold text-text-primary">Which first ten would you rather open Discover to?</h1>
      <p className="mt-1 text-sm text-text-secondary">
        Two orders of the same morning&apos;s cards. Pick before grading today&apos;s deck.
      </p>
      {!normalizeGraderName(grader) && (
        <input
          className="mt-3 w-full max-w-sm rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary"
          placeholder="Your name"
          value={grader}
          maxLength={40}
          onChange={(e) => setGrader(e.target.value)}
        />
      )}
      <fieldset className="mt-3 text-sm text-text-primary">
        <legend className="font-semibold">Have you already opened Discover today?</legend>
        <div className="mt-1 flex gap-4">
          {[["yes", true], ["no", false]].map(([label, value]) => (
            <label key={String(label)} className="flex items-center gap-2">
              <input type="radio" name="opened" checked={opened === value} onChange={() => setOpened(value as boolean)} />
              {label === "yes" ? "Yes" : "No"}
            </label>
          ))}
        </div>
      </fieldset>

      {/* Phone: the two tens take turns at full size. */}
      <div className="mt-3 flex gap-2 md:hidden" role="tablist">
        {(["left", "right"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-semibold ${tab === t ? "border-accent-brand text-text-primary" : "border-surface-border text-text-secondary"}`}
            onClick={() => {
              setTab(t);
              if (t === "right") setSeenRight(true);
            }}
          >
            {t === "left" ? "Left ten" : "Right ten"}
          </button>
        ))}
      </div>
      <div className="mt-3 md:hidden">
        <Column side={tab === "left" ? deck.left : deck.right} label={tab === "left" ? "Left ten" : "Right ten"} />
      </div>

      {/* Wide screen: both tens side by side, full size. */}
      <div className="mt-3 hidden gap-6 md:flex">
        <Column side={deck.left} label="Left ten" />
        <Column side={deck.right} label="Right ten" />
      </div>

      {/* Above the phone tab bar (57 px, painted over the page at z-50, #7848);
          at the bottom of the window on a wide screen. */}
      <div className="sticky bottom-[64px] z-40 mt-3 grid max-w-[804px] grid-cols-3 gap-2 bg-surface-deep py-2 md:bottom-0">
        {PAIR_CHOICES.map((c) => (
          <button
            key={c}
            className="rounded-lg border border-surface-border bg-surface-elevated px-2 py-3 text-sm font-semibold text-text-primary disabled:opacity-50"
            disabled={!canPick || (!seenRight && isPhone())}
            onClick={() => void pick(c)}
          >
            {PAIR_CHOICE_LABELS[c]}
          </button>
        ))}
      </div>
      {!seenRight && <p className="text-xs text-text-muted md:hidden">Open both tens before picking.</p>}
      {saved && (
        <p className="mt-1 text-sm text-text-secondary" role="status">
          Saved: {PAIR_CHOICE_LABELS[saved]}.{" "}
          <a className="font-semibold text-accent-brand hover:underline" href={gradeDeckHref(deck.slate_id)}>
            Now grade this morning&apos;s deck →
          </a>
        </p>
      )}
      {error && <p className="mt-1 text-sm text-text-secondary">{error}</p>}
    </Shell>
  );
}

function isPhone(): boolean {
  return typeof window !== "undefined" && !window.matchMedia("(min-width: 768px)").matches;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-deep px-3 py-4">
      <div className="mx-auto max-w-[820px]">{children}</div>
    </div>
  );
}
