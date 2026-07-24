"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";
import { trackEvent } from "@/lib/analytics";
import {
  INITIAL_SESSION,
  isReversible,
  keyToAction,
  navigate,
  progressLabel,
  recordVerdict,
  reconcileVerdict,
  rollbackVerdict,
  sessionTotals,
  undoLast,
  type Verdict,
} from "@/lib/teamClusterSession";

interface Member {
  id: number;
  name: string;
  slug: string;
  recent_events: number;
  total_events: number;
  mappings: number;
}
interface Recommendation {
  action: Verdict;
  canonical_id: number;
  fold_ids: number[];
  reason: string;
}
interface Cluster {
  cluster_key: string;
  sport_key: string | null;
  espn_id: string | null;
  status: string;
  reason: string;
  members: Member[];
  member_ids: number[];
  recommended: Recommendation;
}

const VERDICT_LABEL: Record<Verdict, string> = {
  merge: "Merge",
  keep_separate: "Keep separate",
  defer: "Defer",
};

export default function TeamClustersPage() {
  usePageTracking({ pageType: "admin_team_clusters" });
  useScrollDepth({ pageType: "admin_team_clusters" });
  useEngagementTime({ pageType: "admin_team_clusters" });

  const { secret } = useAdminAuth();

  const { data, error } = useSWR(
    secret ? ["team-clusters-pending", secret] : null,
    () => adminFetchJSON("/api/admin/team-clusters/pending", secret)
  );

  const [session, setSession] = useState(INITIAL_SESSION);
  // Chosen canonical per cluster (defaults to the recommendation). Keyed by
  // cluster_key so it survives arrow navigation.
  const [canonicalPick, setCanonicalPick] = useState<Record<string, number>>({});
  const uidRef = useRef(0);

  const items = ((data as Record<string, unknown[]>)?.items as unknown as Cluster[]) || [];
  const total = items.length;
  const current = (items[session.index] as Cluster | undefined) || null;
  const totals = sessionTotals(session);

  const selectedCanonical = current
    ? canonicalPick[current.cluster_key] ?? current.recommended.canonical_id
    : null;

  const handleVerdict = useCallback(
    (verdict: Verdict) => {
      if (!current || !secret) return;
      const clusterKey = current.cluster_key;
      // Arrow-nav can land back on an already-decided cluster — never double-record.
      if (session.history.some((h) => h.clusterKey === clusterKey)) return;

      const canonicalId = canonicalPick[clusterKey] ?? current.recommended.canonical_id;
      const foldIds =
        verdict === "merge" ? current.member_ids.filter((id) => id !== canonicalId) : [];

      const uid = ++uidRef.current;
      // Optimistic advance: the next cluster slides in immediately.
      setSession((s) =>
        recordVerdict(s, {
          uid,
          clusterKey,
          verdict,
          reversible: isReversible(verdict),
          pending: true,
        })
      );

      (async () => {
        try {
          await adminFetchJSON("/api/admin/team-clusters/verdict", secret, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              cluster_key: clusterKey,
              verdict,
              sport_key: current.sport_key,
              canonical_id: verdict === "merge" ? canonicalId : null,
              fold_ids: foldIds,
              member_ids: current.member_ids,
              reason: current.recommended.reason,
            }),
          });
          trackEvent("team_cluster_verdict", {
            verdict,
            cluster_key: clusterKey,
            sport: current.sport_key || undefined,
            status: current.status,
            followed_recommendation: verdict === current.recommended.action,
            surface: "team_clusters",
          });
          setSession((s) => reconcileVerdict(s, uid));
        } catch (e) {
          console.error(e);
          setSession((s) => rollbackVerdict(s, uid));
        }
      })();
    },
    [current, secret, session.history, canonicalPick]
  );

  const handleUndo = useCallback(() => {
    const { state: next, undone } = undoLast(session);
    if (!undone) return;
    setSession(next);
    if (secret) {
      (async () => {
        try {
          await adminFetchJSON("/api/admin/team-clusters/undo", secret, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cluster_key: undone.clusterKey }),
          });
        } catch (e) {
          console.error(e);
        }
      })();
    }
  }, [session, secret]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      // Number keys pick the canonical among the current cluster's members.
      if (current && /^[1-9]$/.test(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        const m = current.members[idx];
        if (m) setCanonicalPick((p) => ({ ...p, [current.cluster_key]: m.id }));
        return;
      }
      const action = keyToAction(e.key);
      if (!action) return;
      if (action === "merge" || action === "keep_separate" || action === "defer") {
        handleVerdict(action);
      } else if (action === "undo") {
        handleUndo();
      } else if (action === "next" || action === "prev") {
        setSession((s) => navigate(s, action, total));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleVerdict, handleUndo, total, current]);

  if (!secret)
    return <div className="p-8 text-text-muted">Enter admin secret to adjudicate team clusters.</div>;
  if (error) return <div className="p-8 text-accent-danger">Error loading clusters.</div>;
  if (!data) return <div className="p-8 text-text-muted">Loading…</div>;

  if (!current) {
    return (
      <div className="max-w-3xl mx-auto p-8">
        <h1 className="text-2xl font-bold mb-4">Team cluster adjudication complete</h1>
        <p className="text-text-secondary">{progressLabel(session, total)}.</p>
        {session.history.length > 0 && (
          <button
            onClick={handleUndo}
            className="mt-3 text-xs text-text-muted hover:text-text-primary"
          >
            Undo last (u)
          </button>
        )}
      </div>
    );
  }

  const rec = current.recommended;

  return (
    <div className="max-w-3xl mx-auto p-8">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">Team cluster adjudication</h1>
        <span className="text-sm text-text-muted font-mono">
          {session.index + 1} / {total}
        </span>
      </div>

      <div className="text-sm text-text-secondary font-mono mb-2" data-testid="progress-strip">
        {progressLabel(session, total)}
      </div>

      <p className="text-xs text-text-muted mb-3 leading-relaxed">
        #247&apos;s merge auto-folded the clean stubs and skipped these ambiguous clusters.
        Pick the canonical row (click or press its number), then <strong>Merge</strong> to fold the
        rest into it, <strong>Keep separate</strong> if they are genuinely distinct teams, or{" "}
        <strong>Defer</strong>. Merge is not reversible.
      </p>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted mb-5">
        <span><kbd className="font-mono font-semibold text-text-secondary">m</kbd> merge</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">k</kbd> keep separate</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">d</kbd> defer</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">1–9</kbd> pick canonical</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">u</kbd> undo</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">← →</kbd> navigate</span>
      </div>

      {/* Cluster meta + recommendation */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5 mb-4 shadow-md">
        <div className="flex items-center gap-2 mb-3 text-xs">
          <span className="font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-surface-elevated text-text-secondary">
            {current.sport_key || "unknown"}
          </span>
          {current.espn_id && <span className="text-text-muted font-mono">espn_id {current.espn_id}</span>}
          <span className="ml-auto text-text-muted font-mono">{current.status}</span>
        </div>

        <div
          className={`mb-4 rounded-lg px-3 py-2 text-sm ${
            rec.action === "merge"
              ? "bg-emerald-50 text-emerald-800"
              : rec.action === "keep_separate"
              ? "bg-amber-50 text-amber-800"
              : "bg-surface-elevated text-text-secondary"
          }`}
        >
          <span className="font-semibold">Recommended: {VERDICT_LABEL[rec.action]}</span> — {rec.reason}
        </div>

        {/* Candidate rows side by side */}
        <div className="space-y-2">
          {current.members.map((m, i) => {
            const isCanonical = m.id === selectedCanonical;
            return (
              <button
                key={m.id}
                onClick={() => setCanonicalPick((p) => ({ ...p, [current.cluster_key]: m.id }))}
                className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                  isCanonical
                    ? "border-accent-brand bg-accent-brand/5 ring-1 ring-accent-brand/30"
                    : "border-surface-border bg-surface-card hover:bg-surface-elevated"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-text-muted w-4">{i + 1}</span>
                  <span className="font-semibold text-text-primary">{m.name}</span>
                  {isCanonical && (
                    <span className="text-micro font-bold uppercase tracking-wider text-accent-brand">
                      canonical
                    </span>
                  )}
                  <span className="ml-auto text-xs text-text-muted font-mono">id {m.id}</span>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-xs text-text-muted font-mono pl-6">
                  <span>/{m.slug}</span>
                  <span>{m.recent_events} recent</span>
                  <span>{m.total_events} total events</span>
                  <span>{m.mappings} mappings</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => handleVerdict("merge")}
          className="flex-1 py-3 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-600 transition-colors"
        >
          Merge into canonical (m)
        </button>
        <button
          onClick={() => handleVerdict("keep_separate")}
          className="flex-1 py-3 rounded-lg bg-amber-500 text-white font-semibold hover:bg-amber-600 transition-colors"
        >
          Keep separate (k)
        </button>
        <button
          onClick={() => handleVerdict("defer")}
          className="flex-1 py-3 rounded-lg bg-surface-elevated text-text-secondary font-semibold hover:bg-surface-border transition-colors"
        >
          Defer (d)
        </button>
      </div>
      <button
        onClick={handleUndo}
        disabled={session.history.length === 0}
        className="text-xs text-text-muted hover:text-text-primary disabled:opacity-30"
      >
        Undo last (u)
      </button>
    </div>
  );
}
