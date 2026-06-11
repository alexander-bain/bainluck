"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";

export default function LabelPassPage() {
  usePageTracking({ pageType: "admin_label_pass" });
  useScrollDepth({ pageType: "admin_label_pass" });
  useEngagementTime({ pageType: "admin_label_pass" });

  const { secret } = useAdminAuth();

  const { data, error, mutate } = useSWR(
    secret ? ["label-pass-pending", secret] : null,
    () => adminFetchJSON("/api/admin/label-pass/pending", secret)
  );
  const [index, setIndex] = useState(0);
  const [history, setHistory] = useState<Array<{ id: number; verdict: string }>>([]);
  const [submitting, setSubmitting] = useState(false);

  const items = (data as Record<string, unknown[]>)?.items || [];
  const current = items[index] as Record<string, unknown> | null || null;
  const total = items.length;
  const reviewed = history.length;

  const handleVerdict = useCallback(async (verdict: string) => {
    if (!current || submitting || !secret) return;
    setSubmitting(true);
    try {
      await adminFetchJSON("/api/admin/label-pass/verdict", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_id: (current as Record<string, unknown>).id, verdict, features: (current as Record<string, unknown>).features || {} }),
      });
      setHistory((h) => [...h, { id: (current as Record<string, unknown>).id as number, verdict }]);
      setIndex((i) => i + 1);
    } catch (e) {
      console.error(e);
    }
    setSubmitting(false);
  }, [current, submitting, secret]);

  const handleUndo = useCallback(() => {
    if (history.length === 0) return;
    setHistory((h) => h.slice(0, -1));
    setIndex((i) => Math.max(0, i - 1));
  }, [history]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case "j": handleVerdict("accept"); break;
        case "k": handleVerdict("reject"); break;
        case " ": e.preventDefault(); handleVerdict("skip"); break;
        case "u": handleUndo(); break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleVerdict, handleUndo]);

  if (!secret) return <div className="p-8 text-text-muted">Enter admin secret to access label pass.</div>;
  if (error) return <div className="p-8 text-red-500">Error loading proposals.</div>;
  if (!data) return <div className="p-8 text-text-muted">Loading...</div>;

  if (!current) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <h1 className="text-2xl font-bold mb-4">Label Pass Complete</h1>
        <p className="text-text-secondary">{reviewed} of {total} proposals reviewed.</p>
        <div className="mt-4 space-y-1">
          {history.map((h, i) => (
            <div key={i} className="text-xs text-text-muted">#{h.id} → {h.verdict}</div>
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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Label Speed Pass</h1>
        <span className="text-sm text-text-muted font-mono">{reviewed + 1} / {total}</span>
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

      {/* Actions */}
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => handleVerdict("accept")}
          disabled={submitting}
          className="flex-1 py-3 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-600 transition-colors disabled:opacity-50"
        >
          Accept (j)
        </button>
        <button
          onClick={() => handleVerdict("reject")}
          disabled={submitting}
          className="flex-1 py-3 rounded-lg bg-red-500 text-white font-semibold hover:bg-red-600 transition-colors disabled:opacity-50"
        >
          Reject (k)
        </button>
        <button
          onClick={() => handleVerdict("skip")}
          disabled={submitting}
          className="flex-1 py-3 rounded-lg bg-surface-elevated text-text-secondary font-semibold hover:bg-surface-border transition-colors disabled:opacity-50"
        >
          Skip (space)
        </button>
      </div>
      <button onClick={handleUndo} disabled={history.length === 0} className="text-xs text-text-muted hover:text-text-primary disabled:opacity-30">
        Undo last (u)
      </button>
    </div>
  );
}
