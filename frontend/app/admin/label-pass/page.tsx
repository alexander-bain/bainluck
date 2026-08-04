"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";
import { trackEvent } from "@/lib/analytics";
import {
  INITIAL_SESSION,
  keyToAction,
  recordVerdict,
  reconcileVerdict,
  rollbackVerdict,
  undoLast,
  navigate,
  sessionTotals,
  progressLabel,
  type Verdict,
} from "@/lib/labelPassSession";

export default function LabelPassPage() {
  usePageTracking({ pageType: "admin_label_pass" });
  useScrollDepth({ pageType: "admin_label_pass" });
  useEngagementTime({ pageType: "admin_label_pass" });

  const { secret } = useAdminAuth();

  const { data, error } = useSWR(
    secret ? ["label-pass-pending", secret] : null,
    () => adminFetchJSON("/api/admin/label-pass/pending", secret)
  );

  // L2-168: the whole session is a pure state machine (labelPassSession.ts) so
  // the velocity logic is node-testable; this component is a thin wiring shell.
  const [session, setSession] = useState(INITIAL_SESSION);
  const uidRef = useRef(0);

  const items = (data as Record<string, unknown[]>)?.items || [];
  const total = items.length;

  // #1542: lifecycle-safety summary — how many stale proposals were retired /
  // quarantined before Alex ever saw them, and any already-applied verdict now
  // on a stale market (review only, never auto-deleted).
  const lifecycle = data as {
    retired?: { count?: number; reasons?: Record<string, number> };
    quarantined?: { count?: number; reasons?: Record<string, number> };
    stale_applied_review?: { count?: number; reasons?: Record<string, number> };
  } | undefined;
  const retiredCount = lifecycle?.retired?.count || 0;
  const quarantinedCount = lifecycle?.quarantined?.count || 0;
  const staleAppliedCount = lifecycle?.stale_applied_review?.count || 0;
  const reasonSummary = (reasons?: Record<string, number>) =>
    Object.entries(reasons || {})
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
  const current = (items[session.index] as Record<string, unknown> | null) || null;
  const totals = sessionTotals(session);

  const handleVerdict = useCallback(
    (verdict: Verdict) => {
      if (!current || !secret) return;
      const c = current as Record<string, unknown>;
      const decisionId = c.id as number;
      // Arrow-navigation can land back on an already-decided card — never double-record.
      if (session.history.some((h) => h.id === decisionId)) return;

      const uid = ++uidRef.current;
      // Optimistic advance: the next card slides in immediately (no spinner-per-verdict).
      setSession((s) =>
        recordVerdict(s, { uid, id: decisionId, verdict, applied: false, pending: true })
      );

      (async () => {
        try {
          const res = (await adminFetchJSON("/api/admin/label-pass/verdict", secret, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision_id: decisionId, verdict, features: c.features || {} }),
          })) as { new_id?: number; applied?: boolean } | null;
          // #222: `applied` reflects reality — true only when an Accept applied a
          // live Discover-ranking term (kill switch on), false otherwise.
          const applied = verdict === "accept" ? Boolean(res?.applied) : false;
          trackEvent("eval_verdict", {
            verdict,
            decision_id: decisionId,
            proposal: ((c.decision as string) || "").replace("llm_proposed_", "") || undefined,
            item_name: (c.item_name as string) || undefined,
            category: (c.category as string) || undefined,
            applied,
            surface: "label_pass",
          });
          setSession((s) => reconcileVerdict(s, uid, { newId: res?.new_id, applied }));
        } catch (e) {
          console.error(e);
          // POST failed — drop the phantom verdict and step back so it can be retried.
          setSession((s) => rollbackVerdict(s, uid));
        }
      })();
    },
    [current, secret, session.history]
  );

  const handleUndo = useCallback(() => {
    const { state: next, undone } = undoLast(session);
    if (!undone) return;
    setSession(next);
    // #222 server-side undo: delete the verdict row so any applied ranking boost
    // is reverted and the proposal returns to the pending queue.
    if (undone.newId != null && secret) {
      (async () => {
        try {
          await adminFetchJSON("/api/admin/label-pass/undo", secret, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision_id: undone.newId }),
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
      const action = keyToAction(e.key);
      if (!action) return;
      if (action === "accept" || action === "reject" || action === "skip") {
        if (e.key === " ") e.preventDefault();
        handleVerdict(action);
      } else if (action === "undo") {
        handleUndo();
      } else if (action === "next" || action === "prev") {
        setSession((s) => navigate(s, action, total));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleVerdict, handleUndo, total]);

  if (!secret) return <div className="p-8 text-text-muted">Enter admin secret to access label pass.</div>;
  if (error) return <div className="p-8 text-red-500">Error loading proposals.</div>;
  if (!data) return <div className="p-8 text-text-muted">Loading...</div>;

  const lifecycleBanner = (retiredCount > 0 || quarantinedCount > 0 || staleAppliedCount > 0) ? (
    <div
      data-testid="lifecycle-summary"
      className="mb-4 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs text-text-secondary leading-relaxed"
    >
      <span className="font-semibold text-text-primary">Lifecycle filter:</span>{" "}
      {retiredCount} retired
      {retiredCount > 0 && lifecycle?.retired?.reasons && (
        <span className="text-text-muted"> ({reasonSummary(lifecycle.retired.reasons)})</span>
      )}
      {" · "}{quarantinedCount} quarantined
      {quarantinedCount > 0 && lifecycle?.quarantined?.reasons && (
        <span className="text-text-muted"> ({reasonSummary(lifecycle.quarantined.reasons)})</span>
      )}
      {staleAppliedCount > 0 && (
        <span className="text-accent-danger">
          {" · "}{staleAppliedCount} applied verdict{staleAppliedCount === 1 ? "" : "s"} now stale — review
        </span>
      )}
    </div>
  ) : null;

  if (!current) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <h1 className="text-2xl font-bold mb-4">Label Pass Complete</h1>
        {lifecycleBanner}
        <p className="text-text-secondary">{progressLabel(session, total)}.</p>
        {session.history.length > 0 && (
          <button
            onClick={handleUndo}
            className="mt-3 text-xs text-text-muted hover:text-text-primary"
          >
            Undo last (u)
          </button>
        )}
        <div className="mt-4 space-y-1">
          {session.history.map((h) => (
            <div key={h.uid} className="text-xs text-text-muted">
              #{h.id} → {h.verdict}
              {h.applied ? " · applied" : ""}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const item = current as Record<string, unknown>;
  const proposal = ((item.decision as string) || "").replace("llm_proposed_", "") || "unknown";
  const features = (item.features || {}) as Record<string, number | null>;
  const probPct = features.probability != null
    ? `${Math.round(features.probability * 100)}%`
    : "—";

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">Label Speed Pass</h1>
        <span className="text-sm text-text-muted font-mono">{session.index + 1} / {total}</span>
      </div>

      {lifecycleBanner}

      {/* L2-168 session progress strip — live counts reflect accepts in real time */}
      <div className="text-sm text-text-secondary font-mono mb-2" data-testid="progress-strip">
        {progressLabel(session, total)}
        {totals.applied > 0 && (
          // L2-169: "this session" disambiguates from the cockpit's persistent
          // all-time applied-boosts count (they are different numbers by design).
          <span className="ml-2 text-emerald-600">● {totals.applied} live boost{totals.applied === 1 ? "" : "s"} this session</span>
        )}
      </div>

      {/* #222 shipped: verdicts now steer live Discover ranking AND train the
          scorer. Accept applies a bounded, 14-day term; Reject suppresses + trains. */}
      <p className="text-xs text-text-muted mb-3 leading-relaxed">
        Accept promotes this market in Discover (bounded steer, expires in 14 days) and trains
        the scorer. Reject suppresses it and trains the scorer.
      </p>

      {/* Visible keyboard legend (L2-168) */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted mb-6">
        <span><kbd className="font-mono font-semibold text-text-secondary">a</kbd> accept</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">r</kbd> reject</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">s</kbd> skip</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">u</kbd> undo last</span>
        <span><kbd className="font-mono font-semibold text-text-secondary">← →</kbd> navigate</span>
      </div>

      {/* Card */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5 mb-6 shadow-md">
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
            proposal === "promote" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
          }`}>
            LLM: {proposal}
          </span>
          <span className="text-xs text-text-muted">{item.category as string}</span>
          <span className="ml-auto font-mono text-lg font-bold text-text-primary">{probPct}</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2 leading-tight">{item.item_name as string}</h2>
        {item.admin_notes && (
          <p className="text-sm text-text-secondary leading-relaxed mb-3">{item.admin_notes as string}</p>
        )}
        <div className="flex gap-4 text-xs text-text-muted">
          {features.movement_24h != null && (
            <span>24h: {features.movement_24h > 0 ? "+" : ""}{(features.movement_24h * 100).toFixed(1)}pts</span>
          )}
          {features.volume_24h != null && (
            <span>Vol: ${Math.round(features.volume_24h / 1000)}K</span>
          )}
          {item.archetype && <span>{item.archetype as string}</span>}
        </div>
      </div>

      {/* Actions — optimistic (never disabled; the next card slides in on click) */}
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => handleVerdict("accept")}
          className="flex-1 py-3 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-600 transition-colors"
        >
          Accept (a)
        </button>
        <button
          onClick={() => handleVerdict("reject")}
          className="flex-1 py-3 rounded-lg bg-red-500 text-white font-semibold hover:bg-red-600 transition-colors"
        >
          Reject (r)
        </button>
        <button
          onClick={() => handleVerdict("skip")}
          className="flex-1 py-3 rounded-lg bg-surface-elevated text-text-secondary font-semibold hover:bg-surface-border transition-colors"
        >
          Skip (s)
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
