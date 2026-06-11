"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

const ADMIN_TOKEN = typeof window !== "undefined" ? localStorage.getItem("admin_token") || "" : "";

async function fetchPending() {
  const res = await fetch(`/api/admin/label-pass/pending?secret=${ADMIN_TOKEN}`);
  if (!res.ok) throw new Error("Failed to load");
  return res.json();
}

async function submitVerdict(id: number, verdict: string, features: Record<string, unknown>) {
  const res = await fetch(`/api/admin/label-pass/verdict?secret=${ADMIN_TOKEN}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision_id: id, verdict, features }),
  });
  if (!res.ok) throw new Error("Failed to submit");
  return res.json();
}

export default function LabelPassPage() {
  usePageTracking({ pageType: "admin_label_pass" });
  useScrollDepth({ pageType: "admin_label_pass" });
  useEngagementTime({ pageType: "admin_label_pass" });

  const { data, error, mutate } = useSWR("label-pass-pending", fetchPending);
  const [index, setIndex] = useState(0);
  const [history, setHistory] = useState<Array<{ id: number; verdict: string }>>([]);
  const [submitting, setSubmitting] = useState(false);

  const items = data?.items || [];
  const current = items[index] || null;
  const total = items.length;
  const reviewed = history.length;

  const handleVerdict = useCallback(async (verdict: string) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await submitVerdict(current.id, verdict, current.features || {});
      setHistory((h) => [...h, { id: current.id, verdict }]);
      setIndex((i) => i + 1);
    } catch (e) {
      console.error(e);
    }
    setSubmitting(false);
  }, [current, submitting]);

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

  if (error) return <div className="p-8 text-red-500">Error loading proposals. Set admin_token in localStorage.</div>;
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

  const proposal = current.decision?.replace("llm_proposed_", "") || "unknown";
  const probPct = current.features?.probability != null
    ? `${Math.round(current.features.probability * 100)}%`
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
          <span className="text-xs text-text-muted">{current.category}</span>
          <span className="ml-auto font-mono text-lg font-bold text-text-primary">{probPct}</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2 leading-tight">{current.item_name}</h2>
        {current.admin_notes && (
          <p className="text-sm text-text-secondary leading-relaxed mb-3">{current.admin_notes}</p>
        )}
        <div className="flex gap-4 text-xs text-text-muted">
          {current.features?.movement_24h != null && (
            <span>24h: {current.features.movement_24h > 0 ? "+" : ""}{(current.features.movement_24h * 100).toFixed(1)}pts</span>
          )}
          {current.features?.volume_24h != null && (
            <span>Vol: ${Math.round(current.features.volume_24h / 1000)}K</span>
          )}
          {current.archetype && <span>{current.archetype}</span>}
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
